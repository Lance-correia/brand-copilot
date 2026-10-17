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
    layer(crowded, 'logo').update(x=380, y=930)  # within half a logo height of the CTA pill
    assert rule_ids(crowded, kit) == ['CLEAR-01']

    background = deepcopy(base)
    background['background'] = {'colorToken': 'neon'}
    fix_clears(background, kit, 'COL-01')

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
