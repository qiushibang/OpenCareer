from __future__ import annotations

from coworker.providers.aiden_provider import (
    AIDEN_BASE_URL,
    AidenResponsesProvider,
    aiden_headers,
)
from coworker.providers.matrix import model_context_windows
from coworker.providers.registry import (
    build_provider_client,
    descriptor_configured,
    get_descriptor,
    verify_provider_key,
)


def test_aiden_provider_builds_responses_client_with_dynamic_token(
    monkeypatch,
):
    captured = {}
    tokens = iter(["jwt-first", "jwt-second"])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    provider = AidenResponsesProvider(
        token_provider=lambda: next(tokens),
        env={
            "AIDEN_X_HEADER_X_AIDEN_X_CLIENT": "client",
            "AIDEN_X_HEADER_X_AIDEN_SESSION_ID": "session",
            "AIDEN_X_HEADER_X_AIDEN_TERMINAL_ID": "terminal",
        },
    )

    provider._ensure_client()

    assert captured["base_url"] == AIDEN_BASE_URL
    assert captured["api_key"]() == "jwt-first"
    assert captured["api_key"]() == "jwt-second"
    assert captured["default_headers"] == {
        "X-Aiden-X-Client": "client",
        "X-Aiden-Session-Id": "session",
        "X-Aiden-Terminal-Id": "terminal",
    }


def test_aiden_headers_accept_aiden_x_suffixed_environment_names():
    assert aiden_headers(
        {
            "AIDEN_X_HEADER_X_AIDEN_X_CLIENT_0": "client",
            "AIDEN_X_HEADER_X_AIDEN_SESSION_ID_1": "session",
            "AIDEN_X_HEADER_X_AIDEN_TERMINAL_ID_2": "terminal",
        }
    ) == {
        "X-Aiden-X-Client": "client",
        "X-Aiden-Session-Id": "session",
        "X-Aiden-Terminal-Id": "terminal",
    }


def test_registry_routes_keyless_aiden_to_responses_provider():
    descriptor = get_descriptor("aiden")

    assert descriptor is not None
    assert descriptor.needs_key is False
    assert descriptor_configured(descriptor, {}) is True
    assert isinstance(build_provider_client("aiden", {}, None), AidenResponsesProvider)
    assert descriptor.recommended_model == "deepseek-v4-flash"


def test_aiden_deepseek_flash_has_verified_context_window():
    assert model_context_windows()["aiden:deepseek-v4-flash"] == 1_000_000


def test_verify_aiden_uses_runtime_token_and_models_endpoint(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

    def fake_get(url, *, headers, timeout):
        captured.update(url=url, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr(
        "coworker.providers.registry.get_aiden_token",
        lambda _: "runtime-jwt",
    )
    monkeypatch.setattr("httpx.get", fake_get)

    result = verify_provider_key(
        "aiden",
        fields={"aiden_path": "/opt/aiden"},
    )

    assert result == {"ok": True}
    assert captured["url"] == "https://aiden-aiproxy.bytedance.net/v2/models"
    assert captured["headers"]["Authorization"] == "Bearer runtime-jwt"


def test_aiden_model_is_selectable_only_when_local_login_is_available(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    from coworker.server.manager import SessionManager

    monkeypatch.setattr(
        SessionManager,
        "_aiden_alive",
        lambda self: False,
        raising=False,
    )
    unavailable = SessionManager(data_dir=tmp_path / "unavailable")
    assert "aiden:deepseek-v4-flash" not in unavailable.get_settings()["models"]

    monkeypatch.setattr(
        SessionManager,
        "_aiden_alive",
        lambda self: True,
        raising=False,
    )
    available = SessionManager(data_dir=tmp_path / "available")
    assert "aiden:deepseek-v4-flash" in available.get_settings()["models"]
