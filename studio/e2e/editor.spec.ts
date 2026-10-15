import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';

const originals = ['garden-demo', 'composition-demo'].map((key) => ({
  key,
  bytes: readFileSync(`../books/${key}/book.yaml`),
}));
test.afterAll(() => {
  for (const { key, bytes } of originals)
    expect(readFileSync(`../books/${key}/book.yaml`)).toEqual(bytes);
});

test('real draft edit, validation, deterministic preview, quality, save, reload and conflicts', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const api = '/api/projects/editor-demo';
  const original = await (await request.get(api)).json();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/books/editor-demo/edit');
  await expect(page.getByLabel('Puzzle title', { exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: '../docs/images/studio/editor.png', fullPage: true });
  await page.getByLabel('Puzzle title', { exact: true }).fill('Flowers for a quiet morning');
  await page.getByLabel('Word 1', { exact: true }).fill('ASTER');
  await expect(page.getByText('Unsaved changes', { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: '../docs/images/studio/word-editing.png', fullPage: true });
  await page.getByRole('button', { name: 'Validate draft' }).click();
  await expect(page.getByRole('status')).toHaveText(
    'Draft is valid. Python accepted the proposed project.',
  );
  const previewResponse = page.waitForResponse((r) => r.url().endsWith('/draft/preview'));
  await page.getByRole('button', { name: 'Preview draft' }).click();
  const first = await (await previewResponse).json();
  await expect(page.getByRole('table')).toBeVisible();
  const secondResponse = page.waitForResponse((r) => r.url().endsWith('/draft/preview'));
  await page.getByRole('button', { name: 'Preview draft' }).click();
  expect(await (await secondResponse).json()).toEqual(first);
  await page.getByRole('button', { name: 'Show solution' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Hide solution' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: '../docs/images/studio/draft-preview.png', fullPage: true });
  expect((await (await request.get(api)).json()).revision).toBe(original.revision);
  await page.getByText('Quality policy · shared across the book', { exact: true }).click();
  await page.getByLabel('Prohibited words (one per line)').fill('ASTER');
  await page.getByRole('button', { name: 'Preview draft' }).click();
  await expect(page.getByRole('status')).toHaveText('Draft preview ready. Source has not changed.');
  await page.getByRole('button', { name: 'Whole-book quality' }).click();
  await expect(page.getByText('Review findings', { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: '../docs/images/studio/editor-quality.png', fullPage: true });
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('status')).toHaveText('Saved and reloaded from source.');
  await page.reload();
  await expect(page.getByLabel('Puzzle title', { exact: true })).toHaveValue(
    'Flowers for a quiet morning',
  );
  const saved = await (await request.get(api)).json();
  expect(saved.source.word_search.banks[0].entries[0].display).toBe('ASTER');
  await page.getByLabel('Puzzle title', { exact: true }).fill('My retained draft');
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
  await expect(page.getByLabel('Puzzle title', { exact: true })).toHaveValue('My retained draft');
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: '../docs/images/studio/editor-conflict.png', fullPage: true });
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Reload saved source' }).click();
  await expect(page.getByRole('status')).toHaveText('Saved source reloaded.');
  await page.getByLabel('Puzzle title', { exact: true }).fill('Retain on failed save');
  await page.route('**/draft/save', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        error: {
          code: 'save_failed',
          message: 'Save failed. Source was not replaced.',
          issues: [],
        },
      }),
    }),
  );
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('alert')).toContainText('Save failed');
  await expect(page.getByLabel('Puzzle title', { exact: true })).toHaveValue(
    'Retain on failed save',
  );
  await page.unroute('**/draft/save');
  await page.getByLabel('Puzzle title', { exact: true }).fill('');
  await page.getByRole('button', { name: 'Validate draft' }).click();
  await expect(page.getByLabel('Puzzle title', { exact: true })).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: '../docs/images/studio/editor-validation.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('editor is keyboard operable and responsive at all requested widths', async ({ page }) => {
  await page.goto('/books/garden-demo/edit');
  await expect(page.getByLabel('Puzzle title', { exact: true })).toBeVisible();
  // Select the second puzzle from the navigator, then move it, all by keyboard.
  await page.getByRole('button', { name: /^2. The Herb Garden/ }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Move puzzle 2 up' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Puzzle title', { exact: true })).toHaveValue('The Herb Garden');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: 'Remove puzzle' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Puzzle title', { exact: true })).toHaveValue('The Herb Garden');
  await page.getByRole('button', { name: 'Preview draft' }).click();
  await expect(page.getByRole('table')).toBeVisible();
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible();
    await expect(page.getByLabel('Puzzle title', { exact: true })).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `../docs/images/studio/editor-${width}.png`, fullPage: true });
  }
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
