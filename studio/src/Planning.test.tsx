import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { App } from './App';
import { starterPlan } from './planning-draft';
import project from './fixtures/planning-project.json';
import demo from './fixtures/planning-demo.json';
import empty from './fixtures/planning-empty.json';
import ready from './fixtures/planning-ready.json';
import approved from './fixtures/planning-approved.json';
import draftStale from './fixtures/planning-draft-stale.json';

// Fixtures are real responses of the Python planning API on disposable copies of
// books/automotive (the demo plan, a synthetic ready plan, its approval).

type Call = { url: string; method: string; body: Record<string, unknown> };

afterEach(() => {
  vi.restoreAllMocks();
  history.replaceState(null, '', '/');
});

function setup({
  status = demo as object,
  draft = () => new Response(JSON.stringify({ report: (status as typeof ready).report })),
  hash = '',
}: {
  status?: object;
  draft?: () => Response;
  hash?: string;
} = {}) {
  let current = status;
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    const path = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : {};
    calls.push({ url: path, method: options?.method ?? 'GET', body });
    if (path.endsWith('/draft/planning')) return draft();
    if (path.endsWith('/planning/save')) {
      current = { ...(ready as object), source: body.source };
      return new Response(JSON.stringify(current));
    }
    if (path.endsWith('/planning/approval')) {
      current = approved;
      return new Response(JSON.stringify(current));
    }
    if (path.endsWith('/planning')) return new Response(JSON.stringify(current));
    return new Response(JSON.stringify(project));
  });
  history.replaceState(null, '', `/books/automotive/planning${hash}`);
  render(<App />);
  return calls;
}

const readiness = () => screen.getByRole('complementary', { name: 'Readiness' });
const sections = () => screen.getByRole('navigation', { name: 'Plan sections' });

test('the demo plan shows Python readiness as separate text verdicts', async () => {
  setup();
  const panel = await screen.findByRole('complementary', { name: 'Readiness' });
  expect(
    within(panel).getByText(/^Needs research: blocking questions or unattributed evidence/),
  ).toBeVisible();
  const gates = within(panel).getAllByRole('listitem').slice(0, 6);
  expect(gates.map((g) => (g.textContent?.startsWith('Passed') ? 'P' : 'B')).join('')).toBe(
    'PBBPBB',
  );
  expect(within(panel).getByRole('button', { name: 'Approve this plan' })).toBeDisabled();
  expect(within(panel).getByText(/A project holds at most 20 puzzle definitions/)).toBeVisible();
  expect(within(panel).getByText(/not publishing approval/)).toBeVisible();
  // The 60-puzzle target is kept and reported beside its field, never lowered.
  expect(screen.getByLabelText('Target puzzle count')).toHaveValue('60');
  expect(screen.getByLabelText('Target puzzle count')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByText(/60 planned puzzles exceed the current cap of 20/)).toBeVisible();
  expect(within(sections()).getByRole('link', { name: /Overview/ })).toHaveAttribute(
    'aria-current',
    'location',
  );
  expect(within(sections()).getByRole('link', { name: /Vocabulary 10 to review/ })).toBeVisible();
});

test('project navigation links to Planning and to this project’s Publishing', async () => {
  setup();
  await screen.findByRole('complementary', { name: 'Readiness' });
  const projectNav = screen.getByRole('navigation', { name: 'Project' });
  expect(within(projectNav).getByRole('link', { name: 'Plan' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  // Regression: this link pointed to /publishing, a page that does not exist.
  expect(within(projectNav).getByRole('link', { name: 'Publishing' })).toHaveAttribute(
    'href',
    '/books/automotive/publishing',
  );
});

test('sections are deep links and charts print Python’s numbers', async () => {
  setup({ hash: '#planning-themes' });
  const heading = await screen.findByRole('heading', { name: 'Themes', level: 3 });
  await waitFor(() => expect(heading).toHaveFocus());
  const chart = screen.getByRole('table', { name: /Puzzles by theme: 60 allocated of a target/ });
  const row = within(chart).getByRole('row', { name: /Engines & Powertrains/ });
  expect(within(row).getAllByRole('cell')[0]).toHaveTextContent('10');
  history.replaceState(null, '', '/books/automotive/planning#planning-difficulty');
  fireEvent(window, new HashChangeEvent('hashchange'));
  expect(await screen.findByRole('heading', { name: 'Difficulty', level: 3 })).toBeVisible();
  const strip = screen.getByRole('list', { name: 'Planned puzzles in book order' });
  expect(within(strip).getByText('53 not yet specified')).toBeVisible();
  expect(within(strip).getByText(/Puzzle 1, Under the Hood: Warm-up/)).toBeInTheDocument();
});

test('starting a plan decides nothing and creates it only on save', async () => {
  const user = userEvent.setup();
  const calls = setup({ status: empty });
  await user.click(await screen.findByRole('button', { name: 'Start a plan' }));
  const starter = starterPlan();
  expect(starter.structure.print_profile).toBeNull();
  expect(starter.positioning.familiarity).toBe('undecided');
  expect(starter.difficulty.strategy).toBe('undecided');
  expect(starter.approval).toBeNull();
  expect(calls.some((c) => c.url.endsWith('/planning/save'))).toBe(false);
  expect(screen.getByText('Unsaved changes', { exact: true })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Save plan' }));
  const save = calls.find((c) => c.url.endsWith('/planning/save'));
  expect(save?.body.revision).toBeNull();
  expect(save?.body.source).toEqual(starter);
});

test('edits are sent exactly as typed and checked by Python', async () => {
  const user = userEvent.setup();
  const calls = setup({ status: ready });
  const subject = await screen.findByLabelText('Subject or niche');
  await user.clear(subject);
  await user.type(subject, '  Engines, spaced  ');
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/draft/planning'))).toBe(true));
  const check = calls.filter((c) => c.url.endsWith('/draft/planning')).at(-1)!;
  expect((check.body.source as typeof ready.source).concept.subject).toBe('  Engines, spaced  ');
  expect(screen.getByText('Unsaved changes', { exact: true })).toBeVisible();
  expect(within(readiness()).getByRole('button', { name: 'Approve this plan' })).toBeDisabled();
  expect(within(readiness()).getByText(/Save the draft first/)).toBeVisible();
  await user.clear(subject);
  // Emptying an optional field records it as unknown (null), not as text.
  await waitFor(() => {
    const last = calls.filter((c) => c.url.endsWith('/draft/planning')).at(-1)!;
    expect((last.body.source as typeof ready.source).concept.subject).toBeNull();
  });
});

test('schema problems stay beside their field and the draft is kept', async () => {
  const user = userEvent.setup();
  const issue = {
    path: 'structure.target_puzzles',
    code: 'number',
    message: 'Expected a whole number from 1 to 10000, or null.',
  };
  setup({
    status: ready,
    draft: () =>
      new Response(
        JSON.stringify({
          error: { code: 'invalid_planning', message: 'Invalid', issues: [issue] },
        }),
        { status: 422 },
      ),
  });
  const target = await screen.findByLabelText('Target puzzle count');
  await user.clear(target);
  await user.type(target, 'sixty');
  expect(await screen.findByText(/Expected a whole number from 1 to 10000/)).toBeVisible();
  expect(target).toHaveAttribute('aria-invalid', 'true');
  expect(target).toHaveValue('sixty');
  expect(
    await within(readiness()).findByText(/Showing the last version Python could check/),
  ).toBeVisible();
});

test('approval sends the reviewed identity of the saved revision', async () => {
  const user = userEvent.setup();
  const calls = setup({ status: ready });
  const panel = await screen.findByRole('complementary', { name: 'Readiness' });
  expect(within(panel).getByText('Ready for author approval.')).toBeVisible();
  await user.click(within(panel).getByRole('button', { name: 'Approve this plan' }));
  const call = calls.find((c) => c.url.endsWith('/planning/approval'))!;
  expect(call.body).toEqual({
    revision: ready.revision,
    identity: ready.report.planning_identity,
  });
  expect(await within(panel).findByText('You approved this exact plan.')).toBeVisible();
  expect(within(panel).queryByRole('button', { name: 'Approve this plan' })).toBeNull();
  expect(within(panel).getByText(/puzzlepress plan handoff/)).toBeVisible();
});

test('unsaved edits to an approved plan say the approval would go stale', async () => {
  const user = userEvent.setup();
  setup({ status: approved, draft: () => new Response(JSON.stringify(draftStale)) });
  const subject = await screen.findByLabelText('Subject or niche');
  await user.type(subject, ' tools');
  expect(
    await within(readiness()).findByText(/Saving them makes the approval stale/),
  ).toBeVisible();
  expect(within(readiness()).getByRole('button', { name: 'Withdraw approval' })).toBeDisabled();
});
