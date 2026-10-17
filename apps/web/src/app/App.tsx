import { useEffect, useState } from 'react';
import { Routes, Route, Link, NavLink, useLocation, useMatch, Navigate, useParams } from 'react-router';
import Welcome from '../screens/Welcome';
import BrandIdentity from '../screens/BrandIdentity';
import UseScreen from '../use/UseScreen';
import StudioScreen from '../studio/StudioScreen';
import { getWorkspace } from '../api/client';
import type { Workspace } from '../types';
import './styles.css';

function TopBar() {
  const id = useMatch('/w/:id/*')?.params.id;
  const { pathname } = useLocation();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  // Refetch on every navigation so the Use step unlocks right after the kit is confirmed.
  useEffect(() => {
    if (!id) { setWorkspace(null); return; }
    let live = true;
    getWorkspace(id).then(ws => { if (live) setWorkspace(ws); }, () => { if (live) setWorkspace(null); });
    return () => { live = false; };
  }, [id, pathname]);

  const useReady = !!workspace?.brandKitConfirmed;
  return <header className="topbar">
    <Link to="/" className="brand">Brand Copilot</Link>
    {workspace && <span className="ws-name">{workspace.name}</span>}
    <nav className="steps" aria-label="Steps">
      <NavLink to="/" end>1 Welcome</NavLink>
      {id ? <NavLink to={`/w/${id}/brand`}>2 Brand identity</NavLink> : <span aria-disabled="true">2 Brand identity</span>}
      {id && useReady ? <NavLink to={`/w/${id}/studio`}>3 Studio</NavLink>
        : <span aria-disabled="true" title="Confirm the brand kit first">3 Studio</span>}
    </nav>
  </header>;
}

function LegacyUse() {
  const { id } = useParams();
  const { search } = useLocation();
  return <Navigate to={`/w/${id}/studio${search}`} replace />;
}

export function App() {
  return <><TopBar /><main><Routes>
    <Route path="/" element={<Welcome />} />
    <Route path="/w/:id/brand" element={<BrandIdentity />} />
    <Route path="/w/:id/use" element={<LegacyUse />} />
    <Route path="/w/:id/studio" element={<StudioScreen />} />
    <Route path="/w/:id/editor" element={<UseScreen />} />
    <Route path="*" element={<p>Page not found. <Link to="/">Go home</Link></p>} />
  </Routes></main></>;
}
