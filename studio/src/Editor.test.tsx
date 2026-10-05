import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { test, expect, vi } from 'vitest';
import { App } from './App';
import projectData from './fixtures/project.json';
import generated from './fixtures/generation.json';

function setup(fail?: string) {
  let saved = structuredClone(projectData);
  const calls: { url: string; body: Record<string, unknown> }[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    const path = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : {};
    calls.push({ url: path, body });
    if (path.endsWith('/save')) {
      if (fail)
        return new Response(
          JSON.stringify({
            error: {
              code: fail,
              message:
                fail === 'source_changed' ? 'Source changed. Reload to review.' : 'Save failed.',
              issues: [],
            },
          }),
          { status: 409 },
        );
      saved = { ...saved, source: body.source, revision: 'sha256-new' };
      saved.source.word_search.puzzles[0].title = saved.source.word_search.puzzles[0].title.trim();
    }
    if (path.endsWith('/validate') && !body.source.word_search.puzzles[0].title)
      return new Response(
        JSON.stringify({
          error: {
            code: 'invalid_project',
            message: 'Project validation failed.',
            issues: [
              {
                path: 'word_search.puzzles.0.title',
                code: 'text',
                message: 'Expected nonempty text.',
              },
            ],
          },
        }),
        { status: 422 },
      );
    return new Response(JSON.stringify(path.endsWith('/preview') ? generated : saved));
  });
  history.replaceState(null, '', '/books/garden-demo/edit');
  render(<App />);
  return calls;
}

test('loads, edits, validates, previews and saves authoritative returned state', async () => {
  const calls = setup();
  const user = userEvent.setup();
  const title = await screen.findByLabelText('Puzzle title');
  fireEvent.change(title, { target: { value: '  Edited flowers  ' } });
  expect(screen.getByText('Unsaved changes')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Validate draft' }));
  expect(
    await screen.findByText('Draft is valid. Python accepted the proposed project.'),
  ).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Preview draft' }));
  expect(await screen.findByText('Unsaved draft preview')).toBeVisible();
  expect(screen.getByRole('table')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Whole-book quality' }));
  expect(screen.getByText('No target words are shared between definitions.')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('Saved and reloaded from source.')).toBeVisible();
  expect(title).toHaveValue('Edited flowers');
  expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  expect(calls.find((c) => c.url.endsWith('/save'))?.body.revision).toBe(projectData.revision);
});

test('word editing, target ordering, puzzle management and shared profile selection', async () => {
  const calls = setup();
  const user = userEvent.setup();
  await screen.findByLabelText('Puzzle title');
  fireEvent.change(screen.getByLabelText('Word 1'), { target: { value: 'ASTER' } });
  await user.click(screen.getByRole('button', { name: 'Move target 2 up' }));
  await user.selectOptions(screen.getByLabelText('Difficulty profile'), 'varied');
  await user.click(screen.getByRole('button', { name: 'Add word' }));
  const count = projectData.source.word_search.banks[0].entries.length + 1;
  fireEvent.change(screen.getByLabelText(`Word ${count}`), { target: { value: 'BUD' } });
  await user.selectOptions(screen.getByLabelText(/Add a target from/), 'word-1');
  await user.click(screen.getByRole('button', { name: 'Add puzzle' }));
  expect(screen.getByLabelText('Puzzle ID')).toHaveValue('puzzle-1');
  await user.click(screen.getByRole('button', { name: 'Move puzzle 3 up' }));
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  await user.click(screen.getByRole('button', { name: 'Remove puzzle' }));
  await user.click(screen.getByRole('button', { name: 'Validate draft' }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/validate'))).toBe(true));
  const source = calls.find((c) => c.url.endsWith('/validate'))!.body
    .source as typeof projectData.source;
  expect(source.word_search.puzzles).toHaveLength(2);
  expect(source.word_search.banks[0].entries[0].display).toBe('ASTER');
  expect(source.word_search.puzzles[0].difficulty).toBe('varied');
  expect(source.word_search.puzzles[0].target_ids.at(-1)).toBe('word-1');
});

test.each(['save_failed', 'source_changed'])(
  'retains draft after %s and supports deliberate revert',
  async (code) => {
    setup(code);
    const user = userEvent.setup();
    fireEvent.change(await screen.findByLabelText('Puzzle title'), {
      target: { value: 'Keep my work' },
    });
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByRole('alert')).toBeVisible();
    expect(screen.getByLabelText('Puzzle title')).toHaveValue('Keep my work');
    expect(screen.getByText('Unsaved changes')).toBeVisible();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    await user.click(screen.getByRole('button', { name: 'Revert draft' }));
    expect(screen.getByLabelText('Puzzle title')).toHaveValue('Keep my work');
    confirm.mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: 'Revert draft' }));
    expect(screen.getByLabelText('Puzzle title')).toHaveValue('In the Flower Bed');
  },
);

test('structured validation is associated with the input and edits invalidate old results', async () => {
  setup();
  const user = userEvent.setup();
  const title = await screen.findByLabelText('Puzzle title');
  fireEvent.change(title, { target: { value: '' } });
  await user.click(screen.getByRole('button', { name: 'Validate draft' }));
  await screen.findByRole('alert');
  expect(title).toHaveAttribute('aria-invalid', 'true');
  expect(title).toHaveAccessibleDescription(/Expected nonempty text/);
  fireEvent.change(title, { target: { value: 'Repaired' } });
  expect(title).not.toHaveAttribute('aria-invalid');
  await user.click(screen.getByRole('button', { name: 'Preview draft' }));
  await screen.findByRole('table');
  fireEvent.change(title, { target: { value: 'Newer draft' } });
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

test('draft survives project tabs, blocks leaving and warns on browser unload', async () => {
  setup();
  const user = userEvent.setup();
  fireEvent.change(await screen.findByLabelText('Puzzle title'), {
    target: { value: 'Keep draft' },
  });
  await user.click(screen.getByRole('link', { name: 'Overview' }));
  await user.click(screen.getByRole('link', { name: 'Edit' }));
  expect(screen.getByLabelText('Puzzle title')).toHaveValue('Keep draft');
  const event = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  await user.click(screen.getByRole('link', { name: 'Book library' }));
  expect(confirm).toHaveBeenCalled();
  expect(location.pathname).toBe('/books/garden-demo/edit');
});

test.each(['unavailable', 'malformed'])('preserves edits after %s response', async (failure) => {
  setup();
  const user = userEvent.setup();
  fireEvent.change(await screen.findByLabelText('Puzzle title'), { target: { value: 'Retained' } });
  vi.mocked(fetch).mockImplementationOnce(async () => {
    if (failure === 'unavailable') throw new TypeError('Network error');
    return new Response('not json');
  });
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    failure === 'unavailable' ? 'cannot reach' : 'unreadable response',
  );
  expect(screen.getByLabelText('Puzzle title')).toHaveValue('Retained');
  expect(screen.getByText('Unsaved changes')).toBeVisible();
});

test('pending operations disable changes and unmounted preview responses are ignored', async () => {
  setup();
  const user = userEvent.setup();
  const title = await screen.findByLabelText('Puzzle title');
  let finish!: (response: Response) => void;
  vi.mocked(fetch).mockImplementationOnce(
    () =>
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
  );
  await user.click(screen.getByRole('button', { name: 'Preview draft' }));
  expect(title).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  await user.click(screen.getByRole('link', { name: 'Book library' }));
  finish(new Response(JSON.stringify(generated)));
  await waitFor(() => expect(location.pathname).toBe('/books'));
  expect(
    screen.queryByText('Draft preview ready. Source has not changed.'),
  ).not.toBeInTheDocument();
});
