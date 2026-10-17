import { useEffect, useRef, useState } from 'react';
import { createDesign, decompose, generateVariants, listDesigns, uploadSample } from '../api/client';
import { useCanvasStore } from '../use';
import type { Asset, Design, DesignSpec } from '../types';
import { DesignThumb } from './VariantsGrid';
import { errorText, newId, pollJob, useBrandKit, useCopilotStore, useWorkspaceId } from './shared';

const SIZES: [number, number][] = [[1080, 1080], [1080, 1350], [1080, 1920]];

export function StartModal() {
  const ws = useWorkspaceId();
  const kit = useBrandKit(ws);
  const design = useCanvasStore(s => s.design);
  const { startOpen, gridOpen } = useCopilotStore();
  const [sample, setSample] = useState<{ asset: Asset; spec: DesignSpec } | null>(null);
  const [brief, setBrief] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<Design[] | null>(null);
  const cancelPoll = useRef<(() => void) | null>(null);

  const hasDesign = design?.workspaceId === ws;
  const visible = !gridOpen && (!hasDesign || startOpen);
  useEffect(() => { if (visible) listDesigns(ws).then(setSaved, e => setError(errorText(e))); }, [visible, ws]);
  useEffect(() => () => cancelPoll.current?.(), []);

  if (!visible) {
    return hasDesign && !gridOpen
      ? <button className="side-btn" onClick={() => useCopilotStore.setState({ startOpen: true })}>New or open design…</button>
      : null;
  }

  const close = () => useCopilotStore.setState({ startOpen: false });
  function open(next: Design) {
    useCanvasStore.getState().load(next);
    close();
  }
  async function run(label: string, task: () => Promise<void>) {
    setBusy(label); setError('');
    try { await task(); setBusy(''); } catch (e) { setError(errorText(e)); setBusy(''); }
  }

  const upload = (file: File) => run('Analyzing sample…', async () => { setSample(await uploadSample(ws, file)); });

  const split = () => run('Splitting into layers…', async () => {
    const { jobId } = await decompose(ws, { sampleAssetId: sample!.asset.id });
    const first = await new Promise<Design>((resolve, reject) => {
      cancelPoll.current = pollJob(jobId, job => {
        setBusy(`Splitting into layers… ${job.progress}`);
        if (job.status === 'done') job.designs[0] ? resolve(job.designs[0]) : reject(new Error('The job returned no design'));
      }, message => reject(new Error(message)));
    });
    open(first);
  });

  const variants = () => run('Starting variants…', async () => {
    const { jobId } = await generateVariants(ws, { sampleAssetId: sample!.asset.id, ...(brief.trim() ? { brief: brief.trim() } : {}) });
    useCopilotStore.setState({ jobId, gridOpen: true, startOpen: false });
  });

  const blank = (width: number, height: number) => run('Creating canvas…', async () => {
    const paper = kit?.colors.find(c => c.token === 'paper') ?? kit?.colors.find(c => c.role === 'background') ?? kit?.colors[0];
    open(await createDesign(ws, { id: newId('des'), workspaceId: ws, name: `Blank ${width}×${height}`, width, height,
      background: { colorToken: paper?.token ?? 'paper' }, layers: [] }));
  });

  const spec = sample?.spec;
  return <div className="modal-backdrop">
    <div className="modal wide" role="dialog" aria-modal="true" aria-labelledby="start-title">
      <header className="modal-head">
        <h2 id="start-title">Start a design</h2>
        {hasDesign && <button className="icon-btn" aria-label="Close" onClick={close}>×</button>}
      </header>
      {error && <p className="error" role="alert">{error}</p>}
      {busy && <p className="muted" aria-live="polite"><span className="spinner" aria-hidden="true" /> {busy}</p>}

      <div className="start-grid">
        <section className="start-card">
          <h3>Upload an image</h3>
          <p className="muted">We read its layout, then rebuild it in your brand.</p>
          <label className="zone-drop small">
            <span>{sample ? sample.asset.filename : 'Choose an image'}</span>
            <input className="visually-hidden" type="file" accept="image/*" disabled={!!busy}
              onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ''; }} />
          </label>
          {spec && <>
            <dl className="spec">
              <dt>Aspect</dt><dd>{spec.aspect}</dd>
              <dt>Layout</dt><dd>{spec.hierarchy.join(' → ')}</dd>
              <dt>Mood</dt><dd>{spec.mood}</dd>
              <dt>Imagery</dt><dd>{spec.imageryStyle}</dd>
              <dt>Colors</dt><dd>{spec.observedColors.map(c => <span key={c} className="swatch" title={c} style={{ background: c }} />)}</dd>
            </dl>
            <button onClick={split} disabled={!!busy}>Split into layers</button>
            <input aria-label="Brief (optional)" placeholder="Optional one-line brief, e.g. autumn launch" value={brief}
              maxLength={200} onChange={e => setBrief(e.target.value)} />
            <button className="primary" onClick={variants} disabled={!!busy}>Generate 4 variants</button>
          </>}
        </section>

        <section className="start-card">
          <h3>Blank canvas</h3>
          <p className="muted">Start empty on your paper background.</p>
          {SIZES.map(([w, h]) => <button key={h} onClick={() => blank(w, h)} disabled={!!busy}>{w} × {h}</button>)}
        </section>

        <section className="start-card">
          <h3>Open a saved design</h3>
          {saved === null ? <p className="muted">Loading…</p>
            : saved.length === 0 ? <p className="muted">No saved designs yet.</p>
            : <ul className="saved">{saved.map(d => <li key={d.id}>
                <button className="saved-item" onClick={() => { try { open(d); } catch (e) { setError(errorText(e)); } }} disabled={!!busy}>
                  <DesignThumb design={d} kit={kit} size={96} />
                  <span>{d.name}<small className="muted">{d.width}×{d.height}</small></span>
                </button>
              </li>)}</ul>}
        </section>
      </div>
    </div>
  </div>;
}
