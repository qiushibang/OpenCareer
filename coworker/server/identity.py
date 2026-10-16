"""Resolve transport credentials into an authenticated OpenCareer principal."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

LOCAL_USER = "local"
USER_TOKENS_ENV = "OPENCAR_USER_TOKENS"


@dataclass(frozen=True)
class Principal:
    user_id: str
    via: str


def _user_tokens() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for raw in os.environ.get(USER_TOKENS_ENV, "").split(","):
        user_id, separator, token = raw.strip().partition(":")
        if separator and user_id.strip() and token.strip():
            pairs.append((user_id.strip(), token.strip()))
    return tuple(pairs)


def _user_tokens_configured() -> bool:
    return bool(os.environ.get(USER_TOKENS_ENV, "").strip())


def resolve_principal(
    token: str | None,
    *,
    legacy_token: str,
) -> Principal | None:
    users = _user_tokens()
    if _user_tokens_configured():
        if not token:
            return None
        matched_users: set[str] = set()
        for user_id, expected in users:
            if secrets.compare_digest(token, expected):
                matched_users.add(user_id)
        if len(matched_users) == 1:
            return Principal(matched_users.pop(), "user-token")
        return None
    if legacy_token:
        if token and secrets.compare_digest(token, legacy_token):
            return Principal(LOCAL_USER, "legacy-token")
        return None
    return Principal(LOCAL_USER, "local")


def authentication_required(*, legacy_token: str) -> bool:
    return _user_tokens_configured() or bool(legacy_token)
