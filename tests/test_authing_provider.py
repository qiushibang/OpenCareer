from __future__ import annotations

import time

import pytest
from fastapi import Request
from joserfc import jwt
from joserfc.jwk import OctKey

from coworker.server.auth import load_auth_settings, safe_return_to
from coworker.server.authing import AuthingIdentityProvider, _hs256_jwk_set


class _OAuthClient:
    def __init__(self) -> None:
        self.redirect_kwargs = None

    async def authorize_redirect(self, request, redirect_uri: str, **kwargs):
        from fastapi.responses import RedirectResponse

        self.redirect_kwargs = (redirect_uri, kwargs)
        return RedirectResponse("https://tenant.authing.cn/oidc/auth")

    async def authorize_access_token(self, request):
        return {
            "userinfo": {
                "sub": "authing-subject",
                "email": "alice@example.com",
                "email_verified": True,
                "name": "Alice",
            }
        }


def _request(path: str = "/auth/login") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "scheme": "https",
        "server": ("app.opencareer.online", 443),
        "client": ("127.0.0.1", 1234),
        "session": {},
    }
    return Request(scope)


def _environment() -> dict[str, str]:
    return {
        "OPENCAR_AUTH_ISSUER": "https://tenant.authing.cn/oidc/",
        "OPENCAR_AUTH_CLIENT_ID": "client-id",
        "OPENCAR_AUTH_CLIENT_SECRET": "client-secret",
        "OPENCAR_AUTH_REDIRECT_URI": (
            "https://app.opencareer.online/_openworker/auth/callback"
        ),
        "OPENCAR_AUTH_STATE_SECRET": "state-secret-with-at-least-32-characters",
    }


def test_auth_settings_are_atomic_and_https_only() -> None:
    assert load_auth_settings({}) is None

    with pytest.raises(RuntimeError, match="incomplete"):
        load_auth_settings({"OPENCAR_AUTH_CLIENT_ID": "client-id"})

    insecure = _environment()
    insecure["OPENCAR_AUTH_REDIRECT_URI"] = "http://app.opencareer.online/callback"
    with pytest.raises(RuntimeError, match="HTTPS"):
        load_auth_settings(insecure)

    settings = load_auth_settings(_environment())
    assert settings is not None
    assert settings.issuer == "https://tenant.authing.cn/oidc"
    assert settings.cookie_secure is True
    assert settings.session_ttl_seconds == 604800


def test_authing_hs256_jwk_set_uses_the_server_side_client_secret() -> None:
    jwk_set = _hs256_jwk_set("client-secret")

    assert jwk_set == {
        "keys": [
            {
                "kty": "oct",
                "k": "Y2xpZW50LXNlY3JldA",
                "alg": "HS256",
                "use": "sig",
            }
        ]
    }


def test_authing_provider_registers_its_hs256_key_with_authlib() -> None:
    provider = AuthingIdentityProvider(
        issuer="https://tenant.authing.cn/oidc",
        client_id="client-id",
        client_secret="client-secret",
    )

    assert provider._client.server_metadata["jwks"] == _hs256_jwk_set(
        "client-secret"
    )


@pytest.mark.asyncio
async def test_authing_provider_validates_an_authing_default_hs256_id_token() -> None:
    secret = "a-server-only-secret-that-is-long-enough"
    issuer = "https://tenant.authing.cn/oidc"
    provider = AuthingIdentityProvider(
        issuer=issuer,
        client_id="client-id",
        client_secret=secret,
    )
    provider._client.server_metadata.update(
        {
            "issuer": issuer,
            "_loaded_at": time.time(),
            "id_token_signing_alg_values_supported": ["HS256"],
        }
    )
    id_token = jwt.encode(
        {"alg": "HS256"},
        {
            "iss": issuer,
            "sub": "authing-subject",
            "aud": "client-id",
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
            "nonce": "expected-nonce",
        },
        OctKey.import_key(secret.encode("utf-8")),
    )

    claims = await provider._client.parse_id_token(
        {"id_token": id_token},
        nonce="expected-nonce",
    )

    assert claims["sub"] == "authing-subject"


def test_return_path_cannot_escape_the_opencareer_origin() -> None:
    assert safe_return_to("/career/jobs?tab=favorites") == (
        "/career/jobs?tab=favorites"
    )
    assert safe_return_to("https://evil.example/steal") == "/"
    assert safe_return_to("//evil.example/steal") == "/"
    assert safe_return_to("/career\\evil") == "/"
    assert safe_return_to("/career\nX-Injected: value") == "/"


@pytest.mark.asyncio
async def test_authing_provider_preserves_return_path_and_maps_verified_claims() -> None:
    client = _OAuthClient()
    provider = AuthingIdentityProvider(
        issuer="https://tenant.authing.cn/oidc",
        oauth_client=client,
    )
    request = _request()

    response = await provider.begin(
        request,
        redirect_uri="https://app.opencareer.online/_openworker/auth/callback",
        return_to="/career/jobs",
        force_login=True,
    )

    assert response.status_code == 307
    assert request.session["opencar_return_to"] == "/career/jobs"
    assert client.redirect_kwargs is not None
    _, redirect_kwargs = client.redirect_kwargs
    assert redirect_kwargs["nonce"]
    assert redirect_kwargs["prompt"] == "login"

    completed = await provider.complete(request)
    assert completed.return_to == "/career/jobs"
    assert completed.claims.issuer == "https://tenant.authing.cn/oidc"
    assert completed.claims.subject == "authing-subject"
    assert completed.claims.email_verified is True
    assert completed.claims.display_name == "Alice"


@pytest.mark.asyncio
async def test_authing_provider_rejects_a_token_without_subject() -> None:
    class MissingSubject(_OAuthClient):
        async def authorize_access_token(self, request):
            return {"userinfo": {"email": "alice@example.com"}}

    provider = AuthingIdentityProvider(
        issuer="https://tenant.authing.cn/oidc",
        oauth_client=MissingSubject(),
    )

    with pytest.raises(ValueError, match="subject"):
        await provider.complete(_request("/auth/callback"))
