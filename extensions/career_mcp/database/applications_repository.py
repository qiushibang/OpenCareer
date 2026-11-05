"""SQLite persistence for personal applications; never part of the public feed."""
from __future__ import annotations

import json
import sqlite3
from uuid import uuid4
from datetime import datetime
from zoneinfo import ZoneInfo

from ..domain.applications import DEFAULTS, ROUND_DEFAULTS, STATUS_LABELS, annual_salary


def unpack(row: sqlite3.Row) -> dict:
    defaults = ROUND_DEFAULTS if "application_id" in row.keys() else DEFAULTS
    result = {**defaults, **json.loads(row["data_json"]), **{key: row[key] for key in row.keys() if key != "data_json"}}
    if defaults is DEFAULTS:
        result["annual_salary"] = annual_salary(result["monthly_salary"], result["salary_months"])
    return result


class ApplicationsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, application_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM career_applications WHERE id=?", (application_id,)).fetchone()
        return unpack(row) if row else None

    def records(self) -> list[dict]:
        return [unpack(row) for row in self.connection.execute("SELECT * FROM career_applications ORDER BY updated_at DESC,id")]

    def current(self, job_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM career_applications WHERE job_id=? AND is_current=1", (job_id,)).fetchone()
        return unpack(row) if row else None

    def insert(self, data: dict, now: str, *, job_id: str | None = None, migrated_job_id: str | None = None) -> str:
        application_id = str(uuid4())
        if job_id:
            self.connection.execute("UPDATE career_applications SET is_current=0 WHERE job_id=?", (job_id,))
        self.connection.execute("INSERT INTO career_applications(id,job_id,migrated_job_id,data_json,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                                (application_id, job_id, migrated_job_id, json.dumps(data, ensure_ascii=False), now, now))
        return application_id

    def update(self, application_id: str, data: dict, expected_version: int, now: str) -> None:
        changed = self.connection.execute("UPDATE career_applications SET data_json=?,version=version+1,updated_at=? WHERE id=? AND version=?",
                                          (json.dumps(data, ensure_ascii=False), now, application_id, expected_version))
        if changed.rowcount != 1:
            raise ValueError("VERSION_CONFLICT：记录已更新，请刷新后再保存；当前草稿不会自动覆盖。")

    def event(self, application_id: str, kind: str, summary: str, now: str) -> None:
        self.connection.execute("INSERT INTO career_application_history VALUES (?,?,?,?,?)", (str(uuid4()), application_id, kind, summary, now))

    def history(self, application_id: str) -> list[dict]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM career_application_history WHERE application_id=? ORDER BY occurred_at DESC,rowid DESC", (application_id,))]

    def interviews(self, application_id: str) -> list[dict]:
        return [unpack(row) for row in self.connection.execute("SELECT * FROM career_application_interviews WHERE application_id=? ORDER BY created_at,rowid", (application_id,))]

    def save_interview(self, application_id: str, data: dict, now: str, interview_id: str | None, version: int | None) -> dict:
        if interview_id:
            changed = self.connection.execute("UPDATE career_application_interviews SET data_json=?,updated_at=?,version=version+1 WHERE id=? AND application_id=? AND version=?",
                (json.dumps(data, ensure_ascii=False), now, interview_id, application_id, version))
            if changed.rowcount != 1:
                raise ValueError("VERSION_CONFLICT：本轮面试已更新，请刷新后再保存。")
        else:
            interview_id = str(uuid4())
            self.connection.execute("INSERT INTO career_application_interviews(id,application_id,data_json,created_at,updated_at) VALUES (?,?,?,?,?)", (interview_id, application_id, json.dumps(data, ensure_ascii=False), now, now))
        return next(row for row in self.interviews(application_id) if row["id"] == interview_id)

    def job_snapshot(self, job_id: str) -> dict:
        row = self.connection.execute("SELECT j.*,c.name AS company FROM jobs j JOIN companies c ON c.id=j.company_id WHERE j.id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("岗位不存在，无法加入进度。")
        tracking = self.connection.execute("SELECT * FROM job_tracking WHERE job_id=?", (job_id,)).fetchone()
        data = {**DEFAULTS, "company": row["company"], "title": row["title"] or "未命名岗位", "location": "、".join(json.loads(row["locations_json"])),
                "jd": row["description_raw"], "source_url": row["canonical_url"] if str(row["canonical_url"]).startswith(("http://", "https://")) else "",
                "recruitment_type": "experienced" if row["recruitment_type"] == "social" else row["recruitment_type"] if row["recruitment_type"] in {"experienced", "internship", "campus"} else ""}
        if tracking:
            data.update(status=tracking["application_status"] if tracking["application_status"] != "not_started" else "preparing", notes=tracking["note"] or "")
            if tracking["applied_at"]:
                data["applied_on"] = datetime.fromisoformat(tracking["applied_at"].replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                data["applied_date_source"] = "legacy_tracking"
        return data

    def migrate_legacy(self) -> None:
        rows = self.connection.execute("""SELECT t.* FROM job_tracking t WHERE (t.application_status!='not_started' OR t.applied_at IS NOT NULL)
            AND NOT EXISTS(SELECT 1 FROM career_applications a WHERE a.migrated_job_id=t.job_id OR (a.job_id=t.job_id AND a.is_current=1))""").fetchall()
        for row in rows:
            application_id = self.insert(self.job_snapshot(row["job_id"]), row["created_at"], job_id=row["job_id"], migrated_job_id=row["job_id"])
            self.connection.execute("UPDATE career_applications SET updated_at=? WHERE id=?", (row["updated_at"], application_id))
            for event in self.connection.execute("SELECT * FROM job_application_events WHERE job_id=? ORDER BY occurred_at", (row["job_id"],)):
                self.event(application_id, "legacy_status", f"保留原进度：{STATUS_LABELS.get(event['from_status'], '原状态')} → {STATUS_LABELS.get(event['to_status'], '原状态')}", event["occurred_at"])
            self.event(application_id, "migrated", "已保留旧申请进度与备注；历史面试轮次未推断", row["updated_at"])

    def mirror_tracking(self, application: dict, now: str) -> None:
        if not application["job_id"] or not application["is_current"]:
            return
        from .job_tracking_repository import JobTrackingRepository
        tracking = JobTrackingRepository(self.connection)
        old = tracking.get(application["job_id"])
        applied_at = application["applied_on"] + "T00:00:00+08:00" if application["applied_on"] else None
        if old and old["applied_at"] and application["applied_on"]:
            old_day = datetime.fromisoformat(old["applied_at"].replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            if old_day == application["applied_on"]:
                applied_at = old["applied_at"]
        values = {"job_id": application["job_id"], "is_favorite": old["is_favorite"] if old else False,
                  "favorited_at": old["favorited_at"] if old else None, "application_status": application["status"],
                  "applied_at": applied_at,
                  "note": application["notes"] or None, "created_at": old["created_at"] if old else now, "updated_at": now}
        if old and all(old[key] == values[key] for key in ("application_status", "applied_at", "note")):
            return
        if old:
            tracking.update_if_version(values, old["version"])
        else:
            tracking.insert(values)
        if not old or old["application_status"] != values["application_status"]:
            tracking.add_status_event(event_id=str(uuid4()), job_id=application["job_id"], from_status=old["application_status"] if old else "not_started", to_status=values["application_status"], occurred_at=now)


def tracking_changed(connection: sqlite3.Connection, tracking: dict) -> None:
    """Transaction-local compatibility bridge; no second writer/connection."""
    repo = ApplicationsRepository(connection)
    repo.migrate_legacy()
    app = repo.current(tracking["job_id"])
    if app:
        data = {key: app[key] for key in DEFAULTS}
        data.update(status=tracking["application_status"], notes=tracking["note"] or "")
        data["applied_on"] = datetime.fromisoformat(tracking["applied_at"].replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() if tracking["applied_at"] else None
        if data["applied_on"] != app["applied_on"]:
            data["applied_date_source"] = "legacy_tracking" if data["applied_on"] else "unknown"
        if all(data[key] == app[key] for key in DEFAULTS):
            return
        repo.update(app["id"], data, app["version"], tracking["updated_at"])
        repo.event(app["id"], "legacy_edit", "通过岗位详情更新申请状态或备注", tracking["updated_at"])
