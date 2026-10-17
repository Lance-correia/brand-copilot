import { useEffect, useRef, useState } from 'react';
import { CanvasView } from '../use/CanvasView';
import { useCanvasStore } from '../use/canvasStore';
import { PropertiesPanel } from '../use/panels';
import type { Asset } from '../types';
import { downloadDesign } from './OptionCard';

export function StudioPreview({ ws, assets, status }: { ws: string; assets: Asset[]; status: string }) {
  const design = useCanvasStore(s => s.design);
  const kit = useCanvasStore(s => s.kit);
  const selection = useCanvasStore(s => s.selection);
  const [advanced, setAdvanced] = useState(false);
  const [zoom, setZoom] = useState(.4);
  const frame = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!frame.current || !design) return;
    const observer = new ResizeObserver(([entry]) => setZoom(Math.max(.1, Math.min(1,
      (entry.contentRect.width - 32) / design.width, (entry.contentRect.height - 32) / design.height))));
    observer.observe(frame.current); return () => observer.disconnect();
  }, [design?.id]);
  return <aside className="studio-preview" aria-label="Canvas preview">
    <header><div><small>PREVIEW</small><h2>{design?.label ?? 'Your canvas'}</h2></div>
      {design && <span className="studio-version">v{design.version ?? 1}</span>}
      <span className="studio-save" role="status">{status}</span>
    </header>
    <div className="studio-preview-frame" ref={frame}>
      {design && kit ? <CanvasView key={design.id} zoom={zoom} textOnly onDropAsset={() => {}} />
        : <div className="studio-preview-empty"><span>✦</span><h3>A little space for your next idea.</h3><p>Attach a reference. Your editable options will appear here.</p></div>}
    </div>
    {design && <>
      <div className="studio-preview-actions"><p>Double-click text to make a quick fix.</p>
        <button onClick={() => setAdvanced(a => !a)} aria-expanded={advanced}>Advanced</button>
        <button onClick={() => kit && void downloadDesign(design, kit)}>PNG</button>
      </div>
      {advanced && <section className="studio-inspector">
        <h3>Layers</h3><p>Ask in chat for style, layout and image changes.</p>
        <ul>{[...design.layers].reverse().map(l => <li key={l.id}><button aria-pressed={selection.includes(l.id)} onClick={() => useCanvasStore.getState().select([l.id])}>{l.role} <small>{l.type}</small></button></li>)}</ul>
        <fieldset disabled><PropertiesPanel ws={ws} assets={assets} onAsset={() => {}} /></fieldset>
      </section>}
    </>}
  </aside>;
}
