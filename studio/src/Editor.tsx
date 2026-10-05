import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from './api';
import { Inspector, Quality } from './Puzzles';
import type { Definition, Generation, Issue, Project } from './types';
import { Empty, Issues } from './ui';
import { ContentEditor } from './ContentEditor';

import { Field, move, type Source, type Content } from './editor-fields';

export function Editor({
  project,
  onSaved,
  onDirty,
}: {
  project: Project;
  onSaved: (project: Project) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const [saved, setSaved] = useState(project);
  const [draft, setDraft] = useState<Source>(() => structuredClone(project.source!));
  const [selected, setSelected] = useState(0);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [error, setError] = useState<Error>();
  const [message, setMessage] = useState('Ready to edit. Source has not changed.');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Generation>();
  const [view, setView] = useState<'puzzle' | 'quality'>('puzzle');
  const version = useRef(0);
  const active = useRef<AbortController | null>(null);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved.source);
  useEffect(() => {
    onDirty(dirty);
  }, [dirty, onDirty]);
  useEffect(
    () => () => {
      active.current?.abort();
      onDirty(false);
    },
    [onDirty],
  );
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  function change(next: Source) {
    version.current++;
    setDraft(next);
    setPreview(undefined);
    setIssues([]);
    setError(undefined);
    setMessage('Draft changed. Validate or preview to check these edits.');
  }
  function content(next: Content) {
    change({ ...draft, word_search: next });
  }
  function updatePuzzle(patch: Partial<Definition>) {
    if (!draft.word_search) return;
    content({
      ...draft.word_search,
      puzzles: draft.word_search.puzzles.map((p, i) => (i === selected ? { ...p, ...patch } : p)),
    });
  }
  function accept(next: Project) {
    if (!next.source || !next.revision || !next.validation?.valid)
      throw new ApiError(
        'Studio received an incomplete saved project. Reload to review.',
        'malformed_response',
      );
    setSaved(next);
    setDraft(structuredClone(next.source));
    setPreview(undefined);
    setIssues([]);
    setSelected(0);
    onSaved(next);
  }
  async function run(action: 'validate' | 'preview' | 'save' | 'reload') {
    if (busy) return;
    const controller = new AbortController();
    active.current = controller;
    const current = version.current;
    setBusy(true);
    setError(undefined);
    setIssues([]);
    setMessage(action === 'preview' ? 'Generating and checking the draft…' : 'Checking project…');
    try {
      const url = `/api/projects/${encodeURIComponent(project.key)}`;
      const data = await request<Project | Generation>(
        action === 'reload' ? url : `${url}/draft/${action}`,
        controller.signal,
        action === 'reload'
          ? undefined
          : { source: draft, ...(action === 'save' ? { revision: saved.revision } : {}) },
      );
      if (controller.signal.aborted || version.current !== current) return;
      if (action === 'preview') {
        const result = data as Generation;
        if (!result.report?.puzzles || !result.solution_cells || !result.verification)
          throw new ApiError(
            'Studio received an incomplete preview. Retry preview.',
            'malformed_response',
          );
        setPreview(result);
        setMessage('Draft preview ready. Source has not changed.');
      } else if (action === 'validate') {
        if (!(data as Project).validation?.valid)
          throw new ApiError(
            'Studio received an incomplete validation result.',
            'malformed_response',
          );
        setMessage('Draft is valid. Python accepted the proposed project.');
      } else {
        accept(data as Project);
        setMessage(
          action === 'save' ? 'Saved and reloaded from source.' : 'Saved source reloaded.',
        );
      }
    } catch (err) {
      if (!controller.signal.aborted && version.current === current) {
        setError(err as Error);
        setIssues(err instanceof ApiError ? err.issues : []);
        setMessage('The operation did not complete. Your draft is retained.');
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const ws = draft.word_search;
  const puzzle = ws?.puzzles[selected];
  const path = `word_search.puzzles.${selected}`;
  const result = preview?.report.puzzles[selected];
  return (
    <div className="editor">
      <div className="editor-toolbar">
        <div>
          <h2>Authoring desk</h2>
          <p className={dirty ? 'draft-status' : 'muted'}>
            {dirty ? 'Unsaved changes' : 'Saved source'}
          </p>
        </div>
        <div className="editor-actions">
          <a href="#draft-preview">Jump to preview</a>
          <button type="button" disabled={busy} onClick={() => void run('validate')}>
            Validate draft
          </button>
          <button type="button" disabled={busy || !ws} onClick={() => void run('preview')}>
            Preview draft
          </button>
          <button
            type="button"
            className="primary"
            disabled={busy || !dirty}
            onClick={() => void run('save')}
          >
            Save changes
          </button>
          <button
            type="button"
            disabled={busy || !dirty}
            onClick={() => {
              if (window.confirm('Discard unsaved edits and return to the source you opened?')) {
                change(structuredClone(saved.source!));
                setSelected(0);
                setMessage('Draft reverted to the saved source you opened.');
              }
            }}
          >
            Revert draft
          </button>
        </div>
      </div>
      <p className="small muted">
        Save writes normalized YAML. Comments, quoting and original formatting are not preserved.
      </p>
      <p role="status" aria-live="polite">
        {message}
      </p>
      {error && (
        <div role="alert" className="notice error">
          <h3>
            {error instanceof ApiError && error.code === 'source_changed'
              ? 'Saved source has changed'
              : 'Could not complete the request'}
          </h3>
          <p>{error.message}</p>
          <Issues issues={issues} />
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  'Reload the latest saved source and discard this draft? Copy any edits you want to keep first.',
                )
              )
                void run('reload');
            }}
          >
            Reload saved source
          </button>
        </div>
      )}
      <div className="editor-layout">
        <form aria-label="Project authoring" onSubmit={(event) => event.preventDefault()}>
          <fieldset className="authoring-fields" disabled={busy}>
            <legend className="sr-only">Project draft</legend>
            <details className="editor-settings">
              <summary>Book title & shared seed</summary>
              <Field
                label="Book title"
                path="book.title"
                value={draft.book.title}
                issues={issues}
                onChange={(title) => change({ ...draft, book: { ...draft.book, title } })}
              />
              <Field
                label="Project seed"
                path="build.seed"
                value={draft.build.seed}
                issues={issues}
                onChange={(seed) => change({ ...draft, build: { seed } })}
              />
              <p className="small muted">
                Shared by every puzzle. Puzzle IDs determine their individual seeds; changing an ID
                changes its grid.
              </p>
            </details>
            {!ws ? (
              <Empty title="No word-search content">
                <span>
                  This legacy project has no banks, profiles or puzzle definitions. Add its first
                  word-search content explicitly.
                </span>
                <button
                  type="button"
                  onClick={() =>
                    content({
                      banks: [{ id: 'words', entries: [{ id: 'word-1', display: '' }] }],
                      profiles: [
                        {
                          id: 'custom',
                          width: 10,
                          height: 10,
                          directions: ['right', 'down'],
                          max_restarts: 20,
                          max_attempts: 100000,
                        },
                      ],
                      puzzles: [
                        {
                          id: 'puzzle-1',
                          title: 'New puzzle',
                          theme: '',
                          bank: 'words',
                          target_ids: ['word-1'],
                          difficulty: 'custom',
                        },
                      ],
                      quality: {
                        max_word_reuse: 2,
                        target_similarity_threshold: 0.8,
                        grid_similarity_threshold: 0.9,
                        prohibited_words: [],
                      },
                    })
                  }
                >
                  Add word-search content
                </button>
              </Empty>
            ) : (
              <>
                <div className="section-heading">
                  <h3>Puzzle definitions</h3>
                  <button
                    type="button"
                    onClick={() => {
                      let n = 1;
                      while (ws.puzzles.some((p) => p.id === `puzzle-${n}`)) n++;
                      content({
                        ...ws,
                        puzzles: [
                          ...ws.puzzles,
                          {
                            id: `puzzle-${n}`,
                            title: 'New puzzle',
                            theme: '',
                            bank: ws.banks[0]?.id ?? '',
                            target_ids: [],
                            difficulty: ws.profiles[0]?.id ?? '',
                          },
                        ],
                      });
                      setSelected(ws.puzzles.length);
                    }}
                  >
                    Add puzzle
                  </button>
                </div>
                <ol className="definition-list">
                  {ws.puzzles.map((p, i) => (
                    <li key={i}>
                      <button
                        type="button"
                        className="definition-select"
                        aria-pressed={i === selected}
                        onClick={() => setSelected(i)}
                      >
                        <span>{i + 1}.</span> {p.title || 'Untitled puzzle'}
                      </button>
                      <button
                        type="button"
                        aria-label={`Move puzzle ${i + 1} up`}
                        disabled={i === 0}
                        onClick={() => {
                          content({ ...ws, puzzles: move(ws.puzzles, i, -1) });
                          setSelected(i - 1);
                        }}
                      >
                        Up
                      </button>
                      <button
                        type="button"
                        aria-label={`Move puzzle ${i + 1} down`}
                        disabled={i === ws.puzzles.length - 1}
                        onClick={() => {
                          content({ ...ws, puzzles: move(ws.puzzles, i, 1) });
                          setSelected(i + 1);
                        }}
                      >
                        Down
                      </button>
                    </li>
                  ))}
                </ol>
                {puzzle ? (
                  <section className="puzzle-fields">
                    <div className="section-heading">
                      <h3>Edit puzzle {selected + 1}</h3>
                      <button
                        type="button"
                        onClick={() => {
                          if (
                            window.confirm(
                              `Remove “${puzzle.title}” from this draft? Its word bank will remain.`,
                            )
                          ) {
                            content({
                              ...ws,
                              puzzles: ws.puzzles.filter((_, i) => i !== selected),
                            });
                            setSelected(Math.max(0, selected - 1));
                          }
                        }}
                      >
                        Remove puzzle
                      </button>
                    </div>
                    <Field
                      label="Puzzle title"
                      path={`${path}.title`}
                      value={puzzle.title}
                      issues={issues}
                      onChange={(title) => updatePuzzle({ title })}
                    />
                    <div className="field-pair">
                      <Field
                        label="Puzzle ID"
                        path={`${path}.id`}
                        value={puzzle.id}
                        issues={issues}
                        onChange={(id) => updatePuzzle({ id })}
                      />
                      <Field
                        label="Theme"
                        path={`${path}.theme`}
                        value={puzzle.theme}
                        issues={issues}
                        onChange={(theme) => updatePuzzle({ theme })}
                      />
                    </div>
                    <ContentEditor
                      content={ws}
                      puzzle={puzzle}
                      selected={selected}
                      issues={issues}
                      onChange={content}
                      onPuzzle={updatePuzzle}
                    />
                  </section>
                ) : (
                  <p>Add a puzzle definition to continue. Python requires at least one.</p>
                )}
              </>
            )}
          </fieldset>
        </form>
        <div className="draft-preview" id="draft-preview" tabIndex={-1} aria-label="Draft preview">
          <div className="section-heading">
            <h3>
              {preview
                ? dirty
                  ? 'Unsaved draft preview'
                  : 'Preview of saved content'
                : 'Your draft on paper'}
            </h3>
          </div>
          {!preview ? (
            <div className="preview-empty">
              <h2>See what your edits make.</h2>
              <p>
                Preview validates the whole draft, generates every puzzle and checks quality.
                Nothing is saved until you choose Save changes.
              </p>
            </div>
          ) : (
            <>
              <div className="editor-actions">
                <button
                  type="button"
                  aria-pressed={view === 'puzzle'}
                  onClick={() => setView('puzzle')}
                >
                  Selected puzzle
                </button>
                <button
                  type="button"
                  aria-pressed={view === 'quality'}
                  onClick={() => setView('quality')}
                >
                  Whole-book quality
                </button>
              </div>
              {view === 'quality' ? (
                <Quality generation={preview} />
              ) : (
                result && (
                  <Inspector
                    key={result.id}
                    project={{ ...saved, source: draft }}
                    generation={preview}
                    result={result}
                  />
                )
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
