"""Hosted login orchestration behind a provider-neutral interface."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from .identity import Principal

SESSION_COOKIE = "opencar_session"


@dataclass(frozen=True)
class IdentityClaims:
    issuer: str
    subject: str
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None


@dataclass(frozen=True)
class CompletedIdentity:
    claims: IdentityClaims
    return_to: str = "/"


@dataclass(frozen=True)
class AuthSession:
    principal: Principal
    email: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class IssuedAuthSession:
    raw_token: str
    session: AuthSession


@dataclass(frozen=True)
class AuthSettings:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    state_secret: str
    cookie_secure: bool = True
    session_ttl_seconds: int = 7 * 24 * 60 * 60


_AUTH_ENV_NAMES = {
    "issuer": "OPENCAR_AUTH_ISSUER",
    "client_id": "OPENCAR_AUTH_CLIENT_ID",
    "client_secret": "OPENCAR_AUTH_CLIENT_SECRET",
    "redirect_uri": "OPENCAR_AUTH_REDIRECT_URI",
    "state_secret": "OPENCAR_AUTH_STATE_SECRET",
}


def load_auth_settings(
    environ: Mapping[str, str] | None = None,
) -> AuthSettings | None:
    """Load hosted-login configuration atomically and fail closed if partial."""
    values = os.environ if environ is None else environ
    required = {
        field: values.get(env_name, "").strip()
        for field, env_name in _AUTH_ENV_NAMES.items()
    }
    if not any(required.values()):
        return None
    missing = [
        env_name
        for field, env_name in _AUTH_ENV_NAMES.items()
        if not required[field]
    ]
    if missing:
        raise RuntimeError(
            "hosted login configuration is incomplete: " + ", ".join(missing)
        )

    issuer = urlsplit(required["issuer"])
    redirect = urlsplit(required["redirect_uri"])
    if (
        issuer.scheme != "https"
        or not issuer.netloc
        or issuer.query
        or issuer.fragment
    ):
        raise RuntimeError("OPENCAR_AUTH_ISSUER must be an HTTPS issuer URL")
    redirect_is_local = redirect.hostname in {"localhost", "127.0.0.1", "::1"}
    if not redirect.netloc or (
        redirect.scheme != "https"
        and not (redirect.scheme == "http" and redirect_is_local)
    ):
        raise RuntimeError(
            "OPENCAR_AUTH_REDIRECT_URI must use HTTPS (HTTP is local-only)"
        )
    if len(required["state_secret"]) < 32:
        raise RuntimeError("OPENCAR_AUTH_STATE_SECRET must be at least 32 characters")

    ttl_text = values.get("OPENCAR_AUTH_SESSION_TTL_SECONDS", "604800").strip()
    try:
        ttl = int(ttl_text)
    except ValueError as exc:
        raise RuntimeError(
            "OPENCAR_AUTH_SESSION_TTL_SECONDS must be an integer"
        ) from exc
    if not 300 <= ttl <= 30 * 24 * 60 * 60:
        raise RuntimeError(
            "OPENCAR_AUTH_SESSION_TTL_SECONDS must be between 300 and 2592000"
        )

    return AuthSettings(
        issuer=required["issuer"].rstrip("/"),
        client_id=required["client_id"],
        client_secret=required["client_secret"],
        redirect_uri=required["redirect_uri"],
        state_secret=required["state_secret"],
        cookie_secure=redirect.scheme == "https",
        session_ttl_seconds=ttl,
    )


class HostedIdentityProvider(Protocol):
    async def begin(
        self,
        request: Request,
        *,
        redirect_uri: str,
        return_to: str,
        force_login: bool = False,
    ) -> Response: ...

    async def complete(self, request: Request) -> CompletedIdentity: ...


class AuthSessionStore(Protocol):
    def issue(
        self,
        claims: IdentityClaims,
        *,
        ttl_seconds: int,
    ) -> IssuedAuthSession: ...

    def resolve(self, raw_token: str | None) -> AuthSession | None: ...

    def revoke(self, raw_token: str | None) -> None: ...


def safe_return_to(value: str | None) -> str:
    candidate = (value or "/").strip()
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
        or any(ord(character) < 32 for character in candidate)
    ):
        return "/"
    return candidate


class AuthModule:
    """Deep module for hosted login, local sessions, and cookie policy."""

    def __init__(
        self,
        provider: HostedIdentityProvider,
        sessions: AuthSessionStore,
        settings: AuthSettings,
    ) -> None:
        self._provider = provider
        self._sessions = sessions
        self.settings = settings

    @property
    def configured(self) -> bool:
        return True

    def resolve(self, raw_token: str | None) -> AuthSession | None:
        return self._sessions.resolve(raw_token)

    async def login(self, request: Request) -> Response:
        return await self._provider.begin(
            request,
            redirect_uri=self.settings.redirect_uri,
            return_to=safe_return_to(request.query_params.get("return_to")),
            force_login=request.query_params.get("prompt") == "login",
        )

    async def callback(self, request: Request) -> Response:
        completed = await self._provider.complete(request)
        issued = self._sessions.issue(
            completed.claims,
            ttl_seconds=self.settings.session_ttl_seconds,
        )
        response = RedirectResponse(safe_return_to(completed.return_to))
        response.set_cookie(
            SESSION_COOKIE,
            issued.raw_token,
            max_age=self.settings.session_ttl_seconds,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite="lax",
            path="/",
        )
        return response

    def logout(self, raw_token: str | None) -> Response:
        self._sessions.revoke(raw_token)
        response = JSONResponse({"ok": True})
        response.delete_cookie(
            SESSION_COOKIE,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite="lax",
            path="/",
        )
        return response
