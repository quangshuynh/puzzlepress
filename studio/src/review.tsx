import { useCallback, useEffect, useState } from 'react';
import { ApiError, request } from './api';
import type { Source } from './editor-fields';
import type { PuzzleReviewState, ReviewState, ReviewStatusResponse } from './types';
import { Status } from './ui';

// Editorial review: your own judgment of each puzzle's saved content. Python binds
// every judgment to the content's review identity; editing the puzzle makes the
// judgment stale. Nothing is ever marked reviewed because automated checks passed.

export const REVIEW_LABELS: Record<ReviewState, string> = {
  not_reviewed: 'Not reviewed',
  needs_changes: 'Needs changes',
  reviewed: 'Reviewed',
  stale: 'Stale review',
};
const TONES = {
  not_reviewed: 'neutral',
  needs_changes: 'review',
  reviewed: 'pass',
  stale: 'fail',
} as const;

export function ReviewBadge({ state, compact = false }: { state: ReviewState; compact?: boolean }) {
  return (
    <span className={`status ${TONES[state]} review-badge review-${state}`}>
      <span aria-hidden="true" className="status-mark" />
      <span className={compact ? 'sr-only' : undefined}>{REVIEW_LABELS[state]}</span>
    </span>
  );
}

export function useReviews(projectKey: string, revision?: string) {
  const [data, setData] = useState<ReviewStatusResponse>();
  const [error, setError] = useState('');
  const url = `/api/projects/${encodeURIComponent(projectKey)}/reviews`;
  const reload = useCallback(() => {
    const controller = new AbortController();
    request<ReviewStatusResponse>(url, controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return;
        if (Array.isArray(next?.report?.puzzles)) setData(next);
        else setError('Studio received an incomplete review report.');
      })
      .catch((err: Error) => !controller.signal.aborted && setError(err.message));
    return controller;
  }, [url]);
  useEffect(() => {
    const controller = reload();
    return () => controller.abort();
  }, [reload, revision]);
  return { data, setData, error, setError, reload };
}

// What a review covers, from source: so an unsaved edit to this puzzle is visible.
export function puzzleSignature(source: Source, id: string) {
  const content = source.word_search;
  const puzzle = content?.puzzles.find((p) => p.id === id);
  if (!content || !puzzle) return null;
  const bank = content.banks.find((b) => b.id === puzzle.bank);
  const profile = content.profiles.find((p) => p.id === puzzle.difficulty);
  return JSON.stringify([
    puzzle.title,
    puzzle.theme,
    puzzle.difficulty,
    profile && [profile.width, profile.height, [...profile.directions].sort()],
    puzzle.target_ids.map((t) => bank?.entries.find((e) => e.id === t)?.display ?? t),
  ]);
}

export function ReviewControls({
  projectKey,
  review,
  data,
  onSaved,
  unsaved,
}: {
  projectKey: string;
  review: PuzzleReviewState | undefined;
  data: ReviewStatusResponse | undefined;
  onSaved: (next: ReviewStatusResponse) => void;
  unsaved: boolean;
}) {
  const [note, setNote] = useState(review?.recorded?.note ?? '');
  const [reviewer, setReviewer] = useState(review?.recorded?.reviewer ?? '');
  const [date, setDate] = useState(review?.recorded?.reviewed_on ?? '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => {
    setNote(review?.recorded?.note ?? '');
    setReviewer(review?.recorded?.reviewer ?? '');
    setDate(review?.recorded?.reviewed_on ?? '');
    setMessage('');
  }, [review?.puzzle, review?.recorded]);
  if (!review || !data)
    return (
      <p className="small muted">This puzzle is not in the saved book yet; save it to review it.</p>
    );
  const record = async (status: 'reviewed' | 'needs_changes' | 'not_reviewed') => {
    setBusy(true);
    try {
      const next = await request<ReviewStatusResponse>(
        `/api/projects/${encodeURIComponent(projectKey)}/reviews/record`,
        new AbortController().signal,
        {
          source_revision: data.source_revision,
          revision: data.revision,
          puzzle: review.puzzle,
          status,
          identity: status === 'not_reviewed' ? null : review.identity,
          note: note.trim() || null,
          reviewer: reviewer.trim() || null,
          reviewed_on: date || null,
        },
      );
      onSaved(next);
      setMessage(
        status === 'not_reviewed'
          ? 'Reset to not reviewed. reviews.yaml was updated; book.yaml is unchanged.'
          : `Recorded “${status === 'reviewed' ? 'reviewed' : 'needs changes'}” for the saved content.`,
      );
    } catch (err) {
      setMessage(
        err instanceof ApiError && (err.code === 'source_changed' || err.code === 'content_changed')
          ? 'The saved book or reviews changed since this page loaded. Reload, then review again.'
          : err instanceof Error
            ? err.message
            : 'The review was not recorded.',
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="review-panel" aria-labelledby="review-heading">
      <div className="review-head">
        <h4 id="review-heading">
          Editorial review <ReviewBadge state={review.state} />
        </h4>
        <div className="button-row" role="group" aria-label="Record your review">
          <button
            type="button"
            className="primary small-button"
            disabled={busy || unsaved}
            onClick={() => void record('reviewed')}
          >
            Mark reviewed
          </button>
          <button
            type="button"
            className="small-button"
            disabled={busy || unsaved}
            onClick={() => void record('needs_changes')}
          >
            Needs changes
          </button>
          <button
            type="button"
            className="small-button"
            disabled={busy || unsaved}
            onClick={() => void record('not_reviewed')}
          >
            Reset
          </button>
        </div>
      </div>
      {unsaved ? (
        <p className="draft-status small">
          This puzzle has unsaved edits. Save first: a review covers the saved content.
        </p>
      ) : (
        review.state === 'stale' && (
          <p className="small">The content changed after your last judgment; review it again.</p>
        )
      )}
      <details open={Boolean(review.recorded?.note)}>
        <summary className="small">Notes, reviewer and date</summary>
        <p className="small muted">
          Your judgment of this puzzle&apos;s words, title and theme as saved, not an automated
          check; it never changes the puzzle or the PDF. Name and date are what you type;
          PuzzlePress records no clock time.
        </p>
        <fieldset disabled={busy || unsaved} className="review-fields">
          <legend className="sr-only">Notes for this review</legend>
          <div className="editor-field">
            <label htmlFor="review-note">Editorial notes</label>
            <textarea
              id="review-note"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <div className="field-pair">
            <div className="editor-field">
              <label htmlFor="review-reviewer">Reviewer (optional)</label>
              <input
                id="review-reviewer"
                value={reviewer}
                onChange={(e) => setReviewer(e.target.value)}
              />
            </div>
            <div className="editor-field">
              <label htmlFor="review-date">Date reviewed (optional)</label>
              <input
                id="review-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>
          </div>
        </fieldset>
      </details>
      <p aria-live="polite" className="small review-message">
        {message}
      </p>
    </section>
  );
}

export function ReviewProgress({ data }: { data: ReviewStatusResponse | undefined }) {
  if (!data) return null;
  const s = data.report.summary;
  return (
    <p className="small review-progress" aria-label="Review progress">
      <Status tone={s.complete ? 'pass' : 'neutral'}>
        {s.reviewed} of {s.total} reviewed
      </Status>{' '}
      <span className="muted">
        {s.needs_changes} need changes · {s.not_reviewed} not reviewed · {s.stale} stale
      </span>
    </p>
  );
}
