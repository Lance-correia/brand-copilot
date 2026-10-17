import { cache } from 'fabric';
import type { BrandKit, FontToken } from '../types';

const loaded = new Map<string, Promise<void>>();

export const fontFamily = (font: FontToken) => `brand_${font.assetId}_${font.weight}`;

/** Asset-specific font families prevent another workspace's font from replacing this one. */
export async function loadBrandFonts(kit: BrandKit): Promise<void> {
  await Promise.all(kit.fonts.map(font => {
    const key = `${font.token}:${font.assetId}`;
    if (!loaded.has(key)) {
      const family = fontFamily(font);
      const face = new FontFace(family, `url(/api/files/${encodeURIComponent(font.assetId)})`, { weight: String(font.weight) });
      loaded.set(key, face.load().then(() => { document.fonts.add(face); cache.clearFontCache(family); },
        error => { loaded.delete(key); throw new Error(`Could not load ${font.family}. Check your brand font file.`, { cause: error }); }));
    }
    return loaded.get(key);
  }));
}
