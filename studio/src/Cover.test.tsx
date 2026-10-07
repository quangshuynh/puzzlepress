import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { test, expect, vi } from 'vitest';
import { App } from './App';
import { dragFocal, starterCover, viewBox } from './Cover';
import type { CoverDraft, CoverLayoutView } from './types';
import assets from './fixtures/cover-assets.json';
import built from './fixtures/cover-built.json';
import draftFixture from './fixtures/cover-draft.json';
import missing from './fixtures/cover-missing.json';
import project from './fixtures/cover-project.json';
import stale from './fixtures/cover-stale.json';

type Call = { url: string; body: Record<string, unknown>; type: string | null };
const draft = draftFixture as unknown as CoverDraft;
const layout = draft.layout as CoverLayoutView;

function setup({
  status = missing as object,
  source = project as object,
  invalid = false,
}: { status?: object; source?: object; invalid?: boolean } = {}) {
  let saved = structuredClone(source) as typeof project;
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    const path = String(url);
    const type = (options?.headers as Record<string, string> | undefined)?.['Content-Type'] ?? null;
    const body =
      options?.body && type === 'application/json' ? JSON.parse(String(options.body)) : {};
    calls.push({ url: path, body, type });
    if (path.includes('/cover/assets') && options?.method === 'POST')
      return new Response(
        JSON.stringify({ asset: { ...assets.assets[0], reused: false }, assets: assets.assets }),
      );
    if (path.endsWith('/cover/assets')) return new Response(JSON.stringify(assets));
    if (path.endsWith('/draft/cover')) {
      if (invalid)
        return new Response(
          JSON.stringify({
            error: {
              code: 'invalid_project',
              message: 'Project validation failed.',
              issues: [
                {
                  path: 'cover.crop.zoom',
                  code: 'crop_invalid',
                  message: 'Expected a value from 1 to 4.',
                },
              ],
            },
          }),
          { status: 422 },
        );
      return new Response(JSON.stringify(draft));
    }
    if (path.endsWith('/cover/build')) return new Response(JSON.stringify(built));
    if (path.endsWith('/cover')) return new Response(JSON.stringify(status));
    if (path.endsWith('/draft/save')) {
      saved = { ...saved, source: body.source as typeof saved.source, revision: 'sha256-new' };
    }
    return new Response(JSON.stringify(saved));
  });
  history.replaceState(null, '', '/books/cover-demo/cover');
  render(<App />);
  return calls;
}

const studio = () => document.querySelector('.cover-studio') as HTMLElement;
const drafts = (calls: Call[]) => calls.filter((c) => c.url.endsWith('/draft/cover'));
const lastCrop = (calls: Call[]) =>
  (drafts(calls).at(-1)!.body.source as { cover: { crop: object } }).cover.crop;

test('previews the real draft PDF and reports interior facts from Python', async () => {
  const calls = setup();
  const image = await screen.findByRole('img', { name: /Draft cover: full wrap view/ });
  expect(image.getAttribute('src')).toContain(`pdf=${draft.preview!.pdf_sha256}`);
  expect(image.getAttribute('src')).toContain('/api/projects/cover-demo/cover/preview?size=');
  expect(screen.getByRole('link', { name: 'Cover', current: 'page' })).toBeVisible();
  const readiness = screen.getByRole('complementary', { name: 'Cover readiness' });
  expect(within(readiness).getByText('0.0788 in')).toBeVisible();
  expect(within(readiness).getByText('35 pages · white paper · 8.5 x 11 in')).toBeVisible();
  expect(within(readiness).getByText(/320 DPI · Sufficient/)).toBeVisible();
  expect(
    within(readiness).getByText(
      'Omitted: KDP prints spine text only on books of 80 pages or more.',
    ),
  ).toBeVisible();
  expect(within(readiness).getByText(/No cover has been built/)).toBeVisible();
  // A cover that does not exist yet is not shown as invalid.
  expect(within(readiness).queryByLabelText('Cover preflight status')).toBeNull();
  expect(within(readiness).getByRole('button', { name: 'Build cover' })).toBeEnabled();
  expect(drafts(calls)).toHaveLength(1);
});

test('crop controls edit the draft, re-render it and block building until saved', async () => {
  const calls = setup();
  await screen.findByRole('img', { name: /Draft cover/ });
  fireEvent.change(screen.getByLabelText(/Focal point, left to right/), {
    target: { value: '0.25' },
  });
  fireEvent.change(screen.getByLabelText(/Zoom/), { target: { value: '1.5' } });
  await waitFor(() => expect(drafts(calls)).toHaveLength(2), { timeout: 3000 });
  expect(lastCrop(calls)).toEqual({ x: 0.25, y: 0.45, zoom: 1.5 });
  expect(within(studio()).getByText('Unsaved changes')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Build cover' })).toBeDisabled();
  expect(screen.getByText(/Save the draft first/)).toBeVisible();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Build cover' })).toBeEnabled());
  const save = calls.find((c) => c.url.endsWith('/draft/save'))!;
  expect((save.body.source as { cover: { crop: object } }).cover.crop).toEqual({
    x: 0.25,
    y: 0.45,
    zoom: 1.5,
  });
});

test('keyboard moves the focal point and zooms without a pointer', async () => {
  const calls = setup();
  await screen.findByRole('img', { name: /Draft cover/ });
  const canvas = screen.getByRole('group', { name: /Drag to move the photograph/ });
  fireEvent.keyDown(canvas, { key: 'ArrowRight' });
  fireEvent.keyDown(canvas, { key: 'ArrowDown', shiftKey: true });
  fireEvent.keyDown(canvas, { key: '+' });
  fireEvent.keyDown(canvas, { key: '', code: 'Equal' });
  await waitFor(() => expect(lastCrop(calls)).toEqual({ x: 0.51, y: 0.5, zoom: 1.1 }));
  fireEvent.keyDown(canvas, { key: '0' });
  await waitFor(() => expect(lastCrop(calls)).toEqual({ x: 0.5, y: 0.5, zoom: 1 }));
});

test('overlays draw Python geometry and views crop the same raster', async () => {
  setup();
  await screen.findByRole('img', { name: /Draft cover/ });
  expect(screen.queryByTestId('cover-overlay')).toBeNull();
  const user = userEvent.setup();
  await user.click(screen.getByRole('checkbox', { name: /Barcode area/ }));
  await user.click(screen.getByRole('checkbox', { name: /Trim and folds/ }));
  const overlay = screen.getByTestId('cover-overlay');
  const barcode = layout.geometry.regions.barcode;
  const rect = overlay.querySelector('.overlay-barcode')!;
  expect(Number(rect.getAttribute('x'))).toBeCloseTo(barcode.x);
  expect(Number(rect.getAttribute('width'))).toBeCloseTo(barcode.width);
  expect(overlay.querySelectorAll('.overlay-fold')).toHaveLength(2);
  await user.click(screen.getByRole('button', { name: 'Front' }));
  expect(screen.getByRole('img', { name: /front view/ })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Front' })).toHaveAttribute('aria-pressed', 'true');
});

test('building shows separate structural and KDP verdicts and the built PDF', async () => {
  const calls = setup();
  await screen.findByRole('img', { name: /Draft cover/ });
  await userEvent.setup().click(screen.getByRole('button', { name: 'Build cover' }));
  const verdict = await screen.findByLabelText('Cover preflight status');
  expect(within(verdict).getByText('Valid')).toBeVisible();
  expect(within(verdict).getByText('Ready')).toBeVisible();
  const build = calls.find((c) => c.url.endsWith('/cover/build'))!;
  expect(build.body).toEqual({ revision: project.revision });
  expect(screen.getByRole('heading', { name: 'Warnings (1)' })).toBeVisible();
  expect(screen.getByText(/KDP recommends CMYK/)).toBeVisible();
  const image = screen.getByRole('img', { name: /Built cover\.pdf/ });
  expect(image.getAttribute('src')).toContain(`pdf=${built.preview!.pdf_sha256}`);
});

test('a stale built cover says why', async () => {
  setup({ status: stale });
  expect(await screen.findByText('The built cover is out of date.')).toBeVisible();
  expect(screen.getByText(/crop changed/)).toBeVisible();
});

test('field errors from Python attach to the crop controls', async () => {
  setup({ invalid: true });
  await waitFor(
    () => expect(screen.getByLabelText(/^Zoom/)).toHaveAttribute('aria-invalid', 'true'),
    { timeout: 3000 },
  );
  expect(screen.getByText(/Expected a value from 1 to 4/)).toBeVisible();
});

test('a book without a cover starts from a chosen or imported photograph', async () => {
  const bare = structuredClone(project);
  Reflect.deleteProperty(bare.source, 'cover');
  const calls = setup({ source: bare, status: { ...missing, state: 'no_config', report: null } });
  expect(
    await screen.findByRole('heading', { name: 'Start a cover from your photograph' }),
  ).toBeVisible();
  const user = userEvent.setup();
  const input = screen.getByLabelText('Import a photograph (JPEG or PNG)');
  // The accept filter can be bypassed in file pickers; the client still refuses.
  await userEvent
    .setup({ applyAccept: false })
    .upload(input, new File(['gif'], 'scan.gif', { type: 'image/gif' }));
  expect(await screen.findByText('Choose a JPEG or PNG photograph.')).toBeVisible();
  await user.upload(input, new File(['jpeg bytes'], 'Dawn.jpg', { type: 'image/jpeg' }));
  await waitFor(() => expect(within(studio()).getByText('Unsaved changes')).toBeVisible(), {
    timeout: 3000,
  });
  const post = calls.find((c) => c.url.includes('/cover/assets?name=Dawn.jpg'))!;
  expect(post.type).toBe('image/jpeg');
  await waitFor(() => expect(drafts(calls).length).toBeGreaterThan(0));
  const cover = (drafts(calls).at(-1)!.body.source as { cover: object }).cover;
  expect(cover).toEqual(
    starterCover({ path: assets.assets[0].path, sha256: assets.assets[0].sha256! }),
  );
});

test('view boxes and drag mapping use Python geometry only', () => {
  const g = layout.geometry;
  expect(viewBox(g, 'wrap')).toEqual(g.regions.media);
  const front = viewBox(g, 'front');
  expect(front.x).toBe(g.regions.front.x);
  expect(front.x + front.width).toBeCloseTo(g.regions.media.width);
  const spine = viewBox(g, 'spine');
  expect(spine.x).toBeLessThan(g.regions.spine.x);
  expect(spine.x + spine.width).toBeGreaterThan(g.regions.spine.x + g.regions.spine.width);
  // Dragging the photo right and down moves the focal point left and up.
  const moved = dragFocal(layout, 40, 30, 0.5);
  expect(moved.x).toBeLessThanOrEqual(layout.photo.center[0]);
  expect(moved.y).toBeLessThan(layout.photo.center[1]);
  expect(dragFocal(layout, -1e6, -1e6, 1)).toEqual({ x: 1, y: 1 });
});
