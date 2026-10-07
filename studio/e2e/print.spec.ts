import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const shot = (name: string) => `../docs/images/studio/${name}.png`;

async function noAxeViolations(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}

async function imagesLoaded(page: Page, selector: string) {
  await expect
    .poll(() =>
      page
        .locator(selector)
        .evaluateAll((images) =>
          images.every(
            (i) => (i as HTMLImageElement).complete && (i as HTMLImageElement).naturalWidth > 0,
          ),
        ),
    )
    .toBe(true);
}

test('build, preflight and proof the real composition demo interior', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/books/print-demo/print');
  await expect(page.getByRole('heading', { name: 'No interior has been built.' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await noAxeViolations(page);

  const built = page.waitForResponse((r) => r.url().endsWith('/interior/build'));
  await page.getByRole('button', { name: 'Build interior' }).click();
  expect((await built).status()).toBe(200);
  const verdict = page.getByLabel('Preflight status');
  await expect(verdict.getByText('Valid', { exact: true })).toBeVisible();
  await expect(verdict.getByText('Not ready', { exact: true })).toBeVisible();
  const findings = page.getByRole('region', { name: 'Preflight findings' });
  await expect(
    findings.getByText('11 pages. The supported KDP paperback minimum is 24 pages.'),
  ).toBeVisible();
  await expect(page.getByText('Interior built and preflight complete.')).toBeVisible();
  const thumbs = page.getByRole('navigation', { name: 'Pages' }).locator('img');
  await expect(thumbs).toHaveCount(11);
  await imagesLoaded(page, '.sheet img');
  await noAxeViolations(page);
  await page.screenshot({ path: shot('print'), fullPage: true });
  await verdict.screenshot({ path: shot('print-kdp-not-ready') });
  await findings.screenshot({ path: shot('print-findings') });

  // Keyboard: four pages forward from the title page reaches the first puzzle (recto).
  await page.locator('.print-canvas').focus();
  for (let i = 0; i < 4; i++) await page.keyboard.press('ArrowRight');
  await expect(page.locator('.print-current')).toHaveText(
    'Page 5 · Recto (right) · Puzzle · number 1 printed of 11',
  );
  const puzzle = page.getByRole('img', { name: /Rendered Page 5/ });
  await expect(puzzle).toHaveAttribute('src', /\/pages\/5\?size=page&pdf=[0-9a-f]{64}$/);
  await imagesLoaded(page, '.sheet img');
  await page.locator('.print-stage').screenshot({ path: shot('print-puzzle') });

  // The blank and a solution page are real pages in the same sequence.
  await page.keyboard.press('ArrowLeft');
  await expect(page.locator('.print-current')).toHaveText(
    'Page 4 · Verso (left) · Intentional blank of 11',
  );
  const jump = page.getByLabel('Page', { exact: true });
  await jump.fill('9');
  await jump.press('Enter');
  await expect(page.locator('.print-current')).toContainText('Page 9 · Recto (right) · Solutions');
  await imagesLoaded(page, '.sheet img');

  // Overlays come from the layout's boxes, drawn over the raster only.
  await jump.fill('6');
  await jump.press('Enter');
  await page.getByRole('checkbox', { name: /Live area/ }).check();
  await page.getByRole('checkbox', { name: /KDP minimum margins/ }).check();
  const live = page.getByTestId('overlay-6').locator('.overlay-live');
  await expect(live).toHaveAttribute('x', '36');
  await expect(live).toHaveAttribute('width', '522');
  await imagesLoaded(page, '.sheet img');
  await page.locator('.print-stage').screenshot({ path: shot('print-overlays') });

  // Spread: verso on the left, recto on the right.
  await page.getByRole('button', { name: 'Spread' }).click();
  await page
    .getByRole('navigation', { name: 'Pages' })
    .getByRole('button', { name: /^Page 9 ·/ })
    .click();
  await expect(page.locator('.print-current')).toHaveText('Spread: pages 8 and 9 of 11');
  await expect(page.locator('.sheet figcaption strong')).toHaveText([
    'Page 8 · Verso (left) · Puzzle · number 4 printed',
    'Page 9 · Recto (right) · Solutions · number 5 printed',
  ]);
  await imagesLoaded(page, '.sheet img');
  await page.locator('.print-stage').screenshot({ path: shot('print-spread') });
  await page.locator('.print-canvas').focus();
  await page.keyboard.press('Home');
  await expect(page.locator('.print-current')).toHaveText(
    'Spread: page 1 of 11 alone (first page is a recto)',
  );
  await noAxeViolations(page);

  // A real raster at detail zoom.
  await page.getByRole('button', { name: 'Single page' }).click();
  await page.getByLabel('Zoom level').selectOption('300');
  await expect(page.locator('.sheet img')).toHaveAttribute('src', /size=detail/);
  await imagesLoaded(page, '.sheet img');
  expect(
    await page.locator('.sheet img').evaluate((i) => (i as HTMLImageElement).naturalWidth),
  ).toBe(2448);
  expect(errors).toEqual([]);
});

test('print workspace stays usable at laptop, tablet and phone widths', async ({ page }) => {
  for (const [name, width, height] of [
    ['1440', 1440, 1000],
    ['1024', 1024, 768],
    ['768', 768, 1024],
    ['390', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    await page.goto('/books/print-demo/print');
    const build = page.getByRole('button', { name: 'Build interior' });
    const verdict = page.getByLabel('Preflight status');
    await expect(build.or(verdict).first()).toBeVisible();
    if (await build.isVisible()) await build.click();
    await expect(verdict).toBeVisible();
    await imagesLoaded(page, '.sheet img');
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBeTruthy();
    await expect(page.getByRole('button', { name: 'Next page' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Preflight findings' })).toBeAttached();
    const sheet = await page.locator('.sheet').boundingBox();
    expect(sheet!.width).toBeGreaterThan(Math.min(260, width * 0.6));
    if (name === '390') {
      await noAxeViolations(page);
      await page.screenshot({ path: shot('print-390'), fullPage: true });
    }
  }
});
