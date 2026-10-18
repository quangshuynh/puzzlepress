import { useRef, useState } from 'react';
import { ApiError, request } from './api';
import { NumberField } from './cover-inspector';
import { Segmented } from './cover-tools';
import { FieldErrors, matchIssues, type Source } from './editor-fields';
import type {
  AnswerSummary,
  CoverAsset,
  DesignCatalogue,
  DesignImport,
  InteriorDraft,
  InteriorStyle,
  Issue,
  LookOverrides,
  ThemeDivider,
} from './types';
import { Status } from './ui';

// The editing panels of Interior design. Every value here is authored source in
// book.yaml: `composition` for pagination (spreads, solutions per page) and the
// `interior` style for presentation. Python resolves, lays out and validates them.

export type StyleSection = 'title_page' | 'puzzle_pages' | 'solution_pages' | 'dividers';

export interface PanelProps {
  draft: Source;
  style: InteriorStyle | undefined;
  issues: Issue[];
  preview: InteriorDraft | undefined;
  catalogue: DesignCatalogue | undefined;
  photos: CoverAsset[];
  base: string;
  change: (next: InteriorStyle | undefined) => void;
  set: <K extends StyleSection>(section: K, patch: Partial<NonNullable<InteriorStyle[K]>>) => void;
  setTop: (patch: Partial<InteriorStyle>) => void;
  setComposition: (next: NonNullable<Source['composition']>) => void;
  show: (view: string) => void;
}

const V1_PRESETS: [NonNullable<InteriorStyle['preset']>, string, string][] = [
  ['classic', 'Classic', 'The original PuzzlePress interior, unchanged.'],
  ['editorial', 'Editorial', 'Left-aligned headers, fine rules, page numbers outside.'],
  ['modern', 'Modern', 'Regular-weight titles, a framed title page, heavier grids.'],
  ['high_contrast', 'High contrast', 'Larger words, bold frames and solution marks.'],
];
// Version 1 presets and their closest version 2 theme, for the explicit conversion.
const CONVERTED_THEME: Record<string, NonNullable<InteriorStyle['theme']>> = {
  classic: 'classic',
  editorial: 'editorial_minimal',
  modern: 'classic',
  high_contrast: 'high_contrast',
};
export const NEW_DESIGN: InteriorStyle = { version: 2, theme: 'classic', layout: 'classic' };

export function prune<T extends object>(value: T): T {
  const next = { ...value } as Record<string, unknown>;
  for (const [key, item] of Object.entries(next)) if (item === undefined) delete next[key];
  return next as T;
}

// Issues for a section's own mapping or unknown keys; each field lists its own.
function sectionIssues(issues: Issue[], path: string) {
  return matchIssues(issues, path).filter((i) => i.path === path || i.code === 'unknown_field');
}

function ink(gray: number | undefined) {
  return gray === undefined ? '' : `${Math.round((1 - gray) * 100)}% black`;
}

// A version 1 style's controls stay usable; themes and layouts need the explicit upgrade.
export function VersionCard({ style, change }: Pick<PanelProps, 'style' | 'change'>) {
  if (!style)
    return (
      <div className="convert-card">
        <p className="small">
          This book uses the classic interior with no design section. Adding one records your
          choices in book.yaml; the Classic theme with the Classic layout draws exactly the same
          pages.
        </p>
        <button type="button" className="small-button" onClick={() => change({ ...NEW_DESIGN })}>
          Add an interior design
        </button>
      </div>
    );
  if (style.version !== 1) return null;
  return (
    <div className="convert-card">
      <p className="small">
        This book uses interior style version 1 (preset {style.preset ?? 'classic'}). Themes, page
        layouts, accents and answer captions need version 2. Converting keeps your overrides and
        picks the closest theme; pages may look different, so review the preview before saving.
      </p>
      <button
        type="button"
        className="small-button"
        onClick={() => {
          const rest = { ...style };
          delete rest.preset;
          change({
            ...rest,
            version: 2,
            theme: CONVERTED_THEME[style.preset ?? 'classic'],
            layout: 'classic',
          });
        }}
      >
        Convert to version 2
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ page layout

export function PageLayoutPanel(p: PanelProps) {
  const { style, issues, set, setTop, catalogue, draft } = p;
  const composition = draft.composition!;
  const v2 = style?.version === 2;
  const puzzle = style?.puzzle_pages ?? {};
  const spread = composition.puzzles.layout === 'spread';
  const setLayout = (layout: 'single' | 'spread') => {
    const puzzles = { ...composition.puzzles };
    if (layout === 'spread') puzzles.layout = 'spread';
    else delete puzzles.layout;
    p.setComposition({ ...composition, puzzles });
  };
  return (
    <>
      <section className="interior-section" aria-labelledby="layout-arrangement">
        <h3 id="layout-arrangement">Puzzle pages</h3>
        <Segmented
          legend="Each puzzle takes"
          value={spread ? 'spread' : 'single'}
          path="composition.puzzles.layout"
          issues={issues}
          options={[
            ['single', 'One page'],
            ['spread', 'A two-page spread'],
          ]}
          onChange={setLayout}
        />
        <p className="small muted">
          {spread
            ? 'The word list sits on a left-hand page facing its grid. This doubles the puzzle pages: the page count, solution page references and the cover spine all change.'
            : 'Title, grid and word list share one page (the original arrangement).'}
        </p>
        <FieldErrors
          id="composition.puzzles.start"
          issues={matchIssues(issues, 'composition.puzzles.start')}
        />
      </section>
      <section className="interior-section" aria-labelledby="layout-presets">
        <h3 id="layout-presets">Page layout</h3>
        {!v2 ? (
          <VersionCard style={style} change={p.change} />
        ) : (
          <ul className="preset-list" aria-label="Page layouts">
            {(catalogue?.layouts ?? []).map((layout) => (
              <li key={layout.id}>
                <label className="check">
                  <input
                    type="radio"
                    name="interior-layout"
                    checked={(style?.layout ?? 'classic') === layout.id}
                    onChange={() => setTop({ layout: layout.id })}
                  />
                  <span>
                    <strong>{layout.name}</strong>
                    <small>{layout.description}</small>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <FieldErrors id="interior.layout" issues={matchIssues(issues, 'interior.layout')} />
      </section>
      {style && (
        <>
          <section className="interior-section" aria-labelledby="layout-header">
            <h3 id="layout-header">Header</h3>
            <Segmented
              legend="Title alignment"
              value={puzzle.header_align ?? 'preset'}
              options={[
                ['preset', 'As the layout'],
                ['center', 'Centered'],
                ['left', 'Left'],
              ]}
              onChange={(value) =>
                set('puzzle_pages', { header_align: value === 'preset' ? undefined : value })
              }
            />
            <div className="field-grid">
              <NumberField
                id="interior-puzzle-title"
                label="Title size"
                value={puzzle.title_size}
                placeholder="Layout"
                min={16}
                max={30}
                step={1}
                unit="pt"
                issues={issues}
                path="interior.puzzle_pages.title_size"
                onChange={(title_size) => set('puzzle_pages', { title_size })}
              />
              <NumberField
                id="interior-theme-size"
                label="Theme label size"
                value={puzzle.theme_size}
                placeholder="Layout"
                min={9}
                max={14}
                step={0.5}
                unit="pt"
                issues={issues}
                path="interior.puzzle_pages.theme_size"
                onChange={(theme_size) => set('puzzle_pages', { theme_size })}
              />
            </div>
            {(
              [
                ['title_bold', 'Bold puzzle titles', true, false],
                ['theme_label', 'Show the theme (category) under the title', true, false],
                ['header_rule', 'Rule under the header', false, false],
                ['puzzle_number', 'Show the puzzle number', false, true],
              ] as const
            ).map(([key, label, fallback, needsV2]) =>
              needsV2 && !v2 ? null : (
                <label key={key} className="check">
                  <input
                    type="checkbox"
                    checked={puzzle[key] ?? fallback}
                    onChange={(e) => set('puzzle_pages', { [key]: e.target.checked })}
                  />
                  <span>{label}</span>
                </label>
              ),
            )}
          </section>
          <section className="interior-section" aria-labelledby="layout-words">
            <h3 id="layout-words">Word list</h3>
            {v2 && !spread && (
              <Segmented
                legend="Position"
                value={puzzle.word_position ?? 'below'}
                options={[
                  ['below', 'Below the grid'],
                  ['above', 'Above the grid'],
                ]}
                onChange={(word_position) =>
                  set('puzzle_pages', {
                    word_position: word_position === 'below' ? undefined : word_position,
                  })
                }
              />
            )}
            {v2 && (
              <div className="field-grid">
                <Segmented
                  legend="Alignment"
                  value={puzzle.word_align ?? 'center'}
                  options={[
                    ['center', 'Centered'],
                    ['left', 'Left'],
                  ]}
                  onChange={(word_align) =>
                    set('puzzle_pages', {
                      word_align: word_align === 'center' ? undefined : word_align,
                    })
                  }
                />
                <Segmented
                  legend="Weight"
                  value={puzzle.word_weight ?? 'layout'}
                  options={[
                    ['layout', 'As the layout'],
                    ['regular', 'Regular'],
                    ['bold', 'Bold'],
                  ]}
                  onChange={(value) =>
                    set('puzzle_pages', { word_weight: value === 'layout' ? undefined : value })
                  }
                />
              </div>
            )}
            <div className="field-grid">
              <NumberField
                id="interior-word-size"
                label="Size"
                value={puzzle.word_size}
                placeholder="Layout"
                min={10}
                max={16}
                step={0.5}
                unit="pt"
                issues={issues}
                path="interior.puzzle_pages.word_size"
                onChange={(word_size) => set('puzzle_pages', { word_size })}
              />
              <NumberField
                id="interior-word-columns"
                label="Columns, at most"
                value={puzzle.word_columns}
                placeholder="Layout"
                min={v2 ? 1 : 2}
                max={5}
                step={1}
                issues={issues}
                path="interior.puzzle_pages.word_columns"
                onChange={(word_columns) => set('puzzle_pages', { word_columns })}
              />
            </div>
            <label className="check">
              <input
                type="checkbox"
                checked={puzzle.word_rule ?? false}
                onChange={(e) => set('puzzle_pages', { word_rule: e.target.checked })}
              />
              <span>Rule between the grid and the word list</span>
            </label>
            <p className="small muted">
              Words are never cut off or shrunk: a list too long for its page is reported, and
              spacing follows the theme&apos;s density.
            </p>
          </section>
          <section className="interior-section" aria-labelledby="layout-grid">
            <h3 id="layout-grid">Grid</h3>
            <div className="field-grid">
              <NumberField
                id="interior-grid-frame"
                label="Frame weight"
                value={puzzle.grid_frame}
                placeholder="Theme"
                min={0.75}
                max={3}
                step={0.25}
                unit="pt"
                issues={issues}
                path="interior.puzzle_pages.grid_frame"
                onChange={(grid_frame) => set('puzzle_pages', { grid_frame })}
              />
              {v2 && (
                <NumberField
                  id="interior-grid-width"
                  label="Width, at most"
                  value={puzzle.grid_width}
                  placeholder="100"
                  min={60}
                  max={100}
                  step={5}
                  unit="%"
                  issues={issues}
                  path="interior.puzzle_pages.grid_width"
                  onChange={(grid_width) => set('puzzle_pages', { grid_width })}
                />
              )}
            </div>
            {v2 && (
              <Segmented
                legend="Letters"
                value={puzzle.letter_scale ?? 'layout'}
                options={[
                  ['layout', 'As the layout'],
                  ['standard', 'Standard'],
                  ['large', 'Large in each cell'],
                ]}
                onChange={(value) =>
                  set('puzzle_pages', { letter_scale: value === 'layout' ? undefined : value })
                }
              />
            )}
            <p className="small muted">
              Grids, letters and paths stay exactly as generated; letters never go below the print
              profile&apos;s 9 pt minimum.
            </p>
          </section>
          <section className="interior-section" aria-labelledby="layout-footer">
            <h3 id="layout-footer">Footer</h3>
            <Segmented
              legend="Page numbers"
              value={style.folio ?? 'preset'}
              options={[
                ['preset', 'As the theme'],
                ['center', 'Centered'],
                ['outside', 'Outside edge'],
              ]}
              onChange={(folio) => setTop({ folio: folio === 'preset' ? undefined : folio })}
            />
            {v2 && (
              <TemplateField
                id="interior-answer-reference"
                label="Answer reference (optional)"
                value={puzzle.answer_reference}
                example="Solution on page {page}"
                path="interior.puzzle_pages.answer_reference"
                issues={issues}
                onChange={(answer_reference) => set('puzzle_pages', { answer_reference })}
              />
            )}
          </section>
          <button
            type="button"
            className="small-button"
            onClick={() => {
              const next = { ...style };
              delete next.puzzle_pages;
              delete next.folio;
              if (v2) next.layout = 'classic';
              p.change(next);
            }}
          >
            Reset page layout
          </button>
          <FieldErrors
            id="interior.puzzle_pages"
            issues={sectionIssues(issues, 'interior.puzzle_pages')}
          />
        </>
      )}
    </>
  );
}

function TemplateField({
  id,
  label,
  value,
  example,
  path,
  issues,
  onChange,
}: {
  id: string;
  label: string;
  value: string | undefined;
  example: string;
  path: string;
  issues: Issue[];
  onChange: (value: string | undefined) => void;
}) {
  const matching = matchIssues(issues, path);
  return (
    <div className="editor-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        value={value ?? ''}
        placeholder={example}
        maxLength={60}
        aria-invalid={matching.length ? true : undefined}
        aria-describedby={`${id}-hint${matching.length ? ` ${path}-issues` : ''}`}
        onChange={(e) => onChange(e.target.value || undefined)}
      />
      <p id={`${id}-hint`} className="small muted field-hint">
        Your words, in the book&apos;s language. Write {'{page}'} where the page number goes; Python
        fills in the real page and keeps it right when pages move.
      </p>
      <FieldErrors id={path} issues={matching} />
    </div>
  );
}

// ------------------------------------------------------------------ answer layout

function choiceText(per_page: number, summary: AnswerSummary | null | undefined) {
  const choice = summary?.choices.find((c) => c.per_page === per_page);
  if (!choice) return null;
  const grid = choice.grid ? ` for ${choice.grid[0]} × ${choice.grid[1]} grids` : '';
  if (!choice.fits)
    return (
      <>
        <Status tone="fail">Too small</Status> letters {choice.letter_size.toFixed(1)} pt{grid},
        below the {choice.minimum} pt minimum
      </>
    );
  if (!choice.comfortable)
    return (
      <>
        <Status tone="review">Cramped</Status> letters {choice.letter_size.toFixed(1)} pt{grid}
      </>
    );
  return (
    <>
      <Status tone="pass">Fits</Status> letters {choice.letter_size.toFixed(1)} pt{grid}
    </>
  );
}

const ARRANGEMENTS: [number, string][] = [
  [1, 'One large solution'],
  [2, 'Two, stacked'],
  [4, 'Four in a 2 × 2 grid'],
  [6, 'Six in a 2 × 3 grid'],
  [8, 'Eight in a 2 × 4 grid (small grids only)'],
];

export function AnswerLayoutPanel(p: PanelProps) {
  const { style, issues, set, draft, preview } = p;
  const composition = draft.composition!;
  const solutions = composition.solutions;
  const v2 = style?.version === 2;
  const summary = preview?.answers;
  const solution = style?.solution_pages ?? {};
  if (solutions.placement !== 'end')
    return (
      <section className="interior-section" aria-labelledby="answers-none">
        <h3 id="answers-none">Answer layout</h3>
        <p className="small">
          This book omits solutions. Place them at the end in{' '}
          <a href={`${p.base.replace('/api/projects/', '/books/')}/book`}>Book</a> to lay out answer
          pages.
        </p>
      </section>
    );
  const perPage = solutions.per_page ?? 4;
  const setPerPage = (per_page: number) =>
    p.setComposition({ ...composition, solutions: { ...solutions, per_page } });
  const viable = summary?.choices.filter((c) => c.fits).map((c) => c.per_page) ?? [];
  const chosen = summary?.choices.find((c) => c.per_page === perPage);
  return (
    <>
      <section className="interior-section" aria-labelledby="answers-count">
        <h3 id="answers-count">Solutions per printed page</h3>
        <p className="small muted">
          The count on each printed page, not across a spread. Four (2 × 2) is the default. Letter
          sizes are Python&apos;s measure of this book&apos;s largest grids.
        </p>
        <fieldset className="answer-choices">
          <legend className="sr-only">Solutions per printed page</legend>
          {ARRANGEMENTS.map(([count, label]) => (
            <label key={count} className="check answer-choice">
              <input
                type="radio"
                name="solutions-per-page"
                checked={perPage === count}
                onChange={() => setPerPage(count)}
              />
              <span>
                <strong>
                  {count} a page{count === 4 ? ' (default)' : ''}
                </strong>
                <small>{label}</small>
                <small>{choiceText(count, summary)}</small>
              </span>
            </label>
          ))}
        </fieldset>
        <FieldErrors
          id="composition.solutions.per_page"
          issues={matchIssues(issues, 'composition.solutions.per_page')}
        />
        {chosen && !chosen.fits && (
          <p role="alert" className="field-errors small">
            {perPage} solutions a page cannot print these grids at {chosen.minimum} pt.{' '}
            {viable.length
              ? `Choose ${Math.max(...viable)} or fewer. Your choice is kept until you change it.`
              : 'No choice fits these grids on this trim size.'}
          </p>
        )}
        {summary && (
          <p className="small">
            {summary.pages} answer page{summary.pages === 1 ? '' : 's'}
            {summary.pages > 1 && summary.last_page_solutions < summary.per_page
              ? `; the last holds ${summary.last_page_solutions}.`
              : '.'}{' '}
            <button type="button" className="link-button" onClick={() => p.show('answers')}>
              Show a full answer page
            </button>
            {summary.pages > 1 && summary.last_page_solutions < summary.per_page && (
              <>
                {' · '}
                <button
                  type="button"
                  className="link-button"
                  onClick={() => p.show('answers_last')}
                >
                  Show the last answer page
                </button>
              </>
            )}
          </p>
        )}
      </section>
      <section className="interior-section" aria-labelledby="answers-captions">
        <h3 id="answers-captions">Headings and captions</h3>
        <p className="small">
          Section heading: <strong>{solutions.title}</strong> (edit it in{' '}
          <a href={`${p.base.replace('/api/projects/', '/books/')}/book`}>Book</a>). Each solution
          is captioned with its puzzle&apos;s title and the page it is printed on.
        </p>
        {v2 ? (
          <TemplateField
            id="interior-page-label"
            label="Caption page label (optional)"
            value={solution.page_label}
            example="page {page}"
            path="interior.solution_pages.page_label"
            issues={issues}
            onChange={(page_label) => set('solution_pages', { page_label })}
          />
        ) : (
          <p className="small muted">Caption labels need interior design version 2.</p>
        )}
        {style && (
          <div className="field-grid">
            <NumberField
              id="interior-caption"
              label="Caption size"
              value={solution.caption_size}
              placeholder="Theme"
              min={8}
              max={12}
              step={0.5}
              unit="pt"
              issues={issues}
              path="interior.solution_pages.caption_size"
              onChange={(caption_size) => set('solution_pages', { caption_size })}
            />
            <NumberField
              id="interior-mark"
              label="Path outline weight"
              value={solution.mark_width}
              placeholder="Theme"
              min={0.75}
              max={2}
              step={0.25}
              unit="pt"
              issues={issues}
              path="interior.solution_pages.mark_width"
              onChange={(mark_width) => set('solution_pages', { mark_width })}
            />
            <NumberField
              id="interior-muted"
              label="Other letters"
              value={solution.muted_ink}
              placeholder="Theme"
              min={35}
              max={65}
              step={5}
              unit="% black"
              issues={issues}
              path="interior.solution_pages.muted_ink"
              onChange={(muted_ink) => set('solution_pages', { muted_ink })}
            />
          </div>
        )}
        <p className="small muted">
          Found words print black and bold inside their outlines; other letters print in gray, so
          paths stay distinct from the grid and from any decoration.
        </p>
      </section>
      <button
        type="button"
        className="small-button"
        onClick={() => {
          setPerPage(4);
          if (style) {
            const next = { ...style };
            delete next.solution_pages;
            p.change(next);
          }
        }}
      >
        Reset answer layout
      </button>
    </>
  );
}

// ------------------------------------------------------------------ theme

const LOOK_CONTROLS: [keyof LookOverrides, string, [string, string][]][] = [
  [
    'banner',
    'Headings and banners',
    [
      ['none', 'Plain'],
      ['rule', 'Heavy rule'],
      ['outline', 'Outlined'],
      ['solid', 'Solid'],
    ],
  ],
  [
    'corners',
    'Frames and banners',
    [
      ['square', 'Square'],
      ['rounded', 'Rounded'],
    ],
  ],
  [
    'background',
    'Background',
    [
      ['none', 'None'],
      ['header_band', 'Tint behind the header'],
      ['frame', 'Page frame'],
    ],
  ],
  [
    'motif',
    'Decoration',
    [
      ['none', 'None'],
      ['stripes', 'Angled stripes'],
      ['chevrons', 'Chevrons'],
    ],
  ],
  [
    'motif_intensity',
    'Decoration intensity',
    [
      ['subtle', 'Subtle'],
      ['medium', 'Medium'],
      ['bold', 'Bold'],
    ],
  ],
  [
    'density',
    'Spacing',
    [
      ['compact', 'Compact'],
      ['balanced', 'Balanced'],
      ['spacious', 'Spacious'],
    ],
  ],
  [
    'folio_style',
    'Page numbers',
    [
      ['plain', 'Plain'],
      ['rule', 'Short rule'],
      ['outline', 'Boxed'],
    ],
  ],
];

export function ThemePanel(p: PanelProps) {
  const { style, issues, setTop, catalogue, preview } = p;
  const v2 = style?.version === 2;
  if (!style || !v2)
    return (
      <section className="interior-section" aria-labelledby="theme-version">
        <h3 id="theme-version">Theme</h3>
        <VersionCard style={style} change={p.change} />
        {style?.version === 1 && (
          <ul className="preset-list" aria-label="Interior presets">
            {V1_PRESETS.map(([key, name, description]) => (
              <li key={key}>
                <label className="check">
                  <input
                    type="radio"
                    name="interior-preset"
                    checked={style.preset === key}
                    onChange={() => p.change({ ...style, preset: key })}
                  />
                  <span>
                    <strong>{name}</strong>
                    <small>{description}</small>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <FieldErrors id="interior" issues={sectionIssues(issues, 'interior')} />
      </section>
    );
  const theme = catalogue?.themes.find((t) => t.id === (style.theme ?? 'classic'));
  const look = preview?.design?.look;
  const themeLook = theme?.look as Record<string, unknown> | undefined;
  return (
    <>
      <section className="interior-section" aria-labelledby="theme-choice">
        <h3 id="theme-choice">Theme</h3>
        <p className="small muted">
          This interior prints in black ink: every colour prints as the gray of its brightness, and
          the preview is that print simulation. Themes apply to puzzle, word-list, answer and
          divider pages alike.
        </p>
        <ul className="preset-list" aria-label="Themes">
          {(catalogue?.themes ?? []).map((item) => (
            <li key={item.id}>
              <label className="check">
                <input
                  type="radio"
                  name="interior-theme"
                  checked={(style.theme ?? 'classic') === item.id}
                  onChange={() => setTop({ theme: item.id })}
                />
                <span>
                  <strong>
                    <span
                      className="swatch"
                      aria-hidden="true"
                      style={{ background: item.look.accent }}
                    />
                    <span
                      className="swatch"
                      aria-hidden="true"
                      style={{ background: item.look.secondary }}
                    />
                    {item.name}
                  </strong>
                  <small>{item.description}</small>
                </span>
              </label>
            </li>
          ))}
        </ul>
        <FieldErrors id="interior.theme" issues={matchIssues(issues, 'interior.theme')} />
      </section>
      <section className="interior-section" aria-labelledby="theme-colours">
        <h3 id="theme-colours">Accents</h3>
        <div className="field-grid">
          {(['accent', 'secondary'] as const).map((key) => {
            const value = style.colors?.[key];
            const shown = value ?? (themeLook?.[key] as string | undefined) ?? '#000000';
            const gray = look
              ? key === 'accent'
                ? look.accent_gray
                : look.secondary_gray
              : undefined;
            const path = `interior.colors.${key}`;
            return (
              <div key={key} className="editor-field colour-field">
                <label htmlFor={`interior-colour-${key}`}>
                  {key === 'accent' ? 'Accent' : 'Secondary (banners)'}
                </label>
                <div>
                  <input
                    id={`interior-colour-${key}`}
                    type="color"
                    value={shown}
                    onChange={(e) =>
                      setTop({ colors: prune({ ...style.colors, [key]: e.target.value }) })
                    }
                  />
                  <span className="small">
                    {value ? value : 'Theme'} · prints as {ink(gray)}
                  </span>
                  {value && (
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => {
                        const colors = prune({ ...style.colors, [key]: undefined });
                        setTop({ colors: Object.keys(colors).length ? colors : undefined });
                      }}
                    >
                      Use theme colour
                    </button>
                  )}
                </div>
                <FieldErrors id={path} issues={matchIssues(issues, path)} />
              </div>
            );
          })}
        </div>
      </section>
      <section className="interior-section" aria-labelledby="theme-look">
        <h3 id="theme-look">Treatments</h3>
        {LOOK_CONTROLS.map(([key, legend, options]) => (
          <Segmented
            key={key}
            legend={legend}
            value={(style[key] as string | undefined) ?? (themeLook?.[key] as string | undefined)}
            path={`interior.${key}`}
            issues={issues}
            options={options}
            onChange={(value) =>
              setTop({
                [key]: value === themeLook?.[key] ? undefined : value,
              } as Partial<InteriorStyle>)
            }
          />
        ))}
        <p className="small muted">
          Decoration stays inside the margins, clear of the gutter, text and grids; Python refuses
          any layout where it would touch them.
        </p>
        <button
          type="button"
          className="small-button"
          onClick={() => {
            const next = { ...style };
            delete next.colors;
            for (const [key] of LOOK_CONTROLS) delete next[key];
            p.change(next);
          }}
        >
          Reset to the theme
        </button>
      </section>
      <DesignFiles {...p} />
    </>
  );
}

// Named designs travel as validated JSON files: never photographs, book details or code.
function DesignFiles(p: PanelProps) {
  const { style, base, draft } = p;
  const [name, setName] = useState('');
  const [message, setMessage] = useState('');
  const [problems, setProblems] = useState<Issue[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const exportDesign = async () => {
    setMessage('');
    setProblems([]);
    const response = await fetch(`${base}/draft/interior/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: draft, name }),
    }).catch(() => undefined);
    if (!response?.ok) {
      const data = (await response?.json().catch(() => null)) as {
        error?: { message: string };
      } | null;
      setMessage(data?.error?.message ?? 'Studio could not export this design.');
      return;
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') ?? '';
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'design.json';
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
    setMessage(`Exported ${filename}.`);
  };
  const importDesign = async (file: File) => {
    setMessage('');
    setProblems([]);
    const controller = new AbortController();
    try {
      const result = await request<DesignImport>(
        `${base}/draft/interior/import`,
        controller.signal,
        { source: draft, text: await file.text() },
      );
      if (!result.success || !result.interior) {
        setProblems(result.issues ?? []);
        setMessage(`${file.name} is not a usable design file.`);
        return;
      }
      p.change(result.interior);
      setMessage(`Applied “${result.name}” to the draft. Review the preview, then save.`);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Studio could not read that file.');
    }
  };
  return (
    <section className="interior-section" aria-labelledby="theme-files">
      <h3 id="theme-files">Saved designs</h3>
      <p className="small muted">
        Save this design as a file to reuse it in another book. Files hold presentation only: no
        book details, puzzles, page structure or photographs.
      </p>
      <div className="field-pair">
        <div className="editor-field">
          <label htmlFor="interior-design-name">Design name</label>
          <input
            id="interior-design-name"
            value={name}
            maxLength={80}
            placeholder="Automotive Racing"
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <button
          type="button"
          className="small-button"
          disabled={!style || !name.trim()}
          onClick={() => void exportDesign()}
        >
          Export design
        </button>
      </div>
      <input
        ref={input}
        type="file"
        accept="application/json,.json"
        className="sr-only"
        aria-label="Design file to import"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (file) void importDesign(file);
        }}
      />
      <button type="button" className="small-button" onClick={() => input.current?.click()}>
        Import a design…
      </button>
      <p role="status" aria-live="polite" className="small">
        {message}
      </p>
      {problems.length > 0 && (
        <ul className="field-errors small">
          {problems.map((issue, i) => (
            <li key={i}>
              {issue.path}: {issue.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ title page and dividers

function themesOf(source: Source) {
  const themes: string[] = [];
  for (const puzzle of source.word_search?.puzzles ?? [])
    if (themes.at(-1) !== puzzle.theme) themes.push(puzzle.theme);
  return themes;
}

export function TitleDividersPanel(p: PanelProps) {
  const { style, issues, set, draft, photos } = p;
  const composition = draft.composition!;
  const title = style?.title_page ?? {};
  const unset = style?.version === 1 ? 'Preset' : 'Default';
  const dividerStyle = style?.dividers ?? {};
  const dividers = composition.puzzles.dividers;
  const setDividers = (next: typeof dividers) => {
    const puzzles = { ...composition.puzzles };
    if (next) puzzles.dividers = next;
    else delete puzzles.dividers;
    p.setComposition({ ...composition, puzzles });
  };
  const themes = themesOf(draft);
  const entry = (theme: string): ThemeDivider =>
    dividers?.themes.find((t) => t.theme === theme) ?? { theme };
  const setEntry = (theme: string, patch: Partial<ThemeDivider>) => {
    if (!dividers) return;
    const merged = prune({ ...entry(theme), ...patch });
    const others = dividers.themes.filter((t) => t.theme !== theme);
    const keep = Object.keys(merged).length > 1;
    const ordered = [...others, ...(keep ? [merged] : [])].sort(
      (a, b) => themes.indexOf(a.theme) - themes.indexOf(b.theme),
    );
    setDividers({ ...dividers, themes: ordered });
  };
  const photoChoice = (
    id: string,
    label: string,
    value: { path: string } | undefined,
    onChoose: (asset: CoverAsset | undefined) => void,
  ) => (
    <div className="editor-field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={value?.path ?? ''}
        onChange={(e) => onChoose(photos.find((ph) => ph.path === e.target.value))}
      >
        <option value="">No photograph</option>
        {photos.map((photo) => (
          <option key={photo.path} value={photo.path}>
            {photo.path.replace('cover-assets/', '')}
          </option>
        ))}
      </select>
      <p className="small muted field-hint">
        Printed in grayscale by Python, inside the margins. Import photos in Cover.
      </p>
    </div>
  );
  return (
    <>
      {style && (
        <section className="interior-section" aria-labelledby="interior-title">
          <h3 id="interior-title">Title page</h3>
          <Segmented
            legend="Layout"
            value={title.layout ?? 'preset'}
            path="interior.title_page.layout"
            issues={issues}
            options={[
              ['preset', unset],
              ['minimal', 'Minimal'],
              ['editorial', 'Editorial'],
              ['color_block', 'Tinted block'],
              ['framed', 'Framed'],
              ['photo_feature', 'Photo feature'],
            ]}
            onChange={(layout) =>
              set('title_page', {
                layout: layout === 'preset' ? undefined : layout,
                photo: layout === 'photo_feature' ? title.photo : undefined,
              })
            }
          />
          <div className="field-grid">
            <NumberField
              id="interior-title-tint"
              label="Tint"
              value={title.tint}
              placeholder={unset}
              min={0}
              max={100}
              step={5}
              unit="% black"
              issues={issues}
              path="interior.title_page.tint"
              onChange={(tint) => set('title_page', { tint })}
            />
            <NumberField
              id="interior-title-size"
              label="Title size"
              value={title.title_size}
              placeholder={unset}
              min={18}
              max={48}
              step={1}
              unit="pt"
              issues={issues}
              path="interior.title_page.title_size"
              onChange={(title_size) => set('title_page', { title_size })}
            />
          </div>
          <Segmented
            legend="Alignment"
            value={title.align ?? 'preset'}
            options={[
              ['preset', unset],
              ['center', 'Centered'],
              ['left', 'Left'],
            ]}
            onChange={(align) =>
              set('title_page', { align: align === 'preset' ? undefined : align })
            }
          />
          <label className="check">
            <input
              type="checkbox"
              checked={title.rule ?? true}
              onChange={(e) => set('title_page', { rule: e.target.checked ? undefined : false })}
            />
            <span>Short rule under the title</span>
          </label>
          {title.layout === 'photo_feature' &&
            photoChoice(
              'interior-title-photo',
              'Title page photograph',
              title.photo?.image,
              (asset) =>
                set('title_page', {
                  photo: asset
                    ? {
                        image: { path: asset.path, sha256: asset.sha256! },
                        crop: title.photo?.crop ?? { x: 0.5, y: 0.5, zoom: 1 },
                      }
                    : undefined,
                }),
            )}
          <FieldErrors
            id="interior.title_page"
            issues={matchIssues(issues, 'interior.title_page')}
          />
        </section>
      )}
      <section className="interior-section" aria-labelledby="interior-dividers">
        <h3 id="interior-dividers">Theme dividers</h3>
        <p className="small muted">
          A divider page before each theme group, with only the words you write. These are real
          pages: the page count changes, so the cover must be rebuilt afterwards. Each theme&apos;s
          puzzles must be together in the book order.
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={Boolean(dividers)}
            onChange={(e) =>
              setDividers(e.target.checked ? { start: 'any', themes: [] } : undefined)
            }
          />
          <span>Add theme divider pages ({themes.length} theme groups)</span>
        </label>
        {dividers && (
          <>
            <Segmented
              legend="Divider pages start"
              value={dividers.start}
              path="composition.puzzles.dividers.start"
              issues={issues}
              options={[
                ['any', 'On the next page'],
                ['recto', 'On a right-hand page'],
              ]}
              onChange={(start) => setDividers({ ...dividers, start })}
            />
            {style && (
              <div className="field-grid">
                <Segmented
                  legend="Divider layout"
                  value={dividerStyle.layout ?? 'preset'}
                  options={[
                    ['preset', 'As the theme'],
                    ['centered', 'Centered'],
                    ['framed', 'Framed'],
                    ['band', 'Tinted band'],
                  ]}
                  onChange={(layout) =>
                    set('dividers', { layout: layout === 'preset' ? undefined : layout })
                  }
                />
                <NumberField
                  id="interior-divider-tint"
                  label="Tint"
                  value={dividerStyle.tint}
                  placeholder="Theme"
                  min={0}
                  max={100}
                  step={5}
                  unit="% black"
                  issues={issues}
                  path="interior.dividers.tint"
                  onChange={(tint) => set('dividers', { tint })}
                />
              </div>
            )}
            <ol className="divider-list">
              {themes.map((theme, index) => {
                const value = entry(theme);
                const position = dividers.themes.findIndex((t) => t.theme === theme);
                const path = `composition.puzzles.dividers.themes.${position}`;
                const photo = dividerStyle.photos?.find((ph) => ph.theme === theme);
                return (
                  <li key={theme}>
                    <h4>{theme}</h4>
                    <div className="editor-field">
                      <label htmlFor={`divider-title-${index}`}>Title</label>
                      <input
                        id={`divider-title-${index}`}
                        value={value.title ?? ''}
                        placeholder={theme}
                        onChange={(e) => setEntry(theme, { title: e.target.value || undefined })}
                      />
                    </div>
                    <div className="editor-field">
                      <label htmlFor={`divider-text-${index}`}>Introduction (optional)</label>
                      <textarea
                        id={`divider-text-${index}`}
                        rows={2}
                        value={value.text ?? ''}
                        onChange={(e) => setEntry(theme, { text: e.target.value || undefined })}
                      />
                    </div>
                    <div className="field-pair">
                      <div className="editor-field">
                        <label htmlFor={`divider-quote-${index}`}>Quote (yours, optional)</label>
                        <input
                          id={`divider-quote-${index}`}
                          value={value.quote ?? ''}
                          onChange={(e) =>
                            setEntry(theme, {
                              quote: e.target.value || undefined,
                              attribution: e.target.value ? value.attribution : undefined,
                            })
                          }
                        />
                      </div>
                      <div className="editor-field">
                        <label htmlFor={`divider-attribution-${index}`}>Attribution</label>
                        <input
                          id={`divider-attribution-${index}`}
                          value={value.attribution ?? ''}
                          disabled={!value.quote}
                          onChange={(e) =>
                            setEntry(theme, { attribution: e.target.value || undefined })
                          }
                        />
                      </div>
                    </div>
                    {style &&
                      photoChoice(
                        `divider-photo-${index}`,
                        'Divider photograph',
                        photo?.image,
                        (asset) => {
                          const others = (dividerStyle.photos ?? []).filter(
                            (ph) => ph.theme !== theme,
                          );
                          const next = asset
                            ? [
                                ...others,
                                {
                                  theme,
                                  image: { path: asset.path, sha256: asset.sha256! },
                                  crop: photo?.crop ?? { x: 0.5, y: 0.5, zoom: 1 },
                                },
                              ]
                            : others;
                          set('dividers', { photos: next.length ? next : undefined });
                        },
                      )}
                    {position >= 0 && <FieldErrors id={path} issues={matchIssues(issues, path)} />}
                  </li>
                );
              })}
            </ol>
            <p className="small muted">
              PuzzlePress never supplies quotations or sources; leave a quote empty unless it is
              yours or you have checked it.
            </p>
          </>
        )}
        <FieldErrors
          id="composition.puzzles.dividers"
          issues={matchIssues(issues, 'composition.puzzles.dividers')}
        />
      </section>
    </>
  );
}
