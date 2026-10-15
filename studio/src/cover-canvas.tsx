import { useLayoutEffect, useRef, useState } from 'react';
import {
  VIEWS,
  contains,
  dragFocal,
  layerBoxes,
  layerName,
  panelOf,
  round,
  viewBox,
  type View,
} from './cover-model';
import { elementOf, isPhotoLayer, movable } from './cover-elements-model';
import type { CoverConfig, CoverLayoutView, PtBox } from './types';

// The cover canvas: a PDFium raster of the real cover PDF with an SVG layer of
// Python's measured text boxes. Selecting and dragging edit authored offsets; the
// preview updates when Python has laid out and rendered the draft again.

export const OVERLAYS = [
  ['trim', 'Trim and folds', 'Final size and the two spine folds'],
  ['bleed', 'Bleed', '0.125 in printed beyond the trim, cut away'],
  ['safe', 'KDP safe areas', 'Text 0.125 in inside trim and folds; spine 0.0625 in'],
  ['design', 'Type area', 'PuzzlePress keeps type 0.5 in from panel edges'],
  ['barcode', 'Barcode area', 'Lower-right back corner reserved for KDP'],
  ['text', 'Text bounds', 'Measured extent of every line'],
  ['regions', 'Region boundaries', 'Back, spine and front as the interior sizes them'],
] as const;
export type Overlay = (typeof OVERLAYS)[number][0];
export const ZOOMS = [1, 1.5, 2, 3, 4] as const;
// Layout-independent fallbacks for keys whose `key` value varies by keyboard.
const KEY_CODES: Record<string, string> = {
  Equal: '=',
  NumpadAdd: '+',
  Minus: '-',
  NumpadSubtract: '-',
  Digit0: '0',
  Numpad0: '0',
};
const SNAP = 6; // Screen pixels.

function Rect({ box, className }: { box: PtBox; className: string }) {
  return (
    <rect
      className={className}
      x={box.x}
      y={-(box.y + box.height)}
      width={box.width}
      height={box.height}
      vectorEffect="non-scaling-stroke"
    />
  );
}

function Overlays({ layout, overlays }: { layout: CoverLayoutView; overlays: Set<Overlay> }) {
  const r = layout.geometry.regions;
  const m = r.media;
  return (
    <g data-testid="cover-overlay">
      {overlays.has('bleed') && (
        <path
          className="overlay-bleed"
          fillRule="evenodd"
          d={`M${m.x},${-m.y} H${m.x + m.width} V${-(m.y + m.height)} H${m.x} Z M${r.trim.x},${-r.trim.y} V${-(r.trim.y + r.trim.height)} H${r.trim.x + r.trim.width} V${-r.trim.y} Z`}
        />
      )}
      {overlays.has('trim') && (
        <>
          <Rect box={r.trim} className="overlay-trim" />
          {[r.spine.x, r.spine.x + r.spine.width].map((x) => (
            <line
              key={x}
              className="overlay-fold"
              x1={x}
              x2={x}
              y1={-m.height}
              y2={0}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </>
      )}
      {overlays.has('safe') &&
        (['front_safe', 'back_safe', 'spine_safe'] as const).map((k) => (
          <Rect key={k} box={r[k]} className="overlay-kdp" />
        ))}
      {overlays.has('design') &&
        (['front_design', 'back_design'] as const).map((k) => (
          <Rect key={k} box={r[k]} className="overlay-live" />
        ))}
      {overlays.has('barcode') && (
        <>
          <Rect box={r.barcode_keep_clear} className="overlay-barcode-zone" />
          <Rect box={r.barcode} className="overlay-barcode" />
        </>
      )}
      {overlays.has('text') &&
        layout.texts.map((t, i) => <Rect key={i} box={t.box} className="overlay-element" />)}
      {overlays.has('regions') &&
        layout.regions &&
        (['back', 'spine', 'front'] as const).map((key) => (
          <Rect key={key} box={layout.regions![key].area} className="overlay-region" />
        ))}
      {overlays.has('regions') &&
        (layout.elements ?? []).map((e) => (
          <Rect key={e.role} box={e.bounds} className="overlay-element" />
        ))}
    </g>
  );
}

function useSize() {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 720, height: 480 });
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () =>
      setSize({ width: element.clientWidth || 720, height: element.clientHeight || 480 });
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, size] as const;
}

type Drag = {
  kind: 'photo' | 'layer' | 'element';
  layer: string;
  x: number;
  y: number;
  dx: number;
  dy: number;
  moved: boolean;
};

export function CoverCanvas({
  projectKey,
  layout,
  cover,
  pdf,
  scales,
  label,
  view,
  zoom,
  overlays,
  interactive,
  selected,
  flagged,
  onSelect,
  onCrop,
  onNudgeCrop,
  onMoveLayer,
  onMoveElement,
  onAnnounce,
  fitWidth = false,
}: {
  projectKey: string;
  layout: CoverLayoutView;
  cover: CoverConfig;
  pdf: string;
  scales: Record<string, number>;
  label: string;
  view: View;
  zoom: number;
  overlays: Set<Overlay>;
  interactive: boolean;
  selected: string | null;
  flagged: Set<string>;
  onSelect: (layer: string | null) => void;
  onCrop: (layer: string, focal: { x: number; y: number }) => void;
  onNudgeCrop: (key: string, big: boolean) => boolean;
  onMoveLayer: (layer: string, delta: { x: number; y: number }) => void;
  onMoveElement?: (layer: string, delta: { x: number; y: number }) => void;
  onAnnounce: (message: string) => void;
  // Phones: fit the width and let the canvas take the cover's own height.
  fitWidth?: boolean;
}) {
  const [frame, size] = useSize();
  const [drag, setDrag] = useState<Drag | null>(null);
  const g = layout.geometry;
  const box = viewBox(g, view);
  const fit = Math.max(
    0.05,
    fitWidth
      ? (size.width - 24) / box.width
      : Math.min((size.width - 24) / box.width, (size.height - 24) / box.height),
  );
  const scale = fit * zoom;
  const dpr = typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1;
  const raster = scale * dpr <= scales.preview * 1.05 ? 'preview' : 'detail';
  const src = `/api/projects/${encodeURIComponent(projectKey)}/cover/preview?size=${raster}&pdf=${pdf}`;
  const media = g.regions.media;
  const boxes = layerBoxes(layout);
  const viewName = VIEWS.find(([v]) => v === view)![1].toLowerCase();
  const textSelected = selected !== null && selected !== 'photo' && boxes.has(selected);
  const photoSelected = isPhotoLayer(cover, selected);
  const elements = layout.elements ?? [];
  const elementBoxes = new Map(elements.map((e) => [e.layer, e.bounds]));
  const chosen = elementOf(cover, selected);
  const elementSelected = chosen !== undefined && chosen.type !== 'photo';
  const photoDrag = drag?.kind === 'photo' && drag.moved && drag.layer === 'photo';

  // The dragged layer's box in points, with snapping to its panel's centre lines.
  let ghost: PtBox | null = null;
  const guides: { x?: number; y?: number } = {};
  let outside = false;
  if ((drag?.kind === 'layer' || drag?.kind === 'element') && drag.moved) {
    const isElement = drag.kind === 'element';
    const original = (isElement ? elementBoxes : boxes).get(drag.layer)!;
    const region = isElement ? elementOf(cover, drag.layer)?.region : undefined;
    const panel = region ? (region === 'wrap' ? 'front' : region) : panelOf(drag.layer, cover);
    const area =
      isElement && region && layout.regions
        ? layout.regions[region].area
        : panel === 'spine'
          ? g.regions.spine_safe
          : g.regions[`${panel}_design`];
    let dx = drag.dx / scale;
    let dy = -drag.dy / scale;
    const cx = original.x + original.width / 2 + dx;
    const cy = original.y + original.height / 2 + dy;
    const ax = area.x + area.width / 2;
    const ay = area.y + area.height / 2;
    if (Math.abs(cx - ax) * scale < SNAP) {
      dx = ax - (original.x + original.width / 2);
      guides.x = ax;
    }
    if (Math.abs(cy - ay) * scale < SNAP) {
      dy = ay - (original.y + original.height / 2);
      guides.y = ay;
    }
    ghost = { ...original, x: original.x + dx, y: original.y + dy };
    const safe =
      panel === 'spine'
        ? g.regions.spine_safe
        : g.regions[panel === 'back' ? 'back_safe' : 'front_safe'];
    outside = !contains(safe, ghost);
  }

  const finishDrag = () => {
    if (!drag) return;
    if (drag.moved && drag.kind === 'photo')
      onCrop(drag.layer, dragFocal(layout, drag.dx, drag.dy, scale, drag.layer));
    if (drag.moved && (drag.kind === 'layer' || drag.kind === 'element') && ghost) {
      const original = (drag.kind === 'element' ? elementBoxes : boxes).get(drag.layer)!;
      // Snapped ghost position minus the measured box: the change in points.
      const delta = { x: round(ghost.x - original.x, 2), y: round(ghost.y - original.y, 2) };
      if (drag.kind === 'element') onMoveElement?.(drag.layer, delta);
      else onMoveLayer(drag.layer, delta);
      onAnnounce(
        `${layerName(cover, drag.layer)} moved ${delta.x} pt across and ${delta.y} pt up${
          outside ? '; it is outside the safe area' : ''
        }.`,
      );
    }
    setDrag(null);
  };

  const help = !interactive
    ? ''
    : elementSelected
      ? chosen!.locked
        ? `${layerName(cover, selected!)} is locked; unlock it in Layers or Properties to move it.`
        : `${layerName(cover, selected!)} selected. Drag it, or use arrow keys to move it by 1 point (Shift for 10). Escape cancels a drag or clears the selection.`
      : textSelected
        ? `${layerName(cover, selected!)} selected. Drag it, or use arrow keys to move it by 1 point (Shift for 10). Escape clears the selection.`
        : photoSelected
          ? `${layerName(cover, selected!)} selected. Drag to move the picture inside its frame; arrow keys move the focal point (Shift for larger steps); plus and minus zoom; 0 resets the crop.`
          : 'Select a layer or a photograph to edit it.';
  return (
    <div
      className={`cover-canvas${drag ? ' dragging' : ''}${selected === 'photo' ? ' photo-selected' : ''}`}
      ref={frame}
      tabIndex={0}
      role="group"
      aria-roledescription="cover canvas"
      aria-label={`${label}, ${viewName} view. ${help}`}
      onKeyDown={(event) => {
        if (!interactive) return;
        if (event.key === 'Escape') {
          if (drag) setDrag(null);
          else onSelect(null);
          event.preventDefault();
          return;
        }
        if ((textSelected || elementSelected) && event.key.startsWith('Arrow')) {
          const step = event.shiftKey ? 10 : 1;
          const delta = {
            ArrowLeft: { x: -step, y: 0 },
            ArrowRight: { x: step, y: 0 },
            ArrowUp: { x: 0, y: step },
            ArrowDown: { x: 0, y: -step },
          }[event.key];
          if (delta) {
            if (elementSelected) onMoveElement?.(selected!, delta);
            else onMoveLayer(selected!, delta);
            event.preventDefault();
          }
          return;
        }
        if (photoSelected) {
          const known = ['+', '=', '-', '0'].includes(event.key) || event.key.startsWith('Arrow');
          const key = known ? event.key : (KEY_CODES[event.code] ?? event.key);
          if (onNudgeCrop(key, event.shiftKey)) event.preventDefault();
        }
      }}
      onPointerDown={(event) => {
        if (!interactive || event.button !== 0) return;
        const target = event.target as Element;
        const layer = target.getAttribute?.('data-layer');
        event.currentTarget.focus();
        const element = layer ? elementOf(cover, layer) : undefined;
        if (element?.type === 'photo') {
          if (selected !== layer) {
            onSelect(layer);
            return;
          }
          event.currentTarget.setPointerCapture?.(event.pointerId);
          setDrag({
            kind: 'photo',
            layer: layer!,
            x: event.clientX,
            y: event.clientY,
            dx: 0,
            dy: 0,
            moved: false,
          });
          return;
        }
        if (element) {
          onSelect(layer);
          if (element.locked || !movable(element)) return;
          event.currentTarget.setPointerCapture?.(event.pointerId);
          setDrag({
            kind: 'element',
            layer: layer!,
            x: event.clientX,
            y: event.clientY,
            dx: 0,
            dy: 0,
            moved: false,
          });
          return;
        }
        if (layer) {
          onSelect(layer);
          event.currentTarget.setPointerCapture?.(event.pointerId);
          setDrag({
            kind: 'layer',
            layer,
            x: event.clientX,
            y: event.clientY,
            dx: 0,
            dy: 0,
            moved: false,
          });
          return;
        }
        if (!cover.image) {
          onSelect(null); // A region design: empty canvas clears the selection.
          return;
        }
        if (selected !== 'photo') {
          // A first click selects the photograph; it never drags the cover by accident.
          onSelect(textSelected ? null : 'photo');
          return;
        }
        event.currentTarget.setPointerCapture?.(event.pointerId);
        setDrag({
          kind: 'photo',
          layer: 'photo',
          x: event.clientX,
          y: event.clientY,
          dx: 0,
          dy: 0,
          moved: false,
        });
      }}
      onPointerMove={(event) => {
        if (!drag) return;
        const dx = event.clientX - drag.x;
        const dy = event.clientY - drag.y;
        setDrag({ ...drag, dx, dy, moved: drag.moved || Math.abs(dx) > 2 || Math.abs(dy) > 2 });
      }}
      onPointerUp={finishDrag}
      onPointerCancel={() => setDrag(null)}
    >
      <div
        className="cover-window"
        style={{ width: box.width * scale, height: box.height * scale }}
      >
        <img
          src={src}
          alt={`${label}: ${viewName} view of the rendered cover PDF`}
          draggable={false}
          width={Math.round(media.width * scale)}
          height={Math.round(media.height * scale)}
          style={{
            left: -box.x * scale,
            top: -(media.height - (box.y + box.height)) * scale,
            transform: photoDrag ? `translate(${drag!.dx}px, ${drag!.dy}px)` : undefined,
          }}
        />
        <svg
          className="cover-overlay"
          viewBox={`${box.x} ${-(box.y + box.height)} ${box.width} ${box.height}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {overlays.size > 0 && !drag && <Overlays layout={layout} overlays={overlays} />}
          {interactive &&
            elements
              .filter((e) => e.kind !== 'text')
              .map((e) => (
                <rect
                  key={e.layer}
                  data-layer={e.layer}
                  className={`layer-hit element-hit${e.layer === selected ? ' selected' : ''}${
                    flagged.has(e.layer) ? ' flagged' : ''
                  }`}
                  x={e.bounds.x}
                  y={-(e.bounds.y + e.bounds.height)}
                  width={e.bounds.width}
                  height={e.bounds.height}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
          {interactive &&
            [...boxes].map(([layer, b]) =>
              layer === 'spine' ? null : (
                <rect
                  key={layer}
                  data-layer={layer}
                  className={`layer-hit${layer === selected ? ' selected' : ''}${
                    flagged.has(layer) ? ' flagged' : ''
                  }`}
                  x={b.x - 2}
                  y={-(b.y + b.height) - 2}
                  width={b.width + 4}
                  height={b.height + 4}
                  vectorEffect="non-scaling-stroke"
                />
              ),
            )}
          {ghost && (
            <rect
              className={`layer-ghost${outside ? ' outside' : ''}`}
              x={ghost.x}
              y={-(ghost.y + ghost.height)}
              width={ghost.width}
              height={ghost.height}
              vectorEffect="non-scaling-stroke"
            />
          )}
          {guides.x !== undefined && (
            <line
              className="layer-guide"
              x1={guides.x}
              x2={guides.x}
              y1={-media.height}
              y2={0}
              vectorEffect="non-scaling-stroke"
            />
          )}
          {guides.y !== undefined && (
            <line
              className="layer-guide"
              x1={0}
              x2={media.width}
              y1={-guides.y}
              y2={-guides.y}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
        {ghost && outside && (
          <p className="canvas-warning" role="status">
            Outside the safe area: the cover will not build there.
          </p>
        )}
      </div>
    </div>
  );
}
