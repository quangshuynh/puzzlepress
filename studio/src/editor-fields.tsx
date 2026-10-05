import type { Issue, Project } from './types';
import { Issues } from './ui';

export type Source = NonNullable<Project['source']>;
export type Content = NonNullable<Source['word_search']>;

export function Field({
  label,
  path,
  value,
  issues,
  onChange,
  type = 'text',
}: {
  label: string;
  path: string;
  value: string | number;
  issues: Issue[];
  onChange: (value: string) => void;
  type?: string;
}) {
  const matching = issues.filter((i) => i.path === path || i.path.startsWith(path + '.'));
  return (
    <div className="editor-field">
      <label htmlFor={path}>{label}</label>
      <input
        id={path}
        type={type}
        value={typeof value === 'number' && Number.isNaN(value) ? '' : value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={matching.length ? true : undefined}
        aria-describedby={matching.length ? `${path}-issues` : undefined}
      />
      {matching.length > 0 && (
        <div className="field-errors" id={`${path}-issues`}>
          <Issues issues={matching} />
        </div>
      )}
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
