import type { PublishingFinding, PublishingRule, PublishingStatus } from './types';
import { Status } from './ui';

// The readiness checklist: Python's rule results and findings, grouped by where the
// author acts. Grouping is presentation only; every verdict and message is Python's.

type Group = {
  key: string;
  title: string;
  codes: (code: string) => boolean;
  link: (base: string) => { href: string; label: string };
};

const starts =
  (...prefixes: string[]) =>
  (code: string) =>
    prefixes.some((prefix) => code.startsWith(prefix));

export const GROUPS: Group[] = [
  {
    key: 'content',
    title: 'Book content',
    codes: (code) =>
      starts('title_', 'names_', 'contributors_', 'imprint_', 'language_')(code) ||
      ['author_present', 'description_claims'].includes(code),
    link: (base) => ({ href: `${base}/book`, label: 'Open Book' }),
  },
  {
    key: 'interior',
    title: 'Interior',
    codes: (code) =>
      starts('interior_')(code) || ['output_directory', 'saved_reports'].includes(code),
    link: (base) => ({ href: `${base}/print`, label: 'Open Print proof' }),
  },
  {
    key: 'cover',
    title: 'Cover',
    codes: starts('cover_'),
    link: (base) => ({ href: `${base}/cover`, label: 'Open Cover' }),
  },
  {
    key: 'metadata',
    title: 'Metadata',
    codes: (code) =>
      starts('description_', 'keywords_')(code) ||
      ['publishing_configured', 'series_eligibility'].includes(code),
    link: () => ({ href: '#publishing.description', label: 'Go to description' }),
  },
  {
    key: 'disclosure',
    title: 'Rights and AI disclosure',
    codes: starts('ai_disclosure_'),
    link: () => ({ href: '#publishing.ai_disclosure.text', label: 'Go to AI disclosure' }),
  },
  {
    key: 'classification',
    title: 'ISBN and classification',
    codes: starts('isbn_', 'low_content_', 'audience_', 'categories_'),
    link: () => ({ href: '#publishing.isbn.mode', label: 'Go to ISBN' }),
  },
  {
    key: 'confirmations',
    title: 'Final confirmations',
    codes: (code) => code === 'attestations',
    link: () => ({ href: '#publishing.attestations', label: 'Go to confirmations' }),
  },
];

export function groupOf(code: string): string {
  return GROUPS.find((group) => group.codes(code))?.key ?? 'metadata';
}

function tally(rules: PublishingRule[], findings: PublishingFinding[]) {
  const blocking =
    findings.filter((f) => f.severity === 'error').length +
    rules.filter((r) => r.outcome === 'not_evaluated' && r.severity === 'error').length;
  const review = findings.filter((f) => f.severity === 'warning').length;
  const passed = rules.filter((r) => r.outcome === 'passed').length;
  return { blocking, review, passed };
}

export function PublishingChecklist({
  status,
  projectKey,
}: {
  status: PublishingStatus;
  projectKey: string;
}) {
  const r = status.readiness;
  const base = `/books/${encodeURIComponent(projectKey)}`;
  return (
    <ol className="checklist-groups" aria-label="Publishing checklist">
      {GROUPS.map((group) => {
        const rules = r.rules.filter((rule) => group.codes(rule.code));
        const findings = r.findings.filter((f) => groupOf(f.code) === group.key);
        const unchecked = rules.filter(
          (rule) => rule.outcome === 'not_evaluated' && rule.severity === 'error',
        );
        const { blocking, review, passed } = tally(rules, findings);
        const link = group.link(base);
        const tone = blocking ? 'fail' : review ? 'review' : 'pass';
        const summary = blocking
          ? `${blocking} blocking`
          : review
            ? `${review} to review`
            : rules.length
              ? 'Complete'
              : 'Nothing to check';
        return (
          <li key={group.key} className={`checklist-group ${tone}`}>
            <details open={blocking > 0}>
              <summary>
                <Status tone={tone}>{summary}</Status>
                <span className="checklist-title">{group.title}</span>
                <span className="small muted">
                  {passed}/{rules.length} checks passed
                </span>
              </summary>
              <div className="checklist-body">
                {findings.length === 0 && unchecked.length === 0 && (
                  <p className="small muted">Every check in this group passed or does not apply.</p>
                )}
                <ul className="finding-list">
                  {findings.map((f, i) => (
                    <li key={`${f.code}-${i}`}>
                      <Status
                        tone={
                          f.severity === 'error'
                            ? 'fail'
                            : f.severity === 'warning'
                              ? 'review'
                              : 'neutral'
                        }
                      >
                        {f.severity === 'error'
                          ? 'Blocking'
                          : f.severity === 'warning'
                            ? 'Review'
                            : 'Note'}
                      </Status>
                      <p>{f.message}</p>
                      {f.action && <p className="small">{f.action}</p>}
                      <p className="finding-meta">
                        {f.area === 'publishing' && f.field ? (
                          <a href={`#${f.field}`}>Go to field</a>
                        ) : (
                          <a href={`${base}/${f.area}`}>Open {f.area}</a>
                        )}{' '}
                        · <code>{f.code}</code> ·{' '}
                        {f.source.url.startsWith('http') ? (
                          <a href={f.source.url} target="_blank" rel="noreferrer">
                            {f.source.title}
                          </a>
                        ) : (
                          f.source.title
                        )}
                      </p>
                    </li>
                  ))}
                  {unchecked.length > 0 && (
                    <li>
                      <Status tone="fail">Not checked</Status>
                      <p>
                        {unchecked.length === 1 ? 'One check' : `${unchecked.length} checks`} could
                        not run yet ({unchecked.map((rule) => rule.title.toLowerCase()).join('; ')}
                        ): {unchecked[0].note ?? 'a prerequisite is missing'}. Unchecked rules block
                        export.
                      </p>
                    </li>
                  )}
                </ul>
                <a className="small" href={link.href}>
                  {link.label}
                </a>
              </div>
            </details>
          </li>
        );
      })}
    </ol>
  );
}
