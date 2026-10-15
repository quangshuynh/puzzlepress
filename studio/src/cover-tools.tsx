import { useEffect, useState, type ReactNode } from 'react';
import { request, upload } from './api';
import { ROLES, addExtra, fontId, fontUsers, layerOf, setLayer } from './cover-model';
import { FieldErrors, matchIssues } from './editor-fields';
import type { CoverAsset, CoverConfig, CoverLibrary, FontFacts, Issue, PhotoOption } from './types';

// Left-hand Cover Studio tools: the photo library, text layers, fonts and the
// cover's design presets. Each tab edits authored values only.

export const TOOL_TABS = [
  ['photo', 'Photo'],
  ['text', 'Text'],
  ['fonts', 'Fonts'],
  ['design', 'Design'],
] as const;
export type ToolTab = (typeof TOOL_TABS)[number][0];

export function Tabs<T extends string>({
  label,
  tabs,
  value,
  onChange,
  idPrefix,
}: {
  label: string;
  tabs: readonly (readonly [T, string])[];
  value: T;
  onChange: (value: T) => void;
  idPrefix: string;
}) {
  return (
    <div className="panel-tabs" role="tablist" aria-label={label}>
      {tabs.map(([key, name], index) => (
        <button
          key={key}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${key}`}
          aria-controls={`${idPrefix}-panel-${key}`}
          aria-selected={value === key}
          tabIndex={value === key ? 0 : -1}
          onClick={() => onChange(key)}
          onKeyDown={(event) => {
            const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
            if (!step) return;
            const next = tabs[(index + step + tabs.length) % tabs.length][0];
            onChange(next);
            document.getElementById(`${idPrefix}-tab-${next}`)?.focus();
            event.preventDefault();
          }}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({
  legend,
  value,
  options,
  onChange,
  issues = [],
  path,
}: {
  legend: string;
  value: T | undefined;
  options: readonly (readonly [T, string])[];
  onChange: (value: T) => void;
  issues?: Issue[];
  path?: string;
}) {
  const matching = path ? matchIssues(issues, path) : [];
  return (
    <fieldset
      className="segmented"
      aria-describedby={matching.length ? `${path}-issues` : undefined}
    >
      <legend>{legend}</legend>
      <div>
        {options.map(([key, name]) => (
          <button
            key={key}
            type="button"
            aria-pressed={value === key}
            onClick={() => onChange(key)}
          >
            {name}
          </button>
        ))}
      </div>
      {path && <FieldErrors id={path} issues={matching} />}
    </fieldset>
  );
}

function dpiText(photo: PhotoOption) {
  if (!photo.dpi) return null;
  const { effective, minimum, sufficient } = photo.dpi;
  return (
    <span className={`dpi-badge ${sufficient ? 'pass' : 'fail'}`}>
      {Math.round(effective)} DPI{sufficient ? '' : ` · needs ${minimum}`}
    </span>
  );
}

export function PhotoLibrary({
  projectKey,
  cover,
  library,
  trial,
  onTrial,
  onChoose,
  notice,
  setNotice,
}: {
  projectKey: string;
  cover: CoverConfig;
  library?: CoverLibrary;
  trial: CoverAsset | null;
  onTrial?: (asset: CoverAsset | null) => void;
  onChoose: (asset: CoverAsset) => void;
  notice: string;
  setNotice: (message: string) => void;
}) {
  const [assets, setAssets] = useState<CoverAsset[]>();
  const [busy, setBusy] = useState(false);
  const base = `/api/projects/${encodeURIComponent(projectKey)}/cover/assets`;
  useEffect(() => {
    const controller = new AbortController();
    request<{ assets: CoverAsset[] }>(base, controller.signal)
      .then((data) => !controller.signal.aborted && setAssets(data.assets))
      .catch((err: Error) => !controller.signal.aborted && setNotice(err.message));
    return () => controller.abort();
  }, [base, setNotice]);
  const photos: PhotoOption[] = library?.photos ?? assets ?? [];
  const importPhoto = async (file: File) => {
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      setNotice('Choose a JPEG or PNG photograph.');
      return;
    }
    setBusy(true);
    setNotice(`Copying ${file.name} into the project…`);
    try {
      const data = await upload<{ asset: CoverAsset; assets: CoverAsset[] }>(
        `${base}?name=${encodeURIComponent(file.name)}`,
        new AbortController().signal,
        file,
        file.type,
      );
      setAssets(data.assets);
      setNotice(
        data.asset.reused
          ? `${data.asset.path} was already in the project; selected it.`
          : `Imported ${data.asset.path}; the original file is unchanged. Save to keep this choice.`,
      );
      onChoose(data.asset);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'The photograph was not imported.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="tool-section">
      <div className="tool-heading">
        <h3>Photo library</h3>
        <label className="button small-button file-button">
          Import…
          <input
            type="file"
            accept="image/jpeg,image/png"
            disabled={busy}
            aria-label="Import a photograph (JPEG or PNG)"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = '';
              if (file) void importPhoto(file);
            }}
          />
        </label>
      </div>
      <p className="small muted">
        Imports copy the original bytes into cover-assets; identical files are reused and nothing is
        upscaled. Choose Compare to preview a photo without applying it.
      </p>
      {assets === undefined && !library ? (
        <p className="small muted">Reading cover-assets…</p>
      ) : photos.length === 0 ? (
        <p className="small muted">No photographs in this project yet.</p>
      ) : (
        <ul className="photo-grid" aria-label="Photographs in this project">
          {photos.map((photo) => {
            const current = photo.path === cover.image.path;
            const comparing = trial?.path === photo.path;
            const name = photo.path.replace('cover-assets/', '');
            return (
              <li
                key={photo.path}
                className={`${current ? 'current' : ''}${comparing ? ' comparing' : ''}`}
              >
                <img
                  src={`/api/projects/${encodeURIComponent(projectKey)}/cover/assets/thumbnail?path=${encodeURIComponent(photo.path)}`}
                  alt=""
                  loading="lazy"
                />
                <div className="photo-facts">
                  <strong title={name}>{name}</strong>
                  <span className="small muted">
                    {photo.pixels
                      ? `${photo.pixels[0]} × ${photo.pixels[1]} px`
                      : `Unusable: ${photo.problem?.replaceAll('_', ' ')}`}
                  </span>
                  {dpiText(photo)}
                </div>
                <div className="photo-actions">
                  {current ? (
                    <span className="small current-mark">In use</span>
                  ) : (
                    <>
                      {onTrial && (
                        <button
                          type="button"
                          className="small-button"
                          aria-pressed={comparing}
                          disabled={!photo.sha256}
                          aria-label={`Compare ${name} without applying it`}
                          onClick={() => onTrial(comparing ? null : photo)}
                        >
                          Compare
                        </button>
                      )}
                      <button
                        type="button"
                        className="small-button"
                        disabled={!photo.sha256}
                        aria-label={`Use ${name}`}
                        onClick={() => onChoose(photo)}
                      >
                        Use
                      </button>
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p role="status" aria-live="polite" className="small">
        {notice}
      </p>
    </div>
  );
}

function TextTab({
  cover,
  display,
  selected,
  onSelect,
  update,
  issues,
}: {
  cover: CoverConfig;
  display?: Record<string, string | null>;
  selected: string | null;
  onSelect: (layer: string) => void;
  update: (next: CoverConfig) => void;
  issues: Issue[];
}) {
  const rows: [string, string, string][] = ROLES.map(([role, name]) => [
    role,
    name,
    role === 'back_text' ? (cover.back_text ?? '') : (display?.[role] ?? ''),
  ]);
  for (const extra of cover.extra ?? [])
    rows.push([
      `extra:${extra.id}`,
      `${extra.panel === 'back' ? 'Back' : 'Front'} text`,
      extra.text,
    ]);
  return (
    <div className="tool-section">
      <div className="tool-heading">
        <h3>Text layers</h3>
      </div>
      <ul className="layer-list" aria-label="Cover text layers">
        {rows.map(([layer, name, text]) => {
          const overrides = layerOf(cover, layer);
          const hidden = overrides.visible === false;
          const problems = matchIssues(
            issues,
            layer.startsWith('extra:') ? 'cover.extra' : `cover.text.${layer}`,
          );
          return (
            <li key={layer} className={layer === selected ? 'selected' : undefined}>
              <button
                type="button"
                className="layer-select"
                aria-pressed={layer === selected}
                onClick={() => onSelect(layer)}
              >
                <span className="layer-name">{name}</span>
                <span className={`layer-text${hidden ? ' hidden-text' : ''}`}>
                  {hidden ? 'Hidden on the cover' : text ? text.split('\n')[0] : 'Empty'}
                </span>
              </button>
              <button
                type="button"
                className="icon-button"
                aria-pressed={!hidden}
                aria-label={`${hidden ? 'Show' : 'Hide'} ${name.toLowerCase()} on the cover`}
                title={hidden ? 'Show on the cover' : 'Hide on the cover'}
                onClick={() => update(setLayer(cover, layer, { visible: hidden }))}
              >
                <EyeIcon open={!hidden} />
              </button>
              {problems.length > 0 && (
                <span className="status fail layer-flag">
                  <span aria-hidden="true" className="status-mark" />
                  Fix
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <div className="button-row">
        {(['front', 'back'] as const).map((panel) => (
          <button
            key={panel}
            type="button"
            className="small-button"
            disabled={(cover.extra?.length ?? 0) >= 8}
            onClick={() => {
              const [next, layer] = addExtra(cover, panel);
              update(next);
              onSelect(layer);
            }}
          >
            Add {panel} text
          </button>
        ))}
      </div>
      <p className="small muted">
        Hiding or restyling cover text never changes the book details: the title, subtitle, author
        and imprint stay as they are in Book.
      </p>
    </div>
  );
}

export function EyeIcon({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
    >
      <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
      {!open && <path d="M4 20 20 4" />}
    </svg>
  );
}

function FontsTab({
  projectKey,
  cover,
  library,
  update,
  issues,
}: {
  projectKey: string;
  cover: CoverConfig;
  library?: CoverLibrary;
  update: (next: CoverConfig) => void;
  issues: Issue[];
}) {
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [listed, setListed] = useState<FontFacts[]>();
  const base = `/api/projects/${encodeURIComponent(projectKey)}/cover/fonts`;
  const fonts = listed ?? library?.fonts ?? [];
  const importFont = async (file: File) => {
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (extension !== 'ttf' && extension !== 'otf') {
      setNotice('Choose a .ttf or .otf font file.');
      return;
    }
    setBusy(true);
    setNotice(`Checking ${file.name}…`);
    try {
      const data = await upload<{ font: FontFacts; fonts: FontFacts[] }>(
        `${base}?name=${encodeURIComponent(file.name)}`,
        new AbortController().signal,
        file,
        `font/${extension}`,
      );
      setListed(data.fonts);
      setNotice(
        data.font.reused
          ? `${data.font.full_name} was already in the project.`
          : `Imported ${data.font.full_name}. Add it to the cover to use it, and record its license.`,
      );
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'The font was not imported.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="tool-section">
      <div className="tool-heading">
        <h3>Imported fonts</h3>
        <label className="button small-button file-button">
          Import…
          <input
            type="file"
            accept=".ttf,.otf,font/ttf,font/otf"
            disabled={busy}
            aria-label="Import a font (.ttf or .otf)"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = '';
              if (file) void importFont(file);
            }}
          />
        </label>
      </div>
      <p className="small muted">
        Static TrueType-outline fonts that allow embedding. PostScript-outline, variable and web
        fonts are not supported yet. Python embeds a subset in cover.pdf.
      </p>
      {fonts.length === 0 && (
        <p className="small muted">No imported fonts. Bundled faces are always available.</p>
      )}
      <ul className="font-list">
        {fonts.map((font) => {
          const inCover = cover.fonts?.find((f) => f.path === font.path);
          const index = cover.fonts?.findIndex((f) => f.path === font.path) ?? -1;
          const missing = library?.fonts.find((f) => f.path === font.path)?.missing ?? font.missing;
          return (
            <li key={font.path}>
              {font.problem ? (
                <>
                  <strong>{font.path.replace('cover-assets/fonts/', '')}</strong>
                  <p className="small field-errors">Unusable: {font.message ?? font.problem}</p>
                </>
              ) : (
                <>
                  <div className="font-head">
                    <strong>{font.full_name}</strong>
                    <span className="small muted">
                      {font.glyphs} characters · embedding {font.embedding?.replace('_', ' ')}
                    </span>
                  </div>
                  <img
                    className="font-specimen"
                    src={`${base}/specimen?font=${encodeURIComponent(font.path)}`}
                    alt={`Specimen of ${font.full_name}, drawn by the cover renderer`}
                    loading="lazy"
                  />
                  {missing && missing.length > 0 ? (
                    <p className="small field-errors">
                      Missing for this cover: {missing.join(' ')}
                    </p>
                  ) : missing ? (
                    <p className="small muted">Draws every character this cover uses.</p>
                  ) : null}
                  {inCover ? (
                    <div className="font-provenance">
                      <p className="small">
                        In this cover as <code>{inCover.id}</code>
                      </p>
                      <label>
                        License
                        <input
                          value={inCover.license ?? ''}
                          placeholder="Unknown"
                          onChange={(e) =>
                            update(
                              setFont(cover, index, {
                                license: e.target.value.trim() ? e.target.value : null,
                              }),
                            )
                          }
                        />
                      </label>
                      <label>
                        Source
                        <input
                          value={inCover.source ?? ''}
                          placeholder="Unknown"
                          onChange={(e) =>
                            update(
                              setFont(cover, index, {
                                source: e.target.value.trim() ? e.target.value : null,
                              }),
                            )
                          }
                        />
                      </label>
                      <FieldErrors
                        id={`cover.fonts.${index}`}
                        issues={matchIssues(issues, `cover.fonts.${index}`)}
                      />
                      <button
                        type="button"
                        className="small-button"
                        disabled={fontUsers(cover, inCover.id).length > 0}
                        title={
                          fontUsers(cover, inCover.id).length ? 'Used by a text layer' : undefined
                        }
                        onClick={() => {
                          const next: CoverConfig = {
                            ...cover,
                            fonts: cover.fonts!.filter((_, i) => i !== index),
                          };
                          if (!next.fonts?.length) delete next.fonts;
                          update(next);
                        }}
                      >
                        Remove from cover
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="small-button"
                      disabled={!font.sha256 || (cover.fonts?.length ?? 0) >= 8}
                      onClick={() =>
                        update({
                          ...cover,
                          version: 2,
                          fonts: [
                            ...(cover.fonts ?? []),
                            {
                              id: fontId(cover, font.full_name ?? 'font'),
                              path: font.path,
                              sha256: font.sha256!,
                            },
                          ],
                        })
                      }
                    >
                      Add to cover
                    </button>
                  )}
                </>
              )}
            </li>
          );
        })}
      </ul>
      <p className="small muted">
        Record where each font came from and the license that allows commercial print use.
        PuzzlePress reads the font&apos;s embedding flags but cannot confirm your license.
      </p>
      <p role="status" aria-live="polite" className="small">
        {notice}
      </p>
    </div>
  );
}

function setFont(
  cover: CoverConfig,
  index: number,
  patch: { license?: string | null; source?: string | null },
) {
  const fonts = cover.fonts!.map((font, i) => (i === index ? { ...font, ...patch } : font));
  return { ...cover, fonts };
}

function DesignTab({
  cover,
  update,
  issues,
}: {
  cover: CoverConfig;
  update: (next: CoverConfig) => void;
  issues: Issue[];
}) {
  const setType = (next: Partial<CoverConfig['type']>) =>
    update({ ...cover, type: { ...cover.type, ...next } });
  return (
    <div className="tool-section">
      <Segmented
        legend="Layout"
        value={cover.layout}
        path="cover.layout"
        issues={issues}
        options={[
          ['full_wrap', 'Full wrap'],
          ['front_photo', 'Front photo'],
        ]}
        onChange={(layout) => update({ ...cover, layout })}
      />
      <p className="small muted field-hint">
        {cover.layout === 'full_wrap'
          ? 'One photo across back, spine and front.'
          : 'Photo on the front; spine and back in the fill color.'}
      </p>
      <Segmented
        legend="Type preset"
        value={cover.type.style}
        path="cover.type.style"
        issues={issues}
        options={[
          ['editorial', 'Editorial'],
          ['bold', 'Bold'],
          ['minimal', 'Minimal'],
        ]}
        onChange={(style) => setType({ style })}
      />
      <Segmented
        legend="Title position"
        value={cover.type.position}
        path="cover.type.position"
        issues={issues}
        options={[
          ['top', 'Top'],
          ['middle', 'Middle'],
          ['bottom', 'Bottom'],
        ]}
        onChange={(position) => setType({ position })}
      />
      <Segmented
        legend="Default alignment"
        value={cover.type.align}
        path="cover.type.align"
        issues={issues}
        options={[
          ['center', 'Centered'],
          ['left', 'Left'],
        ]}
        onChange={(align) => setType({ align })}
      />
      <Segmented
        legend="Text tone"
        value={cover.type.tone}
        path="cover.type.tone"
        issues={issues}
        options={[
          ['light', 'Light text'],
          ['dark', 'Dark text'],
        ]}
        onChange={(tone) => setType({ tone })}
      />
      <Segmented
        legend="Legibility"
        value={cover.legibility}
        path="cover.legibility"
        issues={issues}
        options={[
          ['shade', 'Shade'],
          ['panel', 'Panel'],
          ['none', 'None'],
        ]}
        onChange={(legibility) => update({ ...cover, legibility })}
      />
      <ColorField
        id="cover-background"
        label="Fill color"
        value={cover.background}
        fallback="#26302b"
        hint="Panels and wherever the photograph does not print."
        issues={matchIssues(issues, 'cover.background')}
        path="cover.background"
        onChange={(background) => update({ ...cover, background })}
      />
      <Segmented
        legend="Spine text"
        value={cover.spine_text}
        path="cover.spine_text"
        issues={issues}
        options={[
          ['auto', 'When allowed'],
          ['none', 'None'],
        ]}
        onChange={(spine_text) => update({ ...cover, spine_text })}
      />
      <p className="small muted field-hint">KDP needs 80+ pages and room for 7 pt type.</p>
    </div>
  );
}

export function ColorField({
  id,
  label,
  value,
  fallback,
  hint,
  issues,
  path,
  onChange,
  extra,
}: {
  id: string;
  label: string;
  value: string;
  fallback: string;
  hint?: string;
  issues: Issue[];
  path: string;
  onChange: (value: string) => void;
  extra?: ReactNode;
}) {
  return (
    <div className="editor-field color-field">
      <label htmlFor={id}>{label}</label>
      <div>
        <input
          id={id}
          type="color"
          value={/^#[0-9a-fA-F]{6}$/.test(value) ? value.toLowerCase() : fallback}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={hint ? `${id}-hint` : undefined}
        />
        <input
          aria-label={`${label} as hex`}
          value={value}
          onChange={(e) => onChange(e.target.value.trim())}
          aria-invalid={issues.length ? true : undefined}
        />
        {extra}
      </div>
      {hint && (
        <p className="small muted field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      <FieldErrors id={path} issues={issues} />
    </div>
  );
}

export function CoverTools({
  tab,
  setTab,
  projectKey,
  cover,
  library,
  display,
  selected,
  onSelect,
  update,
  issues,
  trial,
  onTrial,
  onChoosePhoto,
  notice,
  setNotice,
}: {
  tab: ToolTab;
  setTab: (tab: ToolTab) => void;
  projectKey: string;
  cover: CoverConfig;
  library?: CoverLibrary;
  display?: Record<string, string | null>;
  selected: string | null;
  onSelect: (layer: string | null) => void;
  update: (next: CoverConfig) => void;
  issues: Issue[];
  trial: CoverAsset | null;
  onTrial: (asset: CoverAsset | null) => void;
  onChoosePhoto: (asset: CoverAsset) => void;
  notice: string;
  setNotice: (message: string) => void;
}) {
  return (
    <section className="cover-panel cover-tools" aria-label="Cover tools">
      <Tabs
        label="Cover tools"
        tabs={TOOL_TABS}
        value={tab}
        onChange={setTab}
        idPrefix="cover-tools"
      />
      <div
        role="tabpanel"
        id={`cover-tools-panel-${tab}`}
        aria-labelledby={`cover-tools-tab-${tab}`}
        className="panel-body"
      >
        {tab === 'photo' && (
          <PhotoLibrary
            projectKey={projectKey}
            cover={cover}
            library={library}
            trial={trial}
            onTrial={onTrial}
            onChoose={onChoosePhoto}
            notice={notice}
            setNotice={setNotice}
          />
        )}
        {tab === 'text' && (
          <TextTab
            cover={cover}
            display={display}
            selected={selected}
            onSelect={onSelect}
            update={update}
            issues={issues}
          />
        )}
        {tab === 'fonts' && (
          <FontsTab
            projectKey={projectKey}
            cover={cover}
            library={library}
            update={update}
            issues={issues}
          />
        )}
        {tab === 'design' && <DesignTab cover={cover} update={update} issues={issues} />}
      </div>
    </section>
  );
}
