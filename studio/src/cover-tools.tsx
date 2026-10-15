import { useEffect, useRef, useState, type ReactNode } from 'react';
import { request, upload } from './api';
import { ROLES, addExtra, fontId, fontUsers, layerOf, setLayer } from './cover-model';
import { AssetsPanel } from './assets';
import { TemplatesTab } from './cover-templates';
import { plainOf } from './rich-text-model';
import { LayersTab, PresetsSection, RegionPicker, ShapesTab } from './cover-elements';
import { FieldErrors, matchIssues, type Source } from './editor-fields';
import type {
  AssetListing,
  AssetUse,
  CoverAsset,
  CoverConfig,
  CoverLayoutView,
  CoverLibrary,
  CoverTemplateInfo,
  ElementRegion,
  FontFacts,
  Issue,
  PhotoOption,
} from './types';

// Left-hand Cover Studio tools: the photo library, text layers, fonts and the
// cover's design presets. Each tab edits authored values only.

export const TOOL_TABS = [
  ['templates', 'Templates'],
  ['layers', 'Layers'],
  ['photo', 'Photos'],
  ['text', 'Text'],
  ['shapes', 'Shapes'],
  ['fonts', 'Fonts'],
  ['assets', 'Assets'],
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

function inUse(cover: CoverConfig, path: string) {
  if (cover.image) return cover.image.path === path;
  return (cover.elements ?? []).some((e) => e.type === 'photo' && e.image.path === path);
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
  placeLabel,
  source,
  onShowUse,
}: {
  projectKey: string;
  cover: CoverConfig;
  library?: CoverLibrary;
  trial: CoverAsset | null;
  onTrial?: (asset: CoverAsset | null) => void;
  onChoose: (asset: CoverAsset) => void;
  notice: string;
  setNotice: (message: string) => void;
  placeLabel?: string;
  source?: Source; // The draft: with it, each photo shows its uses and unused ones can be removed.
  onShowUse?: (use: AssetUse) => void;
}) {
  const [assets, setAssets] = useState<CoverAsset[]>();
  const [listing, setListing] = useState<AssetListing>();
  const [busy, setBusy] = useState(false);
  const [round, setRound] = useState(0);
  const base = `/api/projects/${encodeURIComponent(projectKey)}/cover/assets`;
  const assetsBase = `/api/projects/${encodeURIComponent(projectKey)}/assets`;
  useEffect(() => {
    const controller = new AbortController();
    request<{ assets: CoverAsset[] }>(base, controller.signal)
      .then((data) => !controller.signal.aborted && setAssets(data.assets))
      .catch((err: Error) => !controller.signal.aborted && setNotice(err.message));
    return () => controller.abort();
  }, [base, setNotice, round]);
  const latest = useRef(source);
  latest.current = source;
  const signature = JSON.stringify(source?.cover ?? null);
  useEffect(() => {
    if (!latest.current) return;
    const controller = new AbortController();
    request<AssetListing>(`${assetsBase}/list`, controller.signal, { source: latest.current })
      .then((data) => !controller.signal.aborted && setListing(data))
      .catch(() => undefined);
    return () => controller.abort();
  }, [assetsBase, signature, round]);
  const remove = async (path: string, sha256: string, name: string) => {
    if (
      !window.confirm(
        `Remove ${name}? It moves to this project's trash (Assets tab), where it can be restored.`,
      )
    )
      return;
    setBusy(true);
    try {
      await request<AssetListing>(`${assetsBase}/trash`, new AbortController().signal, {
        path,
        sha256,
        revision: listing?.revision,
        source: latest.current,
      });
      setNotice(`Moved ${name} to the project's trash. Restore it from the Assets tab.`);
      setRound((n) => n + 1);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'The photograph was not removed.');
    } finally {
      setBusy(false);
    }
  };
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
            const current = inUse(cover, photo.path);
            const comparing = trial?.path === photo.path;
            const name = photo.path.replace('cover-assets/', '');
            const listed = listing?.assets?.find((asset) => asset.path === photo.path);
            const uses = listed?.uses ?? [];
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
                  {current && !placeLabel ? (
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
                        aria-label={placeLabel ? `${placeLabel}: ${name}` : `Use ${name}`}
                        onClick={() => onChoose(photo)}
                      >
                        {placeLabel ? 'Place' : 'Use'}
                      </button>
                    </>
                  )}
                  {listed && (
                    <button
                      type="button"
                      className="small-button"
                      disabled={busy || uses.length > 0 || !photo.sha256}
                      aria-label={
                        uses.length
                          ? `Remove ${name} (unavailable: in use)`
                          : `Remove ${name} from the project`
                      }
                      title={uses.length ? 'In use: remove it from these layers first.' : undefined}
                      onClick={() => photo.sha256 && void remove(photo.path, photo.sha256, name)}
                    >
                      Remove…
                    </button>
                  )}
                </div>
                {uses.length > 0 && (
                  <p className="photo-uses">
                    Used by{' '}
                    {uses.map((use, i) => (
                      <span key={`${use.source}-${use.path}`}>
                        {i > 0 && ', '}
                        {onShowUse ? (
                          <button type="button" onClick={() => onShowUse(use)}>
                            {use.label}
                          </button>
                        ) : (
                          use.label
                        )}
                        {use.source === 'draft' ? ' (draft)' : ''}
                      </span>
                    ))}
                  </p>
                )}
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
    role === 'back_text' ? plainOf(cover.back_text) : (display?.[role] ?? ''),
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
  projectKey,
  source,
  cover,
  update,
  issues,
  onConvert,
}: {
  projectKey: string;
  source: Source;
  cover: CoverConfig;
  update: (next: CoverConfig) => void;
  issues: Issue[];
  onConvert: () => void;
}) {
  const setType = (next: Partial<CoverConfig['type']>) =>
    update({ ...cover, type: { ...cover.type, ...next } });
  const regions = cover.version >= 3;
  return (
    <div className="tool-section">
      {regions ? (
        <p className="small muted">
          A region design: the back, spine and front have their own backgrounds (select a region
          above to color it) and layers. Book text keeps the type preset below.
        </p>
      ) : (
        <>
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
          <button type="button" className="small-button" onClick={onConvert}>
            Convert to region design…
          </button>
        </>
      )}
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
      {regions && (
        <p className="small muted field-hint">
          Shade and panels apply only where book text sits over a photograph.
        </p>
      )}
      {!regions && (
        <ColorField
          id="cover-background"
          label="Fill color"
          value={cover.background ?? '#26302b'}
          fallback="#26302b"
          hint="Panels and wherever the photograph does not print."
          issues={matchIssues(issues, 'cover.background')}
          path="cover.background"
          onChange={(background) => update({ ...cover, background })}
        />
      )}
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
      <PresetsSection projectKey={projectKey} source={source} cover={cover} update={update} />
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
  source,
  cover,
  layout,
  library,
  display,
  selected,
  region,
  onRegion,
  onSelect,
  update,
  issues,
  trial,
  onTrial,
  onChoosePhoto,
  onConvert,
  onApplyTemplate,
  notice,
  setNotice,
}: {
  tab: ToolTab;
  setTab: (tab: ToolTab) => void;
  projectKey: string;
  source: Source;
  cover: CoverConfig;
  layout?: CoverLayoutView;
  library?: CoverLibrary;
  display?: Record<string, string | null>;
  selected: string | null;
  region: ElementRegion;
  onRegion: (region: ElementRegion) => void;
  onSelect: (layer: string | null) => void;
  update: (next: CoverConfig) => void;
  issues: Issue[];
  trial: CoverAsset | null;
  onTrial: (asset: CoverAsset | null) => void;
  onChoosePhoto: (asset: CoverAsset) => void;
  onConvert: () => void;
  onApplyTemplate: (cover: CoverConfig, template: CoverTemplateInfo) => void;
  notice: string;
  setNotice: (message: string) => void;
}) {
  const licenses = Object.fromEntries((cover.fonts ?? []).map((font) => [font.path, font.license]));
  const showUse = (use: AssetUse) => {
    const match = use.path.match(/^cover\.elements\.(\d+)\./);
    if (match) {
      const element = cover.elements?.[Number(match[1])];
      if (element) onSelect(`element:${element.id}`);
    } else if (use.path === 'cover.image') onSelect('photo');
    else if (use.area === 'book')
      window.location.assign(`/books/${encodeURIComponent(projectKey)}/interior`);
    else if (use.path.startsWith('cover.fonts')) setTab('fonts');
  };
  return (
    <section className="cover-panel cover-tools" aria-label="Cover tools">
      {cover.version < 3 && (
        <div className="legacy-banner">
          <p>
            This cover uses the version {cover.version} single-photo layout. Convert it to a region
            design to add layers and shapes, or apply a template.
          </p>
          <button type="button" className="small-button" onClick={onConvert}>
            Convert to region design…
          </button>
        </div>
      )}
      <RegionPicker region={region} onChange={onRegion} />
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
        {tab === 'templates' && (
          <TemplatesTab projectKey={projectKey} source={source} onApply={onApplyTemplate} />
        )}
        {tab === 'layers' && (
          <LayersTab
            cover={cover}
            selected={selected}
            onSelect={onSelect}
            update={update}
            onConvert={onConvert}
          />
        )}
        {tab === 'photo' && (
          <PhotoLibrary
            projectKey={projectKey}
            cover={cover}
            library={library}
            trial={trial}
            onTrial={cover.image ? onTrial : undefined}
            onChoose={onChoosePhoto}
            notice={notice}
            setNotice={setNotice}
            placeLabel={
              cover.version >= 3
                ? `Place on ${region === 'wrap' ? 'the full wrap' : `the ${region}`}`
                : undefined
            }
            source={source}
            onShowUse={showUse}
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
        {tab === 'shapes' && (
          <ShapesTab
            cover={cover}
            layout={layout}
            region={region}
            update={update}
            onSelect={onSelect}
            onConvert={onConvert}
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
        {tab === 'assets' && (
          <AssetsPanel
            projectKey={projectKey}
            draft={source}
            licenses={licenses}
            onShowUse={showUse}
          />
        )}
        {tab === 'design' && (
          <DesignTab
            projectKey={projectKey}
            source={source}
            cover={cover}
            update={update}
            issues={issues}
            onConvert={onConvert}
          />
        )}
      </div>
    </section>
  );
}
