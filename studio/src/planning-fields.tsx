import { useEffect, useRef, useState, type ReactNode } from 'react';
import { FieldErrors, matchIssues } from './editor-fields';
import type { Issue, PlanFinding } from './types';
import { Status } from './ui';

// Small planning form controls. Each shows the Python schema issues and planning
// findings for its own path; none of them validates anything itself. Empty
// optional text becomes null (explicitly unknown); typed text is sent exactly.

export interface Notes {
  issues: Issue[];
  findings: PlanFinding[];
}

export const SEVERITY = {
  error: ['fail', 'Blocking'],
  warning: ['review', 'Review'],
  info: ['neutral', 'Note'],
} as const;

const own = (findings: PlanFinding[], path: string) => findings.filter((f) => f.path === path);

export function described(id: string, notes: Notes, hint?: string) {
  return (
    [
      hint ? `${id}-hint` : '',
      own(notes.findings, id).length ? `${id}-findings` : '',
      matchIssues(notes.issues, id).length ? `${id}-issues` : '',
    ]
      .filter(Boolean)
      .join(' ') || undefined
  );
}

export function invalid(id: string, notes: Notes) {
  return matchIssues(notes.issues, id).length ||
    own(notes.findings, id).some((f) => f.severity === 'error')
    ? true
    : undefined;
}

export function FindingList({ id, findings }: { id: string; findings: PlanFinding[] }) {
  if (!findings.length) return null;
  return (
    <ul className="field-findings" id={`${id}-findings`}>
      {findings.map((f, i) => (
        <li key={i}>
          <Status tone={SEVERITY[f.severity][0]}>{SEVERITY[f.severity][1]}</Status> {f.message}
          {f.action && <span className="muted"> {f.action}</span>}
        </li>
      ))}
    </ul>
  );
}

export function FieldNotes({ id, notes }: { id: string; notes: Notes }) {
  return (
    <>
      <FindingList id={id} findings={own(notes.findings, id)} />
      <FieldErrors id={id} issues={matchIssues(notes.issues, id)} />
    </>
  );
}

// A whole number, null when empty, or the text itself so Python reports it.
export function whole(value: string): number | null {
  if (value.trim() === '') return null;
  const n = Number(value);
  return Number.isInteger(n) ? n : (value as unknown as number);
}

export function TextField({
  label,
  path,
  value,
  onChange,
  notes,
  multiline = false,
  required = false,
  hint,
  type = 'text',
}: {
  label: string;
  path: string;
  value: string | null;
  onChange: (value: string | null) => void;
  notes: Notes;
  multiline?: boolean;
  required?: boolean;
  hint?: string;
  type?: string;
}) {
  const props = {
    id: path,
    value: value ?? '',
    'aria-invalid': invalid(path, notes),
    'aria-describedby': described(path, notes, hint),
    onChange: (e: { target: { value: string } }) =>
      onChange(e.target.value === '' && !required ? null : e.target.value),
  };
  return (
    <div className="editor-field">
      <label htmlFor={path}>{label}</label>
      {multiline ? <textarea rows={3} {...props} /> : <input type={type} {...props} />}
      {hint && (
        <p className="small muted field-hint" id={`${path}-hint`}>
          {hint}
        </p>
      )}
      <FieldNotes id={path} notes={notes} />
    </div>
  );
}

export function NumberField({
  label,
  path,
  value,
  onChange,
  notes,
  hint,
}: {
  label: string;
  path: string;
  value: number | null;
  onChange: (value: number | null) => void;
  notes: Notes;
  hint?: string;
}) {
  return (
    <div className="editor-field">
      <label htmlFor={path}>{label}</label>
      <input
        id={path}
        inputMode="numeric"
        value={value ?? ''}
        aria-invalid={invalid(path, notes)}
        aria-describedby={described(path, notes, hint)}
        onChange={(e) => onChange(whole(e.target.value))}
      />
      {hint && (
        <p className="small muted field-hint" id={`${path}-hint`}>
          {hint}
        </p>
      )}
      <FieldNotes id={path} notes={notes} />
    </div>
  );
}

export function Select({
  label,
  path,
  value,
  options,
  onChange,
  notes,
  hint,
}: {
  label: string;
  path: string;
  value: string | null;
  options: [string | null, string][];
  onChange: (value: string | null) => void;
  notes: Notes;
  hint?: string;
}) {
  const known = options.some(([v]) => v === value);
  return (
    <div className="editor-field">
      <label htmlFor={path}>{label}</label>
      <select
        id={path}
        value={value ?? ''}
        aria-invalid={invalid(path, notes)}
        aria-describedby={described(path, notes, hint)}
        onChange={(e) => {
          const option = options.find(([v]) => (v ?? '') === e.target.value);
          onChange(option ? option[0] : e.target.value);
        }}
      >
        {!known && <option value={value ?? ''}>{value}</option>}
        {options.map(([v, text]) => (
          <option key={v ?? ''} value={v ?? ''}>
            {text}
          </option>
        ))}
      </select>
      {hint && (
        <p className="small muted field-hint" id={`${path}-hint`}>
          {hint}
        </p>
      )}
      <FieldNotes id={path} notes={notes} />
    </div>
  );
}

export function Radios({
  legend,
  path,
  value,
  options,
  onChange,
  notes,
}: {
  legend: string;
  path: string;
  value: string;
  options: [string, string, string?][];
  onChange: (value: string) => void;
  notes: Notes;
}) {
  return (
    <fieldset className="choice-group" id={path} aria-describedby={described(path, notes)}>
      <legend>{legend}</legend>
      {options.map(([v, text, hint]) => (
        <label key={v}>
          <input
            type="radio"
            name={path}
            value={v}
            checked={value === v}
            onChange={() => onChange(v)}
          />
          <span>
            {text}
            {hint && <small>{hint}</small>}
          </span>
        </label>
      ))}
      <FieldNotes id={path} notes={notes} />
    </fieldset>
  );
}

export function Check({
  label,
  checked,
  onChange,
  hint,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (value: boolean) => void;
  hint?: string;
}) {
  return (
    <label className="check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>
        {label}
        {hint && <small className="muted"> {hint}</small>}
      </span>
    </label>
  );
}

export function ListField({
  legend,
  path,
  items,
  onChange,
  notes,
  addLabel,
  hint,
}: {
  legend: string;
  path: string;
  items: string[];
  onChange: (items: string[]) => void;
  notes: Notes;
  addLabel: string;
  hint?: string;
}) {
  const list = useRef<HTMLOListElement>(null);
  return (
    <fieldset className="choice-group text-list" id={path}>
      <legend>
        {legend} <span className="muted">({items.length})</span>
      </legend>
      {hint && (
        <p className="small muted field-hint" id={`${path}-hint`}>
          {hint}
        </p>
      )}
      <ol ref={list}>
        {items.map((item, i) => {
          const id = `${path}.${i}`;
          return (
            <li key={i}>
              <label htmlFor={id} className="visually-hidden">
                {legend} {i + 1}
              </label>
              <input
                id={id}
                value={item}
                aria-invalid={invalid(id, notes)}
                aria-describedby={described(id, notes)}
                onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))}
              />
              <button
                type="button"
                aria-label={`Remove ${legend.toLowerCase()} ${i + 1}`}
                onClick={() => onChange(items.filter((_, j) => j !== i))}
              >
                Remove
              </button>
              <FieldNotes id={id} notes={notes} />
            </li>
          );
        })}
      </ol>
      <button
        type="button"
        onClick={() => {
          onChange([...items, '']);
          requestAnimationFrame(() =>
            list.current?.querySelector<HTMLInputElement>('li:last-child input')?.focus(),
          );
        }}
      >
        {addLabel}
      </button>
      <FieldNotes id={path} notes={notes} />
    </fieldset>
  );
}

// One word or phrase a line. The text area keeps exactly what the author typed
// (including a line still being written); the list sent to Python is its nonblank
// lines, each as typed.
export function LinesField({
  label,
  path,
  lines,
  onChange,
  notes,
  hint,
  resetKey,
}: {
  label: string;
  path: string;
  lines: string[];
  onChange: (lines: string[]) => void;
  notes: Notes;
  hint?: string;
  resetKey: string;
}) {
  const [text, setText] = useState(lines.join('\n'));
  useEffect(() => setText(lines.join('\n')), [resetKey]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="editor-field">
      <label htmlFor={path}>{label}</label>
      <textarea
        id={path}
        rows={10}
        value={text}
        spellCheck={false}
        aria-describedby={described(path, notes, hint)}
        onChange={(e) => {
          setText(e.target.value);
          onChange(e.target.value.split('\n').filter((line) => line.trim() !== ''));
        }}
      />
      {hint && (
        <p className="small muted field-hint" id={`${path}-hint`}>
          {hint}
        </p>
      )}
      <FieldNotes id={path} notes={notes} />
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

export function RowActions({
  label,
  index,
  count,
  onMove,
  onRemove,
}: {
  label: string;
  index: number;
  count: number;
  onMove: (direction: number) => void;
  onRemove: () => void;
}) {
  return (
    <span className="row-actions">
      <button
        type="button"
        aria-label={`Move ${label} up`}
        disabled={index === 0}
        onClick={() => onMove(-1)}
      >
        Up
      </button>
      <button
        type="button"
        aria-label={`Move ${label} down`}
        disabled={index === count - 1}
        onClick={() => onMove(1)}
      >
        Down
      </button>
      <button type="button" aria-label={`Remove ${label}`} onClick={onRemove}>
        Remove
      </button>
    </span>
  );
}

export function nextId(prefix: string, taken: string[]) {
  let n = taken.length + 1;
  while (taken.includes(`${prefix}-${n}`)) n++;
  return `${prefix}-${n}`;
}
