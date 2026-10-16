from __future__ import annotations

import pytest

from extensions.career_mcp.services.public_job_url import (
    PublicJobUrlError,
    PublicJobUrlService,
)


class _Response:
    def __init__(
        self,
        *,
        text: str,
        content_type: str = "text/html; charset=utf-8",
        url: str = "https://careers.example.com/jobs/1",
        status_code: int = 200,
    ) -> None:
        self.content = text.encode("utf-8")
        self.headers = {"content-type": content_type}
        self.url = url
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Client:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _service(response: _Response) -> PublicJobUrlService:
    return PublicJobUrlService(
        client_factory=lambda: _Client(),
        checked_get=lambda _client, _url: response,
    )


def test_public_job_url_extracts_visible_html_text() -> None:
    service = _service(
        _Response(
            text=(
                "<html><head><style>hidden</style></head><body>"
                "<h1>大模型算法工程师</h1>"
                "<p>岗位职责：负责大模型训练、评测和部署。</p>"
                "<p>岗位要求：熟悉 Python、PyTorch 和分布式训练，"
                "能够分析线上效果并持续优化模型。</p>"
                "</body></html>"
            )
        )
    )

    result = service.preview("https://careers.example.com/jobs/1")

    assert result["final_url"] == "https://careers.example.com/jobs/1"
    assert "大模型算法工程师" in result["text"]
    assert "hidden" not in result["text"]
    assert result["truncated"] is False


def test_public_job_url_rejects_private_redirect() -> None:
    def reject(_client, _url):
        raise PermissionError(
            "refusing to fetch 169.254.169.254: link-local"
        )

    service = PublicJobUrlService(
        client_factory=lambda: _Client(),
        checked_get=reject,
    )

    with pytest.raises(PublicJobUrlError, match="refusing to fetch"):
        service.preview("https://careers.example.com/jobs/1")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            _Response(
                text="binary",
                content_type="application/pdf",
            ),
            "content type",
        ),
        (
            _Response(
                text="<html><body>请登录后查看职位</body></html>",
            ),
            "login or verification",
        ),
        (
            _Response(text="x" * (2 * 1024 * 1024 + 1)),
            "too large",
        ),
    ],
)
def test_public_job_url_rejects_unsafe_or_unusable_content(
    response: _Response,
    message: str,
) -> None:
    with pytest.raises(PublicJobUrlError, match=message):
        _service(response).preview("https://careers.example.com/jobs/1")
