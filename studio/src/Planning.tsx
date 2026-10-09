import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError } from './api';
import { usePlanning, type PlanningDraft } from './planning-draft';
import {
  Check,
  FieldNotes,
  FindingList,
  LinesField,
  ListField,
  type Notes,
  NumberField,
  Radios,
  RowActions,
  SEVERITY,
  Select,
  TextField,
  move,
  nextId,
  whole,
} from './planning-fields';
import { AllocationChart, ProgressionChart, VocabularyChart } from './planning-visuals';
import type {
  Evidence,
  PlanComparable,
  PlanFinding,
  PlanLevel,
  PlanNote,
  PlanPool,
  PlanTheme,
  PlannedPuzzle,
  PlanningOptions,
  PlanningReport,
  PlanningSource,
  WordSource,
} from './types';
import { ErrorState, Issues, Loading, Status } from './ui';

// Planning workspace: research, positioning and the book blueprint, before any
// production. Python validates the plan, analyses coverage and feasibility, and
// decides readiness (`puzzlepress plan` shares the same core); this view edits the
// draft planning.yaml and presents Python's findings. It never approves on its
// own, never edits book.yaml and never looks anything up outside this computer.

type Tone = 'pass' | 'review' | 'fail' | 'neutral';
type Change = (next: PlanningSource) => void;

const SECTIONS: [string, string, string[]][] = [
  ['overview', 'Overview', ['concept', 'structure']],
  ['audience', 'Audience', ['positioning']],
  ['research', 'Research', ['questions', 'research']],
  ['comparables', 'Comparable books', ['comparables']],
  ['themes', 'Themes', ['themes']],
  ['puzzles', 'Puzzle allocation', ['puzzles']],
  ['vocabulary', 'Vocabulary', ['vocabulary', 'constraints']],
  ['difficulty', 'Difficulty', ['difficulty']],
  ['coverage', 'Coverage', []],
];
const STATE: Record<PlanningReport['state'], [Tone, string]> = {
  draft: ['neutral', 'Draft'],
  needs_research: ['review', 'Needs research'],
  needs_content: ['review', 'Needs content'],
  structurally_valid: ['review', 'Structurally valid'],
  production_feasible: ['review', 'Production-feasible'],
  ready_for_approval: ['pass', 'Ready for approval'],
  approved: ['pass', 'Approved'],
};
const EVIDENCE: [Evidence, string, string][] = [
  ['verified_source', 'Verified source', 'You read the cited source yourself'],
  ['unverified_source', 'Unverified source', 'Cited, but not checked by you'],
  ['author_observation', 'Your observation', 'Something you noticed; not a study'],
  ['hypothesis', 'Hypothesis', 'An idea still to be tested'],
  ['preference', 'Your preference', 'A choice, not a finding'],
  ['unknown', 'Unknown', 'Not yet classified'],
];
const SOURCES: [WordSource, string][] = [
  ['unknown', 'Not recorded'],
  ['human', 'Written by people'],
  ['public_reference', 'Public factual reference'],
  ['licensed', 'Licensed material'],
  ['ai_assisted', 'AI-assisted'],
  ['ai_generated', 'AI-generated'],
];
const STATUS_TONE: Record<string, Tone> = {
  verified: 'pass',
  estimate: 'neutral',
  unknown: 'neutral',
  unsupported: 'fail',
};

function sectionOf(path: string | null) {
  const head = (path ?? '').split('.')[0];
  return SECTIONS.find(([, , heads]) => heads.includes(head))?.[0] ?? 'coverage';
}

function useSection() {
  const read = () => {
    const id = window.location.hash.replace('#planning-', '');
    return SECTIONS.some(([key]) => key === id) ? id : 'overview';
  };
  const [section, setSection] = useState(read);
  useEffect(() => {
    const update = () => setSection(read());
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  return section;
}

function Section({
  id,
  title,
  intro,
  children,
}: {
  id: string;
  title: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (window.location.hash === `#planning-${id}`) heading.current?.focus();
  }, [id]);
  return (
    <section className="planning-section" aria-labelledby={`plan-${id}-title`}>
      <h3 id={`plan-${id}-title`} ref={heading} tabIndex={-1}>
        {title}
      </h3>
      {intro && <p className="small muted plan-intro">{intro}</p>}
      {children}
    </section>
  );
}

// ------------------------------------------------------------------ sections

function Overview({
  plan,
  change,
  notes,
  options,
}: {
  plan: PlanningSource;
  change: Change;
  notes: Notes;
  options: PlanningOptions;
}) {
  const c = plan.concept;
  const s = plan.structure;
  const concept = (next: Partial<PlanningSource['concept']>) =>
    change({ ...plan, concept: { ...c, ...next } });
  const structure = (next: Partial<PlanningSource['structure']>) =>
    change({ ...plan, structure: { ...s, ...next } });
  return (
    <Section
      id="overview"
      title="Overview"
      intro="What the book is and its planned shape. Leave anything undecided empty; it stays explicitly unknown."
    >
      <h4>Concept</h4>
      <TextField
        label="Book concept"
        path="concept.summary"
        value={c.summary}
        multiline
        notes={notes}
        onChange={(v) => concept({ summary: v })}
      />
      <TextField
        label="Subject or niche"
        path="concept.subject"
        value={c.subject}
        notes={notes}
        onChange={(v) => concept({ subject: v })}
      />
      <TextField
        label="Intended reader experience"
        path="concept.reader_experience"
        value={c.reader_experience}
        multiline
        notes={notes}
        onChange={(v) => concept({ reader_experience: v })}
      />
      <TextField
        label="Scope"
        path="concept.scope"
        value={c.scope}
        multiline
        notes={notes}
        onChange={(v) => concept({ scope: v })}
      />
      <h4>Book structure</h4>
      <div className="field-pair">
        <Select
          label="Puzzle type"
          path="structure.puzzle_type"
          value={s.puzzle_type}
          options={[
            [null, 'Not decided'],
            ...options.puzzle_types.map((t): [string, string] => [t, t.replace('_', ' ')]),
          ]}
          notes={notes}
          onChange={(v) => structure({ puzzle_type: v })}
        />
        <NumberField
          label="Target puzzle count"
          path="structure.target_puzzles"
          value={s.target_puzzles}
          notes={notes}
          onChange={(v) => structure({ target_puzzles: v })}
        />
      </div>
      <Select
        label="Print profile (trim and paper)"
        path="structure.print_profile"
        value={s.print_profile}
        options={[
          [null, 'Not chosen yet'],
          ...options.print_profiles.map((p): [string, string] => [p.id, p.description]),
        ]}
        notes={notes}
        hint="Paper is your decision; PuzzlePress never assumes it."
        onChange={(v) => structure({ print_profile: v })}
      />
      <Radios
        legend="Solutions"
        path="structure.solutions"
        value={s.solutions}
        options={[
          ['undecided', 'Not decided'],
          ['end', 'At the end of the book'],
          ['omit', 'No solutions'],
        ]}
        notes={notes}
        onChange={(v) =>
          structure({ solutions: v, solutions_per_page: v === 'end' ? s.solutions_per_page : null })
        }
      />
      {s.solutions === 'end' && (
        <Select
          label="Solutions a page"
          path="structure.solutions_per_page"
          value={s.solutions_per_page === null ? null : String(s.solutions_per_page)}
          options={[
            [null, 'Not decided'],
            ['1', '1'],
            ['2', '2'],
            ['4', '4'],
            ['6', '6'],
          ]}
          notes={notes}
          onChange={(v) => structure({ solutions_per_page: v === null ? null : whole(v) })}
        />
      )}
      <div className="field-pair">
        <NumberField
          label="Front matter pages"
          path="structure.front_matter_pages"
          value={s.front_matter_pages}
          notes={notes}
          hint="Title, copyright, instructions…"
          onChange={(v) => structure({ front_matter_pages: v })}
        />
        <NumberField
          label="Back matter pages"
          path="structure.back_matter_pages"
          value={s.back_matter_pages}
          notes={notes}
          onChange={(v) => structure({ back_matter_pages: v })}
        />
      </div>
    </Section>
  );
}

function NotePicker({
  legend,
  path,
  selected,
  notes: allNotes,
  onChange,
  hint,
  findings,
}: {
  legend: string;
  path: string;
  selected: string[];
  notes: PlanNote[];
  onChange: (ids: string[]) => void;
  hint?: string;
  findings: Notes;
}) {
  return (
    <fieldset className="choice-group" id={path}>
      <legend>{legend}</legend>
      {hint && <p className="small muted field-hint">{hint}</p>}
      {allNotes.length === 0 && <p className="small muted">No research notes yet.</p>}
      {allNotes.map((n) => (
        <Check
          key={n.id}
          checked={selected.includes(n.id)}
          onChange={(on) => onChange(on ? [...selected, n.id] : selected.filter((x) => x !== n.id))}
          label={
            <>
              <code>{n.id}</code> {n.observation.slice(0, 90)}
              {n.observation.length > 90 ? '…' : ''}{' '}
              <small className="muted">({EVIDENCE.find(([e]) => e === n.evidence)?.[1]})</small>
            </>
          }
        />
      ))}
      {selected
        .filter((id) => !allNotes.some((n) => n.id === id))
        .map((id) => (
          <Check
            key={id}
            checked
            onChange={() => onChange(selected.filter((x) => x !== id))}
            label={<code>{id} (no such note)</code>}
          />
        ))}
      <FieldNotes id={path} notes={findings} />
    </fieldset>
  );
}

function Audience({ plan, change, notes }: { plan: PlanningSource; change: Change; notes: Notes }) {
  const p = plan.positioning;
  const set = (next: Partial<PlanningSource['positioning']>) =>
    change({ ...plan, positioning: { ...p, ...next } });
  return (
    <Section
      id="audience"
      title="Audience and positioning"
      intro="Candidate audiences are possibilities, not findings. Choose the primary audience yourself; PuzzlePress does not validate a market."
    >
      <TextField
        label="Primary audience"
        path="positioning.primary_audience"
        value={p.primary_audience}
        notes={notes}
        onChange={(v) => set({ primary_audience: v })}
      />
      <TextField
        label="Secondary audience"
        path="positioning.secondary_audience"
        value={p.secondary_audience}
        notes={notes}
        onChange={(v) => set({ secondary_audience: v })}
      />
      <ListField
        legend="Candidate audiences"
        path="positioning.candidate_audiences"
        items={p.candidate_audiences}
        notes={notes}
        addLabel="Add candidate audience"
        hint="Audiences you are considering. Listing one does not choose it."
        onChange={(v) => set({ candidate_audiences: v })}
      />
      <Radios
        legend="Reader familiarity with the subject"
        path="positioning.familiarity"
        value={p.familiarity}
        options={[
          ['undecided', 'Not decided'],
          ['newcomer', 'Newcomer'],
          ['casual', 'Casual'],
          ['enthusiast', 'Enthusiast'],
          ['professional', 'Professional'],
          ['mixed', 'Mixed'],
        ]}
        notes={notes}
        onChange={(v) => set({ familiarity: v })}
      />
      <TextField
        label="Tone"
        path="positioning.tone"
        value={p.tone}
        notes={notes}
        onChange={(v) => set({ tone: v })}
      />
      <TextField
        label="Expected use"
        path="positioning.use_case"
        value={p.use_case}
        multiline
        notes={notes}
        onChange={(v) => set({ use_case: v })}
      />
      <TextField
        label="Main benefit to the reader"
        path="positioning.main_benefit"
        value={p.main_benefit}
        multiline
        notes={notes}
        onChange={(v) => set({ main_benefit: v })}
      />
      <TextField
        label="What makes it different"
        path="positioning.differentiation"
        value={p.differentiation}
        multiline
        notes={notes}
        onChange={(v) => set({ differentiation: v })}
      />
      <NotePicker
        legend="Research this positioning relies on"
        path="positioning.evidence"
        selected={p.evidence}
        notes={plan.research}
        findings={notes}
        onChange={(v) => set({ evidence: v })}
      />
      <fieldset className="choice-group" id="positioning.claims">
        <legend>Claims you intend to make about the book</legend>
        <p className="small muted field-hint">
          Each claim needs a verified source. A plan states intent; it is not marketing copy.
        </p>
        <ol className="plan-rows">
          {p.claims.map((claim, i) => (
            <li key={i}>
              <TextField
                label={`Claim ${i + 1}`}
                path={`positioning.claims.${i}.text`}
                value={claim.text}
                required
                notes={notes}
                onChange={(v) =>
                  set({ claims: p.claims.map((c, j) => (j === i ? { ...c, text: v ?? '' } : c)) })
                }
              />
              <NotePicker
                legend={`Evidence for claim ${i + 1}`}
                path={`positioning.claims.${i}.evidence`}
                selected={claim.evidence}
                notes={plan.research}
                findings={notes}
                onChange={(v) =>
                  set({ claims: p.claims.map((c, j) => (j === i ? { ...c, evidence: v } : c)) })
                }
              />
              <FieldNotes id={`positioning.claims.${i}`} notes={notes} />
              <button
                type="button"
                onClick={() => set({ claims: p.claims.filter((_, j) => j !== i) })}
              >
                Remove claim {i + 1}
              </button>
            </li>
          ))}
        </ol>
        <button
          type="button"
          onClick={() => set({ claims: [...p.claims, { text: '', evidence: [] }] })}
        >
          Add claim
        </button>
      </fieldset>
    </Section>
  );
}

function NoteEditor({
  note,
  i,
  plan,
  change,
  notes,
}: {
  note: PlanNote;
  i: number;
  plan: PlanningSource;
  change: Change;
  notes: Notes;
}) {
  const path = `research.${i}`;
  const set = (next: Partial<PlanNote>) =>
    change({ ...plan, research: plan.research.map((n, j) => (j === i ? { ...n, ...next } : n)) });
  const own = notes.findings.filter((f) => f.path?.startsWith(path));
  return (
    <li>
      <details
        className="plan-record"
        open={!note.observation || own.some((f) => f.severity === 'error')}
      >
        <summary>
          <code>{note.id}</code> {note.observation ? note.observation.slice(0, 80) : 'New note'}
          {note.observation.length > 80 ? '…' : ''}{' '}
          <span className="muted">· {EVIDENCE.find(([e]) => e === note.evidence)?.[1]}</span>
          {own.length > 0 && (
            <span className="muted">
              {' '}
              · {own.length} finding{own.length > 1 ? 's' : ''}
            </span>
          )}
        </summary>
        <TextField
          label="Observation"
          path={`${path}.observation`}
          value={note.observation}
          required
          multiline
          notes={notes}
          onChange={(v) => set({ observation: v ?? '' })}
        />
        <Radios
          legend="What kind of statement is this?"
          path={`${path}.evidence`}
          value={note.evidence}
          options={EVIDENCE}
          notes={notes}
          onChange={(v) => set({ evidence: v as Evidence })}
        />
        <div className="field-pair">
          <Select
            label="Research question"
            path={`${path}.question`}
            value={note.question}
            options={[
              [null, 'None'],
              ...plan.questions.map((q): [string, string] => [q.id, q.question.slice(0, 60)]),
            ]}
            notes={notes}
            onChange={(v) => set({ question: v })}
          />
          <Select
            label="Your confidence"
            path={`${path}.confidence`}
            value={note.confidence}
            options={[
              [null, 'Not stated'],
              ['low', 'Low'],
              ['medium', 'Medium'],
              ['high', 'High'],
            ]}
            notes={notes}
            onChange={(v) => set({ confidence: v as PlanNote['confidence'] })}
          />
        </div>
        <TextField
          label="Source citation"
          path={`${path}.source.citation`}
          value={note.source.citation}
          notes={notes}
          onChange={(v) => set({ source: { ...note.source, citation: v } })}
        />
        <div className="field-pair">
          <TextField
            label="Source URL"
            path={`${path}.source.url`}
            value={note.source.url}
            type="url"
            notes={notes}
            onChange={(v) => set({ source: { ...note.source, url: v } })}
          />
          <Select
            label="Source type"
            path={`${path}.source.type`}
            value={note.source.type}
            options={[
              [null, 'Not stated'],
              ['official', 'Official documentation'],
              ['reference', 'Reference work'],
              ['marketplace', 'Store listing, read by you'],
              ['publisher', 'Publisher'],
              ['book', 'Book'],
              ['article', 'Article'],
              ['personal', 'Personal experience'],
              ['other', 'Other'],
            ]}
            notes={notes}
            onChange={(v) => set({ source: { ...note.source, type: v } })}
          />
        </div>
        <TextField
          label="Date observed"
          path={`${path}.observed`}
          value={note.observed}
          type="date"
          notes={notes}
          hint="When you read or saw it. Not filled in automatically."
          onChange={(v) => set({ observed: v })}
        />
        <TextField
          label="Relevance to the book"
          path={`${path}.relevance`}
          value={note.relevance}
          multiline
          notes={notes}
          onChange={(v) => set({ relevance: v })}
        />
        <TextField
          label="Decision it informs"
          path={`${path}.decision`}
          value={note.decision}
          multiline
          notes={notes}
          onChange={(v) => set({ decision: v })}
        />
        <TextField
          label="Notes"
          path={`${path}.notes`}
          value={note.notes}
          multiline
          notes={notes}
          onChange={(v) => set({ notes: v })}
        />
        <FieldNotes id={path} notes={notes} />
        <button
          type="button"
          onClick={() => change({ ...plan, research: plan.research.filter((_, j) => j !== i) })}
        >
          Remove note {note.id}
        </button>
      </details>
    </li>
  );
}

function Research({
  plan,
  change,
  notes,
  report,
}: {
  plan: PlanningSource;
  change: Change;
  notes: Notes;
  report?: PlanningReport;
}) {
  const questions = plan.questions;
  const setQuestion = (i: number, next: Partial<PlanningSource['questions'][number]>) =>
    change({ ...plan, questions: questions.map((q, j) => (j === i ? { ...q, ...next } : q)) });
  return (
    <Section
      id="research"
      title="Research notes"
      intro="Record what you found and what kind of statement it is. A note marked verified means you checked its source; PuzzlePress never fetches or verifies sources, and nothing here is market research unless you did it."
    >
      {report && (
        <p className="small">
          {report.research.notes} notes: {report.research.evidence.verified_source} verified by you,{' '}
          {report.research.evidence.unverified_source} unverified sources,{' '}
          {report.research.evidence.author_observation} observations,{' '}
          {report.research.evidence.hypothesis} hypotheses, {report.research.evidence.preference}{' '}
          preferences, {report.research.evidence.unknown} unknown. {report.research.open_questions}{' '}
          open questions ({report.research.blocking_questions} blocking).
        </p>
      )}
      <h4>Questions</h4>
      <ol className="plan-rows">
        {questions.map((q, i) => (
          <li key={i}>
            <TextField
              label={`Question ${q.id}`}
              path={`questions.${i}.question`}
              value={q.question}
              required
              notes={notes}
              onChange={(v) => setQuestion(i, { question: v ?? '' })}
            />
            <Check
              label="Must be resolved before approval"
              checked={q.blocking}
              onChange={(v) => setQuestion(i, { blocking: v })}
            />
            <TextField
              label="Resolution"
              path={`questions.${i}.resolution`}
              value={q.resolution}
              multiline
              notes={notes}
              onChange={(v) => setQuestion(i, { resolution: v })}
            />
            <button
              type="button"
              onClick={() => change({ ...plan, questions: questions.filter((_, j) => j !== i) })}
            >
              Remove question {q.id}
            </button>
          </li>
        ))}
      </ol>
      <button
        type="button"
        onClick={() =>
          change({
            ...plan,
            questions: [
              ...questions,
              {
                id: nextId(
                  'q',
                  questions.map((q) => q.id),
                ),
                question: '',
                blocking: false,
                resolution: null,
              },
            ],
          })
        }
      >
        Add question
      </button>
      <h4>Notebook</h4>
      <ol className="plan-rows">
        {plan.research.map((note, i) => (
          <NoteEditor key={i} note={note} i={i} plan={plan} change={change} notes={notes} />
        ))}
      </ol>
      <button
        type="button"
        onClick={() =>
          change({
            ...plan,
            research: [
              ...plan.research,
              {
                id: nextId(
                  'note',
                  plan.research.map((n) => n.id),
                ),
                question: null,
                observation: '',
                evidence: 'unknown',
                confidence: null,
                source: { citation: null, url: null, type: null },
                observed: null,
                relevance: null,
                notes: null,
                decision: null,
              },
            ],
          })
        }
      >
        Add research note
      </button>
    </Section>
  );
}

function Comparables({
  plan,
  change,
  notes,
}: {
  plan: PlanningSource;
  change: Change;
  notes: Notes;
}) {
  const list = plan.comparables;
  const set = (i: number, next: Partial<PlanComparable>) =>
    change({ ...plan, comparables: list.map((c, j) => (j === i ? { ...c, ...next } : c)) });
  return (
    <Section
      id="comparables"
      title="Comparable books"
      intro="Only books you have looked at yourself, with where you saw them. Leave anything you do not know blank: unknown stays unknown, never zero. No ratings, sales or rankings are recorded or estimated, and nothing is looked up for you."
    >
      {list.length === 0 && <p className="muted">No comparable books recorded.</p>}
      <ol className="plan-rows">
        {list.map((c, i) => {
          const path = `comparables.${i}`;
          return (
            <li key={i}>
              <details className="plan-record" open={!c.title}>
                <summary>
                  {c.title || 'New comparable book'}{' '}
                  <span className="muted">
                    · {c.url || c.citation ? 'sourced' : 'no source yet'}
                  </span>
                </summary>
                <TextField
                  label="Title"
                  path={`${path}.title`}
                  value={c.title}
                  required
                  notes={notes}
                  onChange={(v) => set(i, { title: v ?? '' })}
                />
                <TextField
                  label="Author or publisher"
                  path={`${path}.contributor`}
                  value={c.contributor}
                  notes={notes}
                  onChange={(v) => set(i, { contributor: v })}
                />
                <div className="field-pair">
                  <TextField
                    label="Source URL"
                    path={`${path}.url`}
                    value={c.url}
                    type="url"
                    notes={notes}
                    onChange={(v) => set(i, { url: v })}
                  />
                  <TextField
                    label="Or citation"
                    path={`${path}.citation`}
                    value={c.citation}
                    notes={notes}
                    onChange={(v) => set(i, { citation: v })}
                  />
                </div>
                <div className="field-pair">
                  <TextField
                    label="Format"
                    path={`${path}.format`}
                    value={c.format}
                    notes={notes}
                    onChange={(v) => set(i, { format: v })}
                  />
                  <TextField
                    label="Trim size"
                    path={`${path}.trim`}
                    value={c.trim}
                    notes={notes}
                    onChange={(v) => set(i, { trim: v })}
                  />
                </div>
                <div className="field-pair">
                  <NumberField
                    label="Pages"
                    path={`${path}.pages`}
                    value={c.pages}
                    notes={notes}
                    onChange={(v) => set(i, { pages: v })}
                  />
                  <NumberField
                    label="Puzzles"
                    path={`${path}.puzzles`}
                    value={c.puzzles}
                    notes={notes}
                    onChange={(v) => set(i, { puzzles: v })}
                  />
                </div>
                <div className="field-pair">
                  <TextField
                    label="Observed price"
                    path={`${path}.price.amount`}
                    value={c.price?.amount ?? null}
                    notes={notes}
                    hint="As written, e.g. 12.99"
                    onChange={(v) =>
                      set(i, {
                        price:
                          v === null && !c.price?.currency
                            ? null
                            : { amount: v ?? '', currency: c.price?.currency ?? '' },
                      })
                    }
                  />
                  <TextField
                    label="Currency"
                    path={`${path}.price.currency`}
                    value={c.price?.currency ?? null}
                    notes={notes}
                    hint="e.g. USD"
                    onChange={(v) =>
                      set(i, {
                        price:
                          v === null && !c.price?.amount
                            ? null
                            : { amount: c.price?.amount ?? '', currency: v ?? '' },
                      })
                    }
                  />
                </div>
                <TextField
                  label="Date observed"
                  path={`${path}.observed`}
                  value={c.observed}
                  type="date"
                  notes={notes}
                  onChange={(v) => set(i, { observed: v })}
                />
                <TextField
                  label="Intended audience"
                  path={`${path}.audience`}
                  value={c.audience}
                  notes={notes}
                  onChange={(v) => set(i, { audience: v })}
                />
                <ListField
                  legend="Strengths you noticed"
                  path={`${path}.strengths`}
                  items={c.strengths}
                  notes={notes}
                  addLabel="Add strength"
                  onChange={(v) => set(i, { strengths: v })}
                />
                <ListField
                  legend="Weaknesses you noticed"
                  path={`${path}.weaknesses`}
                  items={c.weaknesses}
                  notes={notes}
                  addLabel="Add weakness"
                  onChange={(v) => set(i, { weaknesses: v })}
                />
                <TextField
                  label="Positioning observations"
                  path={`${path}.positioning`}
                  value={c.positioning}
                  multiline
                  notes={notes}
                  onChange={(v) => set(i, { positioning: v })}
                />
                <Radios
                  legend="What kind of record is this?"
                  path={`${path}.evidence`}
                  value={c.evidence}
                  options={EVIDENCE.filter(([e]) => e !== 'hypothesis' && e !== 'preference')}
                  notes={notes}
                  onChange={(v) => set(i, { evidence: v as Evidence })}
                />
                <FieldNotes id={path} notes={notes} />
                <button
                  type="button"
                  onClick={() => change({ ...plan, comparables: list.filter((_, j) => j !== i) })}
                >
                  Remove {c.title || 'this record'}
                </button>
              </details>
            </li>
          );
        })}
      </ol>
      <button
        type="button"
        onClick={() =>
          change({
            ...plan,
            comparables: [
              ...list,
              {
                id: nextId(
                  'book',
                  list.map((c) => c.id),
                ),
                title: '',
                contributor: null,
                url: null,
                citation: null,
                format: null,
                trim: null,
                pages: null,
                puzzles: null,
                price: null,
                audience: null,
                strengths: [],
                weaknesses: [],
                positioning: null,
                observed: null,
                evidence: 'unknown',
              },
            ],
          })
        }
      >
        Add comparable book
      </button>
    </Section>
  );
}

function Themes({
  plan,
  change,
  notes,
  report,
}: {
  plan: PlanningSource;
  change: Change;
  notes: Notes;
  report?: PlanningReport;
}) {
  const themes = plan.themes;
  const set = (i: number, next: Partial<PlanTheme>) =>
    change({ ...plan, themes: themes.map((t, j) => (j === i ? { ...t, ...next } : t)) });
  return (
    <Section
      id="themes"
      title="Themes"
      intro="The theme hierarchy and how many puzzles each theme receives. A parent theme may hold no puzzles of its own. Allocations should add up to the target."
    >
      {report && <AllocationChart report={report} />}
      <ol className="plan-rows">
        {themes.map((t, i) => {
          const path = `themes.${i}`;
          return (
            <li key={t.id + i} className="theme-row">
              <div className="row-head">
                <span className="muted">
                  <code>{t.id}</code>
                </span>
                <RowActions
                  label={`theme ${t.label || t.id}`}
                  index={i}
                  count={themes.length}
                  onMove={(d) => change({ ...plan, themes: move(themes, i, d) })}
                  onRemove={() => change({ ...plan, themes: themes.filter((_, j) => j !== i) })}
                />
              </div>
              <div className="field-pair">
                <TextField
                  label="Label"
                  path={`${path}.label`}
                  value={t.label}
                  required
                  notes={notes}
                  onChange={(v) => set(i, { label: v ?? '' })}
                />
                <NumberField
                  label="Puzzles"
                  path={`${path}.puzzles`}
                  value={t.puzzles}
                  notes={notes}
                  onChange={(v) => set(i, { puzzles: v })}
                />
              </div>
              <div className="field-pair">
                <Select
                  label="Parent theme"
                  path={`${path}.parent`}
                  value={t.parent}
                  options={[
                    [null, 'None (top level)'],
                    ...themes
                      .filter((o) => o.id !== t.id)
                      .map((o): [string, string] => [o.id, o.label || o.id]),
                  ]}
                  notes={notes}
                  onChange={(v) => set(i, { parent: v })}
                />
                <div className="editor-field">
                  <Check
                    label="Required content area"
                    checked={t.required}
                    onChange={(v) => set(i, { required: v })}
                  />
                </div>
              </div>
              <TextField
                label="Notes"
                path={`${path}.notes`}
                value={t.notes}
                notes={notes}
                onChange={(v) => set(i, { notes: v })}
              />
              <FieldNotes id={path} notes={notes} />
            </li>
          );
        })}
      </ol>
      <button
        type="button"
        onClick={() =>
          change({
            ...plan,
            themes: [
              ...themes,
              {
                id: nextId(
                  'theme',
                  themes.map((t) => t.id),
                ),
                label: '',
                parent: null,
                required: false,
                puzzles: null,
                notes: null,
              },
            ],
          })
        }
      >
        Add theme
      </button>
    </Section>
  );
}

function Puzzles({
  plan,
  change,
  notes,
  report,
}: {
  plan: PlanningSource;
  change: Change;
  notes: Notes;
  report?: PlanningReport;
}) {
  const puzzles = plan.puzzles;
  const set = (i: number, next: Partial<PlannedPuzzle>) =>
    change({ ...plan, puzzles: puzzles.map((p, j) => (j === i ? { ...p, ...next } : p)) });
  const target = plan.structure.target_puzzles;
  return (
    <Section
      id="puzzles"
      title="Puzzle allocation"
      intro={`Planned puzzles in book order: each one's theme, level and words, chosen from its theme's vocabulary. ${puzzles.length} specified${target !== null ? ` of a target of ${target}` : ''}. Puzzles you have not specified are not invented.`}
    >
      {report && <ProgressionChart report={report} />}
      <FieldNotes id="puzzles" notes={notes} />
      <ol className="plan-rows">
        {puzzles.map((p, i) => {
          const path = `puzzles.${i}`;
          const pool = plan.vocabulary.find((v) => v.theme === p.theme);
          const level = plan.difficulty.levels.find((l) => l.id === p.level);
          return (
            <li key={p.id + i}>
              <div className="row-head">
                <span className="ordinal">{i + 1}</span>
                <span className="muted">
                  <code>{p.id}</code>
                </span>
                <RowActions
                  label={`puzzle ${i + 1}`}
                  index={i}
                  count={puzzles.length}
                  onMove={(d) => change({ ...plan, puzzles: move(puzzles, i, d) })}
                  onRemove={() => change({ ...plan, puzzles: puzzles.filter((_, j) => j !== i) })}
                />
              </div>
              <TextField
                label="Working title"
                path={`${path}.title`}
                value={p.title}
                notes={notes}
                onChange={(v) => set(i, { title: v })}
              />
              <div className="field-pair">
                <Select
                  label="Theme"
                  path={`${path}.theme`}
                  value={p.theme}
                  options={plan.themes.map((t): [string, string] => [t.id, t.label || t.id])}
                  notes={notes}
                  onChange={(v) => set(i, { theme: v ?? '' })}
                />
                <Select
                  label="Level"
                  path={`${path}.level`}
                  value={p.level}
                  options={[
                    [null, 'Not chosen'],
                    ...plan.difficulty.levels.map((l): [string, string] => [l.id, l.label || l.id]),
                  ]}
                  notes={notes}
                  onChange={(v) => set(i, { level: v })}
                />
              </div>
              <fieldset className="choice-group word-picker" id={`${path}.words`}>
                <legend>
                  Words{' '}
                  <span className="muted">
                    ({p.words.length}
                    {level?.words.min != null
                      ? `; level expects ${level.words.min}-${level.words.max}`
                      : ''}
                    )
                  </span>
                </legend>
                {!pool && (
                  <p className="small muted">
                    This theme has no vocabulary yet. Add it in Vocabulary.
                  </p>
                )}
                <div className="word-options">
                  {pool?.entries.map((e) => (
                    <Check
                      key={e.word}
                      label={e.word}
                      checked={p.words.includes(e.word)}
                      onChange={(on) =>
                        set(i, {
                          words: on ? [...p.words, e.word] : p.words.filter((w) => w !== e.word),
                        })
                      }
                    />
                  ))}
                  {p.words
                    .filter((w) => !pool?.entries.some((e) => e.word === w))
                    .map((w) => (
                      <Check
                        key={w}
                        label={`${w} (not in this theme's vocabulary)`}
                        checked
                        onChange={() => set(i, { words: p.words.filter((x) => x !== w) })}
                      />
                    ))}
                </div>
                <FindingList
                  id={`${path}.words`}
                  findings={notes.findings.filter((f) => f.path?.startsWith(`${path}.words`))}
                />
              </fieldset>
              <TextField
                label="Educational note"
                path={`${path}.notes`}
                value={p.notes}
                multiline
                notes={notes}
                onChange={(v) => set(i, { notes: v })}
              />
              <FieldNotes id={path} notes={notes} />
            </li>
          );
        })}
      </ol>
      <button
        type="button"
        disabled={!plan.themes.length}
        onClick={() =>
          change({
            ...plan,
            puzzles: [
              ...puzzles,
              {
                id: nextId(
                  'puzzle',
                  puzzles.map((p) => p.id),
                ),
                theme: plan.themes[plan.themes.length - 1]?.id ?? '',
                level: null,
                title: null,
                words: [],
                notes: null,
              },
            ],
          })
        }
      >
        Add planned puzzle
      </button>
      {!plan.themes.length && <p className="small muted">Plan a theme first.</p>}
    </Section>
  );
}

function PoolEditor({
  pool,
  index,
  plan,
  change,
  notes,
  report,
  epoch,
}: {
  pool: PlanPool;
  index: number;
  plan: PlanningSource;
  change: Change;
  notes: Notes;
  report?: PlanningReport;
  epoch: number;
}) {
  const path = `vocabulary.${index}`;
  const set = (next: Partial<PlanPool>) =>
    change({
      ...plan,
      vocabulary: plan.vocabulary.map((p, j) => (j === index ? { ...p, ...next } : p)),
    });
  const view = report?.vocabulary.find((v) => v.theme === pool.theme);
  const entryFindings = notes.findings.filter((f) => f.path?.startsWith(`${path}.entries`));
  return (
    <div className="pool-editor">
      <div className="field-pair">
        <Select
          label="Where these words came from"
          path={`${path}.source`}
          value={pool.source}
          options={SOURCES}
          notes={notes}
          hint="Applies to every word without its own source. A source records origin, never permission."
          onChange={(v) => set({ source: (v ?? 'unknown') as WordSource })}
        />
        <TextField
          label="Reference or licence"
          path={`${path}.reference`}
          value={pool.reference}
          notes={notes}
          onChange={(v) => set({ reference: v })}
        />
      </div>
      <LinesField
        label="Candidate words, one a line"
        path={`${path}.entries`}
        lines={pool.entries.map((e) => e.word)}
        resetKey={`${pool.theme}:${epoch}`}
        notes={notes}
        hint="Kept exactly as typed. Words the generator cannot use are reported, never rewritten."
        onChange={(lines) =>
          set({
            entries: lines.map(
              (word) =>
                pool.entries.find((e) => e.word === word) ?? {
                  word,
                  source: null,
                  reference: null,
                  note: null,
                },
            ),
          })
        }
      />
      <FindingList id={`${path}.entries`} findings={entryFindings} />
      {view && (
        <details className="details">
          <summary>
            Word status and per-word sources ({view.usable} usable of {view.entries})
          </summary>
          <table className="plan-table word-table">
            <thead>
              <tr>
                <th scope="col">Word</th>
                <th scope="col">Search form</th>
                <th scope="col">Status</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {pool.entries.map((entry, j) => {
                const w = view.words[j];
                return (
                  <tr key={j}>
                    <td>{entry.word}</td>
                    <td>
                      <code>{w?.search ?? '-'}</code>
                    </td>
                    <td>
                      {!w ? (
                        <Status>Checking</Status>
                      ) : !w.valid ? (
                        <Status tone="fail">Invalid</Status>
                      ) : w.duplicate ? (
                        <Status tone="fail">Duplicate</Status>
                      ) : w.shared ? (
                        <Status tone="neutral">Also in another theme</Status>
                      ) : (
                        <Status tone="pass">Usable</Status>
                      )}
                    </td>
                    <td>
                      <label className="visually-hidden" htmlFor={`${path}.entries.${j}.source`}>
                        Source of {entry.word}
                      </label>
                      <select
                        id={`${path}.entries.${j}.source`}
                        value={entry.source ?? ''}
                        onChange={(e) =>
                          set({
                            entries: pool.entries.map((x, k) =>
                              k === j
                                ? { ...x, source: (e.target.value || null) as WordSource | null }
                                : x,
                            ),
                          })
                        }
                      >
                        <option value="">
                          As the theme ({SOURCES.find(([s]) => s === pool.source)?.[1]})
                        </option>
                        {SOURCES.map(([s, text]) => (
                          <option key={s} value={s}>
                            {text}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      )}
      <FieldNotes id={path} notes={notes} />
    </div>
  );
}

function Vocabulary({
  plan,
  change,
  notes,
  report,
  epoch,
}: {
  plan: PlanningSource;
  change: Change;
  notes: Notes;
  report?: PlanningReport;
  epoch: number;
}) {
  const [selected, setSelected] = useState<string>();
  const pools = plan.vocabulary;
  const current = pools.find((p) => p.theme === selected) ?? pools[0];
  const index = current ? pools.indexOf(current) : -1;
  const without = plan.themes.filter((t) => !pools.some((p) => p.theme === t.id));
  const c = plan.constraints;
  const constraints = (next: Partial<PlanningSource['constraints']>) =>
    change({ ...plan, constraints: { ...c, ...next } });
  return (
    <Section
      id="vocabulary"
      title="Vocabulary"
      intro="Candidate words and phrases for each theme, checked with the generator's own rules. Record where they came from; AI-generated words are never treated as written by people."
    >
      {report && <VocabularyChart report={report} />}
      <div className="pool-tabs" role="group" aria-label="Theme vocabulary">
        {pools.map((p) => (
          <button
            key={p.theme}
            type="button"
            aria-pressed={p === current}
            onClick={() => setSelected(p.theme)}
          >
            {plan.themes.find((t) => t.id === p.theme)?.label ?? p.theme}{' '}
            <span className="muted">({p.entries.length})</span>
          </button>
        ))}
      </div>
      {current ? (
        <PoolEditor
          key={current.theme}
          pool={current}
          index={index}
          plan={plan}
          change={change}
          notes={notes}
          report={report}
          epoch={epoch}
        />
      ) : (
        <p className="muted">No candidate vocabulary yet.</p>
      )}
      {without.length > 0 && (
        <div className="editor-field add-pool">
          <label htmlFor="plan-add-pool">Add vocabulary for a theme</label>
          <select
            id="plan-add-pool"
            value=""
            onChange={(e) => {
              if (!e.target.value) return;
              change({
                ...plan,
                vocabulary: [
                  ...pools,
                  { theme: e.target.value, source: 'unknown', reference: null, entries: [] },
                ],
              });
              setSelected(e.target.value);
            }}
          >
            <option value="">Choose a theme…</option>
            {without.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label || t.id}
              </option>
            ))}
          </select>
        </div>
      )}
      {current && (
        <button
          type="button"
          onClick={() => change({ ...plan, vocabulary: pools.filter((p) => p !== current) })}
        >
          Remove this theme's vocabulary
        </button>
      )}
      <h4>Content constraints</h4>
      <div className="field-pair">
        <NumberField
          label="Shortest word (letters)"
          path="constraints.min_letters"
          value={c.min_letters}
          notes={notes}
          onChange={(v) => constraints({ min_letters: v })}
        />
        <NumberField
          label="Longest word (letters)"
          path="constraints.max_letters"
          value={c.max_letters}
          notes={notes}
          onChange={(v) => constraints({ max_letters: v })}
        />
      </div>
      <NumberField
        label="Puzzles a word may appear in"
        path="constraints.max_word_reuse"
        value={c.max_word_reuse}
        notes={notes}
        hint="Empty uses the word-search default (2)."
        onChange={(v) => constraints({ max_word_reuse: v })}
      />
      <ListField
        legend="Prohibited words"
        path="constraints.prohibited_words"
        items={c.prohibited_words}
        notes={notes}
        addLabel="Add prohibited word"
        hint="Your own list, normalized like the project's quality list. There is no built-in list."
        onChange={(v) => constraints({ prohibited_words: v })}
      />
      <ListField
        legend="Other content constraints"
        path="constraints.notes"
        items={c.notes}
        notes={notes}
        addLabel="Add constraint"
        onChange={(v) => constraints({ notes: v })}
      />
    </Section>
  );
}

function Difficulty({
  plan,
  change,
  notes,
  report,
  options,
}: {
  plan: PlanningSource;
  change: Change;
  notes: Notes;
  report?: PlanningReport;
  options: PlanningOptions;
}) {
  const d = plan.difficulty;
  const levels = d.levels;
  const set = (i: number, next: Partial<PlanLevel>) =>
    change({
      ...plan,
      difficulty: { ...d, levels: levels.map((l, j) => (j === i ? { ...l, ...next } : l)) },
    });
  return (
    <Section
      id="difficulty"
      title="Difficulty"
      intro="Levels use the generator's own settings. List them from easiest to hardest: that order is your judgment, not a measurement."
    >
      <Radios
        legend="Strategy"
        path="difficulty.strategy"
        value={d.strategy}
        options={[
          ['undecided', 'Not decided'],
          ['consistent', 'Consistent', 'Every puzzle uses one level'],
          ['gradual', 'Gradual progression', 'Levels never step back through the book'],
          ['sections', 'Sections by difficulty', 'Each level forms one section'],
          ['mixed', 'Mixed', 'Levels vary freely'],
        ]}
        notes={notes}
        onChange={(v) => change({ ...plan, difficulty: { ...d, strategy: v } })}
      />
      {report && <ProgressionChart report={report} />}
      <ol className="plan-rows">
        {levels.map((l, i) => {
          const path = `difficulty.levels.${i}`;
          return (
            <li key={l.id + i}>
              <div className="row-head">
                <span className="ordinal">{i + 1}</span>
                <span className="muted">
                  <code>{l.id}</code>
                </span>
                <RowActions
                  label={`level ${l.label || l.id}`}
                  index={i}
                  count={levels.length}
                  onMove={(dir) =>
                    change({ ...plan, difficulty: { ...d, levels: move(levels, i, dir) } })
                  }
                  onRemove={() =>
                    change({
                      ...plan,
                      difficulty: { ...d, levels: levels.filter((_, j) => j !== i) },
                    })
                  }
                />
              </div>
              <TextField
                label="Label"
                path={`${path}.label`}
                value={l.label}
                required
                notes={notes}
                onChange={(v) => set(i, { label: v ?? '' })}
              />
              {l.profile !== null ? (
                <TextField
                  label="Existing project profile"
                  path={`${path}.profile`}
                  value={l.profile}
                  notes={notes}
                  onChange={(v) => set(i, { profile: v })}
                  hint="Clear it to state grid settings instead."
                />
              ) : (
                <>
                  <div className="field-pair">
                    <NumberField
                      label="Grid width"
                      path={`${path}.width`}
                      value={l.width}
                      notes={notes}
                      onChange={(v) => set(i, { width: v })}
                    />
                    <NumberField
                      label="Grid height"
                      path={`${path}.height`}
                      value={l.height}
                      notes={notes}
                      onChange={(v) => set(i, { height: v })}
                    />
                  </div>
                  <fieldset className="choice-group direction-picker" id={`${path}.directions`}>
                    <legend>Directions</legend>
                    <div className="word-options">
                      {options.directions.map((name) => (
                        <Check
                          key={name}
                          label={name}
                          checked={l.directions.includes(name)}
                          onChange={(on) =>
                            set(i, {
                              directions: on
                                ? [...l.directions, name]
                                : l.directions.filter((x) => x !== name),
                            })
                          }
                        />
                      ))}
                    </div>
                    <FieldNotes id={`${path}.directions`} notes={notes} />
                  </fieldset>
                </>
              )}
              <div className="field-pair">
                <NumberField
                  label="Fewest words a puzzle"
                  path={`${path}.words.min`}
                  value={l.words.min}
                  notes={notes}
                  onChange={(v) => set(i, { words: { ...l.words, min: v } })}
                />
                <NumberField
                  label="Most words a puzzle"
                  path={`${path}.words.max`}
                  value={l.words.max}
                  notes={notes}
                  onChange={(v) => set(i, { words: { ...l.words, max: v } })}
                />
              </div>
              <FieldNotes id={`${path}.words`} notes={notes} />
              <FieldNotes id={path} notes={notes} />
            </li>
          );
        })}
      </ol>
      <button
        type="button"
        onClick={() =>
          change({
            ...plan,
            difficulty: {
              ...d,
              levels: [
                ...levels,
                {
                  id: nextId(
                    'level',
                    levels.map((l) => l.id),
                  ),
                  label: '',
                  profile: null,
                  width: null,
                  height: null,
                  directions: [],
                  words: { min: null, max: null },
                  notes: null,
                },
              ],
            },
          })
        }
      >
        Add level
      </button>
    </Section>
  );
}

const GATE_HEADINGS: [string, string][] = [
  ['definition', 'Definition'],
  ['research', 'Research'],
  ['content', 'Content'],
  ['structure', 'References and vocabulary'],
  ['feasibility', 'Feasibility'],
  ['decisions', 'Author decisions'],
  ['editorial', 'Editorial review (never blocks)'],
  ['approval', 'Approval'],
];

function FindingGroups({ findings }: { findings: PlanFinding[] }) {
  return (
    <>
      {GATE_HEADINGS.map(([gate, heading]) => {
        const own = findings.filter((f) => f.gate === gate);
        if (!own.length) return null;
        return (
          <div key={gate} className="finding-group">
            <h4>
              {heading} <span className="muted">({own.length})</span>
            </h4>
            <ul className="plan-findings">
              {own.map((f, i) => (
                <li key={i}>
                  <Status tone={SEVERITY[f.severity][0]}>{SEVERITY[f.severity][1]}</Status>
                  <div>
                    <p>
                      {f.message}
                      {f.actual !== null && f.expected !== null && (
                        <span className="muted">
                          {' '}
                          (actual {f.actual}; expected {f.expected})
                        </span>
                      )}
                    </p>
                    <p className="small muted">
                      {f.basis.replaceAll('_', ' ')} · <code>{f.code}</code>
                      {f.path && (
                        <>
                          {' · '}
                          <a href={`#planning-${sectionOf(f.path)}`}>{f.path}</a>
                        </>
                      )}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </>
  );
}

function Coverage({ report }: { report?: PlanningReport }) {
  if (!report)
    return (
      <Section id="coverage" title="Coverage">
        {<p className="muted">No report yet.</p>}
      </Section>
    );
  const pages = report.page_estimate;
  return (
    <Section
      id="coverage"
      title="Coverage and quality review"
      intro="Every finding, grouped by what it blocks. Editorial findings are prompts for your judgment, based on stated heuristics; they never block and never measure quality or market fit."
    >
      <AllocationChart report={report} />
      <VocabularyChart report={report} />
      <p className="small">
        Page estimate:{' '}
        {pages.minimum === null
          ? 'unknown until a target is set'
          : pages.maximum === null
            ? `at least ${pages.minimum} logical pages (some parts are not planned yet)`
            : `${pages.minimum}-${pages.maximum} logical pages`}
        . The exact count comes from the publication plan in production.
      </p>
      {report.findings.length ? <FindingGroups findings={report.findings} /> : <p>No findings.</p>}
    </Section>
  );
}

// ------------------------------------------------------------------ readiness

function Readiness({ d, report }: { d: PlanningDraft; report?: PlanningReport }) {
  const saved = d.status?.report;
  const tone = report ? STATE[report.state] : undefined;
  const canApprove = !d.dirty && saved?.state === 'ready_for_approval';
  return (
    <aside
      className="plan-readiness"
      id="planning-readiness"
      tabIndex={-1}
      aria-labelledby="plan-readiness-title"
    >
      <h3 id="plan-readiness-title">Readiness</h3>
      {!report ? (
        <p className="muted">Start or load a plan to see its readiness.</p>
      ) : (
        <>
          <p className="small muted">
            {d.dirty
              ? d.reportOutdated
                ? d.issues.length
                  ? 'Showing the last version Python could check. Fix the highlighted fields to update.'
                  : 'Checking the draft…'
                : 'Draft, checked by Python. Not saved.'
              : 'Saved plan.'}{' '}
            Ruleset {report.ruleset.id} v{report.ruleset.version}.
          </p>
          <p className="plan-state">
            {tone && (
              <span className={`status ${tone[0]}`} aria-hidden="true">
                <span className="status-mark" />
              </span>
            )}
            <span>{report.statement}</span>
          </p>
          <ol className="gate-list">
            {report.gates.map((g) => (
              <li key={g.gate}>
                <Status tone={g.passed ? 'pass' : 'fail'}>{g.passed ? 'Passed' : 'Blocked'}</Status>
                <span>
                  {g.label}
                  {!g.passed && (
                    <small className="muted">
                      {' '}
                      {g.blocking.map((c) => c.replaceAll('_', ' ')).join(', ')}
                    </small>
                  )}
                </span>
              </li>
            ))}
          </ol>
          <section className="plan-approval" aria-labelledby="plan-approval-title">
            <h4 id="plan-approval-title">Approval</h4>
            <p className="small">
              {saved?.approval.status === 'current'
                ? saved.approval.counts
                  ? 'You approved this exact plan.'
                  : 'An approval is recorded for this plan, but blocking findings remain, so it does not count.'
                : saved?.approval.status === 'stale'
                  ? 'Stale: the plan changed after you approved it. Review it and approve again.'
                  : 'Not approved.'}
            </p>
            {d.dirty &&
              saved?.approval.status === 'current' &&
              report.approval.status === 'stale' && (
                <p className="draft-status small">
                  These unsaved edits change the approved plan. Saving them makes the approval
                  stale.
                </p>
              )}
            {canApprove && (
              <p className="small">
                Approving records the identity of the saved plan you reviewed. Any later edit makes
                the approval stale.
              </p>
            )}
            {saved?.state !== 'approved' && (
              <button
                type="button"
                className="primary"
                disabled={!canApprove || d.busy}
                onClick={() => saved && void d.approve(saved.planning_identity)}
              >
                Approve this plan
              </button>
            )}
            {d.status?.source?.approval && (
              <button
                type="button"
                disabled={d.dirty || d.busy}
                onClick={() => void d.approve(null)}
              >
                Withdraw approval
              </button>
            )}
            {d.dirty && (
              <p className="draft-status small">
                Save the draft first: approval covers the saved plan.
              </p>
            )}
            {!d.dirty && saved && !canApprove && saved.state !== 'approved' && (
              <p className="small muted">Approval is available once nothing blocks the plan.</p>
            )}
            {saved?.state === 'approved' && (
              <p className="small">
                Production handoff: run <code>puzzlepress plan handoff</code>. Nothing is generated
                from the plan automatically.
              </p>
            )}
            <details className="details">
              <summary>Planning identity</summary>
              <code className="identity">{report.planning_identity}</code>
            </details>
            <p className="small muted">{report.boundary}</p>
          </section>
          <section className="plan-feasibility" aria-labelledby="plan-feasibility-title">
            <h4 id="plan-feasibility-title">Production feasibility</h4>
            <ul className="state-lines feasibility-lines">
              {report.feasibility.map((item) => (
                <li key={item.code}>
                  <Status tone={STATUS_TONE[item.status]}>{item.status}</Status>
                  <span>
                    <strong>{item.label}.</strong> {item.detail}
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <p className="small muted">
            {report.summary.findings.error} blocking, {report.summary.findings.warning} to review,{' '}
            {report.summary.findings.info} notes. <a href="#planning-coverage">See all findings</a>.
          </p>
        </>
      )}
    </aside>
  );
}

// ------------------------------------------------------------------ workspace

export function Planning({
  projectKey,
  onDirty,
}: {
  projectKey: string;
  onDirty: (dirty: boolean) => void;
}) {
  const d = usePlanning(projectKey, onDirty);
  const section = useSection();
  if (d.loadError) return <ErrorState error={d.loadError} retry={d.reload} />;
  if (!d.status) return <Loading>Reading the plan…</Loading>;
  const plan = d.draft;
  const report = d.report;
  const notes: Notes = {
    issues: d.issues,
    findings: report?.findings ?? [],
  };
  const counts = (key: string) => {
    const own = (report?.findings ?? []).filter((f) => sectionOf(f.path) === key);
    const errors = own.filter((f) => f.severity === 'error').length;
    const reviews = own.filter((f) => f.severity === 'warning').length;
    const issues = d.issues.filter((i) => sectionOf(i.path) === key).length;
    return [
      errors + issues ? `${errors + issues} to fix` : '',
      reviews ? `${reviews} to review` : '',
    ]
      .filter(Boolean)
      .join(', ');
  };
  return (
    <div className="editor planning">
      <div className="editor-toolbar">
        <div>
          <h2>Planning</h2>
          <p className={d.dirty ? 'draft-status' : 'muted'}>
            {d.dirty ? 'Unsaved changes' : plan ? 'Saved plan' : 'No plan yet'}
          </p>
        </div>
        {plan && (
          <div className="editor-actions">
            <a href="#planning-readiness">Jump to readiness</a>
            <button
              type="button"
              className="primary"
              disabled={d.busy || !d.dirty}
              onClick={() => void d.save()}
            >
              Save plan
            </button>
            <button type="button" disabled={d.busy || !d.dirty} onClick={d.revert}>
              Revert draft
            </button>
          </div>
        )}
      </div>
      <p className="small muted">
        Saved to <code>planning.yaml</code> beside <code>book.yaml</code>, which planning never
        changes. Saving writes normalized YAML; comments are not preserved.
      </p>
      <p role="status" aria-live="polite" className="small">
        {d.message}
      </p>
      {d.error && (
        <div role="alert" className="notice error">
          <h3>
            {d.error instanceof ApiError && d.error.code === 'source_changed'
              ? 'The saved plan has changed'
              : 'Could not complete the request'}
          </h3>
          <p>{d.error.message}</p>
          <Issues issues={d.issues} />
          <button type="button" disabled={d.busy} onClick={d.reload}>
            Reload saved plan
          </button>
        </div>
      )}
      {!plan ? (
        <section className="publishing-start" aria-labelledby="plan-start">
          <h3 id="plan-start">Plan this book before producing it</h3>
          <p>
            Record research, choose the audience, plan themes, vocabulary, puzzles and difficulty,
            and see whether the current PuzzlePress can produce it. Every decision starts undecided,
            nothing is approved for you, and nothing is saved until you save.
          </p>
          <button type="button" className="primary" onClick={d.start}>
            Start a plan
          </button>
        </section>
      ) : (
        <div className="planning-workspace">
          <nav className="planning-nav" aria-label="Plan sections">
            <ol>
              {SECTIONS.map(([key, label]) => (
                <li key={key}>
                  <a
                    href={`#planning-${key}`}
                    aria-current={section === key ? 'location' : undefined}
                  >
                    {label}
                    {report && counts(key) && <small>{counts(key)}</small>}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
          <div className="planning-main">
            {section === 'overview' && (
              <>
                {report && (
                  <dl className="facts plan-facts">
                    <div>
                      <dt>Book</dt>
                      <dd>
                        {d.status.book.title} <code>{d.status.book.id}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Puzzles</dt>
                      <dd>
                        target {report.summary.target_puzzles ?? 'not set'}, allocated{' '}
                        {report.summary.allocated_puzzles}, specified{' '}
                        {report.summary.specified_puzzles}
                      </dd>
                    </div>
                    <div>
                      <dt>Plan</dt>
                      <dd>
                        {report.summary.themes} themes, {report.summary.levels} levels,{' '}
                        {report.summary.candidate_words} candidate words
                      </dd>
                    </div>
                  </dl>
                )}
                <Overview plan={plan} change={d.change} notes={notes} options={d.status.options} />
              </>
            )}
            {section === 'audience' && <Audience plan={plan} change={d.change} notes={notes} />}
            {section === 'research' && (
              <Research plan={plan} change={d.change} notes={notes} report={report} />
            )}
            {section === 'comparables' && (
              <Comparables plan={plan} change={d.change} notes={notes} />
            )}
            {section === 'themes' && (
              <Themes plan={plan} change={d.change} notes={notes} report={report} />
            )}
            {section === 'puzzles' && (
              <Puzzles plan={plan} change={d.change} notes={notes} report={report} />
            )}
            {section === 'vocabulary' && (
              <Vocabulary
                plan={plan}
                change={d.change}
                notes={notes}
                report={report}
                epoch={d.epoch}
              />
            )}
            {section === 'difficulty' && (
              <Difficulty
                plan={plan}
                change={d.change}
                notes={notes}
                report={report}
                options={d.status.options}
              />
            )}
            {section === 'coverage' && <Coverage report={report} />}
            <FieldNotes
              id="planning"
              notes={{
                issues: d.issues.filter(
                  (i) => i.path === 'planning' || i.path === 'planning_version',
                ),
                findings: [],
              }}
            />
          </div>
          <Readiness d={d} report={report} />
        </div>
      )}
    </div>
  );
}
