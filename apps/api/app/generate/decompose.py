"""Image to layers: read elements (Flash), clean the background plate (edit model), assemble an editable design."""
import difflib
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFilter, ImageStat
from app.core import db, storage
from app.llm import deepseek, images
from . import common as c

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
        'role: headline, subhead, body, cta (button label), cta_bg (button shape), logo, hero, decoration or background.'),
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
    draw, mdraw = ImageDraw.Draw(work), ImageDraw.Draw(mask)
    for x0, y0, x1, y1 in holes:
        box = (max(0, int(x0 * s) - PAD), max(0, int(y0 * s) - PAD), min(pw, int(x1 * s) + PAD), min(ph, int(y1 * s) + PAD))
        # Pre-fill holes so text and brand-logo pixels never reach the image model.
        draw.rectangle(box, fill=ring_color(work, box))
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
        if asset.mime.startswith('image/') and asset.mime != 'image/svg+xml':
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

def nearest_font(kit, style):
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
    path = storage.asset_path(sample.id)
    original = flat(path)
    W, H = original.size
    px = lambda b: (b[0] * W, b[1] * H, b[2] * W, b[3] * H)
    c.update_job(job_id, progress='Reading layers')
    elements = read_elements(path)
    ws_name = db.get('Workspace', ws).get('name', '')
    texts, logos, shapes, holes = [], [], [], []
    for e in elements:
        x0, y0, x1, y1 = px(e['box'])
        crop = original.crop((int(x0), int(y0), max(int(x1), int(x0) + 1), max(int(y1), int(y0) + 1)))
        if e['type'] == 'text' and e['text'].strip():
            texts.append((e, (x0, y0, x1, y1), crop))
            holes.append((x0, y0, x1, y1))
        elif e['type'] == 'logo':
            logo = match_logo(kit, ws_name, e, crop)
            if logo:  # unmatched logos stay in the plate
                logos.append(((x0, y0, x1, y1), logo))
                holes.append((x0, y0, x1, y1))
        elif e['type'] == 'shape':
            shapes.append((e, (x0, y0, x1, y1), crop))
    c.update_job(job_id, progress='Cleaning background')
    plate, ok = clean_plate(original, holes)
    plate_asset = c.save_png(ws, plate, f'clean plate {sample.caption}', {'sampleAssetId':sample.id})
    c.update_job(job_id, progress='Assembling' + ('' if ok else ' (background edit failed, used flat fill)'))
    base = lambda role, x0, y0, x1, y1: {'id':c.layer_id(), 'role':role, 'x':round(x0), 'y':round(y0),
        'w':max(1, round(x1 - x0)), 'h':max(1, round(y1 - y0)), 'rotation':0, 'visible':True, 'locked':False}
    layers = [base('background', 0, 0, W, H) | {'type':'image', 'source':'generated', 'assetId':plate_asset.id, 'fit':'cover'}]
    cta_centers = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for e, b, _ in texts if e['role'] == 'cta']
    for e, (x0, y0, x1, y1), crop in shapes:
        fill = c.rgb(e['colorHex']) if e['colorHex'].startswith('#') and len(e['colorHex']) in (4, 7) else crop.getpixel((crop.width // 2, crop.height // 2))
        role = 'cta_bg' if any(x0 <= cx <= x1 and y0 <= cy <= y1 for cx, cy in cta_centers) else ('cta_bg' if e['role'] == 'cta_bg' else 'decoration')
        layers.append(base(role, x0, y0, x1, y1) | {'type':'shape', 'shape':'rect',
                      'fillToken':c.nearest_color(kit, fill), 'radius':corner_radius(crop, fill)})
    for (x0, y0, x1, y1), logo in logos:
        logo = c.logo_for(kit, c.mean_rgb(storage.asset_path(plate_asset.id), [x0 / W, y0 / H, x1 / W, y1 / H])) or logo
        layers.append(base('logo', x0, y0, x1, y1) | {'type':'image', 'source':'brand_asset', 'assetId':logo.assetId, 'fit':'contain'})
    for e, (x0, y0, x1, y1), crop in texts:
        font = nearest_font(kit, e['fontStyle'])
        lines = e['text'].count('\n') + 1
        size = min(font.maxSize, max(font.minSize, round((y1 - y0) / lines / 1.15)))
        role = e['role'] if e['role'] in ('headline', 'subhead', 'body', 'cta') else 'body'
        # Brand fonts differ from the source font: give a little extra width so words do not reflow.
        grow = (x1 - x0) * 0.08
        x0, x1 = {'left':(x0, x1 + grow), 'right':(x0 - grow, x1), 'center':(x0 - grow / 2, x1 + grow / 2)}[e['align']]
        layers.append(base(role, max(0, x0), y0, min(W, x1), max(y1, y0 + lines * size * 1.15)) | {
            'type':'text', 'text':e['text'].strip(), 'fontToken':font.token, 'fontSize':size,
            'colorToken':safe_color(kit, e['colorHex'], crop), 'align':e['align']})
    design = {'id':'des_' + uuid4().hex, 'workspaceId':ws, 'name':f'Layers from {sample.filename}'[:80],
              'width':W, 'height':H, 'background':{'colorToken':c.nearest_color(kit, ImageStat.Stat(plate).mean)}, 'layers':layers}
    from app.brand.lint import lint_design
    issues = lint_design(design, kit)
    c.add_design(job_id, ws, design)
    c.update_job(job_id, progress=f'Done, {len(issues)} brand issue(s) to review' if issues else 'Done')
