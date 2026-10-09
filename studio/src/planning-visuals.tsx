import type { PlanningReport } from './types';

// Planning visuals. Every number comes from Python's report; each chart is a
// semantic table whose values are printed as text, so bars and shades only
// repeat what the text says. One hue throughout: magnitude is length, level is
// a light-to-dark step of the same green with its rank printed in the cell.

function pct(value: number, scale: number) {
  return `${scale > 0 ? Math.min(100, (value / scale) * 100) : 0}%`;
}

export function AllocationChart({ report }: { report: PlanningReport }) {
  const rows = report.allocation;
  const target = report.summary.target_puzzles;
  const scale = Math.max(1, ...rows.map((r) => r.allocated ?? 0), ...rows.map((r) => r.specified));
  if (!rows.length) return <p className="muted">No themes planned yet.</p>;
  return (
    <figure className="plan-figure">
      <table className="plan-chart">
        <caption>
          Puzzles by theme: {report.summary.allocated_puzzles} allocated of a target of{' '}
          {target ?? 'not set'}; {report.summary.specified_puzzles} specified.
        </caption>
        <thead>
          <tr>
            <th scope="col">Theme</th>
            <th scope="col" className="num">
              Allocated
            </th>
            <th scope="col" className="num">
              Specified
            </th>
            <th scope="col">
              <span className="visually-hidden">Bars</span>
              <span className="chart-legend" aria-hidden="true">
                <span>
                  <i className="swatch allocated" /> Allocated
                </span>
                <span>
                  <i className="swatch specified" /> Specified
                </span>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <th scope="row" style={{ paddingLeft: `${r.depth * 16}px` }}>
                {r.label}
                {r.required && <small className="muted"> required</small>}
              </th>
              <td className="num">{r.allocated ?? 'not set'}</td>
              <td className="num">{r.specified}</td>
              <td aria-hidden="true">
                <div
                  className="bar-track"
                  title={`${r.label}: ${r.allocated ?? 'not set'} allocated, ${r.specified} specified`}
                >
                  <div className="bar allocated" style={{ width: pct(r.allocated ?? 0, scale) }} />
                  <div className="bar specified" style={{ width: pct(r.specified, scale) }} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function shade(rank: number | null, levels: number) {
  if (rank === null || levels < 1) return undefined;
  const step = levels === 1 ? 1 : (rank - 1) / (levels - 1);
  const amount = Math.round(18 + step * 82);
  return {
    background: `color-mix(in oklab, var(--green) ${amount}%, var(--wash))`,
    color: amount >= 55 ? 'var(--paper)' : 'var(--ink)',
  };
}

export function ProgressionChart({ report }: { report: PlanningReport }) {
  const levels = report.levels;
  const sequence = report.progression;
  const target = report.summary.target_puzzles;
  const missing = target !== null ? Math.max(0, target - sequence.length) : 0;
  if (!sequence.length && !levels.length)
    return <p className="muted">No levels or planned puzzles yet.</p>;
  return (
    <figure className="plan-figure">
      <figcaption>
        Difficulty in book order, by the level each planned puzzle uses (1 is the easiest level you
        declared). Level order is your judgment; PuzzlePress does not measure difficulty.
      </figcaption>
      <ul className="level-legend" aria-label="Levels">
        {levels.map((l) => (
          <li key={l.id}>
            <span className="level-cell" style={shade(l.rank, levels.length)}>
              {l.rank}
            </span>{' '}
            {l.label}{' '}
            <small className="muted">
              {l.width && l.height ? `${l.width} x ${l.height}` : 'grid not set'}, {l.words.min}-
              {l.words.max} words, {l.puzzles} planned
            </small>
          </li>
        ))}
      </ul>
      <ol className="progression" aria-label="Planned puzzles in book order">
        {sequence.map((p, i) => {
          const level = levels.find((l) => l.id === p.level);
          return (
            <li
              key={p.id}
              className="level-cell"
              style={shade(p.rank, levels.length)}
              title={`${i + 1}. ${p.title ?? p.id}: ${level?.label ?? 'no level'}, ${p.words} words`}
            >
              <span aria-hidden="true">{p.rank ?? '?'}</span>
              <span className="visually-hidden">
                Puzzle {i + 1}, {p.title ?? p.id}: {level?.label ?? 'no level'}
              </span>
            </li>
          );
        })}
        {missing > 0 && <li className="level-cell unspecified">{missing} not yet specified</li>}
      </ol>
      <details className="details">
        <summary>Progression as a table</summary>
        <table className="plan-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Puzzle</th>
              <th scope="col">Theme</th>
              <th scope="col">Level</th>
              <th scope="col">Words</th>
            </tr>
          </thead>
          <tbody>
            {sequence.map((p, i) => (
              <tr key={p.id}>
                <td>{i + 1}</td>
                <td>{p.title ?? p.id}</td>
                <td>{p.theme}</td>
                <td>{levels.find((l) => l.id === p.level)?.label ?? 'none'}</td>
                <td>{p.words}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

export function VocabularyChart({ report }: { report: PlanningReport }) {
  const rows = report.vocabulary;
  if (!rows.length) return <p className="muted">No candidate vocabulary yet.</p>;
  const scale = Math.max(1, ...rows.map((r) => Math.max(r.usable, r.needed ?? 0)));
  return (
    <figure className="plan-figure">
      <table className="plan-chart">
        <caption>
          Usable candidate words per theme against the distinct words its allocation needs within
          the reuse limit.
        </caption>
        <thead>
          <tr>
            <th scope="col">Theme</th>
            <th scope="col" className="num">
              Usable
            </th>
            <th scope="col" className="num">
              Needed
            </th>
            <th scope="col">
              <span className="visually-hidden">Bars</span>
              <span className="chart-legend" aria-hidden="true">
                <span>
                  <i className="swatch specified" /> Usable
                </span>
                <span>
                  <i className="swatch tick" /> Needed
                </span>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.theme}>
              <th scope="row">
                {r.label ?? r.theme}
                {(r.invalid > 0 || r.duplicates > 0) && (
                  <small className="muted">
                    {' '}
                    {r.invalid} invalid, {r.duplicates} duplicate
                  </small>
                )}
              </th>
              <td className="num">{r.usable}</td>
              <td className="num">{r.needed ?? '-'}</td>
              <td aria-hidden="true">
                <div
                  className="bar-track"
                  title={`${r.label ?? r.theme}: ${r.usable} usable, ${r.needed ?? 'no'} needed`}
                >
                  <div className="bar specified" style={{ width: pct(r.usable, scale) }} />
                  {r.needed !== null && (
                    <div className="bar-tick" style={{ left: pct(r.needed, scale) }} />
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
