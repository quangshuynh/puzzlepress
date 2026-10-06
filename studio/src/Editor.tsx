import { useState } from 'react';
import { Inspector, Quality } from './Puzzles';
import type { Definition } from './types';
import { Empty } from './ui';
import { ContentEditor } from './ContentEditor';
import { DraftToolbar, type Draft } from './draft';

import { Field, move, type Content } from './editor-fields';

export function Editor({ d }: { d: Draft }) {
  const { draft, issues, busy, preview, saved, dirty } = d;
  const change = d.change;
  const [selected, setSelected] = useState(0);
  const [epoch, setEpoch] = useState(d.epoch);
  const [view, setView] = useState<'puzzle' | 'quality'>('puzzle');
  if (epoch !== d.epoch) {
    // Saved, reloaded or reverted drafts start again at the first definition.
    setEpoch(d.epoch);
    setSelected(0);
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
  const ws = draft.word_search;
  const puzzle = ws?.puzzles[selected];
  const path = `word_search.puzzles.${selected}`;
  const result = preview?.report.puzzles[selected];
  return (
    <div className="editor">
      <DraftToolbar
        d={d}
        title="Authoring desk"
        preview="preview"
        previewLabel="Preview draft"
        previewDisabled={!ws}
        jump={{ href: '#draft-preview', label: 'Jump to preview' }}
      />
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
