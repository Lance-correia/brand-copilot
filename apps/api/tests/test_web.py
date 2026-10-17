from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.web import mount_web

def test_single_app_serves_ui_and_keeps_api_and_asset_404s(tmp_path):
    (tmp_path/'index.html').write_text('<html>Studio build</html>')
    (tmp_path/'assets').mkdir();(tmp_path/'assets/app-test.js').write_text('const studio=true;')
    app=FastAPI()
    @app.get('/api/health')
    def health():return {'ok':True}
    mount_web(app,tmp_path)
    client=TestClient(app)
    for path in ['/','/w/ws_demo/studio?thread=thr_demo','/w/ws_demo/editor']:
        result=client.get(path)
        assert result.status_code==200 and 'Studio build' in result.text
        assert result.headers['cache-control']=='no-store'
    assert client.get('/api/health').json()=={'ok':True}
    assert client.get('/api/missing').status_code==404
    assert client.get('/assets/missing.js').status_code==404
    assert 'immutable' in client.get('/assets/app-test.js').headers['cache-control']

def test_single_app_requires_a_build(tmp_path):
    with pytest.raises(RuntimeError,match='web build is missing'):mount_web(FastAPI(),tmp_path)
