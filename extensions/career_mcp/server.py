"""Career MCP stdio server for mock data and local manual JD records."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict

from .config import CareerConfig
from .crawler.adapters import (
    default_adapters,
    default_resumable_adapters,
)
from .database.migrations import schema_version
from .domain.manual_jd import utc_now_iso
from .services.crawler import CrawlerService
from .services.job_tracking import (
    JobTrackingService,
    JobTrackingServiceError,
)
from .services.interviews import (
    InterviewService,
    InterviewServiceError,
)
from .services.jobs import JobService
from .services.public_job_url import (
    PublicJobUrlError,
    PublicJobUrlService,
)
from .services.resumable_crawler import ResumableCrawlerService
from .services.resumes import ResumeService, ResumeServiceError

mcp = FastMCP("career")
_cloud_database = None


class EvaluationDimensionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal[
        "relevance",
        "specificity",
        "ownership",
        "outcome",
        "reasoning",
        "reflection",
        "clarity",
        "product_problem",
        "prioritization",
        "validation",
        "tradeoff",
        "technical_correctness",
        "boundary",
        "testing",
        "complexity",
        "architecture",
        "reliability",
        "scale",
        "evolution",
        "problem_formulation",
        "data",
        "evaluation",
        "baseline",
        "error_analysis",
        "deployment",
        "diagnosis",
    ] = None  # type: ignore[assignment]
    level: Literal[0, 1, 2, 3, 4]
    evidence: list[str]
    missing_evidence: str


class InterviewEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[2]
    question_type: Literal[
        "past_behavior",
        "product_case",
        "technical_knowledge",
        "coding",
        "system_design",
        "ai_ml_case",
        "failure_reflection",
    ]
    target_competency: str
    active_dimensions: list[EvaluationDimensionInput]
    primary_pain: str
    reason: str
    improvement: str
    fact_refs: list[str]
    recommended_action: Literal[
        "FOLLOW_UP",
        "VERIFY_CLAIM",
        "DEEP_DIVE",
        "SWITCH_TOPIC",
        "WRAP_UP",
    ]


class InterviewQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    topic: str
    refs: list[str]
    probe_target: str
    probe_dimension: str
    depth_level: int


_REQUIRED_DIMENSION_ORDER = {
    "past_behavior": (
        "relevance",
        "specificity",
        "ownership",
        "outcome",
    ),
    "product_case": (
        "relevance",
        "product_problem",
        "reasoning",
        "prioritization",
        "validation",
    ),
    "technical_knowledge": (
        "relevance",
        "technical_correctness",
        "clarity",
    ),
    "coding": (
        "relevance",
        "technical_correctness",
        "testing",
        "boundary",
    ),
    "system_design": (
        "relevance",
        "architecture",
        "tradeoff",
        "reliability",
    ),
    "ai_ml_case": (
        "relevance",
        "problem_formulation",
        "data",
        "evaluation",
    ),
    "failure_reflection": (
        "relevance",
        "ownership",
        "diagnosis",
        "reflection",
    ),
}


def _evaluation_payload(
    evaluation: InterviewEvaluationInput | dict,
) -> dict:
    payload = (
        evaluation.model_dump()
        if isinstance(evaluation, BaseModel)
        else dict(evaluation)
    )
    dimensions = payload.get("active_dimensions")
    required = _REQUIRED_DIMENSION_ORDER.get(
        str(payload.get("question_type")),
        (),
    )
    if (
        isinstance(dimensions, list)
        and len(dimensions) == len(required)
        and all(
            isinstance(item, dict) and item.get("name") is None
            for item in dimensions
        )
    ):
        for item, name in zip(dimensions, required):
            item["name"] = name
    return payload


def _crawler_service() -> CrawlerService:
    cloud = _cloud_storage()
    if cloud is None:
        return CrawlerService(adapters=default_adapters())
    database, _principal = cloud
    from extensions.career_mcp.database.postgres_catalog_repository import (
        PostgresCatalogRepository,
    )

    @contextmanager
    def repository_session():
        with database.shared_transaction() as connection:
            yield PostgresCatalogRepository(connection)

    return CrawlerService(
        adapters=default_adapters(),
        repository_session=repository_session,
    )


def _resumable_adapters() -> dict[str, object]:
    return {
        adapter.source_slug: adapter
        for adapter in default_resumable_adapters()
    }


def _resumable_crawler_service() -> ResumableCrawlerService:
    cloud = _cloud_storage()
    if cloud is None:
        return ResumableCrawlerService()
    database, _principal = cloud
    from extensions.career_mcp.database.postgres_catalog_repository import (
        PostgresCatalogRepository,
    )

    @contextmanager
    def repository_session():
        with database.shared_transaction() as connection:
            yield PostgresCatalogRepository(connection)

    return ResumableCrawlerService(
        repository_session=repository_session,
    )


def _resume_service():
    cloud = _cloud_storage()
    if cloud is None:
        return ResumeService()
    database, principal = cloud
    from coworker.storage.postgres.blob_repository import (
        PostgresBlobRepository,
    )
    from coworker.storage.postgres.resume_service import (
        PostgresResumeService,
    )

    return PostgresResumeService(
        database,
        principal,
        PostgresBlobRepository(database),
    )


def _job_service() -> JobService:
    cloud = _cloud_storage()
    if cloud is None:
        return JobService()
    database, principal = cloud
    from extensions.career_mcp.database.postgres_catalog_repository import (
        PostgresCatalogRepository,
    )

    @contextmanager
    def repository_session(*, write: bool = False):
        del write
        with database.transaction(principal) as connection:
            yield PostgresCatalogRepository(
                connection,
                principal_user_id=principal.user_id,
            )

    return JobService(
        repository_session=repository_session,
        tracking_service=_job_tracking_service(),
    )


def _job_tracking_service() -> JobTrackingService:
    cloud = _cloud_storage()
    if cloud is None:
        return JobTrackingService()
    database, principal = cloud
    from coworker.storage.postgres.job_tracking import (
        PostgresJobTrackingRepository,
    )

    @contextmanager
    def repository_session(*, write: bool = False):
        del write
        with database.transaction(principal) as connection:
            yield PostgresJobTrackingRepository(connection, principal)

    return JobTrackingService(
        repository_session=repository_session,
    )


def _interview_service() -> InterviewService:
    cloud = _cloud_storage()
    if cloud is None:
        return InterviewService()
    database, principal = cloud
    from coworker.storage.postgres.blob_repository import (
        PostgresBlobRepository,
    )
    from coworker.storage.postgres.career import PostgresResumeReader
    from extensions.career_mcp.database.postgres_catalog_repository import (
        PostgresCatalogRepository,
    )
    from coworker.storage.postgres.interviews import (
        PostgresInterviewRepository,
    )

    @contextmanager
    def repository_session(*, write: bool = False):
        del write
        with database.transaction(principal) as connection:
            yield PostgresInterviewRepository(connection, principal)

    def resume_loader(resume_id: str):
        with database.transaction(principal) as connection:
            return PostgresResumeReader(
                connection,
                principal,
            ).get_interview_input(resume_id)

    def job_loader(job_id: str):
        with database.transaction(principal) as connection:
            return PostgresCatalogRepository(
                connection,
                principal_user_id=principal.user_id,
            ).get_interview_input(job_id)

    return InterviewService(
        repository_session=repository_session,
        job_loader=job_loader,
        resume_loader=resume_loader,
        blob_repository=PostgresBlobRepository(database),
        principal=principal,
    )


def _cloud_storage():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    user_id = os.environ.get(
        "OPENCAR_PRINCIPAL_USER_ID",
        "",
    ).strip()
    if not user_id:
        raise RuntimeError(
            "OPENCAR_PRINCIPAL_USER_ID is required for cloud Career MCP"
        )
    global _cloud_database
    if _cloud_database is None:
        from coworker.storage.postgres.database import CloudDatabase

        _cloud_database = CloudDatabase.from_url(
            database_url,
            min_size=1,
            max_size=2,
        )
        _cloud_database.check()
    from coworker.server.identity import Principal

    return _cloud_database, Principal(user_id, "mcp-env")


def _ok(data: dict, warnings: list[str] | None = None) -> dict:
    return {
        "ok": True,
        "data": data,
        "warnings": warnings or [],
        "meta": {"generated_at": utc_now_iso()},
    }


def _error(code: str, message: str, *, retryable: bool = False) -> dict:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "retryable": retryable},
        "warnings": [],
        "meta": {"generated_at": utc_now_iso()},
    }


def health_check() -> dict:
    """Return the Career MCP process state without touching external services."""
    config = CareerConfig.from_env()
    version = 0
    if config.database_path.is_file():
        connection = sqlite3.connect(config.database_path)
        try:
            version = schema_version(connection)
        finally:
            connection.close()
    return _ok(
        {
            "service": "career-mcp",
            "version": "0.2.0",
            "mode": "stage2",
            "database": {"configured": config.database_path.is_file(), "schema_version": version},
        }
    )


def get_mock_jobs() -> dict:
    """Return deterministic jobs used only to verify the OpenWorker integration."""
    return _ok(
        {
            "jobs": [
                {
                    "id": "mock-ai-product-intern",
                    "company": "示例 AI 公司",
                    "title": "AI 产品经理实习生",
                    "location": "北京",
                    "recruitment_type": "internship",
                    "summary": "参与 AI 产品调研、需求分析与原型协作。",
                    "source_url": "https://careers.example.com/jobs/ai-product-intern",
                },
                {
                    "id": "mock-agent-fullstack-intern",
                    "company": "示例 Agent 公司",
                    "title": "Agent 全栈开发实习生",
                    "location": "上海",
                    "recruitment_type": "internship",
                    "summary": "参与 Agent 应用、工具调用和评估链路开发。",
                    "source_url": "https://careers.example.com/jobs/agent-fullstack-intern",
                },
            ]
        }
    )


def import_manual_jd(
    raw_text: str,
    source_url: str | None = None,
    company_name: str | None = None,
    title: str | None = None,
    preview_hash: str | None = None,
    confirmed: bool = False,
) -> dict:
    """Preview a manual JD, or persist it only after explicit confirmation."""
    try:
        result = _job_service().import_manual_jd(
            raw_text=raw_text,
            source_url=source_url,
            company_name=company_name,
            title=title,
            preview_hash=preview_hash,
            confirmed=confirmed,
        )
        return _ok(result)
    except ValueError as exc:
        return _error(
            str(getattr(exc, "code", "INVALID_INPUT")),
            str(exc),
        )
    except sqlite3.Error:
        return _error("PERSISTENCE_ERROR", "Career database operation failed.", retryable=True)


def preview_public_job_url(url: str) -> dict:
    """Read visible text from one public job URL under the SSRF guard."""
    try:
        return _ok(PublicJobUrlService().preview(url))
    except PublicJobUrlError as exc:
        return _error("PUBLIC_JOB_URL_UNAVAILABLE", str(exc))


def get_job(job_id: str) -> dict:
    """Return one persisted job with its source, versions and events."""
    try:
        return _ok(_job_service().get_job(job_id))
    except ValueError as exc:
        return _error("INVALID_INPUT", str(exc))
    except LookupError:
        return _error("JOB_NOT_FOUND", "No job found for the supplied id.")
    except sqlite3.Error:
        return _error("PERSISTENCE_ERROR", "Career database operation failed.", retryable=True)


def search_jobs(
    query: str | None = None,
    company_slugs: list[str] | None = None,
    locations: list[str] | None = None,
    recruitment_types: list[str] | None = None,
    statuses: list[str] | None = None,
    first_seen_after: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search local jobs with deterministic filters and offset pagination."""
    try:
        return _ok(
            _job_service().search_jobs(
                query=query,
                company_slugs=company_slugs,
                locations=locations,
                recruitment_types=recruitment_types,
                statuses=statuses,
                first_seen_after=first_seen_after,
                limit=limit,
                offset=offset,
            )
        )
    except ValueError as exc:
        return _error("INVALID_INPUT", str(exc))
    except sqlite3.Error:
        return _error("PERSISTENCE_ERROR", "Career database operation failed.", retryable=True)


def get_job_tracking(job_id: str) -> dict:
    """Return one job's user-owned favorite and application state."""
    try:
        return _ok(_job_tracking_service().get(job_id))
    except JobTrackingServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def list_tracked_jobs(
    favorite_only: bool = False,
    application_status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List jobs filtered by user-owned tracking state."""
    try:
        return _ok(
            _job_service().search_jobs(
                favorite_only=favorite_only,
                application_status=application_status,
                limit=limit,
                offset=offset,
            )
        )
    except ValueError as exc:
        return _error(
            str(getattr(exc, "code", "INVALID_INPUT")),
            str(exc),
        )
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def update_job_tracking(
    job_id: str,
    expected_version: int,
    is_favorite: bool | None = None,
    application_status: str | None = None,
    note: str | None = None,
) -> dict:
    """Update favorite or application state with optimistic locking."""
    patch: dict = {"expected_version": expected_version}
    if is_favorite is not None:
        patch["is_favorite"] = is_favorite
    if application_status is not None:
        patch["application_status"] = application_status
    if note is not None:
        patch["note"] = note
    try:
        return _ok(_job_tracking_service().update(job_id, patch))
    except JobTrackingServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def list_sources() -> dict:
    """List locally configured crawler sources without fetching any remote data."""
    try:
        data = _crawler_service().list_sources()
        sources = {
            source["slug"]: source
            for source in data["sources"]
        }
        for adapter in default_resumable_adapters():
            source = sources.setdefault(
                adapter.source_slug,
                {
                    "slug": adapter.source_slug,
                    "name": adapter.descriptor.source_name,
                    "missing_threshold": None,
                    "enabled": True,
                },
            )
            source["configured"] = True
        return _ok(
            {
                "sources": sorted(
                    sources.values(),
                    key=lambda source: source["slug"],
                )
            }
        )
    except sqlite3.Error:
        return _error("PERSISTENCE_ERROR", "Career database operation failed.", retryable=True)


def list_recent_job_events(limit: int = 20) -> dict:
    """List the most recent persisted manual or crawler job events."""
    try:
        return _ok(_crawler_service().list_recent_job_events(limit=limit))
    except ValueError as exc:
        return _error("INVALID_INPUT", str(exc))
    except sqlite3.Error:
        return _error("PERSISTENCE_ERROR", "Career database operation failed.", retryable=True)


def get_job_radar_digest(
    hours: int = 24,
    sample_limit: int = 20,
) -> dict:
    """Aggregate persisted job changes and source health without crawling."""
    try:
        return _ok(
            _crawler_service().get_job_radar_digest(
                hours=hours,
                sample_limit=sample_limit,
            )
        )
    except ValueError as exc:
        return _error("INVALID_INPUT", str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def get_resume_import_text(upload_token: str) -> dict:
    """Return locally extracted resume text for the current Career turn."""
    try:
        return _ok(_resume_service().get_resume_import_text(upload_token))
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def preview_resume_import(upload_token: str, proposal: dict) -> dict:
    """Validate a structured resume proposal without confirming facts."""
    try:
        return _ok(
            _resume_service().preview_resume_import(
                upload_token,
                proposal,
            )
        )
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def confirm_resume_sections(
    preview_token: str,
    sections: list[str],
    corrections: dict | None = None,
) -> dict:
    """Confirm selected resume sections into the local Career Vault."""
    try:
        return _ok(
            _resume_service().confirm_resume_sections(
                preview_token,
                sections,
                corrections=corrections,
            )
        )
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def get_candidate_profile(include_sensitive: bool = False) -> dict:
    """Return confirmed candidate facts, masked unless explicitly requested."""
    try:
        return _ok(
            _resume_service().get_candidate_profile(
                include_sensitive=include_sensitive,
            )
        )
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def list_confirmed_resumes() -> dict:
    """List safe resume summaries for interview selection."""
    try:
        resumes = [
            {
                key: document[key]
                for key in (
                    "id",
                    "display_name",
                    "target_roles",
                    "status",
                    "confirmed_sections",
                    "updated_at",
                )
            }
            for document in _resume_service().list_resume_documents()
        ]
        return _ok({"resumes": resumes})
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def get_confirmed_resume(resume_id: str) -> dict:
    """Return one confirmed resume with sensitive facts masked."""
    try:
        return _ok(
            _resume_service().get_resume_document(
                resume_id,
                include_sensitive=False,
            )
        )
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def _interview_error(exc: InterviewServiceError) -> dict:
    response = _error(exc.code, "模拟面试操作失败。")
    if exc.violations:
        response["error"]["violations"] = exc.violations
    return response


def create_interview_session(
    job_id: str,
    resume_id: str,
    difficulty: str = "standard",
    duration_minutes: int = 15,
) -> dict:
    """Create one interview from a visible job and confirmed resume."""
    try:
        return _ok(
            _interview_service().create(
                job_id,
                resume_id,
                conversation_id=None,
                difficulty=difficulty,
                duration_minutes=duration_minutes,
            )
        )
    except InterviewServiceError as exc:
        return _interview_error(exc)
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "模拟面试操作失败。",
            retryable=True,
        )


def get_interview_session(session_id: str) -> dict:
    """Read one interview and its ordered turns."""
    try:
        return _ok(_interview_service().get(session_id))
    except InterviewServiceError as exc:
        return _interview_error(exc)
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "模拟面试操作失败。",
            retryable=True,
        )


def start_mock_interview(
    session_id: str,
    expected_version: int,
    question: dict,
) -> dict:
    """Validate and persist the first interview question."""
    try:
        return _ok(
            _interview_service().start(
                session_id,
                expected_version=expected_version,
                question=question,
            )
        )
    except InterviewServiceError as exc:
        return _interview_error(exc)
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "模拟面试操作失败。",
            retryable=True,
        )


def submit_interview_answer(
    session_id: str,
    turn_id: str,
    expected_version: int,
    answer_text: str,
) -> dict:
    """Persist the candidate transcript for the current turn."""
    try:
        return _ok(
            _interview_service().submit_answer(
                session_id,
                turn_id,
                expected_version=expected_version,
                answer_text=answer_text,
            )
        )
    except InterviewServiceError as exc:
        return _interview_error(exc)
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "模拟面试操作失败。",
            retryable=True,
        )


def get_next_interview_question(
    session_id: str,
    turn_id: str,
    expected_version: int,
    evaluation: InterviewEvaluationInput,
    next_action: Literal[
        "FOLLOW_UP",
        "VERIFY_CLAIM",
        "DEEP_DIVE",
        "SWITCH_TOPIC",
        "WRAP_UP",
    ],
    next_reason: str,
    next_question: InterviewQuestionInput | None = None,
    user_requested: bool = False,
) -> dict:
    """Save hidden evaluation and atomically create one next question."""
    try:
        return _ok(
            _interview_service().evaluate_and_next(
                session_id,
                turn_id,
                expected_version=expected_version,
                evaluation=_evaluation_payload(evaluation),
                next_action=next_action,
                next_reason=next_reason,
                next_question=(
                    next_question.model_dump()
                    if isinstance(next_question, BaseModel)
                    else next_question
                ),
                user_requested=user_requested,
            )
        )
    except InterviewServiceError as exc:
        return _interview_error(exc)
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "模拟面试操作失败。",
            retryable=True,
        )


def finish_interview(
    session_id: str,
    expected_version: int,
    user_requested: bool = False,
) -> dict:
    """Finish a wrapped-up interview before report generation."""
    try:
        return _ok(
            _interview_service().finish(
                session_id,
                expected_version=expected_version,
                user_requested=user_requested,
            )
        )
    except InterviewServiceError as exc:
        return _interview_error(exc)
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "模拟面试操作失败。",
            retryable=True,
        )


def generate_interview_report(
    session_id: str,
    expected_version: int,
) -> dict:
    """Compile and publish the transcript, report, and session record."""
    try:
        return _ok(
            _interview_service().generate_report(
                session_id,
                expected_version=expected_version,
            )
        )
    except InterviewServiceError as exc:
        return _interview_error(exc)
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "模拟面试操作失败。",
            retryable=True,
        )


def discard_resume_import(preview_token: str) -> dict:
    """Discard an unconfirmed resume preview and private original."""
    try:
        return _ok(
            _resume_service().discard_resume_import(preview_token)
        )
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def delete_candidate_profile(confirm_text: str) -> dict:
    """Delete the complete local Career profile after exact confirmation."""
    try:
        return _ok(
            _resume_service().delete_candidate_profile(confirm_text)
        )
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


def crawl_source(source_slug: str, dry_run: bool = False) -> dict:
    """Run one explicitly registered source after OpenWorker approval."""
    try:
        resumable = _resumable_adapters()
        if source_slug in resumable:
            if dry_run:
                return _error(
                    "INVALID_INPUT",
                    "Resumable sources require dry_run=false; "
                    "staged pages do not update the Catalog.",
                )
            progress = _resumable_crawler_service().run_batch(
                resumable[source_slug]
            )
            if progress["status"] == "failed":
                return _error(
                    "CRAWL_FAILED",
                    progress.get("error_summary")
                    or "Crawler source failed.",
                    retryable=True,
                )
            return _ok(
                progress,
                warnings=(
                    [progress["error_summary"]]
                    if progress["status"] == "degraded"
                    and progress.get("error_summary")
                    else []
                ),
            )
        result = _crawler_service().crawl_registered_source(source_slug, dry_run=dry_run)
        if result.status == "failed":
            return _error(
                "CRAWL_FAILED",
                result.error_summary or "Crawler source failed.",
                retryable=True,
            )
        return _ok(
            {
                "source_slug": result.source_slug,
                "run_id": result.run_id,
                "status": result.status,
                "transitions": result.transitions,
            }
        )
    except ValueError as exc:
        return _error("INVALID_INPUT", str(exc))
    except LookupError:
        return _error("SOURCE_NOT_FOUND", "No enabled adapter is registered for this source.")
    except sqlite3.Error:
        return _error("PERSISTENCE_ERROR", "Career database operation failed.", retryable=True)


def crawl_all_sources(
    dry_run: bool = True,
    cursor: str | None = None,
) -> dict:
    """Run the next source in deterministic order and return a continuation cursor."""
    try:
        crawler = _crawler_service()
        resumable = _resumable_adapters()
        source_slugs = sorted(
            {
                *crawler.adapters.source_slugs(),
                *resumable,
            }
        )
        start = 0
        if cursor is not None:
            try:
                start = source_slugs.index(cursor) + 1
            except ValueError as exc:
                raise ValueError(
                    "cursor is not a registered source"
                ) from exc
        if start >= len(source_slugs):
            return _ok(
                {
                    "results": [],
                    "transitions": {},
                    "completed": 0,
                    "failed": 0,
                    "total_sources": len(source_slugs),
                    "has_more": False,
                    "next_cursor": None,
                }
            )

        source_slug = source_slugs[start]
        if source_slug in resumable:
            if dry_run:
                raise ValueError(
                    "resumable sources require dry_run=false"
                )
            progress = _resumable_crawler_service().run_batch(
                resumable[source_slug]
            )
            status = progress["status"]
            terminal = status in {
                "committed",
                "degraded",
                "failed",
            }
            results = [progress]
            transitions = progress.get("transitions", {})
            failed = int(status in {"degraded", "failed"})
            completed = int(status == "committed")
            has_more = not terminal or start + 1 < len(
                source_slugs
            )
            next_cursor = (
                source_slug
                if terminal and start + 1 < len(source_slugs)
                else cursor
                if not terminal
                else None
            )
            warnings = (
                [
                    f"{source_slug}: "
                    f"{progress.get('error_summary') or status}"
                ]
                if failed
                else []
            )
        else:
            result = crawler.crawl_registered_source(
                source_slug,
                dry_run=dry_run,
            )
            results = [
                {
                    "source_slug": result.source_slug,
                    "run_id": result.run_id,
                    "status": result.status,
                    "transitions": result.transitions,
                    "error_summary": result.error_summary,
                }
            ]
            transitions = result.transitions
            failed = int(result.status == "failed")
            completed = 1 - failed
            has_more = start + 1 < len(source_slugs)
            next_cursor = source_slug if has_more else None
            warnings = (
                [
                    f"{result.source_slug}: "
                    f"{result.error_summary or 'crawl failed'}"
                ]
                if failed
                else []
            )
        return _ok(
            {
                "results": results,
                "transitions": transitions,
                "completed": completed,
                "failed": failed,
                "total_sources": len(source_slugs),
                "has_more": has_more,
                "next_cursor": next_cursor,
            },
            warnings=warnings,
        )
    except ValueError as exc:
        return _error("INVALID_INPUT", str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )


mcp.tool()(health_check)
mcp.tool()(get_mock_jobs)
mcp.tool()(import_manual_jd)
mcp.tool(
    annotations={
        "title": "预览公开岗位链接",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)(preview_public_job_url)
mcp.tool()(get_job)
mcp.tool()(search_jobs)
mcp.tool()(get_job_tracking)
mcp.tool()(list_tracked_jobs)
mcp.tool()(update_job_tracking)
mcp.tool()(list_sources)
mcp.tool()(list_recent_job_events)
mcp.tool()(get_job_radar_digest)
mcp.tool()(get_resume_import_text)
mcp.tool()(preview_resume_import)
mcp.tool()(confirm_resume_sections)
mcp.tool()(get_candidate_profile)
mcp.tool(
    annotations={
        "title": "列出可用于面试的简历",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)(list_confirmed_resumes)
mcp.tool(
    annotations={
        "title": "读取已确认简历",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)(get_confirmed_resume)
mcp.tool(
    annotations={
        "title": "创建模拟面试",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)(create_interview_session)
mcp.tool(
    annotations={
        "title": "读取模拟面试",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)(get_interview_session)
mcp.tool(
    annotations={
        "title": "开始模拟面试",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)(start_mock_interview)
mcp.tool(
    annotations={
        "title": "提交面试回答",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)(submit_interview_answer)
mcp.tool(
    annotations={
        "title": "生成下一道面试问题",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)(get_next_interview_question)
mcp.tool(
    annotations={
        "title": "结束模拟面试",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)(finish_interview)
mcp.tool(
    annotations={
        "title": "生成面试复盘报告",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)(generate_interview_report)
mcp.tool()(discard_resume_import)
mcp.tool()(delete_candidate_profile)
mcp.tool()(crawl_source)
mcp.tool()(crawl_all_sources)


if __name__ == "__main__":
    mcp.run()
