import { useState } from 'react';
import { Field, move, type Content } from './editor-fields';
import type { Definition, Issue, Profile } from './types';
import { Issues } from './ui';

const directions = [
  'right',
  'left',
  'down',
  'up',
  'down-right',
  'down-left',
  'up-right',
  'up-left',
];

export function ContentEditor({
  content,
  puzzle,
  selected,
  issues,
  onChange,
  onPuzzle,
}: {
  content: Content;
  puzzle: Definition;
  selected: number;
  issues: Issue[];
  onChange: (content: Content) => void;
  onPuzzle: (patch: Partial<Definition>) => void;
}) {
  const [bankIndex, setBankIndex] = useState(0);
  const bank = content.banks.find((b) => b.id === puzzle.bank);
  const editingBank = content.banks[bankIndex];
  const profileIndex = content.profiles.findIndex((p) => p.id === puzzle.difficulty);
  const profile = content.profiles[profileIndex];
  const path = `word_search.puzzles.${selected}`;
  function updateProfile(patch: Partial<Profile>) {
    onChange({
      ...content,
      profiles: content.profiles.map((p, i) => (i === profileIndex ? { ...p, ...patch } : p)),
    });
  }
  return (
    <>
      <div className="field-pair">
        <div className="editor-field">
          <label htmlFor="puzzle-bank">Word bank</label>
          <select
            id="puzzle-bank"
            value={puzzle.bank}
            onChange={(e) => onPuzzle({ bank: e.target.value })}
          >
            {!bank && <option value={puzzle.bank}>{puzzle.bank || 'Choose a bank'}</option>}
            {content.banks.map((b, i) => (
              <option key={i} value={b.id}>
                {b.id}
              </option>
            ))}
          </select>
        </div>
        <div className="editor-field">
          <label htmlFor="puzzle-profile">Difficulty profile</label>
          <select
            id="puzzle-profile"
            value={puzzle.difficulty}
            onChange={(e) => onPuzzle({ difficulty: e.target.value })}
          >
            {!profile && (
              <option value={puzzle.difficulty}>{puzzle.difficulty || 'Choose a profile'}</option>
            )}
            {content.profiles.map((p, i) => (
              <option key={i} value={p.id}>
                {p.id} · {p.width} × {p.height}
              </option>
            ))}
          </select>
        </div>
      </div>
      <Issues
        issues={issues.filter((i) => i.path === `${path}.bank` || i.path === `${path}.difficulty`)}
      />
      <h3 className="editor-subheading">
        Selected targets <span className="muted">({puzzle.target_ids.length})</span>
      </h3>
      <p className="small muted">
        Order is authored. Changing banks keeps your selection so references can be reviewed.
      </p>
      <ol className="target-editor">
        {puzzle.target_ids.map((id, i) => (
          <li key={i}>
            <span>
              {bank?.entries.find((e) => e.id === id)?.display ?? `Missing target: ${id}`}
            </span>
            <button
              type="button"
              aria-label={`Move target ${i + 1} up`}
              disabled={i === 0}
              onClick={() => onPuzzle({ target_ids: move(puzzle.target_ids, i, -1) })}
            >
              Up
            </button>
            <button
              type="button"
              aria-label={`Move target ${i + 1} down`}
              disabled={i === puzzle.target_ids.length - 1}
              onClick={() => onPuzzle({ target_ids: move(puzzle.target_ids, i, 1) })}
            >
              Down
            </button>
            <button
              type="button"
              aria-label={`Remove target ${i + 1}`}
              onClick={() => onPuzzle({ target_ids: puzzle.target_ids.filter((_, j) => i !== j) })}
            >
              Remove
            </button>
          </li>
        ))}
      </ol>
      <Issues issues={issues.filter((i) => i.path.startsWith(`${path}.target_ids`))} />
      <div className="editor-field">
        <label htmlFor="add-target">Add a target from {puzzle.bank}</label>
        <select
          id="add-target"
          value=""
          onChange={(e) => {
            if (e.target.value) onPuzzle({ target_ids: [...puzzle.target_ids, e.target.value] });
          }}
        >
          <option value="">Choose a word…</option>
          {bank?.entries
            .filter((e) => !puzzle.target_ids.includes(e.id))
            .map((e, i) => (
              <option key={i} value={e.id}>
                {e.display} ({e.id})
              </option>
            ))}
        </select>
      </div>
      <details className="editor-settings" open>
        <summary>Word banks · shared content</summary>
        <p className="small muted">
          Changes affect every puzzle referencing an entry. Removing or renaming IDs can leave
          references to repair. Python checks letters, duplicates and normalization.
        </p>
        <div className="editor-field">
          <label htmlFor="editing-bank">Edit bank</label>
          <select
            id="editing-bank"
            value={bankIndex}
            onChange={(e) => setBankIndex(Number(e.target.value))}
          >
            {content.banks.map((b, i) => (
              <option key={i} value={i}>
                {b.id}
              </option>
            ))}
          </select>
        </div>
        {editingBank && (
          <>
            <div className="bank-entries">
              {editingBank.entries.map((entry, i) => {
                const entryPath = `word_search.banks.${bankIndex}.entries.${i}`;
                const update = (patch: Partial<typeof entry>) =>
                  onChange({
                    ...content,
                    banks: content.banks.map((b, j) =>
                      j === bankIndex
                        ? {
                            ...b,
                            entries: b.entries.map((e, k) => (k === i ? { ...e, ...patch } : e)),
                          }
                        : b,
                    ),
                  });
                return (
                  <div className="bank-entry" key={i}>
                    <Field
                      label={`Entry ${i + 1} ID`}
                      path={`${entryPath}.id`}
                      value={entry.id}
                      issues={issues}
                      onChange={(id) => update({ id })}
                    />
                    <Field
                      label={`Word ${i + 1}`}
                      path={`${entryPath}.display`}
                      value={entry.display}
                      issues={issues}
                      onChange={(display) => update({ display })}
                    />
                    <button
                      type="button"
                      aria-label={`Remove word ${i + 1}`}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Remove “${entry.display}” from bank ${editingBank.id}? Referencing puzzles will need review.`,
                          )
                        )
                          onChange({
                            ...content,
                            banks: content.banks.map((b, j) =>
                              j === bankIndex
                                ? { ...b, entries: b.entries.filter((_, k) => k !== i) }
                                : b,
                            ),
                          });
                      }}
                    >
                      Remove
                    </button>
                  </div>
                );
              })}
            </div>
            <button
              type="button"
              onClick={() => {
                let n = 1;
                while (editingBank.entries.some((e) => e.id === `word-${n}`)) n++;
                onChange({
                  ...content,
                  banks: content.banks.map((b, j) =>
                    j === bankIndex
                      ? { ...b, entries: [...b.entries, { id: `word-${n}`, display: '' }] }
                      : b,
                  ),
                });
              }}
            >
              Add word
            </button>
          </>
        )}
      </details>
      {profile && (
        <details className="editor-settings">
          <summary>Profile settings · {profile.id}</summary>
          <p className="small muted">
            Shared by {content.puzzles.filter((p) => p.difficulty === profile.id).length} puzzle(s).
            These are authored settings, not calibrated difficulty scores.
          </p>
          <div className="field-pair">
            {(['width', 'height', 'max_restarts', 'max_attempts'] as const).map((key) => (
              <Field
                key={key}
                label={
                  {
                    width: 'Grid width',
                    height: 'Grid height',
                    max_restarts: 'Maximum restarts',
                    max_attempts: 'Maximum attempts',
                  }[key]
                }
                path={`word_search.profiles.${profileIndex}.${key}`}
                type="number"
                value={profile[key]}
                issues={issues}
                onChange={(value) => updateProfile({ [key]: value === '' ? NaN : Number(value) })}
              />
            ))}
          </div>
          <fieldset className="direction-options">
            <legend>Placement directions</legend>
            {directions.map((d) => (
              <label key={d}>
                <input
                  type="checkbox"
                  checked={profile.directions.includes(d)}
                  onChange={(e) =>
                    updateProfile({
                      directions: e.target.checked
                        ? [...profile.directions, d]
                        : profile.directions.filter((v) => v !== d),
                    })
                  }
                />
                {d.replaceAll('-', ' ')}
              </label>
            ))}
          </fieldset>
          <Issues
            issues={issues.filter((i) => i.path.startsWith(`word_search.profiles.${profileIndex}`))}
          />
        </details>
      )}
      <details className="editor-settings">
        <summary>Quality policy · shared across the book</summary>
        <Field
          label="Maximum word reuse"
          path="word_search.quality.max_word_reuse"
          value={content.quality.max_word_reuse}
          type="number"
          issues={issues}
          onChange={(value) =>
            onChange({ ...content, quality: { ...content.quality, max_word_reuse: Number(value) } })
          }
        />
        <label htmlFor="prohibited-words">Prohibited words (one per line)</label>
        <textarea
          id="prohibited-words"
          rows={4}
          value={content.quality.prohibited_words.join('\n')}
          onChange={(e) =>
            onChange({
              ...content,
              quality: {
                ...content.quality,
                prohibited_words: e.target.value === '' ? [] : e.target.value.split('\n'),
              },
            })
          }
        />
        <p className="small muted">
          An empty list disables screening. Findings never rewrite content or block saving a valid
          project.
        </p>
        <Issues
          issues={issues.filter((i) => i.path.startsWith('word_search.quality.prohibited_words'))}
        />
      </details>
    </>
  );
}
