import { useEffect, useRef } from 'react';
import { Canvas, util, type FabricObject, type TPointerEvent } from 'fabric';
import type { BrandKit, Design, Layer } from '../types';
import { touchedLayerIds, useCanvasStore } from './canvasStore';
import { BoxText, colorHex, createLayerObject, layerIds } from './render';

const round = (n: number) => Math.round(n * 100) / 100;

function setInteractivity(obj: FabricObject, layer: Layer, textOnly = false) {
  const locked = layer.locked;
  obj.set({ evented: layer.visible && (!textOnly || layer.type === 'text'), hasControls: !locked && !textOnly, lockMovementX: locked || textOnly, lockMovementY: locked || textOnly,
    lockScalingX: locked || textOnly, lockScalingY: locked || textOnly, lockRotation: locked || textOnly, hoverCursor: locked ? 'default' : 'move' });
  if (obj instanceof BoxText) obj.editable = !locked;
}

interface Props {
  zoom: number;
  textOnly?: boolean;
  onDropAsset(assetId: string, point: { x: number; y: number }): void;
}

/** The interactive Fabric canvas. It mirrors the store and turns user gestures into ops. */
export function CanvasView({ zoom, onDropAsset, textOnly = false }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<Canvas | null>(null);
  const design = useCanvasStore(s => s.design)!;

  useEffect(() => {
    // A fresh element per mount: StrictMode remounts before Fabric's async dispose finishes.
    const el = document.createElement('canvas');
    hostRef.current!.appendChild(el);
    const canvas = new Canvas(el, { preserveObjectStacking: true, selection: false, renderOnAddRemove: false });
    canvasRef.current = canvas;
    const store = useCanvasStore;
    const objects = new Map<string, FabricObject>();
    const rendered = new Map<string, { layer: Layer; kit: BrandKit }>();
    let disposed = false;
    let quiet = false; // set while we change the selection ourselves, so canvas events don't echo back
    const layerOf = (id: string) => store.getState().design?.layers.find(l => l.id === id);

    async function sync() {
      const { design, kit } = store.getState();
      if (disposed || !design || !kit) return;
      canvas.backgroundColor = colorHex(kit, design.background.colorToken);
      const ids = new Set(design.layers.map(l => l.id));
      for (const [id, obj] of objects) if (!ids.has(id)) { canvas.remove(obj); objects.delete(id); rendered.delete(id); }
      await Promise.all(design.layers.map(async layer => {
        const prev = rendered.get(layer.id);
        if (prev?.layer === layer && prev.kit === kit) return; // untouched by any op
        const entry = { layer, kit };
        rendered.set(layer.id, entry);
        const obj = await createLayerObject(layer, kit);
        if (disposed || rendered.get(layer.id) !== entry) return; // superseded while loading
        setInteractivity(obj, layer, textOnly);
        const old = objects.get(layer.id);
        quiet = true;
        const wasActive = !!old && canvas.getActiveObject() === old;
        if (old) canvas.remove(old);
        canvas.add(obj);
        objects.set(layer.id, obj);
        if (wasActive) canvas.setActiveObject(obj);
        quiet = false;
      }));
      if (disposed) return;
      // Stacking follows the current layer order, whichever sync finishes last.
      store.getState().design?.layers.forEach((l, i) => { const obj = objects.get(l.id); if (obj) canvas.moveObjectTo(obj, i); });
      syncSelection();
    }

    function syncSelection() {
      const id = store.getState().selection[0];
      const obj = id ? objects.get(id) : undefined;
      quiet = true;
      if (obj && obj.visible && canvas.getActiveObject() !== obj) canvas.setActiveObject(obj);
      if (!obj && canvas.getActiveObject()) canvas.discardActiveObject();
      quiet = false;
      canvas.requestRenderAll();
    }

    const select = () => { if (!quiet) store.getState().select(canvas.getActiveObjects().map(o => layerIds.get(o)!).filter(Boolean)); };
    canvas.on('selection:created', select);
    canvas.on('selection:updated', select);
    canvas.on('selection:cleared', select);

    canvas.on('object:modified', ({ target }) => {
      const id = layerIds.get(target);
      const layer = id && layerOf(id);
      if (!id || !layer) return;
      const { translateX, translateY, angle, scaleX, scaleY } = util.qrDecompose(target.calcTransformMatrix());
      const w = Math.max(1, round(target.width * scaleX));
      const h = Math.max(1, round((target instanceof BoxText ? target.boxHeight : target.height) * scaleY));
      const before = store.getState().design;
      store.getState().applyOps([{ op: 'update_layer', layerId: id,
        props: { x: round(translateX - w / 2), y: round(translateY - h / 2), w, h, rotation: round(angle) } }]);
      if (store.getState().design === before) { rendered.delete(id); void sync(); } // op rejected: snap back
    });

    canvas.on('text:editing:exited', ({ target }) => {
      const id = layerIds.get(target);
      const layer = id ? layerOf(id) : undefined;
      if (id && layer?.type === 'text' && target.text !== layer.text)
        store.getState().applyOps([{ op: 'update_layer', layerId: id, props: { text: target.text } }]);
    });

    canvas.on('after:render', ({ ctx }) => {
      const { proposal } = store.getState();
      if (!proposal) return;
      ctx.save();
      ctx.strokeStyle = '#7C3AED';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      for (const id of touchedLayerIds(proposal.ops)) {
        const obj = objects.get(id);
        if (!obj) continue;
        const points = obj.getCoords().map(p => util.transformPoint(p, canvas.viewportTransform));
        ctx.beginPath();
        points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
        ctx.closePath();
        ctx.stroke();
      }
      ctx.restore();
    });

    // Fabric keeps its hidden textarea active when a toolbar or panel takes focus.
    // Finish the edit before those controls read or change the layer in the store.
    function finishExternalEdit(event: PointerEvent) {
      if (event.target instanceof Node && !hostRef.current?.contains(event.target)) {
        const active = canvas.getActiveObject();
        if (active instanceof BoxText && active.isEditing) active.exitEditing();
      }
    }
    document.addEventListener('pointerdown', finishExternalEdit, true);

    void sync();
    const unsubscribe = store.subscribe((s, prev) => {
      if (s.design !== prev.design || s.kit !== prev.kit) void sync();
      else if (s.selection !== prev.selection) syncSelection();
      else if (s.proposal !== prev.proposal) canvas.requestRenderAll();
    });
    return () => { disposed = true; document.removeEventListener('pointerdown', finishExternalEdit, true); unsubscribe(); canvasRef.current = null; void canvas.dispose().then(() => el.remove()); };
  }, [textOnly]);

  useEffect(() => {
    const canvas = canvasRef.current!;
    canvas.setDimensions({ width: Math.round(design.width * zoom), height: Math.round(design.height * zoom) });
    canvas.setZoom(zoom);
    canvas.requestRenderAll();
  }, [zoom, design.width, design.height]);

  function onDrop(event: React.DragEvent) {
    const assetId = event.dataTransfer.getData('application/x-brand-asset');
    if (textOnly || !assetId || !canvasRef.current) return;
    event.preventDefault();
    const p = canvasRef.current.getScenePoint(event.nativeEvent as unknown as TPointerEvent);
    onDropAsset(assetId, { x: p.x, y: p.y });
  }

  return <div className="use-canvas-frame" onDragOver={e => e.preventDefault()} onDrop={onDrop} ref={hostRef} />;
}
