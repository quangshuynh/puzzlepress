import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import type { Generation } from '../src/types';

test('real library to both solutions, quality, refresh, keyboard and screenshots', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/books');
  await expect(page.getByRole('link', { name: 'Garden Word Searches', exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await expect(page.getByRole('link', { name: 'Skip to content' })).toHaveCSS(
    'outline-style',
    'solid',
  );
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  await page.screenshot({ path: '../docs/images/studio/library.png', fullPage: true });
  await page.getByRole('link', { name: 'Garden Word Searches', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'The source at a glance' })).toBeVisible();
  await page.screenshot({ path: '../docs/images/studio/project.png', fullPage: true });
  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/generation'),
  );
  await page.getByRole('link', { name: 'Generate & review puzzles' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const generation = (await response.json()) as Generation;
  for (const id of ['flowers', 'herbs']) {
    const result = generation.report.puzzles.find((p) => p.id === id)!;
    await page.getByRole('link', { name: result.title, exact: true }).click();
    const table = page.getByRole('table');
    await expect(table).toBeVisible();
    expect((await table.getByRole('cell').allTextContents()).join('')).toBe(
      result.puzzle!.grid.join(''),
    );
    await expect(page.getByText('Independently verified')).toBeVisible();
    if (id === 'flowers')
      await page.screenshot({ path: '../docs/images/studio/puzzle.png', fullPage: true });
    const toggle = page.getByRole('button', { name: 'Show solution' });
    await toggle.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Hide solution' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    const actual = await table
      .locator('.solution-cell')
      .evaluateAll((cells) =>
        cells.map((c) => `${(c as HTMLElement).dataset.x},${(c as HTMLElement).dataset.y}`).sort(),
      );
    const expected = [
      ...new Set(
        Object.values(generation.solution_cells[id])
          .flat()
          .map((c) => `${c.x},${c.y}`),
      ),
    ].sort();
    expect(actual).toEqual(expected);
    await expect(page.getByRole('heading', { name: 'Solution register' })).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    if (id === 'flowers')
      await page.screenshot({ path: '../docs/images/studio/solution.png', fullPage: true });
    await page.getByRole('link', { name: 'All puzzles' }).click();
  }
  await page.getByRole('link', { name: 'Quality', exact: true }).click();
  await expect(
    page.getByText('Prohibited-word screening is disabled. No policy words are configured.'),
  ).toBeVisible();
  await expect(page.getByText('No target words are shared between definitions.')).toBeVisible();
  await page.goto('/books/garden-demo/puzzles/herbs');
  await page.reload();
  await expect(page.getByRole('table')).toBeVisible();
  expect(errors).toEqual([]);
});

test('desktop, laptop, tablet and phone retain readable grids without page overflow', async ({
  page,
}) => {
  for (const [name, width, height] of [
    ['desktop', 1440, 1000],
    ['laptop', 1024, 768],
    ['tablet', 768, 1024],
    ['mobile', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    for (const path of ['/books', '/books/garden-demo', '/books/garden-demo/puzzles/herbs']) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      if (path.includes('herbs')) {
        await expect(page.getByRole('table')).toBeVisible();
        await page.getByRole('button', { name: 'Show solution' }).click();
        const size = await page
          .locator('.letter-grid td')
          .first()
          .evaluate((cell) => parseFloat(getComputedStyle(cell).fontSize));
        expect(size).toBeGreaterThanOrEqual(15);
        await page.screenshot({ path: `../docs/images/studio/${name}.png`, fullPage: true });
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBeTruthy();
    }
  }
});

test('real missing-project API error offers recovery', async ({ page }) => {
  await page.goto('/books/missing');
  await expect(page.getByRole('alert')).toContainText('Project not found');
  await page.getByRole('link', { name: 'Return to books' }).click();
  await expect(page.getByRole('heading', { name: 'Your books' })).toBeVisible();
  await expect(page.getByRole('main')).toBeFocused();
});
