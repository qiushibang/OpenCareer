"""Authing OpenID Connect adapter for browser-hosted login."""

from __future__ import annotations

from base64 import urlsafe_b64encode
import secrets
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from .auth import CompletedIdentity, IdentityClaims, safe_return_to


def _hs256_jwk_set(client_secret: str) -> dict[str, list[dict[str, str]]]:
    """Represent Authing's default HS256 signing key without exposing it to clients.

    Authlib's OpenID Connect client otherwise always selects the provider JWKS,
    which only contains Authing's RSA public key. Authing signs ID Tokens with
    the app secret by default, so HS256 must use an in-process symmetric JWK.
    The result is passed only to Authlib and is never returned by this module.
    """
    encoded_secret = urlsafe_b64encode(client_secret.encode("utf-8"))
    return {
        "keys": [
            {
                "kty": "oct",
                "k": encoded_secret.rstrip(b"=").decode("ascii"),
                "alg": "HS256",
                "use": "sig",
            }
        ]
    }


class AuthingIdentityProvider:
    def __init__(
        self,
        *,
        issuer: str,
        client_id: str = "",
        client_secret: str = "",
        oauth_client: Any | None = None,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._oauth = None
        if oauth_client is not None:
            self._client = oauth_client
            return

        from authlib.integrations.starlette_client import OAuth

        self._oauth = OAuth()
        self._client = self._oauth.register(
            name="authing",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=(
                f"{self._issuer}/.well-known/openid-configuration"
            ),
            # Authing defaults to HS256 for ID Tokens. Keep the corresponding
            # key only in this server-side OAuth client so Authlib does not try
            # to verify an HMAC signature with the provider's RSA JWKS.
            jwks=_hs256_jwk_set(client_secret),
            client_kwargs={
                "scope": "openid profile email",
                "code_challenge_method": "S256",
            },
        )

    async def begin(
        self,
        request: Request,
        *,
        redirect_uri: str,
        return_to: str,
        force_login: bool = False,
    ) -> Response:
        request.session["opencar_return_to"] = safe_return_to(return_to)
        authorization_params = {"nonce": secrets.token_urlsafe(32)}
        if force_login:
            authorization_params["prompt"] = "login"
        return await self._client.authorize_redirect(
            request,
            redirect_uri,
            **authorization_params,
        )

    async def complete(self, request: Request) -> CompletedIdentity:
        token = await self._client.authorize_access_token(request)
        userinfo = token.get("userinfo") if hasattr(token, "get") else None
        if userinfo is None or not hasattr(userinfo, "get"):
            raise ValueError("Authing did not return OpenID user information")
        subject = str(userinfo.get("sub") or "").strip()
        if not subject:
            raise ValueError("Authing identity is missing a subject")
        email = str(userinfo.get("email") or "").strip() or None
        display_name = (
            str(userinfo.get("name") or userinfo.get("nickname") or "").strip()
            or None
        )
        return CompletedIdentity(
            claims=IdentityClaims(
                issuer=self._issuer,
                subject=subject,
                email=email,
                email_verified=userinfo.get("email_verified") is True,
                display_name=display_name,
            ),
            return_to=safe_return_to(
                request.session.pop("opencar_return_to", "/")
            ),
        )
