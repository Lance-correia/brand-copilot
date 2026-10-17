import { createElement } from 'react';
import { useParams } from 'react-router';
import { useCanvasStore } from '../use/canvasStore';

function usePlaceholder(name: string) {
  const { id } = useParams();
  const design = useCanvasStore(state => state.design);
  return createElement('section', { 'data-workspace': id, 'data-design': design?.id }, `${name} placeholder — Prompt 1`);
}
export function StartModal() { return usePlaceholder('Start'); }
export function VariantsGrid() { return usePlaceholder('Variants'); }
export function CopilotPanel() { return usePlaceholder('Copilot'); }
export function LintPanel() { return usePlaceholder('Lint'); }
