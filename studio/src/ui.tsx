import type { ReactNode } from 'react';
import { ApiError } from './api';
import type { Finding, Issue } from './types';

export function Status({
  tone = 'neutral',
  children,
}: {
  tone?: 'pass' | 'review' | 'fail' | 'neutral';
  children: ReactNode;
}) {
  return (
    <span className={`status ${tone}`}>
      <span aria-hidden="true" className="status-mark" />
      {children}
    </span>
  );
}

export function Issues({ issues }: { issues: Issue[] }) {
  return (
    <ul className="issue-list">
      {issues.map((issue, i) => (
        <li key={i}>
          <strong>{issue.path}</strong>: {issue.message} <code>{issue.code}</code>
        </li>
      ))}
    </ul>
  );
}

export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <section className="notice error" role="alert">
      <h2>
        {error instanceof ApiError && error.code === 'invalid_project'
          ? 'Project needs attention'
          : 'Unable to open this view'}
      </h2>
      <p>{error.message}</p>
      {error instanceof ApiError && <Issues issues={error.issues} />}
      {retry && <button onClick={retry}>Try again</button>} <a href="/books">Return to books</a>
    </section>
  );
}

export function Loading({ children = 'Reading project source…' }: { children?: ReactNode }) {
  return (
    <div className="notice loading" role="status">
      <span className="loading-line" aria-hidden="true" />
      <p>{children}</p>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="notice">
      <h2>{title}</h2>
      <p>{children}</p>
    </section>
  );
}

export function Details({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="details">
      <summary>{title}</summary>
      <div>{children}</div>
    </details>
  );
}

export function Findings({ findings }: { findings: Finding[] }) {
  return findings.length ? (
    <ul className="findings">
      {findings.map((finding, i) => (
        <li key={i}>
          <Status tone="review">Review</Status>
          <div>
            <strong>{finding.code.replaceAll('_', ' ')}</strong>
            <p>{finding.message}</p>
            <p className="muted">
              {finding.puzzle_ids.join(', ')}
              {finding.words.length ? ` · ${finding.words.join(', ')}` : ''}
            </p>
          </div>
        </li>
      ))}
    </ul>
  ) : (
    <p className="quality-clear">
      <Status tone="pass">No findings</Status> The configured checks found nothing to flag.
    </p>
  );
}
