import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from './api';
import type { Source } from './editor-fields';
import type { Generation, Issue, PlanResult, Project } from './types';
import { Issues } from './ui';

export type DraftAction = 'validate' | 'preview' | 'plan' | 'save' | 'reload';

// One whole-project draft shared by puzzle authoring and book composition, so both
// views use a single revision and the same Python validation/save transaction.
export interface Draft {
  key: string;
  saved: Project;
  draft: Source;
  dirty: boolean;
  busy: boolean;
  issues: Issue[];
  error?: Error;
  message: string;
  preview?: Generation;
  plan?: PlanResult;
  epoch: number;
  change: (next: Source) => void;
  run: (action: DraftAction, done?: string) => Promise<void>;
  revert: () => void;
}

const running: Partial<Record<DraftAction, string>> = {
  preview: 'Generating and checking the draft…',
  plan: 'Generating puzzles and planning the book…',
};

export function useDraft(
  project: Project,
  onSaved: (project: Project) => void,
  onDirty: (dirty: boolean) => void,
): Draft {
  const [saved, setSaved] = useState(project);
  const [draft, setDraft] = useState<Source>(() => structuredClone(project.source!));
  const [issues, setIssues] = useState<Issue[]>([]);
  const [error, setError] = useState<Error>();
  const [message, setMessage] = useState('Ready to edit. Source has not changed.');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Generation>();
  const [plan, setPlan] = useState<PlanResult>();
  const [epoch, setEpoch] = useState(0);
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

  function reset(next: Source, text: string) {
    version.current++;
    setDraft(next);
    setPreview(undefined);
    setPlan(undefined);
    setIssues([]);
    setError(undefined);
    setMessage(text);
  }
  function accept(next: Project) {
    if (!next.source || !next.revision || !next.validation?.valid)
      throw new ApiError(
        'Studio received an incomplete saved project. Reload to review.',
        'malformed_response',
      );
    setSaved(next);
    reset(structuredClone(next.source), '');
    setEpoch((n) => n + 1);
    onSaved(next);
  }
  async function run(action: DraftAction, done?: string) {
    if (busy) return;
    const controller = new AbortController();
    active.current = controller;
    const current = version.current;
    setBusy(true);
    setError(undefined);
    setIssues([]);
    setMessage(running[action] ?? 'Checking project…');
    try {
      const url = `/api/projects/${encodeURIComponent(project.key)}`;
      const data = await request<Project | Generation | PlanResult>(
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
      } else if (action === 'plan') {
        const result = data as PlanResult;
        if (!result.plan?.pages || !result.plan.statistics || !result.verification)
          throw new ApiError(
            'Studio received an incomplete publication plan. Retry the plan preview.',
            'malformed_response',
          );
        setPlan(result);
        setMessage(done ?? 'Publication plan ready. Source has not changed.');
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
  return {
    key: project.key,
    saved,
    draft,
    dirty,
    busy,
    issues,
    error,
    message,
    preview,
    plan,
    epoch,
    change: (next) => reset(next, 'Draft changed. Validate or preview to check these edits.'),
    run,
    revert: () => {
      if (window.confirm('Discard unsaved edits and return to the source you opened?')) {
        reset(structuredClone(saved.source!), 'Draft reverted to the saved source you opened.');
        setEpoch((n) => n + 1);
      }
    },
  };
}

export function DraftToolbar({
  d,
  title,
  preview,
  previewLabel,
  previewDisabled,
  jump,
}: {
  d: Draft;
  title: string;
  preview?: 'preview' | 'plan';
  previewLabel?: string;
  previewDisabled?: boolean;
  jump: { href: string; label: string };
}) {
  return (
    <>
      <div className="editor-toolbar">
        <div className="toolbar-title">
          <h2>{title}</h2>
          <p className={d.dirty ? 'draft-status' : 'muted'}>
            <span aria-hidden="true" className="status-mark" />
            {d.dirty ? 'Unsaved changes' : 'Saved source'}
          </p>
          <p role="status" aria-live="polite" className="toolbar-message">
            {d.message}
          </p>
        </div>
        <div className="editor-actions">
          <a className="jump-link" href={jump.href}>
            {jump.label}
          </a>
          <button type="button" disabled={d.busy} onClick={() => void d.run('validate')}>
            Validate draft
          </button>
          {preview && (
            <button
              type="button"
              disabled={d.busy || previewDisabled}
              onClick={() => void d.run(preview)}
            >
              {previewLabel}
            </button>
          )}
          <button type="button" disabled={d.busy || !d.dirty} onClick={d.revert}>
            Revert draft
          </button>
          <button
            type="button"
            className="primary"
            disabled={d.busy || !d.dirty}
            onClick={() => void d.run('save')}
            aria-describedby="yaml-note"
          >
            Save changes
          </button>
        </div>
        <p className="small muted yaml-note" id="yaml-note">
          Save writes normalized YAML. Comments, quoting and original formatting are not preserved.
        </p>
      </div>
      {d.error && (
        <div role="alert" className="notice error">
          <h3>
            {d.error instanceof ApiError && d.error.code === 'source_changed'
              ? 'Saved source has changed'
              : 'Could not complete the request'}
          </h3>
          <p>{d.error.message}</p>
          <Issues issues={d.issues} />
          <button
            type="button"
            disabled={d.busy}
            onClick={() => {
              if (
                window.confirm(
                  'Reload the latest saved source and discard this draft? Copy any edits you want to keep first.',
                )
              )
                void d.run('reload');
            }}
          >
            Reload saved source
          </button>
        </div>
      )}
    </>
  );
}
