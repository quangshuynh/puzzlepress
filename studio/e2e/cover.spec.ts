import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';

const shot = (name: string) => `../docs/images/studio/${name}.png`;
const assets = '../books/cover-demo/cover-assets';
const photo = join(
  assets,
  readdirSync(assets).find((name) => name.endsWith('.jpg'))!,
);

async function noAxeViolations(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}

async function coverLoaded(page: Page) {
  const image = page.locator('.cover-window img');
  await expect(image).toBeVisible();
  await expect
    .poll(() =>
      image.evaluate(
        (i) => (i as HTMLImageElement).complete && (i as HTMLImageElement).naturalWidth > 0,
      ),
    )
    .toBe(true);
}

async function buildInterior(page: Page, key: string) {
  await page.goto(`/books/${key}/print`);
  const build = page.getByRole('button', { name: /Build interior|Rebuild interior/ });
  await expect(build).toBeEnabled();
  const response = page.waitForResponse((r) => r.url().endsWith('/interior/build'));
  await build.click();
  expect((await response).status()).toBe(200);
}

async function draftRendered(page: Page) {
  await page.waitForResponse((r) => r.url().endsWith('/draft/cover') && r.status() === 200);
  await coverLoaded(page);
}

test('import a photograph, crop by keyboard, save, reload and build a cover', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await buildInterior(page, 'cover-start');
  await page.goto('/books/cover-start/cover');
  await expect(
    page.getByRole('heading', { name: 'Start a cover from your photograph' }),
  ).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await noAxeViolations(page);
  await page.screenshot({ path: shot('cover-start'), fullPage: true });

  const rendered = draftRendered(page);
  await page.getByLabel('Import a photograph (JPEG or PNG)').setInputFiles(photo);
  await rendered;
  await expect(page.getByText(/Imported cover-assets\/.+\.jpg/)).toBeVisible();
  await expect(page.locator('.cover-studio .draft-status').first()).toHaveText('Unsaved changes');
  const readiness = page.getByRole('complementary', { name: 'Cover readiness' });
  await expect(readiness.getByText('0.0248 in', { exact: false })).toBeVisible();
  await expect(readiness.getByText(/Omitted: KDP prints spine text only/)).toBeVisible();
  await expect(readiness.getByText(/DPI · Sufficient/)).toBeVisible();

  // Keyboard-only crop: focus the preview, zoom twice and nudge right.
  const canvas = page.getByRole('group', { name: /Drag to move the photograph/ });
  await canvas.focus();
  for (const key of ['+', '+', 'ArrowRight', 'ArrowDown']) {
    const next = page.waitForResponse((r) => r.url().endsWith('/draft/cover'));
    await page.keyboard.press(key);
    await next;
  }
  await expect(page.getByLabel(/^Zoom/)).toHaveValue('1.1');
  await expect(page.getByLabel(/Focal point, left to right/)).toHaveValue('0.51');
  await expect(page.getByLabel(/Focal point, top to bottom/)).toHaveValue('0.51');
  await coverLoaded(page);
  await expect(readiness.getByText(/DPI · Too low: zoom out/)).toBeVisible();
  // Zoom back out with the keyboard so the photo prints at full resolution.
  for (const key of ['-', '-']) {
    const next = page.waitForResponse((r) => r.url().endsWith('/draft/cover'));
    await page.keyboard.press(key);
    await next;
  }
  await expect(page.getByLabel(/^Zoom/)).toHaveValue('1');
  await coverLoaded(page);
  await page.locator('.cover-main').screenshot({ path: shot('cover-wrap') });

  for (const name of ['Trim and folds', 'Bleed', 'KDP safe areas', 'Barcode area'])
    await page.getByRole('checkbox', { name: new RegExp(name) }).check();
  const overlay = page.getByTestId('cover-overlay');
  await expect(overlay.locator('.overlay-fold')).toHaveCount(2);
  await expect(overlay.locator('.overlay-barcode')).toHaveCount(1);
  await page.locator('.cover-canvas').screenshot({ path: shot('cover-overlays') });
  await page.getByRole('button', { name: 'Spine' }).click();
  await coverLoaded(page);
  await page.locator('.cover-canvas').screenshot({ path: shot('cover-spine') });
  await page.getByRole('button', { name: 'Front' }).click();
  await coverLoaded(page);
  await page.locator('.cover-studio').screenshot({ path: shot('cover-crop') });

  const saved = page.waitForResponse((r) => r.url().endsWith('/draft/save'));
  await page.getByRole('button', { name: 'Save changes' }).click();
  expect((await saved).status()).toBe(200);
  await expect(
    page.locator('.cover-studio').getByText('Saved and reloaded from source.'),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel(/Focal point, left to right/)).toHaveValue('0.51');
  await expect(page.getByLabel(/Focal point, top to bottom/)).toHaveValue('0.51');
  await expect(page.getByLabel(/^Zoom/)).toHaveValue('1');
  await expect(page.locator('input[name="cover-photo"]:checked')).toHaveCount(1);

  const built = page.waitForResponse((r) => r.url().endsWith('/cover/build'));
  await page.getByRole('button', { name: 'Build cover' }).click();
  expect((await built).status()).toBe(200);
  const verdict = page.getByLabel('Cover preflight status');
  await expect(verdict.getByText('Valid', { exact: true })).toBeVisible();
  await expect(verdict.getByText('Not ready', { exact: true })).toBeVisible();
  await expect(page.getByText(/The interior has 11 pages; KDP requires 24\./)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Built cover.pdf' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await coverLoaded(page);
  await noAxeViolations(page);
  await readiness.screenshot({ path: shot('cover-readiness') });
  expect(errors).toEqual([]);
});

test('dragging the photograph moves the focal point', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await buildInterior(page, 'cover-demo');
  await page.goto('/books/cover-demo/cover');
  await coverLoaded(page);
  await page.getByRole('radio', { name: /Front photograph/ }).check();
  await draftRendered(page);
  const before = Number(await page.getByLabel(/Focal point, left to right/).inputValue());
  const box = (await page.locator('.cover-window').boundingBox())!;
  const next = page.waitForResponse((r) => r.url().endsWith('/draft/cover'));
  await page.mouse.move(box.x + box.width * 0.75, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.75 + 120, box.y + box.height / 2, { steps: 6 });
  await page.mouse.up();
  await next;
  const after = Number(await page.getByLabel(/Focal point, left to right/).inputValue());
  expect(after).toBeLessThan(before);
});

test('cover demo is ready at desktop, tablet and phone widths', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await buildInterior(page, 'cover-demo');
  await page.goto('/books/cover-demo/cover');
  await coverLoaded(page);
  const build = page.waitForResponse((r) => r.url().endsWith('/cover/build'));
  await page.getByRole('button', { name: /Build cover|Rebuild cover/ }).click();
  expect((await build).status()).toBe(200);
  const verdict = page.getByLabel('Cover preflight status');
  await expect(verdict.getByText('Ready', { exact: true })).toBeVisible();
  for (const [name, width, height] of [
    ['1440', 1440, 1000],
    ['1024', 1024, 768],
    ['768', 768, 1024],
    ['390', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    await page.goto('/books/cover-demo/cover');
    await coverLoaded(page);
    await expect(page.getByLabel('Cover preflight status').getByText('Ready')).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBeTruthy();
    const stage = (await page.locator('.cover-window').boundingBox())!;
    expect(stage.width).toBeGreaterThan(Math.min(320, width * 0.8));
    expect(stage.x).toBeGreaterThanOrEqual(0);
    expect(stage.x + stage.width).toBeLessThanOrEqual(width);
    if (name === '1440') {
      await page.screenshot({ path: shot('cover'), fullPage: true });
      await page.screenshot({ path: shot('cover-1440') });
    }
    if (name === '390') {
      await noAxeViolations(page);
      await page.screenshot({ path: shot('cover-390'), fullPage: true });
    }
  }
});
