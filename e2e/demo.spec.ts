import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdir, copyFile, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { Design, Asset } from '../apps/web/src/types';

// Start both apps with USE_STUBS=0, then: npx playwright test e2e/demo.spec.ts --workers=1
// This calls real providers. No mocked responses or injected canvas state.
test.use({ viewport: { width: 1600, height: 1100 }, trace: 'retain-on-failure' });
test('real-model demo and direct-edit isolation', async ({ page, request }, info) => {
  test.setTimeout(900_000);
  page.setDefaultTimeout(30_000);
  const base = process.env.DEMO_URL ?? 'http://127.0.0.1:5173';
  const timings: Record<string, number> = {};
  const browserErrors: string[] = [];
  page.on('pageerror', e => browserErrors.push(e.message));
  async function step<T>(name: string, fn: () => Promise<T>): Promise<T> {
    const start = Date.now();
    try { return await test.step(name, fn); }
    finally { timings[name] = (Date.now() - start) / 1000; console.log(`${name}: ${timings[name]}s`); }
  }
  let ws = '', design: Design, textId = '';
  const pack = info.outputPath('Lumen pack');
  for (const folder of ['Guidelines', 'Logos', 'Fonts', 'Images']) await mkdir(path.join(pack, folder), { recursive: true });
  for (const [src, dst] of [
    ['guidelines.pdf', 'Guidelines/guidelines.pdf'], ['logo-dark.svg', 'Logos/logo-dark.svg'],
    ['logo-light.svg', 'Logos/logo-light.svg'], ['fonts/DMSerifDisplay-Regular.ttf', 'Fonts/DMSerifDisplay-Regular.ttf'],
    ['fonts/DMSans.ttf', 'Fonts/DMSans.ttf'], ['images/coffee-01.png', 'Images/coffee-01.png'],
  ]) await copyFile(path.resolve('fixtures/brand', src), path.join(pack, dst));
  const samplePath = info.outputPath('sample.png');
  execFileSync(path.resolve('.venv/bin/python'), ['-c', `
import sys
from PIL import Image, ImageDraw, ImageFont
im=Image.open('fixtures/samples/sample-1.png').convert('RGB'); d=ImageDraw.Draw(im)
serif=lambda s:ImageFont.truetype('fixtures/brand/fonts/DMSerifDisplay-Regular.ttf',s)
sans=ImageFont.truetype('fixtures/brand/fonts/DMSans.ttf',34)
d.text((72,70),'Fresh roast,',font=serif(92),fill='#1B1B1F')
d.text((72,170),'slow mornings',font=serif(92),fill='#1B1B1F')
d.text((72,285),'Small-batch beans, roasted every Monday.',font=sans,fill='#1B1B1F')
d.rounded_rectangle((72,900,392,990),radius=45,fill='#C8553D')
d.text((232,945),'Order now',font=sans,fill='#FBF7F2',anchor='mm')
d.ellipse((760,920,812,972),fill='#FBF7F2')
d.text((826,946),'Lumen',font=serif(64),fill='#FBF7F2',anchor='lm')
im.save(sys.argv[1])`, samplePath]);
  try {
    await step('Welcome and new brand', async () => {
      await page.goto(base);
      await expect(page.getByRole('heading', { name: 'Welcome to Brand Copilot' })).toBeVisible();
      await page.getByRole('textbox', { name: 'Brand name' }).fill(`Lumen Coffee Demo ${Date.now()}`);
      await page.getByRole('button', { name: 'New brand' }).click();
      await page.waitForURL('**/w/*/brand'); ws = new URL(page.url()).pathname.split('/')[2];
    });
    await step('Folder upload and tags', async () => {
      await page.getByTestId('folder-input').setInputFiles(pack);
      await page.getByRole('button', { name: 'Upload 6 files' }).click();
      await expect(page.getByText('Uploaded 6 of 6')).toBeVisible({ timeout: 120_000 });
      const assets: Asset[] = await (await request.get(`${base}/api/workspaces/${ws}/assets`)).json();
      for (const [kind, tag] of [['logo', 'logos'], ['font', 'fonts'], ['image', 'images'], ['guideline', 'guidelines']]) {
        const matching = assets.filter(a => a.kind === kind);
        expect(matching.length).toBeGreaterThan(0);
        expect(matching.every(a => a.tags.includes(tag))).toBe(true);
      }
    });
    await step('Extract, confirm, Use', async () => {
      await page.getByRole('button', { name: 'Extract brand kit', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Confirm brand kit' })).toBeVisible({ timeout: 180_000 });
      await page.getByRole('button', { name: 'Confirm brand kit' }).click();
      await expect(page.getByRole('dialog', { name: 'Start a design' })).toBeVisible();
      await expect(page.getByRole('dialog')).toHaveCount(1);
    });
    await step('Upload sample and split into layers', async () => {
      await page.getByRole('dialog').locator('input[type=file]').setInputFiles(samplePath);
      await expect(page.getByRole('button', { name: 'Split into layers' })).toBeVisible({ timeout: 180_000 });
      const completed = new Promise<Design>((resolve, reject) => {
        const listener = async (r: import('@playwright/test').Response) => {
          if (!/\/api\/jobs\//.test(r.url()) || !r.ok()) return;
          const job = await r.json();
          if (job.status === 'error') { page.off('response', listener); reject(new Error(job.error)); }
          if (job.status === 'done') { page.off('response', listener); resolve(job.designs[0]); }
        };
        page.on('response', listener);
      });
      await page.getByRole('button', { name: 'Split into layers' }).click();
      design = await completed;
      await expect(page.locator('canvas.upper-canvas')).toBeVisible();
      expect(design.layers.some(l => l.type === 'text')).toBe(true);
      expect(design.layers.some(l => l.role === 'logo')).toBe(true);
      await expect(page.getByRole('heading', { name: /^Copilot$/ })).toHaveCount(1);
      await expect(page.getByRole('heading', { name: /^Brand check/ })).toHaveCount(1);
    });
    await step('Direct text, style, move, and library swap make no AI requests', async () => {
      const aiCalls: string[] = [];
      const watch = (r: import('@playwright/test').Request) => {
        if (/\/api\/workspaces\/[^/]+\/(chat|images|variants|decompose|agent)(\/|$)/.test(new URL(r.url()).pathname)) aiCalls.push(r.url());
      };
      page.on('request', watch);
      const text = design.layers.find(l => l.type === 'text' && l.role === 'headline')!;
      textId = text.id;
      const canvas = page.locator('canvas.upper-canvas');
      const box = (await canvas.boundingBox())!;
      const x = box.x + (text.x + text.w * 0.35) * box.width / design.width;
      const y = box.y + (text.y + text.h * 0.35) * box.height / design.height;
      await page.mouse.dblclick(x, y);
      await expect(page.locator('textarea[data-fabric]')).toBeFocused();
      await page.keyboard.press('ControlOrMeta+A'); await page.keyboard.insertText('Fresh mornings');
      await page.getByRole('button', { name: 'Fit', exact: true }).click();
      await page.locator(`[data-layer-id="${textId}"]`).click();
      await expect(page.getByRole('textbox', { name: 'Text', exact: true })).toHaveValue('Fresh mornings');
      await page.getByRole('button', { name: 'center', exact: true }).click();
      await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + 12, y + 8, { steps: 6 }); await page.mouse.up();
      await page.locator('.use-layers li').filter({ hasText: 'logo' }).first().click();
      await expect(page.getByLabel('Edit with AI', { exact: true })).toHaveCount(0);
      await page.locator('.use-right .use-thumbs img:not(.active)').first().click();
      await page.getByRole('button', { name: 'Save', exact: true }).click();
      await expect(page.locator('.use-toolbar')).toContainText('Saved');
      const saved: Design = await (await request.get(`${base}/api/designs/${design.id}`)).json();
      const edited = saved.layers.find(l => l.id === text.id)!;
      expect(edited.type === 'text' && edited.text).toBe('Fresh mornings');
      expect(edited.type === 'text' && edited.align).toBe('center');
      expect(edited.x !== text.x || edited.y !== text.y).toBe(true);
      const assets: Asset[] = await (await request.get(`${base}/api/workspaces/${ws}/assets?kind=logo`)).json();
      const beforeLogo = design.layers.find(l => l.type === 'image' && l.role === 'logo')!;
      const afterLogo = saved.layers.find(l => l.id === beforeLogo.id)!;
      expect(afterLogo.type === 'image' && afterLogo.assetId).not.toBe(beforeLogo.type === 'image' && beforeLogo.assetId);
      expect(aiCalls).toEqual([]);
      page.off('request', watch);
      const forbidden = await request.post(`${base}/api/workspaces/${ws}/images/edit`, { data: { assetId: assets[0].id, instruction: 'Make it blue' } });
      expect(forbidden.status()).toBe(403);
    });
    await step('Edit generated background with AI', async () => {
      await page.locator('.use-layers li').filter({ hasText: 'background' }).first().click();
      await page.getByLabel('Edit with AI', { exact: true }).fill('Make the light slightly warmer. Preserve the scene.');
      const response = page.waitForResponse(r => r.url().endsWith('/images/edit'), { timeout: 240_000 });
      await page.getByRole('button', { name: 'Apply', exact: true }).click();
      const r = await response; expect(r.ok(), await r.text()).toBe(true);
      await expect(page.getByLabel('Edit with AI', { exact: true })).toHaveValue('');
    });
    await step('Chat edit and accept', async () => {
      await page.locator(`[data-layer-id="${textId}"]`).click();
      await page.getByRole('textbox', { name: 'Message the copilot' }).fill('Set the selected headline text to "Slow mornings". Change nothing else.');
      const response = page.waitForResponse(r => r.url().endsWith('/chat'), { timeout: 180_000 });
      await page.getByRole('button', { name: 'AI', exact: true }).click();
      const r = await response; expect(r.ok(), await r.text()).toBe(true);
      const result = await r.json();
      const textOp = result.ops.find((op: { op: string; layerId?: string; props?: { text?: string } }) => op.op === 'update_layer' && op.layerId === textId && op.props?.text);
      expect(textOp?.props.text).toMatch(/^Slow mornings\.?$/);
      await page.locator('.copilot').getByRole('button', { name: 'Accept', exact: true }).click();
      await expect(page.getByRole('textbox', { name: 'Text', exact: true })).toHaveValue(textOp.props.text);
    });
    await step('Generate 4 variants and open one', async () => {
      await page.getByRole('button', { name: 'New or open design…' }).click();
      await expect(page.getByRole('button', { name: 'Generate 4 variants' })).toBeVisible();
      await page.getByRole('button', { name: 'Generate 4 variants' }).click();
      await expect(page.getByRole('dialog', { name: 'Variants' })).toBeVisible();
      await expect(page.getByRole('dialog').locator('button.tile')).toHaveCount(4, { timeout: 300_000 });
      await expect(page.getByRole('dialog')).toContainText('Done', { timeout: 300_000 });
      await page.getByRole('dialog').locator('button.tile').first().click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
    });
    await step('Export PNG', async () => {
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: 'PNG', exact: true }).click();
      const output = info.outputPath('demo-export.png'); await (await download).saveAs(output);
      expect((await readFile(output)).subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
      expect(browserErrors).toEqual([]);
    });
  } finally {
    await writeFile(info.outputPath('timings.json'), JSON.stringify(timings, null, 2));
    await info.attach('step-timings', { body: JSON.stringify(timings, null, 2), contentType: 'application/json' });
    await page.screenshot({ path: info.outputPath('demo.png'), fullPage: true });
  }
});
