import { useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { create } from 'zustand';
import { getBrandKit, getJob } from '../api/client';
import type { BrandKit, Job } from '../types';

/** UI state shared by the copilot components (canvas state lives in useCanvasStore). */
export const useCopilotStore = create<{ jobId: string | null; gridOpen: boolean; startOpen: boolean }>(() => ({
  jobId: null, gridOpen: false, startOpen: false,
}));

export function useWorkspaceId(): string {
  const { id } = useParams();
  if (!id) throw new Error('Copilot components need a /w/:id route');
  return id;
}

export function useBrandKit(ws: string): BrandKit | null {
  const [kit, setKit] = useState<BrandKit | null>(null);
  useEffect(() => {
    let live = true;
    getBrandKit(ws).then(k => { if (live) setKit(k); }, () => {});
    return () => { live = false; };
  }, [ws]);
  return kit;
}

/** Polls a job every 1.5 s until it is done or errors; returns a cancel function. */
export function pollJob(jobId: string, onUpdate: (job: Job) => void, onError: (message: string) => void): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout>;
  const tick = async () => {
    try {
      const job = await getJob(jobId);
      if (stopped) return;
      onUpdate(job);
      if (job.status === 'error') onError(job.error ?? 'Job failed');
      else if (job.status !== 'done') timer = setTimeout(tick, 1500);
    } catch (e) {
      if (!stopped) onError(errorText(e));
    }
  };
  tick();
  return () => { stopped = true; clearTimeout(timer); };
}

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
export const newId = (prefix: string) => `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
