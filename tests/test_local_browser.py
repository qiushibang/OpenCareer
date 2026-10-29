"""Real local browser smoke test; opt in with OPENCAR_TEST_LOCAL_BROWSER=1.

Requires the optional Playwright testing package and Chromium. No paid model calls.
"""
import os

import pytest

from test_local_installation import free_port, running


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_LOCAL_BROWSER") != "1",
                    reason="opt-in real browser smoke test")
def test_shared_catalog_is_visible_without_a_model_or_local_crawl(tmp_path):
    from dataclasses import asdict
    from playwright.sync_api import sync_playwright, expect
    from extensions.career_mcp.config import CareerConfig
    from extensions.career_mcp.domain.crawler import SourceDescriptor
    from extensions.career_mcp.public_catalog_format import publish_stream
    from extensions.career_mcp.services.public_catalog import PublicCatalogSync

    source = SourceDescriptor("public-fixture", "测试公开来源", "public-company", "测试公开公司", "all",
                              "public-json", "https://careers.example.com")
    timestamp = "2026-10-29T00:00:00Z"
    row = {"external_job_id": "test", "title": "共享目录算法岗位", "description_raw": "负责模型训练、评测与推理优化",
           "source_url": "https://careers.example.com/jobs/test", "location_raw": "北京", "locations": ["北京"],
           "recruitment_type": "experienced", "status": "active", "first_seen_at": timestamp,
           "observed_at": timestamp, "last_changed_at": timestamp, "responsibilities": [], "requirements": []}
    feed = tmp_path / "feed"
    publish_stream(iter([{"kind": "source", "descriptor": asdict(source), "expected_count": 1,
                         "last_success_at": timestamp, "latest_status": "failed"},
                        {"kind": "job", "job": row}, {"kind": "end_source"}, {"kind": "end_feed"}]), feed)
    def fetch(url, max_bytes):
        content = (feed / url.removeprefix("https://feed.example.com/")).read_bytes()
        assert len(content) <= max_bytes
        return content
    port, backend_port = free_port(), free_port()
    with running(tmp_path, port, backend_port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}")
            page.wait_for_load_state("networkidle")
            expect(page.get_by_role("button", name="尚未连接模型，前往连接")).to_be_visible()
            page.get_by_role("button", name="岗位雷达", exact=True).click()
            PublicCatalogSync(CareerConfig(tmp_path / "data" / "career"), base_url="https://feed.example.com/",
                              fetch=fetch, descriptors=[source]).run()
            expect(page.get_by_text("共享目录算法岗位", exact=True).first).to_be_visible(timeout=15000)
            expect(page.get_by_label("官方岗位采集").get_by_role("status")).to_contain_text("公共岗位目录已同步")
            expect(page.get_by_text("1 个岗位", exact=True)).to_be_visible()
            expect(page.get_by_text("负责模型训练、评测与推理优化", exact=True)).to_be_visible()
            page.get_by_text("查看更新暂不可用的来源", exact=True).click()
            expect(page.get_by_text("部分官网最近更新未成功，服务器与本机仍保留上次可用的岗位。", exact=False)).to_be_visible()
        finally:
            browser.close()


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_LOCAL_BROWSER") != "1",
                    reason="opt-in real browser smoke test")
def test_radar_automatically_shows_newly_crawled_jobs_and_retry(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from extensions.career_mcp.config import CareerConfig
    from extensions.career_mcp.crawler.adapters import FakeAdapter
    from extensions.career_mcp.domain.crawler import JobSnapshot
    from extensions.career_mcp.local_jobs import LocalJobSync

    class Unavailable(FakeAdapter):
        def fetch_jobs(self):
            raise RuntimeError("offline fixture")

    config = CareerConfig(tmp_path / "data" / "career")
    snapshot = JobSnapshot(external_job_id="local-fixture", title="自动采集算法岗位",
                           source_url="https://careers.example.com/job/local-fixture",
                           description_raw="负责算法训练与评测", observed_at="2026-10-28T00:00:00Z")
    port, backend_port = free_port(), free_port()
    with running(tmp_path, port, backend_port, job_source="local"), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}")
            page.wait_for_load_state("networkidle")
            page.get_by_role("button", name="岗位雷达", exact=True).click()
            banner = page.get_by_label("官方岗位采集")
            expect(banner.get_by_role("status")).to_contain_text("等待后台加载")
            sync = LocalJobSync(config, adapters=[FakeAdapter("test-official", [snapshot]), Unavailable("unavailable", [])], resumable_adapters=[], pause=0)
            sync.run_cycle()
            expect(page.get_by_text("自动采集算法岗位", exact=True).first).to_be_visible(timeout=15000)
            expect(banner.get_by_role("status")).to_contain_text("1 个来源成功")
            # Avoid the one-minute refresh rate limit, without waiting in the test.
            import json
            status_file = config.data_dir / "local-job-sync.json"
            status = json.loads(status_file.read_text())
            status["updated_at"] -= 61
            status_file.write_text(json.dumps(status))
            banner.get_by_role("button", name="重试采集").click()
            expect(banner.get_by_text("已请求更新，后台将开始处理。")).to_be_visible()
            assert (config.data_dir / "local-job-sync.request").is_file()
            page.screenshot(path=str(tmp_path / "radar-sync.png"))
        finally:
            browser.close()


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_LOCAL_BROWSER") != "1",
                    reason="opt-in real browser smoke test")
def test_local_career_page_and_skills(tmp_path):
    from playwright.sync_api import sync_playwright, expect

    port, backend_port = free_port(), free_port()
    with running(tmp_path, port, backend_port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}")
            page.wait_for_load_state("networkidle")
            expect(page.get_by_role("heading", name="今天从哪里开始？")).to_be_visible()
            composer = page.get_by_role("textbox")
            composer.fill("我想分析一个产品岗位")
            expect(composer).to_have_value("我想分析一个产品岗位")
            # A default model ID is not an API credential. Setup must not send or lose the draft.
            expect(page.get_by_role("button", name="尚未连接模型，前往连接")).to_be_visible()
            page.get_by_role("button", name="发送", exact=True).click()
            dialog = page.get_by_role("dialog", name="配置自定义模型")
            expect(dialog).to_be_visible()
            expect(dialog.get_by_text("密钥仅保存在本机。", exact=False)).to_be_visible()
            dialog.get_by_role("button", name="关闭", exact=True).click()
            expect(composer).to_have_value("我想分析一个产品岗位")
            expect(page.get_by_text("模型请求未完成", exact=False)).to_have_count(0)
            page.get_by_role("button", name="添加附件", exact=True).click()
            page.get_by_role("button", name="导入已粘贴的简历", exact=True).click()
            expect(dialog).to_be_visible()
            dialog.get_by_role("button", name="关闭", exact=True).click()
            expect(composer).to_have_value("我想分析一个产品岗位")
            page.get_by_role("button", name="可用技能", exact=True).click()
            page.get_by_role("button", name="JD 岗位分析 /career-jd-analysis").click()
            expect(page.get_by_role("button", name="移除技能")).to_be_visible()
            expect(composer).to_have_value("我想分析一个产品岗位")
            page.get_by_role("button", name="移除技能").click()
            expect(page.get_by_role("button", name="移除技能")).to_have_count(0)
            page.get_by_role("button", name="设置", exact=True).click()
            page.get_by_role("button", name="模型", exact=True).click()
            expect(page.get_by_role("button", name="DeepSeek（深度求索） 未配置")).to_be_visible()
            expect(page.get_by_text("密钥仅保存在本机。", exact=False)).to_be_visible()
            assert not errors, errors
        finally:
            browser.close()
