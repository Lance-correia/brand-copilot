"""Sample analysis and the four-variant job: plan (Pro) -> build -> images (parallel) -> lint."""
import base64
import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from app.core import storage
from app.core.validation import validate_contract
from app.llm import deepseek, images
from . import common as c

IMAGE_ROLES = ['background', 'hero', 'decoration']
SPEC_CACHE = {}

def spec_schema():
    schema = json.loads((c.FIXTURES.parent / 'packages/schema/DesignSpec.schema.json').read_text())
    for key in ('$schema', '$id', 'title'):
        schema.pop(key, None)
    return schema

def analyze_sample(data: bytes, filename):
    mime = mimetypes.guess_type(filename or '')[0] or 'image/png'
    url = f'data:{mime};base64,' + base64.b64encode(data).decode()
    spec = deepseek.chat_json(deepseek.flash(), (
        'Analyse this marketing design and describe its layout as a DesignSpec. '
        'aspect is like "1:1" or "4:5". regions lists every visible element with its role and a box '
        '[x0, y0, x1, y1] as fractions of the image. hierarchy orders roles by visual importance. '
        'observedColors are hex codes like "#C8553D".'), spec_schema(), images=[url])
    for region in spec['regions']:
        region['box'] = [min(1, max(0, v)) for v in region['box']]
    return validate_contract('DesignSpec', spec)

def sample_spec(sample):
    if sample.meta.get('spec'):
        return sample.meta['spec']
    if sample.id not in SPEC_CACHE:
        SPEC_CACHE[sample.id] = analyze_sample(storage.asset_path(sample.id).read_bytes(), sample.filename)
    return SPEC_CACHE[sample.id]

# Plan

def plan_schema(template_ids, tokens):
    s = lambda **p: {'type':'object', 'properties':p, 'required':list(p), 'additionalProperties':False}
    text = {'type':'string'}
    role = {'type':'string', 'enum':IMAGE_ROLES}
    token = {'type':'string', 'enum':tokens}
    plan = s(templateId={'type':'string', 'enum':template_ids}, angle=text,
             copy=s(headline=text, subhead=text, cta=text),
             assetPicks={'type':'array', 'items':s(role=role, assetId=text)},
             imagePrompts={'type':'array', 'items':s(role=role, prompt=text)},
             colors=s(background=token, accent=token, text=token))
    return s(plans={'type':'array', 'items':plan})

def plan(kit, catalogue, spec, templates, brief, source_design=None):
    tokens = [col.token for col in kit.colors]
    context = {
        'brandKit':{'colors':[col.model_dump() for col in kit.colors], 'fonts':[f.token for f in kit.fonts],
                    'voice':kit.voice, 'imageryStyle':kit.imageryStyle},
        'assets':catalogue, 'designSpec':spec, 'brief':brief or '', 'sourceDesign':source_design,
        'templates':[{'id':t['id'], 'name':t['name'], 'aspect':t['aspect'],
                      'slots':[f"{s['role']}:{s['kind']}" for s in t['slots']]} for t in templates]}
    prompt = (
        'You are the art director for this brand. Plan exactly 4 on-brand design variants inspired by the sample design spec '
        'and the brief. Preserve the source design message and key layout ideas when sourceDesign is provided.\n'
        '- Use 4 different templateIds when possible; if you repeat a template, its angle must be clearly different.\n'
        '- angle: one short phrase naming the creative idea.\n'
        "- copy: headline (max 6 words), subhead (max 12 words), cta (max 3 words), all in the brand voice.\n"
        '- For each image slot (hero/background) either pick a fitting brand image from assets by id in assetPicks, '
        'or write an imagePrompts entry describing the photo subject, setting, light and composition. '
        'Use brand images in at most 2 variants; the others get fresh imagePrompts. Never ask for text in images.\n'
        '- Vary the aspect: include at least one non-square template when one exists.\n'
        '- colors are palette tokens: background for the canvas and panels, accent for buttons, text for copy. '
        'text must contrast strongly with background.\n\n'
        + json.dumps(context))
    result = deepseek.chat_json(deepseek.pro(), prompt, plan_schema([t['id'] for t in templates], tokens))
    plans = result['plans'][:4]
    if not plans:
        raise RuntimeError('Planner returned no variants')
    while len(plans) < 4:  # pad short answers rather than fail the whole job
        plans.append(dict(plans[len(plans) % len(plans)], angle=plans[0]['angle'] + ' (alt)'))
    return plans

# Build

def box_px(box, t):
    return box[0] * t['width'], box[1] * t['height'], (box[2] - box[0]) * t['width'], (box[3] - box[1]) * t['height']

def base(role, x, y, w, h):
    return {'id':c.layer_id(), 'role':role, 'x':round(x), 'y':round(y), 'w':max(1, round(w)), 'h':max(1, round(h)),
            'rotation':0, 'visible':True, 'locked':False}

def text_layer(role, text, x, y, w, h, kit, color, align='left'):
    font = c.font_for(kit, role)
    return base(role, x, y, w, h) | {'type':'text', 'text':text, 'fontToken':font.token,
            'fontSize':c.fit_font_size(text, w, h, font), 'colorToken':color, 'align':align}

def build(t, p, kit, ws, name):
    """Deterministic design from template + plan. Image slots without a pick come back in `pending`."""
    picks = {a['role']:a['assetId'] for a in p['assetPicks']}
    prompts = {a['role']:a['prompt'] for a in p['imagePrompts']}
    bg, accent, ink = p['colors']['background'], p['colors']['accent'], p['colors']['text']
    images_, shapes, texts, logos, pending = [], [], [], [], []
    for slot in t['slots']:
        x, y, w, h = box_px(slot['box'], t)
        role = slot['role']
        if slot['kind'] == 'image' and role == 'logo':
            logos.append((x, y, w, h))
        elif slot['kind'] == 'image':
            layer = base(role, x, y, w, h) | {'type':'image', 'fit':'cover'}
            asset = picks.get(role)
            if asset:
                layer |= {'assetId':asset, 'source':storage.get_asset(asset).source}
            else:
                pending.append((layer, prompts.get(role) or p['angle']))
            images_.append(layer)
        elif slot['kind'] == 'shape':
            shapes.append(base(role, x, y, w, h) | {'type':'shape', 'shape':'rect',
                          'fillToken':accent if role == 'cta_bg' else bg, 'radius':round(min(w, h) * 0.04)})
        elif role == 'cta':
            shapes.append(base('cta_bg', x, y, w, h) | {'type':'shape', 'shape':'rect', 'fillToken':accent, 'radius':round(h / 2)})
            texts.append(text_layer('cta', p['copy']['cta'], x + h * 0.3, y + h * 0.2, w - h * 0.6, h * 0.6, kit, bg, 'center'))
        else:
            copy = p['copy']['headline'] if role == 'headline' else p['copy']['subhead']
            centered = abs((slot['box'][0] + slot['box'][2]) / 2 - 0.5) < 0.02 and slot['box'][0] > 0.15
            texts.append(text_layer(role, copy, x, y, w, h, kit, ink, 'center' if centered else 'left'))
    for x, y, w, h in logos:
        logo = kit.logos[0] if kit.logos else None
        if logo:
            texts.append(base('logo', x, y, w, h) | {'type':'image', 'source':'brand_asset', 'assetId':logo.assetId, 'fit':'contain'})
    design = {'id':'des_' + uuid4().hex, 'workspaceId':ws, 'name':name, 'width':t['width'], 'height':t['height'],
              'background':{'colorToken':bg}, 'layers':images_ + shapes + texts}
    return design, pending

def backdrop(design, layer, kit):
    """RGB under the center of `layer`: the topmost layer below it there, else the canvas background."""
    cx, cy = layer['x'] + layer['w'] / 2, layer['y'] + layer['h'] / 2
    below = design['layers'][:design['layers'].index(layer)]
    for under in reversed(below):
        if under['visible'] and under['x'] <= cx <= under['x'] + under['w'] and under['y'] <= cy <= under['y'] + under['h']:
            if under['type'] == 'shape':
                return c.rgb(c.token_hex(kit, under['fillToken']))
            if under['type'] == 'image':
                fx = lambda v, o, s: min(1, max(0, (v - o) / s))
                box = [fx(layer['x'], under['x'], under['w']), fx(layer['y'], under['y'], under['h']),
                       fx(layer['x'] + layer['w'], under['x'], under['w']), fx(layer['y'] + layer['h'], under['y'], under['h'])]
                return c.mean_rgb(storage.asset_path(under['assetId']), box)
    return c.rgb(c.token_hex(kit, design['background']['colorToken']))

def finish(design, kit, preferred_text):
    """Pick readable text colors and the logo variant against what is actually behind them."""
    for layer in design['layers']:
        if layer['type'] == 'text':
            want = layer['colorToken'] if layer['role'] == 'cta' else preferred_text
            layer['colorToken'] = c.readable_token(kit, backdrop(design, layer, kit), want)
        elif layer['role'] == 'logo':
            logo = c.logo_for(kit, backdrop(design, layer, kit))
            meta = storage.get_asset(logo.assetId)
            aspect = (meta.width or 4) / (meta.height or 1)
            w = max(min(layer['w'], layer['h'] * aspect), logo.minWidth)
            layer.update(assetId=logo.assetId, x=round(layer['x'] + layer['w'] - w), y=round(layer['y'] + (layer['h'] - w / aspect) / 2),
                         w=round(w), h=round(w / aspect))
    return design

def generate_image(ws, kit, layer, prompt):
    w, h = images.image_size(layer['w'], layer['h'])
    data = deepseek.retry(images.generate, f'{kit.imageryStyle}. {prompt}', w, h)
    return storage.save_asset(ws, data, f'{c.slug(prompt)}.png', 'image', 'generated', {'prompt':prompt})

def run_variants(job_id, ws, sample, brief, source_design=None, studio=False):
    kit = storage.get_brand_kit(ws)
    from app.brand.fonts import require_design_kit
    require_design_kit(kit)
    c.update_job(job_id, progress='Reading sample')
    spec = sample_spec(sample) if sample else {
        'aspect':f"{source_design['width']}:{source_design['height']}",
        'regions':[{'role':l['role'],'box':[l['x']/source_design['width'],l['y']/source_design['height'],
                  (l['x']+l['w'])/source_design['width'],(l['y']+l['h'])/source_design['height']]} for l in source_design['layers']],
        'hierarchy':[l['role'] for l in source_design['layers']], 'mood':'', 'imageryStyle':kit.imageryStyle, 'observedColors':[]}

    catalogue = [{'id':a.id, 'kind':a.kind, 'caption':a.caption, 'tags':a.tags}
                 for a in storage.list_assets(ws, 'image')]
    templates = {t['id']:t for t in c.templates()}
    c.update_job(job_id, progress='Planning')
    plans = deepseek.retry(plan, kit, catalogue, spec, list(templates.values()), brief, **({'source_design':source_design} if source_design else {}))
    valid_ids = {a['id'] for a in catalogue}
    builds = []
    for i, p in enumerate(plans):
        p['assetPicks'] = [a for a in p['assetPicks'] if a['assetId'] in valid_ids]
        # Give the first Studio option an editable generated photo. Other options can use library imagery.
        if studio and i == 0:
            photo_roles = [slot['role'] for slot in templates[p['templateId']]['slots'] if slot['kind']=='image' and slot['role']!='logo']
            for role in photo_roles:
                p['assetPicks'] = [a for a in p['assetPicks'] if a['role'] != role]
                if not any(a['role']==role for a in p['imagePrompts']):
                    p['imagePrompts'].append({'role':role,'prompt':f'{kit.imageryStyle}. A scene supporting: {p["angle"]}'})
        builds.append(build(templates[p['templateId']], p, kit, ws, f"Variant {chr(65 + i)}: {p['angle']}"[:80]))
    total = sum(len(pending) for _, pending in builds)
    done, failed = [0], [0]
    def progress():
        note = f', {failed[0]} failed (placeholder used)' if failed[0] else ''
        c.update_job(job_id, progress=f'Generating images {done[0]}/{total}{note}')
    def one(layer, prompt):
        try:
            return generate_image(ws, kit, layer, prompt)
        except Exception:
            with c.LOCK:
                failed[0] += 1
            return None
        finally:
            with c.LOCK:
                done[0] += 1
            progress()
    progress()
    with ThreadPoolExecutor(max_workers=max(1, total)) as pool:
        futures = [[(layer, pool.submit(one, layer, prompt)) for layer, prompt in pending] for _, pending in builds]
        for option_index, ((design, _), (p, jobs)) in enumerate(zip(builds, zip(plans, futures))):
            for layer, future in jobs:
                asset = future.result()
                if asset:
                    layer.update(assetId=asset.id, source='generated')
                else:  # keep the variant renderable: accent placeholder instead of the photo
                    for key in ('fit', 'source', 'assetId'):
                        layer.pop(key, None)
                    layer.update(type='shape', shape='rect', fillToken=p['colors']['accent'], radius=0)
            c.update_job(job_id, progress=f'Checking brand ({design["name"][:9]})')
            design, _ = c.lint_fix(finish(design, kit, p['colors']['text']), kit)
            if studio: design.update(label=f'Option {chr(65+option_index)}',version=1)
            c.add_design(job_id, ws, design)
    c.update_job(job_id, progress='Done' + (f' ({failed[0]} image(s) failed, placeholders used)' if failed[0] else ''))
