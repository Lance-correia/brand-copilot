#!/usr/bin/env python3
"""Smoke every contracted HTTP method/path against a running USE_STUBS=1 API."""
import copy
import os
import sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from app.core.validation import validate_contract

client=httpx.Client(base_url=os.getenv('BASE_URL','http://127.0.0.1:8000/api'),timeout=60)
covered=set()

def call(method,path,shape=None,status=200,**kwargs):
    response=client.request(method,path,**kwargs)
    assert response.status_code==status, f'{method} {path}: expected {status}, got {response.status_code}: {response.text[:400]}'
    data=None if status==204 else response.json()
    if shape:
        if shape.endswith('[]'):
            assert isinstance(data,list)
            for item in data:validate_contract(shape[:-2],item)
        else:validate_contract(shape,data)
    covered.add((method,path))
    print(f'PASS {method} {path} ({status})')
    return data

def main():
    ws=call('POST','/workspaces','Workspace',201,json={'name':'Lumen smoke '+uuid4().hex[:8]})['id']
    base=f'/workspaces/{ws}'
    assert any(w['id']==ws for w in call('GET','/workspaces','Workspace[]'))
    call('GET',base,'Workspace')
    with (ROOT/'fixtures/samples/sample-1.png').open('rb') as file:
        uploaded=call('POST',base+'/assets','Asset',201,files={'file':('smoke.png',file,'image/png')},data={'kind':'image'})
    assets=call('GET',base+'/assets','Asset[]')
    logos=call('GET',base+'/assets?kind=logo','Asset[]')
    assert len(logos)==2 and all(a['kind']=='logo' for a in logos)
    response=client.get('/files/'+uploaded['id'])
    assert response.status_code==200 and response.headers['content-type'].startswith('image/png') and response.content.startswith(b'\x89PNG')
    covered.add(('GET','/files/{assetId}'));print('PASS GET /files/{assetId} (PNG bytes)')
    kit=call('POST',base+'/brand-kit/extract','BrandKit')
    assert not kit['confirmed']
    call('GET',base+'/brand-kit','BrandKit')
    kit['confirmed']=True
    call('PUT',base+'/brand-kit','BrandKit',json=kit)
    assert call('GET',base,'Workspace')['brandKitConfirmed']
    designs=call('GET',base+'/designs','Design[]')
    assert len(designs)==3
    bad=next(d for d in designs if d['name']=='Seeded violations')
    violations=call('POST',base+'/lint','LintViolation[]',json=bad)
    assert {'COL-01','LOGO-01','SAFE-01'} <= {v['ruleId'] for v in violations}
    design=copy.deepcopy(designs[0]);design['id']='des_smoke_'+uuid4().hex
    call('POST',base+'/designs','Design',201,json=design)
    path='/designs/'+design['id']
    call('GET',path,'Design')
    design['name']='Smoke updated'
    call('PUT',path,'Design',json=design)
    with (ROOT/'fixtures/samples/sample-2.png').open('rb') as file:
        sample=call('POST',base+'/samples',files={'file':('sample.png',file,'image/png')})
    assert set(sample)=={'asset','spec'}
    validate_contract('Asset',sample['asset']);validate_contract('DesignSpec',sample['spec'])
    decomposition=call('POST',base+'/decompose',json={'sampleAssetId':sample['asset']['id']})
    assert set(decomposition)=={'jobId'}
    decomposed=call('GET','/jobs/'+decomposition['jobId'],'Job')
    assert len(decomposed['designs'])==1 and decomposed['status']=='done'
    job=call('POST',base+'/variants',json={'sampleAssetId':sample['asset']['id'],'brief':'A slow morning'})
    assert set(job)=={'jobId'}
    for count in range(1,5):
        progress=call('GET','/jobs/'+job['jobId'],'Job')
        assert len(progress['designs'])==count
        assert progress['status']==('done' if count==4 else 'running')
    assert len(call('GET','/jobs/'+job['jobId'],'Job')['designs'])==4
    generated=next(a for a in assets if a['source']=='generated')
    call('POST',base+'/images/edit','Asset',json={'assetId':generated['id'],'instruction':'Make it warmer'})
    for asset in [logos[0],sample['asset']]:
        error=call('POST',base+'/images/edit',status=403,json={'assetId':asset['id'],'instruction':'Change it'})
        assert set(error)=={'error'}
    chat=call('POST',base+'/chat',json={'design':design,'selection':['lay_2'],'message':'Help me'})
    assert set(chat)=={'reply','ops'} and isinstance(chat['reply'],str)
    for op in chat['ops']:validate_contract('EditOp',op)
    call('DELETE','/assets/'+uploaded['id'],status=204)
    assert set(call('GET','/assets-not-a-route',status=404))=={'error'}
    invalid=copy.deepcopy(design);invalid['width']=0
    assert set(call('PUT',path,status=422,json=invalid))=={'error'}
    print('PASS all 21 contracted HTTP method/path pairs; progressive jobs, seed lint, source guards and invalid design rejection')

if __name__=='__main__':
    try:main()
    finally:client.close()
