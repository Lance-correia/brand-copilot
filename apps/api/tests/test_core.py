import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('BRAND_TEST_DATA', tempfile.mkdtemp(prefix='brand-test-'))
os.environ['DATA_DIR'] = os.environ['BRAND_TEST_DATA']
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import DATA_DIR, FIXTURES
from app.core.validation import validate_contract

client = TestClient(app)

@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    monkeypatch.setenv('USE_STUBS', os.getenv('LIVE_MODELS') and '0' or '1')

def bare_workspace(monkeypatch):
    stub = os.environ['USE_STUBS']
    monkeypatch.setenv('USE_STUBS', '0')  # stub mode would seed fixture assets into the new workspace
    response = client.post('/api/workspaces', json={'name': 'Test brand'})
    monkeypatch.setenv('USE_STUBS', stub)
    assert response.status_code == 201, response.text
    return response.json()['id']

def upload(ws, relative, kind):
    path = FIXTURES / relative
    response = client.post(f'/api/workspaces/{ws}/assets', files={'file': (path.name, path.read_bytes())}, data={'kind': kind})
    assert response.status_code == 201, response.text
    return response.json()

@pytest.mark.parametrize('relative, kind, mime, source, size, meta', [
    ('brand/logo-dark.svg', 'logo', 'image/svg+xml', 'brand_asset', (512, 128), {}),
    ('brand/fonts/DMSans.ttf', 'font', 'font/ttf', 'brand_asset', (None, None), {'family': 'DM Sans', 'weight': 400}),
    ('brand/fonts/DMSerifDisplay-Regular.ttf', 'font', 'font/ttf', 'brand_asset', (None, None), {'family': 'DM Serif Display', 'weight': 400}),
    ('brand/images/coffee-01.png', 'image', 'image/png', 'brand_asset', None, {}),
    ('brand/images/coffee-02.png', 'icon', 'image/png', 'brand_asset', None, {}),
    ('brand/guidelines.pdf', 'guideline', 'application/pdf', 'brand_asset', (None, None), {}),
    ('samples/sample-1.png', 'sample', 'image/png', 'upload', None, {}),
])
def test_upload_each_kind(monkeypatch, relative, kind, mime, source, size, meta):
    from PIL import Image
    ws = bare_workspace(monkeypatch)
    asset = upload(ws, relative, kind)
    validate_contract('Asset', asset)
    if size is None:
        with Image.open(FIXTURES / relative) as image:
            size = image.size
    assert (asset['kind'], asset['mime'], asset['source'], (asset['width'], asset['height'])) == (kind, mime, source, size)
    assert asset['meta'] == meta and asset['caption'] == ''
    stored = DATA_DIR / 'files' / ws / f"{asset['id']}{Path(relative).suffix}"
    assert stored.read_bytes() == (FIXTURES / relative).read_bytes()
    listed = client.get(f'/api/workspaces/{ws}/assets', params={'kind': kind}).json()
    assert [a['id'] for a in listed] == [asset['id']] and listed[0]['caption'], 'background caption should be filled'
    file = client.get(asset['url'])
    assert file.status_code == 200 and file.headers['content-type'].startswith(mime)
    assert 'max-age=31536000' in file.headers['cache-control'] and file.content == stored.read_bytes()

def test_upload_rejects_bad_kind_and_bad_bytes(monkeypatch):
    ws = bare_workspace(monkeypatch)
    png = (FIXTURES / 'samples/sample-1.png').read_bytes()
    for kind, data in (('video', png), ('font', png), ('logo', b'not an image'), ('image', (FIXTURES / 'brand/guidelines.pdf').read_bytes())):
        response = client.post(f'/api/workspaces/{ws}/assets', files={'file': ('x.bin', data)}, data={'kind': kind})
        assert response.status_code == 422 and response.json()['error'], (kind, response.text)
    assert client.get(f'/api/workspaces/{ws}/assets').json() == []
    assert client.post('/api/workspaces/ws_missing/assets', files={'file': ('a.png', png)}, data={'kind': 'image'}).status_code == 404

def test_delete_asset(monkeypatch):
    ws = bare_workspace(monkeypatch)
    asset = upload(ws, 'brand/images/coffee-03.png', 'image')
    assert client.delete(f"/api/assets/{asset['id']}").status_code == 204
    assert client.get(asset['url']).status_code == 404
    assert client.delete(f"/api/assets/{asset['id']}").status_code == 404
    assert not list((DATA_DIR / 'files' / ws).glob(asset['id'] + '.*'))

def upload_brand(ws, with_pdf=True):
    ids = {name: upload(ws, f'brand/{name}', kind)['id'] for name, kind in (
        ('logo-dark.svg', 'logo'), ('logo-light.svg', 'logo'), ('fonts/DMSerifDisplay-Regular.ttf', 'font'), ('fonts/DMSans.ttf', 'font'),
        ('images/coffee-01.png', 'image'), ('images/coffee-04.png', 'image'))}
    if with_pdf:
        upload(ws, 'brand/guidelines.pdf', 'guideline')
    return ids

def test_extract_from_guidelines_pdf(monkeypatch):
    ws = bare_workspace(monkeypatch)
    ids = upload_brand(ws)
    response = client.post(f'/api/workspaces/{ws}/brand-kit/extract')
    assert response.status_code == 200, response.text
    kit = validate_contract('BrandKit', response.json())
    assert len(kit['colors']) >= 3 and not kit['confirmed']
    assert {f['family']: f['assetId'] for f in kit['fonts']} == {
        'DM Serif Display': ids['fonts/DMSerifDisplay-Regular.ttf'], 'DM Sans': ids['fonts/DMSans.ttf']}
    assert {l['assetId']: l['variant'] for l in kit['logos']} == {ids['logo-dark.svg']: 'dark', ids['logo-light.svg']: 'light'}
    assert client.get(f'/api/workspaces/{ws}').json()['brandKitConfirmed'] is False

    kit['confirmed'] = True
    assert client.put(f'/api/workspaces/{ws}/brand-kit', json=kit).status_code == 200
    assert client.get(f'/api/workspaces/{ws}').json()['brandKitConfirmed'] is True
    assert client.get(f'/api/workspaces/{ws}/brand-kit').json() == kit
    kit['workspaceId'] = 'ws_other'
    assert client.put(f'/api/workspaces/{ws}/brand-kit', json=kit).status_code == 422

def test_extract_without_pdf_derives_palette(monkeypatch):
    ws = bare_workspace(monkeypatch)
    upload_brand(ws, with_pdf=False)
    kit = validate_contract('BrandKit', client.post(f'/api/workspaces/{ws}/brand-kit/extract').json())
    assert 3 <= len(kit['colors']) <= 6
    assert {'text', 'background'} <= {c['role'] for c in kit['colors']}
    assert '#1B1B1F' in {c['hex'] for c in kit['colors']}, 'logo SVG ink should be in the palette'
    assert [f['token'] for f in kit['fonts']] == ['headline', 'body']
    assert len(kit['logos']) == 2 and kit['safeMarginPct'] == 6

def test_brand_kit_missing_is_404(monkeypatch):
    ws = bare_workspace(monkeypatch)
    assert client.get(f'/api/workspaces/{ws}/brand-kit').status_code == 404

def test_designs_crud(monkeypatch):
    import json
    ws = bare_workspace(monkeypatch)
    design = json.loads((FIXTURES / 'designs/01-morning.json').read_text())
    design.update(workspaceId=ws, id='des_crud_' + ws[3:11])
    assert client.post(f'/api/workspaces/{ws}/designs', json=design).status_code == 201
    assert client.get(f"/api/designs/{design['id']}").json() == design
    design['name'] = 'Renamed'
    assert client.put(f"/api/designs/{design['id']}", json=design).json()['name'] == 'Renamed'
    assert [d['name'] for d in client.get(f'/api/workspaces/{ws}/designs').json()] == ['Renamed']
    bad = {**design, 'layers': [{**design['layers'][0], 'w': -1}]}
    assert client.put(f"/api/designs/{design['id']}", json=bad).status_code == 422
    assert client.put('/api/designs/des_other', json=design).status_code in (404, 422)
    other = bare_workspace(monkeypatch)
    assert client.post(f'/api/workspaces/{other}/designs', json={**design, 'workspaceId': other}).status_code == 409
    assert client.get('/api/designs/des_missing').status_code == 404

def test_workspaces_and_lint_route(monkeypatch):
    import json
    ws = bare_workspace(monkeypatch)
    assert ws in {w['id'] for w in client.get('/api/workspaces').json()}
    assert client.get(f'/api/workspaces/{ws}').json()['name'] == 'Test brand'
    assert client.get('/api/workspaces/ws_missing').status_code == 404
    upload_brand(ws, with_pdf=False)
    kit = client.post(f'/api/workspaces/{ws}/brand-kit/extract').json()
    design = json.loads((FIXTURES / 'designs/03-violations.json').read_text())
    design.update(workspaceId=ws, background={'colorToken': kit['colors'][0]['token']})
    violations = client.post(f'/api/workspaces/{ws}/lint', json=design)
    assert violations.status_code == 200, violations.text
    for v in violations.json():
        validate_contract('LintViolation', v)
    assert 'SAFE-01' in {v['ruleId'] for v in violations.json()}  # fixture logo ast_01 is not in this kit
    assert client.post(f'/api/workspaces/{ws}/lint', json={**design, 'workspaceId': 'ws_other'}).status_code == 422

@pytest.mark.skipif(not os.getenv('LIVE_MODELS'), reason='set LIVE_MODELS=1 to call DeepSeek')
def test_live_caption(monkeypatch):
    ws = bare_workspace(monkeypatch)
    asset = upload(ws, 'brand/images/coffee-01.png', 'image')
    captioned = client.get(f'/api/workspaces/{ws}/assets').json()[0]
    assert captioned['caption'] and captioned['caption'] != 'Coffee' and captioned['tags'], captioned
