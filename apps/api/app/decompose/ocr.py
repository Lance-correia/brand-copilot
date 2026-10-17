"""Optional local OCR for accurate text geometry. Flash remains the portable fallback."""
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Lock
from app.core.config import DATA_DIR
from app.generate import common as c

log = logging.getLogger(__name__)
LOCK = Lock()

def _read_text(path):
    if sys.platform != 'darwin' or not shutil.which('xcrun'):
        return None
    source = Path(__file__).with_suffix('.swift')
    folder = DATA_DIR / 'tools'
    binary = folder / 'studio-ocr'
    try:
        with LOCK:
            if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
                folder.mkdir(parents=True,exist_ok=True)
                subprocess.run(['xcrun','swiftc','-module-cache-path',str(folder/'ModuleCache'),'-O',str(source),'-o',str(binary)],
                               check=True,capture_output=True,timeout=90)
        result = subprocess.run([str(binary),str(path)],check=True,capture_output=True,text=True,timeout=20)
        return json.loads(result.stdout)
    except (OSError,subprocess.SubprocessError,ValueError):
        log.warning('Local OCR unavailable; using vision model geometry')
        return None

def read_text(path):
    return _read_text(path) or []

def read_text_checked(path):
    """Distinguish an empty, successful scan from an unavailable OCR service."""
    lines=_read_text(path)
    return lines or [],lines is not None

def refine_elements(elements, lines, image, kit, ws_name):
    if not lines: return elements
    norm = lambda text: re.sub(r'[^a-z0-9]','',text.lower())
    brand = norm(ws_name.split()[0]) if ws_name else ''
    used, refined = set(), []
    for e in elements:
        if e['type']=='logo' and not e['text'].strip() and brand:
            candidates=[line for line in lines if norm(line['text'])==brand and line['confidence']>=.65]
            if candidates:
                b=e['box'];cx,cy=(b[0]+b[2])/2,(b[1]+b[3])/2
                line=min(candidates,key=lambda line:abs((line['box'][0]+line['box'][2])/2-cx)+abs((line['box'][1]+line['box'][3])/2-cy))
                e={**e,'text':line['text'],'box':line['box'],'localOcr':True}
        word = norm(e['text'])
        if e['type'] not in ('text','logo') or not word:
            refined.append(e); continue
        matches=[]
        for i,line in enumerate(lines):
            read = norm(line['text'])
            if i in used or line['confidence'] < .5 or not read: continue
            exact = read==word
            part = len(read)>=6 and read in word and len(read)>=len(word)*.25
            if exact or part: matches.append((i,line))
        if not matches:
            refined.append(e); continue
        for i,line in matches:
            used.add(i)
            refined.append({**e,'text':line['text'],'box':line['box'],'localOcr':True})
    # The semantic model can omit an entire headline. Recover prominent, level text, but not
    # small/rotated labels photographed on a phone or UI screen.
    for i,line in enumerate(lines):
        word = norm(line['text'])
        if i in used or len(word)<8 or word==brand or line['confidence']<.8 or abs(line.get('angle',0))>7: continue
        b=line['box']
        if b[3]-b[1] < .04: continue
        if any(e['type']=='photo' and (e['box'][2]-e['box'][0])*(e['box'][3]-e['box'][1])<.7
               and e['box'][0]<(b[0]+b[2])/2<e['box'][2] and e['box'][1]<(b[1]+b[3])/2<e['box'][3] for e in elements): continue
        crop=image.crop((b[0]*image.width,b[1]*image.height,b[2]*image.width,b[3]*image.height))
        from PIL import ImageStat
        light = sum(ImageStat.Stat(crop).mean)/3 > 128
        color=min(kit.colors,key=lambda col:sum(c.rgb(col.hex))) if light else max(kit.colors,key=lambda col:sum(c.rgb(col.hex)))
        refined.append({'type':'text','text':line['text'],'box':b,'colorHex':color.hex,'role':'headline',
                        'fontStyle':{'serif':False,'weight':700,'italic':False},'align':'left','localOcr':True})
    return refined
