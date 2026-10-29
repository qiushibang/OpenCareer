"""FastAPI app — OpenAI-compatible endpoint + WS session API + REST.

The control plane every surface (GUI/IDE/messaging) rides on. The WS carries the engine
event stream and the approval channel; `/v1/chat/completions` is the OpenAI-compatible
proxy so any OpenAI-format client can use the runtime as a backend.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import sqlite3
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, Optional, Literal
from urllib.parse import quote

from fastapi import Body, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict

from . import alpha
from .auth import AuthModule, SESSION_COOKIE
from .identity import (
    Principal,
    authentication_required,
    resolve_principal,
)
from .origins import OriginRepository, build_origin_policy

logger = logging.getLogger("coworker.server")


class BrowserDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["page_crash", "network_error", "socket_error"]
    page: Literal["jobs", "profile", "interview", "conversation", "models", "auth", "support", "unknown"] = "unknown"

class _CodedRequestError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _coded_error(code: str) -> _CodedRequestError:
    return _CodedRequestError(code)


def career_interview_voice_service():
    from extensions.career_mcp.services.interview_voice import (
        InterviewVoiceService,
    )

    return InterviewVoiceService()


EXTRA_ORIGINS_ENV = "OPENCAR_EXTRA_ORIGINS"


def _content_disposition(disposition: str, filename: str) -> str:
    clean = Path(filename.replace("\\", "/")).name
    clean = clean.replace('"', "").replace("\r", "").replace("\n", "")
    if clean.isascii():
        return f'{disposition}; filename="{clean or "resume"}"'
    suffix = Path(clean).suffix
    fallback = f"resume{suffix}" if suffix.isascii() else "resume"
    return (
        f'{disposition}; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(clean, safe='')}"
    )


# Caps on inbound WebSocket traffic. The loopback socket is unauthenticated (any local
# process can reach it), so bound frames, messages, and per-connection request rate before
# building model content or starting a turn.
_WS_MAX_FRAME_BYTES = 16 * 1024 * 1024
_WS_RATE_LIMIT_COUNT = 30
_WS_RATE_LIMIT_WINDOW_SECONDS = 10.0
_RUNTIME_PRESENCE_TTL_SECONDS = 60
_RUNTIME_TURN_LEASE_TTL_SECONDS = 300
_MAX_MESSAGE_TEXT_CHARS = 200_000
_MAX_ATTACHMENTS_BYTES = 15_000_000  # leaves JSON overhead below the 16 MiB frame cap


def _acquire_turn_lease(
    coordinator,
    *,
    key: str,
    user_id: str,
    owner: str,
    ttl_seconds: int,
) -> bool:
    if coordinator.acquire_lease(key, owner, ttl_seconds):
        return True
    previous_owner = coordinator.lease_owner(key)
    if (
        previous_owner is None
        or previous_owner in coordinator.presence(user_id)
    ):
        return False
    return coordinator.replace_lease(
        key,
        previous_owner,
        owner,
        ttl_seconds,
    )


def _json_value_size(value: Any) -> int:
    """Conservative UTF-8 size of parsed JSON without allocating another giant string."""
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, dict):
        return sum(_json_value_size(k) + _json_value_size(v) for k, v in value.items())
    if isinstance(value, list):
        return sum(_json_value_size(v) for v in value)
    return 8  # numbers, booleans, null, separators


# Brand colors for the connector badge riding the ✓ (UX-DECISIONS §30). The GUI owns the
# real logos; this page must render offline with zero assets, so a colored initial stands in.
_BRAND_COLORS = {
    "slack": "#4A154B",
    "github": "#24292f",
    "hubspot": "#ff7a59",
    "gmail": "#ea4335",
    "google_calendar": "#4285f4",
}


def _browser_page(
    title: str, detail: str, *, ok: bool = True, error: str = "", connector: str = ""
) -> str:
    """The page shown in the user's browser at the end of a loopback flow (sign-in or
    connector callback) — one branded card (UX-DECISIONS §30): OCW mark, ok/fail icon
    (the connector's initial rides the ✓), the friendly detail, and the raw error
    preserved on failures (it's the debugging breadcrumb). Inline CSS, light/dark via
    prefers-color-scheme, no external assets — it must render offline."""
    import html as _html

    badge = ""
    if ok and connector:
        color = _BRAND_COLORS.get(connector, "#3670b2")
        initial = _html.escape((connector[:1] or "?").upper())
        badge = f'<span class="mini" style="background:{color}">{initial}</span>'
    icon = (
        f'<div class="ico ok">✓{badge}</div>' if ok else '<div class="ico bad">✕</div>'
    )
    err = f'<div class="err">{_html.escape(error)}</div>' if error else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_html.escape(title)} — OpenWorker</title><style>"
        ":root{--paper:#f6f5f2;--panel:#fff;--line:#e4e2dc;--ink:#2c2c2a;--muted:#6f6e68;"
        "--faint:#a3a19a;--accent:#3670b2;--ok:#2e7d4f;--ok-soft:#e3f2e9;--bad:#b3423a;"
        "--bad-soft:#f8e7e5}"
        "@media(prefers-color-scheme:dark){:root{--paper:#191918;--panel:#232322;"
        "--line:#373633;--ink:#e8e6e1;--muted:#9d9b94;--faint:#6b6a64;--accent:#6ba3dd;"
        "--ok:#5cb884;--ok-soft:#20362a;--bad:#d97b74;--bad-soft:#3a2422}}"
        "body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;"
        "justify-content:center;gap:18px;background:var(--paper);color:var(--ink);"
        'font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:24px}'
        ".card{background:var(--panel);border:1px solid var(--line);border-radius:16px;"
        "padding:34px 32px 28px;max-width:320px;width:100%;text-align:center;"
        "box-shadow:0 10px 30px rgba(0,0,0,.06);box-sizing:border-box}"
        ".mark{display:flex;align-items:center;justify-content:center;gap:7px;margin-bottom:22px;"
        "font-size:13px;font-weight:650}"
        ".mark i{width:20px;height:20px;border-radius:6px;background:var(--accent);"
        "display:inline-block;position:relative}"
        ".mark i::after{content:'';position:absolute;inset:5px;border-radius:2px;"
        "background:conic-gradient(from 0deg,#fff 0 25%,transparent 0 50%,#fff 0 75%,transparent 0)}"
        ".ico{width:52px;height:52px;border-radius:50%;margin:0 auto 14px;display:flex;"
        "align-items:center;justify-content:center;font-size:24px;position:relative}"
        ".ico.ok{background:var(--ok-soft);color:var(--ok)}"
        ".ico.bad{background:var(--bad-soft);color:var(--bad)}"
        ".mini{position:absolute;right:-3px;bottom:-3px;width:22px;height:22px;border-radius:7px;"
        "display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;"
        "font-weight:700;border:2px solid var(--panel)}"
        "h1{font-size:17px;font-weight:650;margin:0 0 6px;letter-spacing:-.01em}"
        "p{font-size:12.5px;color:var(--muted);margin:0}"
        ".err{font-size:11.5px;color:var(--bad);background:var(--bad-soft);border-radius:8px;"
        "padding:7px 10px;margin-top:12px;text-align:left;word-break:break-word}"
        ".foot{font-size:10.5px;color:var(--faint)}"
        "</style></head><body>"
        '<div class="card"><div class="mark"><i></i>OpenWorker</div>'
        f"{icon}<h1>{_html.escape(title)}</h1><p>{_html.escape(detail)}</p>{err}</div>"
        '<div class="foot">Served locally by OpenWorker on your Mac</div>'
        "</body></html>"
    )


def _connector_title(name: str) -> str:
    """Display name for the loopback page — 'Slack connected', never 'slack connected'."""
    from ..connectors.descriptors import get_descriptor

    d = get_descriptor(name)
    return d.title if d else (name[:1].upper() + name[1:])


_CONNECT_FAILED_DETAIL = (
    "Something went wrong finishing this connection. "
    "Close this tab and try again from OpenWorker."
)

from ..attachments import (
    MAX_ATTACHMENTS as _MAX_ATTACHMENTS,
    MAX_IMAGE_CHARS,
    MAX_PDF_CHARS,
    MAX_TEXT_CHARS,
    build_user_content,
)
from ..engine import ApprovalOutcome
from ..inbox import VIS_INBOX, VIS_INLINE, args_preview
from ..permissions import Mode
from ..providers import AssistantTurn
from .manager import SessionManager


def create_app(
    manager: SessionManager,
    *,
    origin_repository: OriginRepository | None = None,
    storage_runtime: Any | None = None,
    auth_module: AuthModule | None = None,
    diagnostic_store: Any | None = None,
) -> FastAPI:
    from functools import wraps
    from .cloud_security import CloudBudget, MAX_BODY_BYTES

    cloud_budget = CloudBudget()
    from extensions.support.diagnostics import DiagnosticStore, page_category
    from starlette.concurrency import run_in_threadpool

    if diagnostic_store is None:
        try:
            diagnostic_store = DiagnosticStore(
                database=storage_runtime.database if storage_runtime is not None and storage_runtime.mode == "postgres" else None,
                path=Path(manager.audit_store.db_path).with_name("support.db"),
            )
        except (sqlite3.Error, OSError):
            logger.warning("support_storage_unavailable")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            live = (
                await manager.start_gateway() if not alpha.enabled() else []
            )  # start messaging listeners (if configured)
            if live:
                print(f"[coworker] messaging gateway live: {', '.join(live)}")
        except Exception:  # never let a bad connector stop the server
            import traceback

            traceback.print_exc()
        try:
            yield
        finally:
            try:
                await manager.aclose()
            finally:
                if storage_runtime is not None:
                    storage_runtime.close()

    repository = origin_repository
    if repository is None and storage_runtime is not None:
        repository = storage_runtime.origin_repository
    origin_policy = build_origin_policy(
        emergency_origins=os.environ.get(EXTRA_ORIGINS_ENV, ""),
        repository=repository,
    )
    app = FastAPI(title="coworker", version="0.0.0", lifespan=lifespan)
    if auth_module is not None:
        from starlette.middleware.sessions import SessionMiddleware

        app.add_middleware(
            SessionMiddleware,
            secret_key=auth_module.settings.state_secret,
            session_cookie="opencar_oidc_flow",
            max_age=10 * 60,
            same_site="lax",
            https_only=auth_module.settings.cookie_secure,
        )
    api_token = os.environ.get("COWORKER_API_TOKEN", "")
    auth_required = auth_module is not None or authentication_required(
        legacy_token=api_token
    )
    tokenless_paths = {
        "/v1/health",
        "/v1/auth/session",
        "/auth/login",
        "/auth/callback",
        "/mcp/oauth/callback",
        "/oauth/callback",
    }

    def _request_auth_session(request: Request):
        if auth_module is None:
            return None
        return auth_module.resolve(request.cookies.get(SESSION_COOKIE))

    def _request_principal(request: Request) -> Principal | None:
        auth_session = _request_auth_session(request)
        if auth_session is not None:
            return auth_session.principal
        header_token = request.headers.get("x-openworker-token")
        if auth_module is not None:
            return None
        return resolve_principal(
            header_token,
            legacy_token=api_token,
        )

    def _websocket_principal(ws: WebSocket) -> Principal | None:
        if auth_module is not None:
            auth_session = auth_module.resolve(ws.cookies.get(SESSION_COOKIE))
            if auth_session is not None:
                return auth_session.principal
            return None
        protocols = [
            part.strip()
            for part in ws.headers.get("sec-websocket-protocol", "").split(",")
            if part.strip()
        ]
        if not protocols:
            if auth_module is not None:
                return None
            return resolve_principal(None, legacy_token=api_token)
        for protocol in protocols:
            principal = resolve_principal(
                protocol,
                legacy_token=api_token,
            )
            if principal is not None:
                return principal
        return None

    def _origin_allowed(origin: str | None) -> bool:
        return origin is None or origin_policy.allows(origin)

    def _limited_socket(handler):
        @wraps(handler)
        async def guarded(ws: WebSocket, **kwargs):
            principal = _websocket_principal(ws)
            limited = alpha.enabled() and principal is not None
            if limited and not cloud_budget.acquire("socket", principal.user_id):
                logger.warning("cloud_security_refusal category=socket_capacity")
                await ws.close(code=1013)
                return
            try:
                return await handler(ws, **kwargs)
            finally:
                if limited:
                    cloud_budget.release("socket", principal.user_id)
        return guarded

    def _activate_manager(principal: Principal):
        activate = getattr(manager, "activate", None)
        return activate(principal) if callable(activate) else None

    def _deactivate_manager(token) -> None:
        if token is None:
            return
        deactivate = getattr(manager, "deactivate", None)
        if callable(deactivate):
            deactivate(token)

    async def _presence_heartbeat(
        coordinator,
        user_id: str,
        connection_id: str,
    ) -> None:
        while True:
            coordinator.set_presence(
                user_id,
                connection_id,
                _RUNTIME_PRESENCE_TTL_SECONDS,
            )
            await asyncio.sleep(_RUNTIME_PRESENCE_TTL_SECONDS / 3)

    async def _bounded_cloud_body(request: Request):
        if (not alpha.enabled() and not request.url.path.startswith("/v1/support/")) or request.method not in {"POST", "PATCH", "PUT"}:
            return None
        body_limit = 8192 if request.url.path.startswith("/v1/support/") else MAX_BODY_BYTES
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > body_limit):
            logger.warning("cloud_security_refusal category=body_size")
            return JSONResponse({"error": "Request body is too large."}, status_code=413)
        body = bytearray()
        try:
            async with asyncio.timeout(30):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > body_limit:
                        logger.warning("cloud_security_refusal category=body_size")
                        return JSONResponse({"error": "Request body is too large."}, status_code=413)
                    body.extend(chunk)
        except TimeoutError:
            logger.warning("cloud_security_refusal category=body_timeout")
            return JSONResponse({"error": "Request upload timed out."}, status_code=408)
        request._body = bytes(body)
        return None

    @app.middleware("http")
    async def require_sidecar_token(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin is not None and not _origin_allowed(origin):
            return JSONResponse(
                {"error": "origin is not allowed"},
                status_code=403,
            )
        # Preflights carry the requested header name, not its value. CORS checks the
        # Origin; the actual state-changing request still must authenticate.
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.method == "POST" and request.url.path == "/v1/support/anonymous-feedback":
            # One bounded global intake bucket, including signed-in callers.
            # Never trust arbitrary forwarded IP headers for this anonymous admission.
            if not cloud_budget.allow_request("support-anonymous-intake", write=True):
                return JSONResponse({"error": "提交频率过高，请稍后再试。"}, status_code=429, headers={"Retry-After": "60"})
            if not cloud_budget.acquire("anonymous_body", "support-anonymous-intake"):
                logger.warning("cloud_security_refusal category=body_capacity")
                return JSONResponse({"error": "服务繁忙，请稍后再试。"}, status_code=503, headers={"Retry-After": "1"})
            try:
                refusal = await _bounded_cloud_body(request)
                return refusal if refusal is not None else await call_next(request)
            finally:
                cloud_budget.release("anonymous_body", "support-anonymous-intake")
        principal = _request_principal(request)
        if principal is None:
            if request.url.path in tokenless_paths:
                return await call_next(request)
            return JSONResponse(
                {"error": "missing or invalid OpenWorker sidecar token"},
                status_code=401,
            )
        request.state.principal = principal
        if (alpha.enabled() or request.url.path.startswith("/v1/support/")) and not cloud_budget.allow_request(
            principal.user_id, write=request.method not in {"GET", "HEAD"}
        ):
            logger.warning("cloud_security_refusal category=request_rate")
            return JSONResponse({"error": "Too many requests. Please try again later."},
                                status_code=429, headers={"Retry-After": "60"})
        body_limited = (
            (alpha.enabled() or request.url.path.startswith("/v1/support/"))
            and request.method in {"POST", "PATCH", "PUT"}
        )
        if body_limited and not cloud_budget.acquire("body", principal.user_id):
            logger.warning("cloud_security_refusal category=body_capacity")
            return JSONResponse({"error": "Service is busy. Please try again."}, status_code=503,
                                headers={"Retry-After": "1"})
        manager_token = None
        try:
            refusal = await _bounded_cloud_body(request)
            if refusal is not None:
                return refusal
            manager_token = _activate_manager(principal)
            return await call_next(request)
        finally:
            _deactivate_manager(manager_token)
            if body_limited:
                cloud_budget.release("body", principal.user_id)

    @app.middleware("http")
    async def restrict_public_alpha(request: Request, call_next):
        if alpha.blocks_http(request.method, request.url.path):
            logger.warning("cloud_security_refusal category=disabled_route")
            return JSONResponse(
                {"error": "This local-machine control is disabled in Career Alpha."},
                status_code=403,
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origin_policy.origins),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.state.manager = manager
    app.state.origin_policy = origin_policy
    app.state.storage_runtime = storage_runtime
    app.state.auth_module = auth_module
    app.state.diagnostic_store = diagnostic_store
    from extensions.support.feedback import FeedbackStore
    from extensions.support.routes import support_router
    support_available = diagnostic_store is not None
    if support_available:
        try:
            app.include_router(support_router(FeedbackStore(diagnostic_store)))
        except (sqlite3.Error, OSError):
            support_available = False
            logger.warning("support_storage_unavailable")
    if not support_available:
        @app.api_route("/v1/support/{support_path:path}", methods=["GET", "POST", "PATCH"])
        def unavailable_support(support_path: str):
            return JSONResponse({"error": "反馈服务暂不可用，请稍后重试。"}, status_code=503)

    @app.middleware("http")
    async def diagnostic_request(request: Request, call_next):
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            # Never expose arbitrary exception strings or upstream payloads.
            response = JSONResponse({"error": "请求处理失败，请反馈此问题。", "request_id": request_id}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        principal = getattr(request.state, "principal", None)
        if diagnostic_store is not None and response.status_code >= 400 and principal is not None and not request.url.path.startswith("/v1/support/"):
            try:
                await run_in_threadpool(
                    diagnostic_store.record, principal, request_id=request_id,
                    kind="http_server_error" if response.status_code >= 500 else "http_client_error",
                    page=page_category(request.url.path), status=response.status_code,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            except Exception:
                logger.warning("support_diagnostic_storage_unavailable")
        return response

    @app.get("/v1/support/diagnostics/{request_id}")
    def own_diagnostic(request: Request, request_id: str):
        result = diagnostic_store.get(request.state.principal, request_id)
        if result is None:
            return JSONResponse({"error": "诊断记录不存在或已过期。"}, status_code=404)
        return {"diagnostic": result}

    @app.post("/v1/support/diagnostics", status_code=201)
    def browser_diagnostic(request: Request, body: BrowserDiagnostic):
        request_id = diagnostic_store.record(
            request.state.principal, kind=body.kind, page=body.page, source="browser",
        )
        return {"request_id": request_id}

    @app.get("/v1/health")
    def health(request: Request) -> dict[str, Any]:
        if auth_required and _request_principal(request) is None:
            return {"status": "ok"}
        result = {
            "status": "ok",
            "default_workspace": manager.default_workspace,
            "model": manager.model,
        }
        if storage_runtime is not None:
            result["storage"] = storage_runtime.health()
        return result

    @app.get("/v1/auth/session")
    def auth_session(request: Request) -> dict[str, Any]:
        session = _request_auth_session(request)
        principal = getattr(request.state, "principal", None)
        if session is not None:
            principal = session.principal
        if principal is None:
            return {
                "configured": auth_module is not None,
                "authenticated": False,
                "user": None,
            }
        return {
            "configured": auth_module is not None,
            "authenticated": True,
            "user": {
                "id": principal.user_id,
                "email": session.email if session is not None else None,
                "display_name": (
                    session.display_name if session is not None else None
                ),
            },
        }

    @app.get("/auth/login")
    async def hosted_auth_login(request: Request) -> Response:
        if auth_module is None:
            return JSONResponse(
                {"error": "hosted login is not configured"},
                status_code=404,
            )
        return await auth_module.login(request)

    @app.post("/auth/logout")
    def hosted_auth_logout(request: Request) -> Response:
        if auth_module is None:
            return JSONResponse({"ok": True})
        return auth_module.logout(request.cookies.get(SESSION_COOKIE))

    @app.get("/v1/agents")
    def agents() -> dict[str, Any]:
        listed = manager.personas.sidebar() if alpha.enabled() else manager.list_agents()
        return {"agents": alpha.public_agents(listed)}

    @app.get("/v1/personas")
    def personas() -> dict[str, Any]:
        rows = manager.personas.list_all()
        return {"personas": [r for r in rows if r["id"] == "career"] if alpha.enabled() else rows}

    @app.get("/v1/inbox")
    def inbox(session_id: str = "", state: str = "") -> dict[str, Any]:
        from dataclasses import asdict

        # The cross-session Inbox list shows only Unattended (inbox-visibility) items; a per-session
        # query returns inline ones too, so the answer-in-context card sees parked attended prompts.
        items = manager.inbox.list(
            session_id=session_id or None,
            state=state or None,
            visibility=None if session_id else VIS_INBOX,
        )
        # Enrich with the originating session's context so the Inbox is self-contained — the
        # "go to session" chip needs title/agent/workspace without depending on a (possibly stale)
        # client-side session list, and can link straight to it.
        out: list[dict[str, Any]] = []
        for i in items:
            d = asdict(i)
            rec = manager.session_store.load(i.session_id)
            if (
                rec is None
                and not session_id
                and i.state == "pending"
                and i.session_id not in manager._engines
            ):
                # Lazy cleanup for legacy orphans (sessions deleted before delete_session
                # started closing their items): an orphaned prompt can never be answered.
                # A LIVE engine without a record yet (brand-new session, first turn still
                # running) is NOT an orphan — hence the engine guard.
                manager.inbox.resolve_session(i.session_id)
                continue
            d["session_title"] = (rec.title if rec else None) or i.session_id
            d["session_agent"] = rec.agent if rec else None
            d["session_workspace"] = rec.workspace if rec else None
            d["session_exists"] = rec is not None
            out.append(d)
        return {"items": out}

    @app.post("/v1/inbox/{item_id}/resolve")
    async def resolve_inbox_item(item_id: str, body: dict) -> dict[str, Any]:
        # Idempotent + first-responder-wins: ok=False means it was already resolved elsewhere.
        # Routes through resolve_inbox so a restart-orphaned prompt durably resumes its turn.
        ok = await manager.resolve_inbox(item_id, str(body.get("resolution", "deny")))
        return {"ok": ok}

    @app.get("/v1/subscriptions")
    def subscriptions() -> dict[str, Any]:
        # Global view-only list: each (session → channel) subscription, enriched with the session's
        # title/agent and the channel its Inbox routes OUT to (so an inbound/outbound collision on
        # the same channel is visible).
        out: list[dict[str, Any]] = []
        for sub in manager.subscriptions.all():
            rec = manager.session_store.load(sub.session_id)
            agent = rec.agent if rec else ""
            routing = manager._routing_targets(sub.session_id, agent or "cowork")
            out.append(
                {
                    "session_id": sub.session_id,
                    "session_title": (rec.title if rec else None) or sub.session_id,
                    "agent": agent,
                    "channel": sub.channel,
                    # Display name from the channel buffer ("#ocw-test"), when any inbound
                    # message has carried one — the address stays the identifier.
                    "channel_name": manager.channel_buffer.name_for(sub.channel),
                    "routing_target": routing[0] if routing else None,
                    "collision": bool(routing and sub.channel in routing),
                }
            )
        return {"subscriptions": out}

    @app.get("/v1/channels/recent")
    def recent_channels() -> dict[str, Any]:
        # The picker's "recently-seen" source: channels the bot has received messages from.
        return {"channels": manager.channel_buffer.channels()}

    @app.get("/v1/unrouted")
    def unrouted() -> dict[str, Any]:
        # Dead-letter view: inbound messages with no destination + background-turn failures.
        return {"items": manager.unrouted.list()}

    @app.post("/v1/subscriptions")
    def subscribe(body: dict) -> dict[str, Any]:
        from ..subscriptions import resolve_channel

        session_id = str(body.get("session_id", "")).strip()
        raw = str(body.get("channel", ""))
        addr = resolve_channel(raw)
        if not session_id or not addr or ":" not in addr:
            if raw.strip().startswith("#"):
                # A bare #name can't be looked up locally — storing it literally would create a
                # subscription that never matches real traffic (resolve_channel returns "").
                return {
                    "ok": False,
                    "error": "Channel names can't be looked up — paste the channel ID "
                    "(channel name ▸ About) or the channel's Copy-link URL.",
                }
            return {"ok": False, "error": "need a session_id and a channel"}
        manager.subscriptions.subscribe(session_id, addr)
        return {"ok": True, "channel": addr}

    @app.post("/v1/subscriptions/remove")
    def unsubscribe(body: dict) -> dict[str, Any]:
        from ..subscriptions import resolve_channel

        session_id = str(body.get("session_id", "")).strip()
        addr = resolve_channel(str(body.get("channel", "")))
        removed = manager.subscriptions.unsubscribe(session_id, addr)
        return {"ok": True, "removed": removed}

    @app.get("/v1/inbox/reconcile")
    def reconcile_inbox(session_id: str) -> dict[str, Any]:
        # Called when a session resumes attended control (surface pending + recap inline).
        return manager.inbox.reconcile_on_resume(session_id)

    @app.get("/v1/inbox/routing")
    def inbox_routing() -> dict[str, Any]:
        return {"bindings": manager.inbox_routing.bindings()}

    @app.post("/v1/inbox/routing/binding")
    def set_inbox_binding(body: dict) -> dict[str, Any]:
        name = str(body.get("name", "")).strip()
        if not name:
            return {"ok": False, "error": "binding needs a `name`"}
        return manager.set_inbox_binding(
            name,
            channel=body.get("channel") or None,
            target=str(body.get("target", "")),
        )

    @app.get("/v1/sessions/{session_id}/unattended")
    def get_unattended(session_id: str) -> dict[str, Any]:
        return {"unattended": manager.unattended.is_unattended(session_id)}

    @app.post("/v1/sessions/{session_id}/unattended")
    def set_unattended(session_id: str, body: dict) -> dict[str, Any]:
        # The GUI gates the on-transition behind a one-tap confirm.
        on = bool(body.get("unattended"))
        manager.unattended.set(session_id, on)
        return {"ok": True, "session_id": session_id, "unattended": on}

    @app.get("/v1/sessions/{session_id}/skills")
    def session_skills(session_id: str, workspace: str = "") -> dict[str, Any]:
        # The rail's Skills group + the composer popup both read this (SKILLS-SPEC §4.1).
        if alpha.enabled():
            if workspace and Path(workspace).expanduser().resolve() != Path(alpha.workspace()).resolve():
                return JSONResponse({"error": "workspace is not allowed"}, status_code=403)
            workspace = alpha.workspace()
        return manager.session_skills_view(session_id, workspace or None)

    @app.post("/v1/sessions/{session_id}/skills")
    def set_session_skill(session_id: str, body: dict) -> dict[str, Any]:
        # A session mute. `clear` drops the override (inherit again); otherwise explicit
        # on/off. Nothing on disk changes — Settings owns permanent state.
        body = body or {}
        if alpha.enabled():
            workspace = str(body.get("workspace", ""))
            if workspace and Path(workspace).expanduser().resolve() != Path(alpha.workspace()).resolve():
                return JSONResponse({"error": "workspace is not allowed"}, status_code=403)
            body["workspace"] = alpha.workspace()
        skill = str(body.get("skill", "")).strip()
        if not skill:
            return {"ok": False, "error": "skill required"}
        if alpha.enabled() and skill not in {
            row["name"] for row in manager.list_skills(alpha.workspace())
        }:
            return JSONResponse({"error": "unknown cloud skill"}, status_code=403)
        if body.get("clear"):
            manager.session_skills.clear(session_id, skill)
        else:
            manager.session_skills.set(
                session_id, skill, bool(body.get("enabled", False))
            )
        return manager.session_skills_view(
            session_id, str(body.get("workspace", "")) or None
        )

    @app.get("/v1/sessions/{session_id}/connections")
    def session_connections(session_id: str, persona: str = "") -> dict[str, Any]:
        # `persona` is the GUI's hint for brand-new sessions (no record yet) — without it the
        # view resolves to the default persona and shows the wrong defaults/recommends.
        # §6: the Sources drawer payload — connected connectors w/ state + recommended + ⚠ count.
        return manager.session_connections_view(session_id, persona or None)

    @app.post("/v1/sessions/{session_id}/connections")
    def set_session_connection(session_id: str, body: dict) -> dict[str, Any]:
        # §6: a session override. `clear` drops the override (inherit the persona default again);
        # otherwise set an explicit on/off. Return the refreshed view so the drawer can re-render.
        body = body or {}
        connector = str(body.get("connector", "")).strip()
        if not connector:
            return {"ok": False, "error": "connector required"}
        if body.get("clear"):
            manager.session_connections.clear(session_id, connector)
        else:
            manager.session_connections.set(
                session_id, connector, bool(body.get("enabled", False))
            )
        persona = str(body.get("persona", "")) or None
        return {
            "ok": True,
            "connections": manager.session_connections_view(session_id, persona),
        }

    @app.post("/v1/personas/install")
    def install_persona(body: dict) -> dict[str, Any]:
        # Returns a consent summary per persona; they land disabled pending the user's approval
        # (then POST /v1/personas/{id} {enabled:true, surfaced:true}).
        reg = manager.personas
        try:
            if body.get("git_url"):
                summaries = reg.install_from_git(str(body["git_url"]))
            elif body.get("dir"):
                summaries = reg.install_from_dir(str(body["dir"]))
            elif body.get("gallery_slug"):
                # Gallery install = fetch the manifest markdown from the cloud
                # (sign-in required), verify its hash, then reuse the exact
                # same parser + consent path as a local/Git install. The
                # gallery never changes the trust model: no executable code,
                # lands disabled pending consent.
                import hashlib
                import tempfile

                from .. import cloud
                from ..config import load_config

                slug = str(body["gallery_slug"]).strip()
                manifest = cloud.gallery_manifest(manager.secrets, load_config(), slug)
                if manifest is None:
                    return {
                        "ok": False,
                        "error": "gallery requires cloud sign-in (or the cloud is unreachable)",
                    }
                markdown = manifest.get("manifest_markdown", "")
                digest = "sha256:" + hashlib.sha256(markdown.encode()).hexdigest()
                if (
                    manifest.get("manifest_hash")
                    and manifest["manifest_hash"] != digest
                ):
                    return {"ok": False, "error": "manifest hash mismatch"}
                with tempfile.TemporaryDirectory() as td:
                    (Path(td) / f"{slug}.md").write_text(markdown)
                    summaries = reg.install_from_dir(td)
                cloud.gallery_install_event(manager.secrets, load_config(), slug)
            else:
                return {
                    "ok": False,
                    "error": "provide a `dir`, `git_url`, or `gallery_slug`",
                }
        except Exception as e:  # surface manifest/clone errors to the caller
            return {"ok": False, "error": str(e)}
        return {"ok": True, "consent": summaries, "personas": reg.list_all()}

    @app.get("/v1/cloud/gallery/{slug}")
    def cloud_gallery_detail(slug: str) -> dict[str, Any]:
        """Solo page for one gallery coworker: publisher pitch + capabilities
        derived locally from the manifest (same parser as install)."""
        from .. import cloud
        from ..config import load_config

        body = cloud.gallery_detail(manager.secrets, load_config(), slug)
        if body is None:
            return {"ok": False, "error": "gallery requires cloud sign-in"}
        return body

    @app.get("/v1/cloud/gallery")
    def cloud_gallery() -> dict[str, Any]:
        """Gallery cards for the GUI. Signed out ⇒ ok:false (the gallery is a
        signed-in feature by design; local personas are unaffected)."""
        from .. import cloud
        from ..config import load_config

        body = cloud.gallery_list(manager.secrets, load_config())
        if body is None:
            return {
                "ok": False,
                "error": "gallery requires cloud sign-in",
                "personas": [],
            }
        return {"ok": True, "personas": body.get("personas", [])}

    @app.post("/v1/personas/{persona_id}")
    def update_persona(persona_id: str, body: dict) -> dict[str, Any]:
        reg = manager.personas
        archived = 0
        try:
            if "enabled" in body:
                # Disable archives the persona's sessions atomically (server-side, one
                # request) so any client gets the same semantic. See set_persona_enabled.
                archived = manager.set_persona_enabled(
                    persona_id, bool(body["enabled"])
                )["archived_sessions"]
            if "surfaced" in body:
                reg.set_surfaced(persona_id, bool(body["surfaced"]))
            if body.get("default"):
                reg.set_default(persona_id)
        except KeyError:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        return {"ok": True, "personas": reg.list_all(), "archived_sessions": archived}

    @app.delete("/v1/personas/{persona_id}")
    def persona_delete(persona_id: str) -> dict[str, Any]:
        # Uninstall a non-builtin persona (snapshot dir + lifecycle state). Local
        # operation — works signed out, regardless of where the persona came from.
        try:
            manager.personas.uninstall(persona_id)
        except KeyError:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "personas": manager.personas.list_all()}

    @app.get("/v1/personas/{persona_id}")
    def persona_detail(persona_id: str) -> dict[str, Any]:
        # §5 detail page: identity + capabilities + recommends(+connected) + default connections.
        detail = manager.persona_detail(persona_id)
        if detail is None:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        return detail

    @app.post("/v1/personas/{persona_id}/enable")
    def persona_enable(persona_id: str, body: dict) -> dict[str, Any]:
        # Dedicated §5/§8 route; delegates to the same manager toggle as POST /v1/personas/{id}
        # (so disable archives the persona's sessions here too).
        try:
            manager.set_persona_enabled(
                persona_id, bool((body or {}).get("enabled", True))
            )
        except KeyError:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        return {"ok": True, "personas": manager.personas.list_all()}

    @app.post("/v1/personas/{persona_id}/connections")
    def persona_set_connection(persona_id: str, body: dict) -> dict[str, Any]:
        # §5: flip a persona-default connector on/off; re-reads so the client can refresh.
        body = body or {}
        connector = str(body.get("connector", "")).strip()
        if not connector:
            return {"ok": False, "error": "connector required"}
        return manager.set_persona_connection(
            persona_id, connector, bool(body.get("enabled", False))
        )

    @app.get("/v1/skills")
    def skills(workspace: str = "") -> dict[str, Any]:
        if alpha.enabled() and workspace and Path(workspace).expanduser().resolve() != Path(alpha.workspace()).resolve():
            return JSONResponse({"error": "workspace is not allowed"}, status_code=403)
        if alpha.enabled():
            workspace = alpha.workspace()
        return {"skills": manager.list_skills(workspace or None)}

    @app.post("/v1/skills")
    def create_skill(body: dict) -> dict[str, Any]:
        return manager.create_skill(body or {})

    @app.patch("/v1/skills/{name}")
    def update_skill(name: str, body: dict) -> dict[str, Any]:
        return manager.update_skill(name, body or {})

    @app.delete("/v1/skills/{name}")
    def delete_skill(name: str, workspace: str = "") -> dict[str, Any]:
        return manager.delete_skill(name, workspace or None)

    @app.post("/v1/skills/{name}/move")
    def move_skill(name: str, body: dict) -> dict[str, Any]:
        return manager.move_skill(name, body or {})

    @app.post("/v1/skills/{name}/reveal")
    def reveal_skill(name: str, body: dict) -> dict[str, Any]:
        # §6 "Show folder": open the skill's folder in the OS file manager (local machine).
        return manager.reveal_skill(name, str((body or {}).get("workspace", "")) or None)

    @app.post("/v1/skills/upload")
    def stage_skill_upload(body: dict) -> dict[str, Any]:
        # Stage → preview; nothing is installed until /upload/confirm (SKILLS-SPEC §4.2).
        data_b64 = str((body or {}).get("data_b64", ""))
        if not data_b64:
            return {"ok": False, "error": "No archive supplied."}
        try:
            data = base64.b64decode(data_b64, validate=True)
        except (ValueError, binascii.Error):
            return {"ok": False, "error": "Invalid archive encoding."}
        return manager.stage_skill_upload(data, str((body or {}).get("filename", "")))

    @app.post("/v1/skills/upload/confirm")
    def confirm_skill_upload(body: dict) -> dict[str, Any]:
        return manager.confirm_skill_upload(body or {})

    @app.post("/v1/career/resumes/stage")
    def stage_resume_upload(
        request: Request,
        body: Any = Body(...),
    ) -> dict[str, Any]:
        return manager.stage_resume_upload(
            body,
            service=career_resume_service(request),
        )

    def career_resume_service(request: Request):
        from extensions.career_mcp.services.resumes import ResumeService

        if (
            storage_runtime is None
            or getattr(storage_runtime, "mode", "local") != "postgres"
        ):
            return ResumeService()
        from coworker.storage.postgres.blob_repository import (
            PostgresBlobRepository,
        )
        from coworker.storage.postgres.resume_service import (
            PostgresResumeService,
        )

        return PostgresResumeService(
            storage_runtime.database,
            request.state.principal,
            PostgresBlobRepository(storage_runtime.database),
        )

    def career_resume_error(exc: Exception) -> JSONResponse:
        if not getattr(exc, "code", None):
            logger.exception("career profile request failed")
        code = str(getattr(exc, "code", "PERSISTENCE_ERROR"))
        status = (
            400
            if code == "INVALID_INPUT"
            else 404
            if code in {
                "PROFILE_NOT_FOUND",
                "RESUME_NOT_FOUND",
                "ORIGINAL_NOT_FOUND",
            }
            else 409
        )
        messages = {
            "PROFILE_NOT_FOUND": "尚未建立求职档案。",
            "RESUME_NOT_FOUND": "未找到这份简历。",
            "ORIGINAL_NOT_FOUND": "档案存在，但原始简历文件不可用。",
            "CONFIRMATION_REQUIRED": "删除确认内容不正确。",
            "INVALID_INPUT": "简历名称或目标岗位标签不符合要求。",
        }
        return JSONResponse(
            status_code=status,
            content={
                "ok": False,
                "error": {
                    "code": code,
                    "message": messages.get(code, "本地求职档案读取失败。"),
                },
            },
        )

    @app.get("/v1/career/profile")
    def career_profile_get(
        request: Request,
        include_sensitive: bool = False,
    ):
        try:
            profile = career_resume_service(request).get_candidate_profile(
                include_sensitive=include_sensitive,
            )
            return {"ok": True, "profile": profile}
        except Exception as exc:
            return career_resume_error(exc)

    @app.get("/v1/career/profile/versions")
    def career_profile_versions_get(request: Request):
        try:
            return {
                "ok": True,
                "versions": career_resume_service(
                    request
                ).get_profile_versions(),
            }
        except Exception as exc:
            return career_resume_error(exc)

    @app.get("/v1/career/profile/original")
    def career_profile_original_get(request: Request):
        try:
            return {
                "ok": True,
                "original": career_resume_service(
                    request
                ).get_profile_original(),
            }
        except Exception as exc:
            return career_resume_error(exc)

    def career_original_response(
        request: Request,
        *,
        download: bool,
        resume_id: str | None = None,
    ) -> Response:
        try:
            service = career_resume_service(request)
            if resume_id is None:
                original = (
                    service.read_profile_original()
                    if download
                    else service.render_profile_original()
                )
            else:
                original = (
                    service.read_resume_document_original(resume_id)
                    if download
                    else service.render_resume_document_original(resume_id)
                )
        except Exception as exc:
            return career_resume_error(exc)
        filename = str(original["filename"])
        source_kind = original["source_kind"]
        media_type = original.get("media_type") or {
            "pdf": "application/pdf",
            "docx": (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            "text": "text/plain; charset=utf-8",
        }.get(source_kind, "application/octet-stream")
        disposition = "attachment" if download else "inline"
        return Response(
            content=original["bytes"],
            media_type=media_type,
            headers={
                "Content-Disposition": _content_disposition(
                    disposition,
                    filename,
                ),
            },
        )

    @app.get("/v1/career/profile/original/content")
    def career_profile_original_content_get(request: Request):
        return career_original_response(request, download=False)

    @app.get("/v1/career/profile/original/download")
    def career_profile_original_download_get(request: Request):
        return career_original_response(request, download=True)

    @app.get("/v1/career/resumes")
    def career_resumes_get(request: Request):
        try:
            return {
                "ok": True,
                "resumes": career_resume_service(
                    request
                ).list_resume_documents(),
            }
        except Exception as exc:
            return career_resume_error(exc)

    @app.get("/v1/career/resumes/{resume_id}")
    def career_resume_get(
        resume_id: str,
        request: Request,
        include_sensitive: bool = False,
    ):
        try:
            return {
                "ok": True,
                "resume": career_resume_service(
                    request
                ).get_resume_document(
                    resume_id,
                    include_sensitive=include_sensitive,
                ),
            }
        except Exception as exc:
            return career_resume_error(exc)

    @app.patch("/v1/career/resumes/{resume_id}")
    def career_resume_patch(
        resume_id: str,
        request: Request,
        body: dict,
    ):
        try:
            payload = body or {}
            return {
                "ok": True,
                "resume": career_resume_service(
                    request
                ).update_resume_document(
                    resume_id,
                    display_name=payload.get("display_name"),
                    target_roles=payload.get("target_roles", []),
                ),
            }
        except Exception as exc:
            return career_resume_error(exc)

    @app.delete("/v1/career/resumes/{resume_id}")
    def career_resume_delete(
        resume_id: str,
        request: Request,
        body: dict,
    ):
        try:
            deleted = career_resume_service(
                request
            ).delete_resume_document(
                resume_id,
                confirm_name=(body or {}).get("confirm_name"),
            )
            return {"ok": True, "deleted": deleted}
        except Exception as exc:
            return career_resume_error(exc)

    @app.get("/v1/career/resumes/{resume_id}/versions")
    def career_resume_versions_get(
        resume_id: str,
        request: Request,
    ):
        try:
            return {
                "ok": True,
                "versions": career_resume_service(
                    request
                ).get_resume_document_versions(resume_id),
            }
        except Exception as exc:
            return career_resume_error(exc)

    @app.get("/v1/career/resumes/{resume_id}/original")
    def career_resume_original_get(
        resume_id: str,
        request: Request,
    ):
        try:
            return {
                "ok": True,
                "original": career_resume_service(
                    request
                ).get_resume_document_original(resume_id),
            }
        except Exception as exc:
            return career_resume_error(exc)

    @app.get("/v1/career/resumes/{resume_id}/original/content")
    def career_resume_original_content_get(
        resume_id: str,
        request: Request,
    ):
        return career_original_response(
            request,
            download=False,
            resume_id=resume_id,
        )

    @app.get("/v1/career/resumes/{resume_id}/original/download")
    def career_resume_original_download_get(
        resume_id: str,
        request: Request,
    ):
        return career_original_response(
            request,
            download=True,
            resume_id=resume_id,
        )

    @app.delete("/v1/career/profile")
    def career_profile_delete(request: Request, body: dict):
        try:
            deleted = career_resume_service(
                request
            ).delete_candidate_profile(
                str((body or {}).get("confirm_text", "")),
            )
            return {"ok": True, "deleted": deleted}
        except Exception as exc:
            return career_resume_error(exc)

    def career_tracking_service(request: Request):
        from extensions.career_mcp.services.job_tracking import (
            JobTrackingService,
        )

        if (
            storage_runtime is None
            or getattr(storage_runtime, "mode", "local") != "postgres"
        ):
            return JobTrackingService()
        from coworker.storage.postgres.job_tracking import (
            PostgresJobTrackingRepository,
        )

        principal = request.state.principal

        @contextmanager
        def repository_session(*, write: bool = False):
            del write
            with storage_runtime.database.transaction(
                principal
            ) as connection:
                yield PostgresJobTrackingRepository(
                    connection,
                    principal,
                )

        return JobTrackingService(
            repository_session=repository_session,
        )

    def career_job_service(request: Request):
        from extensions.career_mcp.services.jobs import JobService

        if (
            storage_runtime is None
            or getattr(storage_runtime, "mode", "local") != "postgres"
        ):
            return JobService()
        from extensions.career_mcp.database.postgres_catalog_repository import (
            PostgresCatalogRepository,
        )

        principal = request.state.principal

        @contextmanager
        def repository_session(*, write: bool = False):
            del write
            with storage_runtime.database.transaction(
                principal
            ) as connection:
                yield PostgresCatalogRepository(
                    connection,
                    principal_user_id=principal.user_id,
                )

        tracking = career_tracking_service(request)
        return JobService(
            repository_session=repository_session,
            tracking_service=tracking,
        )

    def career_interview_service(request: Request):
        from extensions.career_mcp.services.interviews import (
            InterviewService,
        )

        if (
            storage_runtime is None
            or getattr(storage_runtime, "mode", "local") != "postgres"
        ):
            return InterviewService()
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

        principal = request.state.principal

        @contextmanager
        def repository_session(*, write: bool = False):
            del write
            with storage_runtime.database.transaction(
                principal
            ) as connection:
                yield PostgresInterviewRepository(
                    connection,
                    principal,
                )

        def resume_loader(resume_id: str):
            with storage_runtime.database.transaction(
                principal
            ) as connection:
                return PostgresResumeReader(
                    connection,
                    principal,
                ).get_interview_input(resume_id)

        def job_loader(job_id: str):
            with storage_runtime.database.transaction(
                principal
            ) as connection:
                return PostgresCatalogRepository(
                    connection,
                    principal_user_id=principal.user_id,
                ).get_interview_input(job_id)

        return InterviewService(
            repository_session=repository_session,
            job_loader=job_loader,
            resume_loader=resume_loader,
            blob_repository=PostgresBlobRepository(
                storage_runtime.database
            ),
            principal=principal,
        )

    def career_tracking_error(exc: Exception) -> JSONResponse:
        code = str(getattr(exc, "code", "PERSISTENCE_ERROR"))
        statuses = {
            "INVALID_INPUT": 400,
            "INVALID_STATUS": 400,
            "JOB_NOT_FOUND": 404,
            "VERSION_CONFLICT": 409,
            "PERSISTENCE_ERROR": 409,
        }
        messages = {
            "INVALID_INPUT": "岗位跟踪参数无效。",
            "INVALID_STATUS": "申请进度无效。",
            "JOB_NOT_FOUND": "岗位不存在或已被删除。",
            "VERSION_CONFLICT": "记录已在其他入口更新，请刷新后重试。",
            "PERSISTENCE_ERROR": "本地岗位跟踪记录读写失败。",
        }
        if code == "PERSISTENCE_ERROR":
            logger.exception("career job tracking request failed")
        return JSONResponse(
            status_code=statuses.get(code, 409),
            content={
                "ok": False,
                "error": {
                    "code": code,
                    "message": messages.get(
                        code,
                        "本地岗位跟踪记录读写失败。",
                    ),
                },
            },
        )

    def career_interview_error(exc: Exception) -> JSONResponse:
        code = str(getattr(exc, "code", "PERSISTENCE_ERROR"))
        statuses = {
            "INVALID_INPUT": 400,
            "QUESTION_VALIDATION_FAILED": 400,
            "EVALUATION_VALIDATION_FAILED": 400,
            "VOICE_NOT_CONFIGURED": 400,
            "ASR_FAILED": 400,
            "TTS_FAILED": 400,
            "JOB_NOT_FOUND": 404,
            "RESUME_NOT_FOUND": 404,
            "INTERVIEW_NOT_FOUND": 404,
            "TURN_NOT_FOUND": 404,
            "INTERVIEW_STATE_CONFLICT": 409,
            "TURN_ALREADY_ANSWERED": 409,
            "VERSION_CONFLICT": 409,
            "REPORT_VALIDATION_FAILED": 409,
            "PERSISTENCE_ERROR": 409,
        }
        messages = {
            "INVALID_INPUT": "模拟面试参数无效。",
            "QUESTION_VALIDATION_FAILED": "面试问题未通过事实引用校验。",
            "EVALUATION_VALIDATION_FAILED": "面试评价未通过安全校验。",
            "VOICE_NOT_CONFIGURED": "尚未配置模拟面试语音服务。",
            "ASR_FAILED": "语音识别失败，请重试或输入文字回答。",
            "TTS_FAILED": "语音播放生成失败，请直接阅读文字问题。",
            "JOB_NOT_FOUND": "岗位不存在或已被删除。",
            "RESUME_NOT_FOUND": "简历不存在、未确认或已被删除。",
            "INTERVIEW_NOT_FOUND": "未找到这场模拟面试。",
            "TURN_NOT_FOUND": "未找到当前面试问题。",
            "INTERVIEW_STATE_CONFLICT": "当前面试状态不允许执行此操作。",
            "TURN_ALREADY_ANSWERED": "当前问题已经提交过回答。",
            "VERSION_CONFLICT": "面试已在其他入口更新，请刷新后重试。",
            "REPORT_VALIDATION_FAILED": "面试报告未通过安全校验。",
            "PERSISTENCE_ERROR": "本地模拟面试记录读写失败。",
        }
        if code == "PERSISTENCE_ERROR":
            logger.exception("career interview request failed")
        content: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": code,
                "message": messages.get(
                    code,
                    "本地模拟面试记录读写失败。",
                ),
            },
        }
        violations = getattr(exc, "violations", None)
        if isinstance(violations, list) and violations:
            content["error"]["violations"] = violations
        return JSONResponse(
            status_code=statuses.get(code, 409),
            content=content,
        )

    def career_job_error(exc: Exception) -> JSONResponse:
        if isinstance(exc, LookupError):
            code = "JOB_NOT_FOUND"
            status = 404
            message = "岗位不存在或已被删除。"
        elif isinstance(exc, ValueError):
            code = str(getattr(exc, "code", "INVALID_INPUT"))
            status = 400
            message = (
                "申请进度无效。"
                if code == "INVALID_STATUS"
                else "岗位筛选条件无效。"
            )
        else:
            logger.exception("career jobs request failed")
            code = "PERSISTENCE_ERROR"
            status = 409
            message = "本地岗位数据读取失败。"
        return JSONResponse(
            status_code=status,
            content={
                "ok": False,
                "error": {"code": code, "message": message},
            },
        )

    @app.post("/v1/career/interviews")
    def career_interview_create(
        request: Request,
        body: Any = Body(None),
    ):
        if not isinstance(body, dict):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            return {
                "ok": True,
                "interview": career_interview_service(request).create(
                    body.get("job_id"),
                    body.get("resume_id"),
                    conversation_id=body.get("conversation_id"),
                    difficulty=body.get("difficulty", "standard"),
                    duration_minutes=body.get("duration_minutes", 15),
                    restart=body.get("restart", False),
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.get("/v1/career/interviews")
    def career_interview_get_by_conversation(
        request: Request,
        conversation_id: str,
    ):
        try:
            return {
                "ok": True,
                "interview": (
                    career_interview_service(
                        request
                    ).get_by_conversation(
                        conversation_id
                    )
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.post("/v1/career/interviews/voice/transcribe")
    async def career_interview_transcribe(body: Any = Body(None)):
        if not isinstance(body, dict):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        encoded = body.get("data_base64")
        mime = body.get("mime")
        if not isinstance(encoded, str) or not isinstance(mime, str):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            audio = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            transcript = (
                await career_interview_voice_service().transcribe(
                    audio,
                    mime=mime,
                )
            )
            return {"ok": True, "transcript": transcript}
        except Exception as exc:
            return career_interview_error(exc)

    @app.post("/v1/career/interviews/voice/synthesize")
    async def career_interview_synthesize(body: Any = Body(None)):
        if not isinstance(body, dict) or not isinstance(
            body.get("text"), str
        ):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            audio = await career_interview_voice_service().synthesize(
                body["text"]
            )
        except Exception as exc:
            return career_interview_error(exc)
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/v1/career/interviews/{session_id}")
    def career_interview_get(session_id: str, request: Request):
        try:
            return {
                "ok": True,
                "interview": career_interview_service(request).get(
                    session_id
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.post("/v1/career/interviews/{session_id}/conversation")
    def career_interview_bind_conversation(
        session_id: str,
        request: Request,
        body: Any = Body(None),
    ):
        if not isinstance(body, dict):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            return {
                "ok": True,
                "interview": (
                    career_interview_service(
                        request
                    ).bind_conversation(
                        session_id,
                        expected_version=body.get("expected_version"),
                        conversation_id=body.get("conversation_id"),
                    )
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.post("/v1/career/interviews/{session_id}/start")
    def career_interview_start(
        session_id: str,
        request: Request,
        body: Any = Body(None),
    ):
        if not isinstance(body, dict):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            return {
                "ok": True,
                "interview": career_interview_service(request).start(
                    session_id,
                    expected_version=body.get("expected_version"),
                    question=body.get("question"),
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.post("/v1/career/interviews/{session_id}/answers")
    def career_interview_answer(
        session_id: str,
        request: Request,
        body: Any = Body(None),
    ):
        if not isinstance(body, dict):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            return {
                "ok": True,
                "interview": career_interview_service(
                    request
                ).submit_answer(
                    session_id,
                    body.get("turn_id"),
                    expected_version=body.get("expected_version"),
                    answer_text=body.get("answer_text"),
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.post("/v1/career/interviews/{session_id}/next")
    def career_interview_next(
        session_id: str,
        request: Request,
        body: Any = Body(None),
    ):
        if not isinstance(body, dict):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            return {
                "ok": True,
                "interview": (
                    career_interview_service(
                        request
                    ).evaluate_and_next(
                        session_id,
                        body.get("turn_id"),
                        expected_version=body.get("expected_version"),
                        evaluation=body.get("evaluation"),
                        next_action=body.get("next_action"),
                        next_reason=body.get("next_reason"),
                        next_question=body.get("next_question"),
                        user_requested=bool(
                            body.get("user_requested", False)
                        ),
                    )
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.post("/v1/career/interviews/{session_id}/finish")
    def career_interview_finish(
        session_id: str,
        request: Request,
        body: Any = Body(None),
    ):
        if not isinstance(body, dict):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            return {
                "ok": True,
                "interview": career_interview_service(request).finish(
                    session_id,
                    expected_version=body.get("expected_version"),
                    user_requested=bool(
                        body.get("user_requested", False)
                    ),
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.post("/v1/career/interviews/{session_id}/report")
    def career_interview_report(
        session_id: str,
        request: Request,
        body: Any = Body(None),
    ):
        if not isinstance(body, dict):
            return career_interview_error(
                _coded_error("INVALID_INPUT")
            )
        try:
            return {
                "ok": True,
                "interview": (
                    career_interview_service(
                        request
                    ).generate_report(
                        session_id,
                        expected_version=body.get("expected_version"),
                    )
                ),
            }
        except Exception as exc:
            return career_interview_error(exc)

    @app.get(
        "/v1/career/interviews/{session_id}/artifacts/{kind}"
    )
    def career_interview_artifact(
        session_id: str,
        kind: str,
        request: Request,
    ):
        try:
            result = career_interview_service(request).read_artifact(
                session_id,
                kind,
            )
        except Exception as exc:
            return career_interview_error(exc)
        return Response(
            content=result["bytes"],
            media_type=result["media_type"],
            headers={
                "Content-Disposition": _content_disposition(
                    "attachment",
                    result["filename"],
                ),
            },
        )

    @app.get("/v1/career/jobs")
    def career_jobs_get(
        request: Request,
        query: str = "",
        company_slug: str = "",
        location: str = "",
        recruitment_type: str = "",
        status: str = "active",
        favorite_only: bool = False,
        application_status: str = "",
        limit: int = 20,
        offset: int = 0,
    ):
        try:
            result = career_job_service(request).search_jobs(
                query=query.strip() or None,
                company_slugs=[company_slug] if company_slug else None,
                locations=[location] if location else None,
                recruitment_types=(
                    [recruitment_type] if recruitment_type else None
                ),
                statuses=[status] if status else None,
                favorite_only=favorite_only,
                application_status=(
                    application_status or None
                ),
                limit=limit,
                offset=offset,
            )
            for job in result["jobs"]:
                job.pop("description_raw", None)
                job.pop("responsibilities", None)
                job.pop("requirements", None)
            return {"ok": True, **result}
        except Exception as exc:
            return career_job_error(exc)

    @app.get("/v1/career/jobs/sync")
    def career_local_job_sync_get():
        if os.environ.get("OPENCAR_LOCAL_MODE") != "1":
            return JSONResponse({"ok": False}, status_code=404)
        from extensions.career_mcp.config import CareerConfig
        from extensions.career_mcp.local_jobs import read_status
        state = read_status(CareerConfig.from_env())
        configured_mode = os.environ.get("OPENCAR_LOCAL_JOB_SOURCE", "shared")
        if state.get("mode", configured_mode) != configured_mode:
            state = {"state": "waiting", "sources": [], "completed": 0, "failed": 0,
                     "total_sources": 0, "updated_at": 0}
        state.setdefault("mode", configured_mode)
        return {"ok": True, **state}

    @app.post("/v1/career/jobs/sync")
    def career_local_job_sync_post():
        if os.environ.get("OPENCAR_LOCAL_MODE") != "1":
            return JSONResponse({"ok": False}, status_code=404)
        from extensions.career_mcp.config import CareerConfig
        from extensions.career_mcp.local_jobs import read_status, request_refresh
        config = CareerConfig.from_env()
        state = read_status(config)
        # Ignore repeat clicks during a live cycle and limit completed-cycle refreshes.
        if (state["state"] == "running" and time.time() - state["updated_at"] < 1200
                or time.time() - state["updated_at"] < 60):
            return {"ok": True, "queued": False}
        return {"ok": True, "queued": request_refresh(config)}

    @app.get("/v1/career/jobs/{job_id}/tracking")
    def career_job_tracking_get(job_id: str, request: Request):
        try:
            return {
                "ok": True,
                "tracking": career_tracking_service(request).get(job_id),
            }
        except Exception as exc:
            return career_tracking_error(exc)

    @app.patch("/v1/career/jobs/{job_id}/tracking")
    def career_job_tracking_patch(
        job_id: str,
        request: Request,
        body: Any = Body(None),
    ):
        try:
            return {
                "ok": True,
                "tracking": career_tracking_service(request).update(
                    job_id,
                    body,
                ),
            }
        except Exception as exc:
            return career_tracking_error(exc)

    @app.get("/v1/career/jobs/filters")
    def career_job_filters_get(request: Request):
        try:
            return {
                "ok": True,
                "filters": career_job_service(request).get_job_filters(),
            }
        except Exception as exc:
            return career_job_error(exc)

    @app.get("/v1/career/jobs/{job_id}")
    def career_job_get(job_id: str, request: Request):
        try:
            return {
                "ok": True,
                "job": career_job_service(request).get_job(job_id),
            }
        except Exception as exc:
            return career_job_error(exc)

    @app.get("/v1/workspaces/recent")
    def recent_workspaces() -> dict[str, Any]:
        return {"workspaces": manager.recent_workspaces()}

    @app.post("/v1/workspaces/open")
    def open_workspace(body: dict) -> dict[str, Any]:
        return manager.open_workspace(
            body.get("path", ""), create=bool(body.get("create"))
        )

    @app.get("/v1/workspaces/trusted")
    def trusted_workspaces() -> dict[str, Any]:
        return {"workspaces": manager.trusted_workspaces()}

    @app.post("/v1/workspaces/trust")
    def set_workspace_trust(body: dict) -> dict[str, Any]:
        return manager.set_workspace_trust(
            str((body or {}).get("path", "")),
            trusted=bool((body or {}).get("trusted", False)),
        )

    @app.post("/v1/workspaces/pick")
    async def pick_workspace() -> dict[str, Any]:
        # Native folder picker opened by the LOCAL sidecar (browser GUIs can't get absolute
        # paths from web file dialogs). Off the event loop: blocks until pick/cancel.
        return await asyncio.to_thread(manager.pick_native_folder)

    @app.get("/v1/sessions")
    def sessions(workspace: str | None = None) -> dict[str, Any]:
        return {"sessions": manager.list_sessions(workspace)}

    @app.get("/v1/sessions/{session_id}/messages")
    def session_messages(session_id: str) -> dict[str, Any]:
        return {"messages": manager.session_messages(session_id)}

    @app.patch("/v1/sessions/{session_id}")
    def session_patch(session_id: str, body: dict) -> dict[str, Any]:
        body = body or {}
        if "pinned" in body or "archived" in body:
            return manager.set_session_flags(
                session_id,
                pinned=bool(body["pinned"]) if "pinned" in body else None,
                archived=bool(body["archived"]) if "archived" in body else None,
            )
        return manager.rename_session(session_id, str(body.get("title", "")))

    @app.delete("/v1/sessions/{session_id}")
    def session_delete(session_id: str) -> dict[str, Any]:
        return manager.delete_session(session_id)

    @app.get("/v1/sessions/{session_id}/roots")
    def session_roots(session_id: str) -> dict[str, Any]:
        return {"roots": manager.get_roots(session_id)}

    @app.post("/v1/sessions/{session_id}/roots")
    def session_add_root(session_id: str, body: dict) -> dict[str, Any]:
        body = body or {}
        return manager.add_root(
            session_id, str(body.get("path", "")), bool(body.get("writable", False))
        )

    @app.delete("/v1/sessions/{session_id}/roots")
    def session_remove_root(session_id: str, path: str) -> dict[str, Any]:
        return manager.remove_root(session_id, path)

    @app.get("/v1/sessions/{session_id}/artifacts")
    def session_artifacts(session_id: str) -> dict[str, Any]:
        return {"artifacts": manager.list_artifacts(session_id)}

    @app.get("/v1/sessions/{session_id}/artifacts/read")
    def session_artifact_read(session_id: str, path: str) -> dict[str, Any]:
        return manager.read_artifact(session_id, path)

    @app.post("/v1/sessions/{session_id}/artifacts/reveal")
    def session_artifact_reveal(session_id: str, body: dict) -> dict[str, Any]:
        body = body or {}
        return manager.reveal_artifact(
            session_id, str(body.get("path", "")), str(body.get("mode", "reveal"))
        )

    @app.get("/v1/memory")
    def memory() -> dict[str, Any]:
        return {"memory": manager.list_memory()}

    @app.post("/v1/memory")
    def add_memory(body: dict) -> dict[str, Any]:
        return manager.add_memory(
            body.get("content", ""), body.get("scope", "workspace")
        )

    @app.post("/v1/chat/completions")
    def chat_completions(body: dict) -> dict[str, Any]:
        model = body.get("model", manager.model)
        turn = manager.provider_complete(
            model, body.get("messages", []), body.get("tools")
        )
        return _openai_response(model, turn)

    # -- MCP servers ------------------------------------------------------------
    @app.get("/v1/mcp")
    def mcp_list() -> dict[str, Any]:
        return {"servers": manager.list_mcp()}

    @app.post("/v1/mcp")
    def mcp_add(body: dict) -> dict[str, Any]:
        name = body.get("name")
        config = body.get("config")
        if not name or not isinstance(config, dict):
            return {"ok": False, "error": "name and config required"}
        return manager.add_mcp(name, config)

    @app.patch("/v1/mcp/{name}")
    def mcp_patch(name: str, body: dict) -> dict[str, Any]:
        return manager.patch_mcp(name, body or {})

    @app.delete("/v1/mcp/{name}")
    def mcp_delete(name: str) -> dict[str, Any]:
        return manager.delete_mcp(name)

    @app.get("/v1/mcp/{name}/tools")
    async def mcp_tools(name: str) -> dict[str, Any]:
        return await manager.mcp_tools(name)

    @app.post("/v1/mcp/{name}/connect")
    async def mcp_connect(name: str) -> dict[str, Any]:
        # Connect now. For `auth: oauth` servers the first connect opens the system
        # browser and waits on the loopback callback — that can take minutes, so it
        # runs as a background task; the GUI polls /v1/mcp for the status flip
        # (authorizing → connected | needs_auth + last_error).
        asyncio.create_task(manager.connect_mcp(name))
        return {"ok": True, "started": True}

    @app.post("/v1/mcp/{name}/signout")
    async def mcp_signout(name: str) -> dict[str, Any]:
        return await manager.signout_mcp(name)

    @app.get("/mcp/oauth/callback")
    async def mcp_oauth_callback(
        code: str = "", state: str = "", error: str = ""
    ) -> Any:
        # Loopback landing for the MCP OAuth browser flow (mcp/oauth.py). Browser-facing:
        # returns the same styled page as the managed-connector callbacks.
        from fastapi.responses import HTMLResponse

        from ..mcp import oauth as mcp_oauth

        if error:
            return HTMLResponse(
                _browser_page(
                    "Sign-in failed",
                    "The service reported an error. Return to OpenWorker and try again.",
                    ok=False,
                    error=error,
                ),
                status_code=400,
            )
        if not code or not mcp_oauth.deliver_callback(code, state or None):
            return HTMLResponse(
                _browser_page(
                    "Nothing waiting for this sign-in",
                    "The sign-in may have timed out. Return to OpenWorker and start it again.",
                    ok=False,
                ),
                status_code=400,
            )
        return HTMLResponse(
            _browser_page(
                "Connected",
                "Sign-in complete. You can close this tab and return to OpenWorker.",
                ok=True,
            )
        )

    @app.post("/v1/mcp/reload")
    async def mcp_reload() -> dict[str, Any]:
        return await manager.reload_mcp()

    # -- connectors (Slack / Telegram / …) --------------------------------------
    @app.get("/v1/connectors")
    def connectors_list() -> dict[str, Any]:
        return {"connectors": manager.list_connectors()}

    async def _refresh_listeners_if_two_way(name: str) -> None:
        # New/removed creds only take effect when the platform socket reconnects (Socket Mode
        # authenticates at connect time) — hot-reload the listeners in-process so pasting
        # tokens works immediately, no sidecar restart (§19).
        from ..connectors.config import PLATFORMS

        if name in PLATFORMS:
            try:
                await manager.refresh_gateway()
            except Exception:
                pass  # a listener that fails to come up must not fail the save

    @app.post("/v1/connectors/{name}/connect")
    async def connector_connect(name: str, body: dict) -> dict[str, Any]:
        fields = body.get("fields") if isinstance(body, dict) else None
        # experimental connectors require the caller to explicitly acknowledge the risk notice
        acknowledged = bool(isinstance(body, dict) and body.get("acknowledge_risk"))
        # token validation does a blocking HTTP call → keep it off the event loop
        result = await asyncio.to_thread(
            lambda: manager.connect_connector(
                name, fields or {}, acknowledged=acknowledged
            )
        )
        if result.get("ok"):
            await _refresh_listeners_if_two_way(name)
        return result

    @app.post("/v1/connectors/{name}/mcp-connect")
    async def connector_mcp_connect(name: str) -> dict[str, Any]:
        # One-click connect for an MCP-backed connector: the browser OAuth flow can
        # take minutes, so it runs in the background; the GUI polls /v1/connectors
        # until the card flips to connected (mode "mcp").
        from ..connectors.descriptors import get_descriptor

        d = get_descriptor(name)
        if d is None or not d.mcp_url:
            return {"ok": False, "error": f"{name} has no MCP connect path"}
        asyncio.create_task(manager.mcp_connect_connector(name))
        return {"ok": True, "started": True}

    @app.post("/v1/connectors/{name}/disconnect")
    async def connector_disconnect(name: str) -> dict[str, Any]:
        # Managed profiles: best-effort flip of the cloud metadata record first
        # (network call → off the loop). Local deletion always proceeds.
        from .. import cloud
        from ..config import load_config

        await asyncio.to_thread(
            lambda: cloud.cloud_disconnect(manager.secrets, load_config(), name)
        )
        result = manager.disconnect_connector(name)
        await _refresh_listeners_if_two_way(name)
        return result

    @app.post("/v1/connectors/slack/workspaces/{team_id}/disconnect")
    async def slack_workspace_disconnect(team_id: str) -> dict[str, Any]:
        """Stop relaying one workspace (managed relay). Cloud routing row deleted
        best-effort, local per-team token removed, gateway hot-reloaded."""
        return await manager.disconnect_slack_workspace(team_id)

    @app.get("/v1/connectors/slack/status")
    async def slack_status() -> dict[str, Any]:
        """Slack health, three layers: relay socket / cloud sign-in / per-team tokens."""
        return manager.slack_status()

    @app.post("/v1/connectors/github/installations/{installation_id}/disconnect")
    async def github_installation_disconnect(installation_id: str) -> dict[str, Any]:
        """Stop relaying one GitHub App installation (managed relay). Cloud
        routing rows deleted best-effort, local profile removed, gateway
        hot-reloaded."""
        return await manager.disconnect_github_installation(installation_id)

    @app.get("/v1/connectors/github/status")
    async def github_status() -> dict[str, Any]:
        """GitHub health: relay socket / cloud sign-in / per-installation tokens."""
        return manager.github_status()

    @app.post("/v1/connectors/gmail/accounts/{email}/disconnect")
    async def gmail_account_disconnect(email: str) -> dict[str, Any]:
        """Drop ONE mailbox (cloud metadata best-effort first, like a full
        disconnect); the default pointer moves to the next account."""
        from .. import cloud
        from ..config import load_config
        from ..connectors import gmail_accounts

        profile_key = gmail_accounts.PREFIX + email.strip().lower()
        await asyncio.to_thread(
            lambda: cloud.cloud_disconnect(
                manager.secrets, load_config(), "gmail", profile_key=profile_key
            )
        )
        return gmail_accounts.disconnect_account(manager.secrets, email)

    @app.post("/v1/connectors/gmail/accounts/{email}/default")
    def gmail_account_default(email: str) -> dict[str, Any]:
        from ..connectors import gmail_accounts

        return gmail_accounts.set_default(manager.secrets, email)

    @app.patch("/v1/connectors/gmail/filters")
    def gmail_filters(body: dict) -> dict[str, Any]:
        """Replace the "Never show agents" lists. Enforced in the local tool
        layer; agents see silent omissions, the user sees counts + audit."""
        from ..connectors import gmail_accounts

        senders = body.get("senders") if isinstance(body, dict) else None
        labels = body.get("labels") if isinstance(body, dict) else None
        if senders is not None and not isinstance(senders, list):
            return {"ok": False, "error": "senders must be a list"}
        if labels is not None and not isinstance(labels, list):
            return {"ok": False, "error": "labels must be a list"}
        return gmail_accounts.set_filters(manager.secrets, senders, labels)

    @app.post("/v1/connectors/google_calendar/accounts/{email}/disconnect")
    async def gcal_account_disconnect(email: str) -> dict[str, Any]:
        """Drop ONE Google Calendar account (cloud metadata best-effort first);
        the default pointer moves to the next account."""
        from .. import cloud
        from ..config import load_config
        from ..connectors import gcal_accounts

        profile_key = gcal_accounts.PREFIX + email.strip().lower()
        await asyncio.to_thread(
            lambda: cloud.cloud_disconnect(
                manager.secrets,
                load_config(),
                "google_calendar",
                profile_key=profile_key,
            )
        )
        return gcal_accounts.disconnect_account(manager.secrets, email)

    @app.post("/v1/connectors/google_calendar/accounts/{email}/default")
    def gcal_account_default(email: str) -> dict[str, Any]:
        from ..connectors import gcal_accounts

        return gcal_accounts.set_default(manager.secrets, email)

    @app.post("/v1/connectors/hubspot/portals/{hub_id}/disconnect")
    async def hubspot_portal_disconnect(hub_id: str) -> dict[str, Any]:
        from .. import cloud
        from ..config import load_config
        from ..connectors import hubspot_portals

        profile_key = hubspot_portals.PREFIX + hub_id.strip()
        await asyncio.to_thread(
            lambda: cloud.cloud_disconnect(
                manager.secrets, load_config(), "hubspot", profile_key=profile_key
            )
        )
        return hubspot_portals.disconnect_portal(manager.secrets, hub_id)

    @app.post("/v1/connectors/hubspot/portals/{hub_id}/default")
    def hubspot_portal_default(hub_id: str) -> dict[str, Any]:
        from ..connectors import hubspot_portals

        return hubspot_portals.set_default(manager.secrets, hub_id)

    @app.post("/v1/connectors/{name}/accounts/{account_id}/disconnect")
    async def account_disconnect(name: str, account_id: str) -> dict[str, Any]:
        """Generic per-account disconnect for account-patterned connectors
        (batch 2+). Gmail/Calendar keep their specific email routes."""
        from .. import cloud
        from ..config import load_config
        from ..connectors import accounts

        if not accounts.is_account_connector(name):
            return {"ok": False, "error": "not a multi-account connector"}
        _id, profile_key, profile = accounts.resolve(manager.secrets, name, account_id)
        if profile and profile.get("managed"):
            await asyncio.to_thread(
                lambda: cloud.cloud_disconnect(
                    manager.secrets, load_config(), name, profile_key=profile_key
                )
            )
        return accounts.disconnect_account(manager.secrets, name, account_id)

    @app.post("/v1/connectors/{name}/accounts/{account_id}/default")
    def account_default(name: str, account_id: str) -> dict[str, Any]:
        from ..connectors import accounts

        if not accounts.is_account_connector(name):
            return {"ok": False, "error": "not a multi-account connector"}
        return accounts.set_default(manager.secrets, name, account_id)

    @app.patch("/v1/connectors/hubspot/hidden-fields")
    def hubspot_hidden_fields(body: dict) -> dict[str, Any]:
        """Replace the hidden-fields denylist (property names stripped from every
        record agents read — model-facing policy, not a human ACL)."""
        from ..connectors import hubspot_portals

        fields = body.get("hidden_fields") if isinstance(body, dict) else None
        if not isinstance(fields, list):
            return {"ok": False, "error": "hidden_fields must be a list"}
        return hubspot_portals.set_hidden_fields(manager.secrets, fields)

    @app.post("/v1/connectors/{name}/unauthorized/{item_id}")
    async def connector_unauthorized_resolve(
        name: str, item_id: str, body: dict
    ) -> dict[str, Any]:
        # Resolve a parked unauthorized message: dismiss / allow / allow_deliver (§19).
        action = str((body or {}).get("action", "")).strip()
        return await manager.resolve_unauthorized(name, item_id, action)

    # -- OpenWorker Cloud: sign-in + managed one-click connect ---------------
    # All optional: the app is fully functional signed out (manual token paste
    # stays available for every connector, before and after sign-in).

    @app.get("/v1/cloud/status")
    def cloud_status() -> dict[str, Any]:
        from .. import cloud

        return {
            **cloud.status(manager.secrets),
            "telemetry_enabled": cloud.telemetry_enabled(manager.secrets),
        }

    @app.post("/v1/cloud/telemetry")
    def cloud_telemetry(body: dict) -> dict[str, Any]:
        """The Phase 5 opt-out toggle. Local preference only — signed-out users
        send nothing regardless of this value."""
        from .. import cloud

        return cloud.set_telemetry_enabled(
            manager.secrets, bool((body or {}).get("enabled", True))
        )

    @app.post("/v1/cloud/login")
    def cloud_login() -> dict[str, Any]:
        """Start browser sign-in. The sidecar opens the system browser itself
        (works identically under Tauri and plain-browser dev)."""
        import webbrowser

        from .. import cloud
        from ..config import load_config

        out = cloud.begin_login(load_config())
        webbrowser.open(out["authorize_url"])
        return {"ok": True, "authorize_url": out["authorize_url"]}

    @app.post("/v1/cloud/logout")
    def cloud_logout() -> dict[str, Any]:
        from .. import cloud

        return cloud.logout(manager.secrets)

    @app.get("/auth/callback")
    async def cloud_auth_callback(
        request: Request,
        code: str = "",
        state: str = "",
        error: str = "",
    ):
        if auth_module is not None:
            try:
                return await auth_module.callback(request)
            except Exception as exc:
                # Authorization codes are one-time use. Some email clients and
                # in-app browsers immediately replay the callback after the
                # first request has already issued this browser a session.
                # Keep the authenticated session and return home rather than
                # replacing a successful login with an opaque error page.
                if auth_module.resolve(request.cookies.get(SESSION_COOKIE)):
                    return RedirectResponse("/")
                # Fail closed: never accept a callback whose state/token could
                # not be verified.  Clear the short-lived OIDC flow cookie so
                # the next login starts from a clean state, then return to the
                # product shell instead of exposing a raw API error page.
                request.session.clear()
                logger.warning(
                    "Hosted login callback failed (%s)",
                    type(exc).__name__,
                )
                return RedirectResponse("/?auth_error=login_failed")
        from fastapi.responses import HTMLResponse

        from .. import cloud
        from ..config import load_config

        signin_failed_detail = (
            "Close this tab and try signing in again from OpenWorker."
        )
        if error:
            return HTMLResponse(
                _browser_page(
                    "Sign-in failed", signin_failed_detail, ok=False, error=error
                ),
                status_code=400,
            )
        result = await asyncio.to_thread(
            lambda: cloud.complete_login(manager.secrets, load_config(), code, state)
        )
        if not result.get("ok"):
            return HTMLResponse(
                _browser_page(
                    "Sign-in failed",
                    signin_failed_detail,
                    ok=False,
                    error=result.get("error", ""),
                ),
                status_code=400,
            )

        # Restore managed connections in the background: best-effort metadata work
        # that must not hold the "Signed in" page (or the GUI's signed-in flip)
        # hostage to another broker round trip. Restored GitHub installs hot-add
        # the gateway so the relay connects without a restart.
        async def _restore_connections() -> None:
            try:
                out = await asyncio.to_thread(
                    lambda: cloud.sync_connections(manager.secrets, load_config())
                )
                if out.get("restored"):
                    await manager.refresh_gateway()
            except Exception:
                pass  # sign-in stands; the user can still connect by hand

        asyncio.get_running_loop().create_task(_restore_connections())
        return HTMLResponse(
            _browser_page(
                "Signed in",
                "You're signed in to OpenWorker Cloud. "
                "You can close this tab and return to OpenWorker.",
            )
        )

    @app.post("/v1/connectors/{name}/connect-managed")
    async def connector_connect_managed(
        name: str, body: Optional[dict] = None
    ) -> dict[str, Any]:
        """One-click managed OAuth (requires cloud sign-in). Opens the provider
        consent page in the system browser; the broker's callback page will
        form-POST the tokens to /oauth/callback below. `access` picks a consent
        tier by NAME (e.g. hubspot read | write) — the broker owns the scopes."""
        import webbrowser

        from .. import cloud
        from ..config import load_config
        from ..connectors.descriptors import get_descriptor

        d = get_descriptor(name)
        if d is not None and d.managed_paused:
            # GUI shows the Coming-soon state; this guard covers stale GUIs/API callers.
            return {
                "ok": False,
                "error": f"one-click connect for {d.title} is coming soon — connect manually for now",
            }
        access = str((body or {}).get("access") or "")
        flow = str((body or {}).get("flow") or "")  # github: "" install | "authorize"
        out = await asyncio.to_thread(
            lambda: cloud.begin_managed_connect(
                manager.secrets, load_config(), name, access=access, flow=flow
            )
        )
        if out.get("ok"):
            webbrowser.open(out["authorize_url"])
        return out

    @app.post("/oauth/callback")
    async def managed_oauth_callback(request: Request) -> Any:
        from fastapi.responses import HTMLResponse

        from .. import cloud
        from ..connectors.setup import (
            managed_connect_connector,
            managed_connect_slack_install,
        )

        form = await request.form()
        data = {k: str(v) for k, v in form.items()}
        connector = data.get("connector", "")
        if not cloud.consume_managed_state(data.get("app_state", "")):
            return HTMLResponse(
                _browser_page(
                    "Connection failed",
                    _CONNECT_FAILED_DETAIL,
                    ok=False,
                    error="unknown or expired connection attempt",
                ),
                status_code=400,
            )
        if data.get("error"):
            return HTMLResponse(
                _browser_page(
                    "Connection failed",
                    _CONNECT_FAILED_DETAIL,
                    ok=False,
                    error=data["error"],
                ),
                status_code=400,
            )
        # Managed GitHub deliberately carries NO token fields — the loopback POST
        # is routing metadata only (installation tokens are minted on demand,
        # github-relay-spec §4) — so its branch precedes the access_token check.
        if connector == "github" and data.get("installation_id"):
            from ..connectors.github_installs import managed_connect_install

            result = managed_connect_install(manager.secrets, data)
            if result.get("ok"):
                await manager.refresh_gateway()  # hot-add, like a workspace
            if not result.get("ok"):
                return HTMLResponse(
                    _browser_page(
                        "Connection failed",
                        _CONNECT_FAILED_DETAIL,
                        ok=False,
                        error=result.get("error", ""),
                    ),
                    status_code=400,
                )
            return HTMLResponse(
                _browser_page(
                    "GitHub connected",
                    "You can close this tab and return to OpenWorker.",
                    connector="github",
                )
            )
        if not connector or not data.get("access_token"):
            return HTMLResponse(
                _browser_page(
                    "Connection failed",
                    _CONNECT_FAILED_DETAIL,
                    ok=False,
                    error="missing fields",
                ),
                status_code=400,
            )
        # Managed Slack is multi-workspace + relay: store the per-team bot token
        # and flip to relay mode, rather than the single-token connector path.
        if connector == "slack" and data.get("team_id"):
            result = managed_connect_slack_install(manager.secrets, data)
            if result.get("ok"):
                # Hot-add: rebuild the gateway so the new workspace's token loads
                # (and the relay socket opens on a first-ever install) right away.
                await manager.refresh_gateway()
        elif connector == "gmail":
            # Multi-account: each sign-in lands in its own gmail:account:<email>
            # profile; the first becomes the default mailbox.
            from ..connectors import gmail_accounts

            result = gmail_accounts.managed_connect_account(
                manager.secrets, cloud.managed_profile_from_callback(data)
            )
        elif connector == "google_calendar":
            # Multi-account, same shape as gmail: google_calendar:account:<email>.
            from ..connectors import gcal_accounts

            result = gcal_accounts.managed_connect_account(
                manager.secrets, cloud.managed_profile_from_callback(data)
            )
        elif connector == "hubspot" and data.get("hub_id"):
            # Multi-portal: keyed by hub_id (broker sends it like Slack's team_id).
            from ..connectors import hubspot_portals

            profile = cloud.managed_profile_from_callback(data)
            profile["hub_id"] = data.get("hub_id", "")
            if data.get("sandbox"):
                profile["sandbox"] = True
            result = hubspot_portals.managed_connect_portal(manager.secrets, profile)
        else:
            result = managed_connect_connector(
                manager.secrets, connector, cloud.managed_profile_from_callback(data)
            )
        if not result.get("ok"):
            return HTMLResponse(
                _browser_page(
                    "Connection failed",
                    _CONNECT_FAILED_DETAIL,
                    ok=False,
                    error=result.get("error", ""),
                ),
                status_code=400,
            )
        return HTMLResponse(
            _browser_page(
                f"{_connector_title(connector)} connected",
                "You can close this tab and return to OpenWorker.",
                connector=connector,
            )
        )

    @app.patch("/v1/connectors/{name}/tools")
    def connector_tools_patch(name: str, body: dict) -> dict[str, Any]:
        enabled = (body or {}).get("enabled")
        if not isinstance(enabled, dict):
            return {"ok": False, "error": "enabled map required"}
        return manager.update_connector_tools(name, enabled)

    @app.post("/v1/connectors/{name}/allow")
    def connector_allow(name: str, body: dict) -> dict[str, Any]:
        # `team_id` scopes the edit to one workspace (managed relay); absent → flat list.
        # `name` (optional) seeds the people directory so a directory-picked user's
        # chip shows their display name before they've ever sent a message.
        return manager.allow_user(
            name,
            str(body.get("user_id", "")),
            str(body.get("team_id", "")) or None,
            display_name=str(body.get("name", "")),
        )

    @app.get("/v1/connectors/slack/workspaces/{team_id}/directory")
    async def slack_directory(
        team_id: str, q: str = "", limit: int = 25
    ) -> dict[str, Any]:
        """Workspace member roster for the people picker (team_id "default" =
        the manual Socket-Mode workspace). Cached locally; never leaves this machine."""
        from ..connectors import slack_directory as roster

        return await asyncio.to_thread(
            lambda: roster.list_members(manager.secrets, team_id, q, limit)
        )

    @app.get("/v1/connectors/slack/workspaces/{team_id}/channels")
    async def slack_channels(
        team_id: str, q: str = "", limit: int = 25
    ) -> dict[str, Any]:
        """Channel roster for the channel typeahead: all public channels, private
        ones only where the bot is a member (Slack API constraint)."""
        from ..connectors import slack_directory as roster

        return await asyncio.to_thread(
            lambda: roster.list_channels(manager.secrets, team_id, q, limit)
        )

    @app.post("/v1/connectors/{name}/disallow")
    def connector_disallow(name: str, body: dict) -> dict[str, Any]:
        return manager.disallow_user(
            name, str(body.get("user_id", "")), str(body.get("team_id", "")) or None
        )

    @app.post("/v1/connectors/slack/approval-owners/add")
    def slack_approval_owner_add(body: dict) -> dict[str, Any]:
        return manager.set_slack_approval_owner(
            str(body.get("user_id", "")),
            add=True,
            display_name=str(body.get("name", "")),
        )

    @app.post("/v1/connectors/slack/approval-owners/remove")
    def slack_approval_owner_remove(body: dict) -> dict[str, Any]:
        return manager.set_slack_approval_owner(
            str(body.get("user_id", "")), add=False
        )

    # -- audit / browser observability ------------------------------------------
    @app.get("/v1/audit")
    def audit_list(
        limit: int = 100,
        session_id: str | None = None,
        connector: str | None = None,
        tool: str | None = None,
    ) -> dict[str, Any]:
        return {
            "events": manager.list_audit(
                limit=limit, session_id=session_id, connector=connector, tool=tool
            )
        }

    @app.get("/v1/browser/state")
    def browser_state_get() -> dict[str, Any]:
        return manager.browser_state()

    @app.post("/v1/browser/screenshot")
    def browser_screenshot_post() -> dict[str, Any]:
        return manager.browser_screenshot()

    @app.post("/v1/browser/close")
    def browser_close_post() -> dict[str, Any]:
        return manager.browser_close()

    # -- web search -------------------------------------------------------------
    @app.get("/v1/web-search")
    def web_search_get() -> dict[str, Any]:
        return manager.get_web_search()

    @app.post("/v1/web-search")
    def web_search_set(body: dict) -> dict[str, Any]:
        provider = (body or {}).get("provider", "")
        if not provider:
            return {"ok": False, "error": "provider required"}
        return manager.set_web_search(provider, (body or {}).get("api_key"))

    # -- model providers (OpenAI, Ollama, …) ------------------------------------
    @app.get("/v1/providers")
    def providers_get() -> list[dict[str, Any]]:
        return manager.get_providers()

    @app.post("/v1/providers")
    def providers_set(body: dict) -> dict[str, Any]:
        name = (body or {}).get("name", "")
        if not name:
            return {"ok": False, "error": "name required"}
        from .cloud_security import validate_provider
        try:
            validate_provider(name, (body or {}).get("fields"))
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=403)
        return manager.set_provider(name, (body or {}).get("fields"))

    @app.delete("/v1/providers/{name}")
    def providers_remove(name: str) -> dict[str, Any]:
        return manager.remove_provider(name)

    @app.post("/v1/providers/verify")
    async def providers_verify(body: dict) -> dict[str, Any]:
        # Live read-only credential check (sync httpx) — run off the event loop.
        name = (body or {}).get("name", "") or "openai"
        from .cloud_security import validate_provider
        try:
            validate_provider(name, (body or {}).get("fields"))
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=403)
        return await asyncio.to_thread(
            manager.verify_provider, name, (body or {}).get("fields")
        )

    # -- settings (model API key) -----------------------------------------------
    @app.get("/v1/settings")
    def settings_get() -> dict[str, Any]:
        return manager.get_settings()

    @app.get("/v1/settings/voice-provider")
    def settings_voice_provider_get() -> dict[str, Any]:
        return manager.get_voice_provider()

    @app.post("/v1/settings/voice-provider")
    def settings_voice_provider_set(
        body: Any = Body(None),
    ) -> dict[str, Any]:
        return manager.set_voice_provider(body)

    @app.delete("/v1/settings/voice-provider")
    def settings_voice_provider_delete() -> dict[str, Any]:
        return manager.remove_voice_provider()

    @app.post("/v1/settings/model-key")
    def settings_set_model_key(body: dict) -> dict[str, Any]:
        return manager.set_model_key((body or {}).get("api_key", ""))

    @app.post("/v1/settings/default-model")
    def settings_set_default_model(body: dict) -> dict[str, Any]:
        return manager.set_default_model((body or {}).get("model", ""))

    @app.post("/v1/settings/models/add")
    def settings_models_add(body: dict) -> dict[str, Any]:
        return manager.add_model((body or {}).get("model", ""))

    @app.post("/v1/settings/models/remove")
    def settings_models_remove(body: dict) -> dict[str, Any]:
        return manager.remove_model((body or {}).get("model", ""))

    @app.post("/v1/settings/onboarded")
    def settings_set_onboarded(body: dict) -> dict[str, Any]:
        return manager.set_onboarded(bool((body or {}).get("value", True)))

    @app.post("/v1/settings/experimental-connectors")
    def settings_set_experimental(body: dict) -> dict[str, Any]:
        return manager.set_experimental_connectors(bool((body or {}).get("value")))

    @app.post("/v1/settings/surfaces")
    def settings_set_surfaces(body: dict) -> dict[str, Any]:
        b = body or {}
        return manager.set_surfaces(chat=b.get("chat"), code=b.get("code"))

    @app.post("/v1/settings/scratch-base")
    def settings_set_scratch_base(body: dict) -> dict[str, Any]:
        return manager.set_scratch_base(str((body or {}).get("path", "")))

    @app.post("/v1/settings/nav-layout")
    def settings_set_nav_layout(body: dict) -> dict[str, Any]:
        return manager.set_nav_layout(str((body or {}).get("nav_layout", "")))

    @app.post("/v1/settings/sessions-peek")
    def settings_set_sessions_peek(body: dict) -> dict[str, Any]:
        # Sidebar: sessions shown per group before "Show more" (owner ask, 2026-07-03).
        return manager.set_sessions_peek((body or {}).get("sessions_peek", 5))

    @app.post("/v1/settings/context-bar")
    def settings_set_context_bar(body: dict) -> dict[str, Any]:
        # Composer: show the context-window fill bar, or just the popover (owner ask).
        return manager.set_context_bar((body or {}).get("context_bar", True))

    @app.post("/v1/settings/pdf")
    def settings_set_pdf(body: dict) -> dict[str, Any]:
        # Token savings (owner ask, 2026-07-17): fallback mode for models without native
        # PDF support + attach-time page/size thresholds.
        b = body or {}
        return manager.set_pdf_settings(
            fallback=b.get("pdf_fallback"),
            max_pages=b.get("pdf_max_pages"),
            max_mb=b.get("pdf_max_mb"),
        )

    @app.post("/v1/settings/compaction")
    def settings_set_compaction(body: dict) -> dict[str, Any]:
        # Auto-compaction overrides (OPE-27): threshold % of the context window, the
        # absolute token cap, and the summarizer-model pin ("" → session's own model).
        b = body or {}
        return manager.set_compaction_settings(
            threshold_pct=b.get("compaction_threshold_pct"),
            cap_tokens=b.get("compaction_cap_tokens"),
            model=b.get("compaction_model"),
        )

    @app.post("/v1/attachments/inspect-pdf")
    def attachments_inspect_pdf(body: dict) -> dict[str, Any]:
        # Attach-time page/size probe for the composer's threshold check. Local only.
        from ..pdf_support import inspect

        return inspect(str((body or {}).get("data_url", "")))

    # -- direct-message routing -------------------------------------------------
    @app.get("/v1/messaging/dm-route")
    def dm_route_get() -> dict[str, Any]:
        return {"dm_session": manager.dm_session()}

    @app.post("/v1/messaging/dm-route")
    def dm_route_set(body: dict) -> dict[str, Any]:
        # A falsy session_id clears the designation (DMs then park as unrouted).
        return manager.set_dm_session((body or {}).get("session_id", ""))

    if os.environ.get("COWORKER_DEBUG_INJECT") == "1":
        # Dev-only (env-gated, localhost): feed a message through the real inbound path so the
        # messaging stack can be exercised without a live bot connection. Not registered otherwise.
        @app.post("/v1/_debug/inject_inbound")
        async def debug_inject_inbound(body: dict) -> dict[str, Any]:
            from ..connectors.base import MessageEvent, SessionSource

            event = MessageEvent(
                text=str((body or {}).get("text", "")),
                source=SessionSource(
                    platform=str(body.get("platform", "slack")),
                    chat_id=str(body.get("chat_id", "C0BD7KZ1AH5")),
                    user_id=str(body.get("user_id", "U07JK68S4BH")),
                    user_name=str(body.get("user_name", "tester")),
                    chat_type=str(body.get("chat_type", "channel")),
                    chat_name=str(body.get("chat_name", "")) or None,
                    thread_id=str(body.get("thread_ts", "")) or None,
                    team_id=str(body.get("team_id", "")) or None,
                ),
                message_id=str(body.get("ts", "")) or None,
                # §31 mention router: the flag is normally computed from the raw Slack text
                # at mapping time; the injector sets it directly.
                mentions_me=bool(body.get("mentions_me")),
            )
            await manager._dispatch_inbound(event)
            return {"ok": True}

    # -- automations (scheduled tasks) ------------------------------------------
    @app.get("/v1/automations")
    def automations_list() -> dict[str, Any]:
        return manager.list_automations()

    @app.post("/v1/automations")
    def automations_create(body: dict) -> dict[str, Any]:
        return manager.create_automation(body or {})

    @app.get("/v1/automations/{task_id}")
    def automation_get(task_id: str) -> dict[str, Any]:
        return manager.get_automation(task_id)

    @app.patch("/v1/automations/{task_id}")
    def automation_update(task_id: str, body: dict) -> dict[str, Any]:
        return manager.update_automation(task_id, body or {})

    @app.delete("/v1/automations/{task_id}")
    def automation_delete(task_id: str) -> dict[str, Any]:
        return manager.delete_automation(task_id)

    @app.post("/v1/automations/{task_id}/seen")
    def automations_seen(task_id: str) -> dict[str, Any]:
        return manager.mark_automation_seen(task_id)

    @app.post("/v1/automations/{task_id}/run")
    def automation_run(task_id: str) -> dict[str, Any]:
        # Prepare a live manual run; the GUI opens the returned session and drives it.
        return manager.prepare_manual_run(task_id)

    @app.post("/v1/automations/{task_id}/runs/{run_id}/finalize")
    def automation_run_finalize(task_id: str, run_id: str) -> dict[str, Any]:
        return manager.finalize_manual_run(task_id, run_id)

    @app.websocket("/ws/session/{session_id}")
    @_limited_socket
    async def ws_session(ws: WebSocket, session_id: str) -> None:
        # CORS never gates WebSockets, so a cross-site page could otherwise open this socket
        # and drive the session into tool calls. Reject a disallowed browser Origin before
        # accepting the handshake (1008 = policy violation).
        if not _origin_allowed(ws.headers.get("origin")):
            await ws.close(code=1008)
            return
        principal = _websocket_principal(ws)
        if principal is None:
            await ws.close(code=1008)
            return
        ws.state.principal = principal
        requested_agent = ws.query_params.get("agent") or "code"
        requested_workspace = ws.query_params.get("workspace") or ""
        alpha_workspace = alpha.workspace()
        if not alpha.permits_agent(requested_agent):
            await ws.close(code=1008)
            return
        if alpha.enabled() and (
            not alpha_workspace
            or Path(requested_workspace).expanduser().resolve()
            != Path(alpha_workspace).expanduser().resolve()
        ):
            await ws.close(code=1008)
            return
        manager_token = _activate_manager(principal)
        # Echo the openworker subprotocol whenever the client offered it: the proxied
        # browser (alpha/hosted) always offers ["openworker"] and a browser aborts a
        # handshake whose response selects no offered subprotocol — a tokenless local
        # dev backend used to break that mode after hosted auth landed.
        offered = [
            part.strip()
            for part in ws.headers.get("sec-websocket-protocol", "").split(",")
            if part.strip()
        ]
        await ws.accept(
            subprotocol=(
                "openworker"
                if auth_required or "openworker" in offered
                else None
            )
        )
        runtime_coordinator = manager.runtime_coordinator
        connection_id = uuid.uuid4().hex
        presence_task = asyncio.create_task(
            _presence_heartbeat(
                runtime_coordinator,
                principal.user_id,
                connection_id,
            )
        )
        agent = requested_agent

        # All four interactive prompts (approval / question / directory / plan) are parked as Inbox
        # items and awaited via inbox.wait — so they survive a dropped socket (redelivered on
        # reconnect) and can be resolved from any surface. `visibility` decides where they SHOW:
        # Unattended → the cross-session Inbox; attended → inline in this session only. The agent
        # stays blocked until the item is resolved (live WS response, REST, or a bound channel).
        def _visibility() -> str:
            return (
                VIS_INBOX
                if manager.unattended.is_unattended(session_id)
                else VIS_INLINE
            )

        async def _mirror(item) -> None:
            # Unattended items mirror to a bound channel as buttons (see mirror_inbox_item).
            await manager.mirror_inbox_item(item)

        def _route() -> str:
            return manager.inbox_routing.route_for(session_id, agent)

        async def approver(_request) -> ApprovalOutcome:
            # The engine has already emitted PERMISSION_REQUIRED (the live inline card). Park the
            # item so the answer can also come from the Inbox / a reconnect / after a restart.
            item = manager.inbox.add_approval(
                session_id,
                f"Run `{_request.tool_name}`?",
                body="\n".join(
                    p
                    for p in (
                        (getattr(_request, "reason", "") or "").strip(),
                        args_preview(getattr(_request, "arguments", None)),
                    )
                    if p
                ),
                inbox=_route(),
                visibility=_visibility(),
                # Automation-run context (manual "Run now" rides this socket): lets the
                # card offer the task-persistent "Allow every time" (§25). {} elsewhere.
                data=manager.approval_prompt_data(session_id, _request),
                tool_call_id=getattr(_request, "tool_call_id", None),
            )
            if (
                item.state == "pending"
            ):  # freshly raised (not a durable-resume re-raise)
                manager.persist_session(
                    session_id
                )  # the pending tool call is now on disk
                if item.visibility == VIS_INBOX:
                    await _mirror(item)
            resolution = await manager.inbox.wait(item.id)
            # Accept every vocabulary: the live card sends once/always_tool/always_command/
            # always_task/deny; the Inbox / a channel send allow/always/deny.
            return manager.approval_outcome(resolution, _request, session_id)

        async def question_asker(args: dict, tool_call_id=None) -> dict:
            # ask_user (engine does NOT emit the event — we do, only when attended).
            item = manager.inbox.add_question(
                session_id,
                str(args.get("question", "")),
                inbox=_route(),
                visibility=_visibility(),
                options=list(args.get("options") or []),
                allow_text=bool(args.get("allow_text", True)),
                multi=bool(args.get("multi", False)),
                tool_call_id=tool_call_id,
            )
            if item.state == "pending":
                manager.persist_session(session_id)
                if item.visibility == VIS_INBOX:
                    await _mirror(item)
                else:
                    await ws.send_json(
                        {
                            "type": "question_requested",
                            "data": {
                                "question": item.title,
                                "options": item.options,
                                "allow_text": item.allow_text,
                                "multi": item.multi,
                                "header": str(args.get("header", "")),
                            },
                        }
                    )
            return {"answer": await manager.inbox.wait(item.id)}

        async def directory_requester(args: dict, tool_call_id=None) -> dict:
            # The engine has already emitted DIRECTORY_REQUESTED. Park, await, then apply the grant.
            item = manager.inbox.add_directory(
                session_id,
                "Grant access to a folder?",
                body=str(args.get("reason", "")),
                inbox=_route(),
                visibility=_visibility(),
                data={
                    "path": str(args.get("path", "")),
                    "writable": bool(args.get("writable", False)),
                },
                tool_call_id=tool_call_id,
            )
            if item.state == "pending":
                manager.persist_session(session_id)
                if item.visibility == VIS_INBOX:
                    await _mirror(item)
            resp = _parse_json(
                await manager.inbox.wait(item.id)
            )  # {granted, path, writable}
            if not resp.get("granted"):
                return {"granted": False, "reason": "the user declined the request"}
            path = (resp.get("path") or args.get("path") or "").strip()
            if not path:
                return {"granted": False, "error": "no directory was provided"}
            writable = bool(resp.get("writable", args.get("writable", False)))
            res = manager.add_root(session_id, path, writable)
            if not res.get("ok"):
                return {
                    "granted": False,
                    "error": res.get("error", "could not grant access"),
                }
            primary = next(
                (
                    r
                    for r in res.get("roots", [])
                    if r.get("path")
                    and Path(r["path"]).expanduser().resolve()
                    == Path(path).expanduser().resolve()
                ),
                None,
            )
            return {
                "granted": True,
                "path": (primary or {}).get("path", path),
                "writable": writable,
            }

        async def plan_approver(_args: dict, tool_call_id=None) -> dict:
            # The engine has already emitted PLAN_PROPOSED. Park, await the verdict.
            item = manager.inbox.add_plan(
                session_id,
                "Approve the plan?",
                body=str(_args.get("plan", "")),
                inbox=_route(),
                visibility=_visibility(),
                tool_call_id=tool_call_id,
            )
            if item.state == "pending":
                manager.persist_session(session_id)
                if item.visibility == VIS_INBOX:
                    await _mirror(item)
            resp = _parse_json(
                await manager.inbox.wait(item.id)
            )  # {approved, mode, feedback}
            if not resp.get("approved"):
                return {
                    "approved": False,
                    "feedback": resp.get("feedback") or "the user rejected the plan",
                }
            return {"approved": True, "mode": resp.get("mode") or "interactive"}

        async def _apply_model(model: Optional[str]) -> None:
            # Mid-session rebind is allowed (roadmap item 3, supersedes the 2026-07-04
            # lock): history is canonical and providers convert per call. A real switch
            # appends a persisted notice; broadcast it so live views render the marker
            # and update their header. Never rebind mid-turn — the running loop reads
            # `engine.model` per iteration and a mixed turn is exactly the breakage the
            # old lock existed to prevent.
            if not model or manager.is_running(session_id):
                return
            notice = engine.switch_model(model)
            if notice is None:  # same model, or first bind on a fresh session
                return
            manager.persist_session(session_id)
            await manager.broadcast_session(
                session_id,
                {"type": "model_changed", "data": {"model": model, "text": notice}},
            )

        def _resolve_pending(resolution: str) -> None:
            # Live WS responses resolve THE session's single pending prompt (one at a time, since the
            # agent blocks). Reconnect / Inbox resolve by id via REST instead.
            pend = manager.inbox.pending(session_id)
            if pend:
                manager.inbox.resolve(pend[0].id, resolution)

        workspace = ws.query_params.get("workspace")
        mcp_tools = await manager.prepare_mcp_tools(
            session_id, workspace=workspace, agent=agent
        )
        engine = manager.get_engine(
            session_id,
            workspace=workspace,
            agent=agent,
            approver=approver,
            extra_tools=mcp_tools,
            directory_requester=directory_requester,
            plan_approver=plan_approver,
            question_asker=question_asker,
        )
        if engine is None:
            await ws.send_json(
                {
                    "type": "error",
                    "data": {
                        "error": "no valid workspace — choose a project folder first"
                    },
                }
            )
            await ws.close()
            return
        if alpha.enabled():
            # Restored interview placeholders historically defaulted to Interactive,
            # overriding configure_alpha. Start each cloud engine with the reviewed
            # Custom policy, never the unrestricted Auto policy. Keep an explicit
            # user choice for subsequent connections to this running engine.
            if not getattr(engine, "career_permission_initialized", False):
                engine.permissions.mode = Mode.CUSTOM
                engine.career_permission_initialized = True
            # Public alpha exposes only the explicit Career product workflow. Shell,
            # general file, connector, crawler, deletion, and newly added MCP tools stay
            # unavailable until deliberately reviewed and added to the allowlist.
            engine.registry.retain(alpha.conversation_tools())
            engine.permissions.allowed_commands.clear()
            engine.permissions.auto_allow_tools.clear()
            engine.permissions.session_allow_tools.clear()
            engine.permissions.session_allow_commands.clear()
            # BYOK usability: whitelisted read-only/interview tools run without an
            # approval card (Mode.CUSTOM honors this set); persisted-data writes
            # (import/confirm/tracking) are NOT in it and still ask. Re-seeded after
            # the clear above, intersected with what actually registered.
            engine.permissions.auto_allow_tools.update(
                alpha.AUTO_APPROVE_TOOLS & alpha.conversation_tools()
            )
        # Auto-compaction failure prompt (OPE-27): only an ATTENDED session may be asked
        # Retry/Trim — unattended runs auto-trim (the policy in engine._compact_now).
        engine.is_attended = lambda: _visibility() == VIS_INLINE
        await ws.send_json(
            {
                "type": "ready",
                "data": {
                    "session_id": session_id,
                    "agent": getattr(engine, "agent_name", "code"),
                    "model": engine.model,
                    "mode": engine.permissions.mode.value,
                    "workspace": (
                        str(getattr(engine, "executor").cwd)
                        if getattr(engine, "executor", None)
                        else None
                    ),
                    "command_trust": manager.workspace_command_trust(
                        str(getattr(engine, "audit_context", {}).get("workspace", ""))
                    ),
                },
            }
        )

        # Checkpoint events: persist mid-turn so a crash/quit can't eat the conversation.
        # turn_start = the user message just landed (a brand-new session gets its row here,
        # not at connect — empty never-used sessions shouldn't appear in Recents);
        # permission_required/directory_requested = parked indefinitely on the user;
        # iteration_end = a model response + its tool results completed.
        _CHECKPOINTS = {
            "turn_start",
            "permission_required",
            "directory_requested",
            "plan_proposed",
            "iteration_end",
        }

        async def run_turn(content, *, retry: bool = False, display=None) -> None:
            # The receive loop atomically claims this session before scheduling the task.
            # Keeping the claim outside prevents two back-to-back frames from both starting.
            try:
                events = (
                    engine.retry()
                    if retry
                    else engine.run(content, display=display)
                )
                async for event in events:
                    runtime_coordinator.renew_lease(
                        turn_lease_key,
                        connection_id,
                        _RUNTIME_TURN_LEASE_TTL_SECONDS,
                    )
                    # Broadcast to every socket viewing this session (this socket included — it's a
                    # registered client), so a second view of the same session stays in sync too.
                    event_data = event.data
                    if event.type.value == "error":
                        request_id = uuid.uuid4().hex
                        try:
                            await run_in_threadpool(
                                diagnostic_store.record, principal, request_id=request_id,
                                kind="provider_error", page="conversation", source="agent",
                            )
                        except Exception:
                            logger.warning("support_diagnostic_storage_unavailable")
                        event_data = {"error": "模型请求未完成，请重试或提交反馈。", "request_id": request_id}
                        if alpha.enabled() and engine.messages and engine.messages[-1].get("role") == "notice" and engine.messages[-1].get("kind") == "error":
                            engine.messages[-1]["text"] = event_data["error"]
                            engine.messages[-1]["request_id"] = request_id
                    await manager.broadcast_session(
                        session_id, {"type": event.type.value, "data": event_data}
                    )
                    if event.type.value in _CHECKPOINTS:
                        manager.save(session_id, engine)
            finally:
                if alpha.enabled():
                    cloud_budget.release("turn", principal.user_id)
                runtime_coordinator.release_lease(
                    turn_lease_key,
                    connection_id,
                )
                manager.mark_idle(session_id)
                manager.save(session_id, engine)
                await manager.broadcast_session(
                    session_id, {"type": "turn_done", "data": {}}
                )

        # This socket is now a live view of the session; background turns (channel delivery,
        # self-wake, durable resume) broadcast here too, not just locally driven run_turns.
        manager.register_session_client(session_id, ws.send_json)
        turn_lease_key = (
            f"session-turn:{principal.user_id}:{session_id}"
        )
        inbound_times: deque[float] = deque()

        async def reject_input(reason: str) -> None:
            # Input validation failures are not provider failures and must not offer "Retry"
            # or flush an in-progress assistant stream in the GUI.
            await ws.send_json({"type": "input_rejected", "data": {"error": reason}})

        async def claim_turn(*, retry: bool = False, content=None, display=None) -> None:
            if not _acquire_turn_lease(
                runtime_coordinator,
                key=turn_lease_key,
                user_id=principal.user_id,
                owner=connection_id,
                ttl_seconds=_RUNTIME_TURN_LEASE_TTL_SECONDS,
            ):
                await reject_input(
                    "This session is already running a turn. Wait for it to finish or stop it."
                )
                return
            if not manager.try_mark_running(session_id):
                runtime_coordinator.release_lease(
                    turn_lease_key,
                    connection_id,
                )
                await reject_input(
                    "This session is already running a turn. Wait for it to finish or stop it."
                )
                return
            if alpha.enabled() and not cloud_budget.acquire("turn", principal.user_id):
                logger.warning("cloud_security_refusal category=turn_capacity")
                runtime_coordinator.release_lease(turn_lease_key, connection_id)
                manager.mark_idle(session_id)
                await reject_input("The server is busy. Please wait before starting another conversation.")
                return
            asyncio.create_task(run_turn(content, retry=retry, display=display))

        try:
            while True:
                try:
                    message = await ws.receive_json()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    await reject_input("Invalid WebSocket message: expected JSON.")
                    continue

                now = asyncio.get_running_loop().time()
                while (
                    inbound_times
                    and now - inbound_times[0] > _WS_RATE_LIMIT_WINDOW_SECONDS
                ):
                    inbound_times.popleft()
                if len(inbound_times) >= _WS_RATE_LIMIT_COUNT:
                    await reject_input("Too many WebSocket messages; reconnect and try again.")
                    await ws.close(code=1008)
                    return
                inbound_times.append(now)

                if not isinstance(message, dict):
                    await reject_input("Invalid WebSocket message: expected an object.")
                    continue
                kind = message.get("type")
                if not isinstance(kind, str):
                    await reject_input("Invalid WebSocket message: missing string type.")
                    continue
                if kind == "approval":
                    _resolve_pending(message.get("decision", "deny"))
                elif kind == "directory_response":
                    _resolve_pending(
                        json.dumps(
                            {
                                "granted": bool(message.get("granted")),
                                "path": message.get("path", ""),
                                "writable": bool(message.get("writable", False)),
                            }
                        )
                    )
                elif kind == "plan_response":
                    _resolve_pending(
                        json.dumps(
                            {
                                "approved": bool(message.get("approved")),
                                "mode": message.get("mode", "interactive"),
                                "feedback": message.get("feedback", ""),
                            }
                        )
                    )
                elif kind == "question_response":
                    _resolve_pending(str(message.get("answer", "")))
                elif kind == "interrupt":
                    engine.request_interrupt()
                elif kind == "retry":
                    # Re-run after a provider error (engine guards on the error-notice
                    # tail, so a stray frame is a no-op that still ends with turn_done).
                    await claim_turn(retry=True)
                elif kind == "set_mode":
                    try:
                        requested_mode = Mode(message.get("mode"))
                        if alpha.enabled() and requested_mode not in {
                            Mode.CUSTOM, Mode.INTERACTIVE,
                        }:
                            requested_mode = Mode.CUSTOM
                        engine.permissions.mode = requested_mode
                    except (TypeError, ValueError):
                        pass
                elif kind == "set_model":
                    model = message.get("model")
                    if model is not None and not isinstance(model, str):
                        await reject_input("Invalid model: expected a string.")
                    else:
                        await _apply_model(model)
                elif kind == "user_message":
                    raw_text = message.get("text")
                    if raw_text is None:
                        raw_text = ""
                    if not isinstance(raw_text, str):
                        await reject_input("Invalid message text: expected a string.")
                        continue
                    text = raw_text.strip()
                    raw_attachments = message.get("attachments")
                    attachments = [] if raw_attachments is None else raw_attachments
                    # Reject an oversized frame instead of buffering it into a turn. Send a
                    # visible error so the surface can tell the user, and drop the message.
                    if not isinstance(attachments, list):
                        await reject_input("Invalid attachments: expected a list.")
                        continue
                    reject = None
                    if len(text) > _MAX_MESSAGE_TEXT_CHARS:
                        reject = (
                            f"Message too long ({len(text)} chars; "
                            f"limit {_MAX_MESSAGE_TEXT_CHARS})."
                        )
                    elif len(attachments) > _MAX_ATTACHMENTS:
                        reject = (
                            f"Too many attachments ({len(attachments)}; "
                            f"limit {_MAX_ATTACHMENTS})."
                        )
                    elif any(not isinstance(a, dict) for a in attachments):
                        reject = "Invalid attachment: expected an object."
                    elif _json_value_size(attachments) > _MAX_ATTACHMENTS_BYTES:
                        reject = "Attachments too large (limit 15 MB per message)."
                    else:
                        for attachment in attachments:
                            attachment_kind = attachment.get("kind")
                            name = attachment.get("name")
                            mime = attachment.get("mime")
                            if attachment_kind not in {"image", "pdf", "text"}:
                                reject = "Invalid attachment kind."
                            elif name is not None and (
                                not isinstance(name, str) or len(name) > 1024
                            ):
                                reject = "Invalid attachment name."
                            elif mime is not None and (
                                not isinstance(mime, str) or len(mime) > 255
                            ):
                                reject = "Invalid attachment MIME type."
                            elif attachment_kind == "image":
                                data = attachment.get("data_url")
                                if (
                                    not isinstance(data, str)
                                    or not data.startswith("data:image/")
                                    or ";base64," not in data
                                    or len(data) > MAX_IMAGE_CHARS
                                ):
                                    reject = "Invalid or oversized image attachment."
                            elif attachment_kind == "pdf":
                                data = attachment.get("data_url")
                                if (
                                    not isinstance(data, str)
                                    or not data.startswith(
                                        "data:application/pdf;base64,"
                                    )
                                    or len(data) > MAX_PDF_CHARS
                                ):
                                    reject = "Invalid or oversized PDF attachment."
                            else:
                                body = attachment.get("text")
                                if (
                                    not isinstance(body, str)
                                    or len(body) > MAX_TEXT_CHARS
                                ):
                                    reject = "Invalid or oversized text attachment."
                            if reject is not None:
                                break
                    if reject is not None:
                        await reject_input(reject)
                        continue
                    # The composer sends its visible model with every message — the FIRST
                    # one binds the session (race-proof across reconnects; see api.ts
                    # Session.userMessage), later ones may switch it (notice persisted).
                    model = message.get("model")
                    if model is not None and not isinstance(model, str):
                        await reject_input("Invalid model: expected a string.")
                        continue
                    # Force-run (SKILLS-SPEC §4.1 #3): the composer's `/skill` pick rides as a
                    # separate field. Validated against the session's effective menu — a muted
                    # or unknown skill is a visible error, never a silent no-op (§4.6 #15).
                    # The model-facing framing goes into `content`; the transcript shows the
                    # user's literal "/name …" line via the `_display` sidecar (one bubble).
                    skill = message.get("skill")
                    display = None
                    raw_display = message.get("display")
                    if raw_display is not None and (
                        skill is None
                        or not isinstance(raw_display, str)
                        or not raw_display.strip()
                        or len(raw_display) > _MAX_MESSAGE_TEXT_CHARS
                    ):
                        await reject_input(
                            "Invalid display text for skill message."
                        )
                        continue
                    if skill is not None:
                        if not isinstance(skill, str) or not skill.strip():
                            await reject_input("Invalid skill: expected a name.")
                            continue
                        skill = skill.strip()
                        menu = manager.effective_skill_names(session_id, workspace)
                        if skill not in menu:
                            await reject_input(
                                f"Skill '{skill}' is not available in this session."
                            )
                            continue
                        display = (
                            raw_display.strip()
                            if raw_display is not None
                            else f"/{skill}" + (f" {text}" if text else "")
                        )
                        preloaded = manager.preload_skill_context(
                            session_id,
                            skill,
                            workspace,
                        )
                        if not preloaded.get("ok"):
                            await reject_input(
                                str(
                                    preloaded.get("error")
                                    or "Skill preload failed."
                                )
                            )
                            continue
                        text = (
                            f'Use the preloaded skill "{skill}" for this request. '
                            "Do not call load_skill for any preloaded skill.\n\n"
                            f'{preloaded["instructions"]}'
                            + (f"\n\n{text}" if text else "")
                        )
                    await _apply_model(model)
                    if text or attachments:
                        content = build_user_content(text, attachments)
                        await claim_turn(content=content, display=display)
                else:
                    await reject_input(f"Unknown WebSocket message type: {kind}.")
        except WebSocketDisconnect:
            pass
        finally:
            manager.unregister_session_client(session_id, ws.send_json)
            presence_task.cancel()
            runtime_coordinator.clear_presence(
                principal.user_id,
                connection_id,
            )
            _deactivate_manager(manager_token)

    @app.websocket("/ws/events")
    @_limited_socket
    async def ws_events(ws: WebSocket) -> None:
        """App-wide event stream (session-independent): the GUI keeps one open for
        pushes like automation_run_started (the UX-026 toast). Read-only — inbound
        frames are ignored; the receive loop just detects disconnect."""
        if not _origin_allowed(ws.headers.get("origin")):
            await ws.close(code=1008)
            return
        principal = _websocket_principal(ws)
        if principal is None:
            await ws.close(code=1008)
            return
        ws.state.principal = principal
        manager_token = _activate_manager(principal)
        # Echo the openworker subprotocol whenever the client offered it: the proxied
        # browser (alpha/hosted) always offers ["openworker"] and a browser aborts a
        # handshake whose response selects no offered subprotocol — a tokenless local
        # dev backend used to break that mode after hosted auth landed.
        offered = [
            part.strip()
            for part in ws.headers.get("sec-websocket-protocol", "").split(",")
            if part.strip()
        ]
        await ws.accept(
            subprotocol=(
                "openworker"
                if auth_required or "openworker" in offered
                else None
            )
        )
        runtime_coordinator = manager.runtime_coordinator
        connection_id = uuid.uuid4().hex
        presence_task = asyncio.create_task(
            _presence_heartbeat(
                runtime_coordinator,
                principal.user_id,
                connection_id,
            )
        )
        manager.register_event_client(ws.send_json)
        inbound_times: deque[float] = deque()
        try:
            while True:
                await ws.receive_text()
                if alpha.enabled():
                    now = asyncio.get_running_loop().time()
                    while inbound_times and now - inbound_times[0] > _WS_RATE_LIMIT_WINDOW_SECONDS:
                        inbound_times.popleft()
                    if len(inbound_times) >= _WS_RATE_LIMIT_COUNT:
                        logger.warning("cloud_security_refusal category=event_socket_rate")
                        await ws.close(code=1008)
                        return
                    inbound_times.append(now)
        except WebSocketDisconnect:
            pass
        finally:
            manager.unregister_event_client(ws.send_json)
            presence_task.cancel()
            runtime_coordinator.clear_presence(
                principal.user_id,
                connection_id,
            )
            _deactivate_manager(manager_token)

    return app


def _parse_json(s: str) -> dict[str, Any]:
    """Parse a structured Inbox resolution (directory/plan carry their reply as a JSON string)."""
    try:
        v = json.loads(s) if s else {}
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _openai_response(model: str, turn: AssistantTurn) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": turn.text or ""}
    if turn.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in turn.tool_calls
        ]
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12],
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": turn.finish_reason or "stop",
            }
        ],
    }
