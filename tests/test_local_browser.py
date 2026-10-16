"""Real local browser smoke test; opt in with OPENCAR_TEST_LOCAL_BROWSER=1.

Requires the optional Playwright testing package and Chromium. No paid model calls.
"""
import os

import pytest

from test_local_installation import free_port, running


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
