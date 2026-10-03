import { useState } from 'react';
import type { Generation, Project, PuzzleResult } from './types';
import { Details, Findings, Issues, Status } from './ui';

function MiniGrid({ result }: { result: PuzzleResult }) {
  return (
    <div className="mini-grid" aria-hidden="true">
      {result.puzzle?.grid
        .slice(0, 6)
        .map((row, i) => <div key={i}>{row.slice(0, 8).split('').join(' ')}</div>) ?? (
        <span>No grid</span>
      )}
    </div>
  );
}

export function PuzzleList({ project, generation }: { project: Project; generation: Generation }) {
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>Puzzles for review</h2>
          <p className="muted">Generated from the current source. Select a puzzle to inspect it.</p>
        </div>
        <Status tone={generation.report.success ? 'pass' : 'fail'}>
          {generation.report.success ? 'Generation complete' : 'Generation has failures'}
        </Status>
      </div>
      <div className="puzzle-list">
        {generation.report.puzzles.map((result, index) => {
          const findings = generation.report.findings.filter((f) =>
            f.puzzle_ids.includes(result.id),
          );
          return (
            <article key={result.id} className="puzzle-row">
              <MiniGrid result={result} />
              <div>
                <p className="muted small">
                  Puzzle {String(index + 1).padStart(2, '0')} · {result.theme}
                </p>
                <h3>
                  <a href={`/books/${project.key}/puzzles/${result.id}`}>{result.title}</a>
                </h3>
                <p>
                  {result.puzzle?.targets.length ??
                    project.source?.word_search?.puzzles.find((p) => p.id === result.id)?.target_ids
                      .length}{' '}
                  targets · {result.difficulty}
                  {result.puzzle
                    ? ` · ${result.puzzle.config.width} × ${result.puzzle.config.height}`
                    : ''}
                </p>
                <div className="status-row">
                  <Status tone={result.puzzle ? 'pass' : 'fail'}>
                    {result.puzzle ? 'Generated' : 'Generation failed'}
                  </Status>
                  {result.puzzle && (
                    <Status tone={generation.verification[result.id]?.valid ? 'pass' : 'fail'}>
                      {generation.verification[result.id]?.valid
                        ? 'Verified'
                        : 'Verification failed'}
                    </Status>
                  )}
                  <Status tone={findings.length ? 'review' : 'neutral'}>
                    {findings.length
                      ? `${findings.length} review findings`
                      : result.puzzle
                        ? 'No findings'
                        : 'Grid checks unavailable'}
                  </Status>
                </div>
                {result.errors.length > 0 && <Issues issues={result.errors} />}
              </div>
              <a className="book-open" href={`/books/${project.key}/puzzles/${result.id}`}>
                Inspect <span className="sr-only">{result.title}</span>
                <span aria-hidden="true"> ↗</span>
              </a>
            </article>
          );
        })}
      </div>
    </>
  );
}

export function Inspector({
  project,
  generation,
  result,
}: {
  project: Project;
  generation: Generation;
  result: PuzzleResult;
}) {
  const [solution, setSolution] = useState(false);
  const puzzle = result.puzzle;
  const cells = generation.solution_cells[result.id] ?? {};
  const membership = new Map<string, string[]>();
  if (solution)
    for (const [target, coordinates] of Object.entries(cells))
      for (const cell of coordinates) {
        const key = `${cell.x},${cell.y}`;
        membership.set(key, [...(membership.get(key) ?? []), target]);
      }
  const findings = generation.report.findings.filter((f) => f.puzzle_ids.includes(result.id));
  return (
    <>
      <div className="section-heading inspector-heading">
        <div>
          <a className="back-link" href={`/books/${project.key}/puzzles`}>
            All puzzles
          </a>
          <h2>{result.title}</h2>
          <p className="muted">
            {result.theme} · {result.difficulty} profile
          </p>
        </div>
        {puzzle && (
          <button
            className={solution ? 'primary' : ''}
            aria-pressed={solution}
            onClick={() => setSolution((value) => !value)}
          >
            {solution ? 'Hide solution' : 'Show solution'}
          </button>
        )}
      </div>
      {!puzzle ? (
        <section className="notice error">
          <h3>Generation failed</h3>
          <Issues issues={result.errors} />
          <p>The engine kept the authored words, dimensions, and search limits.</p>
          <p>Review the source configuration on disk before trying again.</p>
          {result.failure_stats && (
            <p>
              {result.failure_stats.attempts} attempts · {result.failure_stats.restarts} restarts
            </p>
          )}
        </section>
      ) : (
        <>
          <div className="inspector-layout">
            <section className="puzzle-paper" aria-label="Generated puzzle">
              <div className="paper-heading">
                <span>WORD SEARCH</span>
                <span>
                  {puzzle.config.width} × {puzzle.config.height}
                </span>
              </div>
              <h3>{result.title}</h3>
              <p className="paper-instruction">
                {solution ? 'Authoritative solution placements' : 'Find the words. Take your time.'}
              </p>
              <div
                className="grid-scroll"
                tabIndex={0}
                role="region"
                aria-label="Letter grid, scroll horizontally for large puzzles"
              >
                <table className="letter-grid">
                  <caption className="sr-only">
                    {result.title}, {puzzle.config.height} rows and {puzzle.config.width} columns.{' '}
                    {solution ? 'Solution cells are marked and listed below.' : 'Puzzle view.'}
                  </caption>
                  <tbody>
                    {puzzle.grid.map((row, y) => (
                      <tr key={y}>
                        {[...row].map((letter, x) => {
                          const targets = membership.get(`${x},${y}`);
                          return (
                            <td
                              key={x}
                              className={targets ? 'solution-cell' : ''}
                              data-x={x}
                              data-y={y}
                              aria-label={`Row ${y + 1}, column ${x + 1}: ${letter}${targets ? `, solution for ${targets.join(', ')}` : ''}`}
                            >
                              {letter}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="paper-footer">
                {solution
                  ? 'Underlined letters belong to the solution.'
                  : `${puzzle.targets.length} words · ${puzzle.config.directions.length} placement directions`}
              </p>
            </section>
            <aside className="inspector-notes" aria-label="Puzzle details">
              <Status tone={generation.verification[result.id]?.valid ? 'pass' : 'fail'}>
                {generation.verification[result.id]?.valid
                  ? 'Independently verified'
                  : 'Verification failed'}
              </Status>
              <h3>Find these words</h3>
              <ul className="target-list">
                {puzzle.targets.map((target) => (
                  <li key={target.id}>
                    <span>{target.display}</span>
                    <small>{target.search.length} letters</small>
                  </li>
                ))}
              </ul>
              <h3>Generation details</h3>
              <dl className="facts">
                <div>
                  <dt>Profile</dt>
                  <dd>{result.difficulty}</dd>
                </div>
                <div>
                  <dt>Dimensions</dt>
                  <dd>
                    {puzzle.config.width} × {puzzle.config.height}
                  </dd>
                </div>
                <div>
                  <dt>Seed</dt>
                  <dd>
                    <code>{result.seed}</code>
                  </dd>
                </div>
                <div>
                  <dt>Work</dt>
                  <dd>
                    {puzzle.stats.attempts} attempts · {puzzle.stats.restarts} restarts
                  </dd>
                </div>
              </dl>
              <Details title="Enabled directions">
                <p>{puzzle.config.directions.join(', ')}</p>
              </Details>
              <p className="small muted">
                Read-only analysis. The grid and solution come from the Python engine.
              </p>
            </aside>
          </div>
          {solution && (
            <section className="solution-register">
              <h3>Solution register</h3>
              <p className="muted">
                Coordinates are one-based (column, row) for reading. The API retains zero-based
                coordinates.
              </p>
              <ul>
                {puzzle.placements.map((placement) => (
                  <li key={placement.target_id}>
                    <strong>
                      {puzzle.targets.find((t) => t.id === placement.target_id)?.display}
                    </strong>
                    <span>
                      ({placement.start.x + 1}, {placement.start.y + 1}) → ({placement.end.x + 1},{' '}
                      {placement.end.y + 1})
                    </span>
                    <span>{placement.direction}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
      <section>
        <h2>Quality review</h2>
        {puzzle ? (
          <>
            <Findings findings={findings} />
            <p className="muted">
              {result.quality?.prohibited_screening_enabled
                ? 'Prohibited-word screening enabled using the authored policy list.'
                : 'Prohibited-word screening disabled. No policy list is configured.'}
            </p>
            {result.quality && (
              <Details title="Occurrence coordinates & screening completeness">
                <p>
                  Accidental-target scan:{' '}
                  {result.quality.accidental_targets.truncated ? 'incomplete' : 'complete'}.
                  Prohibited-word scan:{' '}
                  {!result.quality.prohibited_screening_enabled
                    ? 'disabled'
                    : result.quality.prohibited.truncated
                      ? 'incomplete'
                      : 'complete'}
                  .
                </p>
                <pre>{JSON.stringify(result.quality, null, 2)}</pre>
              </Details>
            )}
          </>
        ) : (
          <p>Grid quality checks are unavailable because generation failed.</p>
        )}
      </section>
    </>
  );
}

export function Quality({ generation }: { generation: Generation }) {
  const report = generation.report;
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>A considered review</h2>
          <p className="muted">
            Descriptive checks on this generated batch. Findings never change a puzzle.
          </p>
        </div>
        <Status tone={!report.success ? 'fail' : report.clean ? 'pass' : 'review'}>
          {!report.success ? 'Generation failed' : report.clean ? 'No findings' : 'Review findings'}
        </Status>
      </div>
      {!report.success && (
        <div className="notice error">
          <h3>Some puzzles could not be generated</h3>
          <p>
            Authored-content comparisons remain available. Grid checks only cover successfully
            generated puzzles.
          </p>
          {report.puzzles
            .filter((p) => !p.puzzle)
            .map((p) => (
              <div key={p.id}>
                <strong>{p.title}</strong>
                <Issues issues={p.errors} />
              </div>
            ))}
        </div>
      )}
      <Findings findings={report.findings} />
      <p>
        {report.quality_config.prohibited_words.length
          ? `Screening policy: ${report.quality_config.prohibited_words.join(', ')}`
          : 'Prohibited-word screening is disabled. No policy words are configured.'}
      </p>
      <p className="muted">
        A clean report describes only the configured checks. It does not certify originality or
        publication readiness.
      </p>
      <section>
        <h2>Across the book</h2>
        <h3>Word reuse</h3>
        {report.reuse.length ? (
          <ul>
            {report.reuse.map((r) => (
              <li key={r.word}>
                {r.word}: {r.puzzle_ids.join(', ')}
              </li>
            ))}
          </ul>
        ) : (
          <p>No target words are shared between definitions.</p>
        )}
        <h3>Puzzle comparisons</h3>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Puzzle comparisons">
          <table className="data-table">
            <caption className="sr-only">Pairwise target and grid similarity</caption>
            <thead>
              <tr>
                <th scope="col">Puzzle pair</th>
                <th scope="col">Target Jaccard</th>
                <th scope="col">Target overlap</th>
                <th scope="col">Grid agreement</th>
              </tr>
            </thead>
            <tbody>
              {report.similarities.map((s) => (
                <tr key={`${s.left_id}-${s.right_id}`}>
                  <th scope="row">
                    {s.left_id} / {s.right_id}
                  </th>
                  <td>{s.target_jaccard.toFixed(3)}</td>
                  <td>{s.target_overlap.toFixed(3)}</td>
                  <td>{s.grid_agreement === null ? 'Unavailable' : s.grid_agreement.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!report.similarities.length && (
          <p>At least two definitions are needed for pairwise comparisons.</p>
        )}
      </section>
      <Details title="Complete engine quality report">
        <pre>
          {JSON.stringify(
            {
              findings: report.findings,
              reuse: report.reuse,
              similarities: report.similarities,
              puzzles: report.puzzles.map((p) => ({ id: p.id, quality: p.quality })),
            },
            null,
            2,
          )}
        </pre>
      </Details>
    </>
  );
}
