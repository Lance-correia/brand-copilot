"""Offline checks for Prompt 4 (no keys, no network). Run: cd apps/api && python tests/test_generate.py (or pytest)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='bc-test-')
os.environ.setdefault('USE_STUBS', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.core import db, storage
from app.core.fixtures import seed_workspace
from app.core.validation import validate_contract
from app.generate import chat, common as c, decompose, variants
from app.llm import images
from app.main import app

seed_workspace()
WS = 'ws_lumen'
KIT = storage.get_brand_kit(WS)

def test_image_size_rules():
    for w, h in [(1080, 1080), (518, 1080), (1080, 100), (50, 2000), (1080, 648)]:
        width, height = images.image_size(w, h)
        assert width % 16 == 0 and height % 16 == 0
        assert 1 / 3 <= width / height <= 3
    assert images.image_prompt('A cup').endswith('No text, letters, logos or watermarks.')

def test_working_size():
    s, (w, h), (pw, ph) = decompose.working_size(1080, 1080)
    assert (s, w, h) == (1, 1080, 1080) and (pw, ph) == (1088, 1088)
    s, (w, h), (pw, ph) = decompose.working_size(4000, 500)
    assert pw % 16 == 0 and ph % 16 == 0 and pw / ph <= 3 and pw >= w and ph >= h

def test_font_size_in_range():
    font = c.font_for(KIT, 'headline')
    assert c.fit_font_size('Hi', 900, 200, font) == font.maxSize
    assert c.fit_font_size('A very long headline that cannot possibly fit ' * 4, 300, 60, font) == font.minSize

def test_corner_radius():
    im = Image.new('RGB', (300, 100), 'white')
    ImageDraw.Draw(im).rounded_rectangle((0, 0, 299, 99), radius=40, fill='red')
    assert 30 <= decompose.corner_radius(im, (255, 0, 0)) <= 50

def test_build_is_valid_and_on_brand():
    asset = storage.list_assets(WS, 'image')[0]
    for t in c.templates():
        plan = {'templateId':t['id'], 'angle':'Slow mornings',
                'copy':{'headline':'Mornings, slowed down', 'subhead':'Small batch beans', 'cta':'Find yours'},
                'assetPicks':[{'role':'hero', 'assetId':asset.id}], 'imagePrompts':[],
                'colors':{'background':'paper', 'accent':'primary', 'text':'ink'}}
        design, pending = variants.build(t, plan, KIT, WS, 'Test')
        assert not pending
        design, issues = c.lint_fix(variants.finish(design, KIT, 'ink'), KIT)
        validate_contract('Design', design)
        assert not [v for v in issues if v.severity == 'error'], (t['id'], issues)
    assert len(c.templates()) >= 6 and {'4:5', '9:16'} <= {t['aspect'] for t in c.templates()}

def test_chat_op_validation():
    design = db.list_records('Design', WS)[0]
    head = next(l for l in design['layers'] if l['role'] == 'headline')
    chat.check_op(design, KIT, {'op':'update_layer', 'layerId':head['id'], 'props':{'text':'Fresh roast'}})
    for bad in [{'op':'update_layer', 'layerId':'lay_missing', 'props':{'text':'x'}},
                {'op':'update_layer', 'layerId':head['id'], 'props':{'colorToken':'#FF0000'}},
                {'op':'update_layer', 'layerId':head['id'], 'props':{'fillToken':'primary'}},
                {'op':'set_background', 'background':{'colorToken':'neon'}}]:
        try:
            chat.check_op(design, KIT, bad)
        except ValueError:
            continue
        raise AssertionError(f'accepted {bad}')
    brand = next(l for l in design['layers'] if l['type'] == 'image' and l['source'] == 'brand_asset')
    try:
        chat.to_ops(WS, design, KIT, 'edit_generated_image', {'layerId':brand['id'], 'instruction':'make it blue'})
        raise AssertionError('brand asset edit allowed')
    except ValueError as exc:
        assert 'locked' in str(exc)

def test_image_edit_rejects_brand_asset_without_model_call():
    logo = storage.list_assets(WS, 'logo')[0]
    os.environ['USE_STUBS'] = '0'
    try:
        r = TestClient(app).post(f'/api/workspaces/{WS}/images/edit', json={'assetId':logo.id, 'instruction':'blue'})
    finally:
        os.environ['USE_STUBS'] = '1'
    assert r.status_code == 403 and r.json() == {'error':'Brand assets are locked'}

def test_failed_image_becomes_accent_placeholder():
    t = c.templates()[0]
    plans = [{'templateId':t['id'], 'angle':f'Angle {i}', 'copy':{'headline':'Fresh roast', 'subhead':'Beans', 'cta':'Order'},
              'assetPicks':[], 'imagePrompts':[{'role':'hero', 'prompt':'A cup'}],
              'colors':{'background':'paper', 'accent':'primary', 'text':'ink'}} for i in range(4)]
    def fail(*a, **k):
        raise TimeoutError('image model down')
    saved = variants.plan, variants.sample_spec, images.generate
    variants.plan, variants.sample_spec, images.generate = (lambda *a: plans), (lambda s: {}), fail
    try:
        job_id = c.new_job()
        c.run_job(job_id, variants.run_variants, WS, storage.list_assets(WS, 'sample')[0], None)
    finally:
        variants.plan, variants.sample_spec, images.generate = saved
    job = c.JOBS[job_id]
    assert job['status'] == 'done' and len(job['designs']) == 4 and 'placeholder' in job['progress'], job['progress']
    hero = next(l for l in job['designs'][0]['layers'] if l['role'] == 'hero')
    assert hero['type'] == 'shape' and hero['fillToken'] == 'primary'

if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('PASS', name)


def test_short_headline_is_not_mistaken_for_raster_logo(monkeypatch):
    from types import SimpleNamespace
    logo=storage.list_assets(WS,'image')[0]
    kit=SimpleNamespace(logos=[SimpleNamespace(assetId=logo.id)])
    from app.decompose import pipeline
    monkeypatch.setattr(pipeline,'dhash',lambda image:[False]*64)
    # A text crop can share a perceptual hash with a mostly blank raster logo.
    crop=Image.new('RGB',(240,40),'white')
    assert pipeline.match_logo(kit,'Lumen',{'type':'text','text':'Fresh mornings'},crop) is None


def test_local_ink_refines_separate_headline_rows():
    from app.decompose.pipeline import refine_text_boxes
    from PIL import ImageFont
    im=Image.new('RGB',(488,612),'white')
    draw=ImageDraw.Draw(im)
    font=ImageFont.truetype(str(c.FIXTURES/'brand/fonts/DMSans.ttf'),40)
    texts=['Suddenly you are','fluent in finance.']
    for y,text in zip([80,140],texts): draw.text((54,y),text,font=font,fill='#000044')
    elements=[]
    for text,box in zip(texts,[(54,79,400,86),(54,110,400,147)]):
        e={'text':text,'colorHex':'#000044'}
        elements.append((e,box,im.crop(box)))
    refined=refine_text_boxes(elements,im)
    assert refined[0][1][3]-refined[0][1][1]>20
    assert refined[1][1][1]>refined[0][1][3]
