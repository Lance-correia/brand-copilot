from uuid import uuid4
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from app.schema import Asset, Design, DesignSpec, EditOp, Job
from app.core import db, storage
from app.core.config import use_stubs
from app.core.fixtures import read_fixture, variant_designs
from app.core.validation import validate_contract

router = APIRouter(prefix='/api')

class SampleResult(BaseModel):
    asset: Asset
    spec: DesignSpec
class SampleRequest(BaseModel):
    sampleAssetId: str
    brief: str | None = None
class JobResult(BaseModel):
    jobId: str
class EditRequest(BaseModel):
    assetId: str
    instruction: str = Field(min_length=1)
class ChatRequest(BaseModel):
    design: Design
    selection: list[str]
    message: str
class ChatResult(BaseModel):
    reply: str
    ops: list[EditOp]

def stub_only():
    if not use_stubs():
        raise HTTPException(501, 'Generation implementation belongs to Prompt 4')

def owned_asset(ws, asset_id):
    db.get('Workspace', ws)
    asset = storage.get_asset(asset_id)
    if asset.workspaceId != ws:
        raise HTTPException(404, 'Asset not found in workspace')
    return asset

@router.post('/workspaces/{ws}/samples', response_model=SampleResult)
def upload_sample(ws: str, file: UploadFile = File(...)):
    stub_only()
    asset = storage.save_asset(ws, file.file.read(), file.filename, 'sample', 'upload')
    return SampleResult(asset=asset, spec=DesignSpec.model_validate(read_fixture('samples/spec.json')))

def start_job(ws, body, count):
    stub_only()
    sample = owned_asset(ws, body.sampleAssetId)
    if sample.kind != 'sample':
        raise HTTPException(422, 'A sample asset is required')
    job_id = 'job_' + uuid4().hex
    db.put('JobState', job_id, ws, {'workspaceId':ws, 'designs':variant_designs(ws, count), 'polls':0})
    return JobResult(jobId=job_id)

@router.post('/workspaces/{ws}/decompose', response_model=JobResult)
def decompose(ws: str, body: SampleRequest):
    return start_job(ws, body, 1)

@router.post('/workspaces/{ws}/variants', response_model=JobResult)
def variants(ws: str, body: SampleRequest):
    return start_job(ws, body, 4)

@router.get('/jobs/{jobId}', response_model=Job, response_model_exclude_unset=True)
def poll_job(jobId: str):
    state = db.get('JobState', jobId)
    state['polls'] = min(state['polls'] + 1, len(state['designs']))
    designs = state['designs'][:state['polls']]
    for design in designs:
        db.put('Design', design['id'], state['workspaceId'], validate_contract('Design', design))
    db.put('JobState', jobId, state['workspaceId'], state)
    total = len(state['designs'])
    return Job(id=jobId, status='done' if len(designs) == total else 'running', progress=f'Completed {len(designs)}/{total}', designs=designs, error=None)

@router.post('/workspaces/{ws}/images/edit', response_model=Asset)
def edit_image(ws: str, body: EditRequest):
    asset = owned_asset(ws, body.assetId)
    if asset.source != 'generated':
        raise HTTPException(403, 'Only generated images can be edited with AI')
    stub_only()
    return storage.save_asset(ws, storage.asset_path(asset.id).read_bytes(), 'edited.png', 'image', 'generated')

@router.post('/workspaces/{ws}/chat', response_model=ChatResult, response_model_exclude_unset=True)
def chat(ws: str, body: ChatRequest):
    stub_only()
    db.get('Workspace', ws)
    if body.design.workspaceId != ws:
        raise HTTPException(422, 'Workspace id mismatch')
    validate_contract('Design', body.design)
    return ChatResult(reply='Stub copilot: select a layer to begin. Direct edits use the canvas controls.', ops=[])
