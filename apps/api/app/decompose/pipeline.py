"""Image to layers: read elements (Flash), clean the background plate (edit model), assemble an editable design."""
import difflib
import re
import statistics
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFilter, ImageStat
from app.core import db, storage
from app.llm import deepseek, images
from app.generate import common as c
from app.brand.fonts import require_design_kit

ROLES = ['background', 'hero', 'headline', 'subhead', 'body', 'cta', 'cta_bg', 'logo', 'decoration']
PAD = 8  # working-image pixels around each hole
PLATE_PROMPT = 'Fill these areas with the surrounding background. No text, letters, logos or watermarks.'

def element_schema():
    s = lambda **p: {'type':'object', 'properties':p, 'required':list(p), 'additionalProperties':False}
    return s(elements={'type':'array', 'items':s(
        type={'type':'string', 'enum':['text', 'logo', 'shape', 'photo']},
        box={'type':'array', 'items':{'type':'number'}},
        text={'type':'string'}, colorHex={'type':'string'},
        fontStyle=s(serif={'type':'boolean'}, weight={'type':'integer'}, italic={'type':'boolean'}),
        align={'type':'string', 'enum':['left', 'center', 'right']},
        role={'type':'string', 'enum':ROLES})})

def read_elements(path):
    result = deepseek.chat_json(deepseek.flash(), (
        'List every visual element of this marketing design, back to front. '
        'type: text (each separate text block; keep its exact words, use \\n for line breaks), logo (brand mark or wordmark; '
        'put any wordmark letters in text), shape (solid buttons, panels, badges) or photo. '
        'box: [x0, y0, x1, y1] as fractions of the image width and height, tight around the element. '
        'colorHex: the text or fill color as #RRGGBB. fontStyle describes text; use serif=false, weight=400 otherwise. '
        'role: headline, subhead, body, cta (button label), cta_bg (button shape), logo, hero, decoration or background. '
        'List each button twice: its shape (role cta_bg) and its label text (role cta).'),
        element_schema(), images=[str(path)])
    elements = []
    for e in result['elements']:
        if len(e['box']) != 4:
            continue
        x0, y0, x1, y1 = (min(1.0, max(0.0, v)) for v in e['box'])
        if x1 - x0 > 0.005 and y1 - y0 > 0.005:
            elements.append(e | {'box':[x0, y0, x1, y1]})
    return elements

# Working copy and clean plate

def working_size(W, H, longest=1536):
    """Scale factor and padded size: sides divisible by 16, aspect within 1:3..3:1."""
    s = min(1.0, longest / max(W, H))
    w, h = round(W * s), round(H * s)
    pw, ph = max(w, -(-h // 3)), max(h, -(-w // 3))
    return s, (w, h), (-(-pw // 16) * 16, -(-ph // 16) * 16)

def ring_color(image, box, width=12):
    x0, y0, x1, y1 = box
    ring = image.crop((max(0, x0 - width), max(0, y0 - width), min(image.width, x1 + width), min(image.height, y1 + width)))
    return tuple(int(v) for v in ImageStat.Stat(ring).median)

def clean_plate(original, holes):
    """holes are original-pixel boxes. Returns (plate image at original size, edit_ok)."""
    W, H = original.size
    s, (w, h), (pw, ph) = working_size(W, H)
    work = Image.new('RGB', (pw, ph), ring_color(original, (0, 0, W, H), 0))
    work.paste(original.resize((w, h)), (0, 0))
    mask = Image.new('RGBA', (pw, ph), (0, 0, 0, 255))  # transparent = area to repaint
    flat_mask = Image.new('L',(pw,ph),0)
    flat_draw = ImageDraw.Draw(flat_mask)
    draw, mdraw = ImageDraw.Draw(work), ImageDraw.Draw(mask)
    for x0, y0, x1, y1 in holes:
        box = (max(0, int(x0 * s) - PAD), max(0, int(y0 * s) - PAD), min(pw, int(x1 * s) + PAD), min(ph, int(y1 * s) + PAD))
        # Pre-fill holes so text and brand-logo pixels never reach the image model.
        patch = work.crop(box)
        colors = patch.resize((64,64)).getcolors(4096) or []
        count, dominant = max(colors,default=(0,(255,255,255)))
        # Text on a flat card/button needs its original surface, not the photographic scene
        # behind that card. Preserve this deterministic fill when inpainting changes the surface.
        uniform = count >= 4096*.45
        draw.rectangle(box, fill=dominant if uniform else ring_color(work, box))
        if uniform: flat_draw.rectangle(box,fill=255)
        mdraw.rectangle(box, fill=(0, 0, 0, 0))
    edited, ok = work, True
    with tempfile.TemporaryDirectory() as tmp:
        work.save(Path(tmp) / 'work.png')
        mask.save(Path(tmp) / 'mask.png')
        try:
            # ponytail: no mask_path; the edit model returns transparent holes when given one. The mask
            # instead limits compositing below, so only hole pixels change. Pass mask_path if that gets fixed.
            data = deepseek.retry(images.edit, Path(tmp) / 'work.png', PLATE_PROMPT)
            import io
            edited = Image.open(io.BytesIO(data)).convert('RGB').resize((pw, ph))
        except Exception:
            ok = False
    # Protect the feathered edge too: model output just outside a flat fill can invent
    # borders/shadows that would otherwise bleed back through the blurred composite mask.
    edited.paste(work,mask=flat_mask.filter(ImageFilter.MaxFilter(25)))
    holes_l = mask.getchannel('A').point(lambda a: 255 - a).crop((0, 0, w, h)).resize((W, H)).filter(ImageFilter.GaussianBlur(3))
    plate = original.copy()
    plate.paste(edited.crop((0, 0, w, h)).resize((W, H)), mask=holes_l)
    return plate, ok

# Matching

def wordmark(asset):
    if asset.mime == 'image/svg+xml':
        try:
            root = ET.parse(storage.asset_path(asset.id)).getroot()
            words = ' '.join(t.strip() for el in root.iter() if el.tag.endswith('text') for t in el.itertext())
            if words.strip():
                return words
        except (ET.ParseError, OSError):
            pass
    return asset.caption or ''

def dhash(image):
    g = image.convert('L').resize((9, 8))
    px = list(g.getdata())
    return [px[r * 9 + col] > px[r * 9 + col + 1] for r in range(8) for col in range(8)]

def flat(path):
    with Image.open(path) as im:
        im = im.convert('RGBA')
        bg = Image.new('RGBA', im.size, 'white')
        return Image.alpha_composite(bg, im).convert('RGB')

def match_logo(kit, ws_name, element, crop):
    """A kit logo matching this element by wordmark text or perceptual hash, else None."""
    read = element['text'].strip().lower()
    for logo in kit.logos:
        asset = storage.get_asset(logo.assetId)
        names = [wordmark(asset), ws_name.split()[0] if ws_name else '']
        if read and any(n and difflib.SequenceMatcher(None, read, n.lower()).ratio() > 0.6 for n in names):
            return logo
        if element['type'] != 'text' and asset.mime.startswith('image/') and asset.mime != 'image/svg+xml':
            a, b = dhash(flat(storage.asset_path(asset.id))), dhash(crop)
            if sum(x != y for x, y in zip(a, b)) <= 12:
                return logo
    return None

def corner_radius(crop, fill):
    """Estimate a rounded-rect radius: step diagonally from the top-left corner until the fill color starts.
    A quarter circle of radius r reaches the diagonal at r * (1 - 1/sqrt 2)."""
    n = min(crop.size) // 2
    close = lambda p: sum(abs(a - b) for a, b in zip(p, fill)) < 60
    d = next((i for i in range(n) if close(crop.getpixel((i, i)))), 0)
    return min(round(d / 0.2929), n)

def box_layer(role, x0, y0, x1, y1):
    return {'id':c.layer_id(), 'role':role, 'x':round(x0), 'y':round(y0), 'w':max(1, round(x1 - x0)),
            'h':max(1, round(y1 - y0)), 'rotation':0, 'visible':True, 'locked':False}

def solid(crop, fill, share=0.6):
    """True when most of the crop is close to the fill color (a button or panel, not an illustration)."""
    px = list(crop.convert('RGB').resize((24, 24)).getdata())
    return sum(sum(abs(a - b) for a, b in zip(p, fill)) < 60 for p in px) >= share * len(px)

def refine_text_boxes(texts, image):
    """Tighten approximate vision boxes to local ink. Keep separate text blocks on separate rows.

    This only measures pixels already on disk; it does not call a model. Uncertain and multiline
    blocks retain their original boxes rather than guessing at photo content.
    """
    used, refined = [], list(texts)
    for i in sorted(range(len(texts)), key=lambda k: texts[k][1][1]):
        e, original_box, crop = texts[i]
        if e.get('localOcr') or '\n' in e['text'] or not re.fullmatch(r'#[0-9a-fA-F]{6}',e['colorHex']):
            continue
        x0,y0,x1,y1 = original_box
        pad = max(y1-y0, image.height*.1)
        left,right = max(0,int(x0-image.width*.025)),min(image.width,int(x1+image.width*.025))
        top,bottom = max(0,int(y0-pad)),min(image.height,int(y1+pad))
        target = c.rgb(e['colorHex'])
        pixels = image.load()
        ink = [[sum(abs(a-b) for a,b in zip(pixels[x,y],target)) < 75 for x in range(left,right)] for y in range(top,bottom)]
        if not ink: continue
        active = [sum(row) >= max(3,(right-left)*.012) for row in ink]
        runs, start = [], None
        for y, on in enumerate(active+[False]):
            if on and start is None: start=y
            if not on and start is not None:
                if y-start >= 4: runs.append((start,y))
                start=None
        candidates=[]
        for lo,hi in runs:
            # A large area of matching color is a panel/photo, not a text line.
            if hi-lo > image.height*.13: continue
            columns=[x for x in range(right-left) if any(ink[y][x] for y in range(lo,hi))]
            groups=[]
            for x in columns:
                if not groups or x-groups[-1][-1] > max(8,(hi-lo)*.65): groups.append([])
                groups[-1].append(x)
            for xs in groups:
                box=(left+xs[0],top+lo,left+xs[-1]+1,top+hi)
                if box[2]-box[0] < max(12,len(e['text'])*1.5): continue
                if any(iou(box,b)>.2 for b in used): continue
                if abs((box[1]+box[3]-y0-y1)/2)>max((y1-y0)*1.5,image.height*.05): continue
                distance=abs((box[1]+box[3]-y0-y1)/2)+abs((box[0]+box[2]-x0-x1)/2)*.2
                candidates.append((distance,box))
        if not candidates: continue
        _,box=min(candidates)
        used.append(box)
        refined[i]=(e,box,image.crop(box))
    return refined

def text_geometry(texts, kit, W):
    """Text layers from (element, pixel box, crop). Sizes are shared per role (lines of one headline match),
    and boxes widen to the text's estimated width in the brand font so words do not reflow."""
    raw = [(y1 - y0) / (e['text'].strip().count('\n') + 1) for e, (x0, y0, x1, y1), _ in texts]
    by_role = {}
    for (e, _, _), r in zip(texts, raw):
        by_role.setdefault(e['role'], []).append(r)
    layers = []
    for e, (x0, y0, x1, y1), crop in texts:
        font = nearest_font(kit, e['fontStyle'], e['role'])
        text = e['text'].strip()
        lines = text.split('\n')
        size = round(min(font.maxSize, max(font.minSize, statistics.median(by_role[e['role']]) * 0.9)))
        w = (x1-x0) if e.get('localOcr') else max((x1 - x0) * 1.08, max(map(len, lines)) * size * 0.56)
        x0, x1 = {'left':(x0, x0 + w), 'right':(x1 - w, x1), 'center':((x0 + x1 - w) / 2, (x0 + x1 + w) / 2)}[e['align']]
        role = e['role'] if e['role'] in ('headline', 'subhead', 'body', 'cta') else 'body'
        layers.append(box_layer(role, max(0, x0), y0, min(W, x1), max(y1, y0 + len(lines) * size * 1.15)) | {
            'type':'text', 'text':text, 'fontToken':font.token, 'fontSize':size,
            'colorToken':safe_color(kit, e['colorHex'], crop), 'align':e['align']})
    return layers

def holds_any(kept, b):
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return any(k[1][0] <= cx <= k[1][2] and k[1][1] <= cy <= k[1][3] for k in kept)

def find_button(image, box, margin=6, tolerance=40):
    """Solid button behind a text box: from just outside the text, walk outward along the center row and
    column while the color stays the same. None when the text sits on no distinct solid fill."""
    x0, y0, x1, y1 = (int(v) for v in box)
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    if x0 - margin < 0 or y0 - margin < 0:
        return None
    fill = image.getpixel((x0 - margin, cy))
    same = lambda x, y: 0 <= x < image.width and 0 <= y < image.height and sum(abs(a - b) for a, b in zip(image.getpixel((x, y)), fill)) < tolerance
    if not (same(x1 + margin, cy) and same(cx, y0 - margin) and same(cx, y1 + margin)):
        return None
    left, right, top, bottom = x0 - margin, x1 + margin, y0 - margin, y1 + margin
    while same(left - 1, cy): left -= 1
    while same(right + 1, cy): right += 1
    while same(cx, top - 1): top -= 1
    while same(cx, bottom + 1): bottom += 1
    if (right - left) * (bottom - top) > 0.2 * image.width * image.height:
        return None  # the text sits on a big plane, not a button
    return left, top, right + 1, bottom + 1

def logo_box(logo, box, W):
    """Widen a wordmark-only box to the logo's full aspect so the symbol is covered too."""
    asset = storage.get_asset(logo.assetId)
    x0, y0, x1, y1 = box
    aspect = (asset.width or 1) / (asset.height or 1)
    h = (y1 - y0) * 1.2
    w = max(x1 - x0, h * aspect)
    # ponytail: assumes the symbol sits left of the wordmark (as in most lockups); anchor right.
    return max(0, x1 - w), max(0, y0 - (y1 - y0) * 0.1), x1, y0 - (y1 - y0) * 0.1 + h

def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda r: (r[2] - r[0]) * (r[3] - r[1])
    return ix / (area(a) + area(b) - ix or 1)

def nearest_font(kit, style, role=None):
    require_design_kit(kit)
    if role and role != 'headline':
        body = next((f for f in kit.fonts if f.token=='body'),None)
        if body: return body
    is_serif = lambda f: 'serif' in f.family.lower() and 'sans' not in f.family.lower()
    return min(kit.fonts, key=lambda f: (is_serif(f) != style['serif']) * 1000 + abs(f.weight - style['weight']))

def safe_color(kit, hex_, crop):
    try:
        return c.nearest_color(kit, hex_)
    except (ValueError, IndexError):
        return c.nearest_color(kit, ImageStat.Stat(crop).median)

# Job

def run_decompose(job_id, ws, sample):
    kit = storage.get_brand_kit(ws)
    require_design_kit(kit)
    path = storage.asset_path(sample.id)
    original = flat(path)
    W, H = original.size
    px = lambda b: (b[0] * W, b[1] * H, b[2] * W, b[3] * H)
    c.update_job(job_id, progress='Reading layers')
    elements = read_elements(path)
    ws_name = db.get('Workspace', ws).get('name', '')
    from .ocr import read_text, refine_elements
    elements = refine_elements(elements,read_text(path),original,kit,ws_name)
    texts, logos, shapes, holes = [], [], [], []
    for e in elements:
        x0, y0, x1, y1 = px(e['box'])
        crop = original.crop((int(x0), int(y0), max(int(x1), int(x0) + 1), max(int(y1), int(y0) + 1)))
        # A short text that reads as the brand wordmark is the logo (Flash labels wordmarks either way).
        logo = match_logo(kit, ws_name, e, crop) if e['type'] == 'logo' or len(e['text'].split()) <= 2 else None
        if logo:
            box = (x0,y0,x1,y1) if e.get('localOcr') else logo_box(logo, (x0, y0, x1, y1), W)
            logos.append((box, logo))
            holes.append(box)
        elif e['type'] == 'text' and e['text'].strip():
            texts.append((e, (x0, y0, x1, y1), crop))
        elif e['type'] == 'shape':
            shapes.append((e, (x0, y0, x1, y1), crop))
    texts = refine_text_boxes(texts, original)
    text_layers = text_geometry(texts, kit, W)
    holes += [box for _,box,_ in texts]  # erase source glyphs, not the potentially wider replacement textbox
    c.update_job(job_id, progress='Cleaning background')
    plate, ok = clean_plate(original, holes)
    plate_asset = c.save_png(ws, plate, f'clean plate {sample.caption}', {'sampleAssetId':sample.id})
    c.update_job(job_id, progress='Assembling' + ('' if ok else ' (background edit failed, used flat fill)'))
    layers = [box_layer('background', 0, 0, W, H) | {'type':'image', 'source':'generated', 'assetId':plate_asset.id, 'fit':'cover'}]
    centers = [(l['role'], l['x'] + l['w'] / 2, l['y'] + l['h'] / 2) for l in text_layers]
    holds = lambda b, role=None: any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] and role in (None, r) for r, cx, cy in centers)
    kept = []
    for e, b, crop in shapes:
        fill = c.rgb(e['colorHex']) if re.fullmatch(r'#[0-9a-fA-F]{6}', e['colorHex']) else crop.getpixel((crop.width // 2, crop.height // 2))
        # ponytail: only small solid panels/buttons that hold text become layers; big planes and illustration stay in the plate.
        small = (b[2] - b[0]) * (b[3] - b[1]) < 0.2 * W * H
        if small and solid(crop, fill) and (holds(b) or e['role'] == 'cta_bg') and not any(iou(b, k[1]) > 0.6 for k in kept):
            kept.append((e, b, crop))
            role = 'cta_bg' if holds(b, 'cta') or e['role'] == 'cta_bg' else 'decoration'
            layers.append(box_layer(role, *b) | {'type':'shape', 'shape':'rect',
                          'fillToken':c.nearest_color(kit, fill), 'radius':corner_radius(crop, fill)})
    for l in text_layers:
        b = (l['x'], l['y'], l['x'] + l['w'], l['y'] + l['h'])
        if l['role'] == 'cta' and not holds_any(kept, b):
            button = find_button(original, b)
            if button:
                fill = original.getpixel((int(button[0]) + 3, int((button[1] + button[3]) / 2)))
                crop = original.crop(tuple(int(v) for v in button))
                layers.append(box_layer('cta_bg', *button) | {'type':'shape', 'shape':'rect',
                              'fillToken':c.nearest_color(kit, fill), 'radius':corner_radius(crop, fill)})
    for (x0, y0, x1, y1), logo in logos:
        logo = c.logo_for(kit, c.mean_rgb(storage.asset_path(plate_asset.id), [x0 / W, y0 / H, x1 / W, y1 / H])) or logo
        layers.append(box_layer('logo', x0, y0, x1, y1) | {'type':'image', 'source':'brand_asset', 'assetId':logo.assetId, 'fit':'contain'})
    layers += text_layers
    design = {'id':'des_' + uuid4().hex, 'workspaceId':ws, 'name':f'Layers from {sample.filename}'[:80],
              'width':W, 'height':H, 'background':{'colorToken':c.nearest_color(kit, ImageStat.Stat(plate).mean)}, 'layers':layers}
    from app.brand.lint import lint_design
    issues = lint_design(design, kit)
    c.add_design(job_id, ws, design)
    c.update_job(job_id, progress=f'Done, {len(issues)} brand issue(s) to review' if issues else 'Done')
