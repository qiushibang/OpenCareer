"""End-to-end local application table, real interviews and an actual XLSX download."""
import os
import zipfile
import xml.etree.ElementTree as ET

import pytest
from test_local_installation import free_port, running


def choose(scope, page, label, value):
    """Pick a value in the custom OcSelect: open the combobox, click the option by value."""
    scope.get_by_role("combobox", name=label, exact=True).click()
    page.get_by_role("listbox", name=label, exact=True).locator(f'[data-value="{value}"]').click()


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_LOCAL_BROWSER") != "1", reason="opt-in real browser acceptance")
def test_application_table_interview_notes_download_and_restart(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from extensions.career_mcp.config import CareerConfig
    from extensions.career_mcp.crawler.adapters import FakeAdapter
    from extensions.career_mcp.domain.crawler import JobSnapshot
    from extensions.career_mcp.services.crawler import CrawlerService
    from extensions.career_mcp.services.jobs import JobService
    from extensions.career_mcp.services.job_tracking import JobTrackingService
    from start_local import prepare_workspace
    from pathlib import Path
    import sys
    prepare_workspace(tmp_path / "data", Path(sys.executable))
    config = CareerConfig(tmp_path / "data" / "career")
    CrawlerService(config).crawl(FakeAdapter("fixture", [JobSnapshot("old", "历史产品岗位", "投递时的完整JD", "https://example.com/old", "2026-10-30T01:00:00Z", "北京", "experienced")]))
    job = JobService(config).search_jobs()["jobs"][0]
    JobTrackingService(config).update(job["id"], {"expected_version":0,"application_status":"interviewing","note":"原来的面试进度和备注","is_favorite":True})
    port, backend_port = free_port(), free_port()
    with running(tmp_path, port, backend_port), sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width":1500,"height":1000})
            page.goto(f"http://127.0.0.1:{port}")
            page.get_by_role("button", name="岗位雷达", exact=True).click()
            page.get_by_role("button", name="加入／打开求职进度", exact=True).click()
            expect(page.get_by_role("table", name="求职申请总表")).to_be_visible()
            panel = page.get_by_role("dialog", name="申请详情")
            expect(panel.get_by_label("申请备注", exact=True)).to_have_value("原来的面试进度和备注")
            expect(panel.get_by_role("textbox",name="公司名称",exact=True)).to_have_count(0)
            expect(panel.get_by_role("textbox",name="工作地点",exact=True)).to_have_count(0)
            expect(panel.get_by_role("textbox",name="职位描述",exact=True)).to_have_count(0)
            expect(panel.get_by_role("combobox",name="当前阶段",exact=True)).to_be_visible()
            expect(panel.get_by_role("link",name="打开原始岗位链接")).to_be_visible()
            expect(panel.get_by_text("个人期望薪资（含单位）",exact=True)).to_have_count(0)
            panel.get_by_label("申请备注", exact=True).fill("原备注保留；准备二面")
            panel.get_by_role("button", name="保存申请信息", exact=True).click()
            expect(panel.get_by_text("申请已保存", exact=True)).to_be_visible()
            panel.get_by_role("button", name="新增面试", exact=True).click()
            form = panel.get_by_role("form", name="真实面试记录")
            choose(form, page, "面试轮次", "一面")
            form.get_by_label("面试日期年",exact=True).fill("2026")
            expect(form.get_by_label("面试日期月",exact=True)).to_be_focused()
            form.get_by_label("面试日期月",exact=True).fill("11")
            expect(form.get_by_label("面试日期日",exact=True)).to_be_focused()
            form.get_by_label("面试日期日",exact=True).fill("04")
            expect(form.get_by_label("安排状态", exact=True)).to_have_count(0)
            choose(form, page, "本轮结果", "pending")
            expect(form.get_by_label("面试问题", exact=True)).to_have_count(0)
            form.get_by_label("面经", exact=True).fill("一面的完整面经与改进点")
            form.get_by_role("button", name="保存", exact=True).click()
            expect(panel.get_by_role("heading",name="一面",exact=True)).to_be_visible()
            panel.get_by_role("button", name="新增面试", exact=True).click()
            choose(form, page, "面试轮次", "二面")
            form.get_by_label("面经", exact=True).fill("二面的面经单独保留")
            form.get_by_role("button", name="保存", exact=True).click()
            expect(panel.get_by_role("heading",name="二面",exact=True)).to_be_visible()
            panel.get_by_role("button", name="关闭详情", exact=True).click()
            with page.expect_download() as download:
                page.get_by_role("button", name="导出 Excel", exact=True).click()
            file = tmp_path / "applications.xlsx"
            download.value.save_as(file)
            with zipfile.ZipFile(file) as book:
                names = [n.attrib["name"] for n in ET.fromstring(book.read("xl/workbook.xml")).iter() if n.tag.endswith("}sheet")]
                assert names == ["申请总表", "面试记录", "职位描述与面经", "字段说明"]
                content = "\n".join(book.read(name).decode() for name in book.namelist() if name.endswith(".xml"))
                assert "原备注保留；准备二面" in content
                assert "一面的完整面经与改进点" in content and "二面的面经单独保留" in content
            page.reload()
            page.get_by_role("button", name="求职进度", exact=True).click()
            page.get_by_role("button", name="历史产品岗位", exact=True).click()
            expect(page.get_by_label("申请备注", exact=True)).to_have_value("原备注保留；准备二面")
            expect(page.get_by_role("heading",name="一面",exact=True)).to_be_visible()
            expect(page.get_by_role("heading",name="二面",exact=True)).to_be_visible()
            page.get_by_role("button",name="面试与面经",exact=True).click()
            expect(panel.get_by_text("一面的完整面经与改进点",exact=True)).to_be_visible()
            panel.get_by_role("button",name="编辑一面",exact=True).click()
            form.get_by_label("面经",exact=True).fill("取消后不应覆盖")
            form.get_by_role("button",name="取消",exact=True).click()
            expect(panel.get_by_text("一面的完整面经与改进点",exact=True)).to_be_visible()
            panel.get_by_role("button",name="编辑一面",exact=True).click()
            form.get_by_label("面经",exact=True).fill("一面编辑后保存")
            form.get_by_role("button",name="保存",exact=True).click()
            expect(panel.get_by_text("一面编辑后保存",exact=True)).to_be_visible()
            page.once("dialog",lambda dialog:dialog.accept())
            panel.get_by_role("button",name="删除二面",exact=True).click()
            expect(panel.get_by_role("button",name="编辑二面",exact=True)).to_have_count(0)
            expect(panel.get_by_text("一面编辑后保存",exact=True)).to_be_visible()
            page.screenshot(path=str(tmp_path / "application-workspace.png"))
        finally:
            browser.close()


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_LOCAL_BROWSER") != "1", reason="opt-in real browser acceptance")
def test_manual_table_edit_filter_export_and_backend_restart(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    port, backend_port=free_port(),free_port()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1500,"height":1000})
        try:
            with running(tmp_path,port,backend_port):
                page.goto(f"http://127.0.0.1:{port}")
                page.get_by_role("button",name="求职进度",exact=True).click()
                page.get_by_role("button",name="新建申请",exact=True).click()
                create=page.get_by_role("dialog",name="新建申请")
                create.get_by_label("公司名称",exact=True).fill("示例科技")
                create.get_by_label("岗位名称",exact=True).fill("评测产品经理")
                create.get_by_label("工作地点",exact=True).fill("北京")
                create.get_by_role("button",name="创建申请",exact=True).click()
                panel=page.get_by_role("dialog",name="申请详情")
                choose(panel, page, "申请状态", "applied")
                panel.get_by_label("投递日期年",exact=True).fill("2026")
                panel.get_by_label("投递日期月",exact=True).fill("10")
                panel.get_by_label("投递日期日",exact=True).fill("30")
                panel.get_by_label("月薪酬（元／月）",exact=True).fill("25000")
                panel.get_by_label("发薪月数",exact=True).fill("14")
                expect(panel.get_by_label("预计年薪酬",exact=True)).to_contain_text("350,000")
                expect(panel.get_by_role("heading",name="下一步",exact=True)).to_have_count(0)
                panel.get_by_label("申请备注",exact=True).fill("手动新增且重启后保留")
                panel.get_by_role("button",name="保存申请信息",exact=True).click()
                expect(panel.get_by_text("申请已保存", exact=True)).to_be_visible()
                panel.get_by_role("button",name="关闭详情",exact=True).click()
                cell_label="当前阶段：评测产品经理"
                with page.expect_response(lambda r:r.request.method=="PATCH" and "/applications/" in r.url):
                    choose(page, page, cell_label, "笔试")
                page.get_by_text("表格设置",exact=True).click()
                page.get_by_label("月薪酬",exact=True).uncheck()
                page.get_by_text("表格设置",exact=True).click()
                page.get_by_label("搜索求职申请",exact=True).fill("不存在的公司")
                expect(page.get_by_role("button",name="评测产品经理",exact=True)).to_have_count(0)
                page.get_by_label("搜索求职申请",exact=True).fill("示例科技")
                expect(page.get_by_role("button",name="评测产品经理",exact=True)).to_be_visible()
                page.get_by_label("勾选申请：评测产品经理",exact=True).check()
                page.get_by_text("表格设置",exact=True).click()
                choose(page, page, "Excel导出范围", "selected")
                page.get_by_text("表格设置",exact=True).click()
                with page.expect_download() as download:
                    page.get_by_role("button",name="导出 Excel",exact=True).click()
                path=tmp_path/"selected.xlsx";download.value.save_as(path)
                with zipfile.ZipFile(path) as book:
                    text="\n".join(book.read(name).decode() for name in book.namelist() if name.endswith(".xml"))
                    assert "350000" in text and "25000" in text and "笔试" in text and "手动新增且重启后保留" in text
                page.screenshot(path=str(tmp_path/"applications-table.png"))
            with running(tmp_path,port,backend_port):
                page.goto(f"http://127.0.0.1:{port}")
                page.get_by_role("button",name="求职进度",exact=True).click()
                expect(page.get_by_label("搜索求职申请",exact=True)).to_have_value("示例科技")
                expect(page.get_by_label("当前阶段：评测产品经理",exact=True)).to_have_value("笔试")
                expect(page.get_by_role("columnheader",name="月薪酬",exact=True)).to_have_count(0)
                page.get_by_role("button",name="评测产品经理",exact=True).click()
                expect(page.get_by_label("申请备注",exact=True)).to_have_value("手动新增且重启后保留")
        finally:
            browser.close()
