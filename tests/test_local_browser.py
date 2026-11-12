"""Real local browser smoke test; opt in with OPENCAR_TEST_LOCAL_BROWSER=1.

Requires the optional Playwright testing package and Chromium. No paid model calls.
"""
import os
import json
import re

import pytest

from test_local_installation import free_port, running


def choose(scope, page, label, value):
    """Pick a value in the custom OcSelect: open the combobox, click the option by value."""
    scope.get_by_role("combobox", name=label, exact=True).click()
    page.get_by_role("listbox", name=label, exact=True).locator(f'[data-value="{value}"]').click()


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_LOCAL_BROWSER") != "1",
                    reason="opt-in real browser smoke test")
def test_catalog_uses_ordinary_tool_steps_and_only_renders_final_answer(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    result_id = "a" * 32
    # The stored result is complete (offset 0, all rows), so the chat card uses it
    # directly instead of re-querying the empty local catalog.
    beijing = {"condition":{"all":[{"field":"locations","op":"in","values":["北京"]}]}}
    result = {"total":54, "evaluated_matches":54, "warnings":[], "has_more":False, "offset":0,
              "query":beijing, "jobs":[
                  {"id":str(i), "title":f"测试产品实习岗位{i+1}", "company":{"name":"测试公司"},
                   "locations":["北京"], "first_seen_at":"2026-10-29T00:00:00Z",
                   "match_evidence":[], "source_url":f"https://jobs.example/{i}"} for i in range(54)]}
    messages = [{"role":"user", "content":"找北京产品实习岗位"},
                {"role":"assistant", "tool_calls":[{"id":"query", "type":"function", "function":{"name":"mcp__career__search_job_catalog", "arguments":json.dumps({"condition":{"all":[{"field":"locations","op":"in","values":["北京"]}]}})}}]},
                {"role":"tool", "tool_call_id":"query", "content":json.dumps({"result_id":result_id})},
                {"role":"assistant", "content":"已整合岗位结果，以下是我的建议。"}]
    port, backend_port = free_port(), free_port()
    with running(tmp_path, port, backend_port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width":1440,"height":1000})
            page.route(re.compile(r"/_openworker/v1/sessions(?:\?.*)?$"), lambda route: route.fulfill(json={"sessions":[{
                "session_id":"catalog-preview", "title":"工具结果折叠验收", "agent":"career", "mode":"custom",
                "workspace":str(tmp_path / "data" / "workspace"), "model":"deepseek:deepseek-v4-flash",
                "messages":4, "updated_at":"2026-10-29 12:00:00", "liveness":"idle"}]}))
            page.route("**/_openworker/v1/sessions/catalog-preview/messages", lambda route: route.fulfill(json={"messages":messages}))
            page.route(f"**/_openworker/v1/career/catalog/results/{result_id}", lambda route: route.fulfill(json={"ok":True,"data":result}))
            page.goto(f"http://127.0.0.1:{port}")
            page.get_by_text("工具结果折叠验收", exact=True).click()
            expect(page.get_by_role("button", name=re.compile("匹配 54 个岗位"))).to_have_count(0)
            expect(page.get_by_role("region", name="岗位工具结果明细")).to_have_count(0)
            # The chat shows the first 10 matches as cards, never the raw tool payload.
            cards = page.get_by_role("region", name="代表岗位")
            expect(cards.get_by_text("测试产品实习岗位1", exact=True)).to_be_visible()
            expect(cards.get_by_text("测试产品实习岗位10", exact=True)).to_be_visible()
            expect(page.get_by_text("测试产品实习岗位11", exact=True)).to_have_count(0)
            expect(cards.get_by_text("共 54 个", exact=True)).to_be_visible()
            expect(page.get_by_text("已整合岗位结果，以下是我的建议。", exact=True)).to_be_visible()
            screenshot = tmp_path / "catalog-collapsed.png"
            page.screenshot(path=str(screenshot))
            print(f"Collapsed UI proof: {screenshot}")
            with page.expect_request(lambda req:"/career/catalog/search" in req.url and req.method=="POST") as navigation:
                page.get_by_role("button",name="查看更多岗位",exact=True).click()
            assert navigation.value.post_data_json["condition"]=={"all":[{"field":"locations","op":"in","values":["北京"]}]}
            expect(page.get_by_text("清除组合条件",exact=True)).to_be_visible()
            page.route("**/_openworker/v1/career/jobs/sync",lambda route:route.fulfill(json={"ok":True,"queued":True}) if route.request.method=="POST" else route.continue_())
            page.get_by_role("button",name="一键同步岗位",exact=True).click()
            expect(page.get_by_text("已请求同步，完成后岗位列表会自动更新。",exact=True)).to_be_visible()
            page.get_by_text("工具结果折叠验收",exact=True).click()
            page.get_by_role("button",name="配置岗位订阅",exact=True).click()
            dialog=page.get_by_role("dialog",name="岗位订阅")
            expect(dialog).to_be_visible()
            # Only the platform approval transport is simulated; the actual local channel/draft APIs persist fixtures.
            from extensions.career_mcp.config import CareerConfig
            from extensions.career_mcp.services.job_subscriptions import JobSubscriptions
            def approved(route):
                channel=JobSubscriptions(CareerConfig(tmp_path/"data"/"career")).save_feishu_app("cli_fixture","fixture-secret-private","ou_fixtureowner")
                route.fulfill(json={"ok":True,"data":{"state":"connected","channel":channel}})
            page.route("**/_openworker/v1/career/job-subscriptions/feishu-pairing",lambda route:route.fulfill(json={"ok":True,"data":{"session_id":"b"*48,"qr_image":"data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnLz4=","verification_url":"https://accounts.feishu.cn/fixture","interval":5,"expires_in":600}}))
            page.route("**/_openworker/v1/career/job-subscriptions/feishu-pairing/"+"b"*48+"/poll",approved)
            dialog.get_by_text("推送渠道 · 尚未连接",exact=True).click()  # Channel settings are folded by design.
            dialog.get_by_role("button",name="生成飞书授权二维码",exact=True).click()
            expect(dialog.get_by_alt_text("飞书官方授权二维码")).to_be_visible()
            expect(dialog.get_by_text("我的飞书（扫码绑定）",exact=True).first).to_be_visible(timeout=12000)
            expect(dialog.get_by_role("checkbox",name="我的飞书（扫码绑定）")).to_be_checked()
            page.route("**/_openworker/v1/career/job-subscriptions/channels/*/check",lambda route:route.fulfill(json={"ok":True,"data":{"status":"failed","diagnostic":{"message":"飞书访问控制策略拒绝了当前应用","platform_code":21001}}}))
            dialog.get_by_role("button",name="检查连接（不发消息）",exact=True).click()
            expect(dialog.get_by_text(re.compile("飞书访问控制策略拒绝了当前应用.*21001"))).to_be_visible()
            dialog.get_by_role("button",name="保存订阅草稿",exact=True).click()
            expect(dialog.get_by_role("button",name="确认启用",exact=True)).to_be_visible()
            page.screenshot(path=str(tmp_path/"feishu-scan-setup.png"))

        finally:
            browser.close()


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
            expect(page.get_by_label("官方岗位采集")).to_have_count(0)
            expect(page.get_by_text("1 个岗位", exact=True)).to_be_visible()
            expect(page.get_by_text("负责模型训练、评测与推理优化", exact=True)).to_be_visible()
            expect(page.get_by_text("首次发现", exact=True)).to_have_count(0)
            expect(page.get_by_text("历史补录", exact=True)).to_be_visible()
            page.get_by_role("button", name="组合筛选", exact=True).click()
            form = page.get_by_role("form", name="组合岗位筛选")
            form.get_by_label("工作城市", exact=True).fill("北京")
            choose(form, page, "岗位职能", "algorithm")
            form.get_by_role("button", name="应用筛选").click()
            expect(page.get_by_text("1 个岗位", exact=True)).to_be_visible()
            page.get_by_role("button", name="岗位订阅", exact=True).click()
            dialog = page.get_by_role("dialog", name="岗位订阅")
            expect(dialog).to_be_visible()
            expect(dialog.get_by_role("button",name="保存订阅草稿",exact=True)).to_have_count(0)
            dialog.get_by_role("button",name="在对话中创建订阅",exact=True).click()
            expect(page.get_by_role("heading",name="想每天收到哪些岗位？",exact=True)).to_be_visible()
            expect(page.get_by_role("textbox")).to_have_value("")
            page.get_by_role("button",name="每天早上9点，把字节跳动北京的产品岗发到我的飞书。",exact=True).click()
            expect(page.get_by_role("textbox")).to_have_value("每天早上9点，把字节跳动北京的产品岗发到我的飞书。")
            # Simulate the model's structured query handoff, not its reasoning or
            # a paid request. Channel save, draft, preview and activation remain real.
            subscription_condition={"all":[{"field":"locations","op":"in","values":["北京"]},{"field":"job_family","op":"in","values":["algorithm"]}]}
            page.evaluate("""condition => {
              sessionStorage.setItem('opencareer-catalog-query',JSON.stringify({condition}));
              sessionStorage.setItem('opencareer-subscription-query',JSON.stringify({title:'北京算法日报'}));
              window.dispatchEvent(new Event('opencareer:catalog-open'));
            }""",subscription_condition)
            expect(dialog.get_by_text("确认 AI 整理的订阅",exact=True)).to_be_visible()
            dialog.get_by_text("推送渠道 · 尚未连接",exact=True).click()  # Channel settings are folded by design.
            dialog.get_by_text("其他平台／已有群机器人",exact=True).click()
            choose(dialog, page, "机器人平台", "wecom")
            dialog.get_by_text("名称与安全设置（按平台要求填写）",exact=True).click()
            dialog.get_by_label("渠道名称（可选）", exact=True).fill("本地验收测试群")
            dialog.get_by_label("官方 Webhook 地址").fill("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fixture")
            dialog.get_by_role("button", name="保存渠道", exact=True).click()
            expect(dialog.get_by_text("渠道已保存。", exact=False)).to_be_visible()
            dialog.get_by_role("checkbox", name="本地验收测试群").check()
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            later = datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(hours=6)
            dialog.get_by_label("每日发送时间（北京时间）").fill(later.strftime("%H:%M"))
            dialog.get_by_role("button", name="保存订阅草稿", exact=True).click()
            expect(dialog.get_by_role("button", name="确认启用", exact=True)).to_be_visible()
            from extensions.career_mcp.services.job_subscriptions import JobSubscriptions
            saved_subscription=JobSubscriptions(CareerConfig(tmp_path/"data"/"career")).list()[0]
            assert saved_subscription['condition']==subscription_condition
            assert saved_subscription['enabled'] is False
            dialog.get_by_role("button", name="预览匹配结果").click()
            expect(dialog.get_by_text("匹配预览：1 项", exact=True)).to_be_visible()
            dialog.get_by_role("button", name="确认启用", exact=True).click()
            expect(dialog.get_by_role("button", name="暂停", exact=True)).to_be_visible()
            dialog.get_by_role("button", name="暂停", exact=True).click()
            expect(dialog.get_by_role("button", name="确认启用", exact=True)).to_be_visible()
            # Saving metadata and confirming a future schedule never sends a test message.
            dialog.get_by_role("button", name="移除渠道", exact=True).click()
            expect(dialog.get_by_role("button", name="发送测试消息", exact=True)).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_LOCAL_BROWSER") != "1",
                    reason="opt-in real browser smoke test")
def test_radar_refreshes_jobs_without_exposing_operations_banner(tmp_path):
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
            expect(banner).to_have_count(0)
            sync = LocalJobSync(config, adapters=[FakeAdapter("test-official", [snapshot]), Unavailable("unavailable", [])], resumable_adapters=[], pause=0)
            sync.run_cycle()
            expect(page.get_by_text("自动采集算法岗位", exact=True).first).to_be_visible(timeout=15000)
            expect(banner).to_have_count(0)
            expect(page.get_by_role("button", name="重试采集", exact=True)).to_have_count(0)
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
            page.get_by_role("button",name="显示侧边面板",exact=True).click()
            expect(page.locator(".right-rail")).to_be_visible()
            expect(page.get_by_test_id("access-section")).to_be_visible()
            page.get_by_test_id("access-toggle").click()
            expect(page.get_by_role("button",name="+ 添加可访问文件夹",exact=True)).to_be_visible()
            expect(page.get_by_text("+ Add a source…",exact=True)).to_have_count(0)
            documents=tmp_path/"documents";documents.mkdir()
            (documents/"resume.txt").write_text("Fictitious browser acceptance document")
            page.get_by_role("button",name="+ 添加可访问文件夹",exact=True).click()
            expect(page.get_by_role("checkbox",name="允许写入",exact=True)).not_to_be_checked()
            page.get_by_placeholder("选择或粘贴文件夹路径…").fill(str(documents))
            page.get_by_role("button",name="添加",exact=True).click()
            row=page.locator(".root-row").filter(has=page.get_by_text("documents",exact=True))
            expect(row.get_by_role("button",name="只读",exact=True)).to_be_visible()
            row.get_by_role("button",name="移除",exact=True).click()
            expect(row).to_have_count(0)
            if os.environ.get("OPENCAR_SCREENSHOT_DIR"):
                from pathlib import Path
                output=Path(os.environ["OPENCAR_SCREENSHOT_DIR"]);output.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(output/"career-web-right-panel.png"))
            page.get_by_role("button",name="管理已连接的服务 →",exact=True).click()
            expect(page.get_by_role("heading",name="连接器",exact=True)).to_be_visible()
            expect(page.get_by_role("button",name="MCP 服务",exact=True)).to_have_count(0)
            page.get_by_role("button",name="新建对话",exact=True).click()
            page.get_by_role("button",name="隐藏侧边面板",exact=True).click()
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
