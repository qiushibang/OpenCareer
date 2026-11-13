"""PostgreSQL persistence for tenant-owned personal applications (求职进度).

Same contract as extensions.career_mcp.database.applications_repository, but
every statement is scoped to the principal and protected by row level security.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from coworker.server.identity import Principal
from coworker.storage.postgres.job_tracking import PostgresJobTrackingRepository
from extensions.career_mcp.database.applications_repository import (
    mirror_application_to_tracking,
)
from extensions.career_mcp.domain.applications import (
    DEFAULTS,
    ROUND_DEFAULTS,
    STATUS_LABELS,
    annual_salary,
)

_VERSION_CONFLICT = "VERSION_CONFLICT：记录已更新，请刷新后再保存；当前草稿不会自动覆盖。"
_NOT_STARTED = "not_started"


def _iso(value: object) -> str | None:
    """ISO-8601 UTC with a trailing Z, the format the SQLite build stores."""
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


class PostgresApplicationsRepository:
    def __init__(self, connection, principal: Principal) -> None:
        self.connection = connection
        self.principal = principal

    # ---- row mapping -------------------------------------------------
    @staticmethod
    def _application(row) -> dict:
        data = dict(row[5] or {})
        result = {
            **DEFAULTS,
            **data,
            "id": row[0],
            "job_id": row[1],
            "migrated_job_id": row[2],
            "is_current": int(bool(row[3])),
            "version": int(row[4]),
            "created_at": _iso(row[6]),
            "updated_at": _iso(row[7]),
        }
        result["annual_salary"] = annual_salary(
            result["monthly_salary"], result["salary_months"]
        )
        return result

    @staticmethod
    def _interview(row) -> dict:
        return {
            **ROUND_DEFAULTS,
            **dict(row[3] or {}),
            "id": row[0],
            "application_id": row[1],
            "version": int(row[2]),
            "created_at": _iso(row[4]),
            "updated_at": _iso(row[5]),
        }

    _APPLICATION_COLUMNS = (
        "id, job_id, migrated_job_id, is_current, version, data, "
        "created_at, updated_at"
    )

    # ---- applications ------------------------------------------------
    def get(self, application_id: str) -> dict | None:
        row = self.connection.execute(
            f"SELECT {self._APPLICATION_COLUMNS} FROM career.applications "
            "WHERE user_id = %s AND id = %s",
            (self.principal.user_id, application_id),
        ).fetchone()
        return self._application(row) if row else None

    def records(self) -> list[dict]:
        rows = self.connection.execute(
            f"SELECT {self._APPLICATION_COLUMNS} FROM career.applications "
            "WHERE user_id = %s ORDER BY updated_at DESC, id",
            (self.principal.user_id,),
        ).fetchall()
        return [self._application(row) for row in rows]

    def _lock_job(self, job_id: str) -> None:
        # Serialise concurrent "add to progress" clicks for the same job; the
        # partial unique index would otherwise turn the race into a 500.
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"application:{self.principal.user_id}:{job_id}",),
        )

    def current(self, job_id: str) -> dict | None:
        self._lock_job(job_id)
        row = self.connection.execute(
            f"SELECT {self._APPLICATION_COLUMNS} FROM career.applications "
            "WHERE user_id = %s AND job_id = %s AND is_current",
            (self.principal.user_id, job_id),
        ).fetchone()
        return self._application(row) if row else None

    def insert(
        self,
        data: dict,
        now: str,
        *,
        job_id: str | None = None,
        migrated_job_id: str | None = None,
    ) -> str:
        application_id = str(uuid4())
        if job_id:
            self._lock_job(job_id)
            self.connection.execute(
                "UPDATE career.applications SET is_current = FALSE "
                "WHERE user_id = %s AND job_id = %s",
                (self.principal.user_id, job_id),
            )
        self.connection.execute(
            "INSERT INTO career.applications("
            "id, user_id, job_id, migrated_job_id, data, created_at, updated_at"
            ") VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)",
            (
                application_id,
                self.principal.user_id,
                job_id,
                migrated_job_id,
                _json(data),
                now,
                now,
            ),
        )
        return application_id

    def update(
        self, application_id: str, data: dict, expected_version: int, now: str
    ) -> None:
        changed = self.connection.execute(
            "UPDATE career.applications "
            "SET data = %s::jsonb, version = version + 1, updated_at = %s "
            "WHERE user_id = %s AND id = %s AND version = %s",
            (_json(data), now, self.principal.user_id, application_id, expected_version),
        )
        if changed.rowcount != 1:
            raise ValueError(_VERSION_CONFLICT)

    # ---- history -----------------------------------------------------
    def event(self, application_id: str, kind: str, summary: str, now: str) -> None:
        self.connection.execute(
            "INSERT INTO career.application_history("
            "id, user_id, application_id, event_type, summary, occurred_at"
            ") VALUES (%s, %s, %s, %s, %s, %s)",
            (str(uuid4()), self.principal.user_id, application_id, kind, summary, now),
        )

    def history(self, application_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT id, application_id, event_type, summary, occurred_at "
            "FROM career.application_history "
            "WHERE user_id = %s AND application_id = %s "
            "ORDER BY occurred_at DESC, id DESC",
            (self.principal.user_id, application_id),
        ).fetchall()
        return [
            {
                "id": row[0],
                "application_id": row[1],
                "event_type": row[2],
                "summary": row[3],
                "occurred_at": _iso(row[4]),
            }
            for row in rows
        ]

    # ---- interviews --------------------------------------------------
    _INTERVIEW_COLUMNS = "id, application_id, version, data, created_at, updated_at"

    def interviews(self, application_id: str) -> list[dict]:
        rows = self.connection.execute(
            f"SELECT {self._INTERVIEW_COLUMNS} FROM career.application_interviews "
            "WHERE user_id = %s AND application_id = %s ORDER BY created_at, id",
            (self.principal.user_id, application_id),
        ).fetchall()
        return [self._interview(row) for row in rows]

    def save_interview(
        self,
        application_id: str,
        data: dict,
        now: str,
        interview_id: str | None,
        version: int | None,
    ) -> dict:
        if interview_id:
            changed = self.connection.execute(
                "UPDATE career.application_interviews "
                "SET data = %s::jsonb, updated_at = %s, version = version + 1 "
                "WHERE user_id = %s AND id = %s AND application_id = %s AND version = %s",
                (_json(data), now, self.principal.user_id, interview_id, application_id, version),
            )
            if changed.rowcount != 1:
                raise ValueError("VERSION_CONFLICT：本轮面试已更新，请刷新后再保存。")
        else:
            interview_id = str(uuid4())
            self.connection.execute(
                "INSERT INTO career.application_interviews("
                "id, user_id, application_id, data, created_at, updated_at"
                ") VALUES (%s, %s, %s, %s::jsonb, %s, %s)",
                (interview_id, self.principal.user_id, application_id, _json(data), now, now),
            )
        return next(row for row in self.interviews(application_id) if row["id"] == interview_id)

    def delete_interview(self, application_id: str, interview_id: str, version: int) -> bool:
        return (
            self.connection.execute(
                "DELETE FROM career.application_interviews "
                "WHERE user_id = %s AND id = %s AND application_id = %s AND version = %s",
                (self.principal.user_id, interview_id, application_id, version),
            ).rowcount
            == 1
        )

    # ---- resumes and jobs -------------------------------------------
    def resume_option(self, resume_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT data, content_hash FROM career.resume_imports "
            "WHERE user_id = %s AND id = %s",
            (self.principal.user_id, resume_id),
        ).fetchone()
        if row is None:
            return None
        data = dict(row[0] or {})
        if data.get("status") == "deleted" or data.get("deleted_at"):
            return None
        return {
            "display_name": data.get("display_name") or "",
            "original_filename": data.get("filename") or "",
            "content_hash": row[1],
        }

    def job_snapshot(self, job_id: str) -> dict:
        row = self.connection.execute(
            "SELECT j.title, j.locations, j.description_raw, j.canonical_url, "
            "j.recruitment_type, c.name "
            "FROM career.visible_jobs j JOIN catalog.companies c ON c.id = j.company_id "
            "WHERE j.id = %s",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError("岗位不存在，无法加入进度。")
        title, locations, description, url, recruitment_type, company = row
        data = {
            **DEFAULTS,
            "company": company,
            "title": title or "未命名岗位",
            "location": "、".join(locations or []),
            "jd": description,
            "source_url": url if str(url).startswith(("http://", "https://")) else "",
            "recruitment_type": (
                "experienced"
                if recruitment_type == "social"
                else recruitment_type
                if recruitment_type in {"experienced", "internship", "campus"}
                else ""
            ),
        }
        tracking = PostgresJobTrackingRepository(self.connection, self.principal).get(job_id)
        if tracking:
            status = tracking["application_status"]
            data.update(
                status=status if status != _NOT_STARTED else "preparing",
                notes=tracking["note"] or "",
            )
            if tracking["applied_at"]:
                data["applied_on"] = (
                    datetime.fromisoformat(str(tracking["applied_at"]).replace("Z", "+00:00"))
                    .astimezone(ZoneInfo("Asia/Shanghai"))
                    .date()
                    .isoformat()
                )
                data["applied_date_source"] = "legacy_tracking"
        return data

    # ---- legacy bridge ----------------------------------------------
    def migrate_legacy(self) -> None:
        """Turn pre-existing per-job tracking into applications, once per job."""
        uid = self.principal.user_id
        rows = self.connection.execute(
            "SELECT t.job_id, t.created_at, t.updated_at FROM career.job_tracking t "
            "WHERE t.user_id = %s "
            "AND (coalesce(t.data->>'application_status', 'not_started') <> 'not_started' "
            "     OR t.data->>'applied_at' IS NOT NULL) "
            "AND NOT EXISTS (SELECT 1 FROM career.applications a "
            "    WHERE a.user_id = t.user_id "
            "      AND (a.migrated_job_id = t.job_id OR (a.job_id = t.job_id AND a.is_current)))",
            (uid,),
        ).fetchall()
        for job_id, created_at, updated_at in rows:
            self._lock_job(job_id)
            try:
                snapshot = self.job_snapshot(job_id)
            except ValueError:
                continue  # the job is no longer visible; keep the tracking row untouched
            application_id = self.insert(
                snapshot, _iso(created_at), job_id=job_id, migrated_job_id=job_id
            )
            self.connection.execute(
                "UPDATE career.applications SET updated_at = %s WHERE user_id = %s AND id = %s",
                (updated_at, uid, application_id),
            )
            events = self.connection.execute(
                "SELECT data, occurred_at FROM career.job_application_events "
                "WHERE user_id = %s AND job_id = %s ORDER BY occurred_at",
                (uid, job_id),
            ).fetchall()
            for data, occurred_at in events:
                data = dict(data or {})
                self.event(
                    application_id,
                    "legacy_status",
                    "保留原进度："
                    f"{STATUS_LABELS.get(data.get('from_status'), '原状态')} → "
                    f"{STATUS_LABELS.get(data.get('to_status'), '原状态')}",
                    _iso(occurred_at),
                )
            self.event(
                application_id,
                "migrated",
                "已保留旧申请进度与备注；历史面试轮次未推断",
                _iso(updated_at),
            )

    def mirror_tracking(self, application: dict, now: str) -> None:
        mirror_application_to_tracking(
            PostgresJobTrackingRepository(self.connection, self.principal),
            application,
            now,
        )


def tracking_changed(connection, principal: Principal, tracking: dict) -> None:
    """Keep the current application in step when job tracking is edited directly."""
    repo = PostgresApplicationsRepository(connection, principal)
    repo.migrate_legacy()
    app = repo.current(tracking["job_id"])
    if not app:
        return
    data = {key: app[key] for key in DEFAULTS}
    data.update(status=tracking["application_status"], notes=tracking["note"] or "")
    data["applied_on"] = (
        datetime.fromisoformat(str(tracking["applied_at"]).replace("Z", "+00:00"))
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .date()
        .isoformat()
        if tracking["applied_at"]
        else None
    )
    if data["applied_on"] != app["applied_on"]:
        data["applied_date_source"] = "legacy_tracking" if data["applied_on"] else "unknown"
    if all(data[key] == app[key] for key in DEFAULTS):
        return
    repo.update(app["id"], data, app["version"], _iso(tracking["updated_at"]))
    repo.event(app["id"], "legacy_edit", "通过岗位详情更新申请状态或备注", _iso(tracking["updated_at"]))
