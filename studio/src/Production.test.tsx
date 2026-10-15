import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import {
  addElement,
  duplicateElement,
  moveElement,
  moveInStack,
  photoCrop,
  resetStyle,
  setPhotoCrop,
  updateElement,
} from './cover-elements-model';
import { ProductionOverview, RebuildPanel } from './production';
import { ReviewControls } from './review';
import type { CoverConfig, CoverLayoutView, ProductionStatus, ReviewStatusResponse } from './types';

// ------------------------------------------------------------------ element model

const base: CoverConfig = {
  version: 3,
  type: { style: 'editorial', position: 'top', align: 'center', tone: 'light' },
  legibility: 'shade',
  spine_text: 'auto',
  regions: {
    back: { color: '#1d2a44' },
    spine: { color: '#1d2a44' },
    front: { color: '#1d2a44' },
  },
  elements: [],
};
const box = (x: number, width: number) => ({ x, y: 0, width, height: 792 });
const layout = {
  geometry: {
    regions: { trim: box(9, 1233), back: box(9, 612), spine: box(621, 9), front: box(630, 612) },
  },
  regions: {
    wrap: { origin: box(9, 1233), area: box(0, 1251) },
    back: { origin: box(9, 612), area: box(0, 621) },
    spine: { origin: box(621, 9), area: box(621, 9) },
    front: { origin: box(630, 612), area: box(630, 621) },
  },
} as unknown as CoverLayoutView;

test('elements are added centered in their region and keep a deterministic stack', () => {
  const [one, first] = addElement(base, 'rect', 'front', layout);
  const [two, second] = addElement(one, 'text', 'back', layout);
  expect([first, second]).toEqual(['element:block-1', 'element:text-1']);
  const rect = two.elements![0];
  expect(rect.type === 'rect' && rect.box).toEqual({ x: 198, y: 342, width: 216, height: 108 });
  const [spine] = addElement(base, 'rect', 'spine', layout);
  expect(spine.elements![0].type === 'rect' && spine.elements![0].box?.width).toBe(9);
  const forward = moveInStack(two, 'block-1', true);
  expect(forward.elements!.map((e) => e.id)).toEqual(['text-1', 'block-1']);
  expect(moveInStack(forward, 'block-1', true)).toBe(forward); // Already on top.
});

test('locked elements never move and duplicates are unlocked copies beside them', () => {
  const [one] = addElement(base, 'rect', 'front', layout);
  const moved = moveElement(one, 'block-1', 10, -5);
  const movedBox = moved.elements![0].type === 'rect' ? moved.elements![0].box : undefined;
  expect(movedBox).toMatchObject({ x: 208, y: 337 });
  const locked = updateElement(one, 'block-1', { locked: true });
  expect(moveElement(locked, 'block-1', 10, 10)).toBe(locked);
  const [copied, layer] = duplicateElement(locked, 'block-1');
  expect(layer).toBe('element:block-2');
  expect(copied.elements![1].locked).toBeUndefined();
  expect(updateElement(locked, 'block-1', { locked: false }).elements![0]).not.toHaveProperty(
    'locked',
  );
});

test('photo crops are edited per layer and styles reset to defaults', () => {
  const image = { path: 'cover-assets/a-1.jpg', sha256: 'a'.repeat(64) };
  const [one, layer] = addElement(base, 'photo', 'front', layout, image);
  expect(photoCrop(one, layer)).toEqual({ x: 0.5, y: 0.5, zoom: 1 });
  const cropped = setPhotoCrop(one, layer, { x: 0.2, y: 0.4, zoom: 2 });
  expect(photoCrop(cropped, layer)).toEqual({ x: 0.2, y: 0.4, zoom: 2 });
  const legacy = { ...base, version: 1, image, crop: { x: 0.5, y: 0.5, zoom: 1 } };
  expect(photoCrop(setPhotoCrop(legacy, 'photo', { x: 0.3, y: 0.3, zoom: 1 }), 'photo')!.x).toBe(
    0.3,
  );
  const [shape] = addElement(base, 'ellipse', 'front', layout);
  const styled = updateElement(shape, 'ellipse-1', { fill: '#000000', opacity: 0.5 });
  const reset = updateElement(styled, 'ellipse-1', resetStyle(styled.elements![0]));
  expect(reset.elements![0]).toMatchObject({ fill: '#f4efe4', stroke: null });
  expect(reset.elements![0]).not.toHaveProperty('opacity');
});

// ------------------------------------------------------------------ rebuild and overview

const status: ProductionStatus = {
  key: 'book',
  revision: 'sha256-1',
  statement: '3 blocking item(s) and 4 decision(s) or outside step(s) remain.',
  items: [
    {
      code: 'interior_current',
      title: 'Interior is current',
      status: 'blocking',
      basis: 'internal',
      blocks_export: true,
      what: 'Built from current source.',
      why: 'Previews must describe the files you upload.',
      action: 'Rebuild in Print.',
      area: 'print',
      detail: 'Out of date: an interior style was added.',
    },
    {
      code: 'ai_disclosure',
      title: 'AI disclosure',
      status: 'awaiting_review',
      basis: 'author_judgment',
      blocks_export: true,
      what: 'Your declaration.',
      why: 'Only you can declare it.',
      action: 'Declare it yourself in Publishing.',
      area: 'publishing',
      detail: 'Not declared yet: nothing is selected for you.',
    },
    {
      code: 'physical_proof',
      title: 'Physical proof',
      status: 'external_pending',
      basis: 'external',
      blocks_export: false,
      what: 'Your review of a printed proof.',
      why: 'PuzzlePress cannot certify acceptance.',
      action: 'Record it in Publishing after you review.',
      area: 'publishing',
      detail: 'Nothing recorded yet.',
    },
  ],
  stages: [
    { code: 'built', title: 'Built artifacts', reached: false, detail: 'Not current.' },
    { code: 'published', title: 'Published', reached: null, detail: 'Never tracked.' },
  ],
  proofing: [{ code: 'upload', title: 'Upload the files to KDP yourself', area: 'external' }],
  assessment: {
    artifacts: [
      {
        name: 'interior',
        state: 'stale',
        reasons: ['An interior style was added.'],
        depends_on: [],
      },
    ],
    steps: [
      {
        action: 'build_interior',
        artifact: 'interior',
        why: 'An interior style was added.',
        conditional: false,
      },
      {
        action: 'build_cover',
        artifact: 'cover',
        why: 'Checked again after the interior.',
        conditional: true,
      },
    ],
    manual: [],
    outdated: true,
  },
  reviews: {
    total: 4,
    reviewed: 0,
    needs_changes: 0,
    not_reviewed: 4,
    stale: 0,
    complete: false,
    require_all: false,
  },
  proofs: {
    revision: null,
    artifacts: null,
    proofs: [],
    print_previewer: null,
    physical_proof: null,
  },
};

test('the rebuild panel shows its plan and reports only what the server confirms', async () => {
  let release!: (value: Response) => void;
  const done = {
    ...status,
    assessment: { ...status.assessment, steps: [], outdated: false },
    rebuild: {
      success: true,
      results: [
        {
          action: 'build_interior',
          status: 'succeeded',
          message: 'Interior built.',
          stage: null,
          diagnostics: [],
        },
        {
          action: 'build_cover',
          status: 'unchanged',
          message: 'Still current.',
          stage: null,
          diagnostics: [],
        },
      ],
    },
  };
  const calls: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    calls.push(String(url));
    if (String(url).endsWith('/rebuild')) return new Promise<Response>((r) => (release = r));
    return new Response(JSON.stringify(status));
  });
  render(<RebuildPanel projectKey="book" revision="sha256-1" dirty={false} />);
  expect(await screen.findByText('Rebuild the interior and its preflight report')).toBeVisible();
  expect(screen.getByText(/only if needed/)).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Rebuild 2 steps' }));
  expect(screen.getByRole('button', { name: 'Rebuilding…' })).toBeDisabled();
  expect(screen.queryByText('succeeded')).toBeNull();
  release(new Response(JSON.stringify(done)));
  const results = await screen.findByRole('list', { name: 'Rebuild results' });
  expect(within(results).getByText('succeeded')).toBeVisible();
  expect(within(results).getByText('unchanged')).toBeVisible();
  expect(screen.getByText(/server confirmed every step/)).toBeVisible();
  expect(calls.filter((c) => c.endsWith('/rebuild'))).toHaveLength(1);
});

test('rebuilds wait for unsaved changes to be saved', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(status)));
  render(<RebuildPanel projectKey="book" revision="sha256-1" dirty />);
  expect(await screen.findByRole('button', { name: 'Rebuild 2 steps' })).toBeDisabled();
  expect(screen.getByText(/rebuilds use the saved source/)).toBeVisible();
});

test('the overview keeps rule kinds apart and never shows an approval it did not receive', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(status)));
  render(<ProductionOverview projectKey="book" revision="sha256-1" dirty={false} />);
  const list = await screen.findByRole('list', { name: 'Production checklist' });
  expect(within(list).getByText('PuzzlePress rule')).toBeVisible();
  expect(within(list).getByText('Your judgment')).toBeVisible();
  expect(within(list).getByText('Outside PuzzlePress')).toBeVisible();
  expect(within(list).getByText('Awaiting your decision')).toBeVisible();
  expect(within(list).getByText('Outside step not recorded')).toBeVisible();
  expect(screen.getByRole('list', { name: 'Production stages' })).toHaveTextContent('Not tracked');
  expect(screen.queryByText(/approved/i)).toBeNull();
  expect(screen.getByText('Build the interior before recording a proof.')).toBeVisible();
});

// ------------------------------------------------------------------ review

const reviews: ReviewStatusResponse = {
  source_revision: 'sha256-book',
  revision: null,
  report: {
    summary: {
      total: 1,
      reviewed: 0,
      needs_changes: 0,
      not_reviewed: 1,
      stale: 0,
      complete: false,
      require_all: false,
    },
    puzzles: [
      {
        puzzle: 'p1',
        title: 'Engines',
        theme: 'Engines',
        identity: 'pp1-puzzle-review-sha256-' + 'b'.repeat(64),
        state: 'not_reviewed',
        recorded: null,
      },
    ],
    orphaned: [],
  },
};

test('a review records the saved content identity Python reported', async () => {
  const bodies: Record<string, unknown>[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
    bodies.push(JSON.parse(String(options?.body)));
    return new Response(JSON.stringify(reviews));
  });
  const saved = vi.fn();
  render(
    <ReviewControls
      projectKey="book"
      review={reviews.report.puzzles[0]}
      data={reviews}
      onSaved={saved}
      unsaved={false}
    />,
  );
  await userEvent.click(screen.getByRole('button', { name: 'Mark reviewed' }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  expect(bodies[0]).toMatchObject({
    source_revision: 'sha256-book',
    puzzle: 'p1',
    status: 'reviewed',
    identity: reviews.report.puzzles[0].identity,
    reviewer: null,
    reviewed_on: null,
  });
});

test('unsaved puzzle edits cannot be marked reviewed', () => {
  render(
    <ReviewControls
      projectKey="book"
      review={reviews.report.puzzles[0]}
      data={reviews}
      onSaved={vi.fn()}
      unsaved
    />,
  );
  expect(screen.getByRole('button', { name: 'Mark reviewed' })).toBeDisabled();
  expect(screen.getByText(/Save first/)).toBeVisible();
});
