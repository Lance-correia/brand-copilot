import { useState } from 'react';
import { api } from '../api/client';
import type { Asset, BrandKit, Design, EditOp, ImageLayer, Layer, LayerProps } from '../types';
import { useCanvasStore } from './canvasStore';
import { loadImage, luminanceUnder } from './render';

const apply = (ops: EditOp[]) => useCanvasStore.getState().applyOps(ops);
const SOURCE_LABEL = { brand_asset: 'Brand', generated: 'Generated', upload: 'Upload' } as const;
const ASSET_MIME = 'application/x-brand-asset';
const newLayerId = () => `lay_${crypto.randomUUID().slice(0, 8)}`;

/** Logo variant for a box: the dark logo on light backgrounds, the light one on dark. */
async function pickLogo(asset: Asset, design: Design, kit: BrandKit, box: { x: number; y: number; w: number; h: number }, excludeId?: string) {
  if (asset.kind !== 'logo') return asset.id;
  const variant = await luminanceUnder(design, kit, box, excludeId) > 0.5 ? 'dark' : 'light';
  return kit.logos.find(l => l.variant === variant)?.assetId ?? asset.id;
}

/** Library drop: replace the image layer under the point, or add a new image layer there. */
export async function dropAsset(asset: Asset, point: { x: number; y: number }, kit: BrandKit) {
  const design = useCanvasStore.getState().design;
  if (!design || !['image', 'logo', 'icon'].includes(asset.kind)) return;
  const target = [...design.layers].reverse().find((l): l is ImageLayer => l.type === 'image' && l.visible && !l.locked
    && point.x >= l.x && point.x <= l.x + l.w && point.y >= l.y && point.y <= l.y + l.h);
  if (target) {
    const assetId = await pickLogo(asset, design, kit, target, target.id);
    return apply([{ op: 'replace_image', layerId: target.id, assetId, source: asset.source }]);
  }
  const img = await loadImage(asset.id).catch(() => null);
  const aspect = (img?.naturalHeight || asset.height || 1) / (img?.naturalWidth || asset.width || 1);
  const minLogo = kit.logos.find(l => l.assetId === asset.id)?.minWidth ?? 0;
  const w = Math.round(asset.kind === 'logo' ? Math.max(minLogo, design.width * 0.2) : design.width * (asset.kind === 'icon' ? 0.12 : 0.4));
  const h = Math.max(1, Math.round(w * aspect));
  const box = { x: Math.round(point.x - w / 2), y: Math.round(point.y - h / 2), w, h };
  const assetId = await pickLogo(asset, design, kit, box);
  apply([{ op: 'add_layer', layer: { id: newLayerId(), type: 'image', role: asset.kind === 'logo' ? 'logo' : 'decoration', ...box,
    rotation: 0, visible: true, locked: false, source: asset.source, assetId, fit: asset.kind === 'image' ? 'cover' : 'contain' } }]);
}

export function LayersPanel() {
  const design = useCanvasStore(s => s.design)!;
  const selection = useCanvasStore(s => s.selection);
  const select = useCanvasStore(s => s.select);
  const [dragId, setDragId] = useState<string | null>(null);
  const top = design.layers.length - 1;
  return <section className="use-panel">
    <h3>Layers</h3>
    <ol className="use-layers">
      {[...design.layers].reverse().map((layer, i) => (
        <li key={layer.id} draggable className={selection.includes(layer.id) ? 'selected' : ''}
          onClick={() => select([layer.id])} onDragStart={() => setDragId(layer.id)} onDragOver={e => e.preventDefault()}
          onDrop={() => { if (dragId && dragId !== layer.id) apply([{ op: 'reorder_layer', layerId: dragId, index: top - i }]); setDragId(null); }}>
          <span className="use-layer-name">{layer.role} <small>{layer.type}</small></span>
          {layer.type === 'image' && <span className={`use-badge ${layer.source}`}>{SOURCE_LABEL[layer.source]}</span>}
          <button title={layer.visible ? 'Hide' : 'Show'} onClick={e => { e.stopPropagation(); apply([{ op: 'update_layer', layerId: layer.id, props: { visible: !layer.visible } }]); }}>{layer.visible ? '👁' : '—'}</button>
          <button title={layer.locked ? 'Unlock' : 'Lock'} onClick={e => { e.stopPropagation(); apply([{ op: 'update_layer', layerId: layer.id, props: { locked: !layer.locked } }]); }}>{layer.locked ? '🔒' : '🔓'}</button>
          <button title="Delete" onClick={e => { e.stopPropagation(); apply([{ op: 'remove_layer', layerId: layer.id }]); }}>✕</button>
        </li>))}
    </ol>
  </section>;
}

function Swatches({ kit, value, onPick }: { kit: BrandKit; value?: string; onPick(token: string): void }) {
  return <div className="use-swatches">{kit.colors.map(c =>
    <button key={c.token} title={c.token} className={c.token === value ? 'active' : ''} style={{ background: c.hex }} onClick={() => onPick(c.token)} />)}</div>;
}

export function PropertiesPanel({ ws, assets, onAsset }: { ws: string; assets: Asset[]; onAsset(asset: Asset): void }) {
  const kit = useCanvasStore(s => s.kit)!;
  const layer = useCanvasStore(s => s.design?.layers.find(l => l.id === s.selection[0]));
  if (!layer) return <section className="use-panel"><h3>Properties</h3><p className="use-muted">Select a layer.</p></section>;
  const update = (props: LayerProps) => apply([{ op: 'update_layer', layerId: layer.id, props }]);
  return <section className="use-panel">
    <h3>Properties <small>{layer.role}</small></h3>
    {layer.type === 'text' && <TextProps key={layer.id + layer.text} layer={layer} kit={kit} update={update} />}
    {layer.type === 'shape' && <>
      <label>Fill</label><Swatches kit={kit} value={layer.fillToken} onPick={fillToken => update({ fillToken })} />
      <label>Corner radius <input type="number" min={0} value={layer.radius ?? 0} onChange={e => update({ radius: Math.max(0, Number(e.target.value)) })} /></label>
    </>}
    {layer.type === 'image' && <ImageProps key={layer.id} ws={ws} layer={layer} assets={assets} onAsset={onAsset} />}
  </section>;
}

function TextProps({ layer, kit, update }: { layer: Extract<Layer, { type: 'text' }>; kit: BrandKit; update(p: LayerProps): void }) {
  const [text, setText] = useState(layer.text);
  const font = kit.fonts.find(f => f.token === layer.fontToken);
  const clamp = (n: number) => font ? Math.min(font.maxSize, Math.max(font.minSize, n)) : Math.max(1, n);
  return <>
    <label>Text<textarea value={text} rows={3} onChange={e => setText(e.target.value)} onBlur={() => text !== layer.text && update({ text })} /></label>
    <label>Font <select value={layer.fontToken} onChange={e => {
      const next = kit.fonts.find(f => f.token === e.target.value);
      update({ fontToken: e.target.value, ...(next && { fontSize: Math.min(next.maxSize, Math.max(next.minSize, layer.fontSize)) }) });
    }}>{kit.fonts.map(f => <option key={f.token} value={f.token}>{f.token} ({f.family})</option>)}</select></label>
    <label>Size <input type="number" min={font?.minSize} max={font?.maxSize} value={layer.fontSize}
      onChange={e => e.target.value && update({ fontSize: clamp(Number(e.target.value)) })} /></label>
    <label>Color</label><Swatches kit={kit} value={layer.colorToken} onPick={colorToken => update({ colorToken })} />
    <label>Align</label>
    <div className="use-row">{(['left', 'center', 'right'] as const).map(align =>
      <button key={align} className={layer.align === align ? 'active' : ''} onClick={() => update({ align })}>{align}</button>)}</div>
  </>;
}

function ImageProps({ ws, layer, assets, onAsset }: { ws: string; layer: ImageLayer; assets: Asset[]; onAsset(a: Asset): void }) {
  const [instruction, setInstruction] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const kind = layer.role === 'logo' ? 'logo' : 'image';
  const choices = assets.filter(a => a.kind === kind || (kind === 'image' && a.kind === 'icon'));
  async function edit() {
    setBusy(true); setError('');
    try {
      const asset = await api.editImage(ws, { assetId: layer.assetId, instruction });
      onAsset(asset);
      apply([{ op: 'replace_image', layerId: layer.id, assetId: asset.id, source: asset.source }]);
      setInstruction('');
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }
  return <>
    <label>Fit <select value={layer.fit} onChange={e => apply([{ op: 'update_layer', layerId: layer.id, props: { fit: e.target.value as ImageLayer['fit'] } }])}>
      <option value="cover">cover</option><option value="contain">contain</option></select></label>
    <label>Replace from library</label>
    <div className="use-thumbs">{choices.map(a => <img key={a.id} src={a.url} alt={a.caption || a.filename} title={a.caption || a.filename}
      className={a.id === layer.assetId ? 'active' : ''} onClick={() => apply([{ op: 'replace_image', layerId: layer.id, assetId: a.id, source: a.source }])} />)}</div>
    {layer.source === 'generated'
      ? <form onSubmit={e => { e.preventDefault(); if (instruction.trim()) void edit(); }}>
          <label>Edit with AI<input value={instruction} disabled={busy} placeholder="Warmer light, add steam" onChange={e => setInstruction(e.target.value)} /></label>
          <button disabled={busy || !instruction.trim()}>{busy ? 'Editing…' : 'Apply'}</button>
          {error && <p className="use-error">{error}</p>}
        </form>
      : layer.source === 'brand_asset' && <p className="use-muted">Brand asset: swap only</p>}
  </>;
}

const TABS = ['Logos', 'Images', 'Icons', 'Colors', 'Fonts'] as const;
const TAB_KIND = { Logos: 'logo', Images: 'image', Icons: 'icon' } as const;

export function LibraryPanel({ assets }: { assets: Asset[] }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Logos');
  const kit = useCanvasStore(s => s.kit)!;
  const layer = useCanvasStore(s => s.design?.layers.find(l => l.id === s.selection[0]));
  function pickColor(token: string) {
    if (layer?.type === 'text') apply([{ op: 'update_layer', layerId: layer.id, props: { colorToken: token } }]);
    else if (layer?.type === 'shape') apply([{ op: 'update_layer', layerId: layer.id, props: { fillToken: token } }]);
    else if (!layer) apply([{ op: 'set_background', background: { colorToken: token } }]);
  }
  return <section className="use-panel use-library">
    <h3>Brand library</h3>
    <div className="use-tabs">{TABS.map(t => <button key={t} className={t === tab ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>)}</div>
    {tab in TAB_KIND && <div className="use-thumbs">
      {assets.filter(a => a.kind === TAB_KIND[tab as keyof typeof TAB_KIND]).map(a =>
        <img key={a.id} src={a.url} alt={a.caption || a.filename} title={`${a.caption || a.filename} (drag onto the canvas)`} draggable
          className={kit.logos.find(l => l.assetId === a.id)?.variant === 'light' ? 'on-dark' : ''}
          onDragStart={e => e.dataTransfer.setData(ASSET_MIME, a.id)} />)}
    </div>}
    {tab === 'Colors' && <>
      <p className="use-muted">{layer ? `Click to recolor the ${layer.role}.` : 'Click to set the background.'}</p>
      {kit.colors.map(c => <button key={c.token} className="use-color" onClick={() => pickColor(c.token)}>
        <span style={{ background: c.hex }} />{c.token} <small>{c.hex} · {c.role}</small></button>)}
    </>}
    {tab === 'Fonts' && <>
      <p className="use-muted">{layer?.type === 'text' ? `Click to set the ${layer.role} font.` : 'Select a text layer to apply a font.'}</p>
      {kit.fonts.map(f => <button key={f.token} className="use-font" style={{ fontFamily: f.token }} disabled={layer?.type !== 'text'}
        onClick={() => layer?.type === 'text' && apply([{ op: 'update_layer', layerId: layer.id,
          props: { fontToken: f.token, fontSize: Math.min(f.maxSize, Math.max(f.minSize, layer.fontSize)) } }])}>
        {f.token} <small>{f.family} · {f.minSize}–{f.maxSize}px</small></button>)}
    </>}
  </section>;
}
