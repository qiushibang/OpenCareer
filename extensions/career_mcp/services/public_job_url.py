"""Read a public job page without exposing general web access."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Callable

from coworker.web.guard import get_checked

_MAX_BYTES = 2 * 1024 * 1024
_MAX_CHARS = 100_000
_MIN_TEXT_CHARS = 40
_ALLOWED_CONTENT_TYPES = (
    "application/json",
    "text/html",
    "text/plain",
)
_RESTRICTED_MARKERS = (
    "请登录",
    "登录后查看",
    "验证码",
    "访问验证",
    "captcha",
)


class PublicJobUrlError(ValueError):
    """A public job URL could not be read within the safe contract."""


class _VisibleTextParser(HTMLParser):
    _SKIPPED = {"head", "script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        if tag.lower() in self._SKIPPED:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIPPED and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            value = data.strip()
            if value:
                self.parts.append(value)


class PublicJobUrlService:
    def __init__(
        self,
        *,
        client_factory: Callable[[], object] | None = None,
        checked_get: Callable[[object, str], object] = get_checked,
    ) -> None:
        self._client_factory = client_factory or _http_client
        self._checked_get = checked_get

    def preview(self, url: str) -> dict:
        if not isinstance(url, str) or not url.lower().startswith(
            ("http://", "https://")
        ):
            raise PublicJobUrlError(
                "public job URL must start with http:// or https://"
            )
        try:
            with self._client_factory() as client:
                response = self._checked_get(client, url)
                response.raise_for_status()
        except PermissionError as exc:
            raise PublicJobUrlError(str(exc)) from exc
        except PublicJobUrlError:
            raise
        except Exception as exc:
            raise PublicJobUrlError(
                f"public job URL fetch failed: {exc}"
            ) from exc

        content = bytes(response.content)
        if len(content) > _MAX_BYTES:
            raise PublicJobUrlError("public job URL response is too large")
        content_type = str(
            response.headers.get("content-type", "")
        ).lower()
        if not any(
            allowed in content_type
            for allowed in _ALLOWED_CONTENT_TYPES
        ):
            raise PublicJobUrlError(
                "public job URL content type is not supported"
            )

        body = content.decode("utf-8", errors="replace")
        text = (
            _html_to_text(body)
            if "text/html" in content_type
            else body.strip()
        )
        lowered = text.lower()
        if any(marker.lower() in lowered for marker in _RESTRICTED_MARKERS):
            raise PublicJobUrlError(
                "public job page requires login or verification"
            )
        if len(text) < _MIN_TEXT_CHARS:
            raise PublicJobUrlError(
                "public job page did not contain enough readable text"
            )
        return {
            "final_url": str(response.url),
            "content_type": content_type,
            "truncated": len(text) > _MAX_CHARS,
            "text": text[:_MAX_CHARS],
        }


def _http_client():
    import httpx

    return httpx.Client(
        follow_redirects=False,
        timeout=20.0,
        headers={"User-Agent": "OpenCareer/1.0 (+public-job-preview)"},
    )


def _html_to_text(body: str) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(body)
    except Exception as exc:
        raise PublicJobUrlError(
            "public job page HTML could not be parsed"
        ) from exc
    return re.sub(r"\n{3,}", "\n\n", "\n".join(parser.parts)).strip()
