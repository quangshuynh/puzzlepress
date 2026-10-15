import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from './api';
import type { Source } from './editor-fields';
import type {
  CoverCheck,
  CoverConfig,
  CoverTemplateInfo,
  TemplateGallery,
  TemplatePreview,
} from './types';
import { Status } from './ui';

// The template gallery. Python lists, validates, applies and renders templates;
// a preview is the real cover PDF of this draft with the template applied, and
// nothing is saved until the author applies it and then saves the draft.

const CATEGORY: Record<string, string> = {
  photographic: 'Photographic',
  bold: 'Bold',
  dynamic: 'Dynamic',
  classic: 'Classic',
  minimal: 'Minimal',
  technical: 'Technical',
  puzzle: 'Puzzle',
  editorial: 'Editorial',
  custom: 'Your template',
};
const PHOTO: Record<CoverTemplateInfo['photo'], string> = {
  required: 'Needs a photograph',
  optional: 'Photograph optional',
  none: 'No photograph',
};

function previewUrl(projectKey: string, pdf: string, size: 'thumb' | 'preview') {
  return `/api/projects/${encodeURIComponent(projectKey)}/cover/preview?size=${size}&pdf=${pdf}`;
}

function counts(checks: CoverCheck[] = []) {
  const blocking = checks.filter((c) => c.severity === 'error').length;
  const advisory = checks.filter((c) => c.severity === 'warning').length;
  return { blocking, advisory };
}

export function TemplatesTab({
  projectKey,
  source,
  onApply,
}: {
  projectKey: string;
  source: Source;
  onApply: (cover: CoverConfig, template: CoverTemplateInfo) => void;
}) {
  const base = `/api/projects/${encodeURIComponent(projectKey)}`;
  const [gallery, setGallery] = useState<TemplateGallery>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [previews, setPreviews] = useState<Record<string, TemplatePreview | 'error'>>({});
  const [open, setOpen] = useState<CoverTemplateInfo | null>(null);
  const [round, setRound] = useState(0);
  const [failures, setFailures] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const latest = useRef(source);
  latest.current = source;

  useEffect(() => {
    const controller = new AbortController();
    request<TemplateGallery>(`${base}/cover/templates`, controller.signal)
      .then((data) => !controller.signal.aborted && setGallery(data))
      .catch((err: Error) => !controller.signal.aborted && setError(err.message));
    return () => controller.abort();
  }, [base]);

  // Card previews, one at a time so a large gallery never floods the renderer.
  const ids = gallery?.templates.map((t) => `${t.id}:${t.identity}`).join(',') ?? '';
  useEffect(() => {
    if (!gallery) return;
    const controller = new AbortController();
    void (async () => {
      for (const template of gallery.templates) {
        if (controller.signal.aborted) return;
        try {
          const data = await request<TemplatePreview>(
            `${base}/draft/cover/templates/${encodeURIComponent(template.id)}/preview`,
            controller.signal,
            { source: latest.current },
          );
          if (!controller.signal.aborted) setPreviews((p) => ({ ...p, [template.id]: data }));
        } catch (err) {
          if (controller.signal.aborted) return;
          setPreviews((p) => ({ ...p, [template.id]: 'error' }));
          setFailures((f) => ({
            ...f,
            [template.id]: err instanceof ApiError ? err.message : 'The preview did not render.',
          }));
        }
      }
    })();
    return () => controller.abort();
    // `ids` and `round` capture what the previews depend on; the draft is read when they run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, ids, round]);

  const replaceGallery = (data: TemplateGallery, message: string) => {
    setGallery({ templates: data.templates, problems: data.problems });
    setNotice(message);
  };
  const act = async (path: string, body: object, message: (data: TemplateGallery) => string) => {
    try {
      const data = await request<TemplateGallery>(
        `${base}/cover/templates${path}`,
        new AbortController().signal,
        body,
      );
      replaceGallery(data, message(data));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'The template request did not complete.');
    }
  };
  const saveCurrent = async () => {
    setSaving(true);
    await act('', { source: latest.current, name, description }, (data) => {
      setName('');
      setDescription('');
      return `Saved “${data.template?.name}” to this project's templates. The book's words, photographs and attestations are not part of it.`;
    });
    setSaving(false);
  };
  const importFile = async (file: File) => {
    if (file.size > 256 * 1024) {
      setNotice('A template file is at most 256 KB.');
      return;
    }
    const text = await file.text();
    await act(
      '/import',
      { text },
      (data) => `Imported “${data.template?.name}” after checking it. Nothing was applied.`,
    );
  };

  if (error) return <p className="small field-errors">{error}</p>;
  if (!gallery) return <p className="small muted">Reading templates…</p>;
  const custom = gallery.templates.filter((t) => !t.builtin);
  const builtin = gallery.templates.filter((t) => t.builtin);
  const card = (template: CoverTemplateInfo) => {
    const preview = previews[template.id];
    const result = preview && preview !== 'error' ? preview : undefined;
    const { blocking } = counts(result?.checks);
    return (
      <li key={template.id} className="template-card">
        {result?.success && result.preview ? (
          <img
            className="template-thumb"
            src={previewUrl(projectKey, result.preview.pdf_sha256, 'thumb')}
            alt={`${template.name} applied to this book: back, spine and front`}
          />
        ) : (
          <div className="template-thumb" role="img" aria-label={`${template.name} colors`}>
            <div className="template-swatch" aria-hidden="true">
              {template.palette.map((color) => (
                <span key={color} style={{ background: color }} />
              ))}
            </div>
            <p className="small muted" style={{ padding: 8 }}>
              {preview === 'error'
                ? `No preview: ${failures[template.id] ?? 'the preview did not render.'}`
                : result && !result.success
                  ? `No preview: ${result.diagnostics?.[0]?.message ?? 'build the interior in Print first.'}`
                  : 'Rendering preview…'}
            </p>
          </div>
        )}
        <h4>{template.name}</h4>
        <p className="small">{template.description}</p>
        <div className="template-meta">
          <span>
            <strong>{CATEGORY[template.category] ?? template.category}</strong>
          </span>
          <span>{PHOTO[template.photo]}</span>
          <span>Fonts: {template.fonts.join(', ')}</span>
          {result?.missing_slots?.length ? <Status tone="review">Photo placeholder</Status> : null}
          {blocking > 0 && <Status tone="fail">{blocking} blocking</Status>}
        </div>
        <div className="template-actions">
          <button
            type="button"
            className="small-button primary"
            onClick={() => setOpen(template)}
            aria-label={`Preview ${template.name} before applying`}
          >
            Preview…
          </button>
          <button
            type="button"
            className="small-button"
            aria-label={`Duplicate ${template.name} as your own template`}
            onClick={() => {
              const copy = window.prompt('Name for the copy', `${template.name} copy`);
              if (copy?.trim())
                void act(
                  `/${encodeURIComponent(template.id)}/duplicate`,
                  { name: copy },
                  () => `Duplicated as “${copy.trim()}”.`,
                );
            }}
          >
            Duplicate
          </button>
          {!template.builtin && (
            <>
              <button
                type="button"
                className="small-button"
                aria-label={`Rename ${template.name}`}
                onClick={() => {
                  const next = window.prompt('Template name', template.name);
                  if (next?.trim() && next.trim() !== template.name)
                    void act(
                      `/${encodeURIComponent(template.id)}/update`,
                      {
                        identity: template.identity,
                        name: next,
                        description: template.description,
                      },
                      () => `Renamed to “${next.trim()}”.`,
                    );
                }}
              >
                Rename
              </button>
              <a
                className="button small-button"
                href={`${base}/cover/templates/${encodeURIComponent(template.id)}/export`}
                download
                aria-label={`Export ${template.name} as a file`}
              >
                Export
              </a>
              <button
                type="button"
                className="small-button danger"
                aria-label={`Delete ${template.name}`}
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete the template “${template.name}” from this project? Covers that used it keep their design.`,
                    )
                  )
                    void act(
                      `/${encodeURIComponent(template.id)}/delete`,
                      { identity: template.identity },
                      () => `Deleted “${template.name}”.`,
                    );
                }}
              >
                Delete
              </button>
            </>
          )}
        </div>
      </li>
    );
  };
  return (
    <div className="tool-section">
      <div className="tool-heading">
        <h3>Templates</h3>
        <button type="button" className="small-button" onClick={() => setRound((n) => n + 1)}>
          Refresh previews
        </button>
      </div>
      <p className="small muted">
        Previews show this book with each template. Browsing saves nothing; applying changes only
        the unsaved draft cover.
      </p>
      {gallery.problems.length > 0 && (
        <ul className="small field-errors">
          {gallery.problems.map((problem) => (
            <li key={problem.file}>
              {problem.file}: {problem.message}
            </li>
          ))}
        </ul>
      )}
      <ul className="template-gallery" aria-label="Built-in templates">
        {builtin.map(card)}
      </ul>
      <h3 className="tool-subheading">Your templates</h3>
      {custom.length ? (
        <ul className="template-gallery" aria-label="Your templates">
          {custom.map(card)}
        </ul>
      ) : (
        <p className="small muted">None yet. Save the current design to reuse it.</p>
      )}
      <details className="template-save">
        <summary>Save the current design as a template</summary>
        <div className="editor-field">
          <label htmlFor="template-name">Template name</label>
          <input
            id="template-name"
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="editor-field">
          <label htmlFor="template-description">Description</label>
          <textarea
            id="template-description"
            rows={2}
            maxLength={300}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <p className="small muted">
          The design is kept; the book&apos;s title, author and other words become placeholders,
          photographs become empty frames and back-cover text is left out.
        </p>
        <button
          type="button"
          className="small-button primary"
          disabled={!name.trim() || saving}
          onClick={() => void saveCurrent()}
        >
          Save as template
        </button>
      </details>
      <label className="button small-button file-button">
        Import a template file…
        <input
          type="file"
          accept=".json,application/json"
          aria-label="Import a template file (JSON)"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (file) void importFile(file);
          }}
        />
      </label>
      <p role="status" aria-live="polite" className="small">
        {notice}
      </p>
      {open && (
        <TemplateDialog
          projectKey={projectKey}
          template={open}
          source={latest.current}
          cached={
            previews[open.id] !== 'error' ? (previews[open.id] as TemplatePreview) : undefined
          }
          onClose={() => setOpen(null)}
          onApply={(cover) => {
            onApply(cover, open);
            setOpen(null);
            setNotice(
              `Applied “${open.name}” to the draft. Undo or Revert restores the previous cover; nothing is saved until you save.`,
            );
          }}
        />
      )}
    </div>
  );
}

function TemplateDialog({
  projectKey,
  template,
  source,
  cached,
  onClose,
  onApply,
}: {
  projectKey: string;
  template: CoverTemplateInfo;
  source: Source;
  cached?: TemplatePreview;
  onClose: () => void;
  onApply: (cover: CoverConfig) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState<TemplatePreview | undefined>(cached);
  const [error, setError] = useState('');
  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) {
      if (typeof element.showModal === 'function') element.showModal();
      else element.setAttribute('open', '');
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    request<TemplatePreview>(
      `/api/projects/${encodeURIComponent(projectKey)}/draft/cover/templates/${encodeURIComponent(template.id)}/preview`,
      controller.signal,
      { source },
    )
      .then((data) => !controller.signal.aborted && setPreview(data))
      .catch(
        (err: Error) =>
          !controller.signal.aborted &&
          setError(err instanceof ApiError ? err.message : 'The preview did not render.'),
      );
    return () => controller.abort();
  }, [projectKey, template.id, source]);
  const { blocking, advisory } = counts(preview?.checks);
  const current = preview?.current;
  return (
    <dialog
      ref={dialog}
      className="template-dialog"
      aria-labelledby="template-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <h2 id="template-dialog-title">{template.name}</h2>
      <p className="small">{template.description}</p>
      <div className="template-dialog-body">
        <div>
          {preview?.success && preview.preview ? (
            <img
              src={previewUrl(projectKey, preview.preview.pdf_sha256, 'preview')}
              alt={`Your book with ${template.name}: back, spine and front as Python renders them`}
            />
          ) : error ? (
            <p className="field-errors">{error}</p>
          ) : preview && !preview.success ? (
            <p className="field-errors">
              This template cannot be previewed yet:{' '}
              {preview.diagnostics?.map((d) => d.message).join(' ')}
            </p>
          ) : (
            <p className="muted">Rendering the preview with Python…</p>
          )}
          {template.provenance && <p className="small muted">{template.provenance}</p>}
        </div>
        <div>
          <h3>Your book details stay</h3>
          <dl>
            <dt>Title</dt>
            <dd>{current?.title ?? '…'}</dd>
            <dt>Subtitle</dt>
            <dd>{current ? (current.subtitle ?? 'None') : '…'}</dd>
            <dt>Author</dt>
            <dd>{current ? (current.author ?? 'None') : '…'}</dd>
            <dt>Imprint</dt>
            <dd>{current ? (current.imprint ?? 'None') : '…'}</dd>
          </dl>
          {preview?.replaced && (
            <>
              <h3>Replaced by the template</h3>
              <ul className="small">
                {preview.replaced.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <h3>Kept</h3>
              <ul className="small">
                {preview.kept?.map((line) => (
                  <li key={line}>{line}</li>
                ))}
                <li>The interior, publishing details and every declaration are untouched.</li>
              </ul>
            </>
          )}
          {preview?.missing_slots?.length ? (
            <p className="small">
              <Status tone="review">Placeholder</Status> This template needs a photograph and the
              cover has none, so the frame shows a grey placeholder. Import a photograph and place
              it afterwards; no other picture is used.
            </p>
          ) : null}
          {preview?.success && (
            <p className="small">
              {blocking ? (
                <Status tone="fail">{blocking} blocking</Status>
              ) : (
                <Status tone="pass">No blocking layout issues</Status>
              )}{' '}
              {advisory > 0 && <Status tone="review">{advisory} advisory</Status>}
            </p>
          )}
          <p className="small muted">
            Applying puts this design in your unsaved draft. Undo or Revert brings back the current
            cover; nothing is saved until you choose Save.
          </p>
          <div className="button-row">
            <button type="button" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="primary"
              disabled={!preview?.success || !preview.cover}
              onClick={() => preview?.cover && onApply(preview.cover)}
            >
              Apply template
            </button>
          </div>
        </div>
      </div>
    </dialog>
  );
}
