import { useState, type DragEvent } from 'react';
import type { Asset } from '../types';
import { groupByFolder, type FolderGroup, type PathedFile } from './folderKinds';

const KIND_LABELS: [Asset['kind'], string][] = [
  ['guideline', 'Guideline'], ['logo', 'Logo'], ['font', 'Font'], ['icon', 'Icon'], ['image', 'Brand image'], ['sample', 'Reference sample'],
];
const CONCURRENCY = 4;

// ponytail: posts directly because api/client uploadAsset has no tags param; switch to it once the client gains one.
async function uploadTagged(ws: string, file: File, kind: Asset['kind'], tag: string): Promise<void> {
  const form = new FormData();
  form.append('file', file); form.append('kind', kind); form.append('tags', tag);
  const response = await fetch(`/api/workspaces/${encodeURIComponent(ws)}/assets`, { method: 'POST', body: form });
  if (!response.ok) {
    const body: { error?: string } = await response.json().catch(() => ({}));
    throw new Error(body.error ?? response.statusText);
  }
}

/** Recursively reads a dropped file or folder; paths are relative to the drop ("Logos/a.svg"). */
async function readEntry(entry: FileSystemEntry): Promise<PathedFile[]> {
  if (entry.name.startsWith('.')) return [];
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
    return [{ file, path: entry.fullPath.replace(/^\//, '') }];
  }
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const children: FileSystemEntry[] = [];
  // readEntries returns at most ~100 entries per call; keep reading until it returns an empty batch.
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    if (!batch.length) break;
    children.push(...batch);
  }
  return (await Promise.all(children.map(readEntry))).flat();
}

export default function FolderUpload({ ws, onUploaded }: { ws: string; onUploaded: () => void }) {
  const [groups, setGroups] = useState<FolderGroup[] | null>(null);
  const [skipped, setSkipped] = useState(0);
  const [progress, setProgress] = useState<{ done: number; total: number; failed: string[] } | null>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState('');
  const uploading = !!progress && progress.done < progress.total;

  function preview(files: PathedFile[]) {
    const next = groupByFolder(files);
    setSkipped(files.length - next.reduce((n, g) => n + g.files.length, 0));
    setGroups(next); setProgress(null); setError('');
  }

  async function drop(event: DragEvent) {
    event.preventDefault(); setOver(false);
    if (uploading) return;
    // webkitGetAsEntry must run synchronously inside the drop handler, before any await.
    const entries = [...event.dataTransfer.items].map(item => item.webkitGetAsEntry()).filter((e): e is FileSystemEntry => !!e);
    try { preview((await Promise.all(entries.map(readEntry))).flat()); }
    catch (e) { setError(`Could not read the dropped folder: ${(e as Error).message}`); }
  }

  async function upload() {
    if (!groups) return;
    const jobs = groups.flatMap(g => g.files.map(file => ({ file, kind: g.kind, tag: g.tag })));
    const failed: string[] = [];
    let done = 0, next = 0;
    setProgress({ done, total: jobs.length, failed });
    const worker = async () => {
      while (next < jobs.length) {
        const job = jobs[next++];
        try { await uploadTagged(ws, job.file, job.kind, job.tag); }
        catch (e) { failed.push(`${job.file.name}: ${(e as Error).message}`); }
        setProgress({ done: ++done, total: jobs.length, failed: [...failed] });
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, jobs.length) }, worker));
    setGroups(null);
    onUploaded();
  }

  const setKind = (i: number, kind: Asset['kind']) => setGroups(gs => gs && gs.map((g, j) => (j === i ? { ...g, kind } : g)));
  const total = groups?.reduce((n, g) => n + g.files.length, 0) ?? 0;

  return <div className={`zone${over ? ' over' : ''}`} style={{ marginTop: '1rem' }}
    onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}>
    <label className="zone-drop">
      <strong>Upload a folder</strong>
      <span className="muted">Drop a brand folder here or click to choose one. Subfolder names decide each file's kind.</span>
      <input className="visually-hidden" type="file" multiple disabled={uploading} data-testid="folder-input"
        ref={el => el?.setAttribute('webkitdirectory', '')}
        onChange={e => { preview([...(e.target.files ?? [])].map(file => ({ file, path: file.webkitRelativePath || file.name }))); e.target.value = ''; }} />
    </label>
    {error && <p className="error" role="alert">{error}</p>}

    {groups && <>
      {groups.length === 0 ? <p className="muted">No images, fonts or PDFs found in that folder.</p>
        : <table style={{ width: '100%', borderCollapse: 'collapse', margin: '.75rem 0' }}>
          <thead><tr style={{ textAlign: 'left' }}><th>Folder</th><th>Files</th><th>Kind</th><th>Tag</th></tr></thead>
          <tbody>{groups.map((g, i) => <tr key={g.folder} style={{ borderTop: '1px solid var(--line)' }}>
            <td>{g.folder}</td>
            <td>{g.files.length}</td>
            <td><select aria-label={`Kind for ${g.folder}`} value={g.kind} disabled={uploading} onChange={e => setKind(i, e.target.value as Asset['kind'])}>
              {KIND_LABELS.map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
            </select></td>
            <td><code>{g.tag}</code></td>
          </tr>)}</tbody>
        </table>}
      {skipped > 0 && <p className="muted">Skipping {skipped} hidden or unsupported file{skipped === 1 ? '' : 's'}.</p>}
      <div className="row">
        <button className="primary" onClick={upload} disabled={uploading || total === 0}>Upload {total} file{total === 1 ? '' : 's'}</button>
        <button onClick={() => setGroups(null)} disabled={uploading}>Cancel</button>
      </div>
    </>}

    {progress && <div aria-live="polite">
      <progress max={progress.total} value={progress.done} style={{ width: '100%' }} />
      <p className="muted">{uploading ? 'Uploading' : 'Uploaded'} {progress.done - progress.failed.length} of {progress.total}
        {progress.failed.length > 0 && `, ${progress.failed.length} failed`}</p>
      {progress.failed.length > 0 && <ul className="error">{progress.failed.map(f => <li key={f}>{f}</li>)}</ul>}
    </div>}
  </div>;
}
