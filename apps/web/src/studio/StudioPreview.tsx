import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { CanvasView } from '../use/CanvasView';
import { useCanvasStore } from '../use/canvasStore';
import { PropertiesPanel } from '../use/panels';
import type { Asset, Design } from '../types';
import { downloadDesign } from './OptionCard';

type View = 'original' | 'clean' | 'final';
export function StudioPreview({ ws, assets, status, designs, flush }: {
  ws: string; assets: Asset[]; status: string; designs: Record<string, Design>; flush(): Promise<void>;
}) {
  const design = useCanvasStore(s => s.design);
  const kit = useCanvasStore(s => s.kit);
  const selection = useCanvasStore(s => s.selection);
  const [advanced, setAdvanced] = useState(false);
  const [view, setView] = useState<View>('final');
  const [error, setError] = useState('');
  const [zoom, setZoom] = useState(.4);
  const frame = useRef<HTMLDivElement>(null);
  const quality = design ? designs[design.id]?.quality ?? design.quality : undefined;
  const provenance = design?.provenance;
  const imageId = view === 'original' ? provenance?.referenceAssetId : provenance?.cleanPlateAssetId;
  useEffect(() => { setView('final'); setError(''); }, [design?.id]);
  useEffect(() => {
    if (!frame.current || !design) return;
    const observer = new ResizeObserver(([entry]) => setZoom(Math.max(.1, Math.min(1,
      (entry.contentRect.width - 32) / design.width, (entry.contentRect.height - 32) / design.height))));
    observer.observe(frame.current); return () => observer.disconnect();
  }, [design?.id]);
  async function changeView(next: View) {
    try { await flush(); setView(next); setError(''); } catch (e) { setError(String(e)); }
  }
  async function downloadBackground() {
    if (!provenance?.cleanPlateAssetId) return;
    try {
      const result = await fetch(`/api/files/${provenance.cleanPlateAssetId}`);
      if (!result.ok) throw new Error('Could not download the clean background.');
      const url = URL.createObjectURL(await result.blob());
      const a = document.createElement('a'); a.href = url; a.download = 'clean-background.png'; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(String(e)); }
  }
  return <aside className="studio-preview" aria-label="Canvas preview">
    <header><div><small>YOUR DESIGN</small><h2>{design?.label ?? 'Your canvas'}</h2></div>
      {design && <span className="studio-version">v{design.version ?? 1}</span>}
      <span className="studio-save" role="status">{status}</span>
    </header>
    {design && <div className="studio-compare" role="group" aria-label="Compare design stages">
      <button aria-pressed={view === 'original'} disabled={!provenance?.referenceAssetId} onClick={() => void changeView('original')}>Original</button>
      <button aria-pressed={view === 'clean'} disabled={!provenance?.cleanPlateAssetId} onClick={() => void changeView('clean')}>Clean background</button>
      <button aria-pressed={view === 'final'} onClick={() => void changeView('final')}>Final design</button>
    </div>}
    <div className="studio-preview-frame" ref={frame}>
      {design && kit ? view === 'final' ? <CanvasView key={design.id} zoom={zoom} textOnly onDropAsset={() => {}} />
        : <img className="studio-comparison-image" src={`/api/files/${imageId}`} alt={view === 'original' ? 'Original reference' : 'Clean reference background without editable text'} />
        : <div className="studio-preview-empty"><span>✦</span><h3>Your next design starts here.</h3><p>Attach a reference to clean it up or explore four directions.</p></div>}
    </div>
    {design && <>
      <p className="studio-preview-caption">{view === 'final' ? `${design.width} × ${design.height} · Double-click text to edit without AI.`
        : view === 'clean' ? 'Reference background with detected lettering removed. Compare it before using the result.'
        : 'Your original upload, preserved for comparison.'}</p>
      {quality && <details className={`studio-quality ${quality.status}`}>
        <summary><span>{quality.findings.length ? '◌ Review before export' : '✓ Checks complete'}</span><small>{quality.findings.length ? `${quality.findings.length} item${quality.findings.length === 1 ? '' : 's'}` : `${quality.checks.length} checks`}</small></summary>
        {quality.findings.length ? <ul>{quality.findings.map((f, i) => <li key={`${f.code}-${i}`}><span className={`studio-finding ${f.severity}`}>{f.severity === 'error' ? 'Fix' : 'Review'}</span>{f.message}</li>)}</ul>
          : <p>No issues found in the completed checks. Review the image at full size before export.</p>}
        <p className="studio-check-list">Checked: {quality.checks.map(c => c.replaceAll('_', ' ')).join(' · ')}</p>
      </details>}
      {error && <p className="studio-error" role="alert">{error}</p>}
      <div className="studio-preview-actions">
        <Link to={`/w/${ws}/editor?design=${design.id}`}>Full editor ↗</Link>
        <button onClick={() => setAdvanced(a => !a)} aria-expanded={advanced}>Advanced</button>
        {view === 'clean' ? <button onClick={() => void downloadBackground()}>Download background</button>
          : <button className="studio-export" onClick={() => kit && void flush().then(() => downloadDesign(design, kit)).catch(e => setError(String(e)))}>Download PNG</button>}
      </div>
      {advanced && <section className="studio-inspector">
        <h3>Layers</h3><p>Ask in chat for style, layout and image changes.</p>
        <ul>{[...design.layers].reverse().map(l => <li key={l.id}><button aria-pressed={selection.includes(l.id)} onClick={() => useCanvasStore.getState().select([l.id])}>{l.role} <small>{l.type}</small></button></li>)}</ul>
        <fieldset disabled><PropertiesPanel ws={ws} assets={assets} onAsset={() => {}} /></fieldset>
      </section>}
    </>}
  </aside>;
}
