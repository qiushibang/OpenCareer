from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = (
    ROOT / "deploy" / "docker-compose.ip.yml",
    ROOT / "deploy" / "docker-compose.yml",
)


def _compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_cloud_composes_reuse_host_database_and_redis() -> None:
    for path in COMPOSE_FILES:
        services = _compose(path)["services"]

        assert "postgres" not in services
        assert "redis" not in services
        assert services["backend-a"]["network_mode"] == "host"
        environment = services["backend-a"]["environment"]
        assert str(environment["DATABASE_URL"]).startswith("${DATABASE_URL:")
        assert "127.0.0.1" in environment["REDIS_URL"]


def test_cloud_services_receive_database_and_redis_urls() -> None:
    for path in COMPOSE_FILES:
        services = _compose(path)["services"]
        backends = [
            service
            for name, service in services.items()
            if name.startswith("backend-")
        ]
        assert backends

        for backend in backends:
            environment = backend["environment"]
            assert environment["DATABASE_URL"]
            assert environment["REDIS_URL"]

        crawler = services["crawler"]
        assert crawler["environment"]["DATABASE_URL"]
        assert crawler["environment"]["REDIS_URL"]


def test_cloud_crawler_has_one_shared_catalog_target() -> None:
    for path in COMPOSE_FILES:
        crawler = _compose(path)["services"]["crawler"]
        environment = crawler["environment"]
        mounts = crawler.get("volumes", [])

        assert "CRAWL_TARGETS" not in environment
        assert all(
            not str(mount).startswith(("data-a:", "data-b:", "data-c:"))
            for mount in mounts
        )
        assert any(str(mount).startswith("crawler-cache:") for mount in mounts)


def test_backend_image_excludes_retired_document_generation_runtime() -> None:
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    crawler = (ROOT / "deploy" / "crawler" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "libreoffice-writer" not in dockerfile
    assert "fonts-noto-cjk" not in dockerfile
    assert "requirements-server.txt" in dockerfile
    assert "playwright install --with-deps chromium" in crawler


def test_domain_compose_uses_one_authing_backend_without_ip_bypass() -> None:
    compose = _compose(ROOT / "deploy" / "docker-compose.yml")
    services = compose["services"]
    backends = [name for name in services if name.startswith("backend-")]

    assert backends == ["backend-a"]
    environment = services["backend-a"]["environment"]
    assert environment["OPENCAR_AUTH_ISSUER"]
    assert environment["OPENCAR_AUTH_CLIENT_ID"]
    assert environment["OPENCAR_AUTH_CLIENT_SECRET"]
    assert environment["OPENCAR_AUTH_REDIRECT_URI"].startswith(
        "https://app."
    )
    assert environment["OPENCAR_AUTH_STATE_SECRET"]
    assert not any("18080" in str(port) or "IP_PORT" in str(port) for port in services["caddy"]["ports"])
    assert services["backend-a"]["cap_drop"] == ["ALL"]
    assert services["backend-a"]["read_only"] is True
    assert services["backend-a"]["security_opt"] == ["no-new-privileges:true"]
    assert services["caddy"]["environment"]["BACKEND_UPSTREAM"].startswith(
        "${BACKEND_BIND_HOST:"
    )
    assert "extra_hosts" not in services["caddy"]


def test_domain_caddy_strips_every_alpha_token_channel() -> None:
    caddyfile = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "app.{$BASE_DOMAIN}" in caddyfile
    domain_snippet = caddyfile.split("(domain_backend)", 1)[1]
    assert "(ip_backend)" not in caddyfile
    assert "max_size 16MB" in caddyfile
    assert "header_up -X-OpenWorker-Token" in domain_snippet
    assert 'header_up Sec-WebSocket-Protocol "openworker"' in domain_snippet
    assert "{args[1]}" not in domain_snippet
    assert "{$BASE_DOMAIN}, www.{$BASE_DOMAIN}" in caddyfile
    assert "redir https://app.{$BASE_DOMAIN}{uri} permanent" in caddyfile


def test_legacy_maintenance_entry_is_never_publicly_bound() -> None:
    compose = _compose(ROOT / "deploy" / "docker-compose.ip.yml")
    assert all(str(port).startswith("127.0.0.1:") for port in compose["services"]["caddy"]["ports"])


def test_release_staging_survives_the_source_rsync_and_errors_reach_rollback() -> None:
    script = (ROOT / "deploy" / "sync-to-server.sh").read_text(
        encoding="utf-8"
    )

    assert "set -eEuo pipefail" in script
    assert 'WEB_STAGE="${REMOTE_DIR}.releases/web-$BACKUP_ID"' in script
    assert 'WEB_STAGE="$REMOTE_DIR/deploy/' not in script
