import { plainOf, richFonts } from './rich-text-model';
// Pure Cover Studio helpers. They edit authored values (offsets in PDF points,
// normalized focal points) and map screen pixels onto them; every position,
// measurement and verdict still comes from Python's layout of the draft.
import type {
  CoverConfig,
  CoverGeometry,
  CoverLayoutView,
  ExtraLayer,
  PtBox,
  TextLayer,
  TextRole,
} from './types';

// Left to right as the wrap prints, the same order as the editing regions.
export const VIEWS = [
  ['wrap', 'Full wrap'],
  ['back', 'Back'],
  ['spine', 'Spine'],
  ['front', 'Front'],
] as const;
export type View = (typeof VIEWS)[number][0];

export const ROLES: [TextRole, string][] = [
  ['title', 'Title'],
  ['subtitle', 'Subtitle'],
  ['author', 'Author'],
  ['back_text', 'Back-cover text'],
  ['imprint', 'Imprint'],
];
// Layers whose words come from the book details (their display text may differ).
export const METADATA_ROLES: TextRole[] = ['title', 'subtitle', 'author', 'imprint'];

export function round(value: number, places = 4) {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}
export function clamp(value: number, low: number, high: number) {
  return Math.min(high, Math.max(low, value));
}

export function starterCover(image: { path: string; sha256: string }): CoverConfig {
  return {
    version: 1,
    layout: 'full_wrap',
    image,
    crop: { x: 0.5, y: 0.5, zoom: 1 },
    type: { style: 'editorial', position: 'top', align: 'center', tone: 'light' },
    legibility: 'shade',
    background: '#26302b',
    spine_text: 'auto',
  };
}

// The part of the wrap each view shows, in PDF points (origin bottom-left).
export function viewBox(g: CoverGeometry, view: View): PtBox {
  const { media, front, back, spine } = g.regions;
  if (view === 'front')
    return { x: front.x, y: 0, width: media.width - front.x, height: media.height };
  if (view === 'back') return { x: 0, y: 0, width: back.x + back.width, height: media.height };
  if (view === 'spine') {
    const width = Math.min(media.width, Math.max(spine.width + 144, 216));
    const x = clamp(spine.x + spine.width / 2 - width / 2, 0, media.width - width);
    return { x, y: 0, width, height: media.height };
  }
  return media;
}

// A drag of (dx, dy) screen pixels at `scale` px/pt moves the focal point so the
// photograph follows the pointer. Uses Python's applied (clamped) window.
export function dragFocal(
  layout: CoverLayoutView,
  dx: number,
  dy: number,
  scale: number,
  layer = 'photo',
) {
  const photo =
    layer === 'photo' ? layout.photo : layout.photos?.find((item) => item.layer === layer);
  if (!photo) return { x: 0.5, y: 0.5 };
  const { region, window, center } = photo;
  const du = (-dx / scale / region.width) * (window.right - window.left);
  const dv = (-dy / scale / region.height) * (window.bottom - window.top);
  return { x: round(clamp(center[0] + du, 0, 1)), y: round(clamp(center[1] + dv, 0, 1)) };
}

// Screen pixels (y down) to an offset change in PDF points (y up), exactly invertible.
export function dragOffset(dx: number, dy: number, scale: number) {
  return { x: round(dx / scale, 2), y: round(-dy / scale, 2) };
}

// The union of a layer's measured lines, in PDF points.
export function layerBoxes(layout: CoverLayoutView): Map<string, PtBox> {
  const boxes = new Map<string, PtBox>();
  for (const text of layout.texts) {
    const box = boxes.get(text.layer);
    if (!box) {
      boxes.set(text.layer, { ...text.box });
      continue;
    }
    const right = Math.max(box.x + box.width, text.box.x + text.box.width);
    const top = Math.max(box.y + box.height, text.box.y + text.box.height);
    box.x = Math.min(box.x, text.box.x);
    box.y = Math.min(box.y, text.box.y);
    box.width = right - box.x;
    box.height = top - box.y;
  }
  return boxes;
}

export function contains(outer: PtBox, inner: PtBox, tolerance = 0.01) {
  return (
    inner.x >= outer.x - tolerance &&
    inner.y >= outer.y - tolerance &&
    inner.x + inner.width <= outer.x + outer.width + tolerance &&
    inner.y + inner.height <= outer.y + outer.height + tolerance
  );
}

// Which panel a layer lives on, for guides and safe-area hints.
export function panelOf(layer: string, cover: CoverConfig): 'front' | 'back' | 'spine' {
  if (layer === 'spine') return 'spine';
  if (layer.startsWith('extra:'))
    return extraLayer(cover, layer.slice(6))?.panel === 'back' ? 'back' : 'front';
  return layer === 'back_text' || layer === 'imprint' ? 'back' : 'front';
}

export function extraLayer(cover: CoverConfig, id: string): ExtraLayer | undefined {
  return cover.extra?.find((layer) => layer.id === id);
}

// The overrides a layer currently has ({} when it follows the layout).
export function layerOf(cover: CoverConfig, layer: string): TextLayer {
  if (layer.startsWith('extra:')) {
    const extra = extraLayer(cover, layer.slice(6));
    if (!extra) return {};
    const rest: TextLayer & { id?: string; panel?: string } = { ...extra };
    delete rest.id;
    delete rest.panel;
    return rest;
  }
  return cover.text?.[layer as TextRole] ?? {};
}

function prune(layer: TextLayer): TextLayer {
  const next: TextLayer = {};
  for (const [key, value] of Object.entries(layer) as [keyof TextLayer, unknown][]) {
    if (value === undefined) continue;
    if (key === 'visible' && value === true) continue;
    if (key === 'offset') {
      const offset = value as { x: number; y: number };
      if (offset.x === 0 && offset.y === 0) continue;
    }
    (next as Record<string, unknown>)[key] = value;
  }
  return next;
}

// Version 2 is set only when a version 2 feature is first used, so untouched
// version 1 covers keep their cover identity.
export function withVersion(cover: CoverConfig): CoverConfig {
  const used =
    Object.keys(cover.text ?? {}).length > 0 ||
    (cover.extra?.length ?? 0) > 0 ||
    (cover.fonts?.length ?? 0) > 0;
  return used && cover.version < 2 ? { ...cover, version: 2 } : cover;
}

export function setLayer(
  cover: CoverConfig,
  layer: string,
  patch: Partial<TextLayer>,
): CoverConfig {
  if (layer.startsWith('extra:')) {
    const id = layer.slice(6);
    const extra = (cover.extra ?? []).map((item) => {
      if (item.id !== id) return item;
      const merged = prune({
        ...item,
        ...patch,
        id: undefined,
        panel: undefined,
        text: undefined,
      } as TextLayer);
      return { id, panel: item.panel, text: patch.text ?? item.text, ...merged } as ExtraLayer;
    });
    return withVersion({ ...cover, extra });
  }
  const role = layer as TextRole;
  const merged = prune({ ...(cover.text?.[role] ?? {}), ...patch });
  const text = { ...(cover.text ?? {}) };
  if (Object.keys(merged).length) text[role] = merged;
  else delete text[role];
  const next: CoverConfig = { ...cover, text };
  if (!Object.keys(text).length) delete next.text;
  return withVersion(next);
}

export function resetLayer(cover: CoverConfig, layer: string): CoverConfig {
  if (layer.startsWith('extra:')) {
    const id = layer.slice(6);
    const extra = (cover.extra ?? []).map((item) =>
      item.id === id ? { id: item.id, panel: item.panel, text: item.text } : item,
    );
    return { ...cover, extra };
  }
  const text = { ...(cover.text ?? {}) };
  delete text[layer as TextRole];
  const next: CoverConfig = { ...cover, text };
  if (!Object.keys(text).length) delete next.text;
  return next;
}

export function addExtra(cover: CoverConfig, panel: 'front' | 'back'): [CoverConfig, string] {
  const used = new Set((cover.extra ?? []).map((layer) => layer.id));
  let n = 1;
  while (used.has(`text-${n}`)) n++;
  const id = `text-${n}`;
  const extra = [...(cover.extra ?? []), { id, panel, text: 'New text' }];
  return [withVersion({ ...cover, extra }), `extra:${id}`];
}

export function removeExtra(cover: CoverConfig, id: string): CoverConfig {
  const extra = (cover.extra ?? []).filter((layer) => layer.id !== id);
  const next: CoverConfig = { ...cover, extra };
  if (!extra.length) delete next.extra;
  return next;
}

// A font id for a newly used imported font: lowercase words of its name, unique.
export function fontId(cover: CoverConfig, name: string): string {
  const base =
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 32) || 'font';
  const bundled = ['sans', 'sans-bold', 'sans-italic', 'serif-display', 'serif', 'serif-italic'];
  const used = new Set([...(cover.fonts ?? []).map((font) => font.id), ...bundled]);
  let id = base;
  for (let n = 2; used.has(id); n++) id = `${base}-${n}`;
  return id;
}

// Every layer that uses a font id (an imported font in use cannot be removed).
export function fontUsers(cover: CoverConfig, id: string): string[] {
  const users = Object.entries(cover.text ?? {})
    .filter(([, layer]) => layer?.font === id)
    .map(([role]) => role);
  for (const extra of cover.extra ?? []) if (extra.font === id) users.push(`extra:${extra.id}`);
  if (richFonts(cover.back_text).includes(id)) users.push('back_text');
  for (const element of cover.elements ?? [])
    if (element.type === 'text' && (element.font === id || richFonts(element.rich).includes(id)))
      users.push(`element:${element.id}`);
  return users;
}

export function layerName(cover: CoverConfig, layer: string): string {
  if (layer === 'photo') return 'Photograph';
  if (layer.startsWith('region:')) return `${layer.slice(7)} region`;
  if (layer.startsWith('element:')) {
    const element = cover.elements?.find((e) => e.id === layer.slice(8));
    if (!element) return 'Element';
    if (element.name) return element.name;
    if (element.type === 'text')
      return `Text box: ${plainOf(element.rich ?? element.text)
        .split('\n')[0]
        .slice(0, 24)}`;
    const kinds = { photo: 'Photograph', rect: 'Rectangle', ellipse: 'Ellipse', line: 'Line' };
    return `${kinds[element.type]} ${element.id}`;
  }
  if (layer === 'spine') return 'Spine text';
  if (layer.startsWith('extra:')) {
    const extra = extraLayer(cover, layer.slice(6));
    return extra ? `Text: ${extra.text.split('\n')[0].slice(0, 28)}` : 'Text layer';
  }
  return ROLES.find(([role]) => role === layer)?.[1] ?? layer;
}

/** The bundled face the type preset sets body text (back text, text boxes) in. */
export function bodyFace(cover: CoverConfig): string {
  return cover.type.style === 'editorial' ? 'serif' : 'sans';
}
