import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { Design } from '../types';
import { useCanvasStore } from '../use/canvasStore';

/** Queue saves by design id so switching cards never loses a pending quick edit. */
export function useCanvasSave(onChange: (design: Design) => void) {
  const changed = useRef(onChange); changed.current = onChange;
  const pending = useRef(new Map<string, Design>());
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const flight = useRef(Promise.resolve());
  const [status, setStatus] = useState('');
  const flush = useCallback(() => {
    clearTimeout(timer.current);
    const batch = [...pending.current.values()]; pending.current.clear();
    flight.current = flight.current.catch(() => {}).then(async () => {
      for (const design of batch) {
        try { await api.saveDesign(design.id, design); }
        catch (e) { if (!pending.current.has(design.id)) pending.current.set(design.id, design); throw e; }
      }
      if (batch.length) setStatus('Saved');
    });
    flight.current.catch(e => setStatus(`Save failed: ${e instanceof Error ? e.message : String(e)}`));
    return flight.current;
  }, []);
  useEffect(() => {
    const unsubscribe = useCanvasStore.subscribe((s, before) => {
      if (!s.design || before.design?.id !== s.design.id || s.design === before.design || s.proposal) return;
      changed.current(s.design);
      pending.current.set(s.design.id, s.design); setStatus('Saving…');
      clearTimeout(timer.current); timer.current = setTimeout(() => void flush(), 350);
    });
    return () => { unsubscribe(); void flush(); };
  }, [flush]);
  return { status, flush };
}
