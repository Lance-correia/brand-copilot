import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { BrandKit, Design } from '../types';
import { renderThumbnail } from '../use';
import { renderDesign } from '../use/render';

export async function downloadDesign(design: Design, kit: BrandKit) {
  const a = document.createElement('a');
  a.href = (await renderDesign(design, kit)).toDataURL('image/png');
  a.download = `${design.label ?? design.name}-v${design.version ?? 1}.png`; a.click();
}

export function OptionCard({ id, designs, kit, focused, onFocus, onOpen }: {
  id: string; designs: Record<string, Design>; kit: BrandKit; focused: string[];
  onFocus(design: Design): void; onOpen(design: Design): void;
}) {
  const [versionId, setVersionId] = useState(id);
  const design = designs[versionId] ?? designs[id];
  const [src, setSrc] = useState('');
  const [errors, setErrors] = useState<number | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!design) return;
    let live = true; setErrors(null);
    renderThumbnail(design, kit, 420).then(url => { if (live) setSrc(url); }, e => { if (live) setError(String(e)); });
    api.lintDesign(design.workspaceId, design).then(v => { if (live) setErrors(v.filter(x => x.severity === 'error').length); }, () => {});
    return () => { live = false; };
  }, [design, kit]);
  if (!design) return <div className="studio-card">Loading option…</div>;
  const history: Design[] = [];
  const seen = new Set<string>();
  let ancestor: Design | undefined = designs[id];
  while (ancestor && !seen.has(ancestor.id)) {
    seen.add(ancestor.id); history.push(ancestor);
    ancestor = ancestor.parentId ? designs[ancestor.parentId] : undefined;
  }
  const selected = focused.includes(design.id);
  return <article className={`studio-card${selected ? ' is-focused' : ''}`} data-design-id={design.id} data-label={design.label} data-version={design.version ?? 1}>
    <div className="studio-card-title"><strong>{design.label ?? design.name}</strong>
      <select className="studio-version" aria-label={`Version of ${design.label}`} value={versionId} onChange={e => { setVersionId(e.target.value); const earlier = designs[e.target.value]; if (earlier) onFocus(earlier); }}>
        {history.map(d => <option key={d.id} value={d.id}>v{d.version ?? 1}</option>)}
      </select>
      <span className={`studio-lint${errors === 0 ? ' ok' : ''}`} title="Deterministic brand check">{errors === null ? 'Checking…' : errors ? `${errors} errors` : 'Brand checked'}</span>
    </div>
    <button className="studio-card-image" aria-label={`Preview ${design.label} v${design.version ?? 1}`} onClick={() => onFocus(design)}>
      {src ? <img src={src} alt={`${design.label} v${design.version ?? 1}`} /> : <span>Rendering…</span>}
    </button>
    {!!design.quality?.findings.length && <p className="studio-card-review">{design.quality.findings.length} item{design.quality.findings.length === 1 ? '' : 's'} to review in preview</p>}
    <div className="studio-card-actions">
      <button aria-pressed={selected} onClick={() => onFocus(design)}>{selected ? 'Unfocus' : 'Focus'}</button>
      <button onClick={() => onOpen(design)}>Open full editor</button>
      <button onClick={() => void downloadDesign(design, kit).catch(e => setError(String(e)))}>Download PNG</button>
    </div>
    {error && <p role="alert">{error}</p>}
  </article>;
}
