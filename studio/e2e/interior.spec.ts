import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Interior design on a disposable cover-demo copy (20 puzzles, 14 x 14 grids, two
// solutions a page as authored). Every preview and fit is Python's; these tests check
// the controls, persistence and that the real build follows the saved design.

const KEY = 'interior-demo';
const shot = (name: string) => `../docs/images/studio/${name}.png`;
const WIDTHS: [string, number, number][] = [
  ['1440', 1440, 1000],
  ['1024', 1024, 900],
  ['768', 768, 1000],
  ['390', 390, 844],
];

function draft(page: Page) {
  return page.waitForResponse((r) => r.url().endsWith('/draft/interior') && r.status() === 200);
}

async function previewReady(page: Page) {
  const image = page.locator('.preview-pages img').first();
  await expect(image).toBeVisible();
  await expect
    .poll(() =>
      image.evaluate(
        (i) => (i as HTMLImageElement).complete && (i as HTMLImageElement).naturalWidth > 0,
      ),
    )
    .toBe(true);
}

test.describe.configure({ mode: 'serial' });

test('answer layout, theme and page layout preview, save, reload and build', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/books/${KEY}/interior`);

  // Answer layout: Python measures each choice for these 14 x 14 grids.
  await page.getByRole('tab', { name: 'Answer layout' }).click();
  await expect(page.getByRole('radio', { name: /2 a page/ })).toBeChecked();
  await expect(page.locator('.answer-choice').filter({ hasText: '4 a page' })).toContainText(
    'Fits',
  );
  await expect(page.locator('.answer-choice').filter({ hasText: '8 a page' })).toContainText(
    'Too small',
  );
  let preview = draft(page);
  await page.getByRole('radio', { name: /4 a page \(default\)/ }).check();
  await preview;
  await expect(page.getByText(/^5 answer pages\./)).toBeVisible();
  await previewReady(page);
  await expect(page.getByRole('img', { name: /Draft answers/ })).toBeVisible();

  // Theme and page layout, previewed as a facing pair of puzzle pages.
  await page.getByRole('tab', { name: 'Theme' }).click();
  await page.getByRole('button', { name: 'Add an interior design' }).click();
  preview = draft(page);
  await page.getByRole('radio', { name: /Racing Orange/ }).check();
  await preview;
  await expect(page.getByText(/prints as 52% black/)).toBeVisible();
  await page.getByRole('tab', { name: 'Page layout' }).click();
  preview = draft(page);
  await page.getByRole('radio', { name: /Bold Header/ }).check();
  await preview;
  preview = draft(page);
  await page.getByLabel('Answer reference (optional)').fill('Solution on page {page}');
  await preview;
  await page.getByRole('button', { name: 'Puzzle spread' }).click();
  await previewReady(page);
  await expect(page.locator('.preview-pages.spread img')).toHaveCount(2);
  const note = page.getByRole('note', { name: 'What saving changes' });
  await expect(note).toContainText('rebuild it in');
  // Nothing is built yet, so no page count is compared (polish.spec covers that).
  await expect(note).not.toContainText('Changes the page count');
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: shot('interior-studio-1440') });

  // Validation feedback comes from Python, beside the field.
  await page.getByLabel('Answer reference (optional)').fill('Solution');
  await page.getByRole('button', { name: 'Validate' }).click();
  // Python's issue appears beside the field (and in the draft bar's summary).
  const field = page.locator('[id="interior.puzzle_pages.answer_reference-issues"]');
  await expect(field).toContainText('Write the text with {page} exactly once');
  preview = draft(page);
  await page.getByLabel('Answer reference (optional)').fill('Solution on page {page}');
  await preview;

  // Save, reload: the design is in book.yaml.
  const saved = page.waitForResponse((r) => r.url().endsWith('/draft/save'));
  await page.getByRole('button', { name: 'Save changes' }).click();
  expect((await saved).status()).toBe(200);
  await page.reload();
  await page.getByRole('tab', { name: 'Theme' }).click();
  await expect(page.getByRole('radio', { name: /Racing Orange/ })).toBeChecked();
  await page.getByRole('tab', { name: 'Answer layout' }).click();
  await expect(page.getByRole('radio', { name: /4 a page \(default\)/ })).toBeChecked();
  await previewReady(page);
  await expect(page.locator('.answer-choice').first()).toContainText('Fits');

  for (const [name, width, height] of WIDTHS) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    if (name === '390') {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: shot(`interior-studio-${name}`), fullPage: true });
    }
  }

  // The real build follows the saved design: four solutions a page, racing banners.
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/books/${KEY}/print`);
  const built = page.waitForResponse((r) => r.url().endsWith('/interior/build'));
  await page.getByRole('button', { name: /Build interior|Rebuild interior/ }).click();
  expect((await built).status()).toBe(200);
  await expect(page.getByText('Interior built and preflight complete.')).toBeVisible();
  const status = await page.request.get(`/api/projects/${KEY}/interior`);
  const body = await status.json();
  expect(body.state).toBe('current');
  expect(errors).toEqual([]);
});

test('a design file exported here imports into the draft without saving', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/books/${KEY}/interior`);
  await page.getByRole('tab', { name: 'Theme' }).click();
  await page.getByLabel('Design name').fill('Automotive Racing');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export design' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('automotive-racing.puzzlepress-design.json');
  const path = await file.path();
  // Change the draft, then import the saved design back.
  await page.getByRole('radio', { name: /Ink Saver/ }).check();
  await page.getByLabel('Design file to import').setInputFiles(path);
  await expect(page.getByText(/Applied “Automotive Racing” to the draft/)).toBeVisible();
  await expect(page.getByRole('radio', { name: /Racing Orange/ })).toBeChecked();
  // The imported design equals the saved one, so the draft is clean again.
  await expect(page.getByRole('button', { name: 'Revert draft' })).toBeDisabled();
});
