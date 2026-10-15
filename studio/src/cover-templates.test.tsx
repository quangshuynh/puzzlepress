import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { TemplatesTab } from './cover-templates';
import type { Source } from './editor-fields';
import type { CoverTemplateInfo, TemplatePreview } from './types';

const TEMPLATE: CoverTemplateInfo = {
  id: 'bold-garage',
  name: 'Bold Garage',
  description: 'Charcoal with stacked capitals.',
  category: 'bold',
  photo: 'optional',
  slots: 1,
  builtin: true,
  palette: ['#24262a', '#f2c230'],
  fonts: ['Vera Sans', 'Vera Sans Bold'],
  imported_fonts: [],
  provenance: 'Original PuzzlePress vector design.',
  identity: 'pp1-cover-template-sha256-' + '1'.repeat(64),
};
const COVER = { version: 3, type: { style: 'bold' }, regions: {}, elements: [] };
const PREVIEW: TemplatePreview = {
  success: true,
  template: TEMPLATE,
  cover: COVER as unknown as TemplatePreview['cover'],
  missing_slots: [],
  replaced: ['Region backgrounds for the back, spine and front'],
  kept: ["The book's title, subtitle, author and imprint (Book details are never changed)"],
  current: { title: 'Automotive Word Search', subtitle: null, author: null, imprint: null },
  checks: [{ code: 'low_contrast', severity: 'warning', message: 'Low contrast.' }],
  buildable: true,
  preview: { pdf_sha256: 'a'.repeat(64), scales: { thumb: 0.3, preview: 1 } },
};

test('the gallery previews without saving and applies only on Apply', async () => {
  const calls: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    const path = String(url);
    calls.push(`${options?.method ?? 'GET'} ${path}`);
    if (path.endsWith('/cover/templates'))
      return new Response(JSON.stringify({ templates: [TEMPLATE], problems: [] }));
    if (path.endsWith('/preview')) return new Response(JSON.stringify(PREVIEW));
    return new Response('{}', { status: 404 });
  });
  const onApply = vi.fn();
  const user = userEvent.setup();
  render(
    <TemplatesTab
      projectKey="book"
      source={{ cover: {} } as unknown as Source}
      onApply={onApply}
    />,
  );
  const card = await screen.findByRole('heading', { name: 'Bold Garage' });
  expect(card).toBeInTheDocument();
  expect(screen.getByText('Photograph optional')).toBeInTheDocument();
  expect(screen.getByText(/Fonts: Vera Sans, Vera Sans Bold/)).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByRole('img', { name: /Bold Garage applied to this book/ })).toHaveAttribute(
      'src',
      expect.stringContaining('size=thumb'),
    ),
  );
  // Built-in templates cannot be renamed or deleted.
  expect(screen.queryByRole('button', { name: 'Delete Bold Garage' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Preview Bold Garage before applying' }));
  const dialog = await screen.findByRole('dialog', { name: 'Bold Garage' });
  expect(within(dialog).getByText('Automotive Word Search')).toBeInTheDocument();
  expect(within(dialog).getByText(/Region backgrounds/)).toBeInTheDocument();
  expect(within(dialog).getByText(/every declaration are untouched/)).toBeInTheDocument();
  expect(onApply).not.toHaveBeenCalled();
  expect(calls.every((call) => !call.includes('/save'))).toBe(true);
  await user.click(within(dialog).getByRole('button', { name: 'Apply template' }));
  expect(onApply).toHaveBeenCalledWith(COVER, TEMPLATE);
  expect(screen.getByRole('status')).toHaveTextContent(/nothing is saved until you save/);
});
