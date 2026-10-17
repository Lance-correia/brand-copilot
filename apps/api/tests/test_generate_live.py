"""Live Prompt 4 checks against real models. Skipped unless RUN_LIVE=1.
Run: cd apps/api && RUN_LIVE=1 python tests/test_generate_live.py"""
import io
import os
import sys
import tempfile
import time
from pathlib import Path

LIVE = os.getenv('RUN_LIVE') == '1'
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='bc-live-')
os.environ['USE_STUBS'] = '0'
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'apps/api'))

from PIL import Image, ImageDraw, ImageFont
from fastapi.testclient import TestClient
from app.brand.lint import lint_design
from app.core import storage
from app.core.fixtures import seed_workspace
from app.core.validation import validate_contract
from app.generate import decompose
from app.llm import images
from app.main import app

WS = 'ws_lumen'
client = TestClient(app)
seed_workspace()
KIT = storage.get_brand_kit(WS)

def make_sample():
    """Flat ad with real words, a button and the Lumen logo (the fixture samples have no text)."""
    im = Image.open(ROOT / 'fixtures/samples/sample-1.png').convert('RGB')
    d = ImageDraw.Draw(im)
    serif = lambda s: ImageFont.truetype(str(ROOT / 'fixtures/brand/fonts/DMSerifDisplay-Regular.ttf'), s)
    sans = ImageFont.truetype(str(ROOT / 'fixtures/brand/fonts/DMSans.ttf'), 34)
    d.text((72, 70), 'Fresh roast,', font=serif(92), fill='#1B1B1F')
    d.text((72, 170), 'slow mornings', font=serif(92), fill='#1B1B1F')
    d.text((72, 285), 'Small-batch beans, roasted every Monday.', font=sans, fill='#1B1B1F')
    d.rounded_rectangle((72, 900, 392, 990), radius=45, fill='#C8553D')
    d.text((232, 945), 'Order now', font=sans, fill='#FBF7F2', anchor='mm')
    d.ellipse((760, 920, 812, 972), fill='#FBF7F2')
    d.text((826, 946), 'Lumen', font=serif(64), fill='#FBF7F2', anchor='lm')
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue()

def post(path, **kw):
    r = client.post(f'/api/workspaces/{WS}{path}', **kw)
    assert r.status_code == 200, (path, r.status_code, r.text[:300])
    return r.json()

def job(job_id):
    # TestClient runs background tasks before returning, so the job is finished here.
    j = client.get(f'/api/jobs/{job_id}').json()
    validate_contract('Job', j)
    assert j['status'] == 'done', j
    return j

def upload_sample():
    return post('/samples', files={'file':('sample.png', make_sample(), 'image/png')})

def test_variants():
    sample = upload_sample()
    validate_contract('DesignSpec', sample['spec'])
    start = time.time()
    j = job(post('/variants', json={'sampleAssetId':sample['asset']['id'], 'brief':'Launch our autumn spiced latte'})['jobId'])
    designs = j['designs']
    assert len(designs) == 4, j['progress']
    assert len({d['name'] for d in designs}) == 4
    for d in designs:
        assert not [v for v in lint_design(d, KIT) if v.severity == 'error'], d['name']
    generated = [l['assetId'] for d in designs for l in d['layers'] if l.get('source') == 'generated']
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor() as pool:
        found = pool.map(lambda a: [e['text'] for e in decompose.read_elements(storage.asset_path(a))
                                    if e['type'] in ('text', 'logo') and e['text'].strip()], generated)
    texts = [t for t in found if t]
    assert not texts, f'generated images contain text: {texts}'
    print(f'  {len(generated)} generated images, no text found')
    print(f'  4 variants in {time.time() - start:.0f}s: ' + '; '.join(d['name'] for d in designs))

def test_decompose():
    sample = upload_sample()
    design = job(post('/decompose', json={'sampleAssetId':sample['asset']['id']})['jobId'])['designs'][0]
    words = ' '.join(l['text'] for l in design['layers'] if l['type'] == 'text').lower()
    assert 'fresh roast' in words and 'order now' in words, words
    logo = [l for l in design['layers'] if l['role'] == 'logo']
    assert logo and logo[0]['source'] == 'brand_asset', 'logo not matched to the brand asset'
    plate = design['layers'][0]
    assert plate['role'] == 'background' and plate['source'] == 'generated'
    left = [e for e in decompose.read_elements(storage.asset_path(plate['assetId'])) if e['type'] == 'text' and e['text'].strip()]
    assert not left, f'plate still has text: {[e["text"] for e in left]}'
    print('  layers:', [(l['type'], l['role'], l.get('text', '')[:20]) for l in design['layers']])

def test_image_edit():
    brand = next(a for a in storage.list_assets(WS, 'image') if a.source == 'brand_asset')
    r = client.post(f'/api/workspaces/{WS}/images/edit', json={'assetId':brand.id, 'instruction':'Make it blue'})
    assert r.status_code == 403 and r.json() == {'error':'Brand assets are locked'}
    generated = next(a for a in storage.list_assets(WS, 'image') if a.source == 'generated')
    asset = post('/images/edit', json={'assetId':generated.id, 'instruction':'Make the light warmer'})
    assert asset['source'] == 'generated' and asset['id'] != generated.id

def generated_design():
    from app.core import db
    return next(d for d in db.list_records('Design', WS)
                if any(l['role'] == 'hero' and l.get('source') == 'generated' for l in d['layers']))

def test_chat_headline_no_image_call():
    design = generated_design()
    head = next(l for l in design['layers'] if l['role'] == 'headline')
    calls = []
    real = images.edit, images.generate
    images.edit = images.generate = lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(RuntimeError('no image calls'))
    try:
        out = post('/chat', json={'design':design, 'selection':[], 'message':'change the headline to Fresh roast'})
    finally:
        images.edit, images.generate = real
    assert not calls
    assert len(out['ops']) == 1 and out['ops'][0]['op'] == 'update_layer', out
    assert out['ops'][0]['layerId'] == head['id'] and out['ops'][0]['props'].get('text') == 'Fresh roast', out

def test_chat_hero_edit():
    design = generated_design()
    hero = next(l for l in design['layers'] if l['role'] == 'hero')
    out = post('/chat', json={'design':design, 'selection':[hero['id']], 'message':'make the hero photo a rainy street'})
    replace = [o for o in out['ops'] if o['op'] == 'replace_image']
    assert replace and replace[0]['layerId'] == hero['id'] and replace[0]['source'] == 'generated', out
    new = storage.get_asset(replace[0]['assetId'])
    assert new.source == 'generated' and new.id != hero['assetId']

if __name__ == '__main__':
    if not LIVE:
        sys.exit('Set RUN_LIVE=1 to call real models')
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            t = time.time()
            try:
                fn()
                print(f'PASS {name} ({time.time() - t:.0f}s)')
            except Exception as exc:
                failed += 1
                print(f'FAIL {name}: {type(exc).__name__}: {str(exc)[:500]}')
    sys.exit(1 if failed else 0)
elif not LIVE:
    import pytest
    pytest.skip('Set RUN_LIVE=1 to call real models', allow_module_level=True)
