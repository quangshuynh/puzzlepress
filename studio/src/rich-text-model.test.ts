import { describe, expect, it } from 'vitest';
import {
  clearFormatting,
  deleteBackward,
  deleteForward,
  deleteRange,
  fromPlain,
  hasMark,
  insertLineBreak,
  insertText,
  isPlain,
  normalize,
  plainOf,
  setBlocks,
  splitBlock,
  stored,
  styleRange,
  toPlain,
  toggleMark,
  variantAvailable,
  type RichDoc,
  type Sel,
} from './rich-text-model';

const at = (block: number, offset: number): Sel => ({
  anchor: { block, offset },
  focus: { block, offset },
});
const span = (block: number, from: number, to: number): Sel => ({
  anchor: { block, offset: from },
  focus: { block, offset: to },
});

describe('rich text model', () => {
  it('round-trips plain text and stays plain until formatted', () => {
    const doc = fromPlain('Sixty puzzles\n\nSolutions at the back');
    expect(toPlain(doc)).toBe('Sixty puzzles\n\nSolutions at the back');
    expect(isPlain(doc)).toBe(true);
    expect(stored(doc)).toBe('Sixty puzzles\n\nSolutions at the back');
    const bold = toggleMark(doc, span(0, 0, 5), 'bold');
    expect(isPlain(bold)).toBe(false);
    const value = stored(bold) as RichDoc;
    expect(value.blocks[0].runs).toEqual([{ text: 'Sixty', bold: true }, { text: ' puzzles' }]);
    expect(plainOf(value)).toBe('Sixty puzzles\n\nSolutions at the back');
    // Removing the only format returns to plain text.
    expect(stored(toggleMark(bold, span(0, 0, 5), 'bold'))).toBe(toPlain(doc));
  });

  it('formats only the selection and typing continues the caret style', () => {
    let doc = toggleMark(fromPlain('Engine bay'), span(0, 7, 10), 'italic');
    expect(doc.blocks[0].runs).toEqual([{ text: 'Engine ' }, { text: 'bay', italic: true }]);
    const [typed, caret] = insertText(doc, at(0, 10), 's');
    expect(typed.blocks[0].runs.at(-1)).toEqual({ text: 'bays', italic: true });
    expect(caret).toEqual({ block: 0, offset: 11 });
    const [front] = insertText(typed, at(0, 0), 'The ');
    expect(front.blocks[0].runs[0]).toEqual({ text: 'The Engine ' });
    doc = styleRange(front, span(0, 4, 10), { size: 18, color: '#c03030' });
    expect(doc.blocks[0].runs[1]).toEqual({ text: 'Engine', size: 18, color: '#c03030' });
    expect(hasMark(doc, span(0, 11, 14), 'italic')).toBe(true);
    expect(hasMark(doc, span(0, 0, 14), 'italic')).toBe(false);
  });

  it('splits, joins and deletes across blocks', () => {
    const doc = fromPlain('Pistons and gears');
    const [split, caret] = splitBlock(doc, at(0, 7));
    expect(split.blocks.map((b) => b.runs.map((r) => r.text).join(''))).toEqual([
      'Pistons',
      ' and gears',
    ]);
    expect(caret).toEqual({ block: 1, offset: 0 });
    const [joined, back] = deleteBackward(split, at(1, 0));
    expect(toPlain(joined)).toBe('Pistons and gears');
    expect(back).toEqual({ block: 0, offset: 7 });
    const [forward] = deleteForward(split, at(0, 7));
    expect(toPlain(forward)).toBe('Pistons and gears');
    const [cut] = deleteRange(split, {
      anchor: { block: 0, offset: 3 },
      focus: { block: 1, offset: 5 },
    });
    expect(toPlain(cut)).toBe('Pisgears');
    const [lines] = insertLineBreak(doc, at(0, 7));
    expect(toPlain(lines)).toBe('Pistons\n and gears');
    expect(lines.blocks).toHaveLength(1);
  });

  it('pastes plain text with line breaks as paragraphs and never markup', () => {
    const [doc] = insertText(fromPlain('AB'), at(0, 1), '<b>x</b>\ny');
    expect(toPlain(doc)).toBe('A<b>x</b>\nyB');
    expect(isPlain(doc)).toBe(true);
  });

  it('sets block formats: lists, headings, alignment and spacing', () => {
    const doc = fromPlain('Tools\nWrench\nJack');
    const listed = setBlocks(doc, span(1, 0, 0), { list: 'bullet' });
    expect(listed.blocks[1].list).toBe('bullet');
    const range = { anchor: { block: 1, offset: 0 }, focus: { block: 2, offset: 2 } };
    const numbered = setBlocks(listed, range, { list: 'number', space_after: 4 });
    expect(numbered.blocks.slice(1).map((b) => b.list)).toEqual(['number', 'number']);
    const heading = setBlocks(numbered, at(0, 0), { type: 'heading', align: 'center' });
    expect(heading.blocks[0]).toEqual({
      type: 'heading',
      align: 'center',
      runs: [{ text: 'Tools' }],
    });
    // A heading is never a list item; Enter after a list item continues the list.
    const [next] = splitBlock(heading, at(2, 4));
    expect(next.blocks[3].list).toBe('number');
    const cleared = clearFormatting(next, {
      anchor: { block: 0, offset: 0 },
      focus: { block: 3, offset: 0 },
    });
    expect(isPlain(cleared)).toBe(true);
  });

  it('knows which bundled variants exist', () => {
    expect(variantAvailable('sans', true, false)).toBe(true);
    expect(variantAvailable('sans', true, true)).toBe(false);
    expect(variantAvailable('serif', true, false)).toBe(false);
    expect(variantAvailable('serif', false, true)).toBe(true);
    expect(variantAvailable('serif-display', false, true)).toBe(false);
    expect(variantAvailable('my-font', true, false)).toBe(false);
  });

  it('normalizes deterministically', () => {
    const doc: RichDoc = {
      rich: 1,
      blocks: [{ runs: [{ text: 'A', bold: true }, { text: '' }, { text: 'B', bold: true }] }],
    };
    expect(normalize(doc).blocks[0].runs).toEqual([{ text: 'AB', bold: true }]);
    expect(JSON.stringify(stored(doc))).toBe(JSON.stringify(stored(normalize(doc))));
  });

  it('removes a surrogate pair as one character', () => {
    const [doc] = deleteBackward(fromPlain('car 🚗'), at(0, 6));
    expect(toPlain(doc)).toBe('car ');
  });
});
