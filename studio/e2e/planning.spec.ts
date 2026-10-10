import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';

// The server serves disposable copies: the automotive planning demo and a SYNTHETIC
// plan that is ready for approval. Approvals here are test decisions on those copies.

const shot = (name: string) => `../docs/images/studio/${name}.png`;
const originals = ['automotive/book.yaml', 'automotive/planning.yaml'].map((path) => ({
  path,
  bytes: readFileSync(`../books/${path}`),
}));
test.afterAll(() => {
  for (const { path, bytes } of originals) expect(readFileSync(`../books/${path}`)).toEqual(bytes);
});

async function noAxeViolations(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}

async function open(page: Page, key: string, section = '') {
  await page.goto(`/books/${key}/planning${section ? `#planning-${section}` : ''}`);
  await expect(page.getByRole('heading', { name: 'Planning', exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

const readiness = (page: Page) => page.getByRole('complementary', { name: 'Readiness' });
const nav = (page: Page) => page.getByRole('navigation', { name: 'Plan sections' });

test('review the automotive demo plan by section, keyboard and width', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await open(page, 'automotive');
  const panel = readiness(page);
  await expect(panel.getByText(/^Needs research: blocking questions/)).toBeVisible();
  await expect(panel.getByText('Producible with current PuzzlePress')).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Approve this plan' })).toBeDisabled();
  await expect(panel.getByText(/Within the project cap of 100 puzzles/)).toBeVisible();
  await expect(page.getByLabel('Target puzzle count')).toHaveValue('60');
  await noAxeViolations(page);
  await page.screenshot({ path: shot('planning'), fullPage: true });

  // Keyboard: the section list is ordinary links; the section heading takes focus.
  await nav(page)
    .getByRole('link', { name: /^Themes/ })
    .focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#planning-themes$/);
  await expect(page.getByRole('heading', { name: 'Themes', exact: true })).toBeFocused();
  await expect(nav(page).getByRole('link', { name: /^Themes/ })).toHaveAttribute(
    'aria-current',
    'location',
  );
  const chart = page.getByRole('table', { name: /Puzzles by theme: 60 allocated/ });
  await expect(chart.getByRole('rowheader', { name: /Engines & Powertrains/ })).toBeVisible();
  await noAxeViolations(page);
  await page.locator('.planning-section').screenshot({ path: shot('planning-themes') });

  await nav(page)
    .getByRole('link', { name: /^Vocabulary/ })
    .click();
  await expect(page.getByRole('table', { name: /Usable candidate words per theme/ })).toBeVisible();
  await expect(page.getByLabel('Where these words came from')).toHaveValue('ai_generated');
  await noAxeViolations(page);
  await page.locator('.planning-section').screenshot({ path: shot('planning-vocabulary') });

  await nav(page)
    .getByRole('link', { name: /^Difficulty/ })
    .click();
  await expect(page.getByRole('list', { name: 'Planned puzzles in book order' })).toBeVisible();
  await expect(page.getByText('53 not yet specified').first()).toBeVisible();
  await page
    .locator('.plan-figure')
    .first()
    .screenshot({ path: shot('planning-progression') });

  await nav(page)
    .getByRole('link', { name: /^Research/ })
    .click();
  await expect(page.getByText(/0 verified by you/)).toBeVisible();
  await nav(page)
    .getByRole('link', { name: /^Comparable books/ })
    .click();
  await expect(page.getByText('No comparable books recorded.')).toBeVisible();

  await nav(page)
    .getByRole('link', { name: /^Coverage/ })
    .click();
  await expect(
    page.getByRole('heading', { name: /Editorial review \(never blocks\)/ }),
  ).toBeVisible();
  await expect(page.getByText(/Pool engines has 31 usable words/)).toBeVisible();
  await noAxeViolations(page);
  await page.locator('.planning-section').screenshot({ path: shot('planning-coverage') });

  for (const [name, width, height] of [
    ['1024', 1024, 768],
    ['768', 768, 1024],
    ['390', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    await open(page, 'automotive', 'themes');
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      name,
    ).toBe(true);
    await expect(readiness(page)).toBeVisible();
    if (name === '390') {
      await noAxeViolations(page);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: shot('planning-390'), fullPage: true });
    }
  }
  expect(errors).toEqual([]);
});

test('edit with Python checks, save beside book.yaml, conflicts keep the draft', async ({
  page,
  request,
}) => {
  page.on('dialog', (dialog) => void dialog.accept());
  await page.setViewportSize({ width: 1440, height: 1000 });
  const book = await (await request.get('/api/projects/automotive')).json();
  await open(page, 'automotive');
  const subject = page.getByLabel('Subject or niche');
  const checked = page.waitForResponse((r) => r.url().endsWith('/draft/planning'));
  await subject.fill('Automotive technology and workshop practice');
  await checked;
  await expect(page.getByText('Unsaved changes', { exact: true })).toBeVisible();
  await expect(readiness(page).getByText(/Draft, checked by Python/)).toBeVisible();

  // A schema problem is shown beside its field; the draft is kept and nothing saves.
  await page.getByLabel('Target puzzle count').fill('sixty');
  await expect(page.getByLabel('Target puzzle count')).toHaveAttribute('aria-invalid', 'true');
  await page.getByRole('button', { name: 'Save plan' }).click();
  await expect(page.getByRole('alert')).toContainText('does not satisfy the planning schema');
  await expect(subject).toHaveValue('Automotive technology and workshop practice');
  await page.getByLabel('Target puzzle count').fill('60');

  await page.getByRole('button', { name: 'Save plan' }).click();
  await expect(page.getByText(/Saved planning.yaml and reloaded it/)).toBeVisible();
  await expect(page.getByText('Saved plan', { exact: true })).toBeVisible();
  const after = await (await request.get('/api/projects/automotive')).json();
  expect(after.revision).toBe(book.revision); // book.yaml untouched.
  const saved = await (await request.get('/api/projects/automotive/planning')).json();
  expect(saved.source.concept.subject).toBe('Automotive technology and workshop practice');

  // Someone else saves meanwhile: this draft is refused, kept, and can be reloaded.
  await subject.fill('My unsaved subject');
  await request.post('/api/projects/automotive/planning/save', {
    data: {
      source: { ...saved.source, concept: { ...saved.source.concept, scope: 'Changed elsewhere' } },
      revision: saved.revision,
    },
  });
  await page.getByRole('button', { name: 'Save plan' }).click();
  await expect(page.getByRole('heading', { name: 'The saved plan has changed' })).toBeVisible();
  await expect(subject).toHaveValue('My unsaved subject');
  await page.getByRole('button', { name: 'Reload saved plan' }).click();
  await expect(page.getByLabel('Scope')).toHaveValue('Changed elsewhere');

  // Revert returns to the saved plan.
  await subject.fill('Discard me');
  await page.getByRole('button', { name: 'Revert draft' }).click();
  await expect(subject).toHaveValue('Automotive technology and workshop practice');
});

test('approve the reviewed plan; edits make it stale; restoring restores it', async ({ page }) => {
  page.on('dialog', (dialog) => void dialog.accept());
  await page.setViewportSize({ width: 1440, height: 1000 });
  await open(page, 'planning-ready');
  const panel = readiness(page);
  await expect(panel.getByText('Ready for author approval.')).toBeVisible();
  await noAxeViolations(page);
  const approve = panel.getByRole('button', { name: 'Approve this plan' });
  await approve.focus();
  await page.keyboard.press('Enter');
  await expect(panel.getByText('You approved this exact plan.')).toBeVisible();
  await expect(panel.getByText(/Approved: this exact plan is approved/)).toBeVisible();
  await expect(panel.getByText(/puzzlepress plan handoff/)).toBeVisible();
  await page.screenshot({ path: shot('planning-approved'), fullPage: true });

  const subject = page.getByLabel('Subject or niche');
  await subject.fill('Automotive tools');
  await expect(panel.getByText(/Saving them makes the approval stale/)).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Withdraw approval' })).toBeDisabled();
  await page.getByRole('button', { name: 'Save plan' }).click();
  await expect(panel.getByText(/Stale: the plan changed after you approved it/)).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Approve this plan' })).toBeEnabled();
  await noAxeViolations(page);
  await panel.screenshot({ path: shot('planning-stale') });

  // Restoring exactly the approved content restores the approval; nothing re-approves.
  await subject.fill('Automotive');
  await page.getByRole('button', { name: 'Save plan' }).click();
  await expect(panel.getByText('You approved this exact plan.')).toBeVisible();
  await panel.getByRole('button', { name: 'Withdraw approval' }).click();
  await expect(panel.getByText('Not approved.')).toBeVisible();
});

test('start a plan from nothing, keyboard first', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await open(page, 'garden-demo');
  await expect(
    page.getByRole('heading', { name: 'Plan this book before producing it' }),
  ).toBeVisible();
  await noAxeViolations(page);
  await page.getByRole('button', { name: 'Start a plan' }).click();
  await expect(
    readiness(page).getByText(/^Draft: the blueprint is not fully defined/),
  ).toBeVisible();
  await nav(page)
    .getByRole('link', { name: /^Themes/ })
    .click();
  await page.getByRole('button', { name: 'Add theme' }).click();
  const label = page.getByLabel('Label', { exact: true });
  await expect(label).toHaveAttribute('aria-invalid', 'true');
  await label.fill('Flowers');
  await expect(label).not.toHaveAttribute('aria-invalid', 'true');
  await page.getByLabel('Puzzles', { exact: true }).fill('4');
  await page.getByRole('button', { name: 'Save plan' }).click();
  await expect(page.getByText(/Saved planning.yaml and reloaded it/)).toBeVisible();
  await expect(page.getByRole('table', { name: /Puzzles by theme: 4 allocated/ })).toBeVisible();
});
