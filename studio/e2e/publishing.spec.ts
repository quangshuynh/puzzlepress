import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// The publishing demo leaves AI disclosure and every confirmation undecided. These
// tests make those choices through the UI on a disposable copy, as a person would;
// they are synthetic test decisions, never a real author's declarations.

const shot = (name: string) => `../docs/images/studio/${name}.png`;

async function noAxeViolations(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}

async function build(page: Page, key: string, profile?: string) {
  const detail = await (await page.request.get(`/api/projects/${key}`)).json();
  const interior = await page.request.post(`/api/projects/${key}/interior/build`, {
    data: { revision: detail.revision, ...(profile ? { profile } : {}) },
  });
  expect((await interior.json()).build.success).toBe(true);
  if (profile) return;
  const cover = await page.request.post(`/api/projects/${key}/cover/build`, {
    data: { revision: detail.revision },
  });
  expect((await cover.json()).build.success).toBe(true);
}

async function open(page: Page, key: string) {
  await page.goto(`/books/${key}/publishing`);
  await expect(page.getByRole('heading', { name: 'Readiness' })).toBeVisible();
  const front = page.locator('.front-window img');
  if (await front.count())
    await expect
      .poll(() =>
        front.evaluate(
          (i) => (i as HTMLImageElement).complete && (i as HTMLImageElement).naturalWidth > 0,
        ),
      )
      .toBe(true);
  await page.evaluate(() => document.fonts.ready);
}

const readiness = (page: Page) => page.getByRole('complementary', { name: 'Readiness' });

test('review what blocks, declare, confirm by keyboard, save and export', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await build(page, 'publishing-demo');
  await open(page, 'publishing-demo');
  const panel = readiness(page);
  await expect(panel.getByText('Interior current and KDP ready.')).toBeVisible();
  await expect(panel.getByText('Cover current and KDP ready.')).toBeVisible();
  await expect(panel.getByText('AI content disclosure is not yet declared.')).toBeVisible();
  await expect(panel.getByText('Your confirmations are incomplete.')).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Export package' })).toBeDisabled();
  await noAxeViolations(page);
  await page.screenshot({ path: shot('publishing'), fullPage: true });
  await page.locator('.publishing-findings').screenshot({ path: shot('publishing-blocking') });

  // Field-level Python findings: a quoted keyword is reported beside the field.
  const keywords = page.getByRole('group', { name: /^Keywords/ });
  await keywords.getByRole('button', { name: 'Add keyword' }).click();
  const checked = page.waitForResponse((r) => r.url().endsWith('/draft/publishing'));
  await page.getByRole('textbox', { name: 'Keywords 6', exact: true }).fill('"best" word search');
  await checked;
  await expect(keywords.getByText(/contains quotation marks/)).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Keywords 6', exact: true })).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  await page.locator('section[aria-labelledby="pub-discovery"]').screenshot({
    path: shot('publishing-metadata'),
  });
  await keywords.getByRole('button', { name: 'Remove keywords 6' }).click();

  // AI disclosure is the author's decision: nothing is preselected.
  for (const kind of ['Text', 'Images'])
    await page
      .getByRole('group', { name: new RegExp(`^${kind}`) })
      .getByRole('radio', { name: /Created by people/ })
      .check();
  await page
    .getByRole('group', { name: /^Translations/ })
    .getByRole('radio', { name: /Not a translation/ })
    .check();
  // Confirmations by keyboard.
  for (const name of [/hold the rights/, /AI content declaration/, /accurately represent/]) {
    const box = page.getByRole('checkbox', { name });
    await expect(box).not.toBeChecked();
    await box.focus();
    await page.keyboard.press('Space');
    await expect(box).toBeChecked();
  }
  await page.locator('section[aria-labelledby="pub-ai"]').screenshot({
    path: shot('publishing-disclosure'),
  });
  await expect(panel.getByRole('button', { name: 'Export package' })).toBeDisabled();
  await expect(panel.getByText(/Save the draft first/)).toBeVisible();

  const saved = page.waitForResponse((r) => r.url().endsWith('/draft/save'));
  await page.getByRole('button', { name: 'Save changes' }).click();
  expect((await saved).status()).toBe(200);
  await expect(panel.getByText('Package ready for manual KDP submission.')).toBeVisible();
  await expect(panel.locator('.publishing-statement')).toHaveText(
    /^Ready for manual KDP submission: the supported/,
  );
  await panel.screenshot({ path: shot('publishing-ready') });

  await panel.getByRole('checkbox', { name: /Also write/ }).check();
  const exported = page.waitForResponse((r) => r.url().endsWith('/publishing/export'));
  await panel.getByRole('button', { name: 'Export package' }).focus();
  await page.keyboard.press('Enter');
  expect((await exported).status()).toBe(200);
  await expect(panel.getByText('Package exported', { exact: true })).toBeVisible();
  await expect(panel.getByText(/Not submitted to Amazon/)).toBeVisible();
  await panel.getByText(/Package contents/).click();
  await panel.getByText('KDP upload checklist').click();
  await expect(panel.getByLabel('KDP upload checklist')).toContainText(
    'Nothing on this list has been done in KDP',
  );
  await noAxeViolations(page);
  await page.locator('.publishing-export').screenshot({ path: shot('publishing-export') });

  await page.reload();
  await expect(
    readiness(page).getByText('Package exported and current. Upload it in KDP yourself.'),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test('a paper change explains the stale cover and links to Cover', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await build(page, 'publishing-stale');
  await build(page, 'publishing-stale', 'paperback-8.5x11-cream');
  await open(page, 'publishing-stale');
  const panel = readiness(page);
  await expect(
    panel
      .getByText('Cover is out of date because the interior paper changed (white -> cream).')
      .first(),
  ).toBeVisible();
  await expect(panel.getByRole('link', { name: 'Rebuild in Cover' })).toHaveAttribute(
    'href',
    '/books/publishing-stale/cover',
  );
  await expect(page.getByLabel('Publishing verdicts').getByText('stale')).toBeVisible();
  await page.locator('.state-lines').screenshot({ path: shot('publishing-readiness') });
  await panel.getByRole('link', { name: 'Rebuild in Cover' }).click();
  await expect(page).toHaveURL(/\/books\/publishing-stale\/cover$/);
});

test('publishing workspace at desktop, tablet and phone widths', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await build(page, 'publishing-demo');
  for (const [name, width, height] of [
    ['1440', 1440, 1000],
    ['1024', 1024, 768],
    ['768', 768, 1024],
    ['390', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    await open(page, 'publishing-demo');
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBeTruthy();
    const aside = (await readiness(page).boundingBox())!;
    expect(aside.x).toBeGreaterThanOrEqual(0);
    expect(aside.x + aside.width).toBeLessThanOrEqual(width);
    if (name === '390') {
      await noAxeViolations(page);
      await page.screenshot({ path: shot('publishing-390'), fullPage: true });
    }
  }
});
