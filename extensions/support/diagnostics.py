"""Content-free diagnostics with fixed vocabulary and bounded storage."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from coworker.server.identity import Principal

DIAGNOSTIC_KINDS = frozenset({
    "http_client_error", "http_server_error", "page_crash", "network_error",
    "provider_error", "tool_error", "turn_error", "socket_error",
})
PAGES = frozenset({"jobs", "profile", "interview", "conversation", "models", "auth", "support", "unknown"})
_ID = re.compile(r"^[0-9a-f]{32}$")


def page_category(path: str) -> str:
    """Map only known route families; never retain URL parameters or paths."""
    for fragment, page in (
        ("/career/interviews", "interview"), ("/career/jobs", "jobs"),
        ("/career/profile", "profile"), ("/career/resumes", "profile"),
        ("/sessions", "conversation"), ("/providers", "models"),
        ("/auth", "auth"), ("/support", "support"),
    ):
        if fragment in path:
            return page
    return "unknown"


class DiagnosticStore:
    """Use cloud system of record, or an isolated desktop SQLite database."""

    def __init__(self, *, path: Path | None = None, database: Any = None) -> None:
        self.database = database
        self.path = path
        self.table = "support.diagnostics" if database is not None else "diagnostics"
        if database is None:
            if path is None:
                raise ValueError("diagnostic storage path is required")
            path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(path) as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS diagnostics (
                    user_id TEXT NOT NULL, id TEXT NOT NULL, created_at INTEGER NOT NULL,
                    data TEXT NOT NULL, PRIMARY KEY (user_id, id))""")
                connection.execute("CREATE INDEX IF NOT EXISTS diagnostic_time ON diagnostics(user_id, created_at)")
                if "created_order" not in {row[1] for row in connection.execute("PRAGMA table_info(diagnostics)")}:
                    connection.execute("ALTER TABLE diagnostics ADD COLUMN created_order INTEGER NOT NULL DEFAULT 0")
            connection.close()
            os.chmod(path, 0o600)
        release = os.environ.get("OPENCAR_RELEASE", "unknown")
        self.release = release if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", release) else "unknown"

    @contextmanager
    def transaction(self, principal: Principal) -> Iterator[Any]:
        if self.database is not None:
            with self.database.transaction(principal) as connection:
                yield connection
        else:
            connection = sqlite3.connect(self.path, timeout=0.25)
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

    def execute(self, connection: Any, sql: str, parameters: tuple = ()) -> Any:
        return connection.execute(sql.replace("?", "%s") if self.database is not None else sql, parameters)

    def record(self, principal: Principal, *, request_id: str | None = None,
               kind: str, page: str = "unknown", status: int = 0,
               duration_ms: int = 0, source: str = "server") -> str:
        if kind not in DIAGNOSTIC_KINDS or page not in PAGES or source not in {"server", "browser", "agent"}:
            raise ValueError("invalid diagnostic category")
        request_id = request_id or uuid4().hex
        if not _ID.fullmatch(request_id):
            raise ValueError("invalid diagnostic id")
        now = int(time.time())
        # Construct a new whitelist record. No exception/argument/body ever enters it.
        data = {"request_id": request_id, "kind": kind, "page": page,
                "status": max(0, min(599, int(status))),
                "duration_ms": max(0, min(86_400_000, int(duration_ms))),
                "source": source, "created_at": now, "release": self.release}
        with self.transaction(principal) as connection:
            if self.database is not None:
                self.execute(connection, "SELECT pg_advisory_xact_lock(hashtextextended(?,0))", ("support-diagnostics:" + principal.user_id,))
            else:
                self.execute(connection, "BEGIN IMMEDIATE")
            self.execute(connection, f"DELETE FROM {self.table} WHERE user_id=? AND created_at<?",
                         (principal.user_id, now - 14 * 86400))
            self.execute(connection, f"""INSERT INTO {self.table}(user_id,id,created_at,data,created_order)
                VALUES (?,?,?,?,?) ON CONFLICT (user_id,id) DO NOTHING""",
                         (principal.user_id, request_id, now, json.dumps(data), time.time_ns()))
            self.execute(connection, f"""DELETE FROM {self.table} WHERE user_id=? AND id NOT IN
                (SELECT id FROM {self.table} WHERE user_id=? ORDER BY created_at DESC,created_order DESC,id DESC LIMIT 1000)""",
                         (principal.user_id, principal.user_id))
        return request_id

    def get(self, principal: Principal, request_id: str) -> dict | None:
        if not _ID.fullmatch(request_id):
            return None
        with self.transaction(principal) as connection:
            row = self.execute(connection, f"SELECT data FROM {self.table} WHERE user_id=? AND id=? AND created_at>=?",
                               (principal.user_id, request_id, int(time.time()) - 14 * 86400)).fetchone()
        return json.loads(row[0]) if row else None
