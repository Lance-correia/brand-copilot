"""Pixel preservation, bounded repair and shared typography regression checks."""
import io
from PIL import Image,ImageChops,ImageDraw,ImageFont
from app.decompose.cleanup import clean
from app.generate import common as c

def png(image):
    buffer=io.BytesIO();image.save(buffer,'PNG');return buffer.getvalue()

def test_flat_card_skips_image_model_and_removes_glyphs():
    source=Image.new('RGB',(320,200),'#F7F4ED')
    font=ImageFont.truetype(str(c.FIXTURES/'brand/fonts/DMSans.ttf'),28)
    ImageDraw.Draw(source).text((30,50),'Clean output',font=font,fill='#001144')
    def forbidden(*a,**k):raise AssertionError('Flat surface must not call a model')
    result=clean(source,[{'box':[25,45,240,90]}],edit=forbidden)
    assert result.model_calls==0 and result.methods==['local_surface']
    assert result.image.crop((25,45,240,90)).getextrema()==((247,247),(244,244),(237,237))
    assert result.image.getpixel((10,10))==source.getpixel((10,10))

def test_linear_surface_preserves_original_unmasked_pixels():
    tile=Image.new('RGB',(2,2));tile.putdata([(190,210,245),(205,225,255),(160,190,230),(175,205,240)])
    source=tile.resize((320,200),Image.Resampling.BILINEAR)
    original=source.copy()
    ImageDraw.Draw(source).rectangle((70,70,170,85),fill='navy')
    result=clean(source,[{'box':[60,60,180,95]}],edit=lambda *a,**k:(_ for _ in ()).throw(AssertionError()))
    assert result.model_calls==0
    assert result.image.getpixel((5,5))==original.getpixel((5,5))
    assert result.image.getpixel((100,75))[2]>200

def test_masked_photo_repair_changes_only_selected_pixels():
    source=Image.effect_noise((160,160),90).convert('RGB')
    seen=[]
    def repair(path,prompt,mask_path):
        with Image.open(mask_path) as mask:
            assert mask.mode=='RGBA' and mask.getchannel('A').getextrema()==(0,255)
        with Image.open(path) as work: size=work.size
        seen.append(mask_path)
        return png(Image.new('RGB',size,'#40C080'))
    result=clean(source,[{'box':[60,60,100,100]}],edit=repair)
    assert len(seen)==1 and result.model_calls==1 and not result.findings
    assert result.image.getpixel((80,80))==(64,192,128)
    changed=ImageChops.difference(source,result.image).getbbox()
    assert changed[0]>=55 and changed[1]>=55 and changed[2]<=106 and changed[3]<=106

def test_transparent_photo_response_gets_one_bounded_fallback():
    source=Image.effect_noise((160,160),90).convert('RGB')
    calls=[]
    def repair(path,prompt,mask_path):
        calls.append(mask_path)
        with Image.open(path) as work:size=work.size
        return png(Image.new('RGBA',size,(255,0,0,0) if mask_path else (60,180,100,255)))
    result=clean(source,[{'box':[60,60,100,100]}],edit=repair)
    assert len(calls)==2 and calls[0] is not None and calls[1] is None
    assert not result.findings and 'opaque_fallback' in result.methods

def test_failed_photo_repair_is_visible_and_bounded():
    source=Image.effect_noise((160,160),90).convert('RGB')
    def fail(*a,**k):raise TimeoutError()
    result=clean(source,[{'box':[60,60,100,100]}],edit=fail)
    assert result.model_calls==2 and result.findings[0]['code']=='CLEANUP_FAILED'

def test_source_analysis_is_cached_without_repeating_vision(monkeypatch):
    from app.core import storage,db
    from app.decompose import analysis
    sample=storage.list_assets('ws_lumen','sample')[0]
    path=storage.asset_path(sample.id)
    body=db.get('Asset',sample.id);body['meta'].pop('layerAnalysis',None);db.put('Asset',sample.id,sample.workspaceId,body)
    calls=[]
    monkeypatch.setattr(analysis.ocr,'read_text',lambda path:[])
    def reader(path):calls.append(1);return [{'type':'text','text':'Cached'}]
    first=analysis.analyze(sample,path,reader)
    second=analysis.analyze(sample,path,reader)
    assert len(calls)==1 and not first[2]['analysisCacheHit'] and second[2]['analysisCacheHit']
    assert second[0]==first[0]
