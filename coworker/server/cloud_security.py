"""Deterministic cloud policy: user inputs never select programs or network hosts."""

from urllib.parse import urlsplit
from collections import OrderedDict, Counter
from threading import Lock
from time import monotonic
import logging

from .alpha import enabled

MAX_BODY_BYTES = 16 * 1024 * 1024


class CloudBudget:
    """Bounded single-worker admission control; never stores request content or keys."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: OrderedDict[str, list[float]] = OrderedDict()
        self._active: Counter[tuple[str, str]] = Counter()

    def allow_request(self, user_id: str, *, write: bool) -> bool:
        now = monotonic()
        with self._lock:
            for suffix, maximum in (("all", 180), ("write", 30)):
                if suffix == "write" and not write:
                    continue
                key = f"{user_id}:{suffix}"
                times = [t for t in self._requests.pop(key, []) if now - t < 60]
                self._requests[key] = times
                if len(times) >= maximum:
                    return False
            self._requests[f"{user_id}:all"].append(now)
            if write:
                self._requests[f"{user_id}:write"].append(now)
            while len(self._requests) > 4096:
                self._requests.popitem(last=False)
            return True

    def acquire(self, kind: str, user_id: str) -> bool:
        limits = {
            "socket": (8, 32),
            "turn": (2, 4),
            "body": (2, 4),
            "anonymous_body": (2, 2),
        }
        if kind not in limits:
            raise ValueError("unknown cloud capacity category")
        per_user, total = limits[kind]
        with self._lock:
            if self._active[kind, user_id] >= per_user or sum(
                count for (category, _), count in self._active.items() if category == kind
            ) >= total:
                return False
            self._active[kind, user_id] += 1
            return True

    def release(self, kind: str, user_id: str) -> None:
        with self._lock:
            key = (kind, user_id)
            if self._active[key] <= 1:
                self._active.pop(key, None)
            else:
                self._active[key] -= 1

# Exact bases, not suffix matching or user-configurable wildcard domains.
MODEL_ENDPOINTS: dict[str, tuple[str, ...]] = {
    "openai": ("https://api.openai.com/v1",),
    "anthropic": (), "gemini": (),
    "zai": ("https://api.z.ai/api/paas/v4", "https://open.bigmodel.cn/api/paas/v4"),
    "deepseek": ("https://api.deepseek.com", "https://api.deepseek.com/v1"),
    "kimi": ("https://api.moonshot.ai/v1", "https://api.moonshot.cn/v1"),
    "minimax": ("https://api.minimax.io/v1", "https://api.minimax.chat/v1"),
    "qwen": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "xai": ("https://api.x.ai/v1",),
    "mistral": ("https://api.mistral.ai/v1",),
    "meta": ("https://api.meta.ai/v1",),
    "together": ("https://api.together.xyz/v1",),
    "fireworks": ("https://api.fireworks.ai/inference/v1",),
    "openrouter": ("https://openrouter.ai/api/v1",),
}


def validate_provider(name: str, fields: dict | None) -> None:
    """Fail before saving, constructing clients, making requests or spawning programs."""
    if not enabled():
        return
    if not isinstance(name, str) or name not in MODEL_ENDPOINTS:
        logging.getLogger("coworker.server").warning("cloud_security_refusal category=provider_disabled")
        raise ValueError("This model provider is disabled on the public server.")
    if fields is not None and not isinstance(fields, dict):
        raise ValueError("Model settings must be an object.")
    values = fields or {}
    for key in ("api_key", "base_url"):
        value = values.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 8192):
            raise ValueError("Model credential and endpoint fields must be bounded strings.")
    if any(key in values for key in ("aiden_path", "aws_profile", "service_account_json")):
        raise ValueError("Server programs and host credentials are not user-configurable.")
    base = values.get("base_url") or ""
    if not isinstance(base, str):
        raise ValueError("Model endpoint must be a string.")
    if base:
        base = base.strip().rstrip("/")
        parts = urlsplit(base)
        if parts.username or parts.password or parts.query or parts.fragment or base not in MODEL_ENDPOINTS[name]:
            logging.getLogger("coworker.server").warning("cloud_security_refusal category=model_endpoint")
            raise ValueError("Only the approved official HTTPS model endpoints are allowed.")
