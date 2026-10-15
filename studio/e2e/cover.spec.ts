import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const shot = (name: string) => `../docs/images/studio/${name}.png`;
const assets = '../books/cover-demo/cover-assets';
const photo = join(
  assets,
  readdirSync(assets).find((name) => name.endsWith('.jpg'))!,
);
// A bundled SIL OFL font stands in for a font the author imports.
const fontFile = '../src/puzzlepress/cover/fonts/Newsreader16pt-Italic.ttf';

// The same font with OS/2 fsType 0x0002 (restricted license embedding).
function restrictedFont(): Buffer {
  const data = Buffer.from(readFileSync(fontFile));
  const tables = data.readUInt16BE(4);
  for (let i = 0; i < tables; i++) {
    const record = 12 + 16 * i;
    if (data.toString('latin1', record, record + 4) === 'OS/2') {
      data.writeUInt16BE(0x0002, data.readUInt32BE(record + 8) + 8);
      return data;
    }
  }
  throw new Error('No OS/2 table');
}

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

function nextDraft(page: Page) {
  return page.waitForResponse((r) => r.url().endsWith('/draft/cover') && r.status() === 200);
}

async function draftRendered(page: Page) {
  await nextDraft(page);
  await coverLoaded(page);
}

async function openCover(page: Page, key: string) {
  const first = nextDraft(page);
  await page.goto(`/books/${key}/cover`);
  await first;
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
  await expect(page.locator('.cover-studio .draft-status').first()).toContainText(
    'Unsaved changes',
  );
  const quality = page.getByRole('region', { name: 'Print quality' });
  await expect(quality.getByText(/Meets the 300 DPI KDP minimum/)).toBeVisible();

  // Keyboard-only crop: select the photograph, focus the canvas, zoom and nudge.
  await page.getByRole('button', { name: /^Photo \d+ DPI/ }).click();
  const canvas = page.getByRole('group', { name: /Photograph selected/ });
  await canvas.focus();
  for (const key of ['+', '+', 'ArrowRight', 'ArrowDown']) {
    const next = nextDraft(page);
    await page.keyboard.press(key);
    await next;
  }
  await expect(page.getByLabel(/^Zoom$/)).toHaveValue('1.1');
  await expect(page.getByLabel(/Focal point, left to right/)).toHaveValue('0.51');
  await expect(page.getByLabel(/Focal point, top to bottom/)).toHaveValue('0.51');
  await coverLoaded(page);
  // Zooming in uses fewer pixels: the DPI falls below the minimum and says so.
  await expect(quality.getByText(/Below the 300 DPI KDP minimum/)).toBeVisible();
  await expect(quality.getByText(/Zoom out to reach 300 DPI/)).toBeVisible();
  await page.locator('.cover-inspector').screenshot({ path: shot('cover-print-quality') });
  for (const key of ['-', '-']) {
    const next = nextDraft(page);
    await page.keyboard.press(key);
    await next;
  }
  await expect(page.getByLabel(/^Zoom$/)).toHaveValue('1');
  await coverLoaded(page);
  await page.locator('.cover-stage').screenshot({ path: shot('cover-wrap') });

  await page.getByText('Overlays', { exact: true }).click();
  for (const name of ['Trim and folds', 'Bleed', 'KDP safe areas', 'Barcode area'])
    await page.getByRole('checkbox', { name: new RegExp(name) }).check();
  await page.getByText('Overlays (4)').click();
  const overlay = page.getByTestId('cover-overlay');
  await expect(overlay.locator('.overlay-fold')).toHaveCount(2);
  await expect(overlay.locator('.overlay-barcode')).toHaveCount(1);
  await page.locator('.cover-canvas').screenshot({ path: shot('cover-overlays') });
  await page.getByRole('button', { name: 'Spine', exact: true }).click();
  await coverLoaded(page);
  await page.locator('.cover-canvas').screenshot({ path: shot('cover-spine') });
  await page.getByRole('button', { name: 'Front', exact: true }).click();
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
  await expect(page.getByLabel(/^Zoom$/)).toHaveValue('1');
  await expect(page.locator('.photo-grid li.current')).toHaveCount(1);

  await page.getByRole('tab', { name: /Checks/ }).click();
  const readiness = page.getByRole('complementary', { name: 'Cover readiness' });
  await expect(readiness.getByText('0.0248 in', { exact: false })).toBeVisible();
  await expect(readiness.getByText(/Omitted: KDP prints spine text only/)).toBeVisible();
  const built = page.waitForResponse((r) => r.url().endsWith('/cover/build'));
  await page.getByRole('button', { name: 'Build cover' }).click();
  expect((await built).status()).toBe(200);
  const verdict = page.getByLabel('Cover preflight status');
  await expect(verdict.getByText('Valid', { exact: true })).toBeVisible();
  await expect(verdict.getByText('Not ready', { exact: true })).toBeVisible();
  await expect(page.getByText(/The interior has 11 pages; KDP requires 24\./)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Built PDF' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await coverLoaded(page);
  await noAxeViolations(page);
  await page.locator('.cover-inspector').screenshot({ path: shot('cover-readiness') });
  expect(errors).toEqual([]);
});

test('text layers: select, drag at two zoom levels, nudge, hide and keep the book title', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await buildInterior(page, 'cover-demo');
  await openCover(page, 'cover-demo');
  const title = await page.evaluate(async () => {
    const response = await fetch('/api/projects/cover-demo');
    return ((await response.json()) as { source: { book: { title: string } } }).source.book.title;
  });

  // Record what each draft request sends.
  const sent: { cover: { text?: Record<string, { offset?: { x: number; y: number } }> } }[] = [];
  page.on('request', (request) => {
    if (request.url().endsWith('/draft/cover'))
      sent.push((request.postDataJSON() as { source: (typeof sent)[number] }).source);
  });

  for (const zoom of ['Fit', '200%']) {
    if (zoom === '200%') {
      await page.getByRole('button', { name: 'Zoom in' }).click();
      await page.getByRole('button', { name: 'Zoom in' }).click();
      await expect(page.getByRole('button', { name: '200%' })).toBeVisible();
      await page.getByRole('button', { name: 'Front', exact: true }).click();
      await coverLoaded(page);
    }
    const hit = page.locator('rect.layer-hit[data-layer="author"]');
    await hit.scrollIntoViewIfNeeded();
    const box = (await hit.boundingBox())!;
    // Screen pixels per PDF point at this zoom, from the SVG that maps Python's points.
    const pxPerPt = await page.evaluate(() => {
      const svg = document.querySelector('.cover-overlay') as SVGSVGElement;
      return svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
    });
    const before = sent.length;
    const response = nextDraft(page);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 - 60, { steps: 8 });
    await page.mouse.up();
    await response;
    await coverLoaded(page);
    expect(sent.length).toBeGreaterThan(before);
    const offset = sent.at(-1)!.cover.text!.author.offset!;
    // 60 screen pixels upward is 60 / (px per point) points up, at every zoom.
    expect(offset.x).toBe(0);
    expect(Math.abs(offset.y - 60 / pxPerPt)).toBeLessThan(0.6);
    // Python laid the author out at its new offset: its measured box moved exactly.
    const after = (await page.locator('rect.layer-hit[data-layer="author"]').boundingBox())!;
    expect(Math.abs(box.y - after.y - offset.y * pxPerPt)).toBeLessThan(1.5);
    await page.getByRole('button', { name: 'Reset position' }).click();
    await nextDraft(page);
  }
  while (await page.getByRole('button', { name: 'Zoom out' }).isEnabled())
    await page.getByRole('button', { name: 'Zoom out' }).click();
  await page.getByRole('button', { name: 'Full wrap', exact: true }).click();

  // Keyboard: select the title from the layer list and nudge it in points.
  await page.getByRole('tab', { name: 'Text' }).click();
  await page.getByRole('button', { name: /^Title/ }).click();
  const canvas = page.getByRole('group', { name: /Title selected/ });
  await canvas.focus();
  const nudged = nextDraft(page);
  await page.keyboard.press('Shift+ArrowDown');
  await nudged;
  expect(sent.at(-1)!.cover.text!.title.offset).toEqual({ x: 0, y: -10 });
  await expect(page.getByLabel('Up (+) / down')).toHaveValue('-10');
  const undone = nextDraft(page);
  await page.getByRole('button', { name: 'Undo' }).click();
  await undone;
  expect(sent.at(-1)!.cover.text).toBeUndefined();

  // Hide the title on the cover; the book's title is unchanged after saving.
  const hidden = nextDraft(page);
  await page
    .getByRole('list', { name: 'Cover text layers' })
    .getByRole('button', { name: 'Hide title on the cover' })
    .click();
  await hidden;
  await coverLoaded(page);
  await expect(page.locator('rect.layer-hit[data-layer="title"]')).toHaveCount(0);
  await page.getByRole('tab', { name: /Checks/ }).click();
  await expect(page.getByText(/The cover does not print the title/)).toBeVisible();
  await page.locator('.cover-studio').screenshot({ path: shot('cover-layers') });
  const saved = page.waitForResponse((r) => r.url().endsWith('/draft/save'));
  await page.getByRole('button', { name: 'Save changes' }).click();
  expect((await saved).status()).toBe(200);
  const after = await page.evaluate(async () => {
    const response = await fetch('/api/projects/cover-demo');
    return (await response.json()) as {
      source: { book: { title: string }; cover: { version: number; text: object } };
    };
  });
  expect(after.source.book.title).toBe(title);
  expect(after.source.cover.version).toBe(2);
  expect(after.source.cover.text).toEqual({ title: { visible: false } });
  await noAxeViolations(page);
});

test('an imported font previews, embeds through Python and restricted fonts are refused', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await buildInterior(page, 'cover-demo');
  await openCover(page, 'cover-demo');
  await page.getByRole('tab', { name: 'Fonts' }).click();
  const input = page.getByLabel('Import a font (.ttf or .otf)');
  await input.setInputFiles({
    name: 'Locked.ttf',
    mimeType: 'font/ttf',
    buffer: restrictedFont(),
  });
  await expect(page.getByText(/license flags forbid embedding/)).toBeVisible();
  await input.setInputFiles(fontFile);
  await expect(page.getByText(/Imported Newsreader 16pt Italic/)).toBeVisible();
  const specimen = page.getByRole('img', { name: /Specimen of Newsreader 16pt Italic/ });
  await expect
    .poll(() => specimen.evaluate((i) => (i as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  const added = nextDraft(page);
  await page.getByRole('button', { name: 'Add to cover' }).click();
  await added;
  await page.getByLabel('License').fill('SIL Open Font License 1.1');
  await page.getByLabel('Source').fill('Bundled PuzzlePress test font');
  await page.getByRole('tab', { name: 'Text' }).click();
  await page.getByRole('button', { name: /^Subtitle/ }).click();
  const styled = page.waitForResponse(
    (r) => r.url().endsWith('/draft/cover') && r.request().postData()!.includes('"subtitle"'),
  );
  await page.getByLabel('Font').selectOption({ label: 'Newsreader 16pt Italic (imported)' });
  const body = await (await styled).json();
  const subtitle = (body.layout.texts as { layer: string; face: string }[]).filter(
    (t) => t.layer === 'subtitle',
  );
  expect(subtitle.length).toBeGreaterThan(0);
  expect(subtitle.every((t) => t.face.startsWith('PuzzlePressFont-'))).toBe(true);
  await coverLoaded(page);
  await page.getByRole('tab', { name: 'Fonts' }).click();
  await page.locator('.cover-tools').screenshot({ path: shot('cover-fonts') });
  const saved = page.waitForResponse((r) => r.url().endsWith('/draft/save'));
  await page.getByRole('button', { name: 'Save changes' }).click();
  expect((await saved).status()).toBe(200);
  await page.getByRole('tab', { name: /Checks/ }).click();
  const built = page.waitForResponse((r) => r.url().endsWith('/cover/build'));
  await page.getByRole('button', { name: /Build cover|Rebuild cover/ }).click();
  const result = await (await built).json();
  expect(result.build.success).toBe(true);
  const rules = result.report.rules as { code: string; outcome: string }[];
  expect(rules.find((r) => r.code === 'cover_fonts')!.outcome).toBe('passed');
  expect(rules.find((r) => r.code === 'cover_font_license')!.outcome).toBe('passed');
  expect(rules.find((r) => r.code === 'kdp_cover_fonts_embedded')!.outcome).toBe('passed');
  await expect(page.getByLabel('Cover preflight status').getByText('Valid')).toBeVisible();
});

test('dragging the selected photograph moves the focal point', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await buildInterior(page, 'cover-demo');
  await openCover(page, 'cover-demo');
  await page.getByRole('tab', { name: 'Design' }).click();
  const layout = nextDraft(page);
  await page.getByRole('button', { name: 'Front photo' }).click();
  await layout;
  await coverLoaded(page);
  const before = Number(await page.getByLabel(/Focal point, left to right/).inputValue());
  const box = (await page.locator('.cover-window').boundingBox())!;
  // The first click selects the photograph; only then does a drag move it.
  await page.mouse.click(box.x + box.width * 0.75, box.y + box.height * 0.9);
  await expect(page.getByRole('group', { name: /Photograph selected/ })).toBeVisible();
  const next = nextDraft(page);
  await page.mouse.move(box.x + box.width * 0.75, box.y + box.height * 0.9);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.75 + 120, box.y + box.height * 0.9, { steps: 6 });
  await page.mouse.up();
  await next;
  const after = Number(await page.getByLabel(/Focal point, left to right/).inputValue());
  expect(after).toBeLessThan(before);
});

test('cover demo is usable at desktop, tablet and phone widths', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await buildInterior(page, 'cover-demo');
  await openCover(page, 'cover-demo');
  await page.getByRole('tab', { name: /Checks/ }).click();
  const build = page.waitForResponse((r) => r.url().endsWith('/cover/build'));
  await page.getByRole('button', { name: /Build cover|Rebuild cover/ }).click();
  expect((await build).status()).toBe(200);
  await expect(page.getByLabel('Cover preflight status').getByText('Ready')).toBeVisible();
  for (const [name, width, height] of [
    ['1440', 1440, 900],
    ['1024', 1024, 768],
    ['768', 768, 1024],
    ['390', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    await openCover(page, 'cover-demo');
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBeTruthy();
    const stage = (await page.locator('.cover-window').boundingBox())!;
    expect(stage.width).toBeGreaterThan(Math.min(320, width * 0.45));
    expect(stage.x).toBeGreaterThanOrEqual(0);
    expect(stage.x + stage.width).toBeLessThanOrEqual(width);
    // The preview is visible without scrolling on every width.
    expect(stage.y + stage.height * 0.5).toBeLessThan(height);
    await page.evaluate(() => document.fonts.ready);
    if (name === '1440') {
      await noAxeViolations(page);
      await page.screenshot({ path: shot('cover-1440') });
      await page.screenshot({ path: shot('cover') });
    } else {
      await page.screenshot({ path: shot(`cover-${name}`), fullPage: name === '390' });
    }
    if (name === '390') await noAxeViolations(page);
  }
});
