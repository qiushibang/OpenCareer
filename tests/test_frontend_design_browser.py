"""Opt-in responsive usability regression. Uses isolated local state, no external services."""
import os
import pytest
from test_local_installation import free_port, running


@pytest.mark.skipif(os.environ.get('OPENCAR_TEST_LOCAL_BROWSER') != '1', reason='opt-in real browser acceptance')
def test_small_screen_navigation_forms_and_reduced_motion(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    port, backend = free_port(), free_port()
    with running(tmp_path, port, backend), sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={'width':390,'height':844}, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}')
            page.wait_for_load_state('networkidle')
            send = page.get_by_role('button', name='发送', exact=True)
            skill = page.get_by_role('button', name='可用技能', exact=True)
            expect(send).to_be_visible()
            assert abs(send.bounding_box()['y'] - skill.bounding_box()['y']) < 15
            # Keyboard must visibly indicate focus; reduced motion must not animate navigation.
            page.keyboard.press('Tab')
            focus = page.evaluate("({outline:getComputedStyle(document.activeElement).outlineStyle,duration:getComputedStyle(document.activeElement).transitionDuration})")
            assert focus['outline'] == 'solid'
            assert all(float(t.strip().removesuffix('s')) < .01 for t in focus['duration'].split(','))
            page.get_by_role('button', name='显示侧边栏', exact=True).click()
            page.get_by_role('button', name='设置', exact=True).click()
            expect(page.get_by_role('button', name='通用', exact=True)).to_be_visible()
            content = page.locator('.oc-settings > div').bounding_box()
            assert content['width'] >= 350  # A usable form, not a squeezed desktop column.
            # Re-entering the current page must close the mobile drawer as well.
            page.get_by_role('button', name='显示侧边栏', exact=True).click()
            page.get_by_role('button', name='设置', exact=True).click()
            expect(page.get_by_role('button', name='关闭侧边栏', exact=True)).to_have_count(0)
            for label in ['岗位雷达', '求职进度', '我的求职档案']:
                page.get_by_role('button', name='显示侧边栏', exact=True).click()
                page.get_by_role('button', name=label, exact=True).click()
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                expect(page.get_by_role('button', name='关闭侧边栏', exact=True)).to_have_count(0)
            page.evaluate("document.documentElement.dataset.theme='dark'")
            assert page.locator('html').get_attribute('data-theme') == 'dark'
            assert not errors
        finally:
            browser.close()


@pytest.mark.skipif(os.environ.get('OPENCAR_TEST_LOCAL_BROWSER') != '1', reason='opt-in real browser acceptance')
def test_application_horizontal_scroll_keeps_headers_and_frozen_columns_aligned(tmp_path):
    from pathlib import Path
    import sys
    from playwright.sync_api import sync_playwright, expect
    from start_local import prepare_workspace
    from extensions.career_mcp.config import CareerConfig
    from extensions.career_mcp.services.applications import Applications

    prepare_workspace(tmp_path / 'data', Path(sys.executable))
    service = Applications(CareerConfig(tmp_path / 'data/career'))
    service.create({'company':'示例公司','title':'策略产品经理 · 智能产品方向','location':'北京','notes':'滚动不应修改数据'})
    port, backend = free_port(), free_port()
    with running(tmp_path, port, backend), sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={'width':1440,'height':1000})
            page.add_init_script("localStorage.setItem('opencareer-applications-view-v3',JSON.stringify({filters:{view:'all',q:'策略产品',company:'不存在的公司',status:'rejected',applied_from:'2099-01-01'},group:'priority'}))")
            page.goto(f'http://127.0.0.1:{port}')
            page.get_by_role('button', name='求职进度', exact=True).click()
            table = page.get_by_role('table', name='求职申请总表')
            expect(table.get_by_role('button', name='策略产品经理 · 智能产品方向', exact=True)).to_be_visible()
            scroller = table.locator('..')
            heads = [table.get_by_role('columnheader', name=label, exact=True) for label in ['公司','岗位名称']]
            cells = [table.locator('tbody tr').first.locator('td').nth(i) for i in [1,2]]
            header=page.locator('.oc-applications > header')
            assert header.get_by_role('textbox').count()==1
            expect(header.get_by_text('更多筛选',exact=True)).to_have_count(0)
            expect(header.get_by_role('combobox',name='按申请状态筛选',exact=True)).to_have_count(0)
            assert header.get_by_role('button',name='新建申请',exact=True).bounding_box()['x']>1080
            for key,maximum in [('monthly_salary',105),('salary_months',90),('annual_salary',125)]:
                cell=table.locator(f'tbody [data-application-column="{key}"]').first
                assert cell.bounding_box()['width']<=maximum
            origin = [cell.bounding_box()['x'] for cell in cells]
            for offset in [0,250,650,10000,0]:
                scroller.evaluate('(element, x) => {element.scrollLeft=x}', offset)
                for i, (head, cell) in enumerate(zip(heads, cells)):
                    hb, cb = head.bounding_box(), cell.bounding_box()
                    assert abs(hb['x'] - cb['x']) < 1, 'header drifted from its data column'
                    assert abs(hb['width'] - cb['width']) < 1
                    assert abs(cb['x'] - origin[i]) < 1, 'frozen column moved while scrolling'
                for label, index in [('工作地点',3),('申请状态',4)]:
                    head = table.get_by_role('columnheader',name=label,exact=True)
                    cell = table.locator('tbody tr').first.locator('td').nth(index)
                    assert abs(head.bounding_box()['x'] - cell.bounding_box()['x']) < 1
                if os.environ.get('OPENCAR_SCREENSHOT_DIR'):
                    output = Path(os.environ['OPENCAR_SCREENSHOT_DIR'])
                    output.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(output / f'application-scroll-{offset}.png'))
                a,b = [cell.bounding_box() for cell in cells]
                assert abs(a['x'] + a['width'] - b['x']) < 1, 'frozen columns overlap or leave a gap'
            # On narrow screens all columns scroll together instead of consuming the viewport.
            page.set_viewport_size({'width':390,'height':844})
            scroller.evaluate('(element) => {element.scrollLeft=300}')
            for head, cell in zip(heads,cells):
                assert abs(head.bounding_box()['x'] - cell.bounding_box()['x']) < 1
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
            for segment in table.locator('.date-input-segment input').all():
                fit=segment.evaluate("element=>{const c=document.createElement('canvas').getContext('2d');const s=getComputedStyle(element);c.font=s.fontWeight+' '+s.fontSize+' '+s.fontFamily;return {available:element.clientWidth,needed:c.measureText(element.placeholder).width}}")
                assert fit['available']>=fit['needed'], 'date placeholder is clipped'
        finally:
            browser.close()


@pytest.mark.skipif(os.environ.get('OPENCAR_TEST_LOCAL_BROWSER') != '1', reason='opt-in real browser acceptance')
def test_application_date_entry_calendar_anchor_and_compact_select(tmp_path):
    from pathlib import Path
    import sys
    from playwright.sync_api import sync_playwright, expect
    from start_local import prepare_workspace
    from extensions.career_mcp.config import CareerConfig
    from extensions.career_mcp.services.applications import Applications

    prepare_workspace(tmp_path / 'data', Path(sys.executable))
    service = Applications(CareerConfig(tmp_path / 'data/career'))
    record = service.create({'company':'示例公司','title':'日期控件验收岗位','location':'北京','status':'preparing'})
    port, backend = free_port(), free_port()
    with running(tmp_path, port, backend), sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={'width':1440,'height':1000})
            page.goto(f'http://127.0.0.1:{port}')
            page.get_by_role('button',name='求职进度',exact=True).click()
            table = page.get_by_role('table',name='求职申请总表')
            year = table.get_by_label('投递日期：日期控件验收岗位年',exact=True)
            month = table.get_by_label('投递日期：日期控件验收岗位月',exact=True)
            day = table.get_by_label('投递日期：日期控件验收岗位日',exact=True)
            year.fill('202611');expect(year).to_have_value('2026')
            expect(month).to_be_focused();month.fill('02');expect(day).to_be_focused();day.fill('30')
            page.get_by_role('heading',name='求职进度',exact=True).click()
            expect(table.get_by_role('alert')).to_contain_text('有效日期')
            assert not service.get(record['id']).get('applied_on')
            day.fill('28')
            with page.expect_response(lambda r:r.request.method=='PATCH' and '/applications/' in r.url):
                page.get_by_role('heading',name='求职进度',exact=True).click()
            assert service.get(record['id'])['applied_on']=='2026-02-28'
            trigger = table.get_by_role('button',name='投递日期：日期控件验收岗位选择日期',exact=True)
            trigger.click()
            calendar = page.get_by_role('dialog',name='投递日期：日期控件验收岗位日历',exact=True)
            expect(calendar).to_be_visible()
            box=calendar.bounding_box();anchor=table.get_by_role('group',name='投递日期：日期控件验收岗位',exact=True).bounding_box()
            expected_left=anchor['x'] if anchor['x']+box['width']<=1428 else anchor['x']+anchor['width']-box['width']
            assert abs(box['x'] - max(12,min(expected_left,1440-box['width']-12)))<2
            assert abs(box['y']-(anchor['y']+anchor['height']+6))<2
            if os.environ.get('OPENCAR_SCREENSHOT_DIR'):
                output=Path(os.environ['OPENCAR_SCREENSHOT_DIR']);output.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(output/'date-calendar.png'))
            with page.expect_response(lambda r:r.request.method=='PATCH' and '/applications/' in r.url):
                calendar.get_by_role('button',name='2026-02-27',exact=True).click()
            expect(calendar).to_have_count(0)
            assert service.get(record['id'])['applied_on']=='2026-02-27'
            status=table.get_by_label('申请状态：日期控件验收岗位',exact=True)
            assert status.bounding_box()['width']<110
            # Scrolling cannot leave an orphaned calendar floating over another column.
            expect(trigger).to_be_enabled();trigger.click();expect(calendar).to_be_visible()
            table.locator('..').evaluate('(element)=>{element.scrollLeft+=100}')
            expect(calendar).to_have_count(0)
            page.reload();page.get_by_role('button',name='求职进度',exact=True).click()
            expect(day).to_have_value('27')
            year.click();year.press('ControlOrMeta+A');year.press_sequentially('20261104')
            expect(year).to_have_value('2026');expect(month).to_have_value('11');expect(day).to_have_value('04')
            with page.expect_response(lambda r:r.request.method=='PATCH' and '/applications/' in r.url):
                page.get_by_role('heading',name='求职进度',exact=True).click()
            assert service.get(record['id'])['applied_on']=='2026-11-04'
            table.get_by_role('button',name='日期控件验收岗位',exact=True).click()
            panel=page.get_by_role('dialog',name='申请详情',exact=True)
            page.set_viewport_size({'width':390,'height':844})
            panel.get_by_role('button',name='投递日期选择日期',exact=True).click()
            mobile_calendar=page.get_by_role('dialog',name='投递日期日历',exact=True)
            expect(mobile_calendar).to_be_visible()
            box=mobile_calendar.bounding_box()
            assert box['x']>=0 and box['x']+box['width']<=390
            assert box['y']>=0 and box['y']+box['height']<=844
            if os.environ.get('OPENCAR_SCREENSHOT_DIR'):
                page.screenshot(path=str(Path(os.environ['OPENCAR_SCREENSHOT_DIR'])/'mobile-date-calendar.png'))
            page.keyboard.press('Escape');expect(mobile_calendar).to_have_count(0);expect(panel).to_be_visible()

        finally:
            browser.close()
