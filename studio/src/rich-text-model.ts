// Rich text documents as Python stores them (cover_richtext.py): blocks of styled
// runs, never HTML. This module edits that structure purely; Python validates,
// lays out and renders it. Positions are (block, character offset) pairs over the
// block's text; "\n" inside a run is an explicit line break.

export interface RichRun {
  text: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  size?: number;
  font?: string;
  color?: string;
}
export interface RichBlock {
  type?: 'paragraph' | 'heading';
  align?: 'left' | 'center' | 'right';
  list?: 'bullet' | 'number';
  line_spacing?: number;
  space_before?: number;
  space_after?: number;
  runs: RichRun[];
}
export interface RichDoc {
  rich: 1;
  blocks: RichBlock[];
}
export interface Pos {
  block: number;
  offset: number;
}
export interface Sel {
  anchor: Pos;
  focus: Pos;
}
export type Mark = 'bold' | 'italic' | 'underline';
export type RunStyle = Omit<RichRun, 'text'>;
export type BlockStyle = Omit<RichBlock, 'runs'>;

export const MAX_BLOCKS = 40;
export const BUNDLED_FAMILIES = ['sans', 'serif', 'serif-display'] as const;
// Which bundled faces exist for each family: [regular, bold, italic, bold italic].
const VARIANTS: Record<string, [boolean, boolean, boolean, boolean]> = {
  sans: [true, true, true, false],
  serif: [true, false, true, false],
  'serif-display': [true, false, false, false],
};

export function isRich(value: unknown): value is RichDoc {
  return typeof value === 'object' && value !== null && 'rich' in value;
}

export function blockText(block: RichBlock): string {
  return block.runs.map((run) => run.text).join('');
}

export function toPlain(doc: RichDoc): string {
  return doc.blocks.map(blockText).join('\n');
}

export function fromPlain(text: string): RichDoc {
  return {
    rich: 1,
    blocks: text.split('\n').map((line) => ({ runs: line ? [{ text: line }] : [] })),
  };
}

function runStyle(run: RichRun): RunStyle {
  const { text: _text, ...style } = run;
  void _text;
  return style;
}

function sameStyle(a: RunStyle, b: RunStyle) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof RunStyle>;
  for (const key of keys) if ((a[key] ?? undefined) !== (b[key] ?? undefined)) return false;
  return true;
}

function clean(style: RunStyle): RunStyle {
  const out: RunStyle = {};
  for (const [key, value] of Object.entries(style) as [keyof RunStyle, unknown][])
    if (value !== undefined && value !== null && value !== false)
      (out as Record<string, unknown>)[key] = value;
  if (style.bold === false) out.bold = false;
  if (style.italic === false) out.italic = false;
  return out;
}

/** Plain when nothing is formatted: such a document lays out exactly like its text. */
export function isPlain(doc: RichDoc): boolean {
  return doc.blocks.every(
    (block) =>
      (block.type ?? 'paragraph') === 'paragraph' &&
      !block.align &&
      !block.list &&
      block.line_spacing === undefined &&
      !block.space_before &&
      !block.space_after &&
      block.runs.every((run) => Object.keys(clean(runStyle(run))).length === 0),
  );
}

/** Merge neighbouring runs of one style and drop empty runs. */
export function normalize(doc: RichDoc): RichDoc {
  return {
    rich: 1,
    blocks: doc.blocks.map((block) => {
      const runs: RichRun[] = [];
      for (const run of block.runs) {
        if (!run.text) continue;
        const style = clean(runStyle(run));
        const last = runs.at(-1);
        if (last && sameStyle(runStyle(last), style))
          runs[runs.length - 1] = { ...last, text: last.text + run.text };
        else runs.push({ text: run.text, ...style });
      }
      return { ...block, runs };
    }),
  };
}

export function comparePos(a: Pos, b: Pos) {
  return a.block - b.block || a.offset - b.offset;
}

export function ordered(sel: Sel): [Pos, Pos] {
  return comparePos(sel.anchor, sel.focus) <= 0 ? [sel.anchor, sel.focus] : [sel.focus, sel.anchor];
}

export function collapsed(sel: Sel) {
  return comparePos(sel.anchor, sel.focus) === 0;
}

export function clampPos(doc: RichDoc, pos: Pos): Pos {
  const block = Math.max(0, Math.min(doc.blocks.length - 1, pos.block));
  const length = blockText(doc.blocks[block]).length;
  return { block, offset: Math.max(0, Math.min(length, pos.offset)) };
}

/** Split a block's runs at a character offset: [before, after]. */
function splitRuns(runs: RichRun[], offset: number): [RichRun[], RichRun[]] {
  const before: RichRun[] = [];
  const after: RichRun[] = [];
  let seen = 0;
  for (const run of runs) {
    const end = seen + run.text.length;
    if (end <= offset) before.push(run);
    else if (seen >= offset) after.push(run);
    else {
      before.push({ ...run, text: run.text.slice(0, offset - seen) });
      after.push({ ...run, text: run.text.slice(offset - seen) });
    }
    seen = end;
  }
  return [before, after];
}

/** The style typing at `pos` continues: the run before the caret (or after, at a block start). */
export function styleAt(doc: RichDoc, pos: Pos): RunStyle {
  const block = doc.blocks[pos.block];
  if (!block) return {};
  let seen = 0;
  for (const run of block.runs) {
    const end = seen + run.text.length;
    if (pos.offset === 0 || (pos.offset > seen && pos.offset <= end)) return clean(runStyle(run));
    seen = end;
  }
  return {};
}

export function deleteRange(doc: RichDoc, sel: Sel): [RichDoc, Pos] {
  const [start, end] = ordered(sel);
  if (comparePos(start, end) === 0) return [doc, start];
  const first = doc.blocks[start.block];
  const last = doc.blocks[end.block];
  const [keep] = splitRuns(first.runs, start.offset);
  const [, tail] = splitRuns(last.runs, end.offset);
  const merged: RichBlock = { ...first, runs: [...keep, ...tail] };
  const blocks = [...doc.blocks.slice(0, start.block), merged, ...doc.blocks.slice(end.block + 1)];
  return [normalize({ rich: 1, blocks }), start];
}

export function insertText(doc: RichDoc, sel: Sel, text: string, style?: RunStyle): [RichDoc, Pos] {
  if (!text) return deleteRange(doc, sel);
  const [base, pos] = deleteRange(doc, sel);
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const continued = style ?? styleAt(base, pos);
  let current = base;
  let at = pos;
  lines.forEach((line, index) => {
    if (index > 0) [current, at] = splitBlock(current, { anchor: at, focus: at });
    if (!line) return;
    const block = current.blocks[at.block];
    const [before, after] = splitRuns(block.runs, at.offset);
    const runs = [...before, { text: line, ...continued }, ...after];
    const blocks = current.blocks.map((b, i) => (i === at.block ? { ...block, runs } : b));
    current = normalize({ rich: 1, blocks });
    at = { block: at.block, offset: at.offset + line.length };
  });
  return [current, at];
}

/** An explicit line break inside the block (Shift+Enter). */
export function insertLineBreak(doc: RichDoc, sel: Sel): [RichDoc, Pos] {
  const [base, pos] = deleteRange(doc, sel);
  const block = base.blocks[pos.block];
  const [before, after] = splitRuns(block.runs, pos.offset);
  const runs = [...before, { text: '\n', ...styleAt(base, pos) }, ...after];
  const blocks = base.blocks.map((b, i) => (i === pos.block ? { ...block, runs } : b));
  return [normalize({ rich: 1, blocks }), { block: pos.block, offset: pos.offset + 1 }];
}

/** A new block (Enter). Lists continue; a heading is followed by a paragraph. */
export function splitBlock(doc: RichDoc, sel: Sel): [RichDoc, Pos] {
  const [base, pos] = deleteRange(doc, sel);
  if (base.blocks.length >= MAX_BLOCKS) return [base, pos];
  const block = base.blocks[pos.block];
  const [before, after] = splitRuns(block.runs, pos.offset);
  const { runs: _runs, ...style } = block;
  void _runs;
  const next: RichBlock = { ...style, runs: after, space_before: undefined };
  if (next.type === 'heading') delete next.type;
  delete next.space_before;
  const blocks = [
    ...base.blocks.slice(0, pos.block),
    { ...block, runs: before },
    next,
    ...base.blocks.slice(pos.block + 1),
  ];
  return [normalize({ rich: 1, blocks }), { block: pos.block + 1, offset: 0 }];
}

export function deleteBackward(doc: RichDoc, sel: Sel): [RichDoc, Pos] {
  if (!collapsed(sel)) return deleteRange(doc, sel);
  const pos = sel.focus;
  if (pos.offset > 0) {
    const text = blockText(doc.blocks[pos.block]);
    const step = surrogateStep(text, pos.offset, -1);
    return deleteRange(doc, { anchor: { ...pos, offset: pos.offset - step }, focus: pos });
  }
  if (pos.block === 0) {
    const block = doc.blocks[0];
    // At the very start, Backspace first removes a list or heading.
    if (block.list || block.type === 'heading') {
      const blocks = doc.blocks.map((b, i) =>
        i === 0 ? { ...b, list: undefined, type: undefined } : b,
      );
      return [prune({ rich: 1, blocks }), pos];
    }
    return [doc, pos];
  }
  const previous = { block: pos.block - 1, offset: blockText(doc.blocks[pos.block - 1]).length };
  return deleteRange(doc, { anchor: previous, focus: pos });
}

export function deleteForward(doc: RichDoc, sel: Sel): [RichDoc, Pos] {
  if (!collapsed(sel)) return deleteRange(doc, sel);
  const pos = sel.focus;
  const text = blockText(doc.blocks[pos.block]);
  if (pos.offset < text.length) {
    const step = surrogateStep(text, pos.offset, 1);
    return deleteRange(doc, { anchor: pos, focus: { ...pos, offset: pos.offset + step } });
  }
  if (pos.block === doc.blocks.length - 1) return [doc, pos];
  return deleteRange(doc, { anchor: pos, focus: { block: pos.block + 1, offset: 0 } });
}

function surrogateStep(text: string, offset: number, direction: 1 | -1) {
  const code = text.charCodeAt(direction < 0 ? offset - 1 : offset);
  const low = direction < 0 ? code >= 0xdc00 && code <= 0xdfff : code >= 0xd800 && code <= 0xdbff;
  return low ? 2 : 1;
}

/** Apply `patch` to every character in the selection; other text keeps its style. */
export function styleRange(doc: RichDoc, sel: Sel, patch: RunStyle): RichDoc {
  const [start, end] = ordered(sel);
  const blocks = doc.blocks.map((block, index) => {
    if (index < start.block || index > end.block) return block;
    const from = index === start.block ? start.offset : 0;
    const to = index === end.block ? end.offset : blockText(block).length;
    const [before, rest] = splitRuns(block.runs, from);
    const [middle, after] = splitRuns(rest, to - from);
    return {
      ...block,
      runs: [...before, ...middle.map((run) => ({ ...run, ...patch })), ...after],
    };
  });
  return normalize({ rich: 1, blocks });
}

function selectedRuns(doc: RichDoc, sel: Sel): RichRun[] {
  const [start, end] = ordered(sel);
  const runs: RichRun[] = [];
  doc.blocks.forEach((block, index) => {
    if (index < start.block || index > end.block) return;
    const from = index === start.block ? start.offset : 0;
    const to = index === end.block ? end.offset : blockText(block).length;
    const [, rest] = splitRuns(block.runs, from);
    const [middle] = splitRuns(rest, to - from);
    runs.push(...middle.filter((run) => run.text));
  });
  return runs;
}

/** Whether the whole selection has `mark` (bold and italic consider the inherited default). */
export function hasMark(doc: RichDoc, sel: Sel, mark: Mark, inherited = false): boolean {
  const runs = collapsed(sel)
    ? [{ text: 'x', ...styleAt(doc, sel.focus) }]
    : selectedRuns(doc, sel);
  return (
    runs.length > 0 && runs.every((run) => run[mark] ?? (mark === 'underline' ? false : inherited))
  );
}

export function toggleMark(doc: RichDoc, sel: Sel, mark: Mark, inherited = false): RichDoc {
  const on = hasMark(doc, sel, mark, inherited);
  const value = !on;
  // A value equal to the inherited default is stored as "inherit" (absent).
  const patch: RunStyle = {
    [mark]: mark !== 'underline' && value === inherited ? undefined : value,
  };
  return styleRange(doc, sel, patch);
}

/** A run attribute shared by the whole selection, or undefined when it varies. */
export function sharedStyle<K extends keyof RunStyle>(doc: RichDoc, sel: Sel, key: K): RunStyle[K] {
  const runs = collapsed(sel)
    ? [{ text: 'x', ...styleAt(doc, sel.focus) }]
    : selectedRuns(doc, sel);
  const values = new Set(runs.map((run) => run[key]));
  return values.size === 1 ? (runs[0]?.[key] as RunStyle[K]) : undefined;
}

export function setBlocks(doc: RichDoc, sel: Sel, patch: BlockStyle): RichDoc {
  const [start, end] = ordered(sel);
  const blocks = doc.blocks.map((block, index) => {
    if (index < start.block || index > end.block) return block;
    const next = { ...block, ...patch };
    if (next.type === 'heading') delete next.list;
    if (patch.list) delete next.type;
    return next;
  });
  return prune({ rich: 1, blocks });
}

function prune(doc: RichDoc): RichDoc {
  return {
    rich: 1,
    blocks: doc.blocks.map((block) => {
      const next: RichBlock = { runs: block.runs };
      if (block.type === 'heading') next.type = 'heading';
      if (block.align) next.align = block.align;
      if (block.list) next.list = block.list;
      if (block.line_spacing !== undefined) next.line_spacing = block.line_spacing;
      if (block.space_before) next.space_before = block.space_before;
      if (block.space_after) next.space_after = block.space_after;
      return next;
    }),
  };
}

/** Remove every run and block format in the selection's blocks (text is kept). */
export function clearFormatting(doc: RichDoc, sel: Sel): RichDoc {
  const [start, end] = ordered(sel);
  const blocks = doc.blocks.map((block, index) =>
    index < start.block || index > end.block
      ? block
      : { runs: block.runs.map((run) => ({ text: run.text })) },
  );
  return normalize({ rich: 1, blocks });
}

export function variantAvailable(family: string, bold: boolean, italic: boolean) {
  const table = VARIANTS[family];
  if (!table) return !bold && !italic; // Imported fonts are single faces.
  return table[(bold ? 1 : 0) + (italic ? 2 : 0)];
}

/** The bundled family a face belongs to (for faces named by a text box or layer). */
export function familyOf(face: string | undefined, fallback = 'serif'): string {
  if (!face) return fallback;
  if (face.startsWith('sans')) return 'sans';
  if (face === 'serif-display') return 'serif-display';
  if (face.startsWith('serif')) return 'serif';
  return face;
}

export function faceIsBold(face: string | undefined) {
  return face === 'sans-bold';
}
export function faceIsItalic(face: string | undefined) {
  return face === 'sans-italic' || face === 'serif-italic';
}

/** The stored value for a field: plain text while unformatted, the document otherwise. */
export function stored(doc: RichDoc): string | RichDoc {
  const normal = normalize(doc);
  return isPlain(normal) ? toPlain(normal) : prune(normal);
}

export function wordBoundary(text: string, offset: number, direction: 1 | -1) {
  let i = offset;
  const isWord = (c: string | undefined) => c !== undefined && /[\p{L}\p{N}_'’-]/u.test(c);
  if (direction < 0) {
    while (i > 0 && !isWord(text[i - 1])) i--;
    while (i > 0 && isWord(text[i - 1])) i--;
  } else {
    while (i < text.length && !isWord(text[i])) i++;
    while (i < text.length && isWord(text[i])) i++;
  }
  return i;
}

/** The words of a stored field, plain or rich. */
export function plainOf(value: string | RichDoc | undefined | null): string {
  if (value === undefined || value === null) return '';
  return isRich(value) ? toPlain(value) : value;
}

/** Every font a stored field's runs name. */
export function richFonts(value: string | RichDoc | undefined | null): string[] {
  if (!isRich(value)) return [];
  return value.blocks
    .flatMap((block) => block.runs.map((run) => run.font))
    .filter((font): font is string => Boolean(font));
}
