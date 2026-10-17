import { useEffect, useState } from 'react';
import { Routes, Route, Link, NavLink, useLocation, useMatch } from 'react-router';
import Welcome from '../screens/Welcome';
import BrandIdentity from '../screens/BrandIdentity';
import UseScreen from '../use/UseScreen';
import { StartModal, VariantsGrid, CopilotPanel, LintPanel } from '../copilot';
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
      {id && useReady ? <NavLink to={`/w/${id}/use`}>3 Use</NavLink>
        : <span aria-disabled="true" title="Confirm the brand kit first">3 Use</span>}
    </nav>
  </header>;
}

// ponytail: copilot panels mount here because UseScreen (Prompt 2) is still a placeholder; move them into UseScreen if it takes over layout.
function UseLayout() {
  return <div className="use-layout">
    <div className="use-main"><UseScreen /></div>
    <aside className="use-side"><StartModal /><VariantsGrid /><CopilotPanel /><LintPanel /></aside>
  </div>;
}

export function App() {
  return <><TopBar /><main><Routes>
    <Route path="/" element={<Welcome />} />
    <Route path="/w/:id/brand" element={<BrandIdentity />} />
    <Route path="/w/:id/use" element={<UseLayout />} />
    <Route path="*" element={<p>Page not found. <Link to="/">Go home</Link></p>} />
  </Routes></main></>;
}
