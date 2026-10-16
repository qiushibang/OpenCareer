"""Least-privilege support administration with content-free audit records."""
from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping
from uuid import uuid4
from coworker.server.identity import Principal
from .feedback import FeedbackStore, FeedbackConflict


def _linked_resolution(status: str) -> tuple[str, str]:
    """Expose only a fixed public state to merged owners, never the target reply."""
    reply = {
        "open": "关联问题待处理。",
        "in_progress": "关联问题处理中。",
        "resolved": "关联问题已修复，请重新尝试；如问题仍存在，请新建反馈。",
        "declined": "关联问题已关闭；如需补充，请新建反馈。",
    }[status]
    return ("resolved" if status == "resolved" else "merged", reply)


class SupportCenter:
    def __init__(self, feedback: FeedbackStore, *, environ: Mapping[str, str] | None = None) -> None:
        self.feedback = feedback
        self.diagnostics = feedback.diagnostics
        env = os.environ if environ is None else environ
        ids = tuple(value.strip() for value in env.get("OPENCAR_SUPPORT_ADMIN_IDS", "").split(",") if value.strip())
        if any(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None for value in ids):
            raise ValueError("invalid support administrator configuration")
        self.admin_ids = frozenset(ids)
        self.audit_table = "support.admin_audit" if self.diagnostics.database is not None else "support_admin_audit"
        self.merge_table = "support.merge_links" if self.diagnostics.database is not None else "support_merge_links"
        if self.diagnostics.database is None:
            with self.diagnostics.transaction(Principal("local", "internal")) as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS support_admin_audit (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at INTEGER NOT NULL,
                    action TEXT NOT NULL, target_id TEXT)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS support_merge_links (
                    source_id TEXT PRIMARY KEY, target_id TEXT NOT NULL)""")

    def is_admin(self, principal: Principal) -> bool:
        return principal.user_id in self.admin_ids

    @contextmanager
    def transaction(self, principal: Principal) -> Iterator[Any]:
        if not self.is_admin(principal):
            raise PermissionError("support administrator required")
        with self.diagnostics.transaction(principal) as connection:
            if self.diagnostics.database is not None:
                self.diagnostics.execute(connection, "SELECT set_config('app.support_admin', ?, true)", (principal.user_id,))
            else:
                self.diagnostics.execute(connection, "BEGIN IMMEDIATE")
            yield connection

    def audit(self, connection: Any, principal: Principal, action: str, target_id: str | None = None) -> None:
        now = int(time.time() * 1_000_000)
        execute = self.diagnostics.execute
        execute(connection, f"INSERT INTO {self.audit_table}(id,user_id,created_at,action,target_id) VALUES (?,?,?,?,?)",
                (uuid4().hex, principal.user_id, now, action, target_id))
        execute(connection, f"DELETE FROM {self.audit_table} WHERE created_at<?", (now - 30 * 86400 * 1_000_000,))
        execute(connection, f"""DELETE FROM {self.audit_table} WHERE id NOT IN
            (SELECT id FROM {self.audit_table} ORDER BY created_at DESC,id DESC LIMIT 10000)""")

    def list_feedback(self, principal: Principal, *, status: str | None = None, kind: str | None = None, offset: int = 0) -> list[dict]:
        clauses, parameters = [], []
        for name, value in (("status", status), ("kind", kind)):
            if value is not None:
                expression = f"data::jsonb->>'{name}'" if self.diagnostics.database is not None else f"json_extract(data,'$.{name}')"
                clauses.append(f"{expression}=?")
                parameters.append(value)
        condition = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.transaction(principal) as connection:
            rows = self.diagnostics.execute(connection,
                f"SELECT user_id,data FROM {self.feedback.table}{condition} ORDER BY created_at DESC,id DESC LIMIT 50 OFFSET ?",
                tuple(parameters) + (offset,)).fetchall()
            self.audit(connection, principal, "list")
        return [{**json.loads(row[1]), "user_id": row[0]} for row in rows]

    def update(self, principal: Principal, feedback_id: str, *, status: str, reply: str, expected_updated_at: int) -> dict:
        with self.transaction(principal) as connection:
            lock = " FOR UPDATE" if self.diagnostics.database is not None else ""
            row = self.diagnostics.execute(connection, f"SELECT data FROM {self.feedback.table} WHERE id=?{lock}", (feedback_id,)).fetchone()
            if not row:
                raise FeedbackConflict("反馈不存在。")
            item = json.loads(row[0])
            if item["updated_at"] != expected_updated_at:
                raise FeedbackConflict("反馈已更新，请刷新后再处理。")
            if self.diagnostics.execute(connection, f"SELECT 1 FROM {self.merge_table} WHERE source_id=?", (feedback_id,)).fetchone():
                raise FeedbackConflict("该反馈已合并，请处理关联的主问题。")
            item.update(status=status, reply=reply, updated_at=int(time.time() * 1_000_000))
            encoded = json.dumps(item, ensure_ascii=False)
            if len(encoded.encode("utf-8")) > 16384:
                raise FeedbackConflict("反馈与回复总长度超出限制，请缩短回复。")
            self.diagnostics.execute(connection, f"UPDATE {self.feedback.table} SET data=? WHERE id=?", (encoded, feedback_id))
            children = self.diagnostics.execute(connection, f"""SELECT f.id,f.data FROM {self.feedback.table} f
                JOIN {self.merge_table} m ON m.source_id=f.id WHERE m.target_id=?""", (feedback_id,)).fetchall()
            linked_status, linked_reply = _linked_resolution(status)
            for child_id, child_data in children:
                child = json.loads(child_data)
                child.update(status=linked_status, reply=linked_reply,
                             updated_at=item["updated_at"])
                child_encoded = json.dumps(child, ensure_ascii=False)
                if len(child_encoded.encode("utf-8")) > 16384:
                    raise FeedbackConflict("合并反馈的回复超出长度限制，请缩短回复。")
                self.diagnostics.execute(connection, f"UPDATE {self.feedback.table} SET data=? WHERE id=?", (child_encoded, child_id))
            self.audit(connection, principal, "update", feedback_id)
        return item

    def detail(self, principal: Principal, feedback_id: str) -> dict:
        with self.transaction(principal) as connection:
            row = self.diagnostics.execute(connection, f"SELECT user_id,data FROM {self.feedback.table} WHERE id=?", (feedback_id,)).fetchone()
            if not row:
                raise FeedbackConflict("反馈不存在。")
            item = json.loads(row[1])
            diagnostic = None
            if item.get("request_id") and row[0]:
                record = self.diagnostics.execute(connection,
                    f"SELECT data FROM {self.diagnostics.table} WHERE user_id=? AND id=? AND created_at>=?",
                    (row[0], item["request_id"], int(time.time()) - 14 * 86400)).fetchone()
                diagnostic = json.loads(record[0]) if record else None
            self.audit(connection, principal, "detail", feedback_id)
        return {"feedback": {**item, "user_id": row[0]}, "diagnostic": diagnostic}

    def merge(self, principal: Principal, source_id: str, *, target_id: str, expected_updated_at: int) -> dict:
        if source_id == target_id:
            raise FeedbackConflict("不能合并到自身。")
        with self.transaction(principal) as connection:
            lock = " FOR UPDATE" if self.diagnostics.database is not None else ""
            # Stable lock ordering prevents opposite merge requests deadlocking.
            rows = self.diagnostics.execute(connection,
                f"SELECT id,data FROM {self.feedback.table} WHERE id IN (?,?) ORDER BY id{lock}", (source_id, target_id)).fetchall()
            items = {row[0]: json.loads(row[1]) for row in rows}
            if len(items) != 2:
                raise FeedbackConflict("反馈不存在。")
            source, target = items[source_id], items[target_id]
            if source["updated_at"] != expected_updated_at:
                raise FeedbackConflict("反馈已更新，请刷新后再处理。")
            if self.diagnostics.execute(connection, f"SELECT 1 FROM {self.merge_table} WHERE source_id IN (?,?)", (source_id, target_id)).fetchone():
                raise FeedbackConflict("请直接合并到未合并的主问题。")
            if self.diagnostics.execute(connection, f"SELECT 1 FROM {self.merge_table} WHERE target_id=?", (source_id,)).fetchone():
                raise FeedbackConflict("该主问题已有关联反馈，请保留它作为主问题。")
            linked_status, linked_reply = _linked_resolution(target["status"])
            source.update(status=linked_status, reply=linked_reply, updated_at=int(time.time() * 1_000_000))
            self.diagnostics.execute(connection, f"INSERT INTO {self.merge_table}(source_id,target_id) VALUES (?,?)", (source_id, target_id))
            self.diagnostics.execute(connection, f"UPDATE {self.feedback.table} SET data=? WHERE id=?", (json.dumps(source, ensure_ascii=False), source_id))
            self.audit(connection, principal, "merge", source_id)
        return source

    def list_audit(self, principal: Principal) -> list[dict]:
        with self.transaction(principal) as connection:
            self.audit(connection, principal, "list")
            rows = self.diagnostics.execute(connection, f"SELECT id,user_id,created_at,action,target_id FROM {self.audit_table} ORDER BY created_at DESC,id DESC LIMIT 100").fetchall()
        return [dict(zip(("id", "user_id", "created_at", "action", "target_id"), row)) for row in rows]
