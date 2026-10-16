import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.database.resume_repository import ResumeRepository


NOW = "2026-08-06T08:00:00Z"
EXPIRES = "2026-08-07T08:00:00Z"
NATIVE_METADATA = {
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
HYBRID_METADATA = {
    **NATIVE_METADATA,
    "method": "hybrid",
    "total_pages": 2,
    "native_pages": [1],
    "ocr_pages": [2],
    "ocr_attempted_pages": [2],
    "mean_confidence": 0.91,
    "quality": "good",
    "engine": {
        "name": "rapidocr-onnxruntime",
        "version": "3.9.2",
        "model_ids": ["det", "cls", "rec"],
        "model_sha256": ["a" * 64, "b" * 64, "c" * 64],
    },
}
PROPOSAL = {
    "basic": {
        "name": "Zhang San",
        "phone": "13800001234",
        "email": "zhang@example.com",
        "location": "Beijing",
        "summary": None,
    },
    "education": [
        {
            "school": "Example University",
            "degree": "Bachelor",
            "major": "Computer Science",
            "start_date": "2022-09",
            "end_date": "2026-06",
            "details": [],
        }
    ],
    "experience": [],
    "project": [],
    "skill": [],
    "missing_fields": [],
    "warnings": [],
}


def _repository(tmp_path):
    connection = connect(tmp_path / "career.sqlite3")
    return connection, ResumeRepository(connection)


def test_preview_does_not_create_profile_facts(tmp_path):
    connection, repository = _repository(tmp_path)
    try:
        resume_import = repository.create_or_reuse_import(
            content_hash="hash-1",
            upload_token="upload-1",
            source_kind="text",
            original_filename="resume.txt",
            private_path="resumes/hash-1.txt",
            extracted_text="Synthetic resume text for tests",
            expires_at=EXPIRES,
            now=NOW,
        )

        preview = repository.create_preview(
            resume_import_id=resume_import["id"],
            preview_token="preview-1",
            proposal=PROPOSAL,
            conflicts=[],
            expires_at=EXPIRES,
            now=NOW,
        )
        connection.commit()

        assert preview["preview_token"] == "preview-1"
        assert connection.execute(
            "SELECT COUNT(*) FROM candidate_facts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM candidate_profile"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_confirming_sections_versions_profile_and_preserves_other_sections(
    tmp_path,
):
    connection, repository = _repository(tmp_path)
    try:
        resume_import = repository.create_or_reuse_import(
            content_hash="hash-1",
            upload_token="upload-1",
            source_kind="text",
            original_filename="resume.txt",
            private_path="resumes/hash-1.txt",
            extracted_text="Synthetic resume text for tests",
            expires_at=EXPIRES,
            now=NOW,
        )
        repository.create_preview(
            resume_import_id=resume_import["id"],
            preview_token="preview-1",
            proposal=PROPOSAL,
            conflicts=[],
            expires_at=EXPIRES,
            now=NOW,
        )

        first = repository.confirm_sections(
            preview_token="preview-1",
            sections=["basic"],
            corrections={},
            now=NOW,
        )
        second = repository.confirm_sections(
            preview_token="preview-1",
            sections=["education"],
            corrections={
                "education": [
                    {
                        **PROPOSAL["education"][0],
                        "degree": "BSc",
                    }
                ]
            },
            now="2026-08-06T08:10:00Z",
        )
        connection.commit()

        profile = repository.get_profile()
        assert first["version"] == 1
        assert second["version"] == 2
        assert profile["current_version"] == 2
        assert profile["sections"]["basic"]["name"] == "Zhang San"
        assert profile["sections"]["education"][0]["degree"] == "BSc"
        versions = connection.execute(
            "SELECT version_number, snapshot_json FROM profile_versions "
            "ORDER BY version_number"
        ).fetchall()
        assert [row["version_number"] for row in versions] == [1, 2]
        assert '"education"' not in versions[0]["snapshot_json"]
    finally:
        connection.close()


def test_duplicate_import_reuses_content_addressed_record(tmp_path):
    connection, repository = _repository(tmp_path)
    try:
        first = repository.create_or_reuse_import(
            content_hash="same-hash",
            upload_token="upload-1",
            source_kind="pdf",
            original_filename="first.pdf",
            private_path="resumes/same-hash.pdf",
            extracted_text="Synthetic resume text for tests",
            expires_at=EXPIRES,
            now=NOW,
        )
        second = repository.create_or_reuse_import(
            content_hash="same-hash",
            upload_token="upload-2",
            source_kind="pdf",
            original_filename="second.pdf",
            private_path="resumes/same-hash.pdf",
            extracted_text="Synthetic resume text for tests",
            expires_at=EXPIRES,
            now=NOW,
        )
        connection.commit()

        assert second["id"] == first["id"]
        assert connection.execute(
            "SELECT COUNT(*) FROM resume_imports"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_active_import_reuse_refreshes_extraction_provenance(tmp_path):
    connection, repository = _repository(tmp_path)
    try:
        first = repository.create_or_reuse_import(
            content_hash="active-hash",
            upload_token="active-upload-1",
            source_kind="pdf",
            original_filename="first.pdf",
            private_path="resumes/active-hash.pdf",
            extracted_text="First native extraction",
            extraction_method="native",
            extraction_metadata=NATIVE_METADATA,
            expires_at=EXPIRES,
            now=NOW,
        )
        second = repository.create_or_reuse_import(
            content_hash="active-hash",
            upload_token="active-upload-2",
            source_kind="pdf",
            original_filename="second.pdf",
            private_path="resumes/active-hash.pdf",
            extracted_text="Refreshed hybrid extraction",
            extraction_method="hybrid",
            extraction_metadata=HYBRID_METADATA,
            expires_at=EXPIRES,
            now="2026-08-06T09:00:00Z",
        )

        assert second["id"] == first["id"]
        assert second["upload_token"] == "active-upload-1"
        assert second["original_filename"] == "second.pdf"
        assert second["extracted_text"] == "Refreshed hybrid extraction"
        assert second["extraction_method"] == "hybrid"
        assert second["extraction_metadata"] == HYBRID_METADATA
        assert "extraction_metadata_json" not in second
        assert repository.get_import_by_upload_token(
            "active-upload-1"
        )["extraction_metadata"] == HYBRID_METADATA
    finally:
        connection.close()


def test_expired_import_reuse_refreshes_token_and_provenance(tmp_path):
    connection, repository = _repository(tmp_path)
    try:
        first = repository.create_or_reuse_import(
            content_hash="expired-hash",
            upload_token="expired-upload-1",
            source_kind="pdf",
            original_filename="first.pdf",
            private_path="resumes/expired-hash.pdf",
            extracted_text="First native extraction",
            extraction_method="native",
            extraction_metadata=NATIVE_METADATA,
            expires_at="2026-08-06T08:30:00Z",
            now=NOW,
        )
        second = repository.create_or_reuse_import(
            content_hash="expired-hash",
            upload_token="expired-upload-2",
            source_kind="pdf",
            original_filename="second.pdf",
            private_path="resumes/expired-hash.pdf",
            extracted_text="Refreshed hybrid extraction",
            extraction_method="hybrid",
            extraction_metadata=HYBRID_METADATA,
            expires_at="2026-08-07T09:00:00Z",
            now="2026-08-06T09:00:00Z",
        )

        assert second["id"] == first["id"]
        assert second["upload_token"] == "expired-upload-2"
        assert second["extraction_method"] == "hybrid"
        assert second["extraction_metadata"] == HYBRID_METADATA
        assert second["original_filename"] == "second.pdf"
    finally:
        connection.close()


def test_soft_deleted_import_reuse_restores_provenance(tmp_path):
    connection, repository = _repository(tmp_path)
    try:
        first = repository.create_or_reuse_import(
            content_hash="deleted-hash",
            upload_token="deleted-upload-1",
            source_kind="pdf",
            original_filename="deleted.pdf",
            private_path="resumes/deleted-hash.pdf",
            extracted_text="First native extraction",
            extraction_method="native",
            extraction_metadata=NATIVE_METADATA,
            expires_at=EXPIRES,
            now=NOW,
        )
        connection.execute(
            """
            UPDATE resume_imports
            SET extracted_text = '', deleted_at = ?, status = 'confirmed'
            WHERE id = ?
            """,
            ("2026-08-06T08:30:00Z", first["id"]),
        )

        restored = repository.create_or_reuse_import(
            content_hash="deleted-hash",
            upload_token="deleted-upload-2",
            source_kind="pdf",
            original_filename="restored.pdf",
            private_path="resumes/deleted-hash.pdf",
            extracted_text="Restored hybrid extraction",
            extraction_method="hybrid",
            extraction_metadata=HYBRID_METADATA,
            expires_at="2026-08-07T09:00:00Z",
            now="2026-08-06T09:00:00Z",
        )

        assert restored["id"] == first["id"]
        assert restored["upload_token"] == "deleted-upload-2"
        assert restored["status"] == "staged"
        assert restored["deleted_at"] is None
        assert restored["extraction_method"] == "hybrid"
        assert restored["extraction_metadata"] == HYBRID_METADATA
        assert restored["original_filename"] == "restored.pdf"
    finally:
        connection.close()


def test_delete_profile_cascades_vault_rows(tmp_path):
    connection, repository = _repository(tmp_path)
    try:
        resume_import = repository.create_or_reuse_import(
            content_hash="hash-1",
            upload_token="upload-1",
            source_kind="text",
            original_filename="resume.txt",
            private_path="resumes/hash-1.txt",
            extracted_text="Synthetic resume text for tests",
            expires_at=EXPIRES,
            now=NOW,
        )
        repository.create_preview(
            resume_import_id=resume_import["id"],
            preview_token="preview-1",
            proposal=PROPOSAL,
            conflicts=[],
            expires_at=EXPIRES,
            now=NOW,
        )
        repository.confirm_sections(
            preview_token="preview-1",
            sections=["basic"],
            corrections={},
            now=NOW,
        )

        counts = repository.delete_all()
        connection.commit()

        assert counts["profiles"] == 1
        for table in (
            "candidate_profile",
            "candidate_facts",
            "profile_versions",
            "resume_previews",
            "resume_imports",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0] == 0
    finally:
        connection.close()


def test_profile_versions_and_original_follow_confirmed_import(tmp_path):
    connection, repository = _repository(tmp_path)
    try:
        resume_import = repository.create_or_reuse_import(
            content_hash="hash-profile",
            upload_token="private-upload-token",
            source_kind="text",
            original_filename="candidate-resume.txt",
            private_path="resumes/hash-profile.txt",
            extracted_text="Synthetic resume text for tests",
            expires_at=EXPIRES,
            now=NOW,
        )
        repository.create_preview(
            resume_import_id=resume_import["id"],
            preview_token="preview-profile",
            proposal=PROPOSAL,
            conflicts=[],
            expires_at=EXPIRES,
            now=NOW,
        )
        repository.confirm_sections(
            preview_token="preview-profile",
            sections=["basic"],
            corrections={},
            now=NOW,
        )
        connection.commit()

        versions = repository.list_profile_versions()
        original = repository.get_profile_original()

        assert versions == [
            {
                "version": 1,
                "confirmed_sections": ["basic"],
                "filename": "candidate-resume.txt",
                "source_kind": "text",
                "created_at": NOW,
            }
        ]
        assert original["filename"] == "candidate-resume.txt"
        assert original["source_kind"] == "text"
        assert original["private_path"] == "resumes/hash-profile.txt"
        assert "upload_token" not in original
    finally:
        connection.close()


def test_confirmed_imports_are_listed_as_independent_resume_documents(tmp_path):
    connection, repository = _repository(tmp_path)
    try:
        import_ids = []
        for index, filename in enumerate(
            ("通用简历.txt", "产品经理简历.txt"),
            start=1,
        ):
            resume_import = repository.create_or_reuse_import(
                content_hash=f"hash-{index}",
                upload_token=f"upload-{index}",
                source_kind="text",
                original_filename=filename,
                private_path=f"resumes/hash-{index}.txt",
                extracted_text=f"Synthetic resume {index}",
                expires_at=EXPIRES,
                now=f"2026-08-06T08:0{index}:00Z",
            )
            proposal = {
                **PROPOSAL,
                "basic": {
                    **PROPOSAL["basic"],
                    "summary": f"Resume {index}",
                },
            }
            repository.create_preview(
                resume_import_id=resume_import["id"],
                preview_token=f"preview-{index}",
                proposal=proposal,
                conflicts=[],
                expires_at=EXPIRES,
                now=f"2026-08-06T08:0{index}:00Z",
            )
            repository.confirm_sections(
                preview_token=f"preview-{index}",
                sections=["basic"],
                corrections={},
                now=f"2026-08-06T08:0{index}:00Z",
            )
            import_ids.append(resume_import["id"])
        connection.commit()

        documents = repository.list_resume_documents()
        selected = repository.get_resume_document(import_ids[0])
        versions = repository.list_resume_document_versions(import_ids[0])
        original = repository.get_resume_original(import_ids[0])
        updated = repository.update_resume_document_metadata(
            import_ids[0],
            display_name="AI 产品经理简历",
            target_roles=["AI 产品经理", "Agent 产品经理"],
            now="2026-08-06T09:00:00Z",
        )
        connection.commit()

        assert [item["filename"] for item in documents] == [
            "产品经理简历.txt",
            "通用简历.txt",
        ]
        assert documents[0]["display_name"] == "产品经理简历.txt"
        assert documents[0]["target_roles"] == []
        assert selected["sections"] == {
            "basic": {
                **PROPOSAL["basic"],
                "summary": "Resume 1",
            }
        }
        assert selected["confirmed_sections"] == ["basic"]
        assert [item["version"] for item in versions] == [1]
        assert original["filename"] == "通用简历.txt"
        assert "private_path" in original
        assert "upload_token" not in documents[0]
        assert updated["display_name"] == "AI 产品经理简历"
        assert updated["target_roles"] == [
            "AI 产品经理",
            "Agent 产品经理",
        ]
        assert repository.get_resume_document("missing") is None
    finally:
        connection.close()


def test_soft_delete_resume_removes_private_content_but_preserves_audit_rows(
    tmp_path,
):
    connection, repository = _repository(tmp_path)
    try:
        import_ids = []
        for index, sections in enumerate((["basic"], ["skill"]), start=1):
            resume_import = repository.create_or_reuse_import(
                content_hash=f"delete-hash-{index}",
                upload_token=f"delete-upload-{index}",
                source_kind="text",
                original_filename=f"简历-{index}.txt",
                private_path=f"resumes/delete-hash-{index}.txt",
                extracted_text=f"Synthetic resume {index}",
                expires_at=EXPIRES,
                now=f"2026-08-06T08:0{index}:00Z",
            )
            repository.create_preview(
                resume_import_id=resume_import["id"],
                preview_token=f"delete-preview-{index}",
                proposal=PROPOSAL,
                conflicts=[],
                expires_at=EXPIRES,
                now=f"2026-08-06T08:0{index}:00Z",
            )
            repository.confirm_sections(
                preview_token=f"delete-preview-{index}",
                sections=sections,
                corrections={},
                now=f"2026-08-06T08:0{index}:00Z",
            )
            import_ids.append(resume_import["id"])
        connection.commit()

        deleted = repository.soft_delete_resume_document(
            import_ids[0],
            now="2026-08-06T09:00:00Z",
        )
        connection.commit()

        deleted_import = connection.execute(
            """
            SELECT extracted_text, deleted_at
            FROM resume_imports
            WHERE id = ?
            """,
            (import_ids[0],),
        ).fetchone()
        assert deleted == {
            "resume_id": import_ids[0],
            "private_path": "resumes/delete-hash-1.txt",
        }
        assert deleted_import["extracted_text"] == ""
        assert deleted_import["deleted_at"] == "2026-08-06T09:00:00Z"
        assert connection.execute(
            "SELECT COUNT(*) FROM resume_previews WHERE resume_import_id = ?",
            (import_ids[0],),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM candidate_facts"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM profile_versions"
        ).fetchone()[0] == 2
        assert [item["id"] for item in repository.list_resume_documents()] == [
            import_ids[1]
        ]
        assert repository.get_resume_document(import_ids[0]) is None
        assert repository.get_resume_original(import_ids[0]) is None
        assert repository.soft_delete_resume_document("missing", now=NOW) is None
    finally:
        connection.close()
