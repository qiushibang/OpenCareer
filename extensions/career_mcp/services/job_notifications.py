"""Narrow outbound-only official group robot adapters. No arbitrary URL tool."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import socket
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

ENDPOINTS = {"feishu": ("open.feishu.cn", r"/open-apis/bot/v2/hook/[a-zA-Z0-9_-]+", None),
             "dingtalk": ("oapi.dingtalk.com", r"/robot/send", "access_token"),
             "wecom": ("qyapi.weixin.qq.com", r"/cgi-bin/webhook/send", "key")}

_bot_request = ContextVar("career_private_bot_request", default=False)


class _BotTransportPrivacy(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # HTTP client debug/INFO logs include URL tokens. Keep unrelated traffic visible.
        return not _bot_request.get()


for _logger in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy", "httpcore.socks"):
    logging.getLogger(_logger).addFilter(_BotTransportPrivacy())


@contextmanager
def _private_transport():
    token = _bot_request.set(True)
    try:
        yield
    finally:
        _bot_request.reset(token)


def validate_endpoint(kind: str, url: str) -> str:
    if kind not in ENDPOINTS or not isinstance(url, str) or len(url) > 2048:
        raise ValueError("请选择飞书、钉钉或企业微信官方机器人。")
    host, path, query_key = ENDPOINTS[kind]
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment or not re.fullmatch(path, parsed.path):
        raise ValueError("机器人地址必须是该渠道的官方 HTTPS Webhook。")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (query_key is None and parsed.query) or (query_key and (set(query) != {query_key} or len(query[query_key]) != 1 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,500}", query[query_key][0]))):
        raise ValueError("机器人地址参数不正确。")
    return url


class BotSender:
    def __init__(self, *, transport=None, resolve: bool = True, clock=time.time):
        self.transport, self.resolve, self.clock = transport, resolve, clock

    def send(self, kind: str, credentials: dict, message: str) -> str:
        url = validate_endpoint(kind, credentials.get("url", ""))
        if self.resolve:
            try:
                addresses = socket.getaddrinfo(urlsplit(url).hostname, 443, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                    return "failed"
            except OSError:
                return "retryable"
        secret = credentials.get("secret") or ""
        payload = {"msg_type": "text", "content": {"text": message}} if kind == "feishu" else {"msgtype": "text", "text": {"content": message}}
        if secret and kind == "feishu":
            stamp = str(int(self.clock()))
            payload.update({"timestamp": stamp, "sign": base64.b64encode(hmac.new((stamp + "\n" + secret).encode(), b"", hashlib.sha256).digest()).decode()})
        elif secret and kind == "dingtalk":
            stamp = str(int(self.clock() * 1000))
            sign = base64.b64encode(hmac.new(secret.encode(), (stamp + "\n" + secret).encode(), hashlib.sha256).digest()).decode()
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            query.update({"timestamp": [stamp], "sign": [sign]})
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), ""))
        try:
            with _private_transport(), httpx.Client(transport=self.transport, timeout=10, follow_redirects=False, trust_env=False) as client:
                response = client.post(url, json=payload)
            if response.status_code == 429:
                return "retryable"
            if response.status_code >= 500:
                return "uncertain"
            if response.status_code != 200 or len(response.content) > 64000:
                return "failed"
            result = response.json()
            if not isinstance(result, dict):
                return "failed"
            code = result.get("code") if kind == "feishu" else result.get("errcode")
            if kind == "feishu" and code in {11232, 11233, 11247}:
                return "retryable"
            return "sent" if type(code) is int and code == 0 else "failed"
        except (httpx.TimeoutException, httpx.NetworkError):
            return "uncertain"
        except (ValueError, httpx.HTTPError):
            return "failed"


def render_batches(title: str, jobs: list[dict], *, new_since: str, prior_ids: set[str] | None, warning: str = "", partial: bool = False) -> list[str]:
    from .job_catalog import instant
    prefix = f"OpenCareer · {title}\n{'已评估范围内' if partial else ''}匹配 {len(jobs)} 个岗位。\n"
    if warning:
        prefix += warning + "\n"
    prefix = prefix.encode()[:600].decode("utf-8", errors="ignore") + "\n"
    if not jobs:
        return [prefix + "本次没有匹配岗位。"]
    parts, current, delivered = [], prefix, 0
    for job in jobs:
        if len(parts) >= 9 or delivered >= 100:
            break
        marker = "【新增】" if instant(job["first_seen_at"]) >= instant(new_since) else "【重新开放】" if job.get("reopened_at") and instant(job["reopened_at"]) >= instant(new_since) else "【新匹配】" if prior_ids is not None and job["id"] not in prior_ids else ""
        title_text = re.sub(r"[\r\n]", " ", str(job["title"])).encode()[:180].decode("utf-8", errors="ignore")
        from .job_catalog import TZ
        confirmed = instant(job["last_seen_at"]).astimezone(TZ).date().isoformat() if job.get("last_seen_at") else "未知"
        url = job["source_url"] if len(job["source_url"].encode()) <= 400 else "官网链接过长，完整地址见本机运行记录。"
        company = job["company"]["name"].encode()[:90].decode("utf-8", errors="ignore")
        locations = "、".join(job["locations"]).encode()[:90].decode("utf-8", errors="ignore")
        entry = f"\n{marker}{company} · {title_text} · {locations}\n最近确认：{confirmed}\n{url}\n"
        # WeCom's text content limit is byte based, not character based.
        if len((current + entry).encode()) > 1600:
            parts.append(current)
            current = prefix
        current += entry
        delivered += 1
    parts.append(current)
    if delivered < len(jobs):
        parts.append(f"OpenCareer · 匹配共 {len(jobs)} 项，本轮发送 {delivered} 项，尚有 {len(jobs)-delivered} 项未发送。完整结果保存在本机岗位订阅运行记录中。")
    return parts
