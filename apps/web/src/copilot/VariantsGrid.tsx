import { useEffect, useState } from 'react';
import { saveDesign } from '../api/client';
import { renderThumbnail, useCanvasStore } from '../use';
import type { BrandKit, Design, Job } from '../types';
import { errorText, pollJob, useBrandKit, useCopilotStore, useWorkspaceId } from './shared';

export function VariantsGrid() {
  const ws = useWorkspaceId();
  const kit = useBrandKit(ws);
  const { jobId, gridOpen } = useCopilotStore();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');

  // Keeps polling while the grid is closed so tiles are ready when the user comes back.
  useEffect(() => {
    if (!jobId) return;
    setJob(null); setError('');
    return pollJob(jobId, setJob, setError);
  }, [jobId]);

  if (!jobId) return null;
  const designs = job?.designs ?? [];
  if (!gridOpen) {
    return <button className="side-btn" onClick={() => useCopilotStore.setState({ gridOpen: true })}>
      Variants ({designs.length}/{Math.max(4, designs.length)})
    </button>;
  }

  async function open(design: Design) {
    setError('');
    try {
      const saved = await saveDesign(design.id, design);
      useCanvasStore.getState().load(saved);
      useCopilotStore.setState({ gridOpen: false, startOpen: false });
    } catch (e) { setError(errorText(e)); }
  }

  const slots = Array.from({ length: Math.max(4, designs.length) }, (_, i) => designs[i]);
  return <div className="modal-backdrop">
    <div className="modal wide" role="dialog" aria-modal="true" aria-labelledby="variants-title">
      <header className="modal-head">
        <h2 id="variants-title">Variants</h2>
        <span className="muted" aria-live="polite">{job ? `${job.status === 'done' ? 'Done' : 'Working'} · ${job.progress}` : 'Starting…'}</span>
        <button className="icon-btn" aria-label="Close variants" onClick={() => useCopilotStore.setState({ gridOpen: false })}>×</button>
      </header>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="variants">
        {slots.map((design, i) => design
          ? <button key={design.id} className="tile" onClick={() => open(design)}>
              <DesignThumb design={design} kit={kit} size={400} />
              <span>{design.name}</span>
            </button>
          : <div key={i} className="tile pending"><span className="spinner" aria-hidden="true" /><span className="muted">Generating…</span></div>)}
      </div>
    </div>
  </div>;
}

export function DesignThumb({ design, kit, size = 256 }: { design: Design; kit: BrandKit | null; size?: number }) {
  const [src, setSrc] = useState('');
  // Designs from a job never change once they arrive, so re-render only when the id or kit changes.
  useEffect(() => {
    if (!kit) return;
    let live = true;
    renderThumbnail(design, kit, size).then(url => { if (live) setSrc(url); }, () => {});
    return () => { live = false; };
  }, [design.id, kit, size]); // eslint-disable-line react-hooks/exhaustive-deps
  return src ? <img className="design-thumb" src={src} alt={design.name} style={{ aspectRatio: `${design.width} / ${design.height}` }} />
    : <span className="design-thumb placeholder" style={{ aspectRatio: `${design.width} / ${design.height}` }} />;
}
