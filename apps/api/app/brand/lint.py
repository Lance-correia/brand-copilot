"""Deterministic brand lint. No network: reads only the design, the kit and local font files."""
import math
from functools import lru_cache
from PIL import ImageFont
from app.schema import Design, BrandKit, LintViolation
from app.core import storage
from app.core.validation import validate_contract

RULE_IDS = {'palette': 'COL-01', 'font': 'FONT-01', 'contrast': 'CON-01', 'safe_margin': 'SAFE-01',
            'logo_min_size': 'LOGO-01', 'logo_clear_space': 'CLEAR-01', 'text_overflow': 'TEXT-01'}
SEVERITY = {'palette': 'error', 'font': 'error', 'contrast': 'error', 'safe_margin': 'warning',
            'logo_min_size': 'error', 'logo_clear_space': 'warning', 'text_overflow': 'error'}
LINE_HEIGHT = 1.2  # ponytail: assumed renderer default when a text layer has no lineHeight
UNBOUNDED = ('background', 'hero')

def luminance(hex_):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

def contrast_ratio(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)

@lru_cache(maxsize=512)
def _font(path, size):
    return ImageFont.truetype(path, size)

def font_file(asset_id):
    try:
        path = storage.asset_path(asset_id)
    except KeyError:
        return None
    return str(path) if path.is_file() else None

def wrap(text, font, width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split(' '):
            candidate = f'{line} {word}' if line else word
            if line and font.getlength(candidate) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines

def text_fits(layer, path, size):
    font = _font(path, size)
    lines = wrap(layer.text, font, layer.w)
    height = len(lines) * size * (layer.lineHeight or LINE_HEIGHT)
    return height <= layer.h + 1 and all(font.getlength(line) <= layer.w + 1 for line in lines)

def box(layer):
    return layer.x, layer.y, layer.x + layer.w, layer.y + layer.h

def intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

def contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]

def lint_design(design, kit) -> list[LintViolation]:
    design = Design.model_validate(design)
    kit = BrandKit.model_validate(kit)
    ids = {rule.check: rule.id for rule in reversed(kit.rules)}
    colors = {c.token: c.hex for c in kit.colors}
    fonts = {f.token: f for f in kit.fonts}
    logos = {logo.assetId: logo for logo in kit.logos}
    W, H = design.width, design.height
    mx, my = W * kit.safeMarginPct / 100, H * kit.safeMarginPct / 100
    violations = []

    def flag(check, layer_id, message, fix=()):
        violations.append(LintViolation(ruleId=ids.get(check, RULE_IDS[check]), severity=SEVERITY[check],
                                        layerId=layer_id, message=message, fix=list(fix)))

    def update(layer, **props):
        return [{'op': 'update_layer', 'layerId': layer.id, 'props': props}]

    def best_text_token(backdrop):
        candidates = [c for c in kit.colors if c.role in ('text', 'background')] or kit.colors
        if not candidates:
            return None
        if backdrop is None:
            return next((c.token for c in candidates if c.role == 'text'), candidates[0].token)
        return max(candidates, key=lambda c: contrast_ratio(c.hex, backdrop)).token

    bg = colors.get(design.background.colorToken)
    if bg is None:
        token = next((c.token for c in kit.colors if c.role == 'background'), kit.colors[0].token if kit.colors else None)
        flag('palette', None, f'Background color {design.background.colorToken} is not in the palette',
             [{'op': 'set_background', 'background': {'colorToken': token}}] if token else [])

    def backdrop(index):
        layer = design.layers[index]
        cx, cy = layer.x + layer.w / 2, layer.y + layer.h / 2
        for under in reversed(design.layers[:index]):
            if under.visible and under.type != 'text' and under.x <= cx <= under.x + under.w and under.y <= cy <= under.y + under.h:
                # ponytail: no pixel sampling, so contrast over an image is not checked
                return colors.get(under.fillToken) if under.type == 'shape' else None
        return bg

    for index, layer in enumerate(design.layers):
        if not layer.visible:
            continue
        if layer.type == 'shape' and layer.fillToken not in colors:
            token = next((c.token for c in kit.colors if c.role == 'accent'), kit.colors[0].token if kit.colors else None)
            flag('palette', layer.id, f'Fill {layer.fillToken} is not in the palette', update(layer, fillToken=token) if token else [])
        if layer.type == 'text':
            back = backdrop(index)
            color = colors.get(layer.colorToken)
            if color is None:
                token = best_text_token(back)
                flag('palette', layer.id, f'Color {layer.colorToken} is not in the palette', update(layer, colorToken=token) if token else [])
            font = fonts.get(layer.fontToken)
            if font is None:
                fallback = fonts.get(layer.role) or fonts.get('body') or next(iter(fonts.values()), None)
                flag('font', layer.id, f'Font {layer.fontToken} is not in the brand kit',
                     update(layer, fontToken=fallback.token, fontSize=min(max(layer.fontSize, fallback.minSize), fallback.maxSize)) if fallback else [])
            elif not font.minSize <= layer.fontSize <= font.maxSize:
                size = min(max(layer.fontSize, font.minSize), font.maxSize)
                flag('font', layer.id, f'Size {layer.fontSize:g}px is outside {font.token} range {font.minSize:g}-{font.maxSize:g}px',
                     update(layer, fontSize=size))
            if color and back:
                weight = layer.fontWeight or (font.weight if font else 400)
                need = 3 if layer.fontSize >= 24 or (layer.fontSize >= 18.7 and weight >= 700) else 4.5
                ratio = contrast_ratio(color, back)
                if ratio < need:
                    token = best_text_token(back)
                    better = token and token != layer.colorToken and contrast_ratio(colors[token], back) > ratio
                    flag('contrast', layer.id, f'Contrast {ratio:.2f}:1 is below {need:g}:1', update(layer, colorToken=token) if better else [])
            path = font and font_file(font.assetId)
            if path and layer.text.strip() and not text_fits(layer, path, layer.fontSize):
                size = next((s for s in range(math.ceil(layer.fontSize) - 1, math.ceil(font.minSize) - 1, -1) if text_fits(layer, path, s)), None)
                flag('text_overflow', layer.id, 'Text does not fit its box', update(layer, fontSize=size) if size else [])
        if layer.role not in UNBOUNDED and (layer.x < mx or layer.y < my or layer.x + layer.w > W - mx or layer.y + layer.h > H - my):
            props = {}
            for pos, size, lo, hi in (('x', 'w', math.ceil(mx), math.floor(W - mx)), ('y', 'h', math.ceil(my), math.floor(H - my))):
                length = min(getattr(layer, size), hi - lo)
                start = min(max(getattr(layer, pos), lo), hi - length)
                if length != getattr(layer, size):
                    props[size] = length
                if start != getattr(layer, pos):
                    props[pos] = start
            flag('safe_margin', layer.id, f'{layer.role.capitalize()} is outside the {kit.safeMarginPct:g}% safe margin',
                 update(layer, **props) if props and min(props.get('w', 1), props.get('h', 1)) > 0 else [])
        rule = logos.get(layer.assetId) if layer.type == 'image' and layer.role == 'logo' else None
        if rule:
            if layer.w < rule.minWidth:
                flag('logo_min_size', layer.id, f'Logo must be at least {rule.minWidth:g}px wide',
                     update(layer, w=rule.minWidth, h=round(layer.h * rule.minWidth / layer.w, 2)))
            pad = rule.clearSpace * layer.h
            zone = (layer.x - pad, layer.y - pad, layer.x + layer.w + pad, layer.y + layer.h + pad)
            crowding = [o.id for o in design.layers if o is not layer and o.visible and o.role not in UNBOUNDED
                        and intersects(box(o), zone) and not contains(box(o), box(layer))]
            if crowding:
                flag('logo_clear_space', layer.id, f'Keep {pad:g}px clear around the logo; crowded by {", ".join(crowding)}')
    for violation in violations:
        validate_contract('LintViolation', violation)
    return violations
