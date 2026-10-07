import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { test, expect, vi } from 'vitest';
import { App } from './App';
import { measureText, pageLabel, spreadOf } from './Print';
import type { InteriorStatus, PreflightReport } from './types';
import composed from './fixtures/composition-project.json';
import current from './fixtures/interior.json';
import missing from './fixtures/interior-missing.json';
import stale from './fixtures/interior-stale.json';

type Status = object;

function setup(initial: Status, built: object = current) {
  const calls: { url: string; body: Record<string, unknown> }[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    const path = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : {};
    calls.push({ url: path, body });
    if (path.endsWith('/interior/build')) return new Response(JSON.stringify(built));
    if (path.endsWith('/interior')) return new Response(JSON.stringify(initial));
    if (path.endsWith('/draft/plan')) return new Response('{}', { status: 500 });
    return new Response(JSON.stringify(composed));
  });
  history.replaceState(null, '', '/books/composition-demo/print');
  render(<App />);
  return calls;
}

const canvas = () => screen.getByLabelText(/Rendered pages/);
const announced = () => document.querySelector('.print-current')!.textContent;
const pageImages = () =>
  [...document.querySelectorAll('.sheet img')].map((img) => img.getAttribute('src'));

test('shows structural validity and KDP readiness as separate text statuses', async () => {
  setup(current);
  const verdict = await screen.findByLabelText('Preflight status');
  expect(within(verdict).getByText('Structural')).toBeVisible();
  expect(within(verdict).getByText('Valid')).toBeVisible();
  expect(within(verdict).getByText('KDP readiness')).toBeVisible();
  expect(within(verdict).getByText('Not ready')).toBeVisible();
  expect(within(verdict).getByRole('link', { name: '1 blocking · 1 warning' })).toHaveAttribute(
    'href',
    '#print-findings',
  );
  expect(screen.getByRole('link', { name: 'Print', current: 'page' })).toBeVisible();
  const findings = screen.getByRole('region', { name: 'Preflight findings' });
  expect(within(findings).getByRole('heading', { name: 'Blocking (1)' })).toBeVisible();
  expect(
    within(findings).getByText('11 pages. The supported KDP paperback minimum is 24 pages.'),
  ).toBeVisible();
  expect(
    within(findings).getByText('Measured 11 pages · required at least 24 pages'),
  ).toBeVisible();
  expect(within(findings).getByText(/Whole book · Blocks KDP readiness/)).toBeVisible();
  // Book-level findings offer no page to jump to.
  expect(within(findings).queryByRole('button', { name: /Show page/ })).toBeNull();
  expect(
    within(findings).getByText('Amazon KDP remains the final authority.', { exact: false }),
  ).toBeVisible();
  expect(within(findings).getByText('Passed checks (36)')).toBeInTheDocument();
  expect(within(findings).getByText('Not applicable (1)')).toBeInTheDocument();
});

test('navigates pages with buttons, direct entry, thumbnails and the keyboard', async () => {
  setup(current);
  const user = userEvent.setup();
  await screen.findByLabelText('Preflight status');
  expect(announced()).toBe('Page 1 · Recto (right) · Title page of 11');
  expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Next page' }));
  expect(announced()).toBe('Page 2 · Verso (left) · Copyright page of 11');
  const input = screen.getByLabelText('Page');
  await user.clear(input);
  await user.type(input, '9{Enter}');
  expect(announced()).toBe('Page 9 · Recto (right) · Solutions · number 5 printed of 11');
  expect(screen.getByRole('img', { name: /Rendered Page 9/ })).toHaveAccessibleName(
    /Solutions for puzzle 1 \(p\. 1\), 2 \(p\. 2\)/,
  );
  await user.clear(input);
  await user.type(input, '99{Enter}');
  expect(announced()).toMatch(/^Page 11 ·/);
  const pages = screen.getByRole('navigation', { name: 'Pages' });
  await user.click(within(pages).getByRole('button', { name: /^Page 4 · Verso/ }));
  expect(announced()).toBe('Page 4 · Verso (left) · Intentional blank of 11');
  expect(within(pages).getByRole('button', { name: /^Page 4 ·/ })).toHaveAttribute(
    'aria-current',
    'page',
  );
  fireEvent.keyDown(canvas(), { key: 'ArrowRight' });
  expect(announced()).toBe('Page 5 · Recto (right) · Puzzle · number 1 printed of 11');
  fireEvent.keyDown(canvas(), { key: 'End' });
  expect(announced()).toMatch(/^Page 11 · Recto \(right\) · Notes page/);
  fireEvent.keyDown(canvas(), { key: 'PageUp' });
  expect(announced()).toMatch(/^Page 10 ·/);
  fireEvent.keyDown(canvas(), { key: 'Home' });
  expect(announced()).toMatch(/^Page 1 ·/);
  // Typing in the page field never turns pages.
  fireEvent.keyDown(input, { key: 'ArrowRight' });
  expect(announced()).toMatch(/^Page 1 ·/);
  // Thumbnail images are decorative; each button carries the page's text label.
  const thumbs = [...pages.querySelectorAll('img')];
  expect(thumbs).toHaveLength(11);
  expect(thumbs[3]).toHaveAttribute('loading', 'lazy');
  expect(thumbs[3].getAttribute('src')).toContain(`size=thumb&pdf=${current.preview.pdf_sha256}`);
});

test('spread view pairs verso with recto and keeps page 1 alone on the right', async () => {
  setup(current);
  const user = userEvent.setup();
  await screen.findByLabelText('Preflight status');
  await user.click(screen.getByRole('button', { name: 'Spread' }));
  expect(screen.getByRole('button', { name: 'Spread' })).toHaveAttribute('aria-pressed', 'true');
  expect(announced()).toBe('Spread: page 1 of 11 alone (first page is a recto)');
  expect(pageImages()).toHaveLength(1);
  await user.click(screen.getByRole('button', { name: 'Next spread' }));
  expect(announced()).toBe('Spread: pages 2 and 3 of 11');
  const [left, right] = pageImages();
  expect(left).toContain('/pages/2?');
  expect(right).toContain('/pages/3?');
  fireEvent.keyDown(canvas(), { key: 'ArrowRight' });
  fireEvent.keyDown(canvas(), { key: 'ArrowRight' });
  fireEvent.keyDown(canvas(), { key: 'ArrowRight' });
  expect(announced()).toBe('Spread: pages 8 and 9 of 11');
  const captions = [...document.querySelectorAll('.sheet figcaption strong')].map(
    (c) => c.textContent,
  );
  expect(captions).toEqual([
    'Page 8 · Verso (left) · Puzzle · number 4 printed',
    'Page 9 · Recto (right) · Solutions · number 5 printed',
  ]);
  fireEvent.keyDown(canvas(), { key: 'ArrowLeft' });
  expect(announced()).toBe('Spread: pages 6 and 7 of 11');
});

test('overlays draw authoritative boxes and zoom chooses page or detail rasters', async () => {
  setup(current);
  const user = userEvent.setup();
  await screen.findByLabelText('Preflight status');
  await user.click(screen.getByRole('button', { name: 'Next page' }));
  const overlay = screen.getByTestId('overlay-2');
  expect(overlay.querySelector('.overlay-live')).toBeNull();
  await user.click(screen.getByRole('checkbox', { name: /Live area/ }));
  await user.click(screen.getByRole('checkbox', { name: /KDP minimum margins/ }));
  await user.click(screen.getByRole('checkbox', { name: /Element bounds/ }));
  const live = overlay.querySelector('.overlay-live')!;
  const geometry = current.preview.geometry[1];
  // A verso page: the binding (inside) margin is on the right.
  expect(live.getAttribute('x')).toBe(String(geometry.live.x));
  expect(live.getAttribute('y')).toBe(String(-(geometry.live.y + geometry.live.height)));
  expect(geometry.live.x).toBe(36);
  expect(overlay.querySelector('.overlay-kdp')!.getAttribute('x')).toBe('18');
  expect(overlay.querySelector('.overlay-binding')!.getAttribute('x')).toBe('608');
  expect(overlay.querySelectorAll('.overlay-element')).toHaveLength(geometry.elements.length);
  expect(pageImages()[0]).toContain('size=page');
  await user.selectOptions(screen.getByLabelText('Zoom level'), '300');
  expect(pageImages()[0]).toContain('size=detail');
  expect(document.querySelector<HTMLElement>('.sheet')!.style.width).toBe('2448px');
  await user.click(screen.getByRole('button', { name: 'Zoom out' }));
  expect(screen.getByLabelText('Zoom level')).toHaveValue('200');
  await user.click(screen.getByRole('button', { name: 'Zoom in' }));
  expect(screen.getByRole('button', { name: 'Zoom in' })).toBeDisabled();
});

test('selecting a page finding navigates to its page and highlights its region', async () => {
  const withRegion = structuredClone(current) as unknown as InteriorStatus & {
    report: PreflightReport;
  };
  withRegion.report.findings.push({
    ...withRegion.report.findings[0],
    rule: 'kdp_minimum_font_size',
    severity: 'error',
    message: 'Text size 6 pt is below the 7 pt minimum.',
    physical_page: 6,
    side: 'verso',
    page_kind: 'puzzle',
    folio: '2',
    region: 'word_list',
    bounds: { x: 100, y: 200, width: 50, height: 12 },
    measure: { actual: 6, required: 7, unit: 'pt', comparison: 'at_least' },
  });
  setup(withRegion);
  const user = userEvent.setup();
  await screen.findByLabelText('Preflight status');
  expect(screen.getByText('Measured 6 pt · required at least 7 pt')).toBeVisible();
  expect(screen.getByText(/Page 6 · verso · Puzzle · number 2/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Show region on page 6' }));
  expect(announced()).toMatch(/^Page 6 · Verso/);
  expect(screen.getByRole('button', { name: 'Show region on page 6' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  const highlight = screen.getByTestId('overlay-6').querySelector('.overlay-selected')!;
  expect([highlight.getAttribute('x'), highlight.getAttribute('y')]).toEqual(['100', '-212']);
  expect(screen.getByRole('checkbox', { name: /Finding regions/ })).toBeChecked();
});

test('missing interior offers a build that runs preflight and shows the proof', async () => {
  const calls = setup(missing);
  const user = userEvent.setup();
  expect(await screen.findByText('No interior has been built.')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Build interior' }));
  await screen.findByLabelText('Preflight status');
  const build = calls.find((c) => c.url.endsWith('/interior/build'))!;
  expect(build.body).toEqual({ revision: composed.revision });
  expect(screen.getByText('Interior built and preflight complete.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Rebuild interior' })).toBeEnabled();
});

test('a failed build lists diagnostics and keeps the previous state', async () => {
  setup(missing, {
    ...missing,
    build: {
      success: false,
      stage: 'layout',
      diagnostics: [
        {
          code: 'text_overflow',
          message: 'Text does not fit its region.',
          page: 3,
          physical_page: 3,
          kind: 'instructions',
          subject: null,
          region: 'body',
          actual: '900.00 pt tall',
          required: 'at most 654.00 pt',
        },
      ],
    },
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Build interior' }));
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('The interior did not build');
  expect(alert).toHaveTextContent('Text does not fit its region. text_overflow · page 3');
  expect(alert).toHaveTextContent('measured 900.00 pt tall; allowed at most 654.00 pt');
  expect(screen.getByText('No interior has been built.')).toBeVisible();
});

test('a stale interior is labeled, shows the old pages and disables overlays', async () => {
  setup(stale);
  await screen.findByLabelText('Preflight status');
  expect(screen.getByText('This interior is out of date.')).toBeVisible();
  expect(screen.getByText('Invalid')).toBeVisible();
  expect(screen.getByText('Built from current source')).toBeVisible();
  expect(screen.getByRole('checkbox', { name: /Live area/ })).toBeDisabled();
  expect(
    screen.getByText('Overlays need an interior built from the current saved source.'),
  ).toBeVisible();
  expect(announced()).toBe('Page 1 · Recto (right) of 11');
  expect(
    [...document.querySelectorAll('summary')].some((e) =>
      /^Not evaluated \(\d+\)$/.test(e.textContent ?? ''),
    ),
  ).toBe(true);
  expect(pageImages()[0]).toContain(`pdf=${stale.preview.pdf_sha256}`);
});

test('unsaved drafts block builds with an explanation', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const path = String(url);
    if (path.endsWith('/interior')) return new Response(JSON.stringify(missing));
    if (path.endsWith('/draft/plan')) return new Response('{}', { status: 500 });
    return new Response(JSON.stringify(composed));
  });
  history.replaceState(null, '', '/books/composition-demo/book');
  render(<App />);
  const user = userEvent.setup();
  const title = await screen.findByLabelText('Section heading');
  await user.type(title, ' edited');
  await user.click(screen.getByRole('link', { name: 'Print' }));
  await waitFor(() => expect(screen.getByText('No interior has been built.')).toBeVisible());
  expect(screen.getByRole('button', { name: 'Build interior' })).toBeDisabled();
  expect(
    screen.getByText(
      'You have unsaved changes. This proof shows the saved source; save before building.',
    ),
  ).toBeVisible();
});

test('pure helpers: spreads, labels and measures', () => {
  expect(spreadOf(1, 11)).toEqual([null, 1]);
  expect(spreadOf(2, 11)).toEqual([2, 3]);
  expect(spreadOf(3, 11)).toEqual([2, 3]);
  expect(spreadOf(10, 10)).toEqual([10, null]);
  expect(pageLabel(undefined, 4)).toBe('Page 4 · Verso (left)');
  expect(measureText({ actual: 0.3, required: 0.375, unit: 'in', comparison: 'at_least' })).toBe(
    'Measured 0.3 in · required at least 0.375 in',
  );
  expect(measureText({ actual: 11, required: null, unit: 'pages', comparison: null })).toBe(
    'Measured 11 pages',
  );
});
