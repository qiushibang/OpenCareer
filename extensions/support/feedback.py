"""User-initiated support text, separate from automatic technical diagnostics."""
from __future__ import annotations

import json
import time
from uuid import uuid4
from coworker.server.identity import Principal
from .diagnostics import DiagnosticStore


class FeedbackConflict(ValueError):
    pass


class FeedbackStore:
    def __init__(self, diagnostics: DiagnosticStore) -> None:
        self.diagnostics = diagnostics
        self.table = "support.feedback" if diagnostics.database is not None else "feedback"
        if diagnostics.database is None:
            with diagnostics.transaction(Principal("local", "internal")) as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY, user_id TEXT, nonce TEXT NOT NULL,
                    created_at INTEGER NOT NULL, data TEXT NOT NULL)""")
                connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS feedback_nonce ON feedback(COALESCE(user_id,''),nonce)")
                connection.execute("CREATE INDEX IF NOT EXISTS feedback_time ON feedback(user_id,created_at)")

    def create(self, principal: Principal | None, *, nonce: str, kind: str, description: str,
               request_id: str | None = None, ui_release: str = "unknown") -> dict:
        now = int(time.time() * 1_000_000)
        item = {"id": uuid4().hex, "kind": kind, "description": description,
                "request_id": request_id, "release": self.diagnostics.release,
                "ui_release": ui_release if ui_release == self.diagnostics.release else "unknown",
                "created_at": now, "updated_at": now, "status": "open", "reply": ""}
        owner = principal.user_id if principal else ""
        with self.diagnostics.transaction(principal or Principal("support-intake", "internal")) as connection:
            execute = self.diagnostics.execute
            if self.diagnostics.database is not None:
                if principal is None:
                    execute(connection, "SELECT set_config('app.support_intake', '1', true)")
                execute(connection, "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", ("support-feedback:" + owner,))
            else:
                execute(connection, "BEGIN IMMEDIATE")
            # The nonce is scoped to its owner. A changed payload must not silently replace a draft.
            existing = execute(connection, f"SELECT data FROM {self.table} WHERE COALESCE(user_id,'')=? AND nonce=?",
                               (owner, nonce)).fetchone()
            if existing:
                previous = json.loads(existing[0])
                if any(previous[key] != item[key] for key in ("kind", "description", "request_id")):
                    raise FeedbackConflict("该提交编号已用于另一条反馈，请重新提交。")
                return previous
            if request_id is not None:
                diagnostic = execute(connection,
                    f"SELECT 1 FROM {self.diagnostics.table} WHERE user_id=? AND id=? AND created_at>=?",
                    (owner, request_id, int(time.time()) - 14 * 86400)).fetchone()
                if principal is None or diagnostic is None:
                    raise FeedbackConflict("排查编号不存在、已过期或不属于当前账号。")
            if execute(connection, f"SELECT COUNT(*) FROM {self.table} WHERE COALESCE(user_id,'')=?",
                       (owner,)).fetchone()[0] >= 500:
                raise FeedbackConflict("反馈数量达到上限，请等待已有反馈处理。")
            execute(connection, f"INSERT INTO {self.table}(id,user_id,nonce,created_at,data) VALUES (?,?,?,?,?)",
                    (item["id"], principal.user_id if principal else None, nonce, now, json.dumps(item, ensure_ascii=False)))
        return item

    def list_own(self, principal: Principal, *, limit: int = 50, offset: int = 0) -> list[dict]:
        with self.diagnostics.transaction(principal) as connection:
            rows = self.diagnostics.execute(connection,
                f"SELECT data FROM {self.table} WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (principal.user_id, limit, offset)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_own(self, principal: Principal, feedback_id: str) -> dict | None:
        with self.diagnostics.transaction(principal) as connection:
            row = self.diagnostics.execute(connection,
                f"SELECT data FROM {self.table} WHERE user_id=? AND id=?", (principal.user_id, feedback_id)).fetchone()
        return json.loads(row[0]) if row else None
