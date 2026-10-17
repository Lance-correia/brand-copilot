import { cache } from 'fabric';
import type { BrandKit } from '../types';

const loaded = new Map<string, Promise<void>>();

/** Registers each brand font as a FontFace whose family name is its token (for example `headline`). */
export async function loadBrandFonts(kit: BrandKit): Promise<void> {
  await Promise.all(kit.fonts.map(font => {
    const key = `${font.token}:${font.assetId}`;
    if (!loaded.has(key)) {
      const face = new FontFace(font.token, `url(/api/files/${encodeURIComponent(font.assetId)})`, { weight: String(font.weight) });
      loaded.set(key, face.load().then(() => { document.fonts.add(face); cache.clearFontCache(font.token); },
        error => { loaded.delete(key); console.warn(`Font ${font.token} failed to load`, error); }));
    }
    return loaded.get(key);
  }));
}
