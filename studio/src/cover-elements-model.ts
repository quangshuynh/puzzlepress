import { plainOf } from './rich-text-model';
// Pure helpers for version 3 region designs: element ids, stack order, edits in
// region coordinates (PDF points from each region's trim corner, y up) and the
// photograph a layer crops. Python lays out, flattens and validates every
// element; these functions only produce authored values.
import { round } from './cover-model';
import type {
  CoverConfig,
  CoverElement,
  CoverLayoutView,
  CoverPhotoView,
  Crop,
  ElementRegion,
  PanelRegion,
  RegionStyle,
} from './types';

export const REGION_NAMES: [ElementRegion, string][] = [
  ['wrap', 'Full wrap'],
  ['back', 'Back'],
  ['spine', 'Spine'],
  ['front', 'Front'],
];
export const KIND_NAMES: Record<CoverElement['type'], string> = {
  photo: 'Photograph',
  rect: 'Rectangle',
  ellipse: 'Ellipse',
  line: 'Line',
  text: 'Text box',
};
// What each element type may be placed on (Python enforces the same rule).
export const ALLOWED: Record<CoverElement['type'], ElementRegion[]> = {
  photo: ['wrap', 'back', 'front'],
  rect: ['wrap', 'back', 'spine', 'front'],
  ellipse: ['wrap', 'back', 'spine', 'front'],
  line: ['wrap', 'back', 'spine', 'front'],
  text: ['back', 'front'],
};
export const MAX_ELEMENTS = 24;

export function designed(cover: CoverConfig) {
  return cover.version >= 3;
}

export function elementLayer(id: string) {
  return `element:${id}`;
}

export function elementOf(cover: CoverConfig, layer: string | null): CoverElement | undefined {
  if (!layer?.startsWith('element:')) return undefined;
  const id = layer.slice(8);
  return cover.elements?.find((element) => element.id === id);
}

export function elementName(element: CoverElement) {
  if (element.name) return element.name;
  if (element.type === 'text')
    return `Text: ${plainOf(element.rich ?? element.text)
      .split('\n')[0]
      .slice(0, 24)}`;
  return `${KIND_NAMES[element.type]} ${element.id}`;
}

export function uniqueId(cover: CoverConfig, base: string) {
  const used = new Set((cover.elements ?? []).map((element) => element.id));
  let n = 1;
  while (used.has(`${base}-${n}`)) n++;
  return `${base}-${n}`;
}

// The region's trim size in points: where an element of that region can sit.
export function regionSize(layout: CoverLayoutView, region: ElementRegion) {
  const origin = layout.regions?.[region]?.origin;
  if (origin) return { width: origin.width, height: origin.height };
  const g = layout.geometry.regions;
  const box = region === 'wrap' ? g.trim : g[region];
  return { width: box.width, height: box.height };
}

export function addElement(
  cover: CoverConfig,
  type: CoverElement['type'],
  region: ElementRegion,
  layout: CoverLayoutView,
  photo?: { path: string; sha256: string },
): [CoverConfig, string] {
  const size = regionSize(layout, region);
  const id = uniqueId(cover, type === 'rect' ? 'block' : type);
  const width = Math.min(size.width * 0.5, 216);
  const height = type === 'line' ? 0 : Math.min(size.height * 0.15, 108);
  const x = round((size.width - width) / 2, 2);
  const y = round((size.height - height) / 2, 2);
  const spine = region === 'spine';
  let element: CoverElement;
  if (type === 'photo') {
    element = { id, type, region, image: photo!, crop: { x: 0.5, y: 0.5, zoom: 1 } };
  } else if (type === 'line') {
    element = spine
      ? {
          id,
          type,
          region,
          from: { x: 0, y: round(size.height / 2, 2) },
          to: { x: round(size.width, 2), y: round(size.height / 2, 2) },
          color: '#f4efe4',
          width: 1,
        }
      : {
          id,
          type,
          region,
          from: { x, y },
          to: { x: round(x + width, 2), y },
          color: '#f4efe4',
          width: 1,
        };
  } else if (type === 'text') {
    element = {
      id,
      type,
      region,
      box: { x, y, width, height },
      text: 'Your text',
      size: 14,
      color: '#f4efe4',
      align: 'left',
      line_spacing: 1.3,
    };
  } else {
    element = {
      id,
      type,
      region,
      box: spine
        ? { x: 0, y: round(size.height * 0.4, 2), width: round(size.width, 2), height: 72 }
        : { x, y, width, height },
      fill: '#f4efe4',
      stroke: null,
    };
  }
  return [{ ...cover, elements: [...(cover.elements ?? []), element] }, elementLayer(id)];
}

export function updateElement(
  cover: CoverConfig,
  id: string,
  patch: Partial<CoverElement>,
): CoverConfig {
  const elements = (cover.elements ?? []).map((element) =>
    element.id === id ? ({ ...element, ...patch } as CoverElement) : element,
  );
  return { ...cover, elements: elements.map(prune) };
}

function prune(element: CoverElement): CoverElement {
  const next = { ...element } as Record<string, unknown>;
  for (const [key, value] of Object.entries(next)) if (value === undefined) delete next[key];
  if (next.visible === true) delete next.visible;
  if (next.locked === false) delete next.locked;
  if (next.name === '') delete next.name;
  return next as unknown as CoverElement;
}

export function removeElement(cover: CoverConfig, id: string): CoverConfig {
  return { ...cover, elements: (cover.elements ?? []).filter((element) => element.id !== id) };
}

export function duplicateElement(cover: CoverConfig, id: string): [CoverConfig, string] {
  const elements = cover.elements ?? [];
  const index = elements.findIndex((element) => element.id === id);
  if (index < 0) return [cover, elementLayer(id)];
  const copy = structuredClone(elements[index]);
  copy.id = uniqueId(cover, id.replace(/-\d+$/, '') || 'copy');
  delete copy.locked;
  const moved = nudged(copy, 9, -9);
  const next = [...elements.slice(0, index + 1), moved, ...elements.slice(index + 1)];
  return [{ ...cover, elements: next }, elementLayer(copy.id)];
}

// `forward` moves the element one step toward the top of the stack (drawn later).
export function moveInStack(cover: CoverConfig, id: string, forward: boolean): CoverConfig {
  const elements = [...(cover.elements ?? [])];
  const index = elements.findIndex((element) => element.id === id);
  const target = index + (forward ? 1 : -1);
  if (index < 0 || target < 0 || target >= elements.length) return cover;
  [elements[index], elements[target]] = [elements[target], elements[index]];
  return { ...cover, elements };
}

function nudged(element: CoverElement, dx: number, dy: number): CoverElement {
  if (element.type === 'line')
    return {
      ...element,
      from: { x: round(element.from.x + dx, 2), y: round(element.from.y + dy, 2) },
      to: { x: round(element.to.x + dx, 2), y: round(element.to.y + dy, 2) },
    };
  if (!element.box) return element;
  return {
    ...element,
    box: { ...element.box, x: round(element.box.x + dx, 2), y: round(element.box.y + dy, 2) },
  } as CoverElement;
}

// Move an unlocked element by (dx, dy) points. Locked or region-filling elements stay.
export function moveElement(cover: CoverConfig, id: string, dx: number, dy: number): CoverConfig {
  const element = cover.elements?.find((e) => e.id === id);
  if (!element || element.locked || !movable(element)) return cover;
  return updateElement(cover, id, nudged(element, dx, dy));
}

export function movable(element: CoverElement) {
  return element.type === 'line' || element.box !== undefined;
}

// Reset an element's styling to its type's defaults, keeping its place and words.
export function resetStyle(element: CoverElement): Partial<CoverElement> {
  if (element.type === 'rect' || element.type === 'ellipse')
    return {
      fill: '#f4efe4',
      stroke: null,
      stroke_width: undefined,
      opacity: undefined,
      rotation: undefined,
    };
  if (element.type === 'line') return { color: '#f4efe4', width: 1 };
  if (element.type === 'text')
    return {
      font: undefined,
      size: 14,
      color: '#f4efe4',
      align: 'left',
      line_spacing: 1.3,
      letter_spacing: undefined,
      case: undefined,
    };
  return { crop: { x: 0.5, y: 0.5, zoom: 1 } };
}

export function setRegion(
  cover: CoverConfig,
  region: PanelRegion,
  patch: Partial<RegionStyle>,
): CoverConfig {
  const regions = cover.regions!;
  const next: RegionStyle = { ...regions[region], ...patch };
  if (!next.gradient) delete next.gradient;
  return { ...cover, regions: { ...regions, [region]: next } };
}

// The crop a selected photo layer edits: the version 1/2 photograph or a photo element.
export function photoCrop(cover: CoverConfig, layer: string | null): Crop | undefined {
  if (layer === 'photo') return cover.crop;
  const element = elementOf(cover, layer);
  return element?.type === 'photo' ? element.crop : undefined;
}

export function setPhotoCrop(cover: CoverConfig, layer: string, crop: Crop): CoverConfig {
  if (layer === 'photo') return { ...cover, crop };
  const element = elementOf(cover, layer);
  return element?.type === 'photo' ? updateElement(cover, element.id, { crop }) : cover;
}

export function photoView(layout: CoverLayoutView, layer: string | null): CoverPhotoView | null {
  if (!layer) return null;
  if (layer === 'photo') return layout.photo;
  return layout.photos?.find((photo) => photo.layer === layer) ?? null;
}

export function isPhotoLayer(cover: CoverConfig, layer: string | null) {
  return layer === 'photo' || elementOf(cover, layer)?.type === 'photo';
}
