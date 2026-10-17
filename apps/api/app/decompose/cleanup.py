"""Text removal: rebuild simple surfaces locally; mask and verify photographic repairs.

Only the compositing mask may change source pixels. A sanitized working copy hides
detected lettering and logos from the image model. No stored brand asset is an input.
"""
import io
import math
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat
from app.llm import images

REVISION = 'surface-mask-v3'
PROMPT = ('Restore the underlying background in the masked areas. Continue the surrounding '
          'surface, texture, lighting and edges naturally. Keep the composition unchanged. '
          'Return a fully opaque image with no holes, frames, panels or new objects. '
          'No text, letters, logos or watermarks.')

@dataclass
class CleanupResult:
    image: Image.Image
    mask: Image.Image
    methods: list[str]
    model_calls: int
    findings: list[dict]

def _median(pixels):
    return tuple(round(statistics.median(p[c] for p in pixels)) for c in range(3))

def _pixels(image):
    return list(image.get_flattened_data() if hasattr(image,'get_flattened_data') else image.getdata())

def surface(image, box):
    """Predict a flat/linear-gradient surface from pixels around, rather than inside, text."""
    x0,y0,x1,y1=box
    crop=image.crop(box)
    w,h=crop.size
    edge=max(1,min(3,w//4,h//4))
    corners=[]
    for cx,cy in [(0,0),(w-edge,0),(0,h-edge),(w-edge,h-edge)]:
        corners.append(_median(_pixels(crop.crop((cx,cy,cx+edge,cy+edge)))))
    tile=Image.new('RGB',(2,2));tile.putdata(corners)
    predicted=tile.resize((w,h),Image.Resampling.BILINEAR)
    # Sample only the perimeter: lettering in the middle must not bias the surface color.
    errors=[]
    for x in range(0,w,max(1,w//64)):
        for y in (0,h-1): errors.append(max(abs(a-b) for a,b in zip(crop.getpixel((x,y)),predicted.getpixel((x,y)))))
    for y in range(0,h,max(1,h//32)):
        for x in (0,w-1): errors.append(max(abs(a-b) for a,b in zip(crop.getpixel((x,y)),predicted.getpixel((x,y)))))
    errors.sort()
    simple=errors[int((len(errors)-1)*.9)]<=15
    return predicted,simple

def _ink_mask(crop, predicted):
    # This follows glyph pixels on simple surfaces rather than erasing a rectangular patch.
    diff=ImageChops.difference(crop,predicted)
    channels=diff.split()
    distance=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
    return distance.point(lambda v:255 if v>22 else 0).filter(ImageFilter.MaxFilter(3))

def _photo_mask(crop,region):
    """Follow confidently colored lettering; uncertain colors and logos use the bounded ROI."""
    color=region.get('colorHex','')
    if region.get('kind')=='text' and len(color)==7 and color.startswith('#'):
        try:
            foreground=Image.new('RGB',crop.size,color)
            channels=ImageChops.difference(crop,foreground).split()
            distance=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
            mask=distance.point(lambda v:255 if v<64 else 0)
            share=ImageStat.Stat(mask).mean[0]/255
            if .01<share<.4:return mask.filter(ImageFilter.MaxFilter(5))
        except ValueError:pass
    return Image.new('L',crop.size,255)

def _box(region,W,H,pad=5):
    x0,y0,x1,y1=region['box']
    return (max(0,math.floor(x0)-pad),max(0,math.floor(y0)-pad),
            min(W,math.ceil(x1)+pad),min(H,math.ceil(y1)+pad))

def clean(original, regions, edit=None):
    original=original.convert('RGB')
    W,H=original.size
    plate=original.copy()
    sanitized=original.copy()
    flat_mask=Image.new('L',(W,H),0)
    photo_mask=Image.new('L',(W,H),0)
    methods=set()
    for region in regions:
        box=_box(region,W,H)
        if box[0]>=box[2] or box[1]>=box[3]:continue
        predicted,simple=surface(original,box)
        # Always hide the whole detection on model input, including antialiasing and logos.
        sanitized.paste(predicted,box[:2])
        if simple:
            local=_ink_mask(original.crop(box),predicted)
            plate.paste(predicted,box[:2],local)
            flat_mask.paste(ImageChops.lighter(flat_mask.crop(box),local),box[:2])
            methods.add('local_surface')
        else:
            local=_photo_mask(original.crop(box),region)
            photo_mask.paste(ImageChops.lighter(photo_mask.crop(box),local),box[:2])
            methods.add('masked_inpaint')
    mask=ImageChops.lighter(flat_mask,photo_mask)
    if not photo_mask.getbbox():return CleanupResult(plate,mask,sorted(methods),0,[])
    # Use an exact scale and padding, then crop it away. Never stretch to a new aspect ratio.
    scale=min(1,1536/max(W,H))
    w,h=round(W*scale),round(H*scale)
    pw,ph=math.ceil(max(w,h/3)/16)*16,math.ceil(max(h,w/3)/16)*16
    work=Image.new('RGB',(pw,ph),_median(_pixels(sanitized.resize((16,16)))))
    work.paste(sanitized.resize((w,h)),(0,0))
    alpha=Image.new('L',(pw,ph),255)
    alpha.paste(ImageChops.invert(photo_mask).resize((w,h),Image.Resampling.NEAREST),(0,0))
    api_mask=Image.new('RGBA',(pw,ph),'black');api_mask.putalpha(alpha)
    calls,findings=0,[]
    edit=edit or images.edit
    repaired=None
    with tempfile.TemporaryDirectory() as folder:
        source,mask_path=Path(folder)/'sanitized.png',Path(folder)/'mask.png'
        work.save(source);api_mask.save(mask_path)
        # A single bounded fallback handles providers that return transparent masked pixels.
        for masked in (True,False):
            try:
                calls+=1
                data=edit(source,PROMPT,mask_path=mask_path if masked else None)
                output=Image.open(io.BytesIO(data)).convert('RGBA')
                if output.size!=(pw,ph):output=output.resize((pw,ph))
                coverage=ImageStat.Stat(output.getchannel('A'),ImageChops.invert(alpha)).mean[0]
                if coverage<250:raise ValueError('Transparent repair area')
                repaired=output.convert('RGB').crop((0,0,w,h)).resize((W,H))
                break
            except Exception:
                continue
    if repaired is None:
        repaired=sanitized
        findings.append({'code':'CLEANUP_FAILED','severity':'warning',
                         'message':'Photo cleanup did not finish. A temporary fill needs review; retry this reference.'})
    # Feather inward only. There is zero model contribution outside the selected pixels.
    feather=ImageChops.darker(photo_mask,photo_mask.filter(ImageFilter.GaussianBlur(.7)))
    plate.paste(repaired,mask=feather)
    if calls>1:methods.add('opaque_fallback')
    return CleanupResult(plate,mask,sorted(methods),calls,findings)
