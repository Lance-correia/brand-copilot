import { useEffect, useState } from 'react';
import { lintDesign } from '../api/client';
import { useCanvasStore } from '../use';
import type { LintViolation } from '../types';
import { errorText, useWorkspaceId } from './shared';

export function LintPanel() {
  const ws = useWorkspaceId();
  const design = useCanvasStore(s => s.design);
  const selection = useCanvasStore(s => s.selection);
  const [violations, setViolations] = useState<LintViolation[] | null>(null);
  const [error, setError] = useState('');

  // Deterministic server lint (no model call), debounced 600 ms after each design change.
  useEffect(() => {
    if (!design || design.workspaceId !== ws) { setViolations(null); return; }
    let live = true;
    const timer = setTimeout(() => lintDesign(ws, design).then(
      v => { if (live) { setViolations(v); setError(''); } },
      e => { if (live) setError(errorText(e)); }), 600);
    return () => { live = false; clearTimeout(timer); };
  }, [design, ws]);

  if (!design) return null;

  function fix(v: LintViolation) {
    try { useCanvasStore.getState().applyOps(v.fix); } catch (e) { setError(errorText(e)); }
  }
  const select = (v: LintViolation) => { if (v.layerId) useCanvasStore.getState().select([v.layerId]); };
  const groups = (['error', 'warning'] as const).map(severity => [severity, (violations ?? []).filter(v => v.severity === severity)] as const);

  return <section className="panel lint">
    <h2>Brand check {violations && <span className={violations.length ? 'badge' : 'badge ok'}>{violations.length || '✓'}</span>}</h2>
    {error && <p className="error" role="alert">{error}</p>}
    {violations === null ? <p className="muted">Checking…</p>
      : violations.length === 0 ? <p className="muted">On brand. No issues found.</p>
      : groups.map(([severity, list]) => list.length > 0 && <div key={severity}>
          <h3 className={`sev ${severity}`}>{severity === 'error' ? 'Errors' : 'Warnings'} ({list.length})</h3>
          <ul className="violations">{list.map((v, i) => <li key={`${v.ruleId}-${v.layerId}-${i}`}
              className={v.layerId && selection.includes(v.layerId) ? 'selected' : ''}>
            <button className="violation" onClick={() => select(v)} disabled={!v.layerId}>
              <code>{v.ruleId}</code> {v.message}
            </button>
            {v.fix.length > 0 && <button onClick={() => fix(v)}>Fix</button>}
          </li>)}</ul>
        </div>)}
  </section>;
}
