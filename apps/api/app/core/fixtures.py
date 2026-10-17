import json
from copy import deepcopy
from . import db
from .config import FIXTURES
from .storage import save_asset
from .validation import validate_contract
from app.schema import Workspace

def read_fixture(relative):
    return json.loads((FIXTURES / relative).read_text())

def seed_workspace(ws_id='ws_lumen', name='Lumen Coffee') -> Workspace:
    try:
        existing = Workspace.model_validate(db.get('Workspace', ws_id))
        db.get('BrandKit', ws_id)
        if len(db.list_records('Design', ws_id)) >= 3:
            return existing
    except KeyError:
        pass
    workspace = Workspace(id=ws_id, name=name, createdAt='2026-10-17T10:00:00Z', brandKitConfirmed=False)
    db.put('Workspace', ws_id, ws_id, validate_contract('Workspace', workspace))
    mapping = {}
    existing_assets = {a['filename']: a for a in db.list_records('Asset', ws_id)}
    for item in read_fixture('assets.json'):
        filename = PathName(item['path'])
        if filename in existing_assets:
            mapping[item['id']] = existing_assets[filename]['id']
        else:
            asset = save_asset(ws_id, (FIXTURES / item['path']).read_bytes(), filename, item['kind'], item['source'], item.get('meta'))
            mapping[item['id']] = asset.id
    kit = read_fixture('brand/brand-kit.json')
    kit['workspaceId'] = ws_id
    for font in kit['fonts']:
        font['assetId'] = mapping[font['assetId']]
    for logo in kit['logos']:
        logo['assetId'] = mapping[logo['assetId']]
    db.put('BrandKit', ws_id, ws_id, validate_contract('BrandKit', kit))
    for fixture in sorted((FIXTURES / 'designs').glob('*.json')):
        design = json.loads(fixture.read_text())
        design['workspaceId'] = ws_id
        design['id'] = 'des_' + ws_id.removeprefix('ws_') + '_' + fixture.stem
        for layer in design['layers']:
            if 'assetId' in layer:
                layer['assetId'] = mapping[layer['assetId']]
        db.put('Design', design['id'], ws_id, validate_contract('Design', design))
    return workspace

def PathName(path):
    return path.rsplit('/', 1)[-1]

def variant_designs(ws_id, count=4):
    originals = db.list_records('Design', ws_id)
    if not originals:
        raise KeyError('No fixture designs; run scripts/seed.py first')
    from uuid import uuid4
    designs = []
    for i in range(count):
        design = deepcopy(originals[i % len(originals)])
        design['id'] = 'des_' + uuid4().hex
        design['name'] = f'Variant {chr(65 + i)}'
        designs.append(validate_contract('Design', design))
    return designs
