import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import type { PlanResult } from '../src/types';

// Writes only target the server's temporary composer-demo copy.
const originals = ['garden-demo', 'composition-demo'].map((key) => ({
  key,
  bytes: readFileSync(`../books/${key}/book.yaml`),
}));
test.afterAll(() => {
  for (const { key, bytes } of originals)
    expect(readFileSync(`../books/${key}/book.yaml`)).toEqual(bytes);
});

const api = '/api/projects/composer-demo';
const shot = async (page: Page, name: string) => {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `../docs/images/studio/${name}.png`, fullPage: true });
};
const axe = async (page: Page) =>
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
const planRows = (page: Page) =>
  page.locator('.plan-table tbody tr:not(.plan-section) td.plan-entry strong, .plan-entry em');

test('compose, preview, save, reload and recover from invalid and stale drafts', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    // Expected 422/409 responses are logged by Chrome as failed resources.
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource'))
      errors.push(message.text());
  });
  const original = await (await request.get(api)).json();
  await page.setViewportSize({ width: 1440, height: 1800 });
  await page.goto('/books/composer-demo');
  await page.getByRole('link', { name: 'Book', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Book composer' })).toBeVisible();
  await expect(page.getByRole('status')).toHaveText(
    'Publication plan ready. Source has not changed.',
  );
  await expect(page.getByText('Plan independently verified')).toBeVisible();
  await expect(page.getByRole('cell', { name: '(iv) not printed' })).toBeVisible();
  await expect(page.getByText('Intentional blank', { exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await axe(page);
  await shot(page, 'composer');

  // Front matter: author-written notice and instructions.
  await page.getByLabel('Copyright notice').fill('Copyright 2026 Example Author.');
  await page.getByLabel('Instructions heading').fill('How to Solve');
  await expect(
    page.locator('.composer').getByText('Unsaved changes', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Your draft changed. Choose Preview plan')).toBeVisible();
  await page.getByRole('heading', { name: 'Front matter' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: '../docs/images/studio/composer-front-matter.png' });

  // Keyboard reorder keeps focus on the moved puzzle.
  await page.getByRole('button', { name: 'Move By the Harbour up' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Move By the Harbour up' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Move By the Harbour down' })).toBeFocused();
  const order = page.getByRole('list', { name: 'Puzzle publication order' });
  await expect(order.locator('strong')).toHaveText([
    'By the Harbour',
    'Along the Shoreline',
    'In the Rock Pool',
    'Over the Dunes',
  ]);
  // Solutions per page moved to Interior design; Book states it and links there.
  await expect(page.getByText(/2 solutions on each printed page/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Interior design' })).toHaveAttribute(
    'href',
    '/books/composer-demo/interior#answers',
  );
  await page.getByRole('radio', { name: /^Roman front matter/ }).check();
  await page.getByRole('radio', { name: /^Continuous/ }).check();
  await order.scrollIntoViewIfNeeded();
  await page.screenshot({ path: '../docs/images/studio/composer-order.png' });

  // Unsaved preview is authoritative, deterministic and read-only.
  const firstResponse = page.waitForResponse((r) => r.url().endsWith('/draft/plan'));
  await page.getByRole('button', { name: 'Preview plan' }).click();
  const first = (await (await firstResponse).json()) as PlanResult;
  await expect(page.getByRole('heading', { name: 'Unsaved draft plan' })).toBeVisible();
  const secondResponse = page.waitForResponse((r) => r.url().endsWith('/draft/plan'));
  await page.getByRole('button', { name: 'Preview plan' }).click();
  expect(await (await secondResponse).json()).toEqual(first);
  expect(first.plan.statistics.solution_pages).toBe(2);
  expect(first.plan.pages.filter((p) => p.puzzle).map((p) => p.puzzle!.id)).toEqual([
    'harbour',
    'shoreline',
    'rockpool',
    'dunes',
  ]);
  await expect(planRows(page).nth(4)).toHaveText('Puzzle 1: By the Harbour');
  expect((await (await request.get(api)).json()).revision).toBe(original.revision);
  await axe(page);
  await page.locator('#plan-preview').scrollIntoViewIfNeeded();
  await shot(page, 'composer-plan');

  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('status')).toHaveText(
    'Saved and reloaded from source. Publication plan refreshed.',
  );
  await page.reload();
  await expect(page.getByText('Plan independently verified')).toBeVisible();
  await expect(page.getByLabel('Copyright notice')).toHaveValue('Copyright 2026 Example Author.');
  await expect(order.locator('strong').first()).toHaveText('By the Harbour');
  await expect(planRows(page).nth(4)).toHaveText('Puzzle 1: By the Harbour');
  const saved = await (await request.get(api)).json();
  expect(saved.source.composition.solutions.per_page).toBe(2);
  expect(saved.source.composition.page_numbers.scheme).toBe('continuous');
  expect(saved.source.word_search.puzzles.map((p: { id: string }) => p.id)).toEqual([
    'harbour',
    'shoreline',
    'rockpool',
    'dunes',
  ]);

  // Python rejects an empty heading; the error is attached to the field.
  await page.getByLabel('Section heading').fill('');
  await page.getByRole('button', { name: 'Validate draft' }).click();
  await expect(page.getByLabel('Section heading')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByLabel('Section heading')).toHaveAccessibleDescription(/1\.\.200/);
  await axe(page);
  await page.getByLabel('Section heading').scrollIntoViewIfNeeded();
  await page.screenshot({ path: '../docs/images/studio/composer-validation.png' });

  // A competing save makes this draft stale; it is retained, never overwritten.
  await page.getByLabel('Section heading').fill('Answers');
  saved.source.book.title = 'Externally edited book';
  expect(
    (
      await request.post(`${api}/draft/save`, {
        data: { source: saved.source, revision: saved.revision },
      })
    ).status(),
  ).toBe(200);
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('alert')).toContainText('Saved source has changed');
  await expect(page.getByLabel('Section heading')).toHaveValue('Answers');
  const after = await (await request.get(api)).json();
  expect(after.source.composition.solutions.title).toBe('Solutions');
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Reload saved source' }).click();
  await expect(page.getByRole('status')).toHaveText(
    'Saved source reloaded. Publication plan refreshed.',
  );
  await expect(page.getByLabel('Section heading')).toHaveValue('Solutions');
  expect(errors).toEqual([]);
});

test('composer starts explicitly, stays usable by keyboard and at all widths', async ({ page }) => {
  await page.goto('/books/garden-demo/book');
  await expect(
    page.getByRole('heading', { name: 'This project has no book composition yet' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Start book composition' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Instructions heading')).toHaveValue('How to Play');
  await expect(
    page.locator('.composer').getByText('Unsaved changes', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Preview plan' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByText('Plan independently verified')).toBeVisible();
  await axe(page);
  await page.goto('/books/composition-demo/book');
  await expect(page.getByText('Plan independently verified')).toBeVisible();
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Move In the Rock Pool up' })).toBeVisible();
    await expect(page.getByRole('table', { name: 'Logical pages in reading order' })).toBeVisible();
    await shot(page, `composer-${width}`);
  }
  await axe(page);
});
