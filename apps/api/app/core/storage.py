import io
import mimetypes
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4
from PIL import Image
from app.schema import Asset, BrandKit
from . import db
from .config import DATA_DIR
from .validation import validate_contract

def save_asset(ws_id, data: bytes, filename, kind, source, meta=None) -> Asset:
    db.get('Workspace', ws_id)
    filename = Path(filename or 'upload.bin').name
    ext = Path(filename).suffix.lower()
    if not re.fullmatch(r'\.[a-z0-9]{1,10}', ext):
        ext = '.bin'
    asset_id = 'ast_' + uuid4().hex
    width = height = None
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
    except (OSError, ValueError):
        if ext == '.svg':
            try:
                svg = ET.fromstring(data)
                box = svg.attrib.get('viewBox', '').replace(',', ' ').split()
                if len(box) == 4:
                    width, height = int(float(box[2])), int(float(box[3]))
            except (ET.ParseError, ValueError):
                pass
    asset = Asset(id=asset_id, workspaceId=ws_id, kind=kind, source=source,
                  filename=filename, url=f'/api/files/{asset_id}',
                  mime=mimetypes.guess_type(filename)[0] or 'application/octet-stream',
                  width=width, height=height, caption=Path(filename).stem.replace('-', ' '), tags=[], meta=meta or {})
    body = validate_contract('Asset', asset)
    folder = DATA_DIR / 'files' / ws_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{asset_id}{ext}').write_bytes(data)
    db.put('Asset', asset_id, ws_id, body)
    return asset

def get_asset(asset_id) -> Asset:
    return Asset.model_validate(db.get('Asset', asset_id))

def asset_path(asset_id) -> Path:
    asset = get_asset(asset_id)
    ext = Path(asset.filename).suffix.lower()
    if not re.fullmatch(r'\.[a-z0-9]{1,10}', ext):
        ext = '.bin'
    return DATA_DIR / 'files' / asset.workspaceId / f'{asset.id}{ext}'

def list_assets(ws_id, kind=None) -> list[Asset]:
    return [Asset.model_validate(a) for a in db.list_records('Asset', ws_id) if not kind or a['kind'] == kind]

def get_brand_kit(ws_id) -> BrandKit:
    return BrandKit.model_validate(db.get('BrandKit', ws_id))
