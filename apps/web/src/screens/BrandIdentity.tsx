import { Link, useParams } from 'react-router';
export default function BrandIdentity() {
  const { id } = useParams();
  return <section><h1>Brand identity</h1><p>Upload guidelines, logos, fonts and approved images; confirm your brand kit.</p><p>Workspace: {id}. Placeholder — Prompt 1.</p><Link to={`/w/${id}/use`}>Use this brand</Link></section>;
}
