"""Persistence boundary for staged resumes and confirmed candidate facts."""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from .migrations import migrate

SECTIONS = ("basic", "education", "experience", "project", "skill")


class ResumeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        migrate(connection)

    def create_or_reuse_import(
        self,
        *,
        content_hash: str,
        upload_token: str,
        source_kind: str,
        original_filename: str,
        private_path: str,
        extracted_text: str,
        extraction_method: str = "native",
        extraction_metadata: dict[str, object] | None = None,
        expires_at: str,
        now: str,
    ) -> dict:
        if extraction_metadata is None:
            if extraction_method != "native":
                raise ValueError(
                    "non-native extraction requires provenance metadata"
                )
            extraction_metadata = self._native_extraction_metadata()
        metadata_json = self._json(extraction_metadata)
        existing = self.connection.execute(
            "SELECT * FROM resume_imports WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if existing is not None:
            if existing["deleted_at"] is not None:
                self.connection.execute(
                    """
                    UPDATE resume_imports
                    SET upload_token = ?, source_kind = ?,
                        original_filename = ?, display_name = ?,
                        target_roles_json = '[]', private_path = ?,
                        extracted_text = ?, status = 'staged',
                        extraction_method = ?,
                        extraction_metadata_json = ?,
                        expires_at = ?, deleted_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        upload_token,
                        source_kind,
                        original_filename,
                        original_filename,
                        private_path,
                        extracted_text,
                        extraction_method,
                        metadata_json,
                        expires_at,
                        now,
                        existing["id"],
                    ),
                )
                existing = self.connection.execute(
                    "SELECT * FROM resume_imports WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
            elif str(existing["expires_at"]) < now:
                self.connection.execute(
                    """
                    UPDATE resume_imports
                    SET upload_token = ?, source_kind = ?,
                        original_filename = ?, private_path = ?,
                        extracted_text = ?, extraction_method = ?,
                        extraction_metadata_json = ?,
                        expires_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        upload_token,
                        source_kind,
                        original_filename,
                        private_path,
                        extracted_text,
                        extraction_method,
                        metadata_json,
                        expires_at,
                        now,
                        existing["id"],
                    ),
                )
                existing = self.connection.execute(
                    "SELECT * FROM resume_imports WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
            else:
                self.connection.execute(
                    """
                    UPDATE resume_imports
                    SET source_kind = ?, original_filename = ?,
                        private_path = ?, extracted_text = ?,
                        extraction_method = ?,
                        extraction_metadata_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        source_kind,
                        original_filename,
                        private_path,
                        extracted_text,
                        extraction_method,
                        metadata_json,
                        now,
                        existing["id"],
                    ),
                )
                existing = self.connection.execute(
                    "SELECT * FROM resume_imports WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
            return self._import_row(existing)
        import_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO resume_imports(
                id, content_hash, upload_token, source_kind,
                original_filename, private_path, extracted_text, status,
                extraction_method, extraction_metadata_json,
                expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'staged', ?, ?, ?, ?, ?)
            """,
            (
                import_id,
                content_hash,
                upload_token,
                source_kind,
                original_filename,
                private_path,
                extracted_text,
                extraction_method,
                metadata_json,
                expires_at,
                now,
                now,
            ),
        )
        return self._import_row(
            self.connection.execute(
                "SELECT * FROM resume_imports WHERE id = ?",
                (import_id,),
            ).fetchone()
        )

    def get_import_by_upload_token(self, upload_token: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM resume_imports WHERE upload_token = ?",
            (upload_token,),
        ).fetchone()
        return self._import_row(row) if row is not None else None

    def private_paths(self) -> list[str]:
        return [
            str(row["private_path"])
            for row in self.connection.execute(
                "SELECT DISTINCT private_path FROM resume_imports"
            )
        ]

    def create_preview(
        self,
        *,
        resume_import_id: str,
        preview_token: str,
        proposal: dict,
        conflicts: list,
        expires_at: str,
        now: str,
    ) -> dict:
        preview_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO resume_previews(
                id, resume_import_id, preview_token, proposal_json,
                conflicts_json, confirmed_sections_json, expires_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, '[]', ?, ?, ?)
            """,
            (
                preview_id,
                resume_import_id,
                preview_token,
                self._json(proposal),
                self._json(conflicts),
                expires_at,
                now,
                now,
            ),
        )
        self.connection.execute(
            "UPDATE resume_imports SET status = 'previewed', updated_at = ? "
            "WHERE id = ?",
            (now, resume_import_id),
        )
        return {
            "id": preview_id,
            "preview_token": preview_token,
            "proposal": proposal,
            "conflicts": conflicts,
            "confirmed_sections": [],
            "expires_at": expires_at,
        }

    def get_preview(self, preview_token: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT p.*, i.status AS import_status
            FROM resume_previews p
            JOIN resume_imports i ON i.id = p.resume_import_id
            WHERE p.preview_token = ?
            """,
            (preview_token,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key in (
            "proposal_json",
            "conflicts_json",
            "confirmed_sections_json",
        ):
            result[key.removesuffix("_json")] = json.loads(result.pop(key))
        return result

    def confirm_sections(
        self,
        *,
        preview_token: str,
        sections: list[str],
        corrections: dict,
        now: str,
    ) -> dict:
        preview = self.get_preview(preview_token)
        if preview is None:
            raise LookupError("preview not found")
        proposal = dict(preview["proposal"])
        for section in sections:
            if section not in SECTIONS:
                raise ValueError(f"unsupported resume section: {section}")
            if section in corrections:
                proposal[section] = corrections[section]

        profile = self.connection.execute(
            "SELECT * FROM candidate_profile LIMIT 1"
        ).fetchone()
        if profile is None:
            profile_id = str(uuid4())
            self.connection.execute(
                """
                INSERT INTO candidate_profile(
                    id, display_name, current_version, created_at, updated_at
                ) VALUES (?, NULL, 0, ?, ?)
                """,
                (profile_id, now, now),
            )
            current_version = 0
        else:
            profile_id = str(profile["id"])
            current_version = int(profile["current_version"])

        for section in sections:
            self.connection.execute(
                "DELETE FROM candidate_facts "
                "WHERE profile_id = ? AND section = ?",
                (profile_id, section),
            )
            sensitivity = (
                "sensitive" if section == "basic" else "personal"
            )
            self.connection.execute(
                """
                INSERT INTO candidate_facts(
                    id, profile_id, section, fact_key, fact_value_json,
                    sensitivity, source_import_id, confirmed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'value', ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    profile_id,
                    section,
                    self._json(proposal[section]),
                    sensitivity,
                    preview["resume_import_id"],
                    now,
                    now,
                    now,
                ),
            )

        snapshot = self._profile_sections(profile_id)
        version = current_version + 1
        self.connection.execute(
            """
            INSERT INTO profile_versions(
                id, profile_id, version_number, confirmed_sections_json,
                snapshot_json, source_import_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                profile_id,
                version,
                self._json(sections),
                self._json(snapshot),
                preview["resume_import_id"],
                now,
            ),
        )
        display_name = (snapshot.get("basic") or {}).get("name")
        self.connection.execute(
            """
            UPDATE candidate_profile
            SET display_name = ?, current_version = ?, updated_at = ?
            WHERE id = ?
            """,
            (display_name, version, now, profile_id),
        )
        confirmed = sorted(
            set(preview["confirmed_sections"]) | set(sections)
        )
        all_confirmed = set(confirmed) == set(SECTIONS)
        self.connection.execute(
            """
            UPDATE resume_previews
            SET proposal_json = ?, confirmed_sections_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                self._json(proposal),
                self._json(confirmed),
                now,
                preview["id"],
            ),
        )
        self.connection.execute(
            "UPDATE resume_imports SET status = ?, updated_at = ? WHERE id = ?",
            (
                "confirmed" if all_confirmed else "partially_confirmed",
                now,
                preview["resume_import_id"],
            ),
        )
        return {
            "profile_id": profile_id,
            "version": version,
            "confirmed_sections": confirmed,
            "complete": all_confirmed,
        }

    def get_profile(self) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM candidate_profile LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "display_name": row["display_name"],
            "current_version": int(row["current_version"]),
            "sections": self._profile_sections(str(row["id"])),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def list_profile_versions(self) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT pv.version_number, pv.confirmed_sections_json,
                   pv.created_at, ri.original_filename, ri.source_kind
            FROM profile_versions pv
            JOIN resume_imports ri ON ri.id = pv.source_import_id
            ORDER BY pv.version_number DESC
            """
        ).fetchall()
        return [
            {
                "version": int(row["version_number"]),
                "confirmed_sections": json.loads(
                    row["confirmed_sections_json"]
                ),
                "filename": str(row["original_filename"]),
                "source_kind": str(row["source_kind"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def list_resume_documents(self) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT ri.id, ri.original_filename, ri.display_name,
                   ri.target_roles_json, ri.source_kind, ri.status,
                   ri.created_at, rp.updated_at,
                   rp.confirmed_sections_json
            FROM resume_imports ri
            JOIN resume_previews rp
              ON rp.id = (
                SELECT latest.id
                FROM resume_previews latest
                WHERE latest.resume_import_id = ri.id
                ORDER BY latest.updated_at DESC, latest.id DESC
                LIMIT 1
              )
            WHERE ri.status IN ('partially_confirmed', 'confirmed')
              AND ri.deleted_at IS NULL
            ORDER BY rp.updated_at DESC, ri.id ASC
            """
        ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "filename": str(row["original_filename"]),
                "display_name": str(
                    row["display_name"] or row["original_filename"]
                ),
                "target_roles": json.loads(row["target_roles_json"]),
                "source_kind": str(row["source_kind"]),
                "status": str(row["status"]),
                "confirmed_sections": json.loads(
                    row["confirmed_sections_json"]
                ),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in rows
        ]

    def get_resume_document(self, resume_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT ri.id, ri.original_filename, ri.display_name,
                   ri.target_roles_json, ri.source_kind, ri.status,
                   ri.created_at, rp.updated_at, rp.proposal_json,
                   rp.confirmed_sections_json
            FROM resume_imports ri
            JOIN resume_previews rp
              ON rp.id = (
                SELECT latest.id
                FROM resume_previews latest
                WHERE latest.resume_import_id = ri.id
                ORDER BY latest.updated_at DESC, latest.id DESC
                LIMIT 1
              )
            WHERE ri.id = ?
              AND ri.status IN ('partially_confirmed', 'confirmed')
              AND ri.deleted_at IS NULL
            """,
            (resume_id,),
        ).fetchone()
        if row is None:
            return None
        confirmed_sections = json.loads(row["confirmed_sections_json"])
        proposal = json.loads(row["proposal_json"])
        return {
            "id": str(row["id"]),
            "filename": str(row["original_filename"]),
            "display_name": str(
                row["display_name"] or row["original_filename"]
            ),
            "target_roles": json.loads(row["target_roles_json"]),
            "source_kind": str(row["source_kind"]),
            "status": str(row["status"]),
            "confirmed_sections": confirmed_sections,
            "sections": {
                section: proposal[section]
                for section in confirmed_sections
                if section in proposal
            },
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def get_interview_input(self, resume_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT ri.id, ri.original_filename, ri.display_name,
                   ri.target_roles_json, ri.updated_at AS revision_at,
                   rp.proposal_json, rp.confirmed_sections_json
            FROM resume_imports ri
            JOIN resume_previews rp
              ON rp.id = (
                SELECT latest.id
                FROM resume_previews latest
                WHERE latest.resume_import_id = ri.id
                ORDER BY latest.updated_at DESC, latest.id DESC
                LIMIT 1
              )
            WHERE ri.id = ?
              AND ri.status IN ('partially_confirmed', 'confirmed')
              AND ri.deleted_at IS NULL
            """,
            (resume_id,),
        ).fetchone()
        if row is None:
            return None
        proposal = json.loads(row["proposal_json"])
        confirmed_sections = json.loads(row["confirmed_sections_json"])
        return {
            "id": str(row["id"]),
            "display_name": str(
                row["display_name"] or row["original_filename"]
            ),
            "target_roles": json.loads(row["target_roles_json"]),
            "revision_at": str(row["revision_at"]),
            "sections": {
                section: proposal[section]
                for section in confirmed_sections
                if section in proposal
            },
        }

    def update_resume_document_metadata(
        self,
        resume_id: str,
        *,
        display_name: str,
        target_roles: list[str],
        now: str,
    ) -> dict | None:
        cursor = self.connection.execute(
            """
            UPDATE resume_imports
            SET display_name = ?, target_roles_json = ?, updated_at = ?
            WHERE id = ?
              AND status IN ('partially_confirmed', 'confirmed')
              AND deleted_at IS NULL
            """,
            (
                display_name,
                self._json(target_roles),
                now,
                resume_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        return self.get_resume_document(resume_id)

    def soft_delete_resume_document(
        self,
        resume_id: str,
        *,
        now: str,
    ) -> dict | None:
        row = self.connection.execute(
            """
            SELECT private_path
            FROM resume_imports
            WHERE id = ?
              AND status IN ('partially_confirmed', 'confirmed')
              AND deleted_at IS NULL
            """,
            (resume_id,),
        ).fetchone()
        if row is None:
            return None
        self.connection.execute(
            "DELETE FROM resume_previews WHERE resume_import_id = ?",
            (resume_id,),
        )
        self.connection.execute(
            """
            UPDATE resume_imports
            SET extracted_text = '', deleted_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, resume_id),
        )
        return {
            "resume_id": resume_id,
            "private_path": str(row["private_path"]),
        }

    def list_resume_document_versions(self, resume_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT pv.version_number, pv.confirmed_sections_json,
                   pv.created_at, ri.original_filename, ri.source_kind
            FROM profile_versions pv
            JOIN resume_imports ri ON ri.id = pv.source_import_id
            WHERE pv.source_import_id = ?
            ORDER BY pv.version_number DESC
            """,
            (resume_id,),
        ).fetchall()
        return [
            {
                "version": int(row["version_number"]),
                "confirmed_sections": json.loads(
                    row["confirmed_sections_json"]
                ),
                "filename": str(row["original_filename"]),
                "source_kind": str(row["source_kind"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def get_resume_original(self, resume_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT original_filename, source_kind, private_path
            FROM resume_imports
            WHERE id = ?
              AND status IN ('partially_confirmed', 'confirmed')
              AND deleted_at IS NULL
            """,
            (resume_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "filename": str(row["original_filename"]),
            "source_kind": str(row["source_kind"]),
            "private_path": str(row["private_path"]),
        }

    def get_profile_original(self) -> dict | None:
        row = self.connection.execute(
            """
            SELECT ri.original_filename, ri.source_kind, ri.private_path
            FROM candidate_profile cp
            JOIN profile_versions pv
              ON pv.profile_id = cp.id
             AND pv.version_number = cp.current_version
            JOIN resume_imports ri ON ri.id = pv.source_import_id
            WHERE ri.deleted_at IS NULL
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return {
            "filename": str(row["original_filename"]),
            "source_kind": str(row["source_kind"]),
            "private_path": str(row["private_path"]),
        }

    def discard_preview_import(self, preview_token: str) -> dict:
        preview = self.get_preview(preview_token)
        if preview is None:
            raise LookupError("preview not found")
        if preview["import_status"] in {
            "partially_confirmed",
            "confirmed",
        }:
            raise ValueError("confirmed resume import cannot be discarded")
        resume_import = self.connection.execute(
            "SELECT * FROM resume_imports WHERE id = ?",
            (preview["resume_import_id"],),
        ).fetchone()
        self.connection.execute(
            "DELETE FROM resume_previews WHERE id = ?",
            (preview["id"],),
        )
        self.connection.execute(
            "DELETE FROM resume_imports WHERE id = ?",
            (preview["resume_import_id"],),
        )
        return {
            "previews": 1,
            "imports": 1,
            "private_path": str(resume_import["private_path"]),
        }

    def delete_all(self) -> dict[str, int]:
        counts = {
            "profiles": self._count("candidate_profile"),
            "facts": self._count("candidate_facts"),
            "versions": self._count("profile_versions"),
            "previews": self._count("resume_previews"),
            "imports": self._count("resume_imports"),
        }
        self.connection.execute("DELETE FROM resume_previews")
        self.connection.execute("DELETE FROM candidate_profile")
        self.connection.execute("DELETE FROM resume_imports")
        return counts

    def _profile_sections(self, profile_id: str) -> dict:
        return {
            str(row["section"]): json.loads(row["fact_value_json"])
            for row in self.connection.execute(
                """
                SELECT section, fact_value_json
                FROM candidate_facts
                WHERE profile_id = ?
                ORDER BY section
                """,
                (profile_id,),
            )
        }

    def _count(self, table: str) -> int:
        return int(
            self.connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        )

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _native_extraction_metadata() -> dict[str, object]:
        return {
            "version": 1,
            "method": "native",
            "total_pages": 1,
            "native_pages": [1],
            "ocr_pages": [],
            "ocr_attempted_pages": [],
            "mean_confidence": None,
            "quality": "native",
            "review_required": False,
            "warning_codes": [],
            "engine": None,
        }

    @staticmethod
    def _import_row(row: sqlite3.Row) -> dict:
        result = dict(row)
        result["extraction_metadata"] = json.loads(
            result.pop("extraction_metadata_json")
        )
        return result
