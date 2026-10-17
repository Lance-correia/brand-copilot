"""Studio conversation endpoints; messages run as bounded background jobs."""
from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from app.core import db, storage
from app.core.validation import validate_contract
from app.generate import common
from app.schema import Thread
from app.studio import agent

router = APIRouter(prefix='/api')

class CreateThread(BaseModel):
    title: str | None = Field(default=None,max_length=120)

class SendMessage(BaseModel):
    text: str = Field(max_length=12000)
    attachmentAssetIds: list[str] = Field(default_factory=list,max_length=8)
    focusDesignIds: list[str] = Field(default_factory=list,max_length=20)

@router.post('/workspaces/{ws}/threads',response_model=Thread,status_code=201)
def create_thread(ws: str, body: CreateThread):
    db.get('Workspace',ws)
    thread = validate_contract('Thread',{'id':'thr_'+uuid4().hex,'workspaceId':ws,'title':body.title or 'New chat',
                                         'createdAt':agent.now(),'messages':[]})
    db.put('Thread',thread['id'],ws,thread)
    return thread

@router.get('/workspaces/{ws}/threads',response_model=list[Thread])
def list_threads(ws: str):
    db.get('Workspace',ws)
    return list(reversed(db.list_records('Thread',ws)))

@router.get('/threads/{thread_id}',response_model=Thread)
def get_thread(thread_id: str):
    return db.get('Thread',thread_id)

@router.post('/threads/{thread_id}/messages',status_code=202)
def send_message(thread_id: str, body: SendMessage, tasks: BackgroundTasks):
    thread = db.get('Thread',thread_id)
    ws = thread['workspaceId']
    kit = storage.get_brand_kit(ws)
    if not kit.confirmed: raise HTTPException(409,'Confirm your brand kit before using Studio')
    if not body.text.strip() and not body.attachmentAssetIds:
        raise HTTPException(422,'Add a message or attach a reference image')
    try:
        for asset_id in body.attachmentAssetIds:
            asset = agent.owned_asset(ws,asset_id)
            if asset.kind != 'sample' or asset.source != 'upload':
                raise ValueError('Attachments must be uploaded sample images')
        for design_id in body.focusDesignIds: agent.owned_design(ws,design_id)
    except (KeyError,ValueError) as exc:
        raise HTTPException(422,str(exc))
    with agent.THREAD_LOCK:
        if thread_id in agent.ACTIVE: raise HTTPException(409,'A response is already running in this chat')
        agent.ACTIVE.add(thread_id)
    job_id = common.new_job()
    common.update_job(job_id,steps=[],progress='Queued')
    if not thread['messages'] and thread['title']=='New chat':
        thread['title'] = body.text.strip()[:70] or 'Reference image options'
        db.put('Thread',thread_id,ws,validate_contract('Thread',thread))
    tasks.add_task(agent.run_message,job_id,thread_id,body.text,list(dict.fromkeys(body.attachmentAssetIds)),list(dict.fromkeys(body.focusDesignIds)))
    return {'jobId':job_id}
