from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from app.schema import Asset, Design, DesignSpec, EditOp, Job
from app.core import db, storage
from app.core.config import use_stubs
from app.core.fixtures import read_fixture, variant_designs
from app.core.validation import validate_contract
from app.generate import common, variants as variant_job

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
    data = file.file.read()
    if use_stubs():
        asset = storage.save_asset(ws, data, file.filename, 'sample', 'upload')
        return SampleResult(asset=asset, spec=DesignSpec.model_validate(read_fixture('samples/spec.json')))
    db.get('Workspace', ws)
    try:
        spec = variant_job.analyze_sample(data, file.filename)
    except Exception as exc:
        raise HTTPException(502, f'Sample analysis failed: {type(exc).__name__}')
    asset = storage.save_asset(ws, data, file.filename, 'sample', 'upload', {'spec':spec})
    return SampleResult(asset=asset, spec=DesignSpec.model_validate(spec))

def sample_for(ws, body):
    sample = owned_asset(ws, body.sampleAssetId)
    if sample.kind != 'sample':
        raise HTTPException(422, 'A sample asset is required')
    storage.get_brand_kit(ws)  # 404 early when there is no kit
    return sample

def start_job(ws, body, count):
    stub_only()
    sample_for(ws, body)
    job_id = 'job_' + uuid4().hex
    db.put('JobState', job_id, ws, {'workspaceId':ws, 'designs':variant_designs(ws, count), 'polls':0})
    return JobResult(jobId=job_id)

@router.post('/workspaces/{ws}/decompose', response_model=JobResult)
def decompose(ws: str, body: SampleRequest, tasks: BackgroundTasks):
    if use_stubs():
        return start_job(ws, body, 1)
    from app.decompose.pipeline import run_decompose
    sample = sample_for(ws, body)
    job_id = common.new_job()
    tasks.add_task(common.run_job, job_id, run_decompose, ws, sample)
    return JobResult(jobId=job_id)

@router.post('/workspaces/{ws}/variants', response_model=JobResult)
def variants(ws: str, body: SampleRequest, tasks: BackgroundTasks):
    if use_stubs():
        return start_job(ws, body, 4)
    sample = sample_for(ws, body)
    job_id = common.new_job()
    tasks.add_task(common.run_job, job_id, variant_job.run_variants, ws, sample, body.brief)
    return JobResult(jobId=job_id)

@router.get('/jobs/{jobId}', response_model=Job, response_model_exclude_unset=True)
def poll_job(jobId: str):
    if jobId in common.JOBS:
        with common.LOCK:
            return Job.model_validate(validate_contract('Job', dict(common.JOBS[jobId], designs=list(common.JOBS[jobId]['designs']))))
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
    if asset.source == 'brand_asset':
        raise HTTPException(403, 'Brand assets are locked')
    if asset.source != 'generated':
        raise HTTPException(403, 'Only generated images can be edited with AI')
    if use_stubs():
        return storage.save_asset(ws, storage.asset_path(asset.id).read_bytes(), 'edited.png', 'image', 'generated')
    from app.generate.chat import edit_generated
    try:
        return edit_generated(ws, asset, body.instruction)
    except PermissionError:
        raise HTTPException(403, 'Brand assets are locked')
    except Exception as exc:
        raise HTTPException(502, f'Image edit failed: {type(exc).__name__}')

@router.post('/workspaces/{ws}/chat', response_model=ChatResult, response_model_exclude_unset=True)
def chat(ws: str, body: ChatRequest):
    db.get('Workspace', ws)
    if body.design.workspaceId != ws:
        raise HTTPException(422, 'Workspace id mismatch')
    design = validate_contract('Design', body.design)
    if not use_stubs():
        from app.generate.chat import run_chat
        try:
            reply, ops = run_chat(ws, design, body.selection, body.message)
        except Exception as exc:
            raise HTTPException(502, f'Copilot failed: {type(exc).__name__}')
        return ChatResult(reply=reply, ops=ops)
    return ChatResult(reply='Stub copilot: select a layer to begin. Direct edits use the canvas controls.', ops=[])
