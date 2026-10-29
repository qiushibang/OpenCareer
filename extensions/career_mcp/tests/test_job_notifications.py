import httpx
import pytest
import json
from urllib.parse import parse_qs

from extensions.career_mcp.services.job_notifications import BotSender, validate_endpoint
from extensions.career_mcp.services.job_notifications import render_batches


@pytest.mark.parametrize("url", ["http://open.feishu.cn/open-apis/bot/v2/hook/test", "https://127.0.0.1/hook", "https://open.feishu.cn.evil.example/open-apis/bot/v2/hook/test", "https://open.feishu.cn@evil.example/hook", "https://open.feishu.cn:444/open-apis/bot/v2/hook/test"])
def test_robot_addresses_cannot_be_arbitrary_network_targets(url):
    with pytest.raises(ValueError):
        validate_endpoint("feishu", url)


@pytest.mark.parametrize("kind,url,reply", [
    ("feishu", "https://open.feishu.cn/open-apis/bot/v2/hook/test", {"code": 0}),
    ("dingtalk", "https://oapi.dingtalk.com/robot/send?access_token=test", {"errcode": 0}),
    ("wecom", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test", {"errcode": 0}),
])
def test_three_official_channels_only_accept_explicit_success(kind, url, reply):
    def receiver(request):
        assert b"OpenCareer" in request.content
        return httpx.Response(200, json=reply)
    sender = BotSender(transport=httpx.MockTransport(receiver), resolve=False)
    assert sender.send(kind, {"url": url, "secret": "fixture"}, "OpenCareer 岗位日报") == "sent"
    sender = BotSender(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), resolve=False)
    assert sender.send(kind, {"url": url}, "OpenCareer") == "failed"


def test_ambiguous_timeout_is_not_automatically_retried():
    def receiver(request):
        raise httpx.ReadTimeout("URL with secret", request=request)
    sender = BotSender(transport=httpx.MockTransport(receiver), resolve=False)
    assert sender.send("wecom", {"url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"}, "OpenCareer") == "uncertain"


def test_debug_logging_cannot_record_robot_credentials(caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    sender = BotSender(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"errcode": 0})), resolve=False)
    assert sender.send("wecom", {"url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fixture_private"}, "OpenCareer") == "sent"
    assert "fixture_private" not in caplog.text
    logging.getLogger("httpx").info("unrelated traffic remains observable")
    assert "unrelated traffic remains observable" in caplog.text


def test_long_public_fields_cannot_exceed_channel_byte_budget():
    job = {"id":"one","title":"产品经理"*100,"company":{"name":"公司"*100},"locations":["北京"*100],"source_url":"https://jobs.example/"+"a"*2000,"first_seen_at":"2026-10-29T00:00:00Z"}
    parts = render_batches("日报", [job], new_since="2026-10-28T16:00:00Z", prior_ids=None)
    assert all(len(p.encode()) <= 1600 for p in parts)
    assert "匹配 1 个岗位" in parts[0]
    job.update(first_seen_at="2026-10-20T00:00:00Z", reopened_at="2026-10-29T00:00:00Z")
    assert "【重新开放】" in render_batches("日报", [job], new_since="2026-10-28T16:00:00Z", prior_ids=set())[0]


def test_signatures_match_independent_hmac_vectors():
    # Fixture-only vectors cross-checked with Node's crypto implementation.
    def receiver(request):
        if request.url.host == "open.feishu.cn":
            body = json.loads(request.content)
            assert body["timestamp"] == "1000"
            assert body["sign"] == "GVW3YewCPeHFo1+CUdyn+VTNDDcwEnYOlCk/ZlQh1WM="
            return httpx.Response(200, json={"code":0})
        query = parse_qs(request.url.query.decode())
        assert query["timestamp"] == ["1000000"]
        assert query["sign"] == ["DpgEAKZ7T3EHTVVvzT7ymGo5/QuJf/yWtWUG+ylTkmk="]
        return httpx.Response(200, json={"errcode":0})
    sender = BotSender(transport=httpx.MockTransport(receiver), resolve=False, clock=lambda:1000)
    assert sender.send("feishu", {"url":"https://open.feishu.cn/open-apis/bot/v2/hook/test","secret":"fixture"}, "OpenCareer") == "sent"
    assert sender.send("dingtalk", {"url":"https://oapi.dingtalk.com/robot/send?access_token=test","secret":"fixture"}, "OpenCareer") == "sent"
