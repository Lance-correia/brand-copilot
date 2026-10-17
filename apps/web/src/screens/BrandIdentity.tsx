import { useEffect, useRef, useState, type DragEvent } from 'react';
import { useNavigate, useParams } from 'react-router';
import { ApiError, deleteAsset, extractBrandKit, getBrandKit, listAssets, saveBrandKit, uploadAsset } from '../api/client';
import type { Asset, BrandKit } from '../types';
import BrandKitForm, { AssetThumb } from './BrandKitForm';
import FolderUpload from './FolderUpload';

const ZONES: { kind: Asset['kind']; label: string; accept: string; hint: string }[] = [
  { kind: 'guideline', label: 'Guidelines', accept: 'application/pdf,.pdf', hint: 'PDF brand book' },
  { kind: 'logo', label: 'Logos', accept: 'image/*,.svg', hint: 'SVG or PNG, each variant' },
  { kind: 'font', label: 'Fonts', accept: '.ttf,.otf,.woff,.woff2', hint: 'TTF, OTF or WOFF' },
  { kind: 'image', label: 'Brand images', accept: 'image/*', hint: 'Approved photography' },
  { kind: 'icon', label: 'Icons', accept: 'image/*,.svg', hint: 'SVG or PNG' },
];
const CAPTION_POLL_MS = 3000;
const CAPTION_POLL_WINDOW_MS = 60_000;

export default function BrandIdentity() {
  const ws = useParams().id!;
  const navigate = useNavigate();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [kit, setKit] = useState<BrandKit | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const pollUntil = useRef(Date.now() + CAPTION_POLL_WINDOW_MS);

  useEffect(() => {
    listAssets(ws).then(setAssets, e => setError(e.message));
    getBrandKit(ws).then(setKit, e => { if (!(e instanceof ApiError && e.status === 404)) setError(e.message); });
  }, [ws]);

  // Captions are filled in by the backend after upload: re-list every 3 s while any is empty, for at most 60 s.
  useEffect(() => {
    if (!assets.some(a => !a.caption) || Date.now() > pollUntil.current) return;
    const timer = setTimeout(() => listAssets(ws).then(setAssets, () => {}), CAPTION_POLL_MS);
    return () => clearTimeout(timer);
  }, [assets, ws]);

  async function run(label: string, task: () => Promise<void>) {
    setBusy(label); setError('');
    try { await task(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  const upload = (kind: Asset['kind'], files: FileList | File[]) => run(`upload-${kind}`, async () => {
    const list = [...files];
    if (!list.length) return;
    pollUntil.current = Date.now() + CAPTION_POLL_WINDOW_MS;
    const results = await Promise.allSettled(list.map(file => uploadAsset(ws, file, kind)));
    setAssets(await listAssets(ws));
    const failed = results.flatMap((r, i) => r.status === 'rejected' ? [`${list[i].name}: ${(r.reason as Error).message}`] : []);
    if (failed.length) throw new Error(`Upload failed — ${failed.join('; ')}`);
  });

  const refresh = () => {
    pollUntil.current = Date.now() + CAPTION_POLL_WINDOW_MS;
    listAssets(ws).then(setAssets, e => setError(e.message));
  };

  const remove = (asset: Asset) => run('delete', async () => {
    await deleteAsset(asset.id);
    setAssets(current => current.filter(a => a.id !== asset.id));
  });

  const extract = () => run('extract', async () => { setKit(await extractBrandKit(ws)); });

  const confirm = () => run('confirm', async () => {
    if (!kit) return;
    await saveBrandKit(ws, { ...kit, confirmed: true });
    navigate(`/w/${ws}/use`);
  });

  const brandAssets = assets.filter(a => a.source === 'brand_asset');
  return <section className="page">
    <h1>Brand identity</h1>
    <p className="muted">Upload guidelines, logos, fonts and approved images, then extract and confirm your brand kit.</p>
    {error && <p className="error" role="alert">{error}</p>}

    <FolderUpload ws={ws} onUploaded={refresh} />

    <div className="zones">
      {ZONES.map(zone => <UploadZone key={zone.kind} {...zone} busy={busy === `upload-${zone.kind}`}
        assets={brandAssets.filter(a => a.kind === zone.kind)} onFiles={files => upload(zone.kind, files)} onRemove={remove} />)}
    </div>

    <div className="row">
      <button className={kit ? '' : 'primary'} onClick={extract} disabled={!!busy || !brandAssets.length}>
        {busy === 'extract' ? 'Extracting…' : kit ? 'Re-extract brand kit' : 'Extract brand kit'}
      </button>
      {kit?.confirmed && <span className="badge ok">Confirmed</span>}
    </div>

    {kit && <>
      <BrandKitForm kit={kit} onChange={setKit} assets={brandAssets} />
      <div className="row sticky-actions">
        <button className="primary" onClick={confirm} disabled={!!busy}>{busy === 'confirm' ? 'Saving…' : 'Confirm brand kit'}</button>
      </div>
    </>}
  </section>;
}

function UploadZone({ kind, label, accept, hint, busy, assets, onFiles, onRemove }: {
  kind: Asset['kind']; label: string; accept: string; hint: string; busy: boolean;
  assets: Asset[]; onFiles: (files: File[]) => void; onRemove: (asset: Asset) => void;
}) {
  const [over, setOver] = useState(false);
  const drop = (e: DragEvent) => { e.preventDefault(); setOver(false); onFiles([...e.dataTransfer.files]); };
  return <div className={`zone${over ? ' over' : ''}`} onDragOver={e => { e.preventDefault(); setOver(true); }}
    onDragLeave={() => setOver(false)} onDrop={drop}>
    <label className="zone-drop">
      <strong>{label}</strong>
      <span className="muted">{busy ? 'Uploading…' : `Drop files or click to browse · ${hint}`}</span>
      <input className="visually-hidden" type="file" multiple accept={accept} data-kind={kind}
        onChange={e => { onFiles([...(e.target.files ?? [])]); e.target.value = ''; }} />
    </label>
    {assets.length > 0 && <ul className="asset-list">{assets.map(asset => <li key={asset.id} className="asset">
      <AssetThumb asset={asset} />
      <div className="asset-meta">
        <span className="asset-caption">{asset.caption || <em className="muted">Captioning…</em>}</span>
        <small className="muted">{asset.filename}</small>
        {asset.tags.length > 0 && <span className="tags">{asset.tags.map(t => <span key={t} className="tag">{t}</span>)}</span>}
      </div>
      <button className="icon-btn" aria-label={`Remove ${asset.filename}`} onClick={() => onRemove(asset)}>×</button>
    </li>)}</ul>}
  </div>;
}
