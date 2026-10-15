import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from './api';
import { NumberField } from './cover-inspector';
import { Segmented } from './cover-tools';
import { DraftToolbar, type Draft } from './draft';
import { FieldErrors, matchIssues, type Source } from './editor-fields';
import type {
  CoverAsset,
  InteriorDraft,
  InteriorStatus,
  InteriorStyle,
  Issue,
  ThemeDivider,
} from './types';
import { Loading, Status } from './ui';

// Interior design: the book's optional `interior` style and its theme dividers.
// Python resolves presets into renderer settings, lays out the whole draft book
// and renders a few sample pages; nothing here draws a page. Dividers are
// composition (real pages in the plan), so enabling them changes the page count.

// Draft previews fail fast while Studio is busy; retry this many times, a second apart.
const BUSY_RETRIES = 5;

type Section = 'title_page' | 'puzzle_pages' | 'solution_pages' | 'dividers';

const PRESETS: [InteriorStyle['preset'], string, string][] = [
  ['classic', 'Classic', 'The original PuzzlePress interior, unchanged.'],
  ['editorial', 'Editorial', 'Left-aligned headers, fine rules, page numbers outside.'],
  ['modern', 'Modern', 'Regular-weight titles, a framed title page, heavier grids.'],
  ['high_contrast', 'High contrast', 'Larger words, bold frames and solution marks.'],
];

function prune<T extends object>(value: T): T {
  const next = { ...value } as Record<string, unknown>;
  for (const [key, item] of Object.entries(next)) if (item === undefined) delete next[key];
  return next as T;
}

function themesOf(source: Source) {
  const themes: string[] = [];
  for (const puzzle of source.word_search?.puzzles ?? [])
    if (themes.at(-1) !== puzzle.theme) themes.push(puzzle.theme);
  return themes;
}

export function Interior({ d }: { d: Draft }) {
  const style = d.draft.interior;
  const composition = d.draft.composition;
  const issues: Issue[] = d.issues;
  const [preview, setPreview] = useState<InteriorDraft>();
  const [previewError, setPreviewError] = useState('');
  const [pending, setPending] = useState(false);
  const [built, setBuilt] = useState<InteriorStatus>();
  const [photos, setPhotos] = useState<CoverAsset[]>([]);
  const base = `/api/projects/${encodeURIComponent(d.key)}`;
  const latest = useRef(d.draft);
  latest.current = d.draft;
  const signature = JSON.stringify([style, composition, d.draft.word_search?.puzzles]);

  useEffect(() => {
    const controller = new AbortController();
    request<InteriorStatus>(`${base}/interior`, controller.signal)
      .then((data) => !controller.signal.aborted && setBuilt(data))
      .catch(() => undefined);
    request<{ assets: CoverAsset[] }>(`${base}/cover/assets`, controller.signal)
      .then((data) => !controller.signal.aborted && setPhotos(data.assets.filter((a) => a.sha256)))
      .catch(() => undefined);
    return () => controller.abort();
  }, [base, d.saved.revision]);

  useEffect(() => {
    if (!composition) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    // A short read (such as the interior status) can hold Studio's lock for a moment.
    const run = (attempt: number) => {
      setPending(true);
      request<InteriorDraft>(`${base}/draft/interior`, controller.signal, {
        source: latest.current,
      })
        .then((data) => {
          if (controller.signal.aborted) return;
          setPreview(data);
          setPreviewError('');
          setPending(false);
        })
        .catch((err: Error) => {
          if (controller.signal.aborted) return;
          const busy = err instanceof ApiError && err.code === 'generation_busy';
          if (busy && attempt < BUSY_RETRIES) {
            timer = setTimeout(() => run(attempt + 1), 1000);
            return;
          }
          setPreviewError(
            busy
              ? 'Studio is busy generating; the preview will refresh on your next edit.'
              : err.message,
          );
          setPending(false);
        });
    };
    timer = setTimeout(() => run(0), 600);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // `signature` captures every draft value the interior preview depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, signature]);

  if (!composition)
    return (
      <section className="notice">
        <h2>No book composition</h2>
        <p>Interior styles apply to a composed book. Compose it in Book first.</p>
      </section>
    );

  const change = (next: InteriorStyle | undefined) => {
    const draft = { ...d.draft } as Source;
    if (next) draft.interior = next;
    else delete draft.interior;
    d.change(draft);
  };
  const set = <K extends Section>(section: K, patch: Partial<NonNullable<InteriorStyle[K]>>) => {
    if (!style) return;
    const merged = prune({ ...(style[section] ?? {}), ...patch } as NonNullable<InteriorStyle[K]>);
    const next = { ...style, [section]: merged } as InteriorStyle;
    if (!Object.keys(merged).length) delete next[section];
    change(next);
  };
  const dividers = composition.puzzles.dividers;
  const setDividers = (next: typeof dividers) => {
    const puzzles = { ...composition.puzzles };
    if (next) puzzles.dividers = next;
    else delete puzzles.dividers;
    d.change({ ...d.draft, composition: { ...composition, puzzles } } as Source);
  };
  const themes = themesOf(d.draft);
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
  const builtPages = built?.preview?.page_count ?? built?.report?.page_count;
  const title = style?.title_page ?? {};
  const puzzle = style?.puzzle_pages ?? {};
  const solution = style?.solution_pages ?? {};
  const dividerStyle = style?.dividers ?? {};
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
        onChange={(e) => onChoose(photos.find((p) => p.path === e.target.value))}
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
    <div className="editor interior-design">
      <DraftToolbar
        d={d}
        title="Interior design"
        jump={{ href: '#interior-preview', label: 'Jump to preview' }}
      />
      <div className="interior-layout">
        <form aria-label="Interior style" onSubmit={(e) => e.preventDefault()}>
          <fieldset className="authoring-fields" disabled={d.busy}>
            <legend className="sr-only">Interior style</legend>
            <section className="interior-section" aria-labelledby="interior-presets">
              <h3 id="interior-presets">Preset</h3>
              <p className="small muted">
                Black ink on white or cream paper, no bleed: tints are percentages of black and
                nothing prints to the trimmed edge. Styles never change puzzles, seeds or the plan.
              </p>
              {!style ? (
                <div className="convert-card">
                  <p className="small">
                    This book uses the classic interior with no style section. Adding one records
                    the preset you choose; Classic draws exactly the same pages.
                  </p>
                  <button
                    type="button"
                    className="small-button"
                    onClick={() => change({ version: 1, preset: 'classic' })}
                  >
                    Add an interior style
                  </button>
                </div>
              ) : (
                <>
                  <ul className="preset-list" aria-label="Interior presets">
                    {PRESETS.map(([key, name, description]) => (
                      <li key={key}>
                        <label className="check">
                          <input
                            type="radio"
                            name="interior-preset"
                            checked={style.preset === key}
                            onChange={() => change({ ...style, preset: key })}
                          />
                          <span>
                            <strong>{name}</strong>
                            <small>{description}</small>
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                  <Segmented
                    legend="Page numbers"
                    value={style.folio ?? 'preset'}
                    options={[
                      ['preset', 'As the preset'],
                      ['center', 'Centered'],
                      ['outside', 'Outside edge'],
                    ]}
                    onChange={(folio) =>
                      change(prune({ ...style, folio: folio === 'preset' ? undefined : folio }))
                    }
                  />
                  <button type="button" className="small-button" onClick={() => change(undefined)}>
                    Remove the style section
                  </button>
                </>
              )}
              <FieldErrors id="interior" issues={matchIssues(issues, 'interior')} />
            </section>
            {style && (
              <>
                <section className="interior-section" aria-labelledby="interior-title">
                  <h3 id="interior-title">Title page</h3>
                  <Segmented
                    legend="Layout"
                    value={title.layout ?? 'preset'}
                    path="interior.title_page.layout"
                    issues={issues}
                    options={[
                      ['preset', 'Preset'],
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
                      placeholder="Preset"
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
                      placeholder="Preset"
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
                      ['preset', 'Preset'],
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
                      onChange={(e) =>
                        set('title_page', { rule: e.target.checked ? undefined : false })
                      }
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
                <section className="interior-section" aria-labelledby="interior-puzzles">
                  <h3 id="interior-puzzles">Puzzle pages</h3>
                  <p className="small muted">
                    Presentation only: grids, letters and word lists stay exactly as generated, and
                    grid letters never go below the profile minimum.
                  </p>
                  <Segmented
                    legend="Header alignment"
                    value={puzzle.header_align ?? 'preset'}
                    options={[
                      ['preset', 'Preset'],
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
                      placeholder="Preset"
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
                      label="Theme size"
                      value={puzzle.theme_size}
                      placeholder="Preset"
                      min={9}
                      max={14}
                      step={0.5}
                      unit="pt"
                      issues={issues}
                      path="interior.puzzle_pages.theme_size"
                      onChange={(theme_size) => set('puzzle_pages', { theme_size })}
                    />
                    <NumberField
                      id="interior-grid-frame"
                      label="Grid frame"
                      value={puzzle.grid_frame}
                      placeholder="Preset"
                      min={0.75}
                      max={3}
                      step={0.25}
                      unit="pt"
                      issues={issues}
                      path="interior.puzzle_pages.grid_frame"
                      onChange={(grid_frame) => set('puzzle_pages', { grid_frame })}
                    />
                    <NumberField
                      id="interior-word-size"
                      label="Word list size"
                      value={puzzle.word_size}
                      placeholder="Preset"
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
                      label="Word columns, at most"
                      value={puzzle.word_columns}
                      placeholder="Preset"
                      min={2}
                      max={5}
                      step={1}
                      issues={issues}
                      path="interior.puzzle_pages.word_columns"
                      onChange={(word_columns) => set('puzzle_pages', { word_columns })}
                    />
                  </div>
                  {(
                    [
                      ['title_bold', 'Bold puzzle titles', true],
                      ['theme_label', 'Show the theme under the title', true],
                      ['header_rule', 'Rule under the header', false],
                      ['word_rule', 'Rule above the word list', false],
                    ] as const
                  ).map(([key, label, fallback]) => (
                    <label key={key} className="check">
                      <input
                        type="checkbox"
                        checked={puzzle[key] ?? fallback}
                        onChange={(e) => set('puzzle_pages', { [key]: e.target.checked })}
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                  <FieldErrors
                    id="interior.puzzle_pages"
                    issues={matchIssues(issues, 'interior.puzzle_pages')}
                  />
                </section>
                <section className="interior-section" aria-labelledby="interior-solutions">
                  <h3 id="interior-solutions">Solution pages</h3>
                  <div className="field-grid">
                    <NumberField
                      id="interior-caption"
                      label="Caption size"
                      value={solution.caption_size}
                      placeholder="Preset"
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
                      label="Mark weight"
                      value={solution.mark_width}
                      placeholder="Preset"
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
                      placeholder="Preset"
                      min={35}
                      max={65}
                      step={5}
                      unit="% black"
                      issues={issues}
                      path="interior.solution_pages.muted_ink"
                      onChange={(muted_ink) => set('solution_pages', { muted_ink })}
                    />
                  </div>
                  <p className="small muted">
                    Found words print black and bold inside their outlines; other letters print in
                    gray so solutions read in black ink.
                  </p>
                </section>
              </>
            )}
            <section className="interior-section" aria-labelledby="interior-dividers">
              <h3 id="interior-dividers">Theme dividers</h3>
              <p className="small muted">
                A divider page before each theme group, with only the words you write. These are
                real pages: the page count changes, so the cover must be rebuilt afterwards. Each
                theme&apos;s puzzles must be together in the book order.
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
                          ['preset', 'Preset'],
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
                        placeholder="Preset"
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
                      const photo = dividerStyle.photos?.find((p) => p.theme === theme);
                      return (
                        <li key={theme}>
                          <h4>{theme}</h4>
                          <div className="editor-field">
                            <label htmlFor={`divider-title-${index}`}>Title</label>
                            <input
                              id={`divider-title-${index}`}
                              value={value.title ?? ''}
                              placeholder={theme}
                              onChange={(e) =>
                                setEntry(theme, { title: e.target.value || undefined })
                              }
                            />
                          </div>
                          <div className="editor-field">
                            <label htmlFor={`divider-text-${index}`}>Introduction (optional)</label>
                            <textarea
                              id={`divider-text-${index}`}
                              rows={2}
                              value={value.text ?? ''}
                              onChange={(e) =>
                                setEntry(theme, { text: e.target.value || undefined })
                              }
                            />
                          </div>
                          <div className="field-pair">
                            <div className="editor-field">
                              <label htmlFor={`divider-quote-${index}`}>
                                Quote (yours, optional)
                              </label>
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
                                  (p) => p.theme !== theme,
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
                          {position >= 0 && (
                            <FieldErrors id={path} issues={matchIssues(issues, path)} />
                          )}
                        </li>
                      );
                    })}
                  </ol>
                  <p className="small muted">
                    PuzzlePress never supplies quotations or sources; leave a quote empty unless it
                    is yours or you have checked it.
                  </p>
                </>
              )}
              <FieldErrors
                id="composition.puzzles.dividers"
                issues={matchIssues(issues, 'composition.puzzles.dividers')}
              />
            </section>
          </fieldset>
        </form>
        <section
          className="interior-preview"
          id="interior-preview"
          tabIndex={-1}
          aria-labelledby="interior-preview-heading"
        >
          <div className="section-heading">
            <h3 id="interior-preview-heading">Sample pages</h3>
            <span role="status" aria-live="polite" className="small muted">
              {pending
                ? 'Rendering the draft in Python…'
                : preview?.success
                  ? 'Matches the draft'
                  : ''}
            </span>
          </div>
          {previewError && <p className="field-errors small">{previewError}</p>}
          {!preview && !previewError && <Loading>Laying out the draft book in Python…</Loading>}
          {preview && !preview.success && (
            <div role="alert" className="notice error compact-notice">
              <h4>This draft does not lay out</h4>
              <ul className="issue-list">
                {preview.diagnostics?.map((item, i) => (
                  <li key={i}>
                    {item.message} <code>{item.code}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {preview?.success && (
            <>
              <p className="small">
                {preview.page_count} pages in this draft
                {builtPages !== undefined && builtPages !== preview.page_count && (
                  <>
                    {' '}
                    <Status tone="review">Changes the page count</Status> (built interior:{' '}
                    {builtPages}). Rebuild the interior and then the cover.
                  </>
                )}
              </p>
              {(preview.warnings ?? []).filter((w) => w.code !== 'kdp_minimum_page_count').length >
                0 && (
                <ul className="finding-list">
                  {preview
                    .warnings!.filter((w) => w.code !== 'kdp_minimum_page_count')
                    .map((w, i) => (
                      <li key={i}>
                        <Status tone="review">Review</Status> {w.message}
                        {w.physical_page ? ` (page ${w.physical_page})` : ''}
                      </li>
                    ))}
                </ul>
              )}
              <ul className="sample-pages">
                {preview.pages?.map((page) => (
                  <li key={page.index}>
                    <img
                      src={`${base}/draft/interior/pages/${page.index}?size=thumb&pdf=${preview.pdf_sha256}`}
                      alt={`Draft ${page.kind.replace('_', ' ')}, page ${page.physical_page}`}
                      width={306}
                      height={396}
                    />
                    <span className="small muted">
                      {page.kind.replace('_', ' ')} · page {page.physical_page}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="small muted">
                Rasters of a PDF Python rendered from the draft: the first page of each kind. Build
                the saved book in Print proof to check every page.
              </p>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
