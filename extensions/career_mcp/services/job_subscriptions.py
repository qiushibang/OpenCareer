"""Local-only subscriptions and durable, per-part outbound delivery ledger."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
import json
import re
import sqlite3
import time as clock_time
import uuid

from coworker.secrets import SecretStore
from ..config import CareerConfig
from .job_catalog import JobCatalog, TZ, instant, validate_condition
from .job_notifications import BotSender, render_batches, validate_endpoint


def next_fire(now: datetime, hhmm: str) -> str:
    hour, minute = map(int, hhmm.split(":"))
    local = now.astimezone(TZ)
    value = datetime.combine(local.date(), time(hour, minute), TZ)
    if value <= local:
        value += timedelta(days=1)
    return value.isoformat()


def refresh_catalog(config: CareerConfig, companies: list[str]) -> dict:
    """Ask the launcher's sole sync worker, never start a competing crawler."""
    from ..local_jobs import read_status, request_refresh
    start = clock_time.time()
    request_refresh(config, companies)
    deadline = clock_time.monotonic() + (1800 if read_status(config).get("mode") == "local" else 120)
    while clock_time.monotonic() < deadline:
        state = read_status(config)
        if state.get("updated_at", 0) >= start and state.get("state") in {"completed", "partial"}:
            return {"ok": state.get("state") == "completed" and not state.get("failed"), "status": state}
        clock_time.sleep(1)
    return {"ok": False, "warning": "刷新未在时限内完成，使用本机已有数据。"}


class JobSubscriptions:
    def __init__(self, config: CareerConfig | None = None, *, catalog: JobCatalog | None = None,
                 clock=None, sender=None, refresh=None):
        self.config = config or CareerConfig.from_env()
        self.catalog = catalog or JobCatalog(self.config)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sender = sender or BotSender()
        self.refresh = refresh or (lambda companies: refresh_catalog(self.config, companies))
        self.secrets = SecretStore(self.config.data_dir / "push-secrets.json")

    @contextmanager
    def db(self):
        self.config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.config.data_dir / "job-subscriptions.sqlite3", timeout=30)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, name TEXT, kind TEXT, version INTEGER);
            CREATE TABLE IF NOT EXISTS subscriptions (id TEXT PRIMARY KEY, data TEXT, enabled INTEGER, version INTEGER, next_run TEXT);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, subscription_id TEXT, slot TEXT, started_at TEXT, status TEXT, result TEXT, UNIQUE(subscription_id, slot));
            CREATE TABLE IF NOT EXISTS deliveries (run_id TEXT, channel_id TEXT, part INTEGER, status TEXT, attempts INTEGER DEFAULT 0, PRIMARY KEY(run_id,channel_id,part));
            PRAGMA user_version=1;
        """)
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def channels(self) -> list[dict]:
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT id,name,kind,version FROM channels ORDER BY name")]

    def save_channel(self, name: str, kind: str, url: str, secret: str = "") -> dict:
        validate_endpoint(kind, url)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or not isinstance(secret, str) or len(secret) > 1000:
            raise ValueError("渠道名称或签名密钥不正确。")
        channel_id = uuid.uuid4().hex
        self.secrets.put("job-push:" + channel_id, {"url": url, "secret": secret})
        with self.db() as db:
            db.execute("INSERT INTO channels VALUES (?,?,?,1)", (channel_id, name.strip(), kind))
        return {"id": channel_id, "name": name.strip(), "kind": kind, "version": 1}

    def remove_channel(self, channel_id: str) -> None:
        with self.db() as db:
            for row in db.execute("SELECT data FROM subscriptions WHERE enabled=1"):
                if channel_id in json.loads(row[0])["channel_ids"]:
                    raise ValueError("请先暂停使用此渠道的订阅。")
            db.execute("DELETE FROM channels WHERE id=?", (channel_id,))
        self.secrets.delete("job-push:" + channel_id)

    def test_channel(self, channel_id: str) -> dict:
        channel = next((c for c in self.channels() if c["id"] == channel_id), None)
        if not channel:
            raise ValueError("渠道不存在。")
        status = self.sender.send(channel["kind"], self.secrets.get("job-push:" + channel_id) or {}, "OpenCareer 渠道测试：本消息不包含简历、对话或模型密钥。")
        return {"status": status}

    def draft(self, payload: dict, *, subscription_id: str | None = None) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"title", "condition", "channel_ids", "send_time", "semantic_query", "include_inactive", "today"}:
            raise ValueError("订阅包含不支持的配置。")
        title = payload.get("title", "岗位日报")
        hhmm = payload.get("send_time", "09:00")
        channels = payload.get("channel_ids", [])
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80 or not isinstance(hhmm, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hhmm):
            raise ValueError("标题或发送时间不正确。")
        available = {c["id"]: c for c in self.channels()}
        if not isinstance(channels, list) or not 1 <= len(channels) <= 3 or len(set(channels)) != len(channels) or any(c not in available for c in channels):
            raise ValueError("请选择 1–3 个已配置渠道；请勿在聊天中提交 Webhook。")
        semantic = payload.get("semantic_query") or None
        if semantic is not None and (not isinstance(semantic, str) or len(semantic) > 1000):
            raise ValueError("语义条件过长。")
        if type(payload.get("include_inactive", False)) is not bool:
            raise ValueError("include_inactive 必须是布尔值。")
        if type(payload.get("today", False)) is not bool:
            raise ValueError("today 必须是布尔值。")
        data = {"title": title.strip(), "condition": validate_condition(payload.get("condition")), "channel_ids": channels,
                "send_time": hhmm, "timezone": "Asia/Shanghai", "semantic_query": semantic,
                "include_inactive": payload.get("include_inactive", False), "today": bool(payload.get("today", False)), "channel_versions": {c: available[c]["version"] for c in channels}}
        sid = subscription_id or uuid.uuid4().hex
        with self.db() as db:
            prior = db.execute("SELECT version FROM subscriptions WHERE id=?", (sid,)).fetchone()
            if subscription_id and prior is None:
                raise ValueError("订阅不存在。")
            version = prior[0] + 1 if prior else 1
            db.execute("INSERT OR REPLACE INTO subscriptions VALUES (?,?,0,?,NULL)", (sid, json.dumps(data, ensure_ascii=False), version))
        return {"id": sid, "version": version, "enabled": False, "requires_user_confirmation": True, **data}

    def list(self) -> list[dict]:
        with self.db() as db:
            return [{"id": r["id"], "version": r["version"], "enabled": bool(r["enabled"]), "next_run": r["next_run"], **json.loads(r["data"])} for r in db.execute("SELECT * FROM subscriptions ORDER BY id")]

    def activate(self, sid: str, version: int) -> dict:
        # Called only by the attended local UI, never exposed as a model tool.
        with self.db() as db:
            row = db.execute("SELECT * FROM subscriptions WHERE id=? AND version=?", (sid, version)).fetchone()
            if row is None:
                raise ValueError("订阅已改变，请重新查看后启用。")
            data = json.loads(row["data"])
            channels = {c["id"]: c for c in self.channels()}
            if any(c not in channels or channels[c]["version"] != data["channel_versions"][c] for c in data["channel_ids"]):
                raise ValueError("渠道配置已改变，请重新确认。")
            db.execute("UPDATE subscriptions SET enabled=1,next_run=? WHERE id=?", (next_fire(self.clock(), data["send_time"]), sid))
        return {"ok": True}

    def pause(self, sid: str) -> None:
        with self.db() as db:
            db.execute("UPDATE subscriptions SET enabled=0,version=version+1 WHERE id=?", (sid,))

    def runs(self, sid: str) -> list[dict]:
        with self.db() as db:
            return [{"id": r["id"], "started_at": r["started_at"], "status": r["status"], "result": json.loads(r["result"] or "{}"),
                     "deliveries": [dict(d) for d in db.execute("SELECT channel_id,part,status,attempts FROM deliveries WHERE run_id=? ORDER BY part", (r["id"],))]}
                    for r in db.execute("SELECT * FROM runs WHERE subscription_id=? ORDER BY started_at DESC LIMIT 30", (sid,))]

    def preview(self, sid: str) -> dict:
        sub = next((s for s in self.list() if s["id"] == sid), None)
        if not sub:
            raise ValueError("订阅不存在。")
        return self.catalog.search(sub["condition"], semantic_query=sub["semantic_query"], include_inactive=sub["include_inactive"], today=sub.get("today", False))

    def tick(self) -> int:
        from ..local_jobs import worker_lock
        try:
            with worker_lock(self.config.data_dir / ".job-subscriptions.lock"):
                return self._tick()
        except BlockingIOError:
            return 0

    def _tick(self) -> int:
        now = self.clock()
        self._retry_pending()
        due = [s for s in self.list() if s["enabled"] and s["next_run"] and instant(s["next_run"]) <= now]
        if not due:
            return 0
        try:
            companies = []
            for sub in due:
                condition = sub["condition"]
                leaves = condition.get("all", [condition])
                company = next((c.get("values", []) for c in leaves if c.get("field") == "company" and c.get("op") == "in"), [])
                if not company:
                    companies = []
                    break
                from .job_catalog import ALIASES
                companies.extend(ALIASES.get(c, c) for c in company)
            refreshed = self.refresh(sorted(set(companies)))
        except Exception:
            refreshed = {"ok": False}
        executed = 0
        for sub in due:
            if not self._active(sub):
                continue
            run_id, slot = uuid.uuid4().hex, sub["next_run"]
            with self.db() as db:
                try:
                    db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?)", (run_id, sub["id"], slot, now.isoformat(), "running", "{}"))
                except sqlite3.IntegrityError:
                    # Previous process died after claiming the slot; never blindly resend.
                    db.execute("UPDATE runs SET status='uncertain' WHERE subscription_id=? AND slot=? AND status='running'", (sub["id"], slot))
                    db.execute("UPDATE subscriptions SET next_run=? WHERE id=?", (next_fire(now, sub["send_time"]), sub["id"]))
                    continue
            executed += 1
            try:
                self._execute(run_id, sub, now, refreshed)
            except Exception:
                with self.db() as db:
                    uncertain = db.execute("SELECT 1 FROM deliveries WHERE run_id=? AND status IN ('sending','uncertain')", (run_id,)).fetchone()
                    db.execute("UPDATE runs SET status=? WHERE id=?", ("uncertain" if uncertain else "failed", run_id))
                    row = db.execute("SELECT result FROM runs WHERE id=?", (run_id,)).fetchone()
                    saved = json.loads(row[0] or "{}")
                    saved["error"] = "查询或投递失败；未将失败记为零匹配。"
                    db.execute("UPDATE runs SET result=? WHERE id=?", (json.dumps(saved, ensure_ascii=False), run_id))
            with self.db() as db:
                db.execute("UPDATE subscriptions SET next_run=? WHERE id=? AND version=?", (next_fire(now, sub["send_time"]), sub["id"], sub["version"]))
        return executed

    def _active(self, sub: dict) -> bool:
        return any(s["id"] == sub["id"] and s["enabled"] and s["version"] == sub["version"] for s in self.list())

    def _retry_pending(self) -> None:
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM runs WHERE status='retryable'")]
        for row in rows:
            full = json.loads(row["result"])
            if full.get("retry_after", float("inf")) <= self.clock().timestamp():
                try:
                    self.retry_run(row["id"])
                except ValueError:
                    with self.db() as db:
                        db.execute("UPDATE runs SET status='paused' WHERE id=?", (row["id"],))

    def retry_run(self, run_id: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("运行记录标识不正确。")
        from ..local_jobs import worker_lock
        try:
            with worker_lock(self.config.data_dir / (".job-delivery-" + run_id + ".lock")):
                return self._retry_run(run_id)
        except BlockingIOError:
            raise ValueError("该投递正在重试，请稍后查看结果。") from None

    def _retry_run(self, run_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None or row["status"] not in {"failed", "retryable"}:
            raise ValueError("仅明确失败的投递可以重试；结果不确定的投递需要先在群内核对。")
        full = json.loads(row["result"])
        sub = next((s for s in self.list() if s["id"] == row["subscription_id"]), None)
        if not sub or not self._active(sub) or sub["version"] != full.get("subscription_version") or not full.get("parts"):
            raise ValueError("订阅已暂停、配置已改变或查询未成功，请重新预览并等待下一批次。")
        self._deliver(run_id, sub, full)
        return {"ok": True}

    def _execute(self, run_id: str, sub: dict, now: datetime, refreshed: dict) -> None:
        first = self.catalog.collect(sub["condition"], semantic_query=sub["semantic_query"], include_inactive=sub["include_inactive"], today=sub.get("today", False))
        jobs = first["jobs"]
        with self.db() as db:
            saved = db.execute("SELECT started_at,result FROM runs WHERE subscription_id=? AND status='sent' ORDER BY started_at DESC LIMIT 1", (sub["id"],)).fetchone()
        prior = {"started_at": saved[0], "result": json.loads(saved[1])} if saved else None
        since = prior["result"].get("sent_at", prior["started_at"]) if prior else datetime.combine(now.astimezone(TZ).date(), time.min, TZ).isoformat()
        prior_ids = set(prior["result"].get("job_ids", [])) if prior else None
        warning = "" if refreshed.get("ok") else "注意：本次刷新失败或未完成，以下使用已有数据，请查看岗位最近确认时间。"
        if first["warnings"]:
            warning = "\n".join([warning, *first["warnings"]]).strip()
        parts = render_batches(sub["title"], jobs, new_since=since, prior_ids=prior_ids, warning=warning, partial=first["semantic"]["partial"])
        full = {"jobs": jobs, "job_ids": [j["id"] for j in jobs], "candidate_total": first["candidate_total"],
                "total": first["total"], "partial": first["semantic"]["partial"], "freshness": first["freshness"], "warning": warning,
                "subscription_version": sub["version"], "parts": parts}
        with self.db() as db:
            db.execute("UPDATE runs SET result=? WHERE id=?", (json.dumps(full, ensure_ascii=False), run_id))
        self._deliver(run_id, sub, full)

    def _deliver(self, run_id: str, sub: dict, full: dict) -> None:
        statuses = []
        channel_map = {c["id"]: c for c in self.channels()}
        for channel_id in sub["channel_ids"]:
            channel = channel_map.get(channel_id)
            if not channel or channel["version"] != sub["channel_versions"][channel_id]:
                statuses.append("failed")
                continue
            credentials = self.secrets.get("job-push:" + channel_id)
            for index, part in enumerate(full["parts"]):
                if not self._active(sub):
                    statuses.append("paused")
                    break
                with self.db() as db:
                    prior = db.execute("SELECT status,attempts FROM deliveries WHERE run_id=? AND channel_id=? AND part=?", (run_id,channel_id,index)).fetchone()
                if prior and prior["status"] == "sent":
                    statuses.append("sent")
                    continue
                if prior and prior["status"] in {"uncertain", "sending"}:
                    statuses.append("uncertain")
                    break
                if prior and prior["attempts"] >= 3:
                    statuses.append("failed")
                    break
                with self.db() as db:
                    db.execute("INSERT INTO deliveries VALUES (?,?,?,?,1) ON CONFLICT(run_id,channel_id,part) DO UPDATE SET status='sending',attempts=attempts+1", (run_id, channel_id, index, "sending"))
                status = self.sender.send(channel["kind"], credentials or {}, part)
                with self.db() as db:
                    db.execute("UPDATE deliveries SET status=? WHERE run_id=? AND channel_id=? AND part=?", (status, run_id, channel_id, index))
                statuses.append(status)
                if status != "sent":
                    break
        status = "sent" if statuses and all(s == "sent" for s in statuses) else "uncertain" if "uncertain" in statuses else "paused" if "paused" in statuses else "retryable" if "retryable" in statuses else "failed"
        full["retry_after"] = self.clock().timestamp() + 60
        if status == "sent":
            full["sent_at"] = self.clock().isoformat()
        with self.db() as db:
            db.execute("UPDATE runs SET status=?,result=? WHERE id=?", (status, json.dumps(full, ensure_ascii=False), run_id))
