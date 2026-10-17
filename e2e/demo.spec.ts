import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdir, copyFile, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { Asset, Design, Job, Thread } from '../apps/web/src/types';

// Start API + Vite with USE_STUBS=0, then npm run test:e2e. This calls real models.
test.use({ viewport: { width: 1600, height: 1100 }, trace: 'retain-on-failure' });
test('chat-first Studio with real models, versions and direct-edit isolation', async ({ page, request }, info) => {
  test.setTimeout(1_200_000);
  const base = process.env.DEMO_URL ?? 'http://127.0.0.1:5173';
  const timings: Record<string, number> = {};
  const browserErrors: string[] = [];
  const requests: string[] = [];
  page.on('pageerror', e => browserErrors.push(e.message));
  page.on('request', r => { if (r.method() === 'POST') requests.push(new URL(r.url()).pathname); });
  let ws = '', threadId = '';
  let originals: Design[] = [];
  const pack = info.outputPath('Ledgerly brand');
  const sample = info.outputPath('reference.png');
  for (const folder of ['Guidelines', 'Logos', 'Fonts', 'Product UI']) await mkdir(path.join(pack, folder), { recursive: true });
  await copyFile('fixtures/brand/fonts/DMSerifDisplay-Regular.ttf', path.join(pack, 'Fonts/display.ttf'));
  await copyFile('fixtures/brand/fonts/DMSans.ttf', path.join(pack, 'Fonts/body.ttf'));
  execFileSync(path.resolve('.venv/bin/python'), ['-c', `
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
import sys
root=Path(sys.argv[1]); sample=Path(sys.argv[2])
navy='#102A43'; mint='#3BBFAD'; paper='#F8FAFC'
c=canvas.Canvas(str(root/'Guidelines/brand.pdf'))
lines=['Ledgerly brand guidelines','Palette tokens: navy #102A43 (background and text), mint #3BBFAD (accent), paper #F8FAFC (background).',
'Headline font: DM Serif Display. Body font: DM Sans. Headline sizes 32 to 100 px, body 16 to 40 px.',
'Use only the palette and uploaded fonts. Dark logo on light backgrounds, light logo on navy.',
'Logo minimum width 120 px; clear space half the logo height. Safe margin 6 percent.',
'Voice: clear, direct, useful. For finance teams who want to close their books faster.',
'Imagery: calm modern offices, natural light, organized product interfaces.']
for i,line in enumerate(lines): c.drawString(40,780-i*30,line)
c.save()
for name,color in [('dark',navy),('light',paper)]:
 (root/f'Logos/logo-{name}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="128" viewBox="0 0 512 128"><circle cx="46" cy="64" r="28" fill="{color}"/><text x="90" y="85" font-family="sans-serif" font-size="70" fill="{color}">Ledgerly</text></svg>')
font=lambda s:ImageFont.truetype('fixtures/brand/fonts/DMSans.ttf',s)
for j in range(2):
 im=Image.new('RGB',(960,640),paper); d=ImageDraw.Draw(im)
 d.rectangle((0,0,180,640),fill=navy); d.text((24,30),'Ledgerly',font=font(26),fill=paper)
 d.text((220,36),'Close overview' if j==0 else 'Revenue dashboard',font=font(34),fill=navy)
 for k,label in enumerate(['Cash balance','Reconciled','Month-end close']):
  x=220+k*235; d.rounded_rectangle((x,110,x+210,220),radius=12,fill='#E3EDF3'); d.text((x+14,125),label,font=font(18),fill=navy); d.text((x+14,165),'$248,960' if k==0 else '98%',font=font(28),fill=navy)
 for k in range(7):
  x=240+k*85; h=100+(k*47+j*39)%200; d.rectangle((x,550-h,x+48,550),fill=mint)
 im.save(root/f'Product UI/product-dashboard-{j+1}.png')
im=Image.new('RGB',(1080,1080),'#EEE7DC'); d=ImageDraw.Draw(im)
d.text((70,75),'Close with clarity.',font=font(76),fill=navy)
d.text((70,180),'Know where your business stands.',font=font(36),fill=navy)
ui=Image.open(root/'Product UI/product-dashboard-1.png'); ui.thumbnail((940,560)); im.paste(ui,(70,310))
d.rounded_rectangle((70,900,420,992),radius=35,fill=navy); d.text((105,925),'Meet Ledgerly',font=font(37),fill=paper)
d.text((735,934),'Ledgerly',font=font(48),fill=navy); im.save(sample)
`, pack, sample]);
  async function step<T>(name: string, fn: () => Promise<T>): Promise<T> {
    const started = Date.now();
    try { return await test.step(name, fn); }
    finally { timings[name] = (Date.now() - started) / 1000; console.log(`${name}: ${timings[name]}s`); }
  }
  const assets = async (): Promise<Asset[]> => (await request.get(`${base}/api/workspaces/${ws}/assets`)).json();
  const card = (letter: string, version: number) => page.locator(`.studio-card[data-label="Option ${letter}"][data-version="${version}"]`).last();
  async function send(text: string, stream = false): Promise<Job> {
    await page.getByRole('textbox', { name: 'Message Studio' }).fill(text);
    const started = page.waitForResponse(r => /\/threads\/[^/]+\/messages$/.test(r.url()) && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Send message' }).click();
    const response = await started;
    expect(response.status(), await response.text()).toBe(202);
    const { jobId } = await response.json();
    threadId = new URL(page.url()).searchParams.get('thread')!;
    if (stream) {
      await expect(page.getByRole('region', { name: 'Studio is working' })).toBeVisible();
      await expect.poll(() => page.locator('.studio-live-steps li').count(), { timeout: 30_000 }).toBeGreaterThan(0);
    }
    let job: Job;
    await expect.poll(async () => {
      job = await (await request.get(`${base}/api/jobs/${jobId}`)).json();
      return job.status === 'done' || job.status === 'error';
    }, { timeout: 420_000, intervals: [700] }).toBe(true);
    expect(job!.status, JSON.stringify(job!)).toBe('done');
    expect(job!.reply!.length).toBeLessThanOrEqual(500);
    await expect(page.locator('.studio-pending')).toHaveCount(0, { timeout: 30_000 });
    return job!;
  }
  try {
    await step('Brand folder, extract, confirm, land in Studio', async () => {
      await page.goto(base);
      await page.getByRole('textbox', { name: 'Brand name' }).fill(`Ledgerly ${Date.now()}`);
      await page.getByRole('button', { name: 'New brand' }).click();
      await page.waitForURL('**/w/*/brand'); ws = new URL(page.url()).pathname.split('/')[2];
      await page.getByTestId('folder-input').setInputFiles(pack);
      await page.getByRole('button', { name: 'Upload 7 files' }).click();
      await expect(page.getByText('Uploaded 7 of 7')).toBeVisible({ timeout: 120_000 });
      await page.getByRole('button', { name: 'Extract brand kit', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Confirm brand kit' })).toBeVisible({ timeout: 180_000 });
      const kit = await (await request.get(`${base}/api/workspaces/${ws}/brand-kit`)).json();
      expect(kit.colors.some((c: { token: string }) => c.token === 'navy')).toBe(true);
      await page.getByRole('button', { name: 'Confirm brand kit' }).click();
      await page.waitForURL('**/studio');
      await expect(page.getByRole('textbox', { name: 'Message Studio' })).toBeEnabled();
      await expect(page.getByRole('dialog')).toHaveCount(0);
    });
    await step('Attach without text, live steps, four editable options', async () => {
      await page.getByTestId('studio-image-input').setInputFiles(sample);
      await expect(page.locator('.studio-compose-attachments img')).toHaveCount(1, { timeout: 180_000 });
      const job = await send('', true);
      originals = job.designs;
      expect(originals.map(d => d.label)).toEqual(['Option A', 'Option B', 'Option C', 'Option D']);
      expect(job.steps!.length).toBeGreaterThan(2);
      for (const [i, d] of originals.entries()) {
        await expect(card(String.fromCharCode(65 + i), 1)).toBeVisible();
        expect(d.layers.some(l => l.type === 'text' && l.role === 'headline')).toBe(true);
        expect(d.layers.some(l => l.type === 'image' && l.role === 'logo' && l.source === 'brand_asset')).toBe(true);
      }
      expect(originals[0].layers.some(l => l.type === 'image' && l.source === 'generated')).toBe(true);
      const before = requests.length;
      await page.getByRole('button', { name: 'Original', exact: true }).click();
      await expect(page.getByAltText('Original reference')).toBeVisible();
      await page.screenshot({ path: info.outputPath('original.png') });
      await page.getByRole('button', { name: 'Clean background', exact: true }).click();
      await expect(page.getByAltText('Clean reference background without editable text')).toBeVisible();
      await page.screenshot({ path: info.outputPath('clean-background.png') });
      const background = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Download background', exact: true }).click();
      await (await background).saveAs(info.outputPath('clean-background-export.png'));
      await page.getByRole('button', { name: 'Final design', exact: true }).click();
      await expect(page.locator('.studio-preview canvas.upper-canvas')).toBeVisible();
      expect(requests.slice(before).filter(url => /\/(messages|chat|images|variants|decompose|agent)(\/|$)/.test(url))).toEqual([]);
    });
    await step('B v2: headline and navy background, no image call', async () => {
      const before = (await assets()).filter(a => a.source === 'generated').map(a => a.id);
      const job = await send("Make B's headline 'Close your books faster' and use the navy background");
      expect(job.designs).toHaveLength(1);
      const b = job.designs[0];
      expect(b.label).toBe('Option B'); expect(b.version).toBe(2); expect(b.parentId).toBe(originals[1].id);
      expect(b.background.colorToken).toBe('navy');
      expect(b.layers.some(l => l.type === 'text' && l.role === 'headline' && l.text === 'Close your books faster')).toBe(true);
      expect(job.steps!.join(' ')).not.toMatch(/edit generated image|Planning four options/);
      expect((await assets()).filter(a => a.source === 'generated').map(a => a.id)).toEqual(before);
      await expect(card('B', 2)).toBeVisible();
      // The v1 snapshot survives, and the version chip can show it again.
      const parent: Design = await (await request.get(`${base}/api/designs/${b.parentId}`)).json();
      expect(parent).toEqual(originals[1]);
      await card('B', 2).getByRole('combobox').selectOption(parent.id);
      await expect(page.locator(`.studio-card[data-design-id="${parent.id}"]`).last()).toBeVisible();
    });
    await step('C v2: replace photo with tagged product UI asset', async () => {
      const before = (await assets()).filter(a => a.source === 'generated').map(a => a.id);
      const job = await send('Swap the photo in C for one of our product UI shots');
      expect(job.designs).toHaveLength(1);
      const c = job.designs[0]; expect(c.label).toBe('Option C'); expect(c.version).toBe(2); expect(c.parentId).toBe(originals[2].id);
      const library = await assets();
      const changed = c.layers.filter(l => l.type === 'image' && l.role !== 'logo' && library.some(a => a.id === l.assetId && a.tags.includes('product-ui')));
      expect(changed.length).toBeGreaterThan(0);
      expect(changed.every(l => l.type === 'image' && l.source === 'brand_asset')).toBe(true);
      expect(changed.some(l => l.type === 'image' && originals[2].layers.some(old => old.type === 'image' && old.id === l.id && old.assetId !== l.assetId))).toBe(true);
      expect((await assets()).filter(a => a.source === 'generated').map(a => a.id)).toEqual(before);
      await expect(card('C', 2)).toBeVisible();
    });
    await step('A v2: edit generated background, preserve brand pixels', async () => {
      const before = await assets();
      const job = await send('Change the background image in A to an office at sunrise');
      expect(job.designs).toHaveLength(1);
      const a = job.designs[0]; expect(a.label).toBe('Option A'); expect(a.version).toBe(2); expect(a.parentId).toBe(originals[0].id);
      const fresh = (await assets()).filter(asset => !before.some(old => old.id === asset.id));
      const edited = fresh.find(asset => asset.source === 'generated' && asset.meta.parentAssetId);
      expect(edited).toBeTruthy();
      expect(before.find(asset => asset.id === edited!.meta.parentAssetId)?.source).toBe('generated');
      expect(a.layers.some(l => l.type === 'image' && l.assetId === edited!.id)).toBe(true);
      expect(a.layers.filter(l => l.type === 'image' && l.role === 'logo')).toEqual(originals[0].layers.filter(l => l.type === 'image' && l.role === 'logo'));
      await expect(card('A', 2)).toBeVisible();
      const brand = before.find(asset => asset.source === 'brand_asset' && asset.kind === 'image')!;
      expect((await request.post(`${base}/api/workspaces/${ws}/images/edit`, { data: { assetId: brand.id, instruction: 'blue' } })).status()).toBe(403);
    });
    await step('Focus D, double-click correction, zero model routes', async () => {
      while (await page.locator('.studio-focus-chips button').count()) await page.locator('.studio-focus-chips button').first().click();
      await card('D', 1).getByRole('button', { name: 'Focus', exact: true }).click();
      await expect(page.locator('.studio-preview h2')).toHaveText('Option D');
      const d = originals[3];
      const headline = d.layers.find(l => l.type === 'text' && l.role === 'headline')!;
      const canvas = page.locator('.studio-preview canvas.upper-canvas');
      await expect(canvas).toBeVisible(); const box = (await canvas.boundingBox())!;
      const x = box.x + (headline.x + headline.w * .35) * box.width / d.width;
      const y = box.y + (headline.y + headline.h * .35) * box.height / d.height;
      const callIndex = requests.length;
      await page.mouse.dblclick(x, y);
      await expect(page.locator('textarea[data-fabric]')).toBeFocused();
      await page.keyboard.press('ControlOrMeta+A'); await page.keyboard.insertText('Preview correction survives');
      const saved = page.waitForResponse(r => r.url().endsWith(`/designs/${d.id}`) && r.request().method() === 'PUT');
      await page.getByRole('textbox', { name: 'Message Studio' }).click();
      expect((await saved).ok()).toBe(true);
      await expect(page.locator('.studio-save')).toHaveText('Saved');
      expect(requests.slice(callIndex).filter(url => /\/(messages|chat|images|variants|decompose|agent)(\/|$)/.test(url))).toEqual([]);
      const current: Design = await (await request.get(`${base}/api/designs/${d.id}`)).json();
      expect(current.version).toBe(1);
      expect(current.layers.some(l => l.type === 'text' && l.text === 'Preview correction survives')).toBe(true);
    });
    await step('Next chat sees the direct correction', async () => {
      const job = await send('What is the exact headline of the focused option? Reply with that text. Do not change any designs.');
      expect(job.reply).toContain('Preview correction survives');
      expect(job.designs).toHaveLength(0);
    });
    await step('Persistence, library drawer, PNG and legacy redirect', async () => {
      const before: Thread = await (await request.get(`${base}/api/threads/${threadId}`)).json();
      await page.reload();
      await expect(page.locator('[data-message-id]')).toHaveCount(before.messages.length);
      await expect(page.locator('.studio-message.assistant').last()).toContainText('Preview correction survives');
      await expect(page.locator('.studio-card')).toHaveCount(7);
      await page.getByRole('button', { name: '▦ Brand library' }).click();
      await page.getByRole('textbox', { name: 'Search brand library' }).fill('product-ui');
      await expect(page.locator('.studio-library-assets figure')).toHaveCount(2);
      await page.getByRole('button', { name: 'Close brand library' }).click();
      const download = page.waitForEvent('download');
      await card('A', 2).getByRole('button', { name: 'Download PNG', exact: true }).click();
      const output = info.outputPath('studio-export.png'); await (await download).saveAs(output);
      expect((await readFile(output)).subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
      await page.goto(`${base}/w/${ws}/use?thread=${threadId}`);
      await page.waitForURL(`**/studio?thread=${threadId}`);
      await expect(page.locator('[data-message-id]')).toHaveCount(before.messages.length);
      expect(browserErrors).toEqual([]);
    });
  } finally {
    await writeFile(info.outputPath('timings.json'), JSON.stringify(timings, null, 2));
    await info.attach('step-timings', { body: JSON.stringify(timings, null, 2), contentType: 'application/json' });
    await page.screenshot({ path: info.outputPath('studio.png'), fullPage: true });
  }
});
