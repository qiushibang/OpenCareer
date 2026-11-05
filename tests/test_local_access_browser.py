"""Real Chromium, virtual public fixtures, no external network or real credentials."""
import os
from pathlib import Path
import pytest

@pytest.mark.skipif(os.environ.get('OPENCAR_TEST_LOCAL_BROWSER')!='1',reason='opt-in installed browser acceptance')
def test_local_browser_actions_file_scope_and_redirect_guard(tmp_path,monkeypatch):
    from playwright.sync_api import BrowserType
    from coworker.connectors import browser_automation as browser
    from coworker.roots import RootDir
    for key in ['OPENCAR_ALPHA_TEST','OPENCAR_LOCAL_MODE','OPENCAR_LOCAL_ACCESS']:monkeypatch.setenv(key,'1')
    output=tmp_path/'output';output.mkdir();docs=tmp_path/'docs';docs.mkdir();(docs/'resume.txt').write_text('fictional resume')
    outside=tmp_path/'private.txt';outside.write_text('not granted')
    launch=BrowserType.launch
    monkeypatch.setattr(BrowserType,'launch',lambda self,*args,**kwargs:launch(self,*args,**{**kwargs,'headless':True}))
    check=browser.check_url
    monkeypatch.setattr(browser,'check_url',lambda url:None if url.startswith('https://fixture.example/') else check(url))
    original_page=browser._BrowserController.page
    def page_fixture(self):
        page,error=original_page(self)
        if page and not getattr(self,'fixture_set',False):
            self.fixture_set=True
            def serve(route):
                if route.request.url.endswith('/redirect'):
                    route.fulfill(status=302,headers={'Location':'http://127.0.0.1:1/private'})
                else:
                    route.fulfill(content_type='text/html',body='<title>Local fixture</title><h1 id="message">Hello</h1><input id="q"><input id="upload" type="file"><button id="change" onclick="document.querySelector(\'#message\').textContent=\'Clicked\'">Change</button>')
            self._context.route('https://fixture.example/**',serve)
        return page,error
    monkeypatch.setattr(browser._BrowserController,'page',page_fixture)
    controller=browser._BrowserController();monkeypatch.setattr(browser,'_BROWSER',controller)
    tools={tool.__name__:tool for tool in browser.make_browser_automation_tools(roots=[RootDir(output,True),RootDir(docs,False)])}
    try:
        assert tools['browser_open_url']('https://fixture.example/main')['ok']
        assert 'Hello' in str(tools['browser_snapshot']())
        assert tools['browser_type']('#q','sample')['ok']
        assert tools['browser_click']('#change')['ok']
        assert 'Clicked' in str(tools['browser_snapshot']())
        assert 'error' in tools['browser_upload_file']('#upload',str(outside))
        assert tools['browser_upload_file']('#upload',str(docs/'resume.txt'))['ok']
        assert 'error' in tools['browser_screenshot'](str(docs/'forbidden.png'))
        assert 'error' in tools['browser_screenshot'](str(tmp_path/'escape.png'))
        shot=tools['browser_screenshot']();assert shot['ok'] and Path(shot['path']).is_relative_to(output)
        assert Path(shot['path']).read_bytes().startswith(b'\x89PNG')
        assert 'error' in tools['browser_open_url']('http://127.0.0.1:1/private')
        assert 'error' in tools['browser_open_url']('https://fixture.example/redirect')
    finally:
        controller.close();controller._executor.shutdown(wait=True)
