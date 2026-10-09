import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from './api';
import type { Issue, PlanningReport, PlanningSource, PlanningStatus } from './types';

// The plan is its own document (planning.yaml) with its own byte revision, so its
// draft is separate from the book draft. Python validates, reports and saves; this
// hook only tracks the draft, the last Python check and the saved status.
export interface PlanningDraft {
  status?: PlanningStatus;
  loadError?: Error;
  draft: PlanningSource | null;
  dirty: boolean;
  busy: boolean;
  checking: boolean;
  issues: Issue[];
  error?: Error;
  message: string;
  // The report for what is on screen: the saved plan, or Python's check of the draft.
  report?: PlanningReport;
  // True when `report` describes an earlier draft (the current one has schema issues
  // or is still being checked).
  reportOutdated: boolean;
  epoch: number;
  change: (next: PlanningSource) => void;
  save: () => Promise<void>;
  approve: (identity: string | null) => Promise<void>;
  revert: () => void;
  reload: () => void;
  start: () => void;
}

export function starterPlan(): PlanningSource {
  return {
    planning_version: 1,
    concept: { summary: null, subject: null, reader_experience: null, scope: null },
    positioning: {
      primary_audience: null,
      secondary_audience: null,
      candidate_audiences: [],
      familiarity: 'undecided',
      tone: null,
      use_case: null,
      main_benefit: null,
      differentiation: null,
      evidence: [],
      claims: [],
    },
    structure: {
      puzzle_type: null,
      target_puzzles: null,
      print_profile: null,
      solutions: 'undecided',
      solutions_per_page: null,
      front_matter_pages: null,
      back_matter_pages: null,
    },
    difficulty: { strategy: 'undecided', levels: [] },
    themes: [],
    vocabulary: [],
    puzzles: [],
    constraints: {
      min_letters: null,
      max_letters: null,
      max_word_reuse: null,
      prohibited_words: [],
      notes: [],
    },
    questions: [],
    research: [],
    comparables: [],
    approval: null,
  };
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export function usePlanning(key: string, onDirty: (dirty: boolean) => void): PlanningDraft {
  const base = `/api/projects/${encodeURIComponent(key)}`;
  const [status, setStatus] = useState<PlanningStatus>();
  const [loadError, setLoadError] = useState<Error>();
  const [draft, setDraft] = useState<PlanningSource | null>(null);
  const [check, setCheck] = useState<{ signature: string; report: PlanningReport }>();
  const [checking, setChecking] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const [message, setMessage] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [epoch, setEpoch] = useState(0);
  const latest = useRef(draft);
  latest.current = draft;
  const signature = JSON.stringify(draft);
  const dirty = status !== undefined && !same(draft, status.source);

  function accept(next: PlanningStatus, text: string) {
    setStatus(next);
    setDraft(next.source ? structuredClone(next.source) : null);
    setCheck(undefined);
    setIssues([]);
    setError(undefined);
    setMessage(text);
    setEpoch((n) => n + 1);
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(undefined);
    request<PlanningStatus>(`${base}/planning`, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) accept(data, '');
      })
      .catch((err: Error) => !controller.signal.aborted && setLoadError(err));
    return () => controller.abort();
  }, [base, attempt]);

  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  // Python checks every draft change after a short pause; the result is matched to
  // the exact draft it describes.
  useEffect(() => {
    if (!dirty || !draft) return;
    const controller = new AbortController();
    setChecking(true);
    const timer = setTimeout(() => {
      request<{ report: PlanningReport }>(`${base}/draft/planning`, controller.signal, {
        source: latest.current,
      })
        .then((data) => {
          if (controller.signal.aborted) return;
          setCheck({ signature, report: data.report });
          setIssues([]);
        })
        .catch((err: Error) => {
          if (controller.signal.aborted) return;
          setIssues(err instanceof ApiError ? err.issues : []);
        })
        .finally(() => !controller.signal.aborted && setChecking(false));
    }, 350);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // `signature` captures the whole draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, signature, dirty]);

  const fresh = check?.signature === signature;
  const report = !dirty
    ? (status?.report ?? undefined)
    : (check?.report ?? status?.report ?? undefined);

  async function save() {
    if (!status || !draft || busy) return;
    setBusy(true);
    setError(undefined);
    setMessage('Saving planning.yaml…');
    try {
      const next = await request<PlanningStatus>(
        `${base}/planning/save`,
        new AbortController().signal,
        { source: draft, revision: status.revision },
      );
      accept(next, 'Saved planning.yaml and reloaded it. book.yaml was not changed.');
    } catch (err) {
      setError(err as Error);
      if (err instanceof ApiError) setIssues(err.issues);
      setMessage('The plan was not saved. Your draft is retained.');
    } finally {
      setBusy(false);
    }
  }

  async function approve(identity: string | null) {
    if (!status?.revision || busy || dirty) return;
    setBusy(true);
    setError(undefined);
    setMessage(identity ? 'Recording your approval…' : 'Withdrawing the approval…');
    try {
      const next = await request<PlanningStatus>(
        `${base}/planning/approval`,
        new AbortController().signal,
        { revision: status.revision, identity },
      );
      accept(
        next,
        identity
          ? 'Approved. Any later edit to the plan makes this approval stale.'
          : 'Approval withdrawn.',
      );
    } catch (err) {
      setError(err as Error);
      setMessage(identity ? 'The approval was not recorded.' : 'The approval was not withdrawn.');
    } finally {
      setBusy(false);
    }
  }

  return {
    status,
    loadError,
    draft,
    dirty,
    busy,
    checking: checking || (dirty && !fresh && issues.length === 0),
    issues,
    error,
    message,
    report,
    reportOutdated: dirty && !fresh,
    epoch,
    change: (next) => {
      setDraft(next);
      setMessage('');
    },
    save,
    approve,
    revert: () => {
      if (!status) return;
      if (window.confirm('Discard unsaved planning edits and return to the saved plan?')) {
        setDraft(status.source ? structuredClone(status.source) : null);
        setIssues([]);
        setError(undefined);
        setMessage('Draft reverted to the saved plan.');
        setEpoch((n) => n + 1);
      }
    },
    reload: () => {
      if (
        !dirty ||
        window.confirm('Reload the saved plan and discard this draft? Copy any edits first.')
      )
        setAttempt((n) => n + 1);
    },
    start: () => {
      setDraft(starterPlan());
      setMessage('A new, empty plan. Nothing is saved until you save.');
    },
  };
}
