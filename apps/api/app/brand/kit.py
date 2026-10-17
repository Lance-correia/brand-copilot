"""Brand-kit extraction: guideline PDF text (DeepSeek-V4-Pro) or page images plus text (DeepSeek-V4.1-Flash vision)
become a draft; then the uploaded files overwrite what they know."""
import base64
import io
import json
import os
import re
from collections import Counter
from pypdf import PdfReader
from PIL import Image
from app.schema import BrandKit
from app.core import storage
from app.core.captions import parse_json
from app.core.config import FIXTURES, use_stubs
from app.core.validation import validate_contract, validators
from .lint import luminance

CHECKS = ('palette', 'font', 'contrast', 'safe_margin', 'logo_min_size', 'logo_clear_space', 'text_overflow', 'manual')
DEFAULT_RULES = [
    {'id': 'COL-01', 'text': 'Use only palette colors', 'check': 'palette'},
    {'id': 'FONT-01', 'text': 'Use brand fonts within their size ranges', 'check': 'font'},
    {'id': 'CON-01', 'text': 'Text meets WCAG AA contrast', 'check': 'contrast'},
    {'id': 'SAFE-01', 'text': 'Keep content inside the safe margin', 'check': 'safe_margin'},
    {'id': 'LOGO-01', 'text': 'Respect the logo minimum width', 'check': 'logo_min_size'},
    {'id': 'CLEAR-01', 'text': 'Keep the logo clear space free', 'check': 'logo_clear_space'},
    {'id': 'TEXT-01', 'text': 'Text fits its box', 'check': 'text_overflow'},
]
FONT_SIZES = {'headline': (32, 120), 'body': (16, 40)}
PAGES_PER_CALL = 8
SYSTEM = ('You extract a brand kit from brand guidelines. Return JSON matching the schema exactly. '
          'colors: token is a short lowercase identifier (use the names in the guidelines when given), hex is #RRGGBB, '
          'role is accent, text, background or neutral. fonts: token is headline, body or another short role name; '
          'assetId is the id of the uploaded font file with the same family; sizes are pixels. '
          'logos: one entry per uploaded logo assetId; variant dark means for light backgrounds; clearSpace is a multiple of logo height. '
          'safeMarginPct is a percentage of the canvas. rules: one per stated rule, with ids like COL-01, FONT-01, LOGO-01. '
          'These checks run automatically, so use them whenever a rule is about that topic: palette (only brand colors), '
          'font (brand fonts and size ranges), contrast, safe_margin, logo_min_size, logo_clear_space, text_overflow. '
          'Use check manual only for rules none of these cover. '
          'Look for colors with hex values, fonts, logo rules (clear space, minimum size, allowed backgrounds), safe zones and tone. '
          'Allowed logo backgrounds go in variant and in a manual rule. clearSpace is the stated clear space in logo heights '
          '("half the logo height" is 0.5). A safe zone becomes safeMarginPct. Use 0 for any number the guidelines do not state. '
          'voice is the tone of voice and imageryStyle the photo style, one sentence each. confirmed is false.')

def slug(text):
    return re.sub(r'[^a-z0-9]+', '_', str(text).lower()).strip('_')

def num(value, default, minimum=0):
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value >= minimum
    return value if ok else default

def pdf_text(path):
    try:
        return '\n'.join(page.extract_text() or '' for page in PdfReader(path).pages).strip()
    except Exception:
        return ''

def page_image(path):
    """Guideline page as a JPEG data URL, downscaled so eight pages fit one request."""
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG', quality=85)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode()

def merge_drafts(drafts):
    """Concatenate list fields (the cleanup in extract_brand_kit dedupes); first stated value wins for the rest."""
    merged = {key: [item for d in drafts for item in d.get(key) or []] for key in ('colors', 'fonts', 'logos', 'rules')}
    for key in ('safeMarginPct', 'imageryStyle', 'voice'):
        merged[key] = next((d[key] for d in drafts if d.get(key)), None)
    return merged

def model_draft(ws_id, text, pages, logos, fonts):
    if use_stubs():
        return json.loads((FIXTURES / 'brand/brand-kit.json').read_text())
    from app.llm.deepseek import chat
    schema = {k: v for k, v in validators()['BrandKit'].schema.items() if k not in ('$schema', '$id', 'title')}
    uploads = [{'assetId': a.id, 'kind': a.kind, 'filename': a.filename, **a.meta} for a in logos + fonts]
    intro = f'Workspace id: {ws_id}\nUploaded assets:\n{json.dumps(uploads, indent=1)}'
    guidelines = f'\n\nGuidelines text:\n{text[:40000]}' if text else ''
    def ask(model, prompt, images=None):
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}]
        return parse_json(chat(os.getenv(model), messages, json_schema=schema, images=images).choices[0].message.content)
    if not pages:
        return ask('DEEPSEEK_PRO_MODEL', intro + guidelines)
    drafts = []
    for start in range(0, len(pages), PAGES_PER_CALL):
        chunk = pages[start:start + PAGES_PER_CALL]
        note = f'\n\nAttached: guideline pages {start + 1}-{start + len(chunk)} of {len(pages)}. Extract only what these pages and the text state.'
        drafts.append(ask('DEEPSEEK_FLASH_MODEL', intro + note + (guidelines if start == 0 else ''),
                          [page_image(storage.asset_path(p.id)) for p in chunk]))
    return merge_drafts(drafts)

def to_hex(rgb):
    return '#' + ''.join(f'{v:02X}' for v in rgb[:3])

def svg_colors(path):
    text = path.read_text(errors='ignore')
    found = re.findall(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', text)
    return ['#' + (c if len(c) == 6 else ''.join(ch * 2 for ch in c)).upper() for c in found]

def opaque_pixels(path, size=64):
    try:
        with Image.open(path) as image:
            image = image.convert('RGBA')
            image.thumbnail((size, size))
            data = image.tobytes()
            return [tuple(data[i:i + 3]) for i in range(0, len(data), 4) if data[i + 3] >= 128]
    except OSError:
        return []

def saturation(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return (max(r, g, b) - min(r, g, b)) / 255

def distance(a, b):
    return sum((int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) ** 2 for i in (1, 3, 5)) ** 0.5

def derive_palette(assets, limit=6):
    """Logo SVG fills first, then k-means clusters of logo and brand-image pixels; always a light and a dark."""
    logos = [a for a in assets if a.kind == 'logo']
    images = [a for a in assets if a.kind == 'image' and a.source == 'brand_asset']
    candidates = list(dict.fromkeys(c for a in logos if a.mime == 'image/svg+xml' for c in svg_colors(storage.asset_path(a.id))))
    pixels = [p for a in logos + images if a.mime != 'image/svg+xml' for p in opaque_pixels(storage.asset_path(a.id))]
    if pixels:
        strip = Image.new('RGB', (len(pixels), 1))
        strip.putdata(pixels)
        quantized = strip.quantize(colors=limit, kmeans=10)
        palette = quantized.getpalette()
        candidates += [to_hex(palette[3 * i:3 * i + 3]) for _, i in sorted(quantized.getcolors(), reverse=True)]
    chosen = ([c for c in candidates if luminance(c) >= 0.8][:1] or ['#FFFFFF']) + ([c for c in candidates if luminance(c) <= 0.05][:1] or ['#111111'])
    for color in candidates:
        if len(chosen) < limit and all(distance(color, c) > 48 for c in chosen):
            chosen.append(color)
    for extra in candidates + ['#6B6B6B']:
        if len(chosen) >= 3:
            break
        if extra not in chosen:
            chosen.append(extra)
    light, dark = max(chosen, key=luminance), min(chosen, key=luminance)
    rest = sorted((c for c in chosen if c not in (light, dark)), key=saturation, reverse=True)
    names = iter(('primary', 'secondary', 'tertiary', 'quaternary'))
    return ([{'token': 'paper', 'hex': light, 'role': 'background'}, {'token': 'ink', 'hex': dark, 'role': 'text'}]
            + [{'token': next(names), 'hex': c, 'role': 'accent' if saturation(c) > 0.25 else 'neutral'} for c in rest])

def logo_variant(asset):
    name = asset.filename.lower()
    if re.search(r'light|white|reverse|inverse', name):
        return 'light'
    if re.search(r'dark|black', name):
        return 'dark'
    path = storage.asset_path(asset.id)
    colors = svg_colors(path) if asset.mime == 'image/svg+xml' else [to_hex(p) for p in opaque_pixels(path, 32)]
    return 'light' if colors and sum(map(luminance, colors)) / len(colors) > 0.5 else 'dark'

def link_fonts(draft_fonts, font_assets):
    family = lambda a: str(a.meta.get('family') or a.filename)
    fonts, used = [], set()
    for draft in draft_fonts:
        name = slug(draft.get('family', '')).replace('_', '')
        matches = [a for a in font_assets if a.id not in used and name
                   and (slug(family(a)).replace('_', '') in name or name in slug(family(a)).replace('_', ''))]
        if matches:
            asset = min(matches, key=lambda a: abs(a.meta.get('weight', 400) - draft.get('weight', 400)))
            used.add(asset.id)
            fonts.append({**draft, 'family': family(asset), 'assetId': asset.id})
    # Uploaded fonts the draft did not mention: display-looking families take the headline slot first.
    spare = sorted((a for a in font_assets if a.id not in used), key=lambda a: not re.search(r'display|head|title|poster', family(a), re.I))
    for asset in spare:
        token = next(t for t in ('headline', 'body', *(f'font_{i}' for i in range(2, 99))) if t not in {f['token'] for f in fonts})
        lo, hi = FONT_SIZES.get(token, (16, 64))
        fonts.append({'token': token, 'family': family(asset), 'weight': int(asset.meta.get('weight', 400)),
                      'assetId': asset.id, 'minSize': lo, 'maxSize': hi})
    seen = set()
    for font in fonts:
        font['token'] = slug(font.get('token')) or 'font'
        while font['token'] in seen:
            font['token'] += '_2'
        seen.add(font['token'])
        font['weight'] = min(max(int(font.get('weight') or 400), 1), 1000)
        lo, hi = FONT_SIZES.get(font['token'], (16, 64))
        font['minSize'] = num(font.get('minSize'), lo, 1)
        font['maxSize'] = max(num(font.get('maxSize'), hi, 1), font['minSize'])
    return [{k: f[k] for k in ('token', 'family', 'weight', 'assetId', 'minSize', 'maxSize')} for f in fonts]

def extract_brand_kit(ws_id) -> BrandKit:
    assets = storage.list_assets(ws_id)
    logos = [a for a in assets if a.kind == 'logo']
    fonts = [a for a in assets if a.kind == 'font']
    guidelines = [a for a in assets if a.kind == 'guideline']
    text = '\n\n'.join(pdf_text(storage.asset_path(a.id)) for a in guidelines if a.mime == 'application/pdf').strip()
    pages = [a for a in guidelines if a.mime != 'application/pdf']
    if text or pages:
        draft = model_draft(ws_id, text, pages, logos, fonts)
    else:
        tags = Counter(t for a in assets if a.kind == 'image' for t in a.tags if t != 'image')
        draft = {'colors': derive_palette(assets), 'safeMarginPct': 6, 'rules': DEFAULT_RULES, 'voice': 'Clear, warm and concise',
                 'imageryStyle': 'In the style of the approved brand images' + (': ' + ', '.join(t for t, _ in tags.most_common(5)) if tags else '')}

    colors, tokens = [], set()
    for color in draft.get('colors') or []:
        token, hex_ = slug(color.get('token')), str(color.get('hex', '')).upper()
        if token and token not in tokens and re.fullmatch(r'#[0-9A-F]{6}', hex_) and hex_ not in {c['hex'] for c in colors}:
            tokens.add(token)
            colors.append({'token': token, 'hex': hex_, 'role': slug(color.get('role')) or 'accent'})
    if len(colors) < 3:
        for color in derive_palette(assets):
            if len(colors) < 3 and color['token'] not in tokens and all(distance(color['hex'], c['hex']) > 48 for c in colors):
                tokens.add(color['token'])
                colors.append(color)

    draft_logos, logo_rules = draft.get('logos') or [], []
    for asset in logos:
        # This logo's entries first, then any other; 0 counts as not stated (models emit it for missing values).
        ordered = [l for l in draft_logos if l.get('assetId') == asset.id] + draft_logos
        stated = lambda key, default: next((l[key] for l in ordered if num(l.get(key), 0) > 0), default)
        logo_rules.append({'assetId': asset.id, 'variant': logo_variant(asset),
                           'minWidth': stated('minWidth', 120), 'clearSpace': stated('clearSpace', 0.5)})

    rules, ids = [], set()
    for rule in draft.get('rules') or DEFAULT_RULES:
        if rule.get('id') and rule['id'] not in ids and rule.get('check') in CHECKS:
            ids.add(rule['id'])
            rules.append({'id': str(rule['id']), 'text': str(rule.get('text', '')), 'check': rule['check']})

    # Lint always runs every automatic check, so the kit lists a rule for each one.
    rules += [r for r in DEFAULT_RULES if r['check'] not in {x['check'] for x in rules} and r['id'] not in ids]
    kit = {'workspaceId': ws_id, 'colors': colors, 'fonts': link_fonts(draft.get('fonts') or [], fonts), 'logos': logo_rules,
           'safeMarginPct': min(num(draft.get('safeMarginPct') or None, 6), 50),  # 0 means not stated
           'imageryStyle': str(draft.get('imageryStyle') or ''), 'voice': str(draft.get('voice') or ''),
           'rules': rules, 'confirmed': False}
    from .fonts import ensure_fonts
    return ensure_fonts(BrandKit.model_validate(validate_contract('BrandKit', kit)))
