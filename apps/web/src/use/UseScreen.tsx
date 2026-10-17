import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import { api } from '../api/client';
import { LintPanel } from '../copilot';
import { loadBrandFonts } from '../lib/fonts';
import type { Asset } from '../types';
import { CanvasView } from './CanvasView';
import { useCanvasStore } from './canvasStore';
import { LayersPanel, LibraryPanel, PropertiesPanel, dropAsset } from './panels';
import { renderDesign } from './render';
import { validateDesign } from './validation';
import './use.css';

const AUTOSAVE_MS = 2000;
const clampZoom = (z: number) => Math.min(2, Math.max(0.25, z));

function download(name: string, href: string) {
  const a = document.createElement('a');
  a.href = href; a.download = name; a.click();
}

/** Autosaves 2 s after each change: POST the first time a design is saved, PUT afterwards. */
function useAutosave(ws: string, savedIds: Set<string>) {
  const [status, setStatus] = useState('');
  const saveNow = useRef<() => void>(() => {});
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function save() {
      clearTimeout(timer);
      const { design, proposal } = useCanvasStore.getState();
      if (!design || proposal) return; // never persist an unaccepted proposal
      setStatus('Saving…');
      try {
        validateDesign(design);
        if (savedIds.has(design.id)) await api.saveDesign(design.id, design);
        else { await api.createDesign(ws, design); savedIds.add(design.id); }
        setStatus(useCanvasStore.getState().design === design ? 'Saved' : 'Unsaved changes');
      } catch (error) {
        setStatus(`Save failed: ${error instanceof Error ? error.message : error}`);
      }
    }
    saveNow.current = () => void save();
    const unsubscribe = useCanvasStore.subscribe((s, prev) => {
      const edited = s.design && prev.design?.id === s.design.id && s.design !== prev.design;
      if (edited || (prev.proposal && !s.proposal)) { setStatus('Unsaved changes'); clearTimeout(timer); timer = setTimeout(save, AUTOSAVE_MS); }
    });
    return () => { unsubscribe(); clearTimeout(timer); };
  }, [ws, savedIds]);
  return { status, saveNow: () => saveNow.current() };
}

export default function UseScreen() {
  const ws = useParams().id!;
  const [params, setParams] = useSearchParams();
  const design = useCanvasStore(s => s.design);
  const kit = useCanvasStore(s => s.kit);
  const proposal = useCanvasStore(s => s.proposal);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const [zoom, setZoom] = useState<number | null>(null); // null = fit to viewport
  const [fit, setFit] = useState(1);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [savedIds] = useState(() => new Set<string>());
  const { status, saveNow } = useAutosave(ws, savedIds);

  // Brand kit and fonts load before the canvas's first render.
  useEffect(() => {
    let cancelled = false;
    setReady(false);
    const { design: current } = useCanvasStore.getState();
    if (current && current.workspaceId !== ws) useCanvasStore.setState({ design: null, selection: [], proposal: null, past: [], future: [] });
    (async () => {
      const [brandKit, list] = await Promise.all([api.getBrandKit(ws), api.listAssets(ws)]);
      await loadBrandFonts(brandKit);
      const designId = params.get('design');
      const loaded = designId && useCanvasStore.getState().design?.id !== designId ? await api.getDesign(designId) : null;
      if (cancelled) return;
      useCanvasStore.getState().setKit(brandKit);
      setAssets(list);
      if (loaded) { savedIds.add(loaded.id); useCanvasStore.getState().load(loaded); }
      setReady(true);
    })().catch(e => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => { cancelled = true; };
  }, [ws]);

  // Keep the open design in the URL so a reload reopens it.
  useEffect(() => {
    if (design && params.get('design') !== design.id) setParams(previous => { const next = new URLSearchParams(previous); next.set('design', design.id); return next; }, { replace: true });
  }, [design?.id]);

  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (!el || !design) return;
    const observer = new ResizeObserver(() => setFit(clampZoom(Math.min((el.clientWidth - 48) / design.width, (el.clientHeight - 48) / design.height))));
    observer.observe(el);
    return () => observer.disconnect();
  }, [design?.width, design?.height, ready]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return;
      const key = e.key.toLowerCase();
      if (key === 's') { e.preventDefault(); saveNow(); return; }
      const typing = e.target instanceof HTMLElement && (e.target.matches('input, textarea, select') || e.target.isContentEditable);
      if (key !== 'z' || typing) return;
      e.preventDefault();
      if (e.shiftKey) useCanvasStore.getState().redo(); else useCanvasStore.getState().undo();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  async function exportPng() {
    if (!design || !kit) return;
    download(`${design.name || design.id}.png`, (await renderDesign(design, kit, 1)).toDataURL('image/png'));
  }
  function exportJson() {
    if (!design) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(design, null, 2)], { type: 'application/json' }));
    download(`${design.name || design.id}.json`, url);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  if (error) return <section className="use-screen"><p className="use-error">Could not open this workspace: {error}</p></section>;
  if (!ready || !kit) return <section className="use-screen"><p className="use-muted">Loading brand kit and fonts…</p></section>;
  const z = zoom ?? fit;
  return <section className="use-screen">
    <aside className="use-left"><LibraryPanel assets={assets} /></aside>
    <div className="use-center">
      <div className="use-toolbar">
        <strong>{design?.name ?? 'No design'}</strong>
        <button onClick={() => setZoom(clampZoom(z - 0.25))}>−</button>
        <span>{Math.round(z * 100)}%</span>
        <button onClick={() => setZoom(clampZoom(z + 0.25))}>+</button>
        <button onClick={() => setZoom(null)}>Fit</button>
        <span className="use-spacer" />
        <button onClick={() => useCanvasStore.getState().undo()} title="Undo (Cmd/Ctrl+Z)">Undo</button>
        <button onClick={() => useCanvasStore.getState().redo()} title="Redo (Shift+Cmd/Ctrl+Z)">Redo</button>
        <Link to={`/w/${ws}/studio${params.get("thread") ? `?thread=${params.get("thread")}` : ""}`}>Back to Studio</Link>
        <button disabled={!design} onClick={saveNow} title="Cmd/Ctrl+S">Save</button>
        <button disabled={!design} onClick={() => void exportPng()}>PNG</button>
        <button disabled={!design} onClick={exportJson}>JSON</button>
        <span className="use-muted">{status}</span>
      </div>
      {proposal && <div className="use-proposal">
        Proposed change to {proposal.ops.length} {proposal.ops.length === 1 ? 'item' : 'items'} (outlined).
        <button onClick={() => useCanvasStore.getState().acceptProposal()}>Accept</button>
        <button onClick={() => useCanvasStore.getState().rejectProposal()}>Reject</button>
      </div>}
      <div className="use-viewport" ref={viewportRef}>
        {design && <CanvasView zoom={z} onDropAsset={(id, point) => {
          const asset = assets.find(a => a.id === id);
          if (asset) void dropAsset(asset, point, kit);
        }} />}
      </div>
    </div>
    <aside className="use-right">
      {design && <><LayersPanel /><PropertiesPanel ws={ws} assets={assets} onAsset={a => setAssets(list => [...list, a])} /></>}
      <LintPanel />
    </aside>
  </section>;
}
