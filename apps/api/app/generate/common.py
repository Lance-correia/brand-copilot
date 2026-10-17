"""Shared helpers: in-memory jobs, templates, color/font token math, applying ops."""
import json
import re
import threading
from copy import deepcopy
from uuid import uuid4
from PIL import Image, ImageStat
from app.core import db, storage
from app.core.config import FIXTURES
from app.core.validation import validate_contract
from app.schema import BrandKit

# ponytail: in-memory jobs, lost on restart; fine for a local single-user app.
JOBS = {}
LOCK = threading.Lock()

def new_job():
    job_id = 'job_' + uuid4().hex
    JOBS[job_id] = {'id':job_id, 'status':'queued', 'progress':'Queued', 'designs':[], 'error':None}
    return job_id

def update_job(job_id, **fields):
    with LOCK:
        JOBS[job_id].update(fields)

def add_design(job_id, ws, design):
    design = validate_contract('Design', design)
    db.put('Design', design['id'], ws, design)
    with LOCK:
        JOBS[job_id]['designs'].append(design)

def run_job(job_id, fn, *args):
    update_job(job_id, status='running')
    try:
        fn(job_id, *args)
        update_job(job_id, status='done')
    except Exception as exc:  # surface any failure on the job instead of a silent dead thread
        update_job(job_id, status='error', error=f'{type(exc).__name__}: {exc}'[:500])

def templates():
    return [validate_contract('Template', json.loads(p.read_text())) for p in sorted((FIXTURES / 'templates').glob('*.json'))]

def layer_id():
    return 'lay_' + uuid4().hex[:10]

def slug(text, n=48):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:n] or 'image'

def save_png(ws, image, name, meta=None):
    import io
    buf = io.BytesIO()
    image.save(buf, 'PNG')
    return storage.save_asset(ws, buf.getvalue(), f'{slug(name)}.png', 'image', 'generated', meta)

# Color math

def rgb(hex_):
    hex_ = hex_.lstrip('#')
    if len(hex_) == 3:
        hex_ = ''.join(c * 2 for c in hex_)
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))

def luminance(color):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(color) if isinstance(color, str) else color[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)

def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

def token_hex(kit: BrandKit, token):
    return next((c.hex for c in kit.colors if c.token == token), kit.colors[0].hex)

def nearest_color(kit: BrandKit, color):
    target = rgb(color) if isinstance(color, str) else color[:3]
    return min(kit.colors, key=lambda c: sum((a - b) ** 2 for a, b in zip(rgb(c.hex), target))).token

def readable_token(kit: BrandKit, backdrop, preferred=None, minimum=4.5):
    """preferred token if it reads on backdrop (hex or rgb), else the palette token with the best contrast."""
    if preferred and any(c.token == preferred for c in kit.colors) and contrast(token_hex(kit, preferred), backdrop) >= minimum:
        return preferred
    return max(kit.colors, key=lambda c: contrast(c.hex, backdrop)).token

def role_token(kit: BrandKit, role, fallback=0):
    return next((c.token for c in kit.colors if c.role == role), kit.colors[fallback].token)

def logo_for(kit: BrandKit, backdrop):
    """Kit logo for a backdrop: dark variant on light, light variant on dark."""
    want = 'dark' if luminance(backdrop) > 0.4 else 'light'
    return next((l for l in kit.logos if l.variant == want), kit.logos[0] if kit.logos else None)

def mean_rgb(path, box=None):
    """Average color of an image file, optionally of a [x0,y0,x1,y1] fraction box."""
    with Image.open(path) as im:
        im = im.convert('RGB')
        if box:
            w, h = im.size
            im = im.crop((int(box[0] * w), int(box[1] * h), max(int(box[2] * w), int(box[0] * w) + 1), max(int(box[3] * h), int(box[1] * h) + 1)))
        return tuple(int(v) for v in ImageStat.Stat(im).mean)

# Fonts

def font_for(kit: BrandKit, role):
    tokens = {f.token: f for f in kit.fonts}
    if role == 'headline':
        return tokens.get('headline') or kit.fonts[0]
    return tokens.get('body') or kit.fonts[-1]

def fit_font_size(text, w, h, font, line_height=1.15, char_width=0.55):
    """Largest size in the font token's range whose wrapped text fits w x h (estimate: char width = 0.55em)."""
    words = text.split() or ['']
    for size in range(int(font.maxSize), int(font.minSize) - 1, -2):
        per_line = max(1, int(w / (size * char_width)))
        lines, current = 1, 0
        for word in words:
            if current and current + 1 + len(word) > per_line:
                lines, current = lines + 1, len(word)
            else:
                current += len(word) + (1 if current else 0)
        if lines * size * line_height <= h and max(map(len, words)) <= per_line:
            return size
    return font.minSize

# Ops

def apply_ops(design, ops):
    """Apply EditOps to a copy of a Design dict and return it, schema-validated."""
    design = deepcopy(design)
    layers = design['layers']
    index = lambda lid: next(i for i, l in enumerate(layers) if l['id'] == lid)
    for op in ops:
        op = op if isinstance(op, dict) else op.model_dump(mode='json', exclude_unset=True)
        kind = op['op']
        if kind == 'add_layer':
            layers.insert(op.get('index', len(layers)), op['layer'])
        elif kind == 'update_layer':
            layers[index(op['layerId'])].update(op['props'])
        elif kind == 'remove_layer':
            layers.pop(index(op['layerId']))
        elif kind == 'reorder_layer':
            layers.insert(op['index'], layers.pop(index(op['layerId'])))
        elif kind == 'replace_image':
            layers[index(op['layerId'])].update(assetId=op['assetId'], source=op['source'])
        elif kind == 'set_background':
            design['background'] = op['background']
    return validate_contract('Design', design)

def lint_fix(design, kit, rounds=2):
    """Run lint and apply its deterministic fixes, at most `rounds` times. Returns (design, remaining violations)."""
    from app.brand.lint import lint_design
    violations = lint_design(design, kit)
    for _ in range(rounds):
        fixes = [op for v in violations for op in v.fix]
        if not fixes:
            break
        design = apply_ops(design, fixes)
        violations = lint_design(design, kit)
    return design, violations
