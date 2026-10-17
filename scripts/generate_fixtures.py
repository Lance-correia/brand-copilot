#!/usr/bin/env python3
"""Rebuild the Lumen fixtures. Fonts are checked in with their OFL licenses."""
import json
from copy import deepcopy
from pathlib import Path
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / 'fixtures'

def write_json(path, data):
    path = F / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')

def coffee_image(path, seed, size=(1080, 1080)):
    image = Image.new('RGB', size, ['#E2C7AB', '#D7B99A', '#E4D9C9', '#CFC2AF'][seed % 4])
    d = ImageDraw.Draw(image)
    w, h = size
    d.polygon([(0, h*.7), (w, h*.4), (w, h), (0,h)], fill='#B28B6F')
    cx, cy = w * (.38 + .06 * (seed % 4)), h * .46
    radius = min(w, h) * .22
    d.ellipse((cx-radius,cy-radius*.7,cx+radius,cy+radius*.7),fill='#FBF7F2')
    d.ellipse((cx-radius*.75,cy-radius*.52,cx+radius*.75,cy+radius*.52),fill='#704331')
    d.ellipse((cx-radius*.57,cy-radius*.4,cx+radius*.57,cy+radius*.4),fill='#C69467')
    d.arc((cx+radius*.7,cy-radius*.3,cx+radius*1.4,cy+radius*.3),270,90,fill='#FBF7F2',width=22)
    for i in range(7):
        x, y = int(w*.1+i*47+seed*7)%w, int(h*.82+i*19)%h
        d.ellipse((x,y,x+22,y+13),fill='#56372C')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)

def main():
    assets = []
    for id_, variant, color in [('ast_01','dark','#1B1B1F'),('ast_02','light','#FBF7F2')]:
        path = F / f'brand/logo-{variant}.svg'
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="128" viewBox="0 0 512 128"><circle cx="52" cy="64" r="30" fill="{color}"/><path d="M52 20V6 M52 122v-14 M8 64H0 M104 64h16" stroke="{color}" stroke-width="5"/><text x="104" y="89" fill="{color}" font-family="Georgia,serif" font-size="76">Lumen</text></svg>\n')
        assets.append({'id':id_,'path':f'brand/logo-{variant}.svg','kind':'logo','source':'brand_asset'})
    for id_, filename, family, weight in [('ast_05','DMSerifDisplay-Regular.ttf','DM Serif Display',400), ('ast_06','DMSans.ttf','DM Sans',400)]:
        assets.append({'id':id_,'path':'brand/fonts/'+filename,'kind':'font','source':'brand_asset','meta':{'family':family,'weight':weight}})
    for i in range(8):
        filename = f'brand/images/coffee-{i+1:02}.png'
        coffee_image(F / filename, i)
        assets.append({'id':f'ast_brand_{i+1}','path':filename,'kind':'image','source':'brand_asset'})
    for i in range(2):
        filename = f'samples/sample-{i+1}.png'
        coffee_image(F / filename, 12+i)
        assets.append({'id':f'ast_sample_{i+1}','path':filename,'kind':'sample','source':'upload'})
    for i in range(4):
        filename = f'generated/hero-{i+1}.png'
        coffee_image(F / filename, 20+i)
        assets.append({'id':f'ast_{20+i}','path':filename,'kind':'image','source':'generated'})
    kit = {
      'workspaceId':'ws_lumen',
      'colors':[{'token':'primary','hex':'#C8553D','role':'accent'},{'token':'ink','hex':'#1B1B1F','role':'text'},{'token':'paper','hex':'#FBF7F2','role':'background'}],
      'fonts':[{'token':'headline','family':'DM Serif Display','weight':400,'assetId':'ast_05','minSize':32,'maxSize':120},{'token':'body','family':'DM Sans','weight':400,'assetId':'ast_06','minSize':16,'maxSize':40}],
      'logos':[{'assetId':'ast_01','variant':'dark','minWidth':120,'clearSpace':0.5},{'assetId':'ast_02','variant':'light','minWidth':120,'clearSpace':0.5}],
      'safeMarginPct':6,'imageryStyle':'Natural light, warm tones, real people, no posed stock look','voice':'Short, active sentences',
      'rules':[{'id':'COL-01','text':'Use only palette colors','check':'palette'},{'id':'FONT-01','text':'Use headline and body fonts','check':'font'},{'id':'SAFE-01','text':'Keep text inside a 6 percent safe margin','check':'safe_margin'},{'id':'LOGO-01','text':'Logo must be at least 120 pixels wide','check':'logo_min_size'},{'id':'CLEAR-01','text':'Leave half a logo height clear on each side','check':'logo_clear_space'}], 'confirmed':False}
    write_json('brand/brand-kit.json',kit)
    pdf = canvas.Canvas(str(F / 'brand/guidelines.pdf'), pagesize=(612,792))
    pdf.setTitle('Lumen Coffee - Brand Guidelines')
    def page(number, title):
        pdf.setFillColor(HexColor('#FBF7F2'));pdf.rect(0,0,612,792,fill=1,stroke=0)
        pdf.setFillColor(HexColor('#1B1B1F'));pdf.setFont('Helvetica-Bold',12);pdf.drawString(48,736,'LUMEN COFFEE / BRAND GUIDELINES')
        pdf.setFont('Helvetica-Bold',30);pdf.drawString(48,675,title)
        pdf.setFont('Helvetica',10);pdf.drawString(48,32,f'Lumen Coffee | Fixture brand | {number} / 2')
    page(1,'Warmth in the everyday.')
    pdf.setFont('Helvetica',13)
    for y,line in zip([630,608,586],['Coffee for slow mornings and good company.','Our identity is warm, clear and quietly confident.','Use short, active sentences. Make room to breathe.']):pdf.drawString(48,y,line)
    for i,c in enumerate(kit['colors']):
        x=48+i*174;pdf.setFillColor(HexColor(c['hex']));pdf.rect(x,408,150,112,fill=1,stroke=0)
        pdf.setFillColor(HexColor('#1B1B1F'));pdf.setFont('Helvetica-Bold',12);pdf.drawString(x,386,c['token']);pdf.setFont('Helvetica',11);pdf.drawString(x,368,c['hex'])
    pdf.setFont('Helvetica-Bold',18);pdf.drawString(48,306,'Typography')
    pdf.setFont('Helvetica',12)
    for y,line in zip([276,254,232,210],['Headline: DM Serif Display Regular (400), 32-120px.','Body: DM Sans Regular (400), 16-40px.','Both fonts are supplied under the SIL Open Font License.','Use palette tokens primary, ink and paper in designs.']):pdf.drawString(48,y,line)
    pdf.showPage();page(2,'Keep the identity clear.')
    blocks=[('Logo use',['Dark logo on light backgrounds; light logo on dark backgrounds.','Minimum width: 120px. Clear space: 0.5 times logo height.']),('Layout',['Keep text inside a 6 percent safe margin on all sides.','Layer order runs from background to foreground.']),('Imagery',['Natural light, warm tones, real people. Avoid posed stock imagery.','Generated imagery contains no text, letters, logos or watermarks.']),('Asset protection',['Approved logos and brand images are immutable brand assets.','Only generated images can be edited with AI.'])]
    y=614
    for title,lines in blocks:
        pdf.setFont('Helvetica-Bold',17);pdf.drawString(48,y,title);y-=28;pdf.setFont('Helvetica',11)
        for line in lines:pdf.drawString(48,y,line);y-=20
        y-=32
    pdf.save()
    assets.append({'id':'ast_guidelines','path':'brand/guidelines.pdf','kind':'guideline','source':'brand_asset'})
    write_json('assets.json',assets)
    common={'rotation':0,'visible':True,'locked':False}
    design={'id':'des_01','workspaceId':'ws_lumen','name':'Mornings, slowed down','width':1080,'height':1080,'background':{'colorToken':'paper'},'layers':[
      {'id':'lay_1','type':'image','role':'hero','x':0,'y':0,'w':1080,'h':630,**common,'source':'generated','assetId':'ast_20','fit':'cover'},
      {'id':'lay_2','type':'text','role':'headline','x':72,'y':680,'w':936,'h':160,**common,'text':'Mornings, slowed down','fontToken':'headline','fontSize':80,'colorToken':'ink','align':'left'},
      {'id':'lay_3','type':'shape','role':'cta_bg','x':72,'y':900,'w':320,'h':96,**common,'shape':'rect','fillToken':'primary','radius':48},
      {'id':'lay_5','type':'text','role':'cta','x':96,'y':924,'w':272,'h':48,**common,'text':'Find your morning','fontToken':'body','fontSize':24,'colorToken':'paper','align':'center'},
      {'id':'lay_4','type':'image','role':'logo','x':840,'y':936,'w':160,'h':40,**common,'source':'brand_asset','assetId':'ast_01','fit':'contain'}]}
    write_json('designs/01-morning.json',design)
    second=deepcopy(design);second['id']='des_02';second['name']='A cup of good company';second['layers'][0]['assetId']='ast_21';second['layers'][1]['text']='A cup of good company';write_json('designs/02-company.json',second)
    third=deepcopy(design);third['id']='des_03';third['name']='Seeded violations';third['layers'][0]['assetId']='ast_22';third['layers'][1].update({'x':12,'colorToken':'off_palette'});third['layers'][-1].update({'w':80,'h':20});write_json('designs/03-violations.json',third)
    spec={'aspect':'1:1','regions':[{'role':'hero','box':[0,0,1,0.6]},{'role':'headline','box':[0.06,0.63,0.94,0.78]}],'hierarchy':['hero','headline','cta','logo'],'mood':'bright, unhurried','imageryStyle':'lifestyle photo, morning light','observedColors':['#F2C14E','#1B1B1F']}
    write_json('samples/spec.json',spec)
    templates=[('hero-top','Hero top, text below',[[0,0,1,.6],[.06,.63,.94,.78],[.06,.83,.36,.92],[.78,.86,.94,.92]]),('split-left','Image left, text right',[[0,0,.48,1],[.54,.12,.94,.5],[.54,.65,.94,.76],[.72,.86,.94,.92]]),('full-bleed-overlay','Full bleed with overlay',[[0,0,1,1],[.06,.55,.94,.76],[.06,.83,.36,.92],[.78,.86,.94,.92]]),('centered-badge','Centered badge',[[0,0,1,1],[.2,.32,.8,.55],[.3,.62,.7,.72],[.4,.8,.6,.86]])]
    for id_,name,boxes in templates:
        write_json(f'templates/{id_}.json',{'id':id_,'name':name,'aspect':'1:1','width':1080,'height':1080,'slots':[{'role':role,'kind':kind,'box':box} for role,kind,box in zip(['hero','headline','cta','logo'],['image','text','text','image'],boxes)]})
    print('Generated Lumen Coffee: 2-page PDF, 2 SVG logos, 8 brand images, 2 samples, 4 generated images, 3 designs, 4 templates')

if __name__ == '__main__':main()
