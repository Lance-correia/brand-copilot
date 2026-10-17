"""Deterministic brand lint. No network: reads only the design, the kit and local font and image files."""
import math
from functools import lru_cache
from PIL import Image, ImageFont, ImageStat
from app.schema import Design, BrandKit, LintViolation
from app.core import storage
from app.core.validation import validate_contract

RULE_IDS = {'palette': 'COL-01', 'font': 'FONT-01', 'contrast': 'CON-01', 'safe_margin': 'SAFE-01',
            'logo_min_size': 'LOGO-01', 'logo_clear_space': 'CLEAR-01', 'text_overflow': 'TEXT-01'}
SEVERITY = {'palette': 'error', 'font': 'error', 'contrast': 'error', 'safe_margin': 'warning',
            'logo_min_size': 'error', 'logo_clear_space': 'warning', 'text_overflow': 'error'}
LINE_HEIGHT = 1.2  # ponytail: assumed renderer default when a text layer has no lineHeight
UNBOUNDED = ('background', 'hero')

def channel(v):
    v /= 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

def luminance(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

def ratio(a, b):
    """WCAG contrast ratio of two relative luminances."""
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)

def contrast_ratio(a, b):
    return ratio(luminance(a), luminance(b))

LINEAR = [round(channel(v) * 255) for v in range(256)] * 3  # ponytail: 8-bit linear light, ~0.004 luminance steps

@lru_cache(maxsize=32)
def _luma_image(path, mtime):
    """Linear-light relative luminance (0-255) of a downscaled copy of the image."""
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((256, 256))
        return image.point(LINEAR).convert('L', matrix=(0.2126, 0.7152, 0.0722, 0))

def image_luminance(layer, region):
    """Mean luminance of the part of an image layer drawn under region, or None where nothing is drawn.
    Assumes the canvas centers the image, scaled to cover (cropped) or contain (letterboxed)."""
    try:
        path = storage.asset_path(layer.assetId)
        luma = _luma_image(str(path), path.stat().st_mtime)
    except (KeyError, OSError):
        return None
    tw, th = luma.size
    scale = (max if layer.fit == 'cover' else min)(layer.w / tw, layer.h / th)
    ox, oy = layer.x + (layer.w - tw * scale) / 2, layer.y + (layer.h - th * scale) / 2
    x0, y0 = max(region[0], layer.x, ox), max(region[1], layer.y, oy)
    x1, y1 = min(region[2], layer.x + layer.w, ox + tw * scale), min(region[3], layer.y + layer.h, oy + th * scale)
    if x0 >= x1 or y0 >= y1:
        return None
    left, top = min(math.floor((x0 - ox) / scale), tw - 1), min(math.floor((y0 - oy) / scale), th - 1)
    crop = (left, top, max(math.ceil((x1 - ox) / scale), left + 1), max(math.ceil((y1 - oy) / scale), top + 1))
    return ImageStat.Stat(luma.crop(crop)).mean[0] / 255

from app.core.typography import measured_font as _font, font_path as font_file, wrap, metrics

def text_fits(layer, path, size, weight=None):
    width,height=metrics(layer.text,path,size,layer.w,layer.lineHeight or LINE_HEIGHT,weight or layer.fontWeight or 400)
    return width<=layer.w+1 and height<=layer.h+1

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

    def best_text_token(back):
        """Kit text or background token with the best contrast against luminance back."""
        candidates = [c for c in kit.colors if c.role in ('text', 'background')] or kit.colors
        if not candidates:
            return None
        if back is None:
            return next((c.token for c in candidates if c.role == 'text'), candidates[0].token)
        return max(candidates, key=lambda c: ratio(luminance(c.hex), back)).token

    bg = colors.get(design.background.colorToken)
    if bg is None:
        token = next((c.token for c in kit.colors if c.role == 'background'), kit.colors[0].token if kit.colors else None)
        flag('palette', None, f'Background color {design.background.colorToken} is not in the palette',
             [{'op': 'set_background', 'background': {'colorToken': token}}] if token else [])

    def backdrop(index):
        """(luminance, over_image) of what the text sits on: the topmost shape or image under its center, else the background."""
        layer = design.layers[index]
        cx, cy = layer.x + layer.w / 2, layer.y + layer.h / 2
        for under in reversed(design.layers[:index]):
            if under.visible and under.type != 'text' and under.x <= cx <= under.x + under.w and under.y <= cy <= under.y + under.h:
                if under.type == 'shape':
                    return (luminance(colors[under.fillToken]) if under.fillToken in colors else None), False
                sampled = image_luminance(under, box(layer))
                if sampled is not None:  # None: letterboxed gap or missing file, so look further down
                    return sampled, True
        return (luminance(bg) if bg else None), False

    def shape_behind(index, layer, need):
        """Add a cta_bg-style plate in the kit's background color under the text, recoloring the text if it then fails."""
        fill = next((c for c in kit.colors if c.role == 'background'), None) or max(
            kit.colors, key=lambda c: contrast_ratio(c.hex, colors[layer.colorToken]), default=None)
        if fill is None:
            return []
        pad = round(layer.fontSize * 0.4)
        x0, y0 = max(layer.x - pad, min(layer.x, math.ceil(mx))), max(layer.y - pad, min(layer.y, math.ceil(my)))
        x1 = min(layer.x + layer.w + pad, max(layer.x + layer.w, math.floor(W - mx)))
        y1 = min(layer.y + layer.h + pad, max(layer.y + layer.h, math.floor(H - my)))
        taken, plate_id = {l.id for l in design.layers}, f'{layer.id}_bg'
        while plate_id in taken:
            plate_id += '_2'
        plate = {'id': plate_id, 'type': 'shape', 'role': 'cta_bg', 'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0, 'rotation': 0,
                 'visible': True, 'locked': False, 'shape': 'rect', 'fillToken': fill.token, 'radius': min(pad, (y1 - y0) / 2)}
        ops = [{'op': 'add_layer', 'layer': plate, 'index': index}]
        if contrast_ratio(colors[layer.colorToken], fill.hex) < need:
            ops += update(layer, colorToken=best_text_token(luminance(fill.hex)))
        return ops

    for index, layer in enumerate(design.layers):
        if not layer.visible:
            continue
        if layer.type == 'shape' and layer.fillToken not in colors:
            token = next((c.token for c in kit.colors if c.role == 'accent'), kit.colors[0].token if kit.colors else None)
            flag('palette', layer.id, f'Fill {layer.fillToken} is not in the palette', update(layer, fillToken=token) if token else [])
        if layer.type == 'text':
            back, over_image = backdrop(index)
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
            if color and back is not None:
                weight = layer.fontWeight or (font.weight if font else 400)
                need = 3 if layer.fontSize >= 24 or (layer.fontSize >= 18.7 and weight >= 700) else 4.5
                current = ratio(luminance(color), back)
                if current < need:
                    token = best_text_token(back)
                    best = ratio(luminance(colors[token]), back)
                    if over_image and best < need:
                        fix = shape_behind(index, layer, need)
                    else:
                        fix = update(layer, colorToken=token) if token != layer.colorToken and best > current else []
                    flag('contrast', layer.id, f'Contrast {current:.2f}:1 {"over the image " if over_image else ""}is below {need:g}:1', fix)
            path = font and font_file(font.assetId)
            if path and layer.text.strip() and not text_fits(layer, path, layer.fontSize, font.weight):
                size = next((s for s in range(math.ceil(layer.fontSize) - 1, math.ceil(font.minSize) - 1, -1) if text_fits(layer, path, s, font.weight)), None)
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
            for other in design.layers:  # no fix: which layer should move is a design call
                if (other is not layer and other.visible and other.role not in UNBOUNDED
                        and intersects(box(other), zone) and not contains(box(other), box(layer))):
                    flag('logo_clear_space', other.id,
                         f'Layer {other.id} ({other.role}) is inside the {pad:g}px clear space around logo {layer.id}')
    for violation in violations:
        validate_contract('LintViolation', violation)
    return violations
