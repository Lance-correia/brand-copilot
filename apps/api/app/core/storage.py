import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4
from fontTools.ttLib import TTFont
from PIL import Image
from app.schema import Asset, BrandKit
from . import db
from .config import DATA_DIR
from .validation import validate_contract

FONT_MIME = {'.ttf': 'font/ttf', '.otf': 'font/otf', '.woff': 'font/woff', '.woff2': 'font/woff2'}
PAGE_FORMATS = {'PNG', 'JPEG', 'WEBP'}  # guideline slide pages
EXPECTED = {'guideline': 'PDF, PNG, JPG or WebP', 'sample': 'a raster image'}  # kinds that reject SVG

def _ext(filename):
    ext = Path(filename).suffix.lower()
    return ext if re.fullmatch(r'\.[a-z0-9]{1,10}', ext) else '.bin'

def _svg_size(svg):
    box = svg.attrib.get('viewBox', '').replace(',', ' ').split()
    if len(box) == 4:
        return round(float(box[2])), round(float(box[3]))
    w, h = (re.match(r'[\d.]+', svg.attrib.get(k, '')) for k in ('width', 'height'))
    return (round(float(w[0])), round(float(h[0]))) if w and h else (None, None)

def inspect_file(data: bytes, ext, kind):
    """Check the bytes suit the asset kind; return (mime, width, height, meta). Raises ValueError."""
    if kind == 'font':
        try:
            font = TTFont(io.BytesIO(data), lazy=True)
            names = font['name']
            family = str(names.getDebugName(16) or names.getDebugName(1))
            weight = font['OS/2'].usWeightClass if 'OS/2' in font else 400
        except Exception:
            raise ValueError('Not a valid font file')
        return FONT_MIME.get(ext, 'font/ttf'), None, None, {'family': family, 'weight': weight}
    if data.startswith(b'%PDF'):
        if kind != 'guideline':
            raise ValueError(f'PDF files are not valid for kind {kind}')
        return 'application/pdf', None, None, {}
    expected = EXPECTED.get(kind, 'image or SVG')
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            format, (width, height) = image.format, image.size
    except (OSError, ValueError, Image.DecompressionBombError):
        format = None
    if format:
        if kind == 'guideline' and format not in PAGE_FORMATS:
            raise ValueError(f'{format} is not valid for kind guideline (expected {expected})')
        return Image.MIME.get(format, 'application/octet-stream'), width, height, {}
    try:
        svg = ET.fromstring(data)
    except ET.ParseError:
        svg = None
    if svg is not None and svg.tag.rsplit('}', 1)[-1] == 'svg' and kind not in EXPECTED:
        return ('image/svg+xml', *_svg_size(svg), {})
    raise ValueError(f'Not a valid {kind} file (expected {expected})')

def save_asset(ws_id, data: bytes, filename, kind, source, meta=None) -> Asset:
    db.get('Workspace', ws_id)
    filename = Path(filename or 'upload.bin').name
    ext = _ext(filename)
    mime, width, height, found = inspect_file(data, ext, kind)
    asset_id = 'ast_' + uuid4().hex
    asset = Asset(id=asset_id, workspaceId=ws_id, kind=kind, source=source,
                  filename=filename, url=f'/api/files/{asset_id}', mime=mime,
                  width=width, height=height, caption='', tags=[], meta={**found, **(meta or {})})
    body = validate_contract('Asset', asset)
    folder = DATA_DIR / 'files' / ws_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{asset_id}{ext}').write_bytes(data)
    db.put('Asset', asset_id, ws_id, body)
    return asset

def set_caption(asset_id, caption, tags) -> Asset:
    body = db.get('Asset', asset_id)
    body.update(caption=caption, tags=list(tags))
    db.put('Asset', asset_id, body['workspaceId'], validate_contract('Asset', body))
    return Asset.model_validate(body)

def get_asset(asset_id) -> Asset:
    return Asset.model_validate(db.get('Asset', asset_id))

def asset_path(asset_id) -> Path:
    asset = get_asset(asset_id)
    return DATA_DIR / 'files' / asset.workspaceId / f'{asset.id}{_ext(asset.filename)}'

def list_assets(ws_id, kind=None) -> list[Asset]:
    return [Asset.model_validate(a) for a in db.list_records('Asset', ws_id) if not kind or a['kind'] == kind]

def get_brand_kit(ws_id) -> BrandKit:
    kit = BrandKit.model_validate(db.get('BrandKit', ws_id))
    if kit.fonts and not any(r.id=='FONT-FALLBACK' for r in kit.rules):
        return kit
    from app.brand.fonts import FONT_LOCK, ensure_fonts
    with FONT_LOCK:
        kit = BrandKit.model_validate(db.get('BrandKit', ws_id))
        ready = ensure_fonts(kit)
        if ready != kit:
            db.put('BrandKit', ws_id, ws_id, validate_contract('BrandKit', ready))
        return ready
