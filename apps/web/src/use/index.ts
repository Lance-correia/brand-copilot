import type { BrandKit, Design } from '../types';
export { useCanvasStore } from './canvasStore';

/** Placeholder thumbnail; Prompt 2 replaces this with full scene rendering. */
export async function renderThumbnail(design: Design, kit: BrandKit, maxSize = 256): Promise<string> {
  const canvas = document.createElement('canvas');
  const scale = Math.min(maxSize / design.width, maxSize / design.height);
  canvas.width = Math.max(1, Math.round(design.width * scale));
  canvas.height = Math.max(1, Math.round(design.height * scale));
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas is unavailable');
  context.fillStyle = kit.colors.find(color => color.token === design.background.colorToken)?.hex ?? '#FBF7F2';
  context.fillRect(0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/png');
}
