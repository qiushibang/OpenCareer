"""Transactional application service for Career mock interviews."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..config import CareerConfig
from ..database.interview_repository import InterviewRepository
from ..database.migrations import connect
from ..database.repository import JobRepository
from ..database.resume_repository import ResumeRepository
from ..domain.interviews import (
    DIFFICULTIES,
    InterviewValidationError,
    blueprint_refs,
    build_blueprint,
    compile_interview_artifacts,
    question_budget,
    validate_evaluation,
    validate_question,
    validate_transition,
)
from ..domain.privacy import contains_sensitive_value

_MESSAGES = {
    "INVALID_INPUT": "模拟面试参数无效。",
    "JOB_NOT_FOUND": "岗位不存在，请返回岗位雷达重新选择。",
    "RESUME_NOT_FOUND": "简历不存在、未确认或已删除。",
    "INTERVIEW_NOT_FOUND": "未找到这场模拟面试。",
    "INTERVIEW_STATE_CONFLICT": "模拟面试当前状态不允许执行此操作。",
    "TURN_NOT_FOUND": "未找到当前面试问题。",
    "TURN_ALREADY_ANSWERED": "当前问题已经提交过回答。",
    "QUESTION_VALIDATION_FAILED": "面试问题未通过事实引用校验。",
    "EVALUATION_VALIDATION_FAILED": "面试评价未通过安全校验。",
    "VERSION_CONFLICT": "面试已在其他入口更新，请刷新后重试。",
    "REPORT_VALIDATION_FAILED": "面试报告未通过确定性校验。",
    "PERSISTENCE_ERROR": "模拟面试记录写入失败，请重试。",
}
_ARTIFACT_NAMES = {
    "transcript": "transcript.md",
    "report": "interview-report.md",
    "session": "session.json",
}


class InterviewServiceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        violations: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.violations = list(violations or [])


class InterviewService:
    def __init__(
        self,
        config: CareerConfig | None = None,
        *,
        workspace: Path | None = None,
        clock=None,
        repository_session: Callable[..., object] | None = None,
        job_loader: Callable[[str], dict | None] | None = None,
        resume_loader: Callable[[str], dict | None] | None = None,
        blob_repository=None,
        principal=None,
    ) -> None:
        self.config = config or CareerConfig.from_env()
        self.workspace = (workspace or Path.cwd()).resolve()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._injected_repository_session = repository_session
        self._job_loader = job_loader or self._load_local_job
        self._resume_loader = resume_loader or self._load_local_resume
        self._blob_repository = blob_repository
        self._principal = principal

    def create(
        self,
        job_id: str,
        resume_id: str,
        *,
        conversation_id: str | None,
        difficulty: str,
        duration_minutes: int,
        restart: bool = False,
    ) -> dict:
        normalized_job = self._identifier(job_id)
        normalized_resume = self._identifier(resume_id)
        normalized_conversation = self._optional_identifier(
            conversation_id
        )
        if difficulty not in DIFFICULTIES or not isinstance(restart, bool):
            self._raise("INVALID_INPUT")
        try:
            budget = question_budget(duration_minutes)
            job = self._job_loader(normalized_job)
            if job is None:
                self._raise("JOB_NOT_FOUND")
            resume = self._resume_loader(normalized_resume)
            if resume is None:
                self._raise("RESUME_NOT_FOUND")
            blueprint = build_blueprint(
                job,
                resume_id=normalized_resume,
                difficulty=difficulty,
                duration_minutes=duration_minutes,
                resume_sections=resume["sections"],
            )
        except InterviewValidationError as exc:
            self._raise(exc.code, cause=exc)

        company = job.get("company")
        now = self._iso(self._now())
        record = {
            "id": str(uuid4()),
            "job_id": normalized_job,
            "resume_id": normalized_resume,
            "conversation_id": normalized_conversation,
            "company": (
                company.get("name")
                if isinstance(company, dict)
                else None
            ),
            "position": str(job.get("title") or "未命名岗位"),
            "difficulty": difficulty,
            "duration_minutes": duration_minutes,
            "question_budget": budget,
            "blueprint": blueprint,
            "status": "ready",
            "phase": "idle",
            "started_at": None,
            "ended_at": None,
            "report_path": None,
            "transcript_path": None,
            "session_path": None,
            "report_sha256": None,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self._repository_session(write=True) as repository:
                active = repository.get_active_session(
                    normalized_job,
                    normalized_resume,
                )
                if active is not None and not restart:
                    return self._with_turns(repository, active)
                if active is not None:
                    if not repository.update_session_if_version(
                        active["id"],
                        active["version"],
                        status="cancelled",
                        phase="idle",
                        ended_at=now,
                        updated_at=now,
                    ):
                        self._raise("VERSION_CONFLICT")
                if (
                    normalized_conversation is not None
                    and repository.get_session_by_conversation_id(
                        normalized_conversation
                    )
                    is not None
                ):
                    self._raise("INTERVIEW_STATE_CONFLICT")
                created = repository.create_session(record)
                return {**created, "turns": []}
        except sqlite3.Error as exc:
            self._raise("PERSISTENCE_ERROR", cause=exc)

    def get(self, session_id: str) -> dict:
        normalized_id = self._identifier(session_id)
        with self._repository_session() as repository:
            session = repository.get_session(normalized_id)
            if session is None:
                self._raise("INTERVIEW_NOT_FOUND")
            return self._with_turns(repository, session)

    def get_by_conversation(
        self,
        conversation_id: str,
    ) -> dict | None:
        conversation = self._identifier(conversation_id)
        with self._repository_session() as repository:
            session = repository.get_session_by_conversation_id(
                conversation
            )
            return (
                self._with_turns(repository, session)
                if session is not None
                else None
            )

    def bind_conversation(
        self,
        session_id: str,
        *,
        expected_version: int,
        conversation_id: str,
    ) -> dict:
        normalized_id = self._identifier(session_id)
        version = self._version(expected_version)
        conversation = self._identifier(conversation_id)
        with self._repository_session(write=True) as repository:
            session = repository.get_session(normalized_id)
            if session is None:
                self._raise("INTERVIEW_NOT_FOUND")
            self._require_version(session, version)
            if session["conversation_id"] is not None:
                if session["conversation_id"] == conversation:
                    return self._with_turns(repository, session)
                self._raise("INTERVIEW_STATE_CONFLICT")
            if session["status"] not in {"ready", "in_progress"}:
                self._raise("INTERVIEW_STATE_CONFLICT")
            bound = repository.get_session_by_conversation_id(
                conversation
            )
            if bound is not None and bound["id"] != normalized_id:
                self._raise("INTERVIEW_STATE_CONFLICT")
            now = self._iso(self._now())
            if not repository.update_session_if_version(
                normalized_id,
                version,
                conversation_id=conversation,
                updated_at=now,
            ):
                self._raise("VERSION_CONFLICT")
            saved = repository.get_session(normalized_id)
            return self._with_turns(repository, saved)

    def start(
        self,
        session_id: str,
        *,
        expected_version: int,
        question: object,
    ) -> dict:
        normalized_id = self._identifier(session_id)
        version = self._version(expected_version)
        with self._repository_session(write=True) as repository:
            session = self._session_for_update(
                repository,
                normalized_id,
                version,
                status="ready",
                phase="idle",
            )
            try:
                validated = validate_question(
                    question,
                    blueprint=session["blueprint"],
                    turn_index=1,
                    previous_turns=[],
                )
            except InterviewValidationError as exc:
                self._raise(exc.code, cause=exc)
            now = self._iso(self._now())
            repository.insert_turn(
                {
                    "id": str(uuid4()),
                    "session_id": normalized_id,
                    "turn_index": 1,
                    "question_text": validated["question"],
                    "question_refs": validated["refs"],
                    "answer_text": None,
                    "evaluation": None,
                    "next_action": None,
                    "next_reason": None,
                    "question_topic": validated.get("topic"),
                    "probe_target": validated.get("probe_target"),
                    "probe_dimension": validated.get(
                        "probe_dimension"
                    ),
                    "depth_level": validated.get("depth_level"),
                    "started_at": now,
                    "answered_at": None,
                    "evaluated_at": None,
                }
            )
            if not repository.update_session_if_version(
                normalized_id,
                version,
                status="in_progress",
                phase="waiting_for_answer",
                started_at=now,
                updated_at=now,
            ):
                self._raise("VERSION_CONFLICT")
            saved = repository.get_session(normalized_id)
            return self._with_turns(repository, saved)

    def submit_answer(
        self,
        session_id: str,
        turn_id: str,
        *,
        expected_version: int,
        answer_text: str,
    ) -> dict:
        normalized_id = self._identifier(session_id)
        normalized_turn = self._identifier(turn_id)
        version = self._version(expected_version)
        answer = self._answer(answer_text)
        with self._repository_session(write=True) as repository:
            session = repository.get_session(normalized_id)
            if session is None:
                self._raise("INTERVIEW_NOT_FOUND")
            self._require_version(session, version)
            current = repository.current_turn(normalized_id)
            if current is None or current["id"] != normalized_turn:
                self._raise("TURN_NOT_FOUND")
            if current["answer_text"] is not None:
                self._raise("TURN_ALREADY_ANSWERED")
            if (
                session["status"] != "in_progress"
                or session["phase"] != "waiting_for_answer"
            ):
                self._raise("INTERVIEW_STATE_CONFLICT")
            now = self._iso(self._now())
            if not repository.answer_turn(
                normalized_turn,
                answer_text=answer,
                answered_at=now,
            ):
                self._raise("TURN_ALREADY_ANSWERED")
            if not repository.update_session_if_version(
                normalized_id,
                version,
                phase="evaluating",
                updated_at=now,
            ):
                self._raise("VERSION_CONFLICT")
            saved = repository.get_session(normalized_id)
            return self._with_turns(repository, saved)

    def evaluate_and_next(
        self,
        session_id: str,
        turn_id: str,
        *,
        expected_version: int,
        evaluation: object,
        next_action: str,
        next_reason: str,
        next_question: object | None,
        user_requested: bool = False,
    ) -> dict:
        normalized_id = self._identifier(session_id)
        normalized_turn = self._identifier(turn_id)
        version = self._version(expected_version)
        reason = self._bounded_text(next_reason, 1, 240)
        with self._repository_session(write=True) as repository:
            session = self._session_for_update(
                repository,
                normalized_id,
                version,
                status="in_progress",
                phase="evaluating",
            )
            turns = repository.list_turns(normalized_id)
            if not turns or turns[-1]["id"] != normalized_turn:
                self._raise("TURN_NOT_FOUND")
            current = turns[-1]
            if current["answer_text"] is None:
                self._raise("INTERVIEW_STATE_CONFLICT")
            if current["evaluation"] is not None:
                self._raise("INTERVIEW_STATE_CONFLICT")
            current_target = next(
                (
                    target
                    for target in session["blueprint"].get(
                        "probe_plan",
                        [],
                    )
                    if target.get("target_id")
                    == current.get("probe_target")
                ),
                {},
            )
            target_max_depth = int(
                current_target.get("max_depth") or 0
            )
            at_target_max_depth = (
                target_max_depth > 0
                and int(current.get("depth_level") or 0)
                >= target_max_depth
            )
            allowed_refs = blueprint_refs(session["blueprint"])
            try:
                validated_evaluation = validate_evaluation(
                    evaluation,
                    allowed_refs=allowed_refs,
                    expected_target=current["probe_dimension"],
                    answer_text=current["answer_text"],
                )
                if (
                    validated_evaluation["recommended_action"]
                    != next_action
                    or (
                        validated_evaluation["question_score"] < 60
                        and next_action == "SWITCH_TOPIC"
                        and not at_target_max_depth
                    )
                ):
                    self._raise("EVALUATION_VALIDATION_FAILED")
                _, transition_phase = validate_transition(
                    status=session["status"],
                    phase=session["phase"],
                    event=next_action,
                    answered_turns=len(turns),
                    question_budget=session["question_budget"],
                    user_requested=user_requested,
                )
            except InterviewValidationError as exc:
                self._raise(exc.code, cause=exc)

            validated_question: dict | None = None
            if next_action == "WRAP_UP":
                if next_question is not None:
                    self._raise("QUESTION_VALIDATION_FAILED")
            else:
                if next_question is None:
                    self._raise("QUESTION_VALIDATION_FAILED")
                try:
                    validated_question = validate_question(
                        next_question,
                        blueprint=session["blueprint"],
                        turn_index=len(turns) + 1,
                        previous_turns=turns,
                        next_action=next_action,
                    )
                except InterviewValidationError as exc:
                    self._raise(exc.code, cause=exc)

            now = self._iso(self._now())
            if not repository.evaluate_turn(
                normalized_turn,
                evaluation=validated_evaluation,
                next_action=next_action,
                next_reason=reason,
                evaluated_at=now,
            ):
                self._raise("INTERVIEW_STATE_CONFLICT")
            if validated_question is not None:
                repository.insert_turn(
                    {
                        "id": str(uuid4()),
                        "session_id": normalized_id,
                        "turn_index": len(turns) + 1,
                        "question_text": validated_question["question"],
                        "question_refs": validated_question["refs"],
                        "answer_text": None,
                        "evaluation": None,
                        "next_action": None,
                        "next_reason": None,
                        "question_topic": validated_question.get(
                            "topic"
                        ),
                        "probe_target": validated_question.get(
                            "probe_target"
                        ),
                        "probe_dimension": validated_question.get(
                            "probe_dimension"
                        ),
                        "depth_level": validated_question.get(
                            "depth_level"
                        ),
                        "started_at": now,
                        "answered_at": None,
                        "evaluated_at": None,
                    }
                )
                transition_phase = "waiting_for_answer"
            if not repository.update_session_if_version(
                normalized_id,
                version,
                phase=transition_phase,
                updated_at=now,
            ):
                self._raise("VERSION_CONFLICT")
            saved = repository.get_session(normalized_id)
            return self._with_turns(repository, saved)

    def finish(
        self,
        session_id: str,
        *,
        expected_version: int,
        user_requested: bool,
    ) -> dict:
        normalized_id = self._identifier(session_id)
        version = self._version(expected_version)
        with self._repository_session(write=True) as repository:
            session = repository.get_session(normalized_id)
            if session is None:
                self._raise("INTERVIEW_NOT_FOUND")
            self._require_version(session, version)
            if session["status"] != "in_progress":
                self._raise("INTERVIEW_STATE_CONFLICT")
            turns = repository.list_turns(normalized_id)
            if (
                user_requested
                and session["phase"] == "waiting_for_answer"
            ):
                completed = turns[:-1]
                current = turns[-1] if turns else None
                if (
                    current is None
                    or current["answer_text"] is not None
                    or not completed
                    or any(
                        turn["answer_text"] is None
                        or turn["evaluation"] is None
                        for turn in completed
                    )
                    or not repository.delete_unanswered_turn(
                        current["id"]
                    )
                ):
                    self._raise("INTERVIEW_STATE_CONFLICT")
                turns = completed
            elif session["phase"] != "generating_report":
                self._raise("INTERVIEW_STATE_CONFLICT")
            if (
                not turns
                or any(turn["evaluation"] is None for turn in turns)
                or (len(turns) < 5 and not user_requested)
            ):
                self._raise("INTERVIEW_STATE_CONFLICT")
            now = self._iso(self._now())
            if not repository.update_session_if_version(
                normalized_id,
                version,
                phase="generating_report",
                ended_at=now,
                updated_at=now,
            ):
                self._raise("VERSION_CONFLICT")
            saved = repository.get_session(normalized_id)
            return self._with_turns(repository, saved)

    def generate_report(
        self,
        session_id: str,
        *,
        expected_version: int,
    ) -> dict:
        normalized_id = self._identifier(session_id)
        version = self._version(expected_version)
        staging: Path | None = None
        published: Path | None = None
        blob_ids: list[str] = []
        try:
            with self._repository_session(write=True) as repository:
                session = self._session_for_update(
                    repository,
                    normalized_id,
                    version,
                    status="in_progress",
                    phase="generating_report",
                )
                turns = repository.list_turns(normalized_id)
                if not turns or any(
                    turn["evaluation"] is None for turn in turns
                ):
                    self._raise("INTERVIEW_STATE_CONFLICT")
                generated_at = self._iso(self._now())
                try:
                    artifacts = compile_interview_artifacts(
                        session,
                        turns,
                        generated_at=generated_at,
                    )
                except InterviewValidationError as exc:
                    self._raise(exc.code, cause=exc)

                paths: dict[str, str]
                if self._blob_repository is not None:
                    if self._principal is None:
                        self._raise("PERSISTENCE_ERROR")
                    paths = {}
                    for filename, content in artifacts.items():
                        metadata = self._blob_repository.put(
                            self._principal,
                            content=content.encode("utf-8"),
                            kind="interview_artifact",
                            media_type=(
                                "application/json"
                                if filename.endswith(".json")
                                else "text/markdown; charset=utf-8"
                            ),
                            original_name=filename,
                        )
                        blob_ids.append(metadata.id)
                        paths[filename] = f"blob:{metadata.id}"
                else:
                    parent, target = self._artifact_target(normalized_id)
                    parent.mkdir(parents=True, exist_ok=True)
                    staging = Path(
                        tempfile.mkdtemp(
                            prefix=f".{normalized_id}-",
                            dir=parent,
                        )
                    )
                    for filename, content in artifacts.items():
                        path = staging / filename
                        path.write_text(content, encoding="utf-8")
                        os.chmod(path, 0o600)
                        with path.open("rb") as file:
                            os.fsync(file.fileno())
                    self._fsync_directory(staging)
                    if target.exists() or target.is_symlink():
                        self._raise("PERSISTENCE_ERROR")
                    os.replace(staging, target)
                    published = target
                    staging = None
                    self._fsync_directory(parent)
                    relative = (
                        Path("artifacts")
                        / "interviews"
                        / normalized_id
                    )
                    paths = {
                        filename: (relative / filename).as_posix()
                        for filename in artifacts
                    }

                report_sha256 = hashlib.sha256(
                    artifacts["interview-report.md"].encode("utf-8")
                ).hexdigest()
                if not repository.update_session_if_version(
                    normalized_id,
                    version,
                    status="completed",
                    phase="idle",
                    report_path=paths["interview-report.md"],
                    transcript_path=paths["transcript.md"],
                    session_path=paths["session.json"],
                    report_sha256=report_sha256,
                    updated_at=generated_at,
                ):
                    self._raise("VERSION_CONFLICT")
                saved = repository.get_session(normalized_id)
                return self._with_turns(repository, saved)
        except InterviewServiceError:
            if published is not None:
                shutil.rmtree(published, ignore_errors=True)
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            self._delete_blobs(blob_ids)
            raise
        except (OSError, sqlite3.Error) as exc:
            if published is not None:
                shutil.rmtree(published, ignore_errors=True)
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            self._delete_blobs(blob_ids)
            self._raise("PERSISTENCE_ERROR", cause=exc)
        except Exception:
            if published is not None:
                shutil.rmtree(published, ignore_errors=True)
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            self._delete_blobs(blob_ids)
            raise

    def read_artifact(self, session_id: str, kind: str) -> dict:
        normalized_id = self._identifier(session_id)
        if kind not in _ARTIFACT_NAMES:
            self._raise("INVALID_INPUT")
        session = self.get(normalized_id)
        if session["status"] != "completed":
            self._raise("INTERVIEW_STATE_CONFLICT")
        path_field = {
            "report": "report_path",
            "transcript": "transcript_path",
            "session": "session_path",
        }[kind]
        stored_path = session.get(path_field)
        if isinstance(stored_path, str) and stored_path.startswith(
            "blob:"
        ):
            if self._blob_repository is None or self._principal is None:
                self._raise("PERSISTENCE_ERROR")
            blob_id = stored_path.removeprefix("blob:")
            try:
                content = b"".join(
                    self._blob_repository.iter_content(
                        self._principal,
                        blob_id,
                    )
                )
            except (KeyError, ValueError) as exc:
                self._raise("PERSISTENCE_ERROR", cause=exc)
            return {
                "bytes": content,
                "filename": _ARTIFACT_NAMES[kind],
                "media_type": (
                    "application/json"
                    if kind == "session"
                    else "text/markdown; charset=utf-8"
                ),
            }
        relative = (
            Path("artifacts")
            / "interviews"
            / normalized_id
            / _ARTIFACT_NAMES[kind]
        )
        target = self.workspace / relative
        expected_parent = (
            self.workspace / "artifacts" / "interviews" / normalized_id
        )
        if (
            target.is_symlink()
            or expected_parent.is_symlink()
            or not target.resolve().is_relative_to(self.workspace)
            or not target.is_file()
        ):
            self._raise("PERSISTENCE_ERROR")
        return {
            "bytes": target.read_bytes(),
            "filename": target.name,
            "media_type": (
                "application/json"
                if kind == "session"
                else "text/markdown; charset=utf-8"
            ),
        }

    def _delete_blobs(self, blob_ids: list[str]) -> None:
        if self._blob_repository is None or self._principal is None:
            return
        for blob_id in blob_ids:
            try:
                self._blob_repository.delete(self._principal, blob_id)
            except Exception:
                pass

    @staticmethod
    def _with_turns(
        repository: InterviewRepository,
        session: dict | None,
    ) -> dict:
        if session is None:
            raise RuntimeError("interview session was not persisted")
        return {
            **session,
            "turns": repository.list_turns(session["id"]),
        }

    def _session_for_update(
        self,
        repository: InterviewRepository,
        session_id: str,
        expected_version: int,
        *,
        status: str,
        phase: str,
    ) -> dict:
        session = repository.get_session(session_id)
        if session is None:
            self._raise("INTERVIEW_NOT_FOUND")
        self._require_version(session, expected_version)
        if session["status"] != status or session["phase"] != phase:
            self._raise("INTERVIEW_STATE_CONFLICT")
        return session

    def _artifact_target(self, session_id: str) -> tuple[Path, Path]:
        artifacts = self.workspace / "artifacts"
        parent = artifacts / "interviews"
        target = parent / session_id
        if (
            artifacts.is_symlink()
            or parent.is_symlink()
            or target.is_symlink()
            or not parent.resolve().is_relative_to(self.workspace)
        ):
            self._raise("PERSISTENCE_ERROR")
        return parent, target

    @contextmanager
    def _repository_session(
        self,
        *,
        write: bool = False,
    ) -> Iterator[object]:
        if self._injected_repository_session is not None:
            with self._injected_repository_session(
                write=write
            ) as repository:
                yield repository
            return
        connection = connect(self.config.database_path)
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield InterviewRepository(connection)
            if write:
                connection.commit()
        except Exception:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _load_local_job(self, job_id: str) -> dict | None:
        connection = connect(self.config.database_path)
        try:
            return JobRepository(connection).get_interview_input(job_id)
        finally:
            connection.close()

    def _load_local_resume(self, resume_id: str) -> dict | None:
        connection = connect(self.config.database_path)
        try:
            return ResumeRepository(connection).get_interview_input(
                resume_id
            )
        finally:
            connection.close()

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _identifier(value: object) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value.strip()) > 200
        ):
            InterviewService._raise("INVALID_INPUT")
        return value.strip()

    @staticmethod
    def _optional_identifier(value: object) -> str | None:
        if value is None:
            return None
        return InterviewService._identifier(value)

    @staticmethod
    def _version(value: object) -> int:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
        ):
            InterviewService._raise("INVALID_INPUT")
        return value

    @staticmethod
    def _answer(value: object) -> str:
        answer = InterviewService._bounded_text(value, 1, 20_000)
        if contains_sensitive_value(answer):
            InterviewService._raise("INVALID_INPUT")
        return answer

    @staticmethod
    def _bounded_text(
        value: object,
        minimum: int,
        maximum: int,
    ) -> str:
        if not isinstance(value, str):
            InterviewService._raise("INVALID_INPUT")
        text = " ".join(value.split())
        if not minimum <= len(text) <= maximum:
            InterviewService._raise("INVALID_INPUT")
        return text

    @staticmethod
    def _require_version(session: dict, expected_version: int) -> None:
        if session["version"] != expected_version:
            InterviewService._raise("VERSION_CONFLICT")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("clock must be a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.isoformat(timespec="seconds").replace(
            "+00:00",
            "Z",
        )

    @staticmethod
    def _raise(code: str, *, cause: Exception | None = None):
        violations = (
            [{"code": code, "message": str(cause)}]
            if isinstance(cause, InterviewValidationError)
            else None
        )
        error = InterviewServiceError(
            code,
            _MESSAGES.get(code, _MESSAGES["PERSISTENCE_ERROR"]),
            violations=violations,
        )
        if cause is not None:
            raise error from cause
        raise error
