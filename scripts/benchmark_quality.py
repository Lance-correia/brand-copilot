"""Six reproducible removal cases; emits originals, cleaned PNGs, metrics and an HTML gallery.

Run .venv/bin/python scripts/benchmark_quality.py --real for two real masked repairs.
Without --real, photographic/texture cases are explicitly marked skipped (never mocked passes).
"""
import argparse
import html
import json
import random
import sys
import time
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw,ImageFont,ImageStat

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.decompose.cleanup import clean

def cases():
    W,H=640,480
    paper=Image.new('RGB',(W,H),'#F5F1E8')
    button=paper.copy();ImageDraw.Draw(button).rounded_rectangle((44,140,580,252),radius=24,fill='#24BEE7')
    tile=Image.new('RGB',(2,2));tile.putdata([(195,215,245),(215,230,255),(170,200,235),(185,215,245)])
    gradient=tile.resize((W,H),Image.Resampling.BILINEAR)
    dark=Image.new('RGB',(W,H),'#102A43')
    rng=random.Random(42)
    texture=Image.new('RGB',(W,H));texture.putdata([(120+(n:=rng.randint(-45,45)),155+n,180+n) for _ in range(W*H)])
    scene=texture.copy();draw=ImageDraw.Draw(scene)
    for x in range(0,W,35):draw.line((x,0,x+90,H),fill='#81959D',width=3)
    font=ImageFont.truetype(str(ROOT/'fixtures/brand/fonts/DMSans.ttf'),42)
    for name,background,color,text,point,model in [
        ('01-paper-card',paper,'#102A43','Suddenly you are',(54,160),False),
        ('02-blue-button',button,'#102A43','Try it for free',(72,170),False),
        ('03-gradient',gradient,'#102A43','Close with clarity',(54,160),False),
        ('04-dark-card',dark,'#FFFFFF','A brighter start',(54,160),False),
        ('05-textured-surface',texture,'#FFFFFF','Your next chapter',(54,160),True),
        ('06-patterned-surface',scene,'#FFFFFF','Make room for more',(54,160),True),
    ]:
        original=background.copy();draw=ImageDraw.Draw(original)
        box=draw.textbbox(point,text,font=font,anchor='lt')
        draw.text(point,text,font=font,fill=color,anchor='lt')
        yield name,original,background,[{'box':list(box),'kind':'text','colorHex':color}],model

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real',action='store_true')
    parser.add_argument('--out',type=Path,default=ROOT/'data/quality-benchmark')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    report=[]
    for name,original,expected,regions,needs_model in cases():
        original.save(args.out/f'{name}-original.png');expected.save(args.out/f'{name}-expected.png')
        row={'case':name,'status':'skipped','note':'Requires --real for a genuine image-model check.'}
        if args.real or not needs_model:
            start=time.perf_counter()
            def forbidden(*a,**k):raise AssertionError('Unexpected model request')
            result=clean(original,regions,edit=None if args.real else forbidden)
            result.image.save(args.out/f'{name}-clean.png');result.mask.save(args.out/f'{name}-mask.png')
            outside=ImageChops.multiply(ImageChops.difference(original,result.image).convert('RGB'),Image.merge('RGB',[ImageChops.invert(result.mask)]*3))
            preserved=outside.getbbox() is None
            error=ImageStat.Stat(ImageChops.difference(expected,result.image),result.mask).mean
            row={'case':name,'status':'pass' if preserved and not result.findings else 'review',
                 'seconds':round(time.perf_counter()-start,3),'modelCalls':result.model_calls,
                 'unmaskedPixelsPreserved':preserved,'maskedMeanAbsoluteError':round(sum(error)/3,3),
                 'methods':result.methods,'findings':result.findings,
                 'note':'Review interior texture visually; pixel preservation does not certify a natural reconstruction.' if needs_model else 'Known simple surface; inspect exact text removal and edges.'}
        report.append(row);print(json.dumps(row))
    (args.out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    cards=[]
    for row in report:
        name=row['case'];second='clean' if row['status']!='skipped' else 'expected'
        cards.append(f'<article><h2>{html.escape(name)} · {row["status"]}</h2><div><figure><img src="{name}-original.png"><figcaption>Original</figcaption></figure><figure><img src="{name}-{second}.png"><figcaption>{"Cleaned" if second=="clean" else "Expected target — not executed"}</figcaption></figure></div><p>{html.escape(row["note"])}</p><pre>{html.escape(json.dumps(row,indent=2))}</pre></article>')
    (args.out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Output quality review</title><style>body{font:16px system-ui;background:#f5f3ed;color:#24372d;max-width:1100px;margin:40px auto;padding:20px}article{background:white;border:1px solid #ddd;border-radius:12px;padding:20px;margin:24px 0}article>div{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0}img{width:100%}pre{overflow:auto;font-size:12px}figcaption{padding:8px}</style><h1>Text removal: six-case review</h1><p>Originals and clean backgrounds use the same dimensions. Dark or missing areas must not be mistaken for successful removal.</p>'+''.join(cards))
    print(f'Gallery: {args.out/"index.html"}')

if __name__=='__main__':main()
