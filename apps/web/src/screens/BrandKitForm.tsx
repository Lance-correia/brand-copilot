import { useEffect, type ChangeEvent, type ReactNode } from 'react';
import { loadBrandFonts } from '../lib/fonts';
import type { Asset, BrandKit, BrandRule } from '../types';

type ListKey = 'colors' | 'fonts' | 'logos' | 'rules';
type Item<K extends ListKey> = BrandKit[K][number];
const CHECKS: BrandRule['check'][] = ['palette', 'font', 'contrast', 'safe_margin', 'logo_min_size', 'logo_clear_space', 'text_overflow', 'manual'];
const HEX = /^#[0-9A-Fa-f]{6}$/;
const num = (e: ChangeEvent<HTMLInputElement>) => (Number.isNaN(e.target.valueAsNumber) ? 0 : e.target.valueAsNumber);

export default function BrandKitForm({ kit, onChange, assets }: { kit: BrandKit; onChange: (kit: BrandKit) => void; assets: Asset[] }) {
  const fontAssets = assets.filter(a => a.kind === 'font');
  const logoAssets = assets.filter(a => a.kind === 'logo');
  const byId = new Map(assets.map(a => [a.id, a]));

  const set = (patch: Partial<BrandKit>) => onChange({ ...kit, ...patch });
  const patch = <K extends ListKey>(key: K, i: number, value: Partial<Item<K>>) =>
    set({ [key]: kit[key].map((item, j) => (j === i ? { ...item, ...value } : item)) });
  const remove = (key: ListKey, i: number) => set({ [key]: kit[key].filter((_, j) => j !== i) });
  const add = <K extends ListKey>(key: K, item: Item<K>) => set({ [key]: [...kit[key], item] });

  // Live preview: loadBrandFonts registers each font under its token as the CSS family name.
  const fontKey = JSON.stringify(kit.fonts);
  useEffect(() => { loadBrandFonts(kit).catch(() => {}); }, [fontKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="kit-form">
    <fieldset>
      <legend>Colors</legend>
      <datalist id="color-roles"><option value="accent" /><option value="text" /><option value="background" /></datalist>
      {kit.colors.map((c, i) => <div className="kit-row" key={i}>
        <input type="color" aria-label="Swatch" value={HEX.test(c.hex) ? c.hex.toLowerCase() : '#000000'}
          onChange={e => patch('colors', i, { hex: e.target.value.toUpperCase() })} />
        <Field label="Token"><input value={c.token} onChange={e => patch('colors', i, { token: e.target.value })} /></Field>
        <Field label="Hex"><input value={c.hex} aria-invalid={!HEX.test(c.hex)} onChange={e => patch('colors', i, { hex: e.target.value })} /></Field>
        <Field label="Role"><input list="color-roles" value={c.role} onChange={e => patch('colors', i, { role: e.target.value })} /></Field>
        <button className="icon-btn" aria-label={`Remove color ${c.token}`} onClick={() => remove('colors', i)}>×</button>
      </div>)}
      <button onClick={() => add('colors', { token: `color_${kit.colors.length + 1}`, hex: '#000000', role: 'accent' })}>Add color</button>
    </fieldset>

    <fieldset>
      <legend>Fonts</legend>
      {kit.rules.some(r => r.id === "FONT-FALLBACK") && <p role="status">DM Sans is a temporary fallback because this pack has no font files. You can replace it with your brand font.</p>}
      {kit.fonts.map((f, i) => <div className="kit-row wrap" key={i}>
        <Field label="Token"><input value={f.token} onChange={e => patch('fonts', i, { token: e.target.value })} /></Field>
        <Field label="Family"><input value={f.family} onChange={e => patch('fonts', i, { family: e.target.value })} /></Field>
        <Field label="Weight"><input type="number" min={100} max={900} step={100} value={f.weight} onChange={e => patch('fonts', i, { weight: num(e) })} /></Field>
        <Field label="Min size"><input type="number" min={1} value={f.minSize} onChange={e => patch('fonts', i, { minSize: num(e) })} /></Field>
        <Field label="Max size"><input type="number" min={1} value={f.maxSize} onChange={e => patch('fonts', i, { maxSize: num(e) })} /></Field>
        <Field label="File"><select value={f.assetId} onChange={e => patch('fonts', i, { assetId: e.target.value })}>
          {!byId.has(f.assetId) && <option value={f.assetId}>{f.assetId}</option>}
          {fontAssets.map(a => <option key={a.id} value={a.id}>{a.filename}</option>)}
        </select></Field>
        <button className="icon-btn" aria-label={`Remove font ${f.token}`} onClick={() => remove('fonts', i)}>×</button>
        <p className="font-preview" style={{ fontFamily: `"${f.token}", "${f.family}", sans-serif`, fontWeight: f.weight, fontSize: Math.min(f.maxSize, 48) }}>
          Mornings, slowed down <small className="muted" style={{ fontSize: Math.max(f.minSize, 12) }}>{f.minSize}–{f.maxSize}px</small>
        </p>
      </div>)}
      <button disabled={!fontAssets.length} title={fontAssets.length ? '' : 'Upload a font first'}
        onClick={() => add('fonts', { token: `font_${kit.fonts.length + 1}`, family: String(fontAssets[0].meta.family ?? ''), weight: Number(fontAssets[0].meta.weight ?? 400), assetId: fontAssets[0].id, minSize: 16, maxSize: 40 })}>
        Add font
      </button>
    </fieldset>

    <fieldset>
      <legend>Logos</legend>
      {kit.logos.map((l, i) => <div className="kit-row" key={i}>
        {byId.has(l.assetId) ? <AssetThumb asset={byId.get(l.assetId)!} /> : <span className="thumb thumb-text">?</span>}
        <Field label="File"><select value={l.assetId} onChange={e => patch('logos', i, { assetId: e.target.value })}>
          {!byId.has(l.assetId) && <option value={l.assetId}>{l.assetId}</option>}
          {logoAssets.map(a => <option key={a.id} value={a.id}>{a.filename}</option>)}
        </select></Field>
        <Field label="Variant"><select value={l.variant} onChange={e => patch('logos', i, { variant: e.target.value as 'dark' | 'light' })}>
          <option value="dark">dark (on light backgrounds)</option><option value="light">light (on dark backgrounds)</option>
        </select></Field>
        <Field label="Min width (px)"><input type="number" min={0} value={l.minWidth} onChange={e => patch('logos', i, { minWidth: num(e) })} /></Field>
        <Field label="Clear space (× height)"><input type="number" min={0} step={0.1} value={l.clearSpace} onChange={e => patch('logos', i, { clearSpace: num(e) })} /></Field>
        <button className="icon-btn" aria-label="Remove logo" onClick={() => remove('logos', i)}>×</button>
      </div>)}
      <button disabled={!logoAssets.length} title={logoAssets.length ? '' : 'Upload a logo first'}
        onClick={() => add('logos', { assetId: logoAssets[0].id, variant: 'dark', minWidth: 120, clearSpace: 0.5 })}>Add logo</button>
    </fieldset>

    <fieldset>
      <legend>Layout and style</legend>
      <Field label="Safe margin (%)"><input type="number" min={0} max={50} step={0.5} value={kit.safeMarginPct} onChange={e => set({ safeMarginPct: num(e) })} /></Field>
      <Field label="Imagery style"><textarea rows={2} value={kit.imageryStyle} onChange={e => set({ imageryStyle: e.target.value })} /></Field>
      <Field label="Voice"><textarea rows={2} value={kit.voice} onChange={e => set({ voice: e.target.value })} /></Field>
    </fieldset>

    <fieldset>
      <legend>Rules</legend>
      {kit.rules.map((r, i) => <div className="kit-row" key={i}>
        <Field label="ID"><input className="narrow" value={r.id} onChange={e => patch('rules', i, { id: e.target.value })} /></Field>
        <Field label="Rule" grow><input value={r.text} onChange={e => patch('rules', i, { text: e.target.value })} /></Field>
        <Field label="Check"><select value={r.check} onChange={e => patch('rules', i, { check: e.target.value as BrandRule['check'] })}>
          {CHECKS.map(c => <option key={c} value={c}>{c}</option>)}
        </select></Field>
        <button className="icon-btn" aria-label={`Remove rule ${r.id}`} onClick={() => remove('rules', i)}>×</button>
      </div>)}
      <button onClick={() => add('rules', { id: `RULE-${String(kit.rules.length + 1).padStart(2, '0')}`, text: '', check: 'manual' })}>Add rule</button>
    </fieldset>
  </div>;
}

function Field({ label, grow, children }: { label: string; grow?: boolean; children: ReactNode }) {
  return <label className={grow ? 'field grow' : 'field'}><span>{label}</span>{children}</label>;
}

export function AssetThumb({ asset }: { asset: Asset }) {
  if (asset.mime.startsWith('image/')) return <img className="thumb" src={asset.url} alt={asset.caption || asset.filename} />;
  return <span className="thumb thumb-text" aria-hidden="true">{asset.kind === 'font' ? 'Aa' : asset.kind === 'guideline' ? 'PDF' : '?'}</span>;
}
