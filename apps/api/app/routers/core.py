from uuid import uuid4
from datetime import datetime, timezone
import logging
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.schema import Workspace, Asset, BrandKit, Design, LintViolation
from app.core import db, storage
from app.core.captions import caption_asset
from app.core.config import use_stubs
from app.core.fixtures import seed_workspace
from app.core.validation import validate_contract
from app.brand.kit import extract_brand_kit
from app.brand.lint import lint_design

router = APIRouter(prefix='/api')
log = logging.getLogger(__name__)
KINDS = {'logo', 'font', 'image', 'icon', 'guideline', 'sample'}
FILE_HEADERS = {'Cache-Control': 'public, max-age=31536000, immutable', 'X-Content-Type-Options': 'nosniff',
                'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; sandbox"}

class CreateWorkspace(BaseModel):
    name: str = Field(min_length=1)

@router.post('/workspaces', response_model=Workspace, status_code=201)
def create_workspace(body: CreateWorkspace):
    ws_id = 'ws_' + uuid4().hex
    if use_stubs():
        return seed_workspace(ws_id, body.name)
    ws = Workspace(id=ws_id, name=body.name, createdAt=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), brandKitConfirmed=False)
    db.put('Workspace', ws.id, ws.id, validate_contract('Workspace', ws))
    return ws

@router.get('/workspaces', response_model=list[Workspace])
def list_workspaces():
    return db.list_records('Workspace')

@router.get('/workspaces/{ws}', response_model=Workspace)
def get_workspace(ws: str):
    return db.get('Workspace', ws)

@router.post('/workspaces/{ws}/assets', response_model=Asset, status_code=201)
def upload_asset(ws: str, background: BackgroundTasks, file: UploadFile = File(...), kind: str = Form(...), tags: str = Form('')):
    if kind not in KINDS:
        raise HTTPException(422, f'Invalid asset kind {kind!r}; expected one of {", ".join(sorted(KINDS))}')
    try:
        asset = storage.save_asset(ws, file.file.read(), file.filename, kind, 'upload' if kind == 'sample' else 'brand_asset')
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    user_tags = list(dict.fromkeys(t.strip().lower() for t in tags.split(',') if t.strip()))
    if user_tags:
        asset = storage.set_caption(asset.id, '', user_tags)
    background.add_task(caption_asset, asset.id)
    return asset

@router.get('/workspaces/{ws}/assets', response_model=list[Asset])
def list_assets(ws: str, kind: str | None = None):
    db.get('Workspace', ws)
    if kind and kind not in KINDS:
        raise HTTPException(422, f'Invalid asset kind {kind!r}')
    return storage.list_assets(ws, kind)

@router.delete('/assets/{id}', status_code=204)
def delete_asset(id: str):
    path = storage.asset_path(id)
    path.unlink(missing_ok=True)
    db.delete('Asset', id)
    return Response(status_code=204)

@router.get('/files/{assetId}')
def get_file(assetId: str):
    asset = storage.get_asset(assetId)
    path = storage.asset_path(assetId)
    if not path.is_file():
        raise HTTPException(404, 'Asset file not found')
    return FileResponse(path, media_type=asset.mime, headers=FILE_HEADERS)

@router.post('/workspaces/{ws}/brand-kit/extract', response_model=BrandKit)
def extract_kit(ws: str):
    db.get('Workspace', ws)
    try:
        kit = extract_brand_kit(ws)
    except Exception as exc:
        log.exception('Brand extraction failed for %s', ws)
        raise HTTPException(502, f'Brand extraction failed: {type(exc).__name__}')
    return save_kit(ws, kit)

@router.get('/workspaces/{ws}/brand-kit', response_model=BrandKit)
def get_kit(ws: str):
    return storage.get_brand_kit(ws)

@router.put('/workspaces/{ws}/brand-kit', response_model=BrandKit)
def save_kit(ws: str, kit: BrandKit):
    workspace = db.get('Workspace', ws)
    if kit.workspaceId != ws:
        raise HTTPException(422, 'Workspace id mismatch')
    from app.brand.fonts import ensure_fonts
    kit = ensure_fonts(kit)
    db.put('BrandKit', ws, ws, validate_contract('BrandKit', kit))
    workspace['brandKitConfirmed'] = kit.confirmed
    db.put('Workspace', ws, ws, workspace)
    return kit

@router.post('/workspaces/{ws}/lint', response_model=list[LintViolation], response_model_exclude_unset=True)
def lint(ws: str, design: Design):
    if design.workspaceId != ws:
        raise HTTPException(422, 'Workspace id mismatch')
    validate_contract('Design', design)
    return lint_design(design, storage.get_brand_kit(ws))

@router.get('/workspaces/{ws}/designs', response_model=list[Design], response_model_exclude_unset=True)
def list_designs(ws: str):
    db.get('Workspace', ws)
    return db.list_records('Design', ws)

def checked_design(design):
    from app.core.quality import assess
    body=design.model_dump(mode='json',exclude_unset=True)
    for asset_id in body.get('provenance',{}).values():
        if storage.get_asset(asset_id).workspaceId!=design.workspaceId:
            raise HTTPException(422,'Comparison asset belongs to another workspace')
    try: kit=storage.get_brand_kit(design.workspaceId)
    except KeyError: kit=None  # Designs can be saved before a kit has been extracted.
    if kit:body=assess(body,kit)
    return validate_contract('Design',body)

@router.post('/workspaces/{ws}/designs', response_model=Design, status_code=201, response_model_exclude_unset=True)
def create_design(ws: str, design: Design):
    db.get('Workspace', ws)
    if design.workspaceId != ws:
        raise HTTPException(422, 'Workspace id mismatch')
    try:
        if db.get('Design', design.id)['workspaceId'] != ws:
            raise HTTPException(409, 'Design id belongs to another workspace')
    except KeyError:
        pass
    checked=checked_design(design)
    db.put('Design',design.id,ws,checked)
    return checked

@router.get('/designs/{id}', response_model=Design, response_model_exclude_unset=True)
def get_design(id: str):
    return db.get('Design', id)

@router.put('/designs/{id}', response_model=Design, response_model_exclude_unset=True)
def save_design(id: str, design: Design):
    previous = db.get('Design', id)
    if id != design.id or previous['workspaceId'] != design.workspaceId:
        raise HTTPException(422, 'Design identity mismatch')
    checked=checked_design(design)
    db.put('Design',id,design.workspaceId,checked)
    return checked
