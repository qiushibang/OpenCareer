"""Narrow policy helpers for the disposable public Career alpha environment.

This mode is deliberately opt-in.  It is not an authentication system: it limits
the local OpenWorker surface before a temporary tunnel is opened for a small,
trusted test group.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable


ALPHA_ENV = "OPENCAR_ALPHA_TEST"
ALPHA_WORKSPACE_ENV = "OPENCAR_ALPHA_WORKSPACE"
# Set by the container image (deploy/Dockerfile): this process has no desktop session, so
# Finder/Explorer/xdg-open and native dialogs must fail with a message instead of shelling
# out. Kept separate from ALPHA_ENV on purpose — alpha is a *capability policy* (it can also
# be exercised on the author's Mac, where revealing files still works), while this flag is a
# *fact about the host*.
HEADLESS_ENV = "OPENCAR_HEADLESS"

DESKTOP_ONLY_ERROR = (
    "Desktop-only feature: this OpenCareer server runs headless (no file manager or "
    "native dialogs). Use the desktop app for this action."
)

_CONVERSATION_TOOLS = frozenset(
    {
        "load_skill",
        "mcp__career__health_check",
        "mcp__career__import_manual_jd",
        "mcp__career__get_job",
        "mcp__career__search_jobs",
        "mcp__career__get_job_catalog_schema",
        "mcp__career__search_job_catalog",
        "mcp__career__get_job_catalog_status",
        "mcp__career__list_job_subscriptions",
        "mcp__career__draft_job_subscription",
        "mcp__career__get_job_tracking",
        "mcp__career__list_tracked_jobs",
        "mcp__career__update_job_tracking",
        "mcp__career__list_sources",
        "mcp__career__list_recent_job_events",
        "mcp__career__get_job_radar_digest",
        "mcp__career__get_resume_import_text",
        "mcp__career__preview_resume_import",
        "mcp__career__confirm_resume_sections",
        "mcp__career__get_candidate_profile",
        "mcp__career__list_confirmed_resumes",
        "mcp__career__get_confirmed_resume",
        "mcp__career__create_interview_session",
        "mcp__career__get_interview_session",
        "mcp__career__start_mock_interview",
        "mcp__career__submit_interview_answer",
        "mcp__career__get_next_interview_question",
        "mcp__career__finish_interview",
        "mcp__career__generate_interview_report",
    }
)

# Tools the cloud surface runs WITHOUT an approval card. Read-only Career MCP
# tools plus the interview flow (state lives inside the interview session, not
# the Career Vault). Deliberately excluded: import_manual_jd,
# confirm_resume_sections, update_job_tracking — they write the job store /
# Career Vault / tracking, so the model may only call them after the user
# approves the card. Explicit enumeration (not "conversation minus writes") so
# a future addition to the surface never silently becomes auto-approved.
AUTO_APPROVE_TOOLS = frozenset(
    {
        "load_skill",
        "mcp__career__get_job_catalog_schema",
        "mcp__career__search_job_catalog",
        "mcp__career__get_job_catalog_status",
        "mcp__career__list_job_subscriptions",
        "mcp__career__draft_job_subscription",
        "mcp__career__health_check",
        "mcp__career__get_job",
        "mcp__career__search_jobs",
        "mcp__career__get_job_tracking",
        "mcp__career__list_tracked_jobs",
        "mcp__career__list_sources",
        "mcp__career__list_recent_job_events",
        "mcp__career__get_job_radar_digest",
        "mcp__career__get_resume_import_text",
        "mcp__career__preview_resume_import",
        "mcp__career__get_candidate_profile",
        "mcp__career__list_confirmed_resumes",
        "mcp__career__get_confirmed_resume",
        "mcp__career__create_interview_session",
        "mcp__career__get_interview_session",
        "mcp__career__start_mock_interview",
        "mcp__career__submit_interview_answer",
        "mcp__career__get_next_interview_question",
        "mcp__career__finish_interview",
        "mcp__career__generate_interview_report",
    }
)


def enabled() -> bool:
    """Return whether this server was explicitly launched as the public alpha."""
    return os.environ.get(ALPHA_ENV) == "1"


def headless() -> bool:
    """Return whether this process runs without a desktop session (container/server mode)."""
    return os.environ.get(HEADLESS_ENV) == "1"


def workspace() -> str:
    """Return the launcher-provided, dedicated alpha workspace."""
    return os.environ.get(ALPHA_WORKSPACE_ENV, "").strip()


def blocks_http(method: str, path: str) -> bool:
    """Default-deny cloud routes, including newly added desktop controls."""
    if not enabled():
        return False
    return not any(
        (method.upper() == allowed_method or method.upper() == "OPTIONS")
        and re.fullmatch(pattern + "/?", path)
        for allowed_method, pattern in _PUBLIC_HTTP_ROUTES
    )


_PUBLIC_HTTP_ROUTES = (
    ("POST", r"/v1/support/diagnostics"),
    ("POST", r"/v1/support/feedback"),
    ("POST", r"/v1/support/anonymous-feedback"),
    ("GET", r"/v1/support/capabilities"),
    ("GET", r"/v1/support/admin/feedback"),
    ("PATCH", r"/v1/support/admin/feedback/[0-9a-f]{32}"),
    ("GET", r"/v1/support/admin/feedback/[0-9a-f]{32}"),
    ("POST", r"/v1/support/admin/feedback/[0-9a-f]{32}/merge"),
    ("GET", r"/v1/support/admin/audit"),
    ("GET", r"/v1/support/admin/alerts"),
    ("GET", r"/v1/support/feedback"),
    ("GET", r"/v1/support/feedback/[0-9a-f]{32}"),
    ("GET", r"/v1/support/diagnostics/[0-9a-f]{32}"),
    ("GET", r"/v1/(health|auth/session|agents|personas|skills|providers|sessions|inbox)"),
    ("GET", r"/auth/(login|callback)"), ("POST", r"/auth/logout"),
    ("POST", r"/v1/providers(/verify)?"),
    ("DELETE", r"/v1/providers/[A-Za-z0-9_-]+"),
    ("POST", r"/v1/settings/default-model"),
    ("POST", r"/v1/inbox/[A-Za-z0-9_-]+/resolve"),
    ("GET", r"/v1/sessions/[A-Za-z0-9_-]+/(messages|skills|connections|unattended)"),
    ("POST", r"/v1/sessions/[A-Za-z0-9_-]+/skills"),
    ("PATCH", r"/v1/sessions/[A-Za-z0-9_-]+"),
    ("DELETE", r"/v1/sessions/[A-Za-z0-9_-]+"),
    ("POST", r"/v1/career/resumes/stage"),
    ("GET", r"/v1/career/(profile|resumes|interviews|jobs|jobs/filters)"),
    ("GET", r"/v1/career/jobs/sync"),
    ("GET", r"/v1/career/catalog/(schema|status)"),
    ("GET", r"/v1/career/catalog/results/[a-f0-9]+"),
    ("POST", r"/v1/career/catalog/search"),
    ("GET", r"/v1/career/job-subscriptions(/channels|/[a-f0-9]+/runs)?"),
    ("POST", r"/v1/career/job-subscriptions(/channels|/[a-f0-9]+/(activate|pause|preview))?"),
    ("DELETE", r"/v1/career/job-subscriptions/channels/[a-f0-9]+"),
    ("POST", r"/v1/career/job-subscriptions/channels/[a-f0-9]+/test"),
    ("POST", r"/v1/career/job-subscriptions/runs/[a-f0-9]+/retry"),
    ("POST", r"/v1/career/jobs/sync"),
    ("GET", r"/v1/career/profile/(versions|original(/(content|download))?)"),
    ("DELETE", r"/v1/career/profile"),
    ("GET", r"/v1/career/resumes/[A-Za-z0-9_-]+(/(versions|original(/(content|download))?))?"),
    ("PATCH", r"/v1/career/resumes/[A-Za-z0-9_-]+"),
    ("DELETE", r"/v1/career/resumes/[A-Za-z0-9_-]+"),
    ("POST", r"/v1/career/interviews"),
    ("POST", r"/v1/career/interviews/voice/(transcribe|synthesize)"),
    ("GET", r"/v1/career/interviews/[A-Za-z0-9_-]+(/artifacts/(report|transcript|session))?"),
    ("POST", r"/v1/career/interviews/[A-Za-z0-9_-]+/(conversation|start|answers|next|finish|report)"),
    ("GET", r"/v1/career/jobs/[A-Za-z0-9_-]+(/tracking)?"),
    ("PATCH", r"/v1/career/jobs/[A-Za-z0-9_-]+/tracking"),
)


def public_agents(agents: Iterable[dict]) -> list[dict]:
    """Expose only the Career persona while alpha mode is active."""
    if not enabled():
        return list(agents)
    return [agent for agent in agents if agent.get("name") == "career"]


def permits_agent(agent: str) -> bool:
    return not enabled() or agent == "career"


def conversation_tools() -> set[str]:
    """Explicit product-tool allowlist for public alpha Career conversations."""
    return set(_CONVERSATION_TOOLS)
