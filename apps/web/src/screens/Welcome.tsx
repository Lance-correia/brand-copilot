import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { createWorkspace, listWorkspaces } from '../api/client';
import type { Workspace } from '../types';

export default function Welcome() {
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { listWorkspaces().then(setWorkspaces, e => setError(e.message)); }, []);

  const open = (ws: Workspace) => navigate(`/w/${ws.id}/${ws.brandKitConfirmed ? 'use' : 'brand'}`);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true); setError('');
    try {
      const ws = await createWorkspace({ name: name.trim() });
      navigate(`/w/${ws.id}/brand`);
    } catch (e) {
      setError((e as Error).message); setBusy(false);
    }
  }

  return <section className="page">
    <h1>Welcome to Brand Copilot</h1>
    <p className="muted">Create a brand workspace, or open one you have already set up.</p>
    <form className="row" onSubmit={create}>
      <input aria-label="Brand name" placeholder="Brand name" value={name} onChange={e => setName(e.target.value)} required />
      <button className="primary" disabled={busy || !name.trim()}>New brand</button>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {workspaces === null ? <p className="muted">Loading workspaces…</p>
      : workspaces.length === 0 ? <p className="muted">No workspaces yet.</p>
      : <ul className="cards">{workspaces.map(ws => <li key={ws.id}>
          <button className="card" onClick={() => open(ws)}>
            <strong>{ws.name}</strong>
            <span className={ws.brandKitConfirmed ? 'badge ok' : 'badge'}>{ws.brandKitConfirmed ? 'Kit confirmed' : 'Needs brand kit'}</span>
            <small className="muted">Created {new Date(ws.createdAt).toLocaleDateString()}</small>
          </button>
        </li>)}</ul>}
  </section>;
}
