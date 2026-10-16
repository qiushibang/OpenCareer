"""Request-scoped resume reads backed by PostgreSQL and Blob storage."""

from __future__ import annotations

import json
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from coworker.server.identity import Principal
from extensions.career_mcp.domain.resume import (
    RESUME_SECTIONS,
    ResumeInputError,
    extract_resume_text,
    mask_candidate_profile,
    validate_resume_proposal,
)
from extensions.career_mcp.services.resumes import (
    ResumeService,
    ResumeServiceError,
)


class _LazyResumeOcr:
    def __init__(self) -> None:
        self._service = None

    def extract(self, pages, *, raw_pdf: bytes):
        if self._service is None:
            self._service = ResumeService._default_ocr_service()
        return self._service.extract(pages, raw_pdf=raw_pdf)


class PostgresResumeService:
    def __init__(self, database, principal: Principal, blob_repository) -> None:
        self.database = database
        self.principal = principal
        self.blobs = blob_repository
        self._ocr_service = _LazyResumeOcr()

    def stage_resume(
        self,
        *,
        filename: str,
        mime: str,
        raw_bytes: bytes | None = None,
        text: str | None = None,
    ) -> dict:
        try:
            extracted = extract_resume_text(
                filename=filename,
                mime=mime,
                raw_bytes=raw_bytes,
                text=text,
                ocr_service=self._ocr_service,
            )
        except ResumeInputError as exc:
            raise ResumeServiceError(exc.code, str(exc)) from exc
        if len(extracted.raw_bytes) > 10 * 1024 * 1024:
            raise ResumeServiceError(
                "FILE_TOO_LARGE",
                "resume exceeds 10 MB",
            )
        digest = hashlib.sha256(extracted.raw_bytes).hexdigest()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=24)
        with self.database.transaction(self.principal) as connection:
            row = connection.execute(
                """
                SELECT data
                FROM career.resume_imports
                WHERE user_id = %s AND content_hash = %s
                FOR UPDATE
                """,
                (self.principal.user_id, digest),
            ).fetchone()
            if row is None:
                blob_id = str(uuid4())
                resume_id = str(uuid4())
                data = self._staged_data(
                    extracted,
                    upload_token=secrets.token_urlsafe(32),
                    expires_at=expires_at,
                )
                connection.execute(
                    """
                    INSERT INTO blob.objects(
                        id, scope, user_id, kind, media_type,
                        original_name, size_bytes, sha256, content
                    ) VALUES (
                        %s, 'user', %s, 'resume_original', %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        blob_id,
                        self.principal.user_id,
                        mime or "application/octet-stream",
                        extracted.filename,
                        len(extracted.raw_bytes),
                        digest,
                        extracted.raw_bytes,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO career.resume_imports(
                        id, user_id, blob_id, content_hash, data,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s::jsonb, %s, %s
                    )
                    """,
                    (
                        resume_id,
                        self.principal.user_id,
                        blob_id,
                        digest,
                        json.dumps(data, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            else:
                data = dict(row[0] or {})
                if data.get("status") == "deleted":
                    raise ResumeServiceError(
                        "RESUME_NOT_FOUND",
                        "deleted resume cannot be reused",
                    )
        return {
            "upload_token": data["upload_token"],
            "source_kind": data["source_kind"],
            "filename": data["filename"],
            "sha256": digest,
            "characters": len(data["extracted_text"]),
            "expires_at": data["expires_at"],
            "extraction_method": data["extraction_method"],
            "review_required": bool(
                data["extraction_metadata"]["review_required"]
            ),
            "warnings": list(
                data["extraction_metadata"]["warning_codes"]
            ),
            "pages": {
                "total": int(
                    data["extraction_metadata"]["total_pages"]
                ),
                "ocr": list(data["extraction_metadata"]["ocr_pages"]),
            },
        }

    def list_resume_documents(self) -> list[dict]:
        with self.database.transaction(self.principal) as connection:
            rows = connection.execute(
                """
                SELECT id, data, created_at, updated_at
                FROM career.resume_imports
                WHERE user_id = %s
                  AND data->>'status' IN (
                      'partially_confirmed', 'confirmed'
                  )
                  AND COALESCE(data->>'deleted_at', '') = ''
                ORDER BY updated_at DESC, id ASC
                """,
                (self.principal.user_id,),
            ).fetchall()
        return [self._document(row) for row in rows]

    def get_resume_import_text(self, upload_token: str) -> dict:
        record = self._valid_import(upload_token)
        return {
            "upload_token": upload_token,
            "source_kind": record["source_kind"],
            "filename": record["filename"],
            "text": record["extracted_text"],
            "characters": len(record["extracted_text"]),
            "extraction_metadata": record["extraction_metadata"],
            "extraction_method": record["extraction_method"],
            "review_required": bool(
                record["extraction_metadata"]["review_required"]
            ),
            "warnings": list(
                record["extraction_metadata"]["warning_codes"]
            ),
            "pages": {
                "total": int(
                    record["extraction_metadata"]["total_pages"]
                ),
                "ocr": list(
                    record["extraction_metadata"]["ocr_pages"]
                ),
            },
        }

    def preview_resume_import(
        self,
        upload_token: str,
        proposal: dict,
    ) -> dict:
        record = self._valid_import(upload_token)
        try:
            normalized = validate_resume_proposal(proposal)
        except ResumeInputError as exc:
            raise ResumeServiceError(exc.code, str(exc)) from exc
        current = self._profile_or_none()
        conflicts = []
        if current is not None:
            for section in RESUME_SECTIONS:
                existing = current["sections"].get(section)
                proposed = normalized[section]
                if existing is not None and existing != proposed:
                    conflicts.append(
                        {
                            "section": section,
                            "current": ResumeService._mask_section(
                                section,
                                existing,
                            ),
                            "proposed": ResumeService._mask_section(
                                section,
                                proposed,
                            ),
                        }
                    )
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=24)
        preview_id = str(uuid4())
        preview_token = secrets.token_urlsafe(32)
        preview_data = {
            "preview_token": preview_token,
            "proposal": normalized,
            "conflicts": conflicts,
            "confirmed_sections": [],
        }
        with self.database.transaction(self.principal) as connection:
            connection.execute(
                """
                INSERT INTO career.resume_previews(
                    id, user_id, resume_import_id, data,
                    expires_at, created_at
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    preview_id,
                    self.principal.user_id,
                    record["id"],
                    json.dumps(preview_data, ensure_ascii=False),
                    expires_at,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE career.resume_imports
                SET data = data || jsonb_build_object(
                        'status', 'previewed'
                    ),
                    updated_at = %s
                WHERE user_id = %s AND id = %s
                """,
                (now, self.principal.user_id, record["id"]),
            )
        return {
            "id": preview_id,
            "preview_token": preview_token,
            "proposal": ResumeService._masked_proposal(normalized),
            "conflicts": conflicts,
            "confirmed_sections": [],
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }

    def confirm_resume_sections(
        self,
        preview_token: str,
        sections: list[str],
        *,
        corrections: dict | None = None,
    ) -> dict:
        if not sections or not set(sections) <= set(RESUME_SECTIONS):
            raise ResumeServiceError(
                "INVALID_INPUT",
                "sections must be a non-empty valid subset",
            )
        corrections = corrections or {}
        now = datetime.now(timezone.utc)
        with self.database.transaction(self.principal) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"career-profile:{self.principal.user_id}",),
            )
            row = connection.execute(
                """
                SELECT p.id, p.resume_import_id, p.data, p.expires_at,
                       r.data
                FROM career.resume_previews p
                JOIN career.resume_imports r
                  ON r.user_id = p.user_id
                 AND r.id = p.resume_import_id
                WHERE p.user_id = %s
                  AND p.data->>'preview_token' = %s
                FOR UPDATE OF p, r
                """,
                (self.principal.user_id, preview_token),
            ).fetchone()
            if row is None:
                raise ResumeServiceError(
                    "PREVIEW_NOT_FOUND",
                    "resume preview not found",
                )
            if row[3] < now:
                raise ResumeServiceError(
                    "PREVIEW_EXPIRED",
                    "resume preview expired",
                )
            preview_data = dict(row[2] or {})
            proposal = dict(preview_data.get("proposal") or {})
            proposal.update(corrections)
            try:
                proposal = validate_resume_proposal(proposal)
            except ResumeInputError as exc:
                raise ResumeServiceError(exc.code, str(exc)) from exc
            profile = connection.execute(
                """
                SELECT id, data, created_at
                FROM career.candidate_profiles
                WHERE user_id = %s
                ORDER BY updated_at DESC, id ASC
                LIMIT 1
                FOR UPDATE
                """,
                (self.principal.user_id,),
            ).fetchone()
            if profile is None:
                profile_id = str(uuid4())
                current_version = 0
                profile_sections = {}
                created_at = now
                connection.execute(
                    """
                    INSERT INTO career.candidate_profiles(
                        id, user_id, data, created_at, updated_at
                    ) VALUES (
                        %s, %s,
                        '{"display_name":null,"current_version":0,"sections":{}}'::jsonb,
                        %s, %s
                    )
                    """,
                    (
                        profile_id,
                        self.principal.user_id,
                        created_at,
                        now,
                    ),
                )
            else:
                profile_id = str(profile[0])
                profile_data = dict(profile[1] or {})
                current_version = int(
                    profile_data.get("current_version") or 0
                )
                profile_sections = dict(
                    profile_data.get("sections") or {}
                )
                created_at = profile[2]
            for section in sections:
                profile_sections[section] = proposal[section]
                connection.execute(
                    """
                    DELETE FROM career.candidate_facts
                    WHERE user_id = %s
                      AND profile_id = %s
                      AND section = %s
                    """,
                    (
                        self.principal.user_id,
                        profile_id,
                        section,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO career.candidate_facts(
                        id, user_id, profile_id, section, fact_key,
                        fact_value, confirmed_at
                    ) VALUES (
                        %s, %s, %s, %s, 'value', %s::jsonb, %s
                    )
                    """,
                    (
                        str(uuid4()),
                        self.principal.user_id,
                        profile_id,
                        section,
                        json.dumps(
                            proposal[section],
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )
            version = current_version + 1
            profile_data = {
                "display_name": (
                    profile_sections.get("basic") or {}
                ).get("name"),
                "current_version": version,
                "sections": profile_sections,
            }
            connection.execute(
                """
                UPDATE career.candidate_profiles
                SET data = %s::jsonb, updated_at = %s
                WHERE user_id = %s AND id = %s
                """,
                (
                    json.dumps(profile_data, ensure_ascii=False),
                    now,
                    self.principal.user_id,
                    profile_id,
                ),
            )
            resume_data = dict(row[4] or {})
            confirmed = sorted(
                set(preview_data.get("confirmed_sections") or [])
                | set(sections)
            )
            complete = set(confirmed) == set(RESUME_SECTIONS)
            snapshot = {
                "source_import_id": str(row[1]),
                "filename": resume_data.get("filename") or "resume",
                "source_kind": resume_data.get("source_kind") or "text",
                "confirmed_sections": list(sections),
                "sections": profile_sections,
            }
            connection.execute(
                """
                INSERT INTO career.profile_versions(
                    id, user_id, profile_id, version_number,
                    snapshot, created_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    str(uuid4()),
                    self.principal.user_id,
                    profile_id,
                    version,
                    json.dumps(snapshot, ensure_ascii=False),
                    now,
                ),
            )
            preview_data["proposal"] = proposal
            preview_data["confirmed_sections"] = confirmed
            connection.execute(
                """
                UPDATE career.resume_previews
                SET data = %s::jsonb
                WHERE user_id = %s AND id = %s
                """,
                (
                    json.dumps(preview_data, ensure_ascii=False),
                    self.principal.user_id,
                    row[0],
                ),
            )
            resume_data.update(
                {
                    "status": (
                        "confirmed"
                        if complete
                        else "partially_confirmed"
                    ),
                    "sections": {
                        section: proposal[section]
                        for section in confirmed
                    },
                    "confirmed_sections": confirmed,
                    "revision_at": now.isoformat().replace(
                        "+00:00",
                        "Z",
                    ),
                }
            )
            connection.execute(
                """
                UPDATE career.resume_imports
                SET data = %s::jsonb, updated_at = %s
                WHERE user_id = %s AND id = %s
                """,
                (
                    json.dumps(resume_data, ensure_ascii=False),
                    now,
                    self.principal.user_id,
                    row[1],
                ),
            )
        return {
            "profile_id": profile_id,
            "version": version,
            "confirmed_sections": confirmed,
            "complete": complete,
        }

    def get_resume_document(
        self,
        resume_id: str,
        *,
        include_sensitive: bool = False,
    ) -> dict:
        row = self._resume_row(resume_id)
        if row is None:
            raise ResumeServiceError(
                "RESUME_NOT_FOUND",
                "confirmed resume not found",
            )
        document = self._document(row, include_sections=True)
        return (
            document
            if include_sensitive
            else mask_candidate_profile(document)
        )

    def get_candidate_profile(
        self,
        *,
        include_sensitive: bool = False,
    ) -> dict:
        with self.database.transaction(self.principal) as connection:
            row = connection.execute(
                """
                SELECT id, data, created_at, updated_at
                FROM career.candidate_profiles
                WHERE user_id = %s
                ORDER BY updated_at DESC, id ASC
                LIMIT 1
                """,
                (self.principal.user_id,),
            ).fetchone()
        if row is None:
            raise ResumeServiceError(
                "PROFILE_NOT_FOUND",
                "candidate profile not found",
            )
        data = dict(row[1] or {})
        profile = {
            "id": str(row[0]),
            "display_name": data.get("display_name") or "求职档案",
            "current_version": int(data.get("current_version") or 0),
            "sections": dict(data.get("sections") or {}),
            "created_at": str(row[2]),
            "updated_at": str(row[3]),
        }
        return (
            profile
            if include_sensitive
            else mask_candidate_profile(profile)
        )

    def get_profile_versions(self) -> list[dict]:
        with self.database.transaction(self.principal) as connection:
            rows = connection.execute(
                """
                SELECT version_number, snapshot, created_at
                FROM career.profile_versions
                WHERE user_id = %s
                ORDER BY version_number DESC, created_at DESC
                """,
                (self.principal.user_id,),
            ).fetchall()
        return [
            self._version(int(row[0]), dict(row[1] or {}), row[2])
            for row in rows
        ]

    def update_resume_document(
        self,
        resume_id: str,
        *,
        display_name: str,
        target_roles: list[str],
    ) -> dict:
        normalized_name, normalized_roles = self._metadata(
            display_name,
            target_roles,
        )
        with self.database.transaction(self.principal) as connection:
            result = connection.execute(
                """
                UPDATE career.resume_imports
                SET data = data || %s::jsonb,
                    updated_at = now()
                WHERE user_id = %s
                  AND id = %s
                  AND data->>'status' IN (
                      'partially_confirmed', 'confirmed'
                  )
                  AND COALESCE(data->>'deleted_at', '') = ''
                """,
                (
                    json.dumps(
                        {
                            "display_name": normalized_name,
                            "target_roles": normalized_roles,
                        },
                        ensure_ascii=False,
                    ),
                    self.principal.user_id,
                    resume_id,
                ),
            )
            if result.rowcount != 1:
                raise ResumeServiceError(
                    "RESUME_NOT_FOUND",
                    "confirmed resume not found",
                )
        return self.get_resume_document(resume_id)

    def delete_resume_document(
        self,
        resume_id: str,
        *,
        confirm_name: str,
    ) -> dict:
        document = self.get_resume_document(
            resume_id,
            include_sensitive=True,
        )
        if confirm_name != document["display_name"]:
            raise ResumeServiceError(
                "CONFIRMATION_REQUIRED",
                "exact resume name confirmation is required",
            )
        with self.database.transaction(self.principal) as connection:
            row = connection.execute(
                """
                SELECT blob_id
                FROM career.resume_imports
                WHERE user_id = %s
                  AND id = %s
                  AND data->>'status' IN (
                      'partially_confirmed', 'confirmed'
                  )
                  AND COALESCE(data->>'deleted_at', '') = ''
                FOR UPDATE
                """,
                (self.principal.user_id, resume_id),
            ).fetchone()
            if row is None:
                raise ResumeServiceError(
                    "RESUME_NOT_FOUND",
                    "confirmed resume not found",
                )
            connection.execute(
                """
                DELETE FROM career.resume_previews
                WHERE user_id = %s AND resume_import_id = %s
                """,
                (self.principal.user_id, resume_id),
            )
            connection.execute(
                """
                UPDATE career.resume_imports
                SET data = data || jsonb_build_object(
                        'status', 'deleted',
                        'deleted_at', now()
                    ),
                    updated_at = now()
                WHERE user_id = %s AND id = %s
                """,
                (self.principal.user_id, resume_id),
            )
            original_removed = False
            if row[0] is not None:
                result = connection.execute(
                    """
                    UPDATE blob.objects
                    SET deleted_at = now()
                    WHERE id = %s
                      AND scope = 'user'
                      AND user_id = %s
                      AND deleted_at IS NULL
                    """,
                    (row[0], self.principal.user_id),
                )
                original_removed = result.rowcount == 1
        return {
            "resume_id": resume_id,
            "original_removed": original_removed,
        }

    def get_resume_document_versions(self, resume_id: str) -> list[dict]:
        self.get_resume_document(resume_id)
        with self.database.transaction(self.principal) as connection:
            rows = connection.execute(
                """
                SELECT version_number, snapshot, created_at
                FROM career.profile_versions
                WHERE user_id = %s
                  AND snapshot->>'source_import_id' = %s
                ORDER BY version_number DESC, created_at DESC
                """,
                (self.principal.user_id, resume_id),
            ).fetchall()
        return [
            self._version(int(row[0]), dict(row[1] or {}), row[2])
            for row in rows
        ]

    def get_resume_document_original(self, resume_id: str) -> dict:
        row = self._original_row(resume_id)
        if row is None:
            raise ResumeServiceError(
                "ORIGINAL_NOT_FOUND",
                "confirmed resume original not found",
            )
        filename = str(row[0] or row[1] or "resume")
        source_kind = str(
            row[2] or Path(filename).suffix.lstrip(".") or "text"
        )
        return {
            "filename": filename,
            "source_kind": source_kind,
            "size": int(row[3]),
            "preview_kind": (
                "html" if source_kind == "docx" else source_kind
            ),
        }

    def read_resume_document_original(self, resume_id: str) -> dict:
        metadata = self.get_resume_document_original(resume_id)
        row = self._original_row(resume_id)
        assert row is not None
        content = b"".join(
            self.blobs.iter_content(self.principal, str(row[4]))
        )
        return {
            "filename": metadata["filename"],
            "source_kind": metadata["source_kind"],
            "bytes": content,
            "media_type": str(row[5]),
        }

    def render_resume_document_original(self, resume_id: str) -> dict:
        original = self.read_resume_document_original(resume_id)
        if original["source_kind"] == "docx":
            return {
                **original,
                "bytes": ResumeService._docx_html(original["bytes"]),
                "media_type": "text/html; charset=utf-8",
            }
        return original

    def get_profile_original(self) -> dict:
        return self.get_resume_document_original(
            self._profile_resume_id()
        )

    def read_profile_original(self) -> dict:
        return self.read_resume_document_original(
            self._profile_resume_id()
        )

    def render_profile_original(self) -> dict:
        return self.render_resume_document_original(
            self._profile_resume_id()
        )

    def discard_resume_import(self, preview_token: str) -> dict:
        with self.database.transaction(self.principal) as connection:
            row = connection.execute(
                """
                SELECT p.id, p.resume_import_id, r.data->>'status',
                       r.blob_id
                FROM career.resume_previews p
                JOIN career.resume_imports r
                  ON r.user_id = p.user_id
                 AND r.id = p.resume_import_id
                WHERE p.user_id = %s
                  AND p.data->>'preview_token' = %s
                FOR UPDATE OF p, r
                """,
                (self.principal.user_id, preview_token),
            ).fetchone()
            if row is None:
                raise ResumeServiceError(
                    "PREVIEW_NOT_FOUND",
                    "resume preview not found",
                )
            if row[2] in {"partially_confirmed", "confirmed"}:
                raise ResumeServiceError(
                    "CONFIRMATION_REQUIRED",
                    "confirmed resume import cannot be discarded",
                )
            connection.execute(
                """
                DELETE FROM career.resume_previews
                WHERE user_id = %s AND id = %s
                """,
                (self.principal.user_id, row[0]),
            )
            connection.execute(
                """
                DELETE FROM career.resume_imports
                WHERE user_id = %s AND id = %s
                """,
                (self.principal.user_id, row[1]),
            )
            if row[3] is not None:
                connection.execute(
                    """
                    UPDATE blob.objects
                    SET deleted_at = now()
                    WHERE id = %s
                      AND scope = 'user'
                      AND user_id = %s
                      AND deleted_at IS NULL
                    """,
                    (row[3], self.principal.user_id),
                )
        return {"previews": 1, "imports": 1}

    def delete_candidate_profile(self, confirm_text: str) -> dict:
        if confirm_text != "DELETE MY CAREER PROFILE":
            raise ResumeServiceError(
                "CONFIRMATION_REQUIRED",
                "exact deletion confirmation is required",
            )
        user_id = self.principal.user_id
        with self.database.transaction(self.principal) as connection:
            counts = {
                "profiles": self._count(
                    connection,
                    "career.candidate_profiles",
                ),
                "facts": self._count(
                    connection,
                    "career.candidate_facts",
                ),
                "versions": self._count(
                    connection,
                    "career.profile_versions",
                ),
                "previews": self._count(
                    connection,
                    "career.resume_previews",
                ),
                "imports": self._count(
                    connection,
                    "career.resume_imports",
                ),
            }
            blob_ids = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT blob_id
                    FROM career.resume_imports
                    WHERE user_id = %s AND blob_id IS NOT NULL
                    """,
                    (user_id,),
                ).fetchall()
            ]
            connection.execute(
                """
                DELETE FROM career.interview_turns
                WHERE user_id = %s
                """,
                (user_id,),
            )
            connection.execute(
                """
                DELETE FROM career.interview_sessions
                WHERE user_id = %s
                """,
                (user_id,),
            )
            for table in (
                "resume_previews",
                "candidate_facts",
                "profile_versions",
                "candidate_profiles",
                "resume_imports",
            ):
                connection.execute(
                    f"DELETE FROM career.{table} WHERE user_id = %s",
                    (user_id,),
                )
            if blob_ids:
                connection.execute(
                    """
                    UPDATE blob.objects
                    SET deleted_at = now()
                    WHERE user_id = %s
                      AND scope = 'user'
                      AND id = ANY(%s)
                      AND deleted_at IS NULL
                    """,
                    (user_id, blob_ids),
                )
        return counts

    def _resume_row(self, resume_id: str):
        with self.database.transaction(self.principal) as connection:
            return connection.execute(
                """
                SELECT id, data, created_at, updated_at
                FROM career.resume_imports
                WHERE user_id = %s
                  AND id = %s
                  AND data->>'status' IN (
                      'partially_confirmed', 'confirmed'
                  )
                  AND COALESCE(data->>'deleted_at', '') = ''
                """,
                (self.principal.user_id, resume_id),
            ).fetchone()

    def _original_row(self, resume_id: str):
        with self.database.transaction(self.principal) as connection:
            return connection.execute(
                """
                SELECT r.data->>'filename', b.original_name,
                       r.data->>'source_kind', b.size_bytes, b.id,
                       b.media_type
                FROM career.resume_imports r
                JOIN blob.objects b
                  ON b.id = r.blob_id
                 AND b.scope = 'user'
                 AND b.user_id = r.user_id
                WHERE r.user_id = %s
                  AND r.id = %s
                  AND r.data->>'status' IN (
                      'partially_confirmed', 'confirmed'
                  )
                  AND COALESCE(r.data->>'deleted_at', '') = ''
                  AND b.deleted_at IS NULL
                """,
                (self.principal.user_id, resume_id),
            ).fetchone()

    def _profile_resume_id(self) -> str:
        with self.database.transaction(self.principal) as connection:
            row = connection.execute(
                """
                SELECT pv.snapshot->>'source_import_id'
                FROM career.candidate_profiles cp
                JOIN career.profile_versions pv
                  ON pv.user_id = cp.user_id
                 AND pv.profile_id = cp.id
                 AND pv.version_number =
                     COALESCE((cp.data->>'current_version')::integer, 0)
                WHERE cp.user_id = %s
                ORDER BY cp.updated_at DESC, cp.id ASC
                LIMIT 1
                """,
                (self.principal.user_id,),
            ).fetchone()
        if row is None or not row[0]:
            raise ResumeServiceError(
                "ORIGINAL_NOT_FOUND",
                "confirmed resume original not found",
            )
        return str(row[0])

    def _valid_import(self, upload_token: str) -> dict:
        with self.database.transaction(self.principal) as connection:
            row = connection.execute(
                """
                SELECT id, data
                FROM career.resume_imports
                WHERE user_id = %s
                  AND data->>'upload_token' = %s
                  AND COALESCE(data->>'deleted_at', '') = ''
                """,
                (self.principal.user_id, upload_token),
            ).fetchone()
        if row is None:
            raise ResumeServiceError(
                "UPLOAD_NOT_FOUND",
                "resume upload not found",
            )
        data = dict(row[1] or {})
        expires_at = datetime.fromisoformat(
            str(data["expires_at"]).replace("Z", "+00:00")
        )
        if expires_at < datetime.now(timezone.utc):
            raise ResumeServiceError(
                "UPLOAD_EXPIRED",
                "resume upload expired",
            )
        return {"id": str(row[0]), **data}

    def _profile_or_none(self) -> dict | None:
        try:
            return self.get_candidate_profile(include_sensitive=True)
        except ResumeServiceError as exc:
            if exc.code == "PROFILE_NOT_FOUND":
                return None
            raise

    def _count(self, connection, table: str) -> int:
        return int(
            connection.execute(
                f"SELECT count(*) FROM {table} WHERE user_id = %s",
                (self.principal.user_id,),
            ).fetchone()[0]
        )

    @staticmethod
    def _document(row, *, include_sections: bool = False) -> dict:
        data = dict(row[1] or {})
        sections = dict(data.get("sections") or {})
        document = {
            "id": str(row[0]),
            "filename": data.get("filename") or "resume",
            "display_name": (
                data.get("display_name")
                or data.get("filename")
                or "未命名简历"
            ),
            "target_roles": list(data.get("target_roles") or []),
            "source_kind": data.get("source_kind") or "text",
            "status": data.get("status") or "confirmed",
            "confirmed_sections": list(
                data.get("confirmed_sections") or sections.keys()
            ),
            "created_at": str(row[2]),
            "updated_at": str(row[3]),
        }
        if include_sections:
            document["sections"] = sections
        return document

    @staticmethod
    def _version(number: int, snapshot: dict, created_at) -> dict:
        return {
            "version": number,
            "confirmed_sections": list(
                snapshot.get("confirmed_sections") or []
            ),
            "filename": snapshot.get("filename") or "resume",
            "source_kind": snapshot.get("source_kind") or "text",
            "created_at": str(created_at),
        }

    @staticmethod
    def _metadata(
        display_name: str,
        target_roles: list[str],
    ) -> tuple[str, list[str]]:
        if not isinstance(display_name, str):
            raise ResumeServiceError(
                "INVALID_INPUT",
                "display_name must be a string",
            )
        normalized_name = display_name.strip()
        if not 1 <= len(normalized_name) <= 80:
            raise ResumeServiceError(
                "INVALID_INPUT",
                "display_name must contain 1 to 80 characters",
            )
        if not isinstance(target_roles, list) or not all(
            isinstance(role, str) for role in target_roles
        ):
            raise ResumeServiceError(
                "INVALID_INPUT",
                "target_roles must be a list of strings",
            )
        normalized_roles = list(
            dict.fromkeys(
                role.strip()
                for role in target_roles
                if role.strip()
            )
        )
        if len(normalized_roles) > 10:
            raise ResumeServiceError(
                "INVALID_INPUT",
                "target_roles must contain at most 10 labels",
            )
        if any(len(role) > 30 for role in normalized_roles):
            raise ResumeServiceError(
                "INVALID_INPUT",
                "target role labels must contain at most 30 characters",
            )
        return normalized_name, normalized_roles

    @staticmethod
    def _staged_data(
        extracted,
        *,
        upload_token: str,
        expires_at: datetime,
    ) -> dict:
        return {
            "status": "staged",
            "upload_token": upload_token,
            "filename": extracted.filename,
            "display_name": extracted.filename,
            "target_roles": [],
            "source_kind": extracted.source_kind,
            "extracted_text": extracted.text,
            "extraction_method": extracted.extraction_method,
            "extraction_metadata": extracted.extraction_metadata,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "sections": {},
            "confirmed_sections": [],
        }
