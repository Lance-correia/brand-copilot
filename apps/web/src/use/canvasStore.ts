import { create } from 'zustand';
import type { Design, EditOp } from '../types';
import { validateDesign, validateEditOp } from './validation';

interface CanvasState {
  design: Design | null;
  selection: string[];
  proposal: { ops: EditOp[]; before: Design } | null;
  past: Design[];
  future: Design[];
  load(design: Design): void;
  applyOps(ops: EditOp[], opts?: { proposal?: boolean }): void;
  acceptProposal(): void;
  rejectProposal(): void;
  undo(): void;
  redo(): void;
}

export const useCanvasStore = create<CanvasState>((set, get) => ({
  design: null, selection: [], proposal: null, past: [], future: [],
  load(design) {
    validateDesign(design);
    set({ design: structuredClone(design), selection: [], proposal: null, past: [], future: [] });
  },
  applyOps(ops, opts) {
    const state = get();
    if (!state.design) throw new Error('Load a design before applying ops');
    const design = structuredClone(state.design);
    for (const op of ops) {
      validateEditOp(op);
      if (op.op !== 'update_layer') throw new Error(`Scaffold only supports update_layer; Prompt 2 implements ${op.op}`);
      const layer = design.layers.find(layer => layer.id === op.layerId);
      if (!layer) throw new Error(`Unknown layer ${op.layerId}`);
      Object.assign(layer, op.props);
    }
    validateDesign(design);
    set({ design, past: [...state.past, structuredClone(state.design)], future: [],
      proposal: opts?.proposal ? { ops: structuredClone(ops), before: structuredClone(state.design) } : null });
  },
  acceptProposal() { set({ proposal: null }); },
  rejectProposal() {
    const { proposal, past } = get();
    if (proposal) set({ design: structuredClone(proposal.before), proposal: null, past: past.slice(0, -1), future: [] });
  },
  undo() {
    const { past, future, design } = get();
    if (design && past.length) set({ design: past[past.length - 1], past: past.slice(0, -1), future: [design, ...future], proposal: null });
  },
  redo() {
    const { past, future, design } = get();
    if (design && future.length) set({ design: future[0], past: [...past, design], future: future.slice(1), proposal: null });
  },
}));
