import { useCallback, useEffect, useState } from 'react';
import { ApiError, request } from './api';
import type {
  ItemStatus,
  ProductionItem,
  ProductionStatus,
  ProofRecordView,
  ProofsResponse,
  RebuildStepResult,
} from './types';
import { Loading, Status } from './ui';

// The production workflow: which artifacts are out of date and why, an explicit
// rebuild of only those, and the final-mile checklist. Every state comes from
// Python; nothing here says a step succeeded before the server confirms it.

const ACTIONS: Record<string, string> = {
  build_interior: 'Rebuild the interior and its preflight report',
  build_cover: 'Rebuild the cover and its preflight report',
  write_preflight: 'Refresh the interior preflight report',
  write_cover_preflight: 'Refresh the cover preflight report',
};
const ARTIFACTS: Record<string, string> = {
  interior: 'Interior PDF',
  interior_preflight: 'Interior preflight report',
  cover: 'Cover PDF',
  cover_preflight: 'Cover preflight report',
  package: 'Publishing package',
};
const STEP_TONES = {
  succeeded: 'pass',
  unchanged: 'pass',
  failed: 'fail',
  skipped: 'neutral',
} as const;

export function useProduction(projectKey: string, revision?: string) {
  const [status, setStatus] = useState<ProductionStatus>();
  const [error, setError] = useState<Error>();
  const url = `/api/projects/${encodeURIComponent(projectKey)}/production`;
  const reload = useCallback(() => {
    const controller = new AbortController();
    setError(undefined);
    request<ProductionStatus>(url, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        if (Array.isArray(data?.items) && data.assessment) setStatus(data);
        else
          setError(
            new ApiError('Studio received an incomplete production report.', 'malformed_response'),
          );
      })
      .catch((err: Error) => !controller.signal.aborted && setError(err));
    return controller;
  }, [url]);
  useEffect(() => {
    const controller = reload();
    return () => controller.abort();
  }, [reload, revision]);
  return { status, setStatus, error, reload };
}

export function RebuildPanel({
  projectKey,
  revision,
  dirty,
  onDone,
  onClose,
}: {
  projectKey: string;
  revision?: string;
  dirty: boolean;
  onDone?: (status: ProductionStatus) => void;
  onClose?: () => void;
}) {
  const { status, setStatus, error } = useProduction(projectKey, revision);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<RebuildStepResult[]>();
  const [message, setMessage] = useState('');
  const steps = status?.assessment.steps ?? [];
  const run = async () => {
    setRunning(true);
    setResults(undefined);
    setMessage('Rebuilding in Python. Other builds wait until this finishes.');
    try {
      const data = await request<ProductionStatus>(
        `/api/projects/${encodeURIComponent(projectKey)}/rebuild`,
        new AbortController().signal,
        { revision: status?.revision },
      );
      setStatus(data);
      setResults(data.rebuild?.results ?? []);
      setMessage(
        data.rebuild?.code === 'source_changed'
          ? (data.rebuild.message ?? 'The saved source changed during the rebuild.')
          : data.rebuild?.success
            ? 'The server confirmed every step. Previews and checks now show the new files.'
            : 'A step failed. Nothing was written for it; the previous file is unchanged.',
      );
      onDone?.(data);
    } catch (err) {
      setMessage(
        err instanceof ApiError && err.code === 'source_changed'
          ? 'The saved source changed on disk. Reload the project before rebuilding.'
          : err instanceof Error
            ? err.message
            : 'The rebuild request did not complete.',
      );
    } finally {
      setRunning(false);
    }
  };
  return (
    <section className="rebuild-panel" aria-labelledby="rebuild-heading">
      <div className="section-heading">
        <h3 id="rebuild-heading">Rebuild outdated artifacts</h3>
        {onClose && (
          <button type="button" className="small-button" onClick={onClose}>
            Close
          </button>
        )}
      </div>
      {error && <p className="field-errors small">{error.message}</p>}
      {!status && !error && <Loading>Checking which artifacts are out of date…</Loading>}
      {status && (
        <>
          <ul className="artifact-list" aria-label="Artifacts">
            {status.assessment.artifacts.map((artifact) => (
              <li key={artifact.name}>
                <strong>{ARTIFACTS[artifact.name] ?? artifact.name}</strong>{' '}
                <Status
                  tone={
                    artifact.state === 'current'
                      ? 'pass'
                      : artifact.state === 'not_applicable'
                        ? 'neutral'
                        : 'review'
                  }
                >
                  {artifact.state.replaceAll('_', ' ')}
                </Status>
                {artifact.reasons.length > 0 && (
                  <span className="small muted"> {artifact.reasons.join(' ')}</span>
                )}
              </li>
            ))}
          </ul>
          {results && results.length > 0 && (
            <ol className="rebuild-steps" aria-label="Rebuild results">
              {results.map((result) => (
                <li key={result.action}>
                  <span>{ACTIONS[result.action] ?? result.action}</span>{' '}
                  <Status tone={STEP_TONES[result.status]}>{result.status}</Status>
                  <p className="small muted">{result.message}</p>
                  {result.diagnostics.map((item, i) => (
                    <p key={i} className="small field-errors">
                      {item.message} <code>{item.code}</code>
                    </p>
                  ))}
                </li>
              ))}
            </ol>
          )}
          {steps.length === 0 ? (
            <p className="small">
              <Status tone="pass">Up to date</Status> Every built artifact matches the saved source.
            </p>
          ) : (
            <>
              <p className="small">These steps will run, in order, for the saved source:</p>
              <ol className="rebuild-steps">
                {steps.map((step) => (
                  <li key={step.action}>
                    <span>
                      {ACTIONS[step.action] ?? step.action}
                      {step.conditional ? ' (only if needed)' : ''}
                    </span>{' '}
                    <Status tone="neutral">{running ? 'in progress' : 'planned'}</Status>
                    <p className="small muted">{step.why}</p>
                  </li>
                ))}
              </ol>
              <button
                type="button"
                className="primary"
                disabled={running || dirty}
                onClick={() => void run()}
              >
                {running
                  ? 'Rebuilding…'
                  : `Rebuild ${steps.length} step${steps.length > 1 ? 's' : ''}`}
              </button>
              {dirty && (
                <p className="draft-status small">
                  You have unsaved changes; rebuilds use the saved source. Save first.
                </p>
              )}
            </>
          )}
          {status.assessment.manual.map((note) => (
            <p key={note} className="small muted">
              {note}
            </p>
          ))}
          {results && results.length === 0 && status.rebuild?.code === 'source_changed' && (
            <p className="small field-errors">No step ran.</p>
          )}
        </>
      )}
      <p role="status" aria-live="polite" className="small">
        {message}
      </p>
    </section>
  );
}

const ITEM: Record<ItemStatus, ['pass' | 'review' | 'fail' | 'neutral', string]> = {
  completed: ['pass', 'Completed'],
  needs_attention: ['review', 'Needs attention'],
  blocking: ['fail', 'Blocking'],
  not_applicable: ['neutral', 'Not applicable'],
  awaiting_review: ['review', 'Awaiting your decision'],
  external_pending: ['neutral', 'Outside step not recorded'],
};
const BASIS: Record<ProductionItem['basis'], string> = {
  internal: 'PuzzlePress rule',
  kdp_modeled: 'Modeled KDP requirement',
  author_judgment: 'Your judgment',
  external: 'Outside PuzzlePress',
};
const AREAS: Record<string, string> = {
  plan: 'planning',
  puzzles: 'edit',
  quality: 'quality',
  book: 'book',
  print: 'print',
  cover: 'cover',
  publishing: 'publishing',
};

export function ProductionOverview({
  projectKey,
  revision,
  dirty,
  onRebuilt,
}: {
  projectKey: string;
  revision?: string;
  dirty: boolean;
  onRebuilt?: () => void;
}) {
  const { status, setStatus, error, reload } = useProduction(projectKey, revision);
  const [rebuilding, setRebuilding] = useState(false);
  const base = `/books/${encodeURIComponent(projectKey)}`;
  if (error) return <p className="field-errors small">{error.message}</p>;
  if (!status) return <Loading>Checking every production step…</Loading>;
  return (
    <section className="production-overview" aria-labelledby="production-heading">
      <h3 id="production-heading">Final steps</h3>
      <p className="small">{status.statement}</p>
      <ol className="stage-ladder" aria-label="Production stages">
        {status.stages.map((stage) => (
          <li
            key={stage.code}
            className={stage.reached ? 'reached' : stage.reached === null ? 'untracked' : ''}
          >
            <Status tone={stage.reached ? 'pass' : 'neutral'}>
              {stage.reached ? 'Reached' : stage.reached === null ? 'Not tracked' : 'Not yet'}
            </Status>{' '}
            <strong>{stage.title}</strong>
            <span className="small muted"> {stage.detail}</span>
          </li>
        ))}
      </ol>
      {status.assessment.outdated && (
        <p className="print-state stale">
          <strong>Some artifacts are out of date.</strong>{' '}
          <button type="button" className="link-button" onClick={() => setRebuilding(true)}>
            Review and rebuild outdated artifacts
          </button>
        </p>
      )}
      {rebuilding && (
        <RebuildPanel
          projectKey={projectKey}
          revision={revision}
          dirty={dirty}
          onDone={(next) => {
            setStatus(next);
            onRebuilt?.();
          }}
          onClose={() => setRebuilding(false)}
        />
      )}
      <ul className="guide-list" aria-label="Production checklist">
        {status.items.map((item) => (
          <li key={item.code} className={`guide-${item.status}`}>
            <div className="guide-head">
              <Status tone={ITEM[item.status][0]}>{ITEM[item.status][1]}</Status>
              <strong>{item.title}</strong>
              <span className="basis-label small">{BASIS[item.basis]}</span>
              {item.blocks_export && <span className="small muted">Blocks export</span>}
            </div>
            <details>
              <summary className="small">{item.detail}</summary>
              <p className="small">
                <strong>Checks:</strong> {item.what}
              </p>
              <p className="small">
                <strong>Why:</strong> {item.why}
              </p>
              {item.action && (
                <p className="small">
                  <strong>Next:</strong> {item.action}{' '}
                  {AREAS[item.area] && <a href={`${base}/${AREAS[item.area]}`}>Open {item.area}</a>}
                </p>
              )}
            </details>
          </li>
        ))}
      </ul>
      <h4>Human proofing</h4>
      <ol className="proofing-steps small">
        {status.proofing.map((step) => (
          <li key={step.code}>
            {step.title}
            {step.area === 'external' && (
              <span className="muted"> (in KDP, outside PuzzlePress)</span>
            )}
          </li>
        ))}
      </ol>
      <p className="small muted">
        PuzzlePress cannot certify that Amazon accepts a book and never uploads or submits it.
        Record what you saw in the Print Previewer and in a printed proof below.
      </p>
      <ProofRecords projectKey={projectKey} proofs={status.proofs} onChange={() => reload()} />
    </section>
  );
}

function ProofRecords({
  projectKey,
  proofs,
  onChange,
}: {
  projectKey: string;
  proofs: ProofsResponse;
  onChange: () => void;
}) {
  const [kind, setKind] = useState<ProofRecordView['kind']>('print_previewer');
  const [statusValue, setStatusValue] = useState<ProofRecordView['status']>('reviewed');
  const [decision, setDecision] = useState<ProofRecordView['decision']>('undecided');
  const [received, setReceived] = useState('');
  const [reviewed, setReviewed] = useState('');
  const [issues, setIssues] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const artifacts = proofs.artifacts;
  const save = async () => {
    if (!artifacts) return;
    setBusy(true);
    const id = `proof-${proofs.proofs.length + 1}`;
    try {
      await request(
        `/api/projects/${encodeURIComponent(projectKey)}/proofs/record`,
        new AbortController().signal,
        {
          revision: proofs.revision,
          record: {
            id,
            kind,
            status: kind === 'print_previewer' ? 'reviewed' : statusValue,
            decision,
            artifacts,
            ...(received ? { received_on: received } : {}),
            ...(reviewed ? { reviewed_on: reviewed } : {}),
            ...(issues.trim()
              ? {
                  issues: issues
                    .split('\n')
                    .map((l) => l.trim())
                    .filter(Boolean),
                }
              : {}),
          },
        },
      );
      setMessage(`Recorded ${id} against the artifacts in the build directory now.`);
      setIssues('');
      onChange();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'The proof was not recorded.');
    } finally {
      setBusy(false);
    }
  };
  const decidable = kind === 'print_previewer' || statusValue === 'reviewed';
  return (
    <div className="proof-records">
      <h4>Proof records</h4>
      {proofs.proofs.length === 0 ? (
        <p className="small muted">Nothing recorded yet.</p>
      ) : (
        <ul className="finding-list">
          {proofs.proofs.map(({ record, current }) => (
            <li key={record.id}>
              <Status
                tone={current ? (record.decision === 'approved' ? 'pass' : 'neutral') : 'review'}
              >
                {current ? record.decision.replace('_', ' ') : 'stale'}
              </Status>{' '}
              <strong>
                {record.kind === 'print_previewer' ? 'Print Previewer' : 'Physical proof'}
              </strong>{' '}
              <span className="small muted">
                {record.id} · {record.status}
                {record.reviewed_on ? ` · reviewed ${record.reviewed_on}` : ''}
                {current ? '' : ' · names earlier artifacts; review the current files again'}
              </span>
              {record.issues?.length ? (
                <ul className="small">
                  {record.issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {!artifacts ? (
        <p className="small muted">Build the interior before recording a proof.</p>
      ) : (
        <fieldset className="proof-form" disabled={busy}>
          <legend>Record a proof you reviewed</legend>
          <div className="field-pair">
            <div className="editor-field">
              <label htmlFor="proof-kind">Kind</label>
              <select
                id="proof-kind"
                value={kind}
                onChange={(e) => setKind(e.target.value as typeof kind)}
              >
                <option value="print_previewer">KDP Print Previewer</option>
                <option value="physical_proof">Physical proof copy</option>
              </select>
            </div>
            {kind === 'physical_proof' && (
              <div className="editor-field">
                <label htmlFor="proof-status">Status</label>
                <select
                  id="proof-status"
                  value={statusValue}
                  onChange={(e) => {
                    setStatusValue(e.target.value as typeof statusValue);
                    if (e.target.value !== 'reviewed') setDecision('undecided');
                  }}
                >
                  <option value="ordered">Ordered</option>
                  <option value="received">Received</option>
                  <option value="reviewed">Reviewed</option>
                </select>
              </div>
            )}
          </div>
          <div className="field-pair">
            {kind === 'physical_proof' && (
              <div className="editor-field">
                <label htmlFor="proof-received">Date received</label>
                <input
                  id="proof-received"
                  type="date"
                  value={received}
                  onChange={(e) => setReceived(e.target.value)}
                />
              </div>
            )}
            <div className="editor-field">
              <label htmlFor="proof-reviewed">Date reviewed</label>
              <input
                id="proof-reviewed"
                type="date"
                value={reviewed}
                onChange={(e) => setReviewed(e.target.value)}
              />
            </div>
          </div>
          <div className="editor-field">
            <label htmlFor="proof-issues">Observed issues, one per line</label>
            <textarea
              id="proof-issues"
              rows={3}
              value={issues}
              onChange={(e) => setIssues(e.target.value)}
            />
          </div>
          <div className="editor-field">
            <label htmlFor="proof-decision">Your decision</label>
            <select
              id="proof-decision"
              value={decision}
              disabled={!decidable}
              onChange={(e) => setDecision(e.target.value as typeof decision)}
            >
              <option value="undecided">Undecided</option>
              <option value="changes_needed">Changes needed</option>
              <option value="approved">Approved, after my review</option>
            </select>
          </div>
          <p className="small muted">
            The record names the interior and cover now in the build directory; it goes stale when
            either is rebuilt. Approve only what you have actually reviewed.
          </p>
          <button type="button" className="small-button" onClick={() => void save()}>
            Record proof
          </button>
        </fieldset>
      )}
      <p role="status" aria-live="polite" className="small">
        {message}
      </p>
    </div>
  );
}
