"""PostgreSQL state for Skills loaded into one conversation."""

from __future__ import annotations

from coworker.server.identity import Principal


class PostgresSessionSkillState:
    def __init__(
        self,
        database,
        principal: Principal,
        conversation_id: str,
    ) -> None:
        self._database = database
        self._principal = principal
        self._conversation_id = conversation_id

    def loaded_hash(self, name: str) -> str | None:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                SELECT content_sha256
                FROM agent.session_skills
                WHERE conversation_id = %s AND skill_name = %s
                """,
                (self._conversation_id, name),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def loaded_hashes(self) -> dict[str, str]:
        with self._database.transaction(self._principal) as connection:
            rows = connection.execute(
                """
                SELECT skill_name, content_sha256
                FROM agent.session_skills
                WHERE conversation_id = %s
                ORDER BY skill_name
                """,
                (self._conversation_id,),
            ).fetchall()
        return {
            str(name): str(content_sha256)
            for name, content_sha256 in rows
        }

    def mark_loaded(
        self,
        name: str,
        *,
        version: str | None,
        content_sha256: str,
    ) -> None:
        with self._database.transaction(self._principal) as connection:
            connection.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (self._principal.user_id,),
            )
            connection.execute(
                """
                INSERT INTO agent.conversations(id, user_id, metadata)
                VALUES (%s, %s, '{}'::jsonb)
                ON CONFLICT (user_id, id) DO NOTHING
                """,
                (self._conversation_id, self._principal.user_id),
            )
            connection.execute(
                """
                INSERT INTO agent.session_skills(
                    user_id, conversation_id, skill_name,
                    skill_version, content_sha256, loaded_at
                ) VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (user_id, conversation_id, skill_name)
                DO UPDATE SET
                    skill_version = EXCLUDED.skill_version,
                    content_sha256 = EXCLUDED.content_sha256,
                    loaded_at = now()
                """,
                (
                    self._principal.user_id,
                    self._conversation_id,
                    name,
                    version,
                    content_sha256,
                ),
            )
