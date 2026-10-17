import { useParams } from 'react-router';
export default function UseScreen() {
  const { id } = useParams();
  return <section><h1>Use your brand</h1><p>Layered canvas editor placeholder — Prompt 2.</p><p>Workspace: {id}</p></section>;
}
