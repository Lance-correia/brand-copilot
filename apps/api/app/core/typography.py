"""Font-file measurements shared by generation, reconstruction and lint."""
import math
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont
from . import storage
from .config import DATA_DIR

LINE_HEIGHT=1.2

def font_path(asset_id):
    try:
        path=storage.asset_path(asset_id)
        if not path.is_file():return None
        if path.suffix.lower() in ('.woff','.woff2'):
            from fontTools.ttLib import TTFont
            target=DATA_DIR/'tools'/'fonts'/f'{asset_id}.ttf'
            if not target.exists():
                target.parent.mkdir(parents=True,exist_ok=True)
                font=TTFont(path);font.flavor=None;font.save(target)
            path=target
        return str(path)
    except (KeyError,OSError,ValueError):return None

@lru_cache(maxsize=1024)
def measured_font(path,size,weight=400):
    font=ImageFont.truetype(path,max(1,round(size)))
    try:
        axes=font.get_variation_axes()
        font.set_variation_by_axes([min(a['maximum'],max(a['minimum'],weight)) if b'weight' in a['name'].lower()
                                    else a['default'] for a in axes])
    except (OSError,AttributeError):pass
    return font

def wrap(text,font,width):
    lines=[]
    for paragraph in text.split('\n'):
        line=''
        for word in paragraph.split(' '):
            candidate=f'{line} {word}' if line else word
            if line and font.getlength(candidate)>width:
                lines.append(line);line=word
            else:line=candidate
        lines.append(line)
    return lines

def metrics(text,path,size,width,line_height=LINE_HEIGHT,weight=400):
    font=measured_font(path,size,weight)
    lines=wrap(text,font,width)
    return max((font.getlength(line) for line in lines),default=0),len(lines)*size*line_height

def fit_size(text,w,h,font,line_height=LINE_HEIGHT,max_size=None):
    upper=math.floor(min(font.maxSize,max_size if max_size is not None else font.maxSize))
    lower=min(upper,math.ceil(font.minSize))
    path=font_path(font.assetId)
    if path:
        for size in range(upper,lower-1,-1):
            width,height=metrics(text,path,size,w,line_height,font.weight)
            if width<=w and height<=h:return size
        return lower
    # Explicit fallback for unreadable fonts; quality reporting surfaces the missing measurement.
    return max(lower,min(upper,math.floor(min(w/max(1,len(text))/.6,h/line_height))))
