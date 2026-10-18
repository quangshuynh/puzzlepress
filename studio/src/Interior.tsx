import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from './api';
import { Segmented, Tabs } from './cover-tools';
import { DraftToolbar, type Draft } from './draft';
import type { Source } from './editor-fields';
import {
  AnswerLayoutPanel,
  NEW_DESIGN,
  PageLayoutPanel,
  ThemePanel,
  TitleDividersPanel,
  prune,
  type PanelProps,
  type StyleSection,
} from './interior-panels';
import type {
  CoverAsset,
  DesignCatalogue,
  InteriorDraft,
  InteriorStatus,
  InteriorStyle,
  SampleRole,
} from './types';
import { Loading, Status } from './ui';

// Interior design: page layout, answer layout, theme, title page and dividers.
// Settings are authored source in book.yaml (`composition` for pagination, the
// `interior` style for presentation). Python resolves themes, lays out the whole
// draft book and renders representative pages; nothing here draws a page.

// Draft previews fail fast while Studio is busy; retry this many times, a second apart.
const BUSY_RETRIES = 5;

type Tab = 'page' | 'answers' | 'theme' | 'title';
const TABS: [Tab, string][] = [
  ['page', 'Page layout'],
  ['answers', 'Answer layout'],
  ['theme', 'Theme'],
  ['title', 'Title & dividers'],
];
// Preview views, each a role Python assigned to a rendered page.
const VIEWS: [string, string, SampleRole[]][] = [
  ['spread', 'Puzzle spread', ['spread_left', 'spread_right']],
  ['puzzle', 'Puzzle page', ['puzzle']],
  ['answers', 'Answer page', ['answers']],
  ['answers_last', 'Last answer page', ['answers_last']],
  ['divider', 'Divider', ['divider']],
  ['instructions', 'Instructions', ['instructions']],
  ['title', 'Title page', ['title']],
];
const LABELS: Record<string, string> = {
  title_page: 'title page',
  puzzle_words: 'word list',
  puzzle: 'puzzle',
  solutions: 'answers',
  divider: 'divider',
  instructions: 'instructions',
};

function initialTab(): Tab {
  const hash = window.location.hash.replace('#', '');
  return (TABS.find(([key]) => key === hash)?.[0] as Tab | undefined) ?? 'page';
}

export function Interior({ d }: { d: Draft }) {
  const style = d.draft.interior;
  const composition = d.draft.composition;
  const [tab, setTab] = useState<Tab>(initialTab);
  const [view, setView] = useState('spread');
  const [preview, setPreview] = useState<InteriorDraft>();
  const [previewError, setPreviewError] = useState('');
  const [pending, setPending] = useState(false);
  const [built, setBuilt] = useState<InteriorStatus>();
  const [photos, setPhotos] = useState<CoverAsset[]>([]);
  const [catalogue, setCatalogue] = useState<DesignCatalogue>();
  const base = `/api/projects/${encodeURIComponent(d.key)}`;
  const latest = useRef(d.draft);
  latest.current = d.draft;
  const signature = JSON.stringify([style, composition, d.draft.word_search, d.draft.book]);

  useEffect(() => {
    const controller = new AbortController();
    request<InteriorStatus>(`${base}/interior`, controller.signal)
      .then((data) => !controller.signal.aborted && setBuilt(data))
      .catch(() => undefined);
    request<{ assets: CoverAsset[] }>(`${base}/cover/assets`, controller.signal)
      .then((data) => !controller.signal.aborted && setPhotos(data.assets.filter((a) => a.sha256)))
      .catch(() => undefined);
    request<DesignCatalogue>('/api/interior/designs', controller.signal)
      .then((data) => !controller.signal.aborted && setCatalogue(data))
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
        <p>Interior design applies to a composed book. Compose it in Book first.</p>
      </section>
    );

  const change = (next: InteriorStyle | undefined) => {
    const draft = { ...d.draft } as Source;
    if (next) draft.interior = next;
    else delete draft.interior;
    d.change(draft);
  };
  // Settings only exist inside a design section; the first edit adds one.
  const current = (): InteriorStyle => style ?? { ...NEW_DESIGN };
  const set = <K extends StyleSection>(
    section: K,
    patch: Partial<NonNullable<InteriorStyle[K]>>,
  ) => {
    const base = current();
    const merged = prune({ ...(base[section] ?? {}), ...patch } as NonNullable<InteriorStyle[K]>);
    const next = { ...base, [section]: merged } as InteriorStyle;
    if (!Object.keys(merged).length) delete next[section];
    change(next);
  };
  const setTop = (patch: Partial<InteriorStyle>) => change(prune({ ...current(), ...patch }));
  const setComposition = (next: NonNullable<Source['composition']>) =>
    d.change({ ...d.draft, composition: next } as Source);
  const show = (next: string) => {
    setView(next);
    document.getElementById('interior-preview')?.focus();
  };
  const props: PanelProps = {
    draft: d.draft,
    style,
    issues: d.issues,
    preview,
    catalogue,
    photos,
    base,
    change,
    set,
    setTop,
    setComposition,
    show,
  };

  const pages = preview?.success ? (preview.pages ?? []) : [];
  const available = VIEWS.filter(([, , roles]) =>
    roles.every((role) => pages.some((p) => p.roles.includes(role))),
  );
  const chosen = available.find(([key]) => key === view) ?? available[0];
  const shown = chosen ? chosen[2].map((role) => pages.find((p) => p.roles.includes(role))!) : [];
  const builtPages = built?.preview?.page_count ?? built?.report?.page_count;
  const savedSource = d.saved.source as Source | undefined;
  const designChanged =
    JSON.stringify([d.draft.interior, d.draft.composition]) !==
    JSON.stringify([savedSource?.interior, savedSource?.composition]);
  const pageCountChanged =
    preview?.success && builtPages !== undefined && builtPages !== preview.page_count;
  const warnings = (preview?.warnings ?? []).filter((w) => w.code !== 'kdp_minimum_page_count');

  return (
    <div className="editor interior-design">
      <DraftToolbar
        d={d}
        title="Interior design"
        jump={{ href: '#interior-preview', label: 'Jump to preview' }}
      />
      <div className="interior-layout">
        <form aria-label="Interior design" onSubmit={(e) => e.preventDefault()}>
          <Tabs
            label="Interior design sections"
            tabs={TABS}
            value={tab}
            idPrefix="interior"
            onChange={(next) => {
              setTab(next);
              if (next === 'answers') setView('answers');
              else if (next === 'title') setView('title');
              else if (view === 'answers' || view === 'title') setView('spread');
            }}
          />
          <div role="tabpanel" id={`interior-panel-${tab}`} aria-labelledby={`interior-tab-${tab}`}>
            <fieldset className="authoring-fields" disabled={d.busy}>
              <legend className="sr-only">{TABS.find(([key]) => key === tab)![1]}</legend>
              {tab === 'page' && <PageLayoutPanel {...props} />}
              {tab === 'answers' && <AnswerLayoutPanel {...props} />}
              {tab === 'theme' && <ThemePanel {...props} />}
              {tab === 'title' && <TitleDividersPanel {...props} />}
              {style && (
                <p className="reset-all">
                  <button
                    type="button"
                    className="small-button"
                    onClick={() => {
                      if (
                        window.confirm(
                          'Reset every interior design setting in this draft to the classic defaults? Revert undoes it until you save.',
                        )
                      )
                        change(undefined);
                    }}
                  >
                    Reset the whole design to defaults
                  </button>
                </p>
              )}
            </fieldset>
          </div>
        </form>
        <section
          className="interior-preview"
          id="interior-preview"
          tabIndex={-1}
          aria-labelledby="interior-preview-heading"
        >
          <div className="section-heading">
            <h3 id="interior-preview-heading">Preview</h3>
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
                    {item.message}
                    {item.physical_page ? ` (page ${item.physical_page})` : ''}{' '}
                    <code>{item.code}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {preview?.success && (
            <>
              {available.length > 1 && chosen && (
                <Segmented
                  legend="Show"
                  value={chosen[0]}
                  options={available.map(([key, label]) => [key, label] as const)}
                  onChange={setView}
                />
              )}
              <div className={`preview-pages${shown.length > 1 ? ' spread' : ''}`}>
                {shown.map((page) => (
                  <figure key={page.index}>
                    <img
                      src={`${base}/draft/interior/pages/${page.index}?size=page&pdf=${preview.pdf_sha256}`}
                      alt={`Draft ${LABELS[page.kind] ?? page.kind.replace('_', ' ')}, page ${page.physical_page}`}
                      width={612}
                      height={792}
                    />
                    <figcaption className="small muted">
                      {LABELS[page.kind] ?? page.kind} · page {page.physical_page}
                      {page.folio ? ` (printed ${page.folio})` : ''}
                    </figcaption>
                  </figure>
                ))}
              </div>
              <p className="small muted">
                Black-ink print simulation: rasters of the PDF Python rendered from this draft.
                Build the saved book in Print proof to check every page.
              </p>
              <p className="small">{preview.page_count} pages in this draft.</p>
              {warnings.length > 0 && (
                <ul className="finding-list">
                  {warnings.map((w, i) => (
                    <li key={i}>
                      <Status tone="review">Review</Status> {w.message}
                      {w.physical_page ? ` (page ${w.physical_page})` : ''}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          {(designChanged || pageCountChanged) && (
            <div className="impact-note" role="note" aria-label="What saving changes">
              <h4>What saving changes</h4>
              <ul className="small">
                {designChanged && (
                  <li>
                    The built interior no longer matches: rebuild it in{' '}
                    <a href={`/books/${encodeURIComponent(d.key)}/print`}>Print proof</a>. Proof
                    records for the old interior become stale.
                  </li>
                )}
                {pageCountChanged && (
                  <li>
                    <Status tone="review">Changes the page count</Status> from {builtPages} to{' '}
                    {preview?.page_count}: the cover spine changes, so rebuild the cover after the
                    interior.
                  </li>
                )}
                {designChanged && (
                  <li>
                    A publishing package exported earlier is out of date until you export again.
                  </li>
                )}
              </ul>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
