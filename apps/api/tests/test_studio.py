"""Offline safety, versioning, persistence and orchestration checks for Studio."""
from copy import deepcopy
from uuid import uuid4
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from openai.types.chat import ChatCompletionMessage
from app.main import app
from app.core import db, storage
from app.core.fixtures import seed_workspace
from app.core.validation import validate_contract
from app.generate import common as c
from app.llm import images
from app.studio import agent

@pytest.fixture
def studio(monkeypatch):
    monkeypatch.setenv('USE_STUBS','1')
    ws = 'ws_studio_'+uuid4().hex[:8]
    seed_workspace(ws,'Studio test')
    kit = db.get('BrandKit',ws)
    kit['confirmed'] = True
    kit['colors'].append({'token':'navy','hex':'#10243A','role':'background'})
    db.put('BrandKit',ws,ws,kit)
    client = TestClient(app)
    thread = client.post(f'/api/workspaces/{ws}/threads',json={}).json()
    design = db.list_records('Design',ws)[0]
    design.update(label='Option B',version=1)
    db.put('Design',design['id'],ws,design)
    thread['messages']=[agent.message('assistant','Option B',designs=[design['id']])]
    db.put('Thread',thread['id'],ws,thread)
    return ws,client,thread,design

def session(studio):
    ws,client,thread,design = studio
    return agent.Session(c.new_job(),thread,'Edit B',[],[design['id']])

def tool_message(name,args):
    import json
    return SimpleNamespace(choices=[SimpleNamespace(message=ChatCompletionMessage(role='assistant',content=None,
        tool_calls=[{'id':'call_'+uuid4().hex[:6],'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]))])

def test_new_version_groups_tools_and_preserves_parent(studio,monkeypatch):
    s = session(studio)
    original = deepcopy(studio[3])
    head = next(l for l in original['layers'] if l['role']=='headline')
    monkeypatch.setattr(images,'edit',lambda *a,**k:pytest.fail('Direct ops called an image model'))
    s.execute('update_layer',{'designId':original['id'],'layerId':head['id'],'props':{'text':'Close your books faster'}})
    out = s.execute('set_background',{'designId':original['id'],'colorToken':'navy'})['design']
    assert out['version']==2 and out['parentId']==original['id'] and out['label']=='Option B'
    assert out['background']['colorToken']=='navy'
    assert next(l for l in out['layers'] if l['id']==head['id'])['text']=='Close your books faster'
    assert db.get('Design',original['id'])==original
    assert len(s.outputs_id())==1
    validate_contract('Design',out)
    # Browsing v1 must not make a later named 'B' request resolve to the old version.
    thread = deepcopy(studio[2])
    thread['messages'].append(agent.message('assistant','B updated',designs=[out['id']]))
    next_turn = agent.Session(c.new_job(),thread,'Change B',[],[original['id']])
    assert next_turn.context()['latestByLabel']['Option B']==out['id']

def test_image_edit_checks_stored_source_before_model(studio,monkeypatch):
    s = session(studio)
    design = studio[3]
    brand = storage.list_assets(s.ws,'image')[0]
    layer = next(l for l in design['layers'] if l['type']=='image')
    layer.update(assetId=brand.id,source='generated')  # tampered layer provenance
    db.put('Design',design['id'],s.ws,design)
    monkeypatch.setattr(images,'edit',lambda *a,**k:pytest.fail('Brand pixels reached image model'))
    with pytest.raises(PermissionError,match='stored asset'):
        s.execute('edit_generated_image',{'designId':design['id'],'layerId':layer['id'],'instruction':'Blue'})

def test_library_swap_ownership_and_tags(studio):
    s = session(studio)
    design = studio[3]
    asset = storage.list_assets(s.ws,'image')[0]
    storage.set_caption(asset.id,'Product UI dashboard',['product-ui'])
    found = s.execute('search_assets',{'query':'product UI','kind':'image'})['assets']
    assert found[0]['id']==asset.id
    layer = next(l for l in design['layers'] if l['type']=='image' and l['role']!='logo')
    out=s.execute('replace_image',{'designId':design['id'],'layerId':layer['id'],'assetId':asset.id})['design']
    assert next(l for l in out['layers'] if l['id']==layer['id'])['source']=='brand_asset'
    other=storage.list_assets('ws_lumen','image')[0]
    with pytest.raises(ValueError,match='outside'):
        s.execute('replace_image',{'designId':design['id'],'layerId':layer['id'],'assetId':other.id})

def test_context_reads_direct_edits_and_focus(studio):
    s = session(studio)
    d = studio[3]
    next(l for l in d['layers'] if l['type']=='text')['text']='Direct preview correction'
    db.put('Design',d['id'],s.ws,d)
    context=s.context()
    assert context['focusDesignIds']==[d['id']]
    assert 'Direct preview correction' in str(context['designs'])

def test_thread_persistence_and_bare_attachment(studio):
    ws,client,thread,design=studio
    sample=storage.list_assets(ws,'sample')[0]
    r=client.post(f'/api/threads/{thread["id"]}/messages',json={'text':'','attachmentAssetIds':[sample.id]})
    assert r.status_code==202,r.text
    job=client.get('/api/jobs/'+r.json()['jobId']).json()
    assert job['status']=='done' and {d['label'] for d in job['designs']}=={'Option A','Option B','Option C','Option D'}
    assert len(job['steps'])>=3 and job['reply']
    persisted=TestClient(app).get('/api/threads/'+thread['id']).json()
    assert persisted['messages'][-2]['attachmentAssetIds']==[sample.id]
    assert persisted['messages'][-1]['designIds']==[d['id'] for d in job['designs']]
    assert persisted['messages'][-1]['steps']==job['steps']
    validate_contract('Thread',persisted)
    assert client.get(f'/api/workspaces/{ws}/threads').json()[0]['id']==thread['id']

def test_message_rejects_brand_attachment_and_concurrent_turn(studio):
    ws,client,thread,design=studio
    brand=storage.list_assets(ws,'image')[0]
    assert client.post(f'/api/threads/{thread["id"]}/messages',json={'text':'x','attachmentAssetIds':[brand.id]}).status_code==422
    agent.ACTIVE.add(thread['id'])
    try: assert client.post(f'/api/threads/{thread["id"]}/messages',json={'text':'x'}).status_code==409
    finally: agent.ACTIVE.discard(thread['id'])
    assert client.post(f'/api/threads/{thread["id"]}/messages',json={'text':''}).status_code==422

def test_tool_loop_is_bounded(studio,monkeypatch):
    monkeypatch.setenv('USE_STUBS','0')
    s=session(studio)
    calls=[]
    def again(*a,**k):
        calls.append(1)
        return tool_message('search_assets',{'query':'coffee'})
    monkeypatch.setattr(agent.deepseek,'chat',again)
    s.loop()
    assert len(calls)==15 and s.calls==15
    assert s.reply_text

def test_failed_model_turn_persists_explanatory_pair(studio,monkeypatch):
    monkeypatch.setenv('USE_STUBS','0')
    ws,client,thread,design=studio
    def fail(*a,**k): raise TimeoutError('provider down')
    monkeypatch.setattr(agent.deepseek,'chat',fail)
    r=client.post(f'/api/threads/{thread["id"]}/messages',json={'text':'Edit B'})
    job=client.get('/api/jobs/'+r.json()['jobId']).json()
    assert job['status']=='error' and 'TimeoutError' in job['reply']
    messages=client.get('/api/threads/'+thread['id']).json()['messages']
    assert messages[-2]['text']=='Edit B' and messages[-1]['text']==job['reply']
    assert thread['id'] not in agent.ACTIVE


def test_split_with_fontless_kit_uses_local_fallback(studio,monkeypatch):
    from app.decompose import pipeline
    ws,client,thread,design=studio
    kit=db.get('BrandKit',ws)
    kit['fonts']=[]
    for a in storage.list_assets(ws,'font'): db.delete('Asset',a.id)
    db.put('BrandKit',ws,ws,kit)
    monkeypatch.setenv('USE_STUBS','0')
    monkeypatch.setattr(pipeline,'read_elements',lambda path:[{
        'type':'text','text':'An editable headline','box':[.1,.1,.9,.3],'colorHex':'#1B1B1F',
        'fontStyle':{'serif':False,'weight':700,'italic':False},'align':'left','role':'headline'}])
    monkeypatch.setattr(pipeline,'clean_plate',lambda original,holes:(original.copy(),True))
    s=agent.Session(c.new_job(),thread,'split',[],[])
    sample=storage.list_assets(ws,'sample')[0]
    result=s.execute('split_into_layers',{'assetId':sample.id})['design']
    assert any(l['type']=='text' and l['text']=='An editable headline' for l in result['layers'])
    fonts=storage.list_assets(ws,'font')
    assert len(fonts)==1 and fonts[0].meta['fallback'] is True
    assert all(f.assetId==fonts[0].id for f in storage.get_brand_kit(ws).fonts)
    validate_contract('Design',result)


def test_failed_split_stops_turn_instead_of_repeating_model_calls(studio,monkeypatch):
    ws,client,thread,design=studio
    monkeypatch.setenv('USE_STUBS','0')
    sample=storage.list_assets(ws,'sample')[0]
    calls={'chat':0,'split':0}
    def choose_split(*a,**k):
        calls['chat']+=1
        return tool_message('split_into_layers',{'assetId':sample.id})
    def fail(*a,**k):
        calls['split']+=1
        raise ValueError('min() iterable argument is empty')
    monkeypatch.setattr(agent.deepseek,'chat',choose_split)
    monkeypatch.setattr(agent.pipeline,'run_decompose',fail)
    r=client.post(f'/api/threads/{thread["id"]}/messages',json={'text':'Split this image','attachmentAssetIds':[sample.id]})
    job=client.get('/api/jobs/'+r.json()['jobId']).json()
    assert job['status']=='error'
    assert calls=={'chat':1,'split':1}
    assert 'without uploading it again' in job['reply']
    assert 'min()' not in job['reply']
    assert thread['id'] not in agent.ACTIVE


def test_split_only_request_publishes_reference_card(studio,monkeypatch):
    ws,client,thread,design=studio
    monkeypatch.setenv('USE_STUBS','0')
    sample=storage.list_assets(ws,'sample')[0]
    responses=iter([tool_message('split_into_layers',{'assetId':sample.id}),tool_message('reply',{'text':'Split into editable layers.'})])
    monkeypatch.setattr(agent.deepseek,'chat',lambda *a,**k:next(responses))
    monkeypatch.setattr(agent.pipeline,'run_decompose',lambda job,ws,asset:c.add_design(job,ws,design))
    r=client.post(f'/api/threads/{thread["id"]}/messages',json={'text':'Split this reference','attachmentAssetIds':[sample.id]})
    job=client.get('/api/jobs/'+r.json()['jobId']).json()
    assert job['status']=='done' and len(job['designs'])==1
    assert job['designs'][0]['label']=='Reference'
    assert client.get('/api/threads/'+thread['id']).json()['messages'][-1]['designIds']==[design['id']]
