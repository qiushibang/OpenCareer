"""Local-first personal application workflow, separate from official job state."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
import json
from decimal import Decimal

from ..config import CareerConfig
from ..database.applications_repository import ApplicationsRepository
from ..database.migrations import connect, migrate
from ..domain.applications import DEFAULTS, ROUND_DEFAULTS, FIELD_LABELS, normalize, validate_record


OFFICIAL_FIELDS = {"company", "title", "location", "recruitment_type", "department", "business_line", "source_url", "jd"}


class Applications:
    def __init__(self, config: CareerConfig | None = None, *, repository_session=None) -> None:
        # Hosted deployments inject a per-tenant PostgreSQL repository session;
        # local mode keeps using the SQLite file.
        self._repository_session = repository_session
        self.config = config or (None if repository_session else CareerConfig.from_env())

    @contextmanager
    def _session(self) -> Iterator[ApplicationsRepository]:
        if self._repository_session is not None:
            with self._repository_session() as repo:
                repo.migrate_legacy()
                yield repo
            return
        db = connect(self.config.database_path)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            migrate(db)
            db.execute("BEGIN IMMEDIATE")
            repo = ApplicationsRepository(db)
            repo.migrate_legacy()
            yield repo
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _get(repo: ApplicationsRepository, application_id: str) -> dict:
        result = repo.get(application_id)
        if result is None:
            raise ValueError("NOT_FOUND：申请记录不存在。")
        return result

    def create(self, body: dict) -> dict:
        if not isinstance(body, dict):
            raise ValueError("记录必须是对象。")
        body = dict(body)
        job_id, new_attempt = body.pop("job_id", None), body.pop("new_attempt", False)
        if type(new_attempt) is not bool or (job_id is not None and (not isinstance(job_id, str) or len(job_id) > 100)):
            raise ValueError("岗位标识或新申请选项不正确。")
        with self._session() as repo:
            old = repo.current(job_id) if job_id else None
            if old and not new_attempt:
                return old
            snapshot = repo.job_snapshot(job_id) if job_id else DEFAULTS
            patch = normalize(body)
            if job_id and any(key in patch and patch[key] != snapshot[key] for key in OFFICIAL_FIELDS):
                raise ValueError("官网岗位信息不可修改，请以官网为准。")
            data = {**snapshot, **patch}
            if new_attempt:
                data.update(status="preparing", stage="", applied_on=None, applied_date_source="unknown", notes="")
            elif body.get("applied_on"):
                data["applied_date_source"] = "user_confirmed"
            validate_record(data)
            self._resume(repo, data)
            application_id = repo.insert(data, self._now(), job_id=job_id)
            repo.event(application_id, "created", "加入求职进度，尚未代表投递成功", self._now())
            repo.mirror_tracking(self._get(repo, application_id), self._now())
            return self._get(repo, application_id)

    def update(self, application_id: str, body: dict) -> dict:
        if not isinstance(body, dict):
            raise ValueError("记录必须是对象。")
        body = dict(body)
        version = body.pop("expected_version", None)
        if type(version) is not int or version < 1:
            raise ValueError("请提供当前记录版本。")
        patch = normalize(body)
        with self._session() as repo:
            old = self._get(repo, application_id)
            if version != old["version"]:
                raise ValueError("VERSION_CONFLICT：记录已更新，请读取最新记录后再保存；草稿保留。")
            if old["job_id"] and any(key in patch and patch[key] != old[key] for key in OFFICIAL_FIELDS):
                raise ValueError("官网岗位信息不可修改，请以官网为准。")
            data = {**{key: old[key] for key in DEFAULTS}, **patch}
            if "applied_on" in patch and patch["applied_on"] != old["applied_on"]:
                data["applied_date_source"] = "user_confirmed" if patch["applied_on"] else "unknown"
            validate_record(data)
            if "resume_import_id" in patch and patch["resume_import_id"] != old["resume_import_id"]:
                self._resume(repo, data, replace_label="resume_label" not in patch or patch.get("resume_label") == old["resume_label"])
            changed = [key for key in DEFAULTS if data[key] != old[key]]
            if not changed:
                return old
            repo.update(application_id, data, version, self._now())
            repo.event(application_id, "updated", "更新申请：" + "、".join(FIELD_LABELS.get(key, "信息") for key in changed), self._now())
            saved = self._get(repo, application_id)
            repo.mirror_tracking(saved, self._now())
            return saved

    @staticmethod
    def _resume(repo: ApplicationsRepository, data: dict, *, replace_label: bool = False) -> None:
        if not data["resume_import_id"]:
            data["resume_sha256"] = ""
            return
        row = repo.resume_option(data["resume_import_id"])
        if row is None:
            raise ValueError("所选简历已不可用，请重新选择；申请内容不会清除。")
        data["resume_sha256"] = row["content_hash"]
        if replace_label or not data["resume_label"]:
            data["resume_label"] = row["display_name"] or row["original_filename"]

    def get(self, application_id: str) -> dict:
        with self._session() as repo:
            return {**self._get(repo, application_id), "history": repo.history(application_id), "interviews": repo.interviews(application_id)}

    @staticmethod
    def _filtered(records: list[dict], filters: dict) -> list[dict]:
        allowed = {"q", "company", "location", "status", "stage", "recruitment_type", "batch", "tag", "priority", "view", "archived", "include_archived", "applied_from", "applied_to", "sort", "descending", "due_only"}
        if not isinstance(filters, dict) or set(filters) - allowed:
            raise ValueError("筛选字段不正确。")
        for key, value in filters.items():
            if key in {"archived", "include_archived", "descending", "due_only"}:
                if type(value) is not bool:
                    raise ValueError("筛选选项须为布尔值。")
            elif not isinstance(value, str) or len(value) > 300:
                raise ValueError("筛选值类型或长度不正确。")
        if filters.get("view", "all") not in {"all", "preparing", "interviewing", "followup", "offer", "closed", "archived"}:
            raise ValueError("未知视图。")
        sort = filters.get("sort", "updated_at")
        if sort not in {"company", "title", "location", "status", "stage", "priority", "applied_on", "next_at", "updated_at", "next_action", "recruitment_type", "batch", "department", "business_line", "channel", "annual_salary", "salary_months", "monthly_salary", "salary_advertised", "salary_expected", "salary_offer", "resume_label", "deadline_on"}:
            raise ValueError("不支持的排序字段。")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        def match(row: dict) -> bool:
            view = filters.get("view", "all")
            if not filters.get("include_archived") and bool(row["archived"]) != (view == "archived" or filters.get("archived", False)):
                return False
            if view == "preparing" and row["status"] not in {"not_started", "preparing"}: return False
            if view == "interviewing" and row["status"] != "interviewing": return False
            if view == "offer" and row["status"] not in {"offer", "accepted"}: return False
            if view == "closed" and row["status"] not in {"accepted", "rejected", "withdrawn"}: return False
            if view == "followup" and (not row["next_action"] or row["next_done"]): return False
            if filters.get("due_only") and (not row["next_at"] or row["next_done"] or datetime.fromisoformat(row["next_at"].replace("Z", "+00:00")) > datetime.fromisoformat(now.replace("Z", "+00:00"))): return False
            for key in ("company", "location", "stage", "batch"):
                if filters.get(key) and filters[key].casefold() not in row[key].casefold(): return False
            for key in ("status", "recruitment_type", "priority"):
                if filters.get(key) and filters[key] != row[key]: return False
            if filters.get("tag") and filters["tag"] not in row["tags"]: return False
            if filters.get("applied_from") and (not row["applied_on"] or row["applied_on"] < filters["applied_from"]): return False
            if filters.get("applied_to") and (not row["applied_on"] or row["applied_on"] > filters["applied_to"]): return False
            q = filters.get("q", "").casefold()
            return not q or q in "\n".join(str(row.get(key, "")) for key in ("company", "title", "location", "stage", "jd", "notes", "tags")).casefold()
        def sort_key(row: dict) -> tuple:
            value = {"high":0,"normal":1,"low":2}.get(row["priority"],1) if sort == "priority" else str(row.get(sort) or "")
            if sort == "annual_salary":
                value = Decimal(row.get("annual_salary") or "0")
            elif sort == "salary_months":
                value = row.get("salary_months") or 0
            return value, row["id"]
        return sorted((row for row in records if match(row)), key=sort_key, reverse=filters.get("descending", True))

    def list(self, filters: dict | None = None, *, limit: int = 50, offset: int = 0) -> dict:
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise ValueError("分页范围不正确。")
        with self._session() as repo:
            all_rows = repo.records()
            rows = self._filtered(all_rows, {} if filters is None else filters)
            page = [{key: value for key, value in row.items() if key not in {"jd", "notes"}} for row in rows[offset:offset + limit]]
            return {"records": page, "total": len(rows), "limit": limit, "offset": offset,
                    "summary": {"active": sum(not row["archived"] for row in all_rows), "interviewing": sum(not row["archived"] and row["status"] == "interviewing" for row in all_rows), "offer": sum(not row["archived"] and row["status"] in {"offer", "accepted"} for row in all_rows)}}

    def save_interview(self, application_id: str, body: dict, interview_id: str | None = None) -> dict:
        body = dict(body)
        version, set_stage = body.pop("expected_version", None), body.pop("set_current_stage", False)
        if type(set_stage) is not bool or (interview_id and (type(version) is not int or version < 1)):
            raise ValueError("面试版本或阶段选项不正确。")
        patch = normalize(body, interview=True)
        with self._session() as repo:
            app = self._get(repo, application_id)
            old = next((row for row in repo.interviews(application_id) if row["id"] == interview_id), None) if interview_id else None
            if interview_id and old is None:
                raise ValueError("NOT_FOUND：面试记录不存在。")
            data = {**(old or ROUND_DEFAULTS), **patch}
            data = {key: data[key] for key in ROUND_DEFAULTS}
            validate_record(data, interview=True)
            saved = repo.save_interview(application_id, data, self._now(), interview_id, version)
            app_data = {key: app[key] for key in DEFAULTS}
            if set_stage:
                app_data["stage"] = data["round_name"]
                if app_data["status"] not in {"offer", "accepted", "rejected", "withdrawn"}:
                    app_data["status"] = "interviewing"
            repo.update(application_id, app_data, app["version"], self._now())
            repo.mirror_tracking(self._get(repo, application_id), self._now())
            outcome = {"pending":"待反馈", "passed":"通过", "failed":"未通过", "unknown":"未记录"}[data["result"]]
            repo.event(application_id, "interview", f"{'更新' if interview_id else '新增'}真实面试：{data['round_name']}；结果{outcome}", self._now())
            return saved

    def delete_interview(self, application_id: str, interview_id: str, body: dict) -> dict:
        if not isinstance(body, dict) or set(body) != {"expected_version"} or type(body["expected_version"]) is not int:
            raise ValueError("请提供当前面试记录版本。")
        with self._session() as repo:
            app = self._get(repo, application_id)
            old = next((row for row in repo.interviews(application_id) if row["id"] == interview_id), None)
            if old is None:
                raise ValueError("NOT_FOUND：面试记录不存在。")
            if body["expected_version"] != old["version"]:
                raise ValueError("VERSION_CONFLICT：本轮面试已更新，请刷新后再删除。")
            if not repo.delete_interview(application_id, interview_id, old["version"]):
                raise ValueError("VERSION_CONFLICT：本轮面试已更新，请刷新后再删除。")
            repo.update(application_id, {key: app[key] for key in DEFAULTS}, app["version"], self._now())
            repo.event(application_id, "interview_deleted", f"删除真实面试：{old['round_name']}；申请状态与阶段保留", self._now())
            return {"deleted": True}

    def export(self, body: dict) -> dict:
        if not isinstance(body, dict) or set(body) - {"filters", "ids"}:
            raise ValueError("导出参数不正确。")
        ids = body.get("ids")
        if ids is not None and (not isinstance(ids, list) or len(ids) > 10000 or any(not isinstance(v, str) or len(v) > 100 for v in ids)):
            raise ValueError("所选记录范围不正确。")
        with self._session() as repo:
            rows = self._filtered(repo.records(), body.get("filters", {}))
            if ids is not None:
                rows = [row for row in rows if row["id"] in ids]
                if {row["id"] for row in rows} != set(ids):
                    raise ValueError("部分所选申请已不在当前筛选范围，请刷新后重试。")
            if len(rows) > 10000:
                raise ValueError("导出超过10000条，请缩小范围；未导出不完整文件。")
            applications = [{key: row[key] for key in (*DEFAULTS, "annual_salary", "id", "job_id", "created_at", "updated_at")} for row in rows]
            rounds = [interview for row in rows for interview in repo.interviews(row["id"])]
            result = {"applications": applications, "interviews": rounds, "generated_at": self._now(), "timezone": "Asia/Shanghai", "total": len(rows)}
            if len(json.dumps(result, ensure_ascii=False).encode()) > 32 * 1024 * 1024:
                raise ValueError("导出正文超过32MB，请缩小范围；未截断正文。")
            return result
