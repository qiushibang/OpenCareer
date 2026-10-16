"""Independent host check. Operator-only CLI; no Agent or public write endpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging.config
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description="OpenCareer 脱敏主机健康检查，不默认外发通知。")
    parser.add_argument("--dry-run", action="store_true", help="只读检查，不连接数据库或写入状态")
    parser.add_argument("--state-file", default="/var/lib/opencareer-watchdog/state.json")
    args = parser.parse_args(argv)
    from .logging import cloud_log_config
    logging.config.dictConfig(cloud_log_config())

    observed: dict[str, int] = {}
    checks_unavailable: list[str] = []
    state_path = Path(args.state_file)
    previous: dict = {}
    if state_path.is_symlink():
        print('{"error":"unsafe_watchdog_state"}')
        return 2
    try:
        if state_path.exists():
            if state_path.stat().st_size > 8192:
                raise ValueError("state size")
            previous = json.loads(state_path.read_text())
            if not isinstance(previous, dict) or (not args.dry_run and previous.get("format") != 1):
                raise ValueError("state format")
    except (OSError, ValueError):
        print('{"error":"invalid_watchdog_state"}')
        return 2

    health_url = env.get("OPENCAR_WATCHDOG_HEALTH_URL", "http://127.0.0.1:18768/v1/health")
    try:
        parts = urlsplit(health_url)
        valid_target = (parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "172.18.0.1"}
                        and not parts.username and not parts.password and not parts.query and not parts.fragment
                        and parts.path == "/v1/health" and (parts.port is None or 1 <= parts.port <= 65535))
    except ValueError:
        valid_target = False
    if not valid_target:
        print('{"error":"invalid_watchdog_health_target"}')
        return 2
    try:
        # Disable environment proxies and redirects: this check cannot follow a server-selected URL.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: object, **kwargs: object) -> None:
                return None
        request = urllib.request.Request(health_url, headers={"Accept": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=2) as response:
            if response.geturl() != health_url or response.status != 200 or json.loads(response.read(4096)).get("status") != "ok":
                observed["health_down"] = 1
    except Exception:
        observed["health_down"] = 1

    try:
        disk = shutil.disk_usage(env.get("OPENCAR_WATCHDOG_DISK_PATH", "/data"))
        used = int(100 * (disk.total - disk.free) / max(1, disk.total))
        if used >= 90:
            observed["disk_pressure"] = min(100, used)
    except OSError:
        checks_unavailable.append("disk")
    try:
        fields = {}
        with Path(env.get("OPENCAR_WATCHDOG_MEMINFO_PATH", "/proc/meminfo")).open() as memory:
            for line in memory:
                if line.startswith(("MemTotal:", "MemAvailable:")):
                    name, value, *_ = line.split()
                    fields[name.rstrip(":")] = int(value)
        used = int(100 * (fields["MemTotal"] - fields["MemAvailable"]) / max(1, fields["MemTotal"]))
        if used >= 90:
            observed["memory_pressure"] = min(100, used)
    except (OSError, ValueError, KeyError):
        checks_unavailable.append("memory")

    current = {"format": 1}
    container = env.get("OPENCAR_WATCHDOG_CONTAINER", "")
    if container:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container) is None:
            print('{"error":"invalid_watchdog_container"}')
            return 2
        try:
            result = subprocess.run(["docker", "inspect", "--format", '{"restart_count":{{.RestartCount}},"started_at":"{{.State.StartedAt}}"}', container],
                                    capture_output=True, text=True, timeout=2, check=False)
            value = json.loads(result.stdout) if result.returncode == 0 and len(result.stdout) <= 1024 else {}
            count = value["restart_count"]
            if type(count) is not int or not 0 <= count <= 1_000_000 or not isinstance(value["started_at"], str) or len(value["started_at"]) > 64:
                raise ValueError("invalid restart metrics")
            start = hashlib.sha256(value["started_at"].encode()).hexdigest()
            if "restart_count" in previous and (count > previous["restart_count"] or start != previous.get("started_at")):
                if env.get("OPENCAR_WATCHDOG_MAINTENANCE") != "1":
                    observed["unexpected_restart"] = max(1, count - previous["restart_count"])
            current.update(restart_count=count, started_at=start)
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            checks_unavailable.append("restart")
    else:
        checks_unavailable.append("restart")

    if args.dry_run:
        print(json.dumps({"observed": observed, "checks_unavailable": checks_unavailable, "delivery": "disabled"}))
        return 0

    pending = previous.get("pending", {})
    from .alerts import HOST_ALERTS
    if not isinstance(pending, dict) or any(key not in HOST_ALERTS or type(value) is not int or not 0 <= value <= 1_000_000 for key, value in pending.items()):
        pending = {}
    combined = {**pending, **observed}
    events = []
    failed = False
    database = None
    try:
        from psycopg_pool import ConnectionPool
        from coworker.storage.postgres.database import CloudDatabase
        from coworker.server.identity import Principal
        from .diagnostics import DiagnosticStore
        from .feedback import FeedbackStore
        from .admin import SupportCenter
        from .alerts import AlertCenter
        if not env.get("DATABASE_URL"):
            raise ValueError("database not configured")
        database = CloudDatabase(pool=ConnectionPool(env["DATABASE_URL"], min_size=0, max_size=1, timeout=3,
                                reconnect_timeout=3, kwargs={"connect_timeout": 3}, open=True))
        # SupportCenter reads process configuration; never accept a user-supplied identity.
        center = SupportCenter(FeedbackStore(DiagnosticStore(database=database)), environ=env)
        uid = env.get("OPENCAR_SUPPORT_WATCHDOG_ADMIN_ID", "")
        principal = Principal(uid, "host-watchdog")
        alerts = AlertCenter(center)
        unavailable = frozenset({"disk": "disk_pressure", "memory": "memory_pressure", "restart": "unexpected_restart"}[check]
                                for check in checks_unavailable)
        alerts.synchronize(principal, combined, source="host", unavailable=unavailable)
        alerts.application_alerts(principal)
        alerts.maintain(principal)
        events = alerts.take_notifications(principal)
        combined = {}
    except Exception:
        failed = True
    finally:
        if database is not None:
            database.close()
    current["pending"] = combined
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".watchdog-", dir=state_path.parent)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(current, stream)
        os.replace(temporary, state_path)
    except OSError:
        print('{"error":"watchdog_state_unavailable"}')
        return 1
    print(json.dumps({"events": events, "checks_unavailable": checks_unavailable,
                      "support_storage": "unavailable" if failed else "ready", "delivery": "disabled"}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
