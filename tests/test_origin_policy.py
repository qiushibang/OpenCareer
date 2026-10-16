import pytest

from coworker.server.origins import (
    OriginPolicy,
    build_origin_policy,
    normalize_origin,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Example.COM", "https://example.com"),
        ("https://example.com:443", "https://example.com"),
        ("http://example.com:80", "http://example.com"),
        ("http://example.com:18080", "http://example.com:18080"),
        ("https://例子.测试", "https://xn--fsqu00a.xn--0zwm56d"),
        ("tauri://LOCALHOST", "tauri://localhost"),
    ],
)
def test_normalize_origin_preserves_exact_origin_identity(
    raw: str,
    expected: str,
) -> None:
    assert normalize_origin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://*.example.com",
        "https://example.com/path",
        "https://example.com?query=1",
        "https://example.com#fragment",
        "ftp://example.com",
        "https://user:pass@example.com",
        "example.com",
    ],
)
def test_normalize_origin_rejects_non_origins(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_origin(raw)


def test_policy_rejects_suffix_and_port_mismatches() -> None:
    policy = OriginPolicy(["https://friend.example.com"])

    assert policy.allows("https://friend.example.com")
    assert not policy.allows("https://friend.example.com.evil.test")
    assert not policy.allows("https://friend.example.com:8443")
    assert not policy.allows("http://friend.example.com")


def test_database_outage_keeps_only_explicit_fallback_origins() -> None:
    class UnavailableOrigins:
        def enabled_origins(self) -> tuple[str, ...]:
            raise RuntimeError("database unavailable")

    policy = build_origin_policy(
        defaults=("tauri://localhost",),
        emergency_origins="https://alpha.example.com",
        repository=UnavailableOrigins(),
    )

    assert policy.allows("tauri://localhost")
    assert policy.allows("https://alpha.example.com")
    assert not policy.allows("https://database-only.example.com")
