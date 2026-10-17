import { useEffect, useRef, useState, type FormEvent } from 'react';
import { chat } from '../api/client';
import { useCanvasStore } from '../use';
import { errorText, useWorkspaceId } from './shared';

type Message = { role: 'user' | 'assistant' | 'error'; text: string };

export function CopilotPanel() {
  const ws = useWorkspaceId();
  const design = useCanvasStore(s => s.design);
  const selection = useCanvasStore(s => s.selection);
  const proposal = useCanvasStore(s => s.proposal);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const log = useRef<HTMLOListElement>(null);

  useEffect(() => setMessages([]), [design?.id]);
  useEffect(() => { log.current?.scrollTo(0, log.current.scrollHeight); }, [messages]);

  const push = (m: Message) => setMessages(current => [...current, m]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!design || !message) return;
    push({ role: 'user', text: message }); setInput(''); setBusy(true);
    try {
      const { reply, ops } = await chat(ws, { design, selection, message });
      push({ role: 'assistant', text: reply });
      if (ops.length) {
        try { useCanvasStore.getState().applyOps(ops, { proposal: true }); }
        catch (e) { push({ role: 'error', text: `Could not apply the proposal: ${errorText(e)}` }); }
      }
    } catch (e) {
      push({ role: 'error', text: errorText(e) });
    } finally { setBusy(false); }
  }

  if (!design) return null;
  return <section className="panel copilot">
    <h2>Copilot</h2>
    <ol className="chat" ref={log} aria-live="polite">
      {messages.length === 0 && <li className="muted">Ask for a change, e.g. “make the headline shorter”.</li>}
      {messages.map((m, i) => <li key={i} className={`msg ${m.role}`}>{m.text}</li>)}
      {busy && <li className="msg assistant muted"><span className="spinner" aria-hidden="true" /> Thinking…</li>}
    </ol>
    {proposal && <div className="proposal" role="status">
      <span>{proposal.ops.length} proposed change{proposal.ops.length === 1 ? '' : 's'} on canvas</span>
      <button className="primary" onClick={() => useCanvasStore.getState().acceptProposal()}>Accept</button>
      <button onClick={() => useCanvasStore.getState().rejectProposal()}>Reject</button>
    </div>}
    <form className="chat-input" onSubmit={send}>
      <input aria-label="Message the copilot" value={input} onChange={e => setInput(e.target.value)} disabled={busy || !!proposal}
        placeholder={proposal ? 'Accept or reject the proposal first' : selection.length ? `About ${selection.length} selected layer(s)…` : 'About the whole design…'} />
      <button className="primary" disabled={busy || !!proposal || !input.trim()} title="Sends your message to the AI model">AI</button>
    </form>
  </section>;
}
