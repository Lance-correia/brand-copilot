import { create } from 'zustand';
import type { BrandKit, Design, EditOp, Layer } from '../types';
import { validateDesign, validateEditOp } from './validation';

const HISTORY_LIMIT = 50;

/** One undoable step: the ops as applied and the ops that reverse them. */
interface HistoryEntry { ops: EditOp[]; inverse: EditOp[] }

interface CanvasState {
  design: Design | null;
  selection: string[];
  proposal: { ops: EditOp[]; before: Design } | null;
  kit: BrandKit | null;
  past: HistoryEntry[];
  future: HistoryEntry[];
  load(design: Design): void;
  setKit(kit: BrandKit | null): void;
  select(ids: string[]): void;
  applyOps(ops: EditOp[], opts?: { proposal?: boolean }): void;
  acceptProposal(): void;
  rejectProposal(): void;
  undo(): void;
  redo(): void;
}

/** Layer ids an op touches; used for proposal outlines. */
export function touchedLayerIds(ops: EditOp[]): string[] {
  return ops.flatMap(op => op.op === 'add_layer' ? [op.layer.id] : op.op === 'set_background' ? [] : [op.layerId]);
}

function unknownToken(op: EditOp, kit: BrandKit | null): string | undefined {
  if (!kit) return;
  const colors = new Set(kit.colors.map(c => c.token));
  const fonts = new Set(kit.fonts.map(f => f.token));
  const props = (op.op === 'add_layer' ? op.layer : op.op === 'update_layer' ? op.props
    : op.op === 'set_background' ? op.background : {}) as Record<string, unknown>;
  for (const key of ['colorToken', 'fillToken'] as const) {
    const token = props[key];
    if (typeof token === 'string' && !colors.has(token)) return token;
  }
  if (typeof props.fontToken === 'string' && !fonts.has(props.fontToken)) return props.fontToken;
}

/**
 * Applies one op immutably: untouched layers keep their object identity, which is
 * how the canvas knows what to re-render. Returns the new design and the inverse op.
 */
function applyOp(design: Design, op: EditOp): { design: Design; inverse: EditOp | null } {
  const layers = design.layers;
  const index = op.op === 'add_layer' || op.op === 'set_background' ? -1 : layers.findIndex(l => l.id === op.layerId);
  if (op.op !== 'add_layer' && op.op !== 'set_background' && index < 0) throw new Error(`missing layer ${op.layerId}`);
  switch (op.op) {
    case 'add_layer': {
      if (layers.some(l => l.id === op.layer.id)) throw new Error(`duplicate layer ${op.layer.id}`);
      const at = Math.max(0, Math.min(op.index ?? layers.length, layers.length));
      const next = [...layers];
      next.splice(at, 0, structuredClone(op.layer));
      return { design: { ...design, layers: next }, inverse: { op: 'remove_layer', layerId: op.layer.id } };
    }
    case 'remove_layer':
      return { design: { ...design, layers: layers.filter((_, i) => i !== index) },
        inverse: { op: 'add_layer', layer: layers[index], index } };
    case 'reorder_layer': {
      const next = [...layers];
      const [layer] = next.splice(index, 1);
      next.splice(Math.max(0, Math.min(op.index, next.length)), 0, layer);
      return { design: { ...design, layers: next }, inverse: { op: 'reorder_layer', layerId: op.layerId, index } };
    }
    case 'update_layer': {
      const old = layers[index] as unknown as Record<string, unknown>;
      const layer: Record<string, unknown> = { ...old };
      const before: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(op.props)) {
        if (old[key] === value) continue;
        before[key] = old[key];
        if (value === undefined) delete layer[key]; else layer[key] = value;
      }
      if (!Object.keys(before).length) return { design, inverse: null }; // no-op, e.g. a click without a drag
      return { design: { ...design, layers: layers.map((l, i) => i === index ? layer as unknown as Layer : l) },
        inverse: { op: 'update_layer', layerId: op.layerId, props: before } };
    }
    case 'replace_image': {
      const old = layers[index];
      if (old.type !== 'image') throw new Error(`layer ${op.layerId} is not an image`);
      if (old.assetId === op.assetId && old.source === op.source) return { design, inverse: null };
      return { design: { ...design, layers: layers.map((l, i) => i === index ? { ...old, assetId: op.assetId, source: op.source } : l) },
        inverse: { op: 'replace_image', layerId: op.layerId, assetId: old.assetId, source: old.source } };
    }
    case 'set_background':
      return { design: { ...design, background: { ...op.background } },
        inverse: { op: 'set_background', background: design.background } };
  }
}

/** Applies ops one at a time, skipping (with a warning) any that are invalid. */
function applyAll(design: Design, ops: EditOp[], kit: BrandKit | null, validate: boolean) {
  const applied: EditOp[] = [];
  const inverse: EditOp[] = [];
  for (const op of ops) {
    try {
      if (validate) validateEditOp(op);
      const token = unknownToken(op, kit);
      if (token) throw new Error(`unknown token ${token}`);
      const result = applyOp(design, op);
      if (!result.inverse) continue;
      if (validate) validateDesign(result.design);
      design = result.design;
      applied.push(op);
      inverse.unshift(result.inverse);
    } catch (error) {
      console.warn('Ignoring invalid op', op, error instanceof Error ? error.message : error);
    }
  }
  return { design, entry: { ops: applied, inverse } };
}

const pushEntry = (past: HistoryEntry[], entry: HistoryEntry) => [...past, entry].slice(-HISTORY_LIMIT);

export const useCanvasStore = create<CanvasState>((set, get) => ({
  design: null, selection: [], proposal: null, kit: null, past: [], future: [],
  load(design) {
    validateDesign(design);
    set({ design: structuredClone(design), selection: [], proposal: null, past: [], future: [] });
  },
  setKit(kit) { set({ kit }); },
  select(ids) { set({ selection: ids }); },
  applyOps(ops, opts) {
    if (get().proposal) get().acceptProposal();
    const { design, kit, past, selection } = get();
    if (!design) throw new Error('Load a design before applying ops');
    const result = applyAll(design, ops, kit, true);
    if (!result.entry.ops.length) return;
    const ids = new Set(result.design.layers.map(l => l.id));
    const kept = selection.filter(id => ids.has(id));
    if (opts?.proposal) set({ design: result.design, selection: kept, proposal: { ops: result.entry.ops, before: design } });
    else set({ design: result.design, selection: kept, past: pushEntry(past, result.entry), future: [] });
  },
  acceptProposal() {
    const { proposal, design, kit, past } = get();
    if (!proposal || !design) return;
    // Recompute inverses against the pre-proposal design so undo reverses the whole proposal.
    const { entry } = applyAll(proposal.before, proposal.ops, kit, false);
    set({ proposal: null, past: pushEntry(past, entry), future: [] });
  },
  rejectProposal() {
    const { proposal } = get();
    if (proposal) set({ design: proposal.before, proposal: null });
  },
  undo() {
    if (get().proposal) return get().rejectProposal();
    const { past, future, design, kit } = get();
    const entry = past.at(-1);
    if (!design || !entry) return;
    set({ design: applyAll(design, entry.inverse, kit, false).design, past: past.slice(0, -1), future: [entry, ...future] });
  },
  redo() {
    if (get().proposal) return;
    const { past, future, design, kit } = get();
    const [entry, ...rest] = future;
    if (!design || !entry) return;
    set({ design: applyAll(design, entry.ops, kit, false).design, past: [...past, entry], future: rest });
  },
}));
