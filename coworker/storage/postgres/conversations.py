"""Tenant-scoped PostgreSQL conversation persistence."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from coworker.server.identity import Principal
from coworker.sessions import SessionRecord


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _record_from_metadata(
    session_id: str,
    metadata: dict,
    *,
    messages: list[dict],
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        workspace=str(metadata.get("workspace") or ""),
        model=str(metadata.get("model") or ""),
        mode=str(metadata.get("mode") or "interactive"),
        messages=messages,
        title=(
            metadata.get("title")
            if metadata.get("renamed")
            else metadata.get("auto_title") or metadata.get("title")
        ),
        agent=str(metadata.get("agent") or "code"),
        message_count=(
            len(messages)
            if messages
            else int(metadata.get("message_count") or 0)
        ),
        updated_at=metadata.get("updated_at"),
        extra_roots=list(metadata.get("extra_roots") or []),
        grants=dict(metadata.get("grants") or {}),
        compaction=dict(metadata.get("compaction") or {}),
        pinned=bool(metadata.get("pinned")),
        archived=bool(metadata.get("archived")),
        origin=metadata.get("origin"),
        origin_label=metadata.get("origin_label"),
    )


class PostgresConversationRepository:
    def __init__(self, database, principal: Principal) -> None:
        self._database = database
        self._principal = principal

    def save(self, record: SessionRecord) -> None:
        with self._database.transaction(self._principal) as connection:
            self._ensure_user(connection)
            current = connection.execute(
                """
                SELECT metadata
                FROM agent.conversations
                WHERE id = %s
                FOR UPDATE
                """,
                (record.session_id,),
            ).fetchone()
            if current is None:
                connection.execute(
                    """
                    INSERT INTO agent.conversations(id, user_id, metadata)
                    VALUES (%s, %s, %s::jsonb)
                    """,
                    (
                        record.session_id,
                        self._principal.user_id,
                        "{}",
                    ),
                )

            stored = _json_object(current[0]) if current is not None else {}
            rows = connection.execute(
                """
                SELECT sequence, content
                FROM agent.messages
                WHERE conversation_id = %s
                ORDER BY sequence
                """,
                (record.session_id,),
            ).fetchall()
            existing = [content for _, content in rows]
            if record.messages[: len(existing)] != existing:
                raise RuntimeError(
                    "canonical conversation history is append-only"
                )
            if len(record.messages) < len(existing):
                raise RuntimeError(
                    "canonical conversation history is append-only"
                )
            for sequence, content in enumerate(
                record.messages[len(existing) :],
                start=len(existing) + 1,
            ):
                connection.execute(
                    """
                    INSERT INTO agent.messages(
                        id, user_id, conversation_id, sequence, content
                    ) VALUES (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        str(uuid.uuid4()),
                        self._principal.user_id,
                        record.session_id,
                        sequence,
                        json.dumps(content, ensure_ascii=False),
                    ),
                )

            self._persist_compaction(connection, record)
            metadata = {
                **stored,
                "workspace": record.workspace,
                "model": record.model,
                "mode": record.mode,
                "title": (
                    stored.get("title")
                    if stored.get("renamed")
                    else record.title
                ),
                "agent": record.agent,
                "message_count": len(record.messages),
                "extra_roots": record.extra_roots,
                "grants": record.grants,
                "compaction": {},
                "pinned": stored.get("pinned", record.pinned),
                "archived": stored.get("archived", record.archived),
                "origin": stored.get("origin", record.origin),
                "origin_label": stored.get(
                    "origin_label",
                    record.origin_label,
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            connection.execute(
                """
                UPDATE agent.conversations
                SET metadata = %s::jsonb, updated_at = now()
                WHERE id = %s
                """,
                (
                    json.dumps(metadata, ensure_ascii=False),
                    record.session_id,
                ),
            )

    def load(self, session_id: str) -> SessionRecord | None:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                SELECT metadata
                FROM agent.conversations
                WHERE id = %s
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            metadata = _json_object(row[0])
            messages = [
                content
                for _, content in connection.execute(
                    """
                    SELECT sequence, content
                    FROM agent.messages
                    WHERE conversation_id = %s
                    ORDER BY sequence
                    """,
                    (session_id,),
                ).fetchall()
            ]
            latest_compaction = connection.execute(
                """
                SELECT version, boundary_sequence, source_hash, state
                FROM agent.compactions
                WHERE conversation_id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if latest_compaction is not None:
                metadata["compaction"] = _json_object(latest_compaction[3])
        return _record_from_metadata(
            session_id,
            metadata,
            messages=messages,
        )

    def _persist_compaction(
        self,
        connection,
        record: SessionRecord,
    ) -> None:
        state = record.compaction
        if not state:
            return
        boundary = int(state.get("boundary_index") or 0)
        if boundary <= 0 or boundary > len(record.messages):
            raise ValueError("invalid compaction boundary")
        state_json = json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        source_json = json.dumps(
            record.messages[:boundary],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        source_hash = hashlib.sha256(source_json.encode("utf-8")).hexdigest()
        latest = connection.execute(
            """
            SELECT version, boundary_sequence, source_hash, state
            FROM agent.compactions
            WHERE conversation_id = %s
            ORDER BY version DESC
            LIMIT 1
            """,
            (record.session_id,),
        ).fetchone()
        if latest is not None:
            latest_state = json.dumps(
                _json_object(latest[3]),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if (
                int(latest[1]) == boundary
                and str(latest[2]) == source_hash
                and latest_state == state_json
            ):
                return
            version = int(latest[0]) + 1
        else:
            version = 1
        connection.execute(
            """
            INSERT INTO agent.compactions(
                id, user_id, conversation_id, version,
                boundary_sequence, summary, omitted_message_count,
                source_hash, state
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                str(uuid.uuid4()),
                self._principal.user_id,
                record.session_id,
                version,
                boundary,
                str(state.get("summary_text") or ""),
                boundary,
                source_hash,
                state_json,
            ),
        )

    def _ensure_user(self, connection) -> None:
        connection.execute(
            """
            INSERT INTO identity.users(id)
            VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (self._principal.user_id,),
        )

    def _update_metadata(self, session_id: str, update) -> bool:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                SELECT metadata
                FROM agent.conversations
                WHERE id = %s
                FOR UPDATE
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return False
            metadata = _json_object(row[0])
            if not update(metadata):
                return False
            connection.execute(
                """
                UPDATE agent.conversations
                SET metadata = %s::jsonb
                WHERE id = %s
                """,
                (
                    json.dumps(metadata, ensure_ascii=False),
                    session_id,
                ),
            )
        return True

    def list(self, *, workspace: str | None = None) -> list[SessionRecord]:
        with self._database.transaction(self._principal) as connection:
            rows = connection.execute(
                """
                SELECT id, metadata
                FROM agent.conversations
                ORDER BY
                    COALESCE((metadata->>'pinned')::boolean, FALSE) DESC,
                    updated_at DESC
                """
            ).fetchall()
        records = [
            _record_from_metadata(
                str(session_id),
                _json_object(metadata),
                messages=[],
            )
            for session_id, metadata in rows
        ]
        if workspace is None:
            return records
        return [record for record in records if record.workspace == workspace]

    def set_flags(
        self,
        session_id: str,
        *,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> bool:
        if pinned is None and archived is None:
            return False

        def update(metadata: dict) -> bool:
            if pinned is not None:
                metadata["pinned"] = pinned
            if archived is not None:
                metadata["archived"] = archived
            return True

        return self._update_metadata(session_id, update)

    def touch_workspace(self, path: str) -> None:
        with self._database.transaction(self._principal) as connection:
            self._ensure_user(connection)
            connection.execute(
                """
                INSERT INTO agent.workspaces(user_id, path, last_used)
                VALUES (%s, %s, now())
                ON CONFLICT (user_id, path)
                DO UPDATE SET last_used = now()
                """,
                (self._principal.user_id, path),
            )

    def recent_workspaces(self, limit: int = 20) -> list[str]:
        with self._database.transaction(self._principal) as connection:
            rows = connection.execute(
                """
                SELECT path
                FROM agent.workspaces
                ORDER BY last_used DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def canonicalize_workspaces(self) -> None:
        return None

    def rename(self, session_id: str, title: str) -> bool:
        clean = " ".join((title or "").split())[:120]
        if not clean:
            return False

        def update(metadata: dict) -> bool:
            metadata["title"] = clean
            metadata["renamed"] = True
            return True

        return self._update_metadata(session_id, update)

    def set_auto_title(self, session_id: str, title: str) -> bool:
        clean = " ".join((title or "").split())[:60]
        if not clean:
            return False

        def update(metadata: dict) -> bool:
            if metadata.get("renamed"):
                return False
            metadata["auto_title"] = clean
            return True

        return self._update_metadata(session_id, update)

    def title_state(self, session_id: str) -> dict | None:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                SELECT metadata
                FROM agent.conversations
                WHERE id = %s
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        metadata = _json_object(row[0])
        return {
            "renamed": bool(metadata.get("renamed")),
            "auto_title": metadata.get("auto_title"),
        }

    def set_origin(
        self,
        session_id: str,
        origin: str,
        origin_label: str = "",
    ) -> bool:
        def update(metadata: dict) -> bool:
            metadata["origin"] = origin
            metadata["origin_label"] = origin_label or None
            return True

        return self._update_metadata(session_id, update)

    def set_extra_roots(
        self,
        session_id: str,
        extra_roots: list[dict],
    ) -> None:
        def update(metadata: dict) -> bool:
            metadata["extra_roots"] = extra_roots or []
            return True

        self._update_metadata(session_id, update)

    def delete(self, session_id: str) -> bool:
        with self._database.transaction(self._principal) as connection:
            connection.execute(
                """
                DELETE FROM agent.messages
                WHERE conversation_id = %s
                """,
                (session_id,),
            )
            row = connection.execute(
                """
                DELETE FROM agent.conversations
                WHERE id = %s
                RETURNING id
                """,
                (session_id,),
            ).fetchone()
        return row is not None
