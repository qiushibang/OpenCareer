from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from coworker.runtime.local_coordinator import LocalRuntimeCoordinator
from coworker.server.app import create_app
from coworker.server.identity import Principal
from coworker.server.manager import SessionManager
from coworker.storage.postgres.blob_repository import PostgresBlobRepository
from coworker.storage.postgres.database import CloudDatabase
from coworker.storage.postgres.resume_service import PostgresResumeService
from extensions.career_mcp import server as career_server
from extensions.career_mcp.services.resumes import ResumeServiceError
from extensions.career_mcp.services.resumes import ResumeService


PROPOSAL = {
    "basic": {
        "name": "Zhang San",
        "phone": "13800001234",
        "email": "zhang@example.com",
        "location": "Beijing",
        "summary": "AI Engineer",
    },
    "education": [],
    "experience": [],
    "project": [],
    "skill": [{"name": "Python", "level": None, "evidence": None}],
    "missing_fields": [],
    "warnings": [],
}


@pytest.fixture()
def database() -> CloudDatabase:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL is required")
    database = CloudDatabase.from_url(url, min_size=1, max_size=2)
    database.migrate()
    try:
        yield database
    finally:
        database.close()


def _seed_resume(
    database: CloudDatabase,
    principal: Principal,
    *,
    filename: str,
) -> tuple[str, bytes]:
    resume_id = f"resume-{uuid4()}"
    profile_id = f"profile-{uuid4()}"
    content = f"{principal.user_id}:{filename}".encode()
    blobs = PostgresBlobRepository(database)
    with database.shared_transaction() as connection:
        connection.execute(
            """
            INSERT INTO identity.users(id)
            VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (principal.user_id,),
        )
    blob = blobs.put(
        principal,
        content=content,
        kind="resume_original",
        media_type="text/plain",
        original_name=filename,
    )
    sections = {
        "basic": {
            "name": "Zhang San",
            "phone": "13800001234",
            "email": "zhang@example.com",
        },
        "skill": [{"name": "Python"}],
    }
    with database.transaction(principal) as connection:
        connection.execute(
            """
            INSERT INTO career.resume_imports(
                id, user_id, blob_id, content_hash, data,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s::jsonb, now(), now()
            )
            """,
            (
                resume_id,
                principal.user_id,
                blob.id,
                blob.sha256,
                __import__("json").dumps(
                    {
                        "filename": filename,
                        "display_name": filename,
                        "target_roles": ["AI Engineer"],
                        "source_kind": "text",
                        "status": "confirmed",
                        "confirmed_sections": ["basic", "skill"],
                        "sections": sections,
                    }
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO career.candidate_profiles(
                id, user_id, data, created_at, updated_at
            ) VALUES (%s, %s, %s::jsonb, now(), now())
            """,
            (
                profile_id,
                principal.user_id,
                __import__("json").dumps(
                    {
                        "display_name": "Primary profile",
                        "current_version": 3,
                        "sections": sections,
                    }
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO career.profile_versions(
                id, user_id, profile_id, version_number, snapshot,
                created_at
            ) VALUES (%s, %s, %s, 3, %s::jsonb, now())
            """,
            (
                f"version-{uuid4()}",
                principal.user_id,
                profile_id,
                __import__("json").dumps(
                    {
                        "source_import_id": resume_id,
                        "filename": filename,
                        "source_kind": "text",
                        "confirmed_sections": ["basic", "skill"],
                        "sections": sections,
                    }
                ),
            ),
        )
    return resume_id, content


def test_resume_service_lists_only_current_tenant_and_masks_detail(
    database: CloudDatabase,
) -> None:
    alice = Principal(f"alice-{uuid4()}", "test")
    bob = Principal(f"bob-{uuid4()}", "test")
    alice_resume, _ = _seed_resume(
        database,
        alice,
        filename="alice.txt",
    )
    bob_resume, _ = _seed_resume(database, bob, filename="bob.txt")

    service = PostgresResumeService(
        database,
        alice,
        PostgresBlobRepository(database),
    )

    assert [item["id"] for item in service.list_resume_documents()] == [
        alice_resume
    ]
    assert (
        service.get_resume_document(alice_resume)["sections"]["basic"][
            "phone"
        ]
        == "*******1234"
    )
    with pytest.raises(ResumeServiceError) as denied:
        service.get_resume_document(bob_resume)
    assert denied.value.code == "RESUME_NOT_FOUND"


def test_resume_service_reads_profile_and_versions_from_profile_tables(
    database: CloudDatabase,
) -> None:
    principal = Principal(f"profile-{uuid4()}", "test")
    _seed_resume(database, principal, filename="profile.txt")
    service = PostgresResumeService(
        database,
        principal,
        PostgresBlobRepository(database),
    )

    profile = service.get_candidate_profile()
    versions = service.get_profile_versions()

    assert profile["display_name"] == "Primary profile"
    assert profile["current_version"] == 3
    assert profile["sections"]["basic"]["email"] == "z***@example.com"
    assert versions[0]["version"] == 3
    assert versions[0]["filename"] == "profile.txt"


def test_resume_service_streams_original_blob(
    database: CloudDatabase,
) -> None:
    principal = Principal(f"blob-{uuid4()}", "test")
    resume_id, content = _seed_resume(
        database,
        principal,
        filename="original.txt",
    )
    service = PostgresResumeService(
        database,
        principal,
        PostgresBlobRepository(database),
    )

    metadata = service.get_resume_document_original(resume_id)
    original = service.read_resume_document_original(resume_id)

    assert metadata["filename"] == "original.txt"
    assert metadata["size"] == len(content)
    assert metadata["preview_kind"] == "text"
    assert original["bytes"] == content


def test_resume_service_updates_metadata_for_current_tenant(
    database: CloudDatabase,
) -> None:
    alice = Principal(f"update-alice-{uuid4()}", "test")
    bob = Principal(f"update-bob-{uuid4()}", "test")
    alice_resume, _ = _seed_resume(
        database,
        alice,
        filename="alice-update.txt",
    )
    bob_resume, _ = _seed_resume(
        database,
        bob,
        filename="bob-update.txt",
    )
    service = PostgresResumeService(
        database,
        alice,
        PostgresBlobRepository(database),
    )

    updated = service.update_resume_document(
        alice_resume,
        display_name="AI 产品经理简历",
        target_roles=[" AI 产品经理 ", "AI 产品经理", "Agent 产品经理"],
    )

    assert updated["display_name"] == "AI 产品经理简历"
    assert updated["target_roles"] == ["AI 产品经理", "Agent 产品经理"]
    with pytest.raises(ResumeServiceError) as denied:
        service.update_resume_document(
            bob_resume,
            display_name="Forbidden",
            target_roles=[],
        )
    assert denied.value.code == "RESUME_NOT_FOUND"


def test_resume_service_soft_deletes_resume_and_original_blob(
    database: CloudDatabase,
) -> None:
    principal = Principal(f"delete-{uuid4()}", "test")
    resume_id, _ = _seed_resume(
        database,
        principal,
        filename="delete.txt",
    )
    blobs = PostgresBlobRepository(database)
    service = PostgresResumeService(database, principal, blobs)

    with pytest.raises(ResumeServiceError) as denied:
        service.delete_resume_document(
            resume_id,
            confirm_name="wrong",
        )
    deleted = service.delete_resume_document(
        resume_id,
        confirm_name="delete.txt",
    )

    assert denied.value.code == "CONFIRMATION_REQUIRED"
    assert deleted == {
        "resume_id": resume_id,
        "original_removed": True,
    }
    with pytest.raises(ResumeServiceError) as missing:
        service.get_resume_document(resume_id)
    assert missing.value.code == "RESUME_NOT_FOUND"
    with database.transaction(principal) as connection:
        row = connection.execute(
            """
            SELECT r.data->>'deleted_at', b.deleted_at
            FROM career.resume_imports r
            JOIN blob.objects b ON b.id = r.blob_id
            WHERE r.user_id = %s AND r.id = %s
            """,
            (principal.user_id, resume_id),
        ).fetchone()
    assert row[0]
    assert row[1] is not None


def test_profile_original_uses_current_profile_version(
    database: CloudDatabase,
) -> None:
    principal = Principal(f"profile-original-{uuid4()}", "test")
    resume_id, content = _seed_resume(
        database,
        principal,
        filename="profile-original.txt",
    )
    service = PostgresResumeService(
        database,
        principal,
        PostgresBlobRepository(database),
    )

    metadata = service.get_profile_original()
    rendered = service.render_profile_original()

    assert resume_id
    assert metadata["filename"] == "profile-original.txt"
    assert rendered["bytes"] == content
    assert rendered["media_type"] == "text/plain"


def test_resume_rest_uses_request_principal_in_postgres_mode(
    database: CloudDatabase,
    tmp_path,
    monkeypatch,
) -> None:
    alice = Principal(f"rest-alice-{uuid4()}", "test")
    bob = Principal(f"rest-bob-{uuid4()}", "test")
    alice_resume, content = _seed_resume(
        database,
        alice,
        filename="alice-rest.txt",
    )
    bob_resume, _ = _seed_resume(
        database,
        bob,
        filename="bob-rest.txt",
    )
    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        f"{alice.user_id}:alice-token,{bob.user_id}:bob-token",
    )

    class Runtime:
        mode = "postgres"
        origin_repository = None
        coordinator = LocalRuntimeCoordinator()

        def __init__(self, current: CloudDatabase) -> None:
            self.database = current

        def health(self) -> dict[str, str]:
            return {
                "mode": "postgres",
                "postgres": "ready",
                "redis": "ready",
            }

        def close(self) -> None:
            pass

    client = TestClient(
        create_app(
            SessionManager(data_dir=tmp_path / "state"),
            storage_runtime=Runtime(database),
        )
    )
    alice_headers = {"X-OpenWorker-Token": "alice-token"}
    bob_headers = {"X-OpenWorker-Token": "bob-token"}

    alice_list = client.get(
        "/v1/career/resumes",
        headers=alice_headers,
    )
    bob_list = client.get(
        "/v1/career/resumes",
        headers=bob_headers,
    )
    denied = client.get(
        f"/v1/career/resumes/{bob_resume}",
        headers=alice_headers,
    )
    original = client.get(
        f"/v1/career/resumes/{alice_resume}/original/content",
        headers=alice_headers,
    )

    assert [item["id"] for item in alice_list.json()["resumes"]] == [
        alice_resume
    ]
    assert [item["id"] for item in bob_list.json()["resumes"]] == [
        bob_resume
    ]
    assert denied.status_code == 404
    assert original.content == content


def test_resume_stage_rest_persists_blob_and_import_in_postgres(
    database: CloudDatabase,
    tmp_path,
    monkeypatch,
) -> None:
    principal = Principal(f"stage-{uuid4()}", "test")
    with database.shared_transaction() as connection:
        connection.execute(
            """
            INSERT INTO identity.users(id)
            VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (principal.user_id,),
        )
    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        f"{principal.user_id}:stage-token",
    )

    class Runtime:
        mode = "postgres"
        origin_repository = None
        coordinator = LocalRuntimeCoordinator()

        def __init__(self, current: CloudDatabase) -> None:
            self.database = current

        def health(self) -> dict[str, str]:
            return {
                "mode": "postgres",
                "postgres": "ready",
                "redis": "ready",
            }

        def close(self) -> None:
            pass

    client = TestClient(
        create_app(
            SessionManager(data_dir=tmp_path / "state"),
            storage_runtime=Runtime(database),
        )
    )
    response = client.post(
        "/v1/career/resumes/stage",
        headers={"X-OpenWorker-Token": "stage-token"},
        json={
            "filename": "stage.txt",
            "mime": "text/plain",
            "text": "Zhang San\nPython AI Engineer",
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    with database.transaction(principal) as connection:
        row = connection.execute(
            """
            SELECT r.data->>'upload_token', r.data->>'extracted_text',
                   b.original_name, b.content
            FROM career.resume_imports r
            JOIN blob.objects b ON b.id = r.blob_id
            WHERE r.user_id = %s
              AND r.data->>'upload_token' = %s
            """,
            (principal.user_id, response.json()["upload_token"]),
        ).fetchone()
    assert row[0] == response.json()["upload_token"]
    assert row[1] == "Zhang San\nPython AI Engineer"
    assert row[2] == "stage.txt"
    assert bytes(row[3]) == b"Zhang San\nPython AI Engineer"


def test_resume_preview_and_confirmation_persist_profile_facts(
    database: CloudDatabase,
) -> None:
    principal = Principal(f"confirm-{uuid4()}", "test")
    with database.shared_transaction() as connection:
        connection.execute(
            "INSERT INTO identity.users(id) VALUES (%s)",
            (principal.user_id,),
        )
    service = PostgresResumeService(
        database,
        principal,
        PostgresBlobRepository(database),
    )
    staged = service.stage_resume(
        filename="confirm.txt",
        mime="text/plain",
        text="Zhang San\nPython AI Engineer",
    )

    imported = service.get_resume_import_text(staged["upload_token"])
    preview = service.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )
    with pytest.raises(ResumeServiceError) as missing:
        service.get_candidate_profile()
    first = service.confirm_resume_sections(
        preview["preview_token"],
        ["basic"],
        corrections={},
    )
    second = service.confirm_resume_sections(
        preview["preview_token"],
        ["skill"],
        corrections={
            "skill": [
                {
                    "name": "Python",
                    "level": "advanced",
                    "evidence": None,
                }
            ]
        },
    )
    profile = service.get_candidate_profile(include_sensitive=True)

    assert imported["text"] == "Zhang San\nPython AI Engineer"
    assert preview["proposal"]["basic"]["phone"] == "*******1234"
    assert missing.value.code == "PROFILE_NOT_FOUND"
    assert first["version"] == 1
    assert second["version"] == 2
    assert profile["sections"]["skill"][0]["level"] == "advanced"
    with database.transaction(principal) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM career.candidate_facts
               WHERE user_id = %s),
              (SELECT count(*) FROM career.profile_versions
               WHERE user_id = %s)
            """,
            (principal.user_id, principal.user_id),
        ).fetchone()
    assert counts == (2, 2)


def test_career_mcp_selects_principal_scoped_postgres_resume_service(
    database: CloudDatabase,
    monkeypatch,
) -> None:
    principal = Principal(f"mcp-{uuid4()}", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://configured")
    monkeypatch.setenv(
        "OPENCAR_PRINCIPAL_USER_ID",
        principal.user_id,
    )
    monkeypatch.setattr(career_server, "_cloud_database", database)

    service = career_server._resume_service()

    assert isinstance(service, PostgresResumeService)
    assert service.principal.user_id == principal.user_id


def test_career_mcp_fails_closed_without_cloud_principal(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://configured")
    monkeypatch.delenv("OPENCAR_PRINCIPAL_USER_ID", raising=False)

    with pytest.raises(RuntimeError, match="OPENCAR_PRINCIPAL_USER_ID"):
        career_server._resume_service()


def test_discard_resume_preview_removes_unconfirmed_import_and_blob(
    database: CloudDatabase,
) -> None:
    principal = Principal(f"discard-{uuid4()}", "test")
    with database.shared_transaction() as connection:
        connection.execute(
            "INSERT INTO identity.users(id) VALUES (%s)",
            (principal.user_id,),
        )
    service = PostgresResumeService(
        database,
        principal,
        PostgresBlobRepository(database),
    )
    staged = service.stage_resume(
        filename="discard.txt",
        mime="text/plain",
        text="Discard this resume after validating the complete private flow.",
    )
    preview = service.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )

    discarded = service.discard_resume_import(
        preview["preview_token"]
    )

    assert discarded == {"previews": 1, "imports": 1}
    with database.transaction(principal) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM career.resume_imports
               WHERE user_id = %s),
              (SELECT count(*) FROM career.resume_previews
               WHERE user_id = %s),
              (SELECT count(*) FROM blob.objects
               WHERE user_id = %s AND deleted_at IS NULL)
            """,
            (
                principal.user_id,
                principal.user_id,
                principal.user_id,
            ),
        ).fetchone()
    assert counts == (0, 0, 0)


def test_delete_candidate_profile_clears_postgres_resume_domain(
    database: CloudDatabase,
) -> None:
    principal = Principal(f"delete-profile-{uuid4()}", "test")
    with database.shared_transaction() as connection:
        connection.execute(
            "INSERT INTO identity.users(id) VALUES (%s)",
            (principal.user_id,),
        )
    service = PostgresResumeService(
        database,
        principal,
        PostgresBlobRepository(database),
    )
    staged = service.stage_resume(
        filename="delete-profile.txt",
        mime="text/plain",
        text="Delete this profile after validating the complete private flow.",
    )
    preview = service.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )
    service.confirm_resume_sections(
        preview["preview_token"],
        ["basic"],
        corrections={},
    )

    with pytest.raises(ResumeServiceError) as denied:
        service.delete_candidate_profile("删除")
    deleted = service.delete_candidate_profile(
        "DELETE MY CAREER PROFILE"
    )

    assert denied.value.code == "CONFIRMATION_REQUIRED"
    assert deleted["profiles"] == 1
    assert deleted["facts"] == 1
    assert deleted["versions"] == 1
    assert deleted["imports"] == 1
    with database.transaction(principal) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM career.candidate_profiles
               WHERE user_id = %s),
              (SELECT count(*) FROM career.resume_imports
               WHERE user_id = %s),
              (SELECT count(*) FROM blob.objects
               WHERE user_id = %s AND deleted_at IS NULL)
            """,
            (
                principal.user_id,
                principal.user_id,
                principal.user_id,
            ),
        ).fetchone()
    assert counts == (0, 0, 0)


def test_postgres_text_stage_does_not_initialize_ocr(
    database: CloudDatabase,
    monkeypatch,
) -> None:
    principal = Principal(f"no-ocr-{uuid4()}", "test")
    with database.shared_transaction() as connection:
        connection.execute(
            "INSERT INTO identity.users(id) VALUES (%s)",
            (principal.user_id,),
        )
    monkeypatch.setattr(
        ResumeService,
        "_default_ocr_service",
        lambda: (_ for _ in ()).throw(
            AssertionError("OCR must stay lazy")
        ),
    )
    service = PostgresResumeService(
        database,
        principal,
        PostgresBlobRepository(database),
    )

    staged = service.stage_resume(
        filename="native.txt",
        mime="text/plain",
        text="Native text resume with enough content for direct extraction.",
    )

    assert staged["extraction_method"] == "native"


def test_career_mcp_cloud_factories_share_principal_postgres_boundaries(
    database: CloudDatabase,
    monkeypatch,
) -> None:
    principal = Principal(f"mcp-services-{uuid4()}", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://configured")
    monkeypatch.setenv(
        "OPENCAR_PRINCIPAL_USER_ID",
        principal.user_id,
    )
    monkeypatch.setattr(career_server, "_cloud_database", database)

    jobs = career_server._job_service()
    tracking = career_server._job_tracking_service()
    resumes = career_server._resume_service()
    interviews = career_server._interview_service()

    assert jobs._injected_repository_session is not None
    assert tracking._injected_repository_session is not None
    assert resumes.principal.user_id == principal.user_id
    assert interviews._injected_repository_session is not None
    assert interviews._principal.user_id == principal.user_id
