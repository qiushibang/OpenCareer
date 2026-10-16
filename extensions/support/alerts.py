"""Bounded, content-free alert aggregation; no default external delivery."""
from __future__ import annotations

import json
import time
from uuid import uuid4
from coworker.server.identity import Principal
from .admin import SupportCenter
from .diagnostics import DIAGNOSTIC_KINDS

HOST_ALERTS = frozenset({"health_down", "unexpected_restart", "disk_pressure", "memory_pressure"})


class AlertCenter:
    def __init__(self, center: SupportCenter) -> None:
        self.center = center
        self.diagnostics = center.diagnostics
        self.table = "support.alerts" if self.diagnostics.database is not None else "support_alerts"
        if self.diagnostics.database is None:
            with self.diagnostics.transaction(Principal("local", "internal")) as connection:
                connection.execute("CREATE TABLE IF NOT EXISTS support_alerts(category TEXT PRIMARY KEY,data TEXT NOT NULL)")

    def synchronize(self, principal: Principal, observed: dict[str, int], *, source: str,
                    unavailable: frozenset[str] = frozenset()) -> list[dict]:
        allowed = HOST_ALERTS if source == "host" else DIAGNOSTIC_KINDS if source == "application" else frozenset()
        if not allowed or not unavailable.issubset(allowed) or any(category not in allowed or not isinstance(count, int) or count < 0 for category, count in observed.items()):
            raise ValueError("invalid alert category")
        now = int(time.time())
        with self.center.transaction(principal) as connection:
            execute = self.diagnostics.execute
            if self.diagnostics.database is not None:
                execute(connection, "SELECT pg_advisory_xact_lock(hashtextextended(?,0))", ("support-alerts",))
            previous = {row[0]: json.loads(row[1]) for row in execute(connection, f"SELECT category,data FROM {self.table}").fetchall()}
            for category in allowed:
                if category in unavailable and category not in observed:
                    continue  # A failed measurement is not evidence of recovery.
                count = min(1_000_000, observed.get(category, 0))
                old = previous.get(category)
                if not count and not old:
                    continue
                alert = old or {"id": uuid4().hex, "category": category, "source": source,
                                "created_at": now, "last_notified_at": 0, "occurrences": 0}
                if count and not alert.get("active"):
                    alert["occurrences"] += 1
                alert.update(active=count > 0, count=count, updated_at=now)
                # Delivery is a separate explicitly configured operator action, never a model tool.
                execute(connection, f"INSERT INTO {self.table}(category,data) VALUES (?,?) ON CONFLICT(category) DO UPDATE SET data=excluded.data",
                        (category, json.dumps(alert)))
            self.center.audit(connection, principal, "alerts")
            rows = execute(connection, f"SELECT data FROM {self.table}").fetchall()
        return sorted((json.loads(row[0]) for row in rows), key=lambda item: (not item["active"], -item["updated_at"]))

    def application_alerts(self, principal: Principal) -> list[dict]:
        with self.center.transaction(principal) as connection:
            expression = "data::jsonb->>'kind'" if self.diagnostics.database is not None else "json_extract(data,'$.kind')"
            rows = self.diagnostics.execute(connection, f"""SELECT {expression},COUNT(*) FROM {self.diagnostics.table}
                WHERE created_at>=? GROUP BY {expression}""", (int(time.time()) - 900,)).fetchall()
        return self.synchronize(principal, {kind: count for kind, count in rows if kind in DIAGNOSTIC_KINDS and count >= 10}, source="application")

    def maintain(self, principal: Principal) -> None:
        with self.center.transaction(principal) as connection:
            # Global expiry only touches new technical diagnostics, never feedback or business data.
            self.diagnostics.execute(connection, f"DELETE FROM {self.diagnostics.table} WHERE created_at<?", (int(time.time()) - 14 * 86400,))
            self.center.audit(connection, principal, "maintenance")

    def take_notifications(self, principal: Principal) -> list[dict]:
        now = int(time.time())
        events = []
        with self.center.transaction(principal) as connection:
            execute = self.diagnostics.execute
            if self.diagnostics.database is not None:
                execute(connection, "SELECT pg_advisory_xact_lock(hashtextextended(?,0))", ("support-alerts",))
            for category, encoded in execute(connection, f"SELECT category,data FROM {self.table}").fetchall():
                alert = json.loads(encoded)
                if not alert["active"] or now - alert["last_notified_at"] < 900:
                    continue
                alert["last_notified_at"] = now
                execute(connection, f"UPDATE {self.table} SET data=? WHERE category=?", (json.dumps(alert), category))
                events.append({"id": alert["id"], "category": category, "count": alert["count"]})
        return events
