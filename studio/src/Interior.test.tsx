import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { App } from './App';
import composed from './fixtures/composition-project.json';
import type { AnswerChoice, DesignCatalogue, ResolvedLook } from './types';

// Interior design: every preview, fit and catalogue entry below stands in for a
// Python response; the page only presents them and edits the draft source.

type Call = { url: string; method: string; body: Record<string, unknown> };
type Source = typeof composed.source & {
  interior?: Record<string, unknown>;
  composition: { solutions: { per_page?: number } };
};

const look = (accent: string, secondary: string, gray: number): ResolvedLook => ({
  theme: 'classic',
  layout: 'classic',
  accent,
  secondary,
  accent_gray: gray,
  secondary_gray: 0,
  banner: 'none',
  motif: 'none',
  background: 'none',
});
const catalogue: DesignCatalogue = {
  themes: [
    {
      id: 'classic',
      name: 'Classic',
      description: 'The original PuzzlePress interior.',
      look: look('#000000', '#000000', 0),
      design: {},
    },
    {
      id: 'racing_orange',
      name: 'Racing Orange',
      description: 'Black banners, orange accents.',
      look: { ...look('#e8590c', '#141414', 0.482), banner: 'solid', motif: 'stripes' },
      design: {},
    },
  ],
  layouts: [
    { id: 'classic', name: 'Classic', description: 'The original page.', look: {}, design: {} },
    {
      id: 'bold_header',
      name: 'Bold Header',
      description: 'Titles in a banner.',
      look: {},
      design: {},
    },
  ],
};
const choice = (per_page: number, letter: number): AnswerChoice => ({
  per_page,
  columns: per_page === 1 ? 1 : per_page === 2 ? 1 : 2,
  rows: per_page === 1 ? 1 : per_page / (per_page === 2 ? 2 : 2),
  letter_size: letter,
  minimum: 7,
  grid: [17, 17],
  fits: letter >= 7,
  comfortable: letter >= 7.5,
});
const choices = [choice(1, 14), choice(2, 14), choice(4, 7.9), choice(6, 6.2), choice(8, 5.1)];
const page = (index: number, kind: string, roles: string[]) => ({
  index,
  physical_page: index + 3,
  kind,
  folio: String(index),
  roles,
});

function draftResponse(source: Source) {
  const perPage = source.composition.solutions.per_page ?? 4;
  const answers = { per_page: perPage, pages: 2, last_page_solutions: 1, first_page: 9, choices };
  if (perPage === 6)
    return {
      success: false,
      stage: 'layout',
      diagnostics: [
        {
          code: 'solution_layout_unreadable',
          message:
            '6 solutions a page print 17 x 17 grids with 6.2 pt letters, below the 7 pt minimum. Choose 4 solutions a page or fewer.',
        },
      ],
      answers,
    };
  const theme = (source.interior?.theme as string | undefined) ?? 'classic';
  return {
    success: true,
    pdf_sha256: 'a'.repeat(64),
    page_count: source.interior ? 20 : 19,
    pages: [
      page(1, 'title_page', ['title']),
      page(2, 'puzzle', ['spread_left']),
      page(3, 'puzzle', ['puzzle', 'spread_right']),
      page(4, 'solutions', ['answers']),
      page(5, 'solutions', ['answers_last']),
    ],
    design: { look: { ...catalogue.themes[theme === 'classic' ? 0 : 1].look, theme } },
    warnings: [],
    answers,
  };
}

function setup(fail?: string) {
  let saved = structuredClone(composed) as typeof composed;
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    const path = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : {};
    calls.push({ url: path, method: options?.method ?? 'GET', body });
    const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
    if (path === '/api/interior/designs') return json(catalogue);
    if (path.endsWith('/draft/interior')) return json(draftResponse(body.source as Source));
    if (path.endsWith('/interior')) return json({ state: 'current', report: { page_count: 19 } });
    if (path.endsWith('/cover/assets')) return json({ assets: [] });
    if (path.endsWith('/save')) {
      if (fail)
        return json({ error: { code: fail, message: 'Source changed. Reload to review.' } }, 409);
      saved = { ...saved, source: body.source as typeof composed.source, revision: 'sha256-new' };
    }
    return json(saved);
  });
  history.replaceState(null, '', `/books/${composed.key}/interior`);
  render(<App />);
  return calls;
}

const drafts = (calls: Call[]) => calls.filter((c) => c.url.endsWith('/draft/interior'));
const lastDraft = (calls: Call[]) => drafts(calls).at(-1)!.body.source as Source;

test('answer layout offers Python-measured choices and keeps an unreadable choice', async () => {
  const calls = setup();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('tab', { name: 'Answer layout' }));
  const four = await screen.findByRole('radio', { name: /4 a page \(default\)/ });
  expect(four).not.toBeChecked(); // The demo states 2 a page explicitly.
  expect(screen.getByRole('radio', { name: /2 a page/ })).toBeChecked();
  await waitFor(() =>
    expect(screen.getAllByText(/letters 7\.9 pt for 17 × 17 grids/)).toHaveLength(1),
  );
  expect(screen.getAllByText('Too small')).toHaveLength(2);
  await user.click(four);
  await waitFor(() => expect(lastDraft(calls).composition.solutions.per_page).toBe(4));
  expect(await screen.findByText(/2 answer pages; the last holds 1\./)).toBeVisible();
  expect(await screen.findByRole('img', { name: /Draft answers, page 7/ })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Show the last answer page' }));
  expect(await screen.findByRole('img', { name: /Draft answers, page 8/ })).toBeVisible();

  await user.click(screen.getByRole('radio', { name: /6 a page/ }));
  await waitFor(() => expect(lastDraft(calls).composition.solutions.per_page).toBe(6));
  const failure = await screen.findByRole('heading', { name: 'This draft does not lay out' });
  expect(failure.parentElement).toHaveTextContent('Choose 4 solutions a page or fewer.');
  expect(screen.getByRole('radio', { name: /6 a page/ })).toBeChecked(); // Never changed for you.
  expect(screen.getAllByRole('alert').some((a) => /Choose 4 or fewer/.test(a.textContent!))).toBe(
    true,
  );
});

test('a theme is added to the draft, previewed as a spread and saved to book.yaml', async () => {
  const calls = setup();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('tab', { name: 'Theme' }));
  await user.click(screen.getByRole('button', { name: 'Add an interior design' }));
  await user.click(await screen.findByRole('radio', { name: /Racing Orange/ }));
  await waitFor(() =>
    expect(lastDraft(calls).interior).toEqual({
      version: 2,
      theme: 'racing_orange',
      layout: 'classic',
    }),
  );
  expect(await screen.findByText(/prints as 52% black/)).toBeVisible();
  const spread = await screen.findAllByRole('img', { name: /Draft puzzle, page/ });
  expect(spread).toHaveLength(2);
  const note = screen.getByRole('note', { name: 'What saving changes' });
  expect(within(note).getByText(/rebuild it in/)).toBeVisible();
  expect(within(note).getByText('Changes the page count')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  const save = await waitFor(() => {
    const found = calls.find((c) => c.url.endsWith('/save'));
    expect(found).toBeDefined();
    return found!;
  });
  expect((save.body.source as Source).interior).toEqual({
    version: 2,
    theme: 'racing_orange',
    layout: 'classic',
  });
  expect((save.body.source as Source).book).toEqual(composed.source.book);
});

test('page layout edits only the draft and a failed save keeps it', async () => {
  const calls = setup('source_changed');
  const user = userEvent.setup();
  await screen.findByRole('tab', { name: 'Page layout' });
  await user.click(screen.getByRole('button', { name: /A two-page spread/ }));
  await waitFor(() =>
    expect((lastDraft(calls).composition as { puzzles: { layout?: string } }).puzzles.layout).toBe(
      'spread',
    ),
  );
  await user.click(screen.getByRole('button', { name: 'Add an interior design' }));
  await user.click(await screen.findByRole('radio', { name: /Bold Header/ }));
  await waitFor(() => expect(lastDraft(calls).interior?.layout).toBe('bold_header'));
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByRole('heading', { name: 'Saved source has changed' })).toBeVisible();
  expect(screen.getByRole('radio', { name: /Bold Header/ })).toBeChecked();
});
