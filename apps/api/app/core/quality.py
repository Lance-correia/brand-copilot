"""Deterministic output checks. Reports uncertainty; never invokes a model."""
from datetime import datetime,timezone
from pathlib import Path
from app.core import storage
from app.brand.lint import lint_design

def assess(design,kit):
    findings=[{'code':v.ruleId,'severity':v.severity,'message':v.message,
               **({'layerId':v.layerId} if v.layerId else {})} for v in lint_design(design,kit)]
    checks=['brand_rules','font_measurement','canvas_bounds','asset_integrity','text_collisions']
    def flag(code,message,layer=None,severity='warning'):
        findings.append({'code':code,'severity':severity,'message':message,**({'layerId':layer['id']} if layer else {})})
    for key,asset_id in design.get('provenance',{}).items():
        asset=storage.get_asset(asset_id)
        if asset.workspaceId!=design['workspaceId']:raise ValueError('Comparison asset belongs to another workspace')
    visible=[l for l in design['layers'] if l['visible']]
    from .typography import font_path
    for layer in visible:
        if layer['type']=='shape' and layer['role']=='hero':
            flag('IMAGE_FAILED','The photo could not be generated. This option contains a temporary color fill.',layer)
        if layer['role'] not in ('background','hero') and (layer['x']<0 or layer['y']<0 or layer['x']+layer['w']>design['width']+1 or layer['y']+layer['h']>design['height']+1):
            flag('CLIPPED_LAYER','Layer extends beyond the exported canvas.',layer,'error')
        if layer['type']=='text':
            font=next((f for f in kit.fonts if f.token==layer['fontToken']),None)
            if font and not font_path(font.assetId):flag('FONT_UNREADABLE','The font file could not be measured. Replace it before export.',layer)
        if layer['type']=='image':
            try:
                asset=storage.get_asset(layer['assetId'])
                if asset.workspaceId!=design['workspaceId']:raise ValueError('Image belongs to another workspace')
                if not storage.asset_path(asset.id).is_file():raise KeyError('missing file')
                if asset.width and asset.height and asset.mime!='image/svg+xml' and max(layer['w']/asset.width,layer['h']/asset.height)>1.8:
                    flag('LOW_RESOLUTION','This image is enlarged substantially and may look soft in the export.',layer)
                if asset.meta.get('generationFailed'):flag('IMAGE_FAILED','Image generation failed. Retry this option before export.',layer)
                if layer['assetId']==design.get('provenance',{}).get('cleanPlateAssetId'):
                    report=asset.meta.get('cleanup',{})
                    findings.extend(report.get('findings',[]));checks.append('background_cleanup')
                    if report.get('ocrAvailable'):checks.append('residual_text')
                    else:flag('OCR_UNAVAILABLE','Background text verification was unavailable. Review the clean background.')
            except KeyError:flag('MISSING_ASSET','An image file is missing from this design.',layer,'error')
    text=[l for l in visible if l['type']=='text']
    logos=[l for l in visible if l['role']=='logo']
    for i,a in enumerate(text):
        for b in text[i+1:]+logos:
            overlap=max(0,min(a['x']+a['w'],b['x']+b['w'])-max(a['x'],b['x']))*max(0,min(a['y']+a['h'],b['y']+b['h'])-max(a['y'],b['y']))
            if overlap>min(a['w']*a['h'],b['w']*b['h'])*.1:
                flag('TEXT_COLLISION',f'{a["role"].capitalize()} overlaps {b["role"]}. Adjust spacing before export.',a)
    # Keep independently reported issues once, preserving stable order for the UI.
    unique={ (f['code'],f.get('layerId'),f['message']):f for f in findings }
    design['quality']={'status':'needs_review' if unique else 'ready','checkedAt':datetime.now(timezone.utc).isoformat(),
                       'checks':list(dict.fromkeys(checks)),'findings':list(unique.values())}
    return design
