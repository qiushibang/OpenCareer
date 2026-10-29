from datetime import datetime, timedelta, timezone

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.services.job_catalog import JobCatalog
from extensions.career_mcp.services.job_subscriptions import JobSubscriptions


def test_draft_is_not_a_send_and_daily_empty_digest_still_sends(tmp_path):
    config = CareerConfig(tmp_path / "career")
    now = [datetime(2026, 10, 29, 0, tzinfo=timezone.utc)]
    delivered = []
    class Sender:
        def send(self, kind, credentials, message):
            delivered.append(message)
            return "sent"
    service = JobSubscriptions(config, catalog=JobCatalog(config), clock=lambda: now[0], sender=Sender(), refresh=lambda companies: {"ok": True})
    channel = service.save_channel("test", "wecom", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fixture")
    draft = service.draft({"title": "北京产品", "condition": {"field": "locations", "op": "in", "values": ["北京"]}, "channel_ids": [channel["id"]], "send_time": "09:00"})
    assert service.tick() == 0 and delivered == []
    assert "fixture" not in str(service.channels())
    service.activate(draft["id"], draft["version"])
    now[0] = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)
    assert service.tick() == 1
    assert "没有匹配岗位" in delivered[0]
    assert service.tick() == 0
    now[0] = datetime(2026, 11, 1, 2, tzinfo=timezone.utc)
    assert service.tick() == 1  # missed days collapse to one delivery
    assert len(delivered) == 2


def test_ambiguous_delivery_requires_attention_not_repeated_send(tmp_path):
    config = CareerConfig(tmp_path / "career")
    now = [datetime(2026, 10, 29, 0, tzinfo=timezone.utc)]
    class Sender:
        def send(self, *args):
            return "uncertain"
    service = JobSubscriptions(config, clock=lambda: now[0], sender=Sender(), refresh=lambda c: {"ok": False})
    channel = service.save_channel("test", "wecom", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fixture")
    draft = service.draft({"title": "全部", "channel_ids": [channel["id"]]})
    service.activate(draft["id"], draft["version"])
    now[0] = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)
    assert service.tick() == 1
    assert service.runs(draft["id"])[0]["status"] == "uncertain"
    assert service.tick() == 0


def test_pausing_while_refresh_is_running_prevents_outbound_send(tmp_path):
    config = CareerConfig(tmp_path / "career")
    now = [datetime(2026, 10, 29, 0, tzinfo=timezone.utc)]
    class Sender:
        def send(self, *args):
            raise AssertionError("paused subscription must not send")
    service = JobSubscriptions(config, clock=lambda: now[0], sender=Sender())
    channel = service.save_channel("test", "wecom", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fixture")
    draft = service.draft({"title": "暂停测试", "channel_ids": [channel["id"]]})
    service.activate(draft["id"], draft["version"])
    def refresh(companies):
        service.pause(draft["id"])
        return {"ok": True}
    service.refresh = refresh
    now[0] = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)
    assert service.tick() == 0
    assert service.runs(draft["id"]) == []


def test_retry_resumes_only_failed_parts_across_channels_and_restart(tmp_path):
    config = CareerConfig(tmp_path / "career")
    now = [datetime(2026, 10, 29, 0, tzinfo=timezone.utc)]
    calls = []
    class Sender:
        def send(self, kind, credentials, message):
            calls.append(kind)
            return "retryable" if kind == "dingtalk" and calls.count(kind) == 1 else "sent"
    kwargs = dict(clock=lambda: now[0], sender=Sender(), refresh=lambda c: {"ok": True})
    service = JobSubscriptions(config, **kwargs)
    channels = [service.save_channel("飞书", "feishu", "https://open.feishu.cn/open-apis/bot/v2/hook/fixture"),
                service.save_channel("钉钉", "dingtalk", "https://oapi.dingtalk.com/robot/send?access_token=fixture")]
    draft = service.draft({"title": "可恢复日报", "channel_ids": [c["id"] for c in channels]})
    service.activate(draft["id"], draft["version"])
    now[0] = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)
    assert service.tick() == 1
    assert service.runs(draft["id"])[0]["status"] == "retryable"
    restarted = JobSubscriptions(config, **kwargs)
    now[0] += timedelta(seconds=61)
    assert restarted.tick() == 0
    assert restarted.runs(draft["id"])[0]["status"] == "sent"
    assert calls == ["feishu", "dingtalk", "dingtalk"]
