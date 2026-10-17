import { useCallback, useEffect, useRef, useState, type FormEvent, type DragEvent, type ClipboardEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { api } from '../api/client';
import { loadBrandFonts } from '../lib/fonts';
import type { Asset, BrandKit, Design, Job, Thread } from '../types';
import { useCanvasStore } from '../use/canvasStore';
import { OptionCard } from './OptionCard';
import { StudioPreview } from './StudioPreview';
import { useCanvasSave } from './useCanvasSave';
import '../use/use.css';
import './studio.css';

type Pending = { threadId: string; jobId?: string; text: string; attachmentIds: string[]; job?: Job };
const errorText = (e: unknown) => e instanceof Error ? e.message : String(e);
const clearCanvas = () => useCanvasStore.setState({ design: null, selection: [], proposal: null, past: [], future: [] });

export default function StudioScreen() {
  const ws = useParams().id!;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const threadId = params.get('thread');
  const selected = useRef(threadId); selected.current = threadId;
  const [ready, setReady] = useState(false);
  const [kit, setKit] = useState<BrandKit | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [thread, setThread] = useState<Thread | null>(null);
  const [designs, setDesigns] = useState<Record<string, Design>>({});
  const designRef = useRef(designs); designRef.current = designs;
  const [assets, setAssets] = useState<Asset[]>([]);
  const [focused, setFocused] = useState<string[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [library, setLibrary] = useState(false);
  const [assetQuery, setAssetQuery] = useState('');
  const [over, setOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const chatEnd = useRef<HTMLDivElement>(null);
  const changed = useCallback((d: Design) => setDesigns(all => ({ ...all, [d.id]: d })), []);
  const { status, flush } = useCanvasSave(changed);
  const pendingKey = `studio:pending:${ws}`;
  const focusKey = `studio:focus:${ws}:${threadId}`;

  useEffect(() => {
    let live = true;
    setReady(false); setThread(null); clearCanvas(); setError('');
    Promise.all([api.getBrandKit(ws), api.listThreads(ws), api.listDesigns(ws), api.listAssets(ws)]).then(async ([brand, chats, list, libraryAssets]) => {
      await loadBrandFonts(brand);
      if (!live) return;
      setKit(brand); useCanvasStore.getState().setKit(brand);
      setThreads(chats); setDesigns(Object.fromEntries(list.map(d => [d.id, d]))); setAssets(libraryAssets);
      if (!params.get('thread') && chats.length) setParams({ thread: chats[0].id }, { replace: true });
      try { const saved = localStorage.getItem(pendingKey); if (saved) setPending(JSON.parse(saved)); } catch { localStorage.removeItem(pendingKey); }
      setReady(true);
    }).catch(e => live && setError(errorText(e)));
    return () => { live = false; };
  }, [ws]);

  useEffect(() => {
    if (!ready) return;
    let live = true;
    setError(''); setAttachments([]); setText('');
    if (!threadId) { setThread(null); setFocused([]); clearCanvas(); return; }
    api.getThread(threadId).then(next => {
      if (!live) return;
      if (next.workspaceId !== ws) throw new Error('This chat belongs to another brand.');
      setThread(next);
      let focus: string[] = [];
      try { focus = JSON.parse(localStorage.getItem(focusKey) ?? '[]'); } catch { /* reset invalid local preference */ }
      focus = focus.filter(id => !!designRef.current[id]);
      if (!focus.length) {
        const latest = [...next.messages].reverse().find(m => m.designIds.length)?.designIds[0];
        if (latest) focus = [latest];
      }
      setFocused(focus);
      const first = designRef.current[focus[0]];
      if (first) useCanvasStore.getState().load(first); else clearCanvas();
    }).catch(e => live && setError(errorText(e)));
    return () => { live = false; };
  }, [ready, threadId, ws]);

  useEffect(() => { if (ready && threadId && thread?.id === threadId) localStorage.setItem(focusKey, JSON.stringify(focused)); }, [focused, ready, focusKey, thread?.id]);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [thread?.messages.length, pending?.job?.steps?.length]);

  useEffect(() => {
    if (!pending?.jobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const current = pending;
    async function poll() {
      try {
        const job = await api.getJob(current.jobId!);
        if (stopped) return;
        setPending(p => p && p.jobId === current.jobId ? { ...p, job } : p);
        if (job.designs.length) setDesigns(all => ({ ...all, ...Object.fromEntries(job.designs.map(d => [d.id, d])) }));
        if (job.status === 'done' || job.status === 'error') {
          const next = await api.getThread(current.threadId);
          const [chats, refreshedAssets] = await Promise.all([api.listThreads(ws), api.listAssets(ws)]);
          setAssets(refreshedAssets);
          if (stopped) return;
          setThreads(chats); setDesigns(all => ({ ...all, ...Object.fromEntries(job.designs.map(d => [d.id, d])) }));
          if (selected.current === current.threadId) {
            setThread(next);
            if (job.designs.length) {
              setFocused(before => {
                const replacements = before.map(id => job.designs.find(d => d.parentId === id || d.label === designRef.current[id]?.label)?.id ?? id);
                return replacements.length ? [...new Set(replacements)] : [job.designs[0].id];
              });
              useCanvasStore.getState().load(job.designs[0]);
            }
            if (job.error) setError(job.error);
          }
          localStorage.removeItem(pendingKey); setPending(null);
        } else timer = setTimeout(poll, 700);
      } catch (e) {
        if (!stopped) { setError(`Response interrupted: ${errorText(e)}`); localStorage.removeItem(pendingKey); setPending(null); }
      }
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [pending?.jobId, ws]);

  async function newChat() {
    try {
      await flush();
      const next = await api.createThread(ws);
      setThreads(list => [next, ...list]); setParams({ thread: next.id });
    } catch (e) { setError(errorText(e)); }
  }
  async function switchThread(id: string) {
    try { await flush(); setParams({ thread: id }); } catch (e) { setError(errorText(e)); }
  }
  async function focus(design: Design) {
    try {
      await flush();
      setFocused(before => before.includes(design.id) ? before.filter(id => id !== design.id)
        : [...before.filter(id => designRef.current[id]?.label !== design.label), design.id]);
      useCanvasStore.getState().load(designRef.current[design.id] ?? design);
    } catch (e) { setError(errorText(e)); }
  }
  async function openEditor(design: Design) {
    try { await flush(); navigate(`/w/${ws}/editor?design=${design.id}${threadId ? `&thread=${threadId}` : ''}`); }
    catch (e) { setError(errorText(e)); }
  }
  async function upload(files: File[]) {
    const images = files.filter(f => f.type.startsWith('image/'));
    if (!images.length) { setError('Choose an image to use as a reference.'); return; }
    setUploading(true); setError('');
    try {
      for (const file of images.slice(0, 8 - attachments.length)) {
        const { asset } = await api.uploadSample(ws, file);
        setAttachments(list => [...list, asset]); setAssets(list => [...list, asset]);
      }
    } catch (e) { setError(errorText(e)); } finally { setUploading(false); }
  }
  function drop(event: DragEvent) {
    event.preventDefault(); setOver(false);
    if (!uploading && !pending) void upload([...event.dataTransfer.files]);
  }
  function paste(event: ClipboardEvent) {
    const files = [...event.clipboardData.items].filter(i => i.type.startsWith('image/')).map(i => i.getAsFile()).filter((f): f is File => !!f);
    if (files.length && !uploading && !pending) { event.preventDefault(); void upload(files); }
  }
  async function send(event?: FormEvent, override?: string) {
    event?.preventDefault();
    const messageText = override ?? text;
    if (pending || sending || uploading || (!messageText.trim() && !attachments.length)) return;
    setSending(true); setError('');
    try {
      await flush(); // The API context must see every quick preview correction before it plans this turn.
      let current = thread;
      if (!current) {
        current = await api.createThread(ws);
        setThread(current); setThreads(list => [current!, ...list]); setParams({ thread: current.id });
      }
      const draft: Pending = { threadId: current.id, text: messageText, attachmentIds: attachments.map(a => a.id) };
      setPending(draft);
      const { jobId } = await api.sendThreadMessage(current.id, { text: messageText, attachmentAssetIds: draft.attachmentIds, focusDesignIds: focused });
      const running = { ...draft, jobId }; localStorage.setItem(pendingKey, JSON.stringify(running));
      setPending(running); setText(''); setAttachments([]);
    } catch (e) { setError(errorText(e)); setPending(null); } finally { setSending(false); }
  }

  const attachedImage = (id: string) => assets.find(a => a.id === id);
  const visiblePending = pending && pending.threadId === threadId;
  return <div className="studio-shell">
    <aside className="studio-threads" aria-label="Chats">
      <div className="studio-wordmark"><span>✦</span> Studio <small>BRAND COPILOT</small></div>
      <button className="studio-new" onClick={() => void newChat()}>＋ New chat</button>
      <small className="studio-section-label">YOUR CONVERSATIONS</small>
      <nav>{threads.map(chat => <button key={chat.id} aria-current={chat.id === threadId ? 'page' : undefined} onClick={() => void switchThread(chat.id)}>
        <span>◌</span><span>{chat.title}</span>{pending?.threadId === chat.id && <i className="studio-dot" />}
      </button>)}</nav>
      <div className="studio-brand-links"><button onClick={() => setLibrary(true)}>▦ Brand library</button><Link to={`/w/${ws}/brand`}>Brand identity ↗</Link>
        <p>Your brand, built into every idea.</p></div>
    </aside>
    <section className="studio-conversation" aria-label="Studio chat">
      <header className="studio-chat-head"><div><small>DESIGN WITH YOUR BRAND</small><h1>{thread?.title ?? 'What shall we make?'}</h1></div><span className="studio-brand-status">● Brand connected</span></header>
      <div className="studio-messages" role="log" aria-label="Conversation">
        {!thread?.messages.length && !visiblePending && <div className="studio-welcome"><span>✦</span><h2>From a spark to four directions.</h2>
          <p>Drop in a reference. I’ll make four editable options in your brand. Then tell me what to change.</p>
          <div><span>01 Attach a reference</span><span>02 Explore four options</span><span>03 Make it yours</span></div>
        </div>}
        {thread?.messages.map(m => <section className={`studio-message ${m.role}`} key={m.id} data-message-id={m.id}>
          <div className="studio-message-byline">{m.role === 'assistant' ? '✦ Studio' : 'You'}<time>{new Date(m.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div>
          {m.attachmentAssetIds.length > 0 && <div className="studio-attachments">{m.attachmentAssetIds.map(id => <img key={id} src={attachedImage(id)?.url ?? `/api/files/${id}`} alt="Reference attachment" />)}</div>}
          {m.text && <p className="studio-message-text">{m.text}</p>}
          {m.steps.length > 0 && <details className="studio-completed-steps"><summary>{m.steps.length} steps completed</summary><ol>{m.steps.map((s, i) => <li key={i}>{s}</li>)}</ol></details>}
          {kit && m.designIds.length > 0 && <div className="studio-options">{m.designIds.map(id => <OptionCard key={id} id={id} designs={designs} kit={kit} focused={focused} onFocus={d => void focus(d)} onOpen={d => void openEditor(d)} />)}</div>}
        </section>)}
        {visiblePending && <>
          <section className="studio-message user"><div className="studio-message-byline">You</div>
            {pending.text && <p>{pending.text}</p>}<div className="studio-attachments">{pending.attachmentIds.map(id => <img key={id} src={`/api/files/${id}`} alt="Reference attachment" />)}</div>
          </section>
          <section className="studio-message assistant studio-pending" aria-label="Studio is working" aria-live="polite">
            <div className="studio-message-byline"><span className="studio-dot" /> Studio</div>
            <p className="studio-progress">{pending.job?.progress ?? 'Getting started…'}</p>
            <ol className="studio-live-steps">{pending.job?.steps?.map((s, i) => <li key={i}>✓ {s}</li>)}</ol>
            {kit && pending.job?.designs.length ? <div className="studio-options studio-live-options">{pending.job.designs.map(d => <OptionCard key={d.id} id={d.id} designs={designs} kit={kit} focused={focused} onFocus={d => void focus(d)} onOpen={d => void openEditor(d)} />)}</div> : null}
            <span className="studio-working">{pending.job?.designs.length ? `${pending.job.designs.length} option${pending.job.designs.length === 1 ? '' : 's'} ready — you can preview while I finish.` : 'Preparing your editable design…'}</span>
          </section>
        </>}
        <div ref={chatEnd} />
      </div>
      <div className="studio-compose-area">
        {kit?.rules.some(r => r.id === "FONT-FALLBACK") && <p className="studio-font-notice">Using DM Sans as a temporary font. <Link to={`/w/${ws}/brand`}>Set your brand font</Link></p>}
        {error && <p className="studio-error" role="alert">{error}</p>}
        {focused.length > 0 && <div className="studio-focus-chips"><span>In focus</span>{focused.map(id => <button key={id} aria-label={`Remove focus ${designs[id]?.label}`} onClick={() => setFocused(ids => ids.filter(i => i !== id))}>{designs[id]?.label} <small>v{designs[id]?.version ?? 1}</small> ×</button>)}</div>}
        <form className={`studio-composer${over ? ' drag-over' : ''}`} onSubmit={e => void send(e)} onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop} onPaste={paste}>
          {attachments.length > 0 && <div className="studio-compose-attachments">{attachments.map(a => <div key={a.id}><img src={a.url} alt={a.filename} /><button type="button" aria-label={`Remove ${a.filename}`} onClick={() => setAttachments(list => list.filter(x => x.id !== a.id))}>×</button></div>)}</div>}
          {attachments.length > 0 && !text.trim() && <div className="studio-reference-actions"><span>Choose what to make</span>
            <button type="button" disabled={!!pending || sending || uploading} onClick={() => void send(undefined, 'Clean this reference and split it into editable layers. Keep its existing layout and exact copy. Return only the layered reference, without generating new options.')}>Clean & make editable</button>
            <button type="button" disabled={!!pending || sending || uploading} onClick={() => void send()}>Create four options</button>
          </div>}
          <textarea aria-label="Message Studio" placeholder="Attach a reference, or ask for a change…" value={text} disabled={!ready || !!pending || sending} rows={2} onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
          <div className="studio-composer-tools"><button type="button" className="studio-attach" disabled={!ready || uploading || !!pending || sending} onClick={() => fileInput.current?.click()}>＋ Attach image</button>
            <input ref={fileInput} data-testid="studio-image-input" type="file" accept="image/*" multiple hidden onChange={e => { void upload([...(e.target.files ?? [])]); e.target.value = ''; }} />
            <small>{uploading ? 'Reading reference…' : 'Drop or paste an image · Shift + Enter for a new line'}</small>
            <button className="studio-send" disabled={!ready || uploading || !!pending || sending || (!text.trim() && !attachments.length)} aria-label="Send message">↑</button>
          </div>
        </form><p className="studio-compose-note">On-brand by default. Editable at every step.</p>
      </div>
    </section>
    <StudioPreview ws={ws} assets={assets} status={status} designs={designs} flush={flush} />
    {library && <div className="studio-drawer-backdrop" onClick={() => setLibrary(false)}><aside className="studio-library-drawer" aria-label="Brand library" onClick={e => e.stopPropagation()}>
      <header><h2>Brand library</h2><button onClick={() => setLibrary(false)} aria-label="Close brand library">×</button></header>
      <p>Use a name or tag in chat to bring an approved asset into your design.</p>
      <input aria-label="Search brand library" placeholder="Search assets or tags…" value={assetQuery} onChange={e => setAssetQuery(e.target.value)} />
      <div className="studio-library-assets">{assets.filter(a => a.source === 'brand_asset' && ['image', 'logo', 'icon'].includes(a.kind) && `${a.filename} ${a.caption} ${a.tags.join(' ')}`.toLowerCase().includes(assetQuery.toLowerCase())).map(a => <figure key={a.id}><img src={a.url} alt={a.caption || a.filename} /><figcaption>{a.filename}<small>{a.tags.join(' · ')}</small></figcaption></figure>)}</div>
      <div className="studio-palette">{kit?.colors.map(c => <span key={c.token} style={{ background: c.hex }} title={`${c.token} ${c.hex}`} />)}</div>
    </aside></div>}
  </div>;
}
