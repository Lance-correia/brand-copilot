import type { BrandKit, Design } from '../types';
import { renderDesign } from './render';
export { useCanvasStore } from './canvasStore';

/** PNG data URL of the design, longest side at most maxSize, rendered with the editor's code. */
export async function renderThumbnail(design: Design, kit: BrandKit, maxSize = 360): Promise<string> {
  const scale = Math.min(1, maxSize / Math.max(design.width, design.height));
  return (await renderDesign(design, kit, scale)).toDataURL('image/png');
}
