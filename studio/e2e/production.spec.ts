import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import type { Generation } from '../src/types';

// The 60-puzzle automotive production book, served from a temporary copy
// (automotive-production). Builds write only inside that temporary directory.
const key = 'automotive-production';
const shot = (name: string) => `../docs/images/studio/${name}.png`;
const originals = ['book.yaml', 'planning.yaml'].map((name) => ({
  name,
  bytes: readFileSync(`../books/automotive/${name}`),
}));
test.afterAll(() => {
  for (const { name, bytes } of originals)
    expect(readFileSync(`../books/automotive/${name}`)).toEqual(bytes);
});

async function noAxeViolations(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}

async function imagesLoaded(page: Page, selector: string) {
  // Rasters come from PDFium one at a time; a full suite run queues them.
  await expect
    .poll(
      () =>
        page
          .locator(selector)
          .evaluateAll((images) =>
            images.every(
              (i) => (i as HTMLImageElement).complete && (i as HTMLImageElement).naturalWidth > 0,
            ),
          ),
      { timeout: 30_000 },
    )
    .toBe(true);
}

/** Wall time of one step, printed for the interval's performance record. */
async function timed<T>(label: string, step: () => Promise<T>): Promise<T> {
  const start = Date.now();
  const value = await step();
  console.log(`studio timing: ${label}: ${Date.now() - start} ms`);
  return value;
}

test('open, review, compose, print and check the 60-puzzle production book', async ({ page }) => {
  test.setTimeout(180_000);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });

  // Opening the project lists every definition in source order.
  await timed('open project overview', async () => {
    await page.goto(`/books/${key}`);
    await expect(page.getByText('60 in source order')).toBeVisible();
  });
  await page.evaluate(() => document.fonts.ready);
  await noAxeViolations(page);

  // Generation of all 60 puzzles, then the hardest puzzle in the inspector.
  const generated = page.waitForResponse((r) => r.url().endsWith('/generation'));
  const generation = await timed('generate and review 60 puzzles', async () => {
    await page.getByRole('link', { name: 'Generate & review puzzles' }).click();
    const response = await generated;
    expect(response.status()).toBe(200);
    return (await response.json()) as Generation;
  });
  expect(generation.report.success).toBe(true);
  expect(generation.report.clean).toBe(true);
  expect(generation.report.puzzles).toHaveLength(60);
  const last = generation.report.puzzles.find((p) => p.id === 'engines-10')!;
  await page.getByRole('link', { name: last.title, exact: true }).click();
  const grid = page.getByRole('table');
  await expect(grid).toBeVisible();
  expect((await grid.getByRole('cell').allTextContents()).join('')).toBe(
    last.puzzle!.grid.join(''),
  );
  await expect(page.getByText('Independently verified')).toBeVisible();
  await noAxeViolations(page);
  await page.screenshot({ path: shot('production-puzzle'), fullPage: true });

  // Quality: the configured checks, including screening, find nothing.
  await timed('quality view', async () => {
    await page.goto(`/books/${key}/quality`);
    await expect(page.getByText('The configured checks found nothing to flag.')).toBeVisible();
  });
  await expect(page.getByText(/^Screening policy: /)).toBeVisible();

  // Composition: the verified plan of 95 logical pages.
  await timed('composition plan', async () => {
    await page.goto(`/books/${key}/book`);
    await expect(page.getByText('Plan independently verified')).toBeVisible({ timeout: 30_000 });
  });
  await expect(page.locator('.plan-table tbody tr:not(.plan-section)')).toHaveCount(95);
  await noAxeViolations(page);

  // Print: build the real interior, preflight it and proof pages.
  await page.goto(`/books/${key}/print`);
  await expect(page.getByRole('heading', { name: 'No interior has been built.' })).toBeVisible();
  const built = page.waitForResponse((r) => r.url().endsWith('/interior/build'));
  await timed('build interior and preflight', async () => {
    await page.getByRole('button', { name: 'Build interior' }).click();
    expect((await built).status()).toBe(200);
    await expect(page.getByText('Interior built and preflight complete.')).toBeVisible();
  });
  const verdict = page.getByLabel('Preflight status');
  await expect(verdict.getByText('Valid', { exact: true })).toBeVisible();
  await expect(verdict.getByText('Ready', { exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Pages' }).locator('img')).toHaveCount(95);
  await page.locator('.print-canvas').focus();
  for (let i = 0; i < 4; i++) await page.keyboard.press('ArrowRight');
  await expect(page.locator('.print-current')).toHaveText(
    'Page 5 · Recto (right) · Puzzle · number 1 printed of 95',
  );
  const jump = page.getByLabel('Page', { exact: true });
  await jump.fill('65');
  await jump.press('Enter');
  await expect(page.locator('.print-current')).toContainText('Page 65 · Recto (right) · Solutions');
  await imagesLoaded(page, '.sheet img');
  await noAxeViolations(page);
  await page.screenshot({ path: shot('production-print'), fullPage: true });

  // Cover: no photograph has been supplied, so the cover waits for one.
  await page.goto(`/books/${key}/cover`);
  await expect(
    page.getByRole('heading', { name: 'Start a cover from your photograph' }),
  ).toBeVisible();
  await expect(page.getByText('No photographs in this project yet.')).toBeVisible();
  await noAxeViolations(page);

  // Publishing: the interior is current; everything only the author can decide blocks.
  await timed('publishing readiness', async () => {
    await page.goto(`/books/${key}/publishing`);
    await expect(page.getByRole('heading', { name: 'Readiness' })).toBeVisible({
      timeout: 60_000,
    });
  });
  const readiness = page.locator('#publishing-readiness');
  await expect(readiness.getByText('Interior current and KDP ready.')).toBeVisible();
  await expect(readiness.getByText('No cover is designed. Open Cover.')).toBeVisible();
  await expect(readiness.getByText('AI content disclosure is not yet declared.')).toBeVisible();
  await expect(readiness.getByText('Your confirmations are incomplete.')).toBeVisible();
  await expect(readiness.getByRole('button', { name: 'Export package' })).toBeDisabled();
  await noAxeViolations(page);
  await page.screenshot({ path: shot('production-publishing'), fullPage: true });

  // Planning: the plan is complete but not approved; comparables are still open.
  await timed('planning view', async () => {
    await page.goto(`/books/${key}/planning`);
    await expect(page.getByText(/^Needs research: blocking questions/)).toBeVisible();
  });
  await expect(page.getByText(/Within the project cap of 100 puzzles/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approve this plan' })).toBeDisabled();
  await noAxeViolations(page);

  expect(errors).toEqual([]);
});
