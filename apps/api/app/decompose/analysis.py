"""Reusable source analysis. Cache raw vision/OCR output, never a brand-specific reconstruction."""
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from app.core import db, storage
from . import ocr

REVISION='reference-analysis-v1'

def analyze(sample,path,reader):
    key=REVISION+':'+hashlib.sha256(path.read_bytes()).hexdigest()
    current=db.get('Asset',sample.id)
    cached=current['meta'].get('layerAnalysis',{})
    if cached.get('key')==key:
        return cached['elements'],cached['ocr'],{'analysisSeconds':0,'analysisCacheHit':True,'analysisKey':key}
    start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        vision=pool.submit(reader,path)
        local=pool.submit(ocr.read_text,path)
        elements,lines=vision.result(),local.result()
    current['meta']['layerAnalysis']={'key':key,'elements':elements,'ocr':lines}
    db.put('Asset',sample.id,sample.workspaceId,current)
    return elements,lines,{'analysisSeconds':round(time.perf_counter()-start,3),'analysisCacheHit':False,'analysisKey':key}

def residual_text(lines,elements):
    """Only source marketing text regions count. Product/phone UI lettering remains untouched."""
    import re
    norm=lambda t:re.sub(r'[^a-z0-9]','',t.lower())
    findings=[]
    for line in lines:
        if line['confidence']<.65:continue
        word=norm(line['text'])
        if len(word)<3:continue
        x0,y0,x1,y1=line['box'];cx,cy=(x0+x1)/2,(y0+y1)/2
        for e in elements:
            if e['type'] not in ('text','logo'):continue
            b=e['box'];source=norm(e['text'])
            if source and (word in source or source in word) and b[0]-.01<=cx<=b[2]+.01 and b[1]-.01<=cy<=b[3]+.01:
                findings.append({'code':'RESIDUAL_TEXT','severity':'warning',
                                 'message':f'Background may still contain “{line["text"][:60]}”. Review the clean background.'})
                break
    return findings
