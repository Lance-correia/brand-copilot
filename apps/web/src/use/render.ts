import { Rect, StaticCanvas, Textbox, type FabricObject } from 'fabric';
import type { BrandKit, Design, ImageLayer, Layer, TextLayer } from '../types';
import { loadBrandFonts, fontFamily } from '../lib/fonts';

/** Fabric object -> layer id, for both the editor and offscreen renders. */
export const layerIds = new WeakMap<FabricObject, string>();

/** Matches lint's assumption for text layers without lineHeight (Fabric's own default is 1.16). */
const DEFAULT_LINE_HEIGHT = 1.2;

export const colorHex =(kit: BrandKit, token: string) => kit.colors.find(c => c.token === token)?.hex ?? '#FF00FF';

const images = new Map<string, Promise<HTMLImageElement>>();
export function loadImage(assetId: string): Promise<HTMLImageElement> {
  if (!images.has(assetId)) {
    const img = new Image();
    img.src = `/api/files/${encodeURIComponent(assetId)}`;
    images.set(assetId, img.decode().then(() => img, error => { images.delete(assetId); throw error; }));
  }
  return images.get(assetId)!;
}

/** A rect that paints an image clipped to its own box with cover or contain fit. */
export class ImageBox extends Rect {
  img?: HTMLImageElement;
  fit: ImageLayer['fit'] = 'cover';
  _render(ctx: CanvasRenderingContext2D) {
    const { width: w, height: h, img } = this;
    if (!img) return;
    const iw = img.naturalWidth || w, ih = img.naturalHeight || h;
    const s = this.fit === 'cover' ? Math.max(w / iw, h / ih) : Math.min(w / iw, h / ih);
    if (this.fit === 'cover') ctx.drawImage(img, (iw - w / s) / 2, (ih - h / s) / 2, w / s, h / s, -w / 2, -h / 2, w, h);
    else ctx.drawImage(img, -iw * s / 2, -ih * s / 2, iw * s, ih * s);
  }
}

/** A textbox at least as tall as its layer box. Text sits at the top of the box, or the middle for CTAs. */
export class BoxText extends Textbox {
  boxHeight = 0;
  middle = false;
  initDimensions() {
    super.initDimensions();
    if (this.boxHeight > this.height) this.height = this.boxHeight;
  }
  _getTopOffset() {
    return this.middle ? -Math.min(this.height, this.calcTextHeight()) / 2 : -this.height / 2;
  }
}

/** Shrinks the font in steps, down to the token's minSize, until the text fits its box. Never grows past layer.fontSize. */
function fitText(box: BoxText, layer: TextLayer, kit: BrandKit) {
  const min = Math.min(kit.fonts.find(f => f.token === layer.fontToken)?.minSize ?? 1, layer.fontSize);
  let size = layer.fontSize;
  const overflows = () => box.calcTextHeight() > layer.h || box.dynamicMinWidth > layer.w;
  while (size > min && overflows()) {
    size = Math.max(min, size - 2);
    box.set({ fontSize: size, width: layer.w });
    box.initDimensions();
  }
}

/** Builds the Fabric object for one layer: center origin, unscaled, sized to the layer box. */
export async function createLayerObject(layer: Layer, kit: BrandKit): Promise<FabricObject> {
  const base = { originX: 'center', originY: 'center', left: layer.x + layer.w / 2, top: layer.y + layer.h / 2,
    width: layer.w, height: layer.h, angle: layer.rotation, visible: layer.visible } as const;
  let obj: FabricObject;
  if (layer.type === 'text') {
    const font = kit.fonts.find(f => f.token === layer.fontToken);
    const box = new BoxText(layer.text, { ...base, fontFamily: font ? fontFamily(font) : layer.fontToken, fontSize: layer.fontSize,
      fontWeight: layer.fontWeight ?? font?.weight ?? 400, fill: colorHex(kit, layer.colorToken), textAlign: layer.align,
      lineHeight: layer.lineHeight ?? DEFAULT_LINE_HEIGHT });
    box.boxHeight = layer.h;
    box.middle = layer.role === 'cta'; // ponytail: CTA labels center in their pill; add a valign prop if other roles need it
    box.initDimensions();
    fitText(box, layer, kit);
    obj = box;
  } else if (layer.type === 'shape') {
    const ellipse = layer.shape === 'ellipse';
    const r = Math.min(layer.radius ?? 0, layer.w / 2, layer.h / 2);
    obj = new Rect({ ...base, fill: colorHex(kit, layer.fillToken), rx: ellipse ? layer.w / 2 : r, ry: ellipse ? layer.h / 2 : r });
  } else {
    const box = new ImageBox({ ...base, fill: 'transparent' });
    box.fit = layer.fit;
    box.img = await loadImage(layer.assetId).catch(() => undefined);
    obj = box;
  }
  layerIds.set(obj, layer.id);
  return obj;
}

/** Renders a design offscreen with the same code the editor uses. */
export async function renderDesign(design: Design, kit: BrandKit, scale = 1): Promise<HTMLCanvasElement> {
  await loadBrandFonts(kit);
  const el = document.createElement('canvas');
  const canvas = new StaticCanvas(el, { width: Math.max(1, Math.round(design.width * scale)), height: Math.max(1, Math.round(design.height * scale)),
    enableRetinaScaling: false, renderOnAddRemove: false, backgroundColor: colorHex(kit, design.background.colorToken) });
  canvas.setZoom(scale);
  canvas.add(...await Promise.all(design.layers.map(layer => createLayerObject(layer, kit))));
  canvas.renderAll();
  const result = document.createElement('canvas'); result.width = el.width; result.height = el.height;
  result.getContext('2d')!.drawImage(el, 0, 0);
  await canvas.dispose();
  return result;
}

/** Average relative luminance (0..1) of the design under a box, without the excluded layer. */
export async function luminanceUnder(design: Design, kit: BrandKit, box: { x: number; y: number; w: number; h: number }, excludeId?: string) {
  const scale = 240 / Math.max(design.width, design.height);
  const el = await renderDesign({ ...design, layers: design.layers.filter(l => l.id !== excludeId) }, kit, scale);
  const x = Math.max(0, Math.floor(box.x * scale)), y = Math.max(0, Math.floor(box.y * scale));
  const { data } = el.getContext('2d')!.getImageData(x, y,
    Math.max(1, Math.min(el.width - x, Math.ceil(box.w * scale))), Math.max(1, Math.min(el.height - y, Math.ceil(box.h * scale))));
  let sum = 0;
  for (let i = 0; i < data.length; i += 4) sum += (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]) / 255;
  return sum / (data.length / 4);
}
