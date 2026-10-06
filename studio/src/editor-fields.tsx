import type { Issue, Project } from './types';
import { Issues } from './ui';

export type Source = NonNullable<Project['source']>;
export type Content = NonNullable<Source['word_search']>;

export function matchIssues(issues: Issue[], path: string) {
  return issues.filter((i) => i.path === path || i.path.startsWith(path + '.'));
}

export function FieldErrors({ id, issues }: { id: string; issues: Issue[] }) {
  return issues.length > 0 ? (
    <div className="field-errors" id={`${id}-issues`}>
      <Issues issues={issues} />
    </div>
  ) : null;
}

export function Field({
  label,
  path,
  value,
  issues,
  onChange,
  type = 'text',
  id = path,
  multiline = false,
  hint,
}: {
  label: string;
  path: string;
  value: string | number;
  issues: Issue[];
  onChange: (value: string) => void;
  type?: string;
  id?: string;
  multiline?: boolean;
  hint?: string;
}) {
  const matching = matchIssues(issues, path);
  const described = [hint ? `${id}-hint` : '', matching.length ? `${id}-issues` : '']
    .filter(Boolean)
    .join(' ');
  const props = {
    id,
    value: typeof value === 'number' && Number.isNaN(value) ? '' : value,
    'aria-invalid': matching.length ? true : undefined,
    'aria-describedby': described || undefined,
  };
  return (
    <div className="editor-field">
      <label htmlFor={id}>{label}</label>
      {multiline ? (
        <textarea {...props} rows={4} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input {...props} type={type} onChange={(e) => onChange(e.target.value)} />
      )}
      {hint && (
        <p className="small muted field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      <FieldErrors id={id} issues={matching} />
    </div>
  );
}

export function SelectField({
  label,
  path,
  value,
  options,
  issues,
  onChange,
}: {
  label: string;
  path: string;
  value: string;
  options: [string, string][];
  issues: Issue[];
  onChange: (value: string) => void;
}) {
  const matching = matchIssues(issues, path);
  return (
    <div className="editor-field">
      <label htmlFor={path}>{label}</label>
      <select
        id={path}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={matching.length ? true : undefined}
        aria-describedby={matching.length ? `${path}-issues` : undefined}
      >
        {!options.some(([v]) => v === value) && <option value={value}>{value}</option>}
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
      <FieldErrors id={path} issues={matching} />
    </div>
  );
}

export function move<T>(items: T[], index: number, direction: number): T[] {
  const copy = [...items];
  const next = index + direction;
  if (next < 0 || next >= copy.length) return copy;
  [copy[index], copy[next]] = [copy[next], copy[index]];
  return copy;
}
