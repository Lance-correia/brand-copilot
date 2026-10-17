import os
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path

os.environ.setdefault('BRAND_TEST_DATA', tempfile.mkdtemp(prefix='brand-test-'))
os.environ['DATA_DIR'] = os.environ['BRAND_TEST_DATA']
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import socket
import pytest
from app.core import db, storage
from app.core.fixtures import seed_workspace
from app.core.validation import validate_contract
from app.brand import lint
from app.brand.lint import lint_design

WS = 'ws_linttest'

@pytest.fixture(scope='module')
def seeded():
    seed_workspace(WS, 'Lint test')
    return storage.get_brand_kit(WS), {d['name']: d for d in db.list_records('Design', WS)}

def apply(design, ops):
    design = deepcopy(design)
    for op in ops:
        validate_contract('EditOp', op)
        if op['op'] == 'update_layer':
            next(l for l in design['layers'] if l['id'] == op['layerId']).update(op['props'])
        elif op['op'] == 'add_layer':
            design['layers'].insert(op.get('index', len(design['layers'])), op['layer'])
        elif op['op'] == 'set_background':
            design['background'] = op['background']
    return validate_contract('Design', design)

def rule_ids(design, kit):
    return sorted(v.ruleId for v in lint_design(design, kit))

def test_seeded_design_and_fixes(seeded):
    kit, designs = seeded
    bad = designs['Seeded violations']
    violations = lint_design(bad, kit)
    assert sorted(v.ruleId for v in violations) == ['COL-01', 'LOGO-01', 'SAFE-01']
    assert all(v.fix for v in violations)
    fixed = apply(bad, [op.model_dump(mode='json', exclude_unset=True) for v in violations for op in v.fix])
    assert lint_design(fixed, kit) == []

def test_clean_fixtures(seeded):
    kit, designs = seeded
    for name, design in designs.items():
        if name != 'Seeded violations':
            assert lint_design(design, kit) == [], name

def layer(design, role):
    return next(l for l in design['layers'] if l['role'] == role)

def fix_clears(design, kit, rule):
    violation = next(v for v in lint_design(design, kit) if v.ruleId == rule)
    assert violation.fix, rule
    assert rule not in rule_ids(apply(design, [op.model_dump(mode='json', exclude_unset=True) for op in violation.fix]), kit)

def test_individual_rules(seeded):
    kit, designs = seeded
    base = designs['Mornings, slowed down']

    small = deepcopy(base)  # primary text on paper is 4.07:1: fine when large, fails at body size
    layer(small, 'headline').update(colorToken='primary', fontToken='body', fontSize=20)
    assert rule_ids(small, kit) == ['CON-01']
    fix_clears(small, kit, 'CON-01')

    big = deepcopy(base)
    layer(big, 'headline')['fontSize'] = 200
    assert 'FONT-01' in rule_ids(big, kit)
    fix_clears(big, kit, 'FONT-01')

    unknown = deepcopy(base)
    layer(unknown, 'headline')['fontToken'] = 'comic'
    assert rule_ids(unknown, kit) == ['FONT-01']
    fix_clears(unknown, kit, 'FONT-01')

    long = deepcopy(base)
    layer(long, 'headline')['text'] = 'Mornings, slowed down, with a long second line of copy'
    assert rule_ids(long, kit) == ['TEXT-01']
    fix_clears(long, kit, 'TEXT-01')

    crowded = deepcopy(base)
    layer(crowded, 'logo').update(x=410, y=930)  # 18px right of the CTA pill; clear space is 20px
    [violation] = lint_design(crowded, kit)
    assert (violation.ruleId, violation.severity, violation.layerId, violation.fix) == ('CLEAR-01', 'warning', 'lay_3', [])
    assert 'lay_3' in violation.message and 'lay_4' in violation.message

    background = deepcopy(base)
    background['background'] = {'colorToken': 'neon'}
    fix_clears(background, kit, 'COL-01')

def image_design(design, asset_id, fit, text_box, color='ink', size=20):
    design = deepcopy(design)
    hero = {**layer(design, 'hero'), 'assetId': asset_id, 'fit': fit, 'x': 0, 'y': 0, 'w': 1080, 'h': 1080}
    x, y, w, h = text_box
    text = {**layer(design, 'headline'), 'text': 'Hi', 'fontToken': 'body', 'fontSize': size, 'colorToken': color, 'x': x, 'y': y, 'w': w, 'h': h}
    design['layers'] = [hero, text]
    return design

def png(make):
    import io
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (200, 100), 'white')
    make(ImageDraw.Draw(image))
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()

def test_contrast_samples_image_under_text(seeded):
    kit, designs = seeded
    base = designs['Mornings, slowed down']
    # 200x100 image, left quarter black. Cover on a square canvas crops the sides, so the black never shows.
    split = storage.save_asset(WS, png(lambda d: d.rectangle((0, 0, 49, 99), fill='black')), 'split.png', 'image', 'generated').id
    left = (80, 400, 170, 50)
    assert rule_ids(image_design(base, split, 'cover', left), kit) == []
    # Contain letterboxes it to canvas y 270-810, with the black in canvas x 0-270.
    over_black = image_design(base, split, 'contain', left)
    assert rule_ids(over_black, kit) == ['CON-01']
    [violation] = lint_design(over_black, kit)
    assert [op.model_dump(exclude_unset=True) for op in violation.fix] == [
        {'op': 'update_layer', 'layerId': 'lay_2', 'props': {'colorToken': 'paper'}}]
    fix_clears(over_black, kit, 'CON-01')
    # Above the letterbox the text sits on the paper background, which ink passes.
    assert rule_ids(image_design(base, split, 'contain', (80, 100, 170, 50)), kit) == []

def test_contrast_over_mid_tone_image_adds_plate(seeded):
    kit, designs = seeded
    gray = storage.save_asset(WS, png(lambda d: d.rectangle((0, 0, 199, 99), fill='#7F7F7F')), 'gray.png', 'image', 'generated').id
    for color in ('ink', 'paper'):  # neither ink nor paper reaches 4.5:1 on mid gray
        design = image_design(designs['Mornings, slowed down'], gray, 'cover', (300, 500, 200, 50), color)
        [violation] = lint_design(design, kit)
        assert violation.ruleId == 'CON-01' and violation.fix[0].op == 'add_layer'
        plate = violation.fix[0].layer
        assert (plate.role, plate.fillToken, violation.fix[0].index) == ('cta_bg', 'paper', 1)
        fixed = apply(design, [op.model_dump(mode='json', exclude_unset=True) for op in violation.fix])
        assert lint_design(fixed, kit) == [], color

def test_twenty_layers_fast_and_offline(seeded, monkeypatch):
    kit, designs = seeded
    design = deepcopy(designs['Mornings, slowed down'])
    texts = [l for l in design['layers'] if l['type'] == 'text']
    while len(design['layers']) < 20:
        design['layers'].append({**deepcopy(texts[len(design['layers']) % 2]), 'id': f"lay_extra{len(design['layers'])}"})
    def no_network(*args, **kwargs):
        raise AssertionError('lint made a network call')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(socket, 'create_connection', no_network)
    lint._font.cache_clear()
    start = time.perf_counter()
    lint_design(design, kit)
    assert time.perf_counter() - start < 0.2
