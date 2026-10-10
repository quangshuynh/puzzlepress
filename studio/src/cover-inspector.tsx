import type { ReactNode } from 'react';
import { ColorField, EyeIcon, Segmented } from './cover-tools';
import {
  METADATA_ROLES,
  extraLayer,
  layerName,
  layerOf,
  removeExtra,
  resetLayer,
  round,
  setLayer,
} from './cover-model';
import { FieldErrors, matchIssues, type Source } from './editor-fields';
import { measureText } from './Print';
import type {
  BuildDiagnostic,
  CoverCheck,
  CoverConfig,
  CoverDraft,
  CoverLibrary,
  CoverReport,
  CoverResolution,
  CoverStatus,
  Issue,
  PreflightFinding,
  TextLayer,
  TextRole,
} from './types';
import { Status } from './ui';

// The contextual inspector. Values shown are authored overrides or Python's
// measurements; nothing here decides a position, size or verdict.

const BUNDLED: [string, string][] = [
  ['serif-display', 'Newsreader Display'],
  ['serif', 'Newsreader'],
  ['serif-italic', 'Newsreader Italic'],
  ['sans', 'Vera Sans'],
  ['sans-bold', 'Vera Sans Bold'],
  ['sans-italic', 'Vera Sans Oblique'],
];
const SEVERITY = {
  error: ['fail', 'Blocking'],
  warning: ['review', 'Warning'],
  info: ['neutral', 'Note'],
} as const;
const BOOK_FIELD: Record<string, keyof Source['book']> = {
  title: 'title',
  subtitle: 'subtitle',
  author: 'author',
  imprint: 'imprint',
};

function NumberField({
  id,
  label,
  value,
  placeholder,
  min,
  max,
  step,
  unit,
  onChange,
  issues,
  path,
}: {
  id: string;
  label: string;
  value: number | undefined;
  placeholder?: string;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (value: number | undefined) => void;
  issues: Issue[];
  path: string;
}) {
  const matching = matchIssues(issues, path);
  return (
    <div className="editor-field number-field">
      <label htmlFor={id}>{label}</label>
      <div>
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min={min}
          max={max}
          step={step}
          value={value ?? ''}
          placeholder={placeholder}
          aria-invalid={matching.length ? true : undefined}
          aria-describedby={matching.length ? `${path}-issues` : undefined}
          onChange={(event) => {
            const text = event.target.value;
            onChange(text === '' ? undefined : Number(text));
          }}
        />
        {unit && <span className="unit">{unit}</span>}
      </div>
      <FieldErrors id={path} issues={matching} />
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="inspector-group">
      <legend>{title}</legend>
      {children}
    </fieldset>
  );
}

export function LayerInspector({
  layer,
  cover,
  book,
  library,
  checks,
  issues,
  update,
  onSelect,
}: {
  layer: string;
  cover: CoverConfig;
  book: Source['book'];
  library?: CoverLibrary;
  checks: CoverCheck[];
  issues: Issue[];
  update: (next: CoverConfig) => void;
  onSelect: (layer: string | null) => void;
}) {
  const extra = layer.startsWith('extra:') ? extraLayer(cover, layer.slice(6)) : undefined;
  const extraIndex = extra ? (cover.extra ?? []).indexOf(extra) : -1;
  const path = extra ? `cover.extra.${extraIndex}` : `cover.text.${layer}`;
  const values: TextLayer = layerOf(cover, layer);
  const set = (patch: Partial<TextLayer>) => update(setLayer(cover, layer, patch));
  const name = layerName(cover, layer);
  const role = layer as TextRole;
  const metadata = METADATA_ROLES.includes(role);
  const bookValue = metadata ? (book[BOOK_FIELD[layer]] as string | null | undefined) : undefined;
  const hidden = values.visible === false;
  const fontKeys = [
    ...BUNDLED,
    ...(cover.fonts ?? []).map((font): [string, string] => {
      const facts = library?.fonts.find((f) => f.path === font.path);
      return [font.id, `${facts?.full_name ?? font.id} (imported)`];
    }),
  ];
  const chosen = values.font;
  const missing = chosen
    ? (library?.bundled_fonts.find((f) => f.key === chosen)?.missing ??
      library?.fonts.find((f) => f.path === cover.fonts?.find((c) => c.id === chosen)?.path)
        ?.missing ??
      [])
    : [];
  const layerChecks = checks.filter((check) => check.layer === layer);
  const offset = values.offset ?? { x: 0, y: 0 };
  return (
    <div className="inspector-body" aria-label={`${name} properties`}>
      <div className="inspector-heading">
        <h3>{name}</h3>
        <button
          type="button"
          className="icon-button"
          aria-pressed={!hidden}
          aria-label={`${hidden ? 'Show' : 'Hide'} ${name.toLowerCase()} on the cover`}
          onClick={() => set({ visible: hidden })}
        >
          <EyeIcon open={!hidden} />
        </button>
      </div>
      {layerChecks.map((check) => (
        <p key={check.code} className={`inspector-check ${check.severity}`}>
          <Status tone={SEVERITY[check.severity][0]}>{SEVERITY[check.severity][1]}</Status>{' '}
          {check.message}
        </p>
      ))}
      <Group title="Text">
        {layer === 'back_text' ? (
          <div className="editor-field">
            <label htmlFor="cover-back-text">Back-cover text</label>
            <textarea
              id="cover-back-text"
              rows={5}
              value={cover.back_text ?? ''}
              aria-describedby="cover-back-hint"
              aria-invalid={matchIssues(issues, 'cover.back_text').length ? true : undefined}
              onChange={(e) => {
                const next = { ...cover, back_text: e.target.value || undefined };
                if (next.back_text === undefined) delete next.back_text;
                update(next);
              }}
            />
            <p className="small muted field-hint" id="cover-back-hint">
              Plain text, up to 1,200 characters. Nothing else is added: no prices, reviews or ISBN.
            </p>
            <FieldErrors id="cover.back_text" issues={matchIssues(issues, 'cover.back_text')} />
          </div>
        ) : extra ? (
          <div className="editor-field">
            <label htmlFor="cover-layer-text">Text</label>
            <textarea
              id="cover-layer-text"
              rows={3}
              value={extra.text}
              onChange={(e) => set({ text: e.target.value })}
            />
            <FieldErrors id={`${path}.text`} issues={matchIssues(issues, `${path}.text`)} />
          </div>
        ) : (
          <div className="editor-field">
            <label htmlFor="cover-layer-text">Text on the cover</label>
            <textarea
              id="cover-layer-text"
              rows={2}
              value={values.text ?? bookValue ?? ''}
              aria-describedby="cover-layer-text-hint"
              onChange={(e) =>
                set({
                  text: e.target.value === (bookValue ?? '') ? undefined : e.target.value,
                })
              }
            />
            <p className="small muted field-hint" id="cover-layer-text-hint">
              {values.text === undefined
                ? `From the book details. Add line breaks here; the book's ${layer} stays unchanged.`
                : `Book details: “${bookValue ?? 'none'}”. KDP requires the cover to match them, apart from line breaks and capitals.`}
            </p>
            {values.text !== undefined && (
              <button
                type="button"
                className="small-button"
                onClick={() => set({ text: undefined })}
              >
                Use the book&apos;s {layer}
              </button>
            )}
            <FieldErrors id={`${path}.text`} issues={matchIssues(issues, `${path}.text`)} />
          </div>
        )}
      </Group>
      <Group title="Typography">
        <div className="editor-field">
          <label htmlFor="cover-layer-font">Font</label>
          <select
            id="cover-layer-font"
            value={values.font ?? ''}
            onChange={(e) => set({ font: e.target.value || undefined })}
            aria-invalid={matchIssues(issues, `${path}.font`).length ? true : undefined}
          >
            <option value="">Preset default</option>
            {fontKeys.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
          {missing.length > 0 && (
            <p className="small field-errors">This font lacks: {missing.join(' ')}</p>
          )}
          <FieldErrors id={`${path}.font`} issues={matchIssues(issues, `${path}.font`)} />
        </div>
        <div className="field-pair">
          <NumberField
            id="cover-layer-size"
            label="Size"
            unit="pt"
            min={4}
            max={160}
            step={0.5}
            value={values.size}
            placeholder="Auto"
            path={`${path}.size`}
            issues={issues}
            onChange={(size) => set({ size })}
          />
          <NumberField
            id="cover-layer-line"
            label="Line spacing"
            unit="×"
            min={0.8}
            max={3}
            step={0.05}
            value={values.line_spacing}
            placeholder="Preset"
            path={`${path}.line_spacing`}
            issues={issues}
            onChange={(line_spacing) => set({ line_spacing })}
          />
        </div>
        <div className="field-pair">
          <NumberField
            id="cover-layer-letter"
            label="Letter spacing"
            unit="pt"
            min={-2}
            max={20}
            step={0.25}
            value={values.letter_spacing}
            placeholder="0"
            path={`${path}.letter_spacing`}
            issues={issues}
            onChange={(letter_spacing) => set({ letter_spacing })}
          />
          <div className="editor-field">
            <label htmlFor="cover-layer-case">Letter case</label>
            <select
              id="cover-layer-case"
              value={values.case ?? ''}
              onChange={(e) => set({ case: (e.target.value || undefined) as TextLayer['case'] })}
            >
              <option value="">Preset</option>
              <option value="as_written">As written</option>
              <option value="upper">Capitals</option>
            </select>
          </div>
        </div>
        <ColorField
          id="cover-layer-color"
          label="Color"
          value={values.color ?? ''}
          fallback={cover.type.tone === 'dark' ? '#1b1e1c' : '#ffffff'}
          issues={matchIssues(issues, `${path}.color`)}
          path={`${path}.color`}
          onChange={(color) => set({ color: color || undefined })}
          extra={
            values.color ? (
              <button
                type="button"
                className="small-button"
                onClick={() => set({ color: undefined })}
              >
                Tone
              </button>
            ) : (
              <span className="small muted">Text tone</span>
            )
          }
        />
        <Segmented
          legend="Alignment"
          value={values.align}
          path={`${path}.align`}
          issues={issues}
          options={[
            ['left', 'Left'],
            ['center', 'Center'],
            ['right', 'Right'],
          ]}
          onChange={(align) => set({ align: values.align === align ? undefined : align })}
        />
      </Group>
      <Group title="Position">
        <div className="field-pair">
          <NumberField
            id="cover-layer-x"
            label="Across (right +)"
            unit="pt"
            min={-1200}
            max={1200}
            step={1}
            value={offset.x}
            path={`${path}.offset.x`}
            issues={issues}
            onChange={(x) => set({ offset: { ...offset, x: round(x ?? 0, 2) } })}
          />
          <NumberField
            id="cover-layer-y"
            label="Up (+) / down"
            unit="pt"
            min={-1200}
            max={1200}
            step={1}
            value={offset.y}
            path={`${path}.offset.y`}
            issues={issues}
            onChange={(y) => set({ offset: { ...offset, y: round(y ?? 0, 2) } })}
          />
        </div>
        <p className="small muted">
          Offsets from the layout&apos;s own position, in points (72 per inch). Drag on the canvas
          or use arrow keys there (Shift moves 10 pt).
        </p>
        <button
          type="button"
          className="small-button"
          disabled={!values.offset}
          onClick={() => set({ offset: undefined })}
        >
          Reset position
        </button>
      </Group>
      <div className="button-row">
        <button
          type="button"
          className="small-button"
          onClick={() => update(resetLayer(cover, layer))}
          disabled={Object.keys(values).filter((k) => k !== 'text' || !extra).length === 0}
        >
          Reset to layout defaults
        </button>
        {extra && (
          <button
            type="button"
            className="small-button"
            onClick={() => {
              update(removeExtra(cover, extra.id));
              onSelect(null);
            }}
          >
            Delete layer
          </button>
        )}
      </div>
    </div>
  );
}

function Slider({
  id,
  label,
  value,
  min,
  max,
  step,
  display,
  onChange,
  issues,
  path,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  display: string;
  onChange: (value: number) => void;
  issues: Issue[];
  path: string;
}) {
  const matching = matchIssues(issues, path);
  return (
    <div className="editor-field cover-slider">
      <div className="cover-slider-label">
        <label htmlFor={id}>{label}</label>
        <output htmlFor={id} aria-hidden="true">
          {display}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-valuetext={display}
        aria-invalid={matching.length ? true : undefined}
        aria-describedby={matching.length ? `${path}-issues` : undefined}
        onChange={(e) => onChange(round(Number(e.target.value)))}
      />
      <FieldErrors id={path} issues={matching} />
    </div>
  );
}

export function PrintQuality({ resolution }: { resolution: CoverResolution }) {
  const pass = resolution.status === 'ok';
  const zoomedOut = resolution.max_dpi + 1e-9 >= resolution.minimum_dpi;
  return (
    <section className="print-quality" aria-labelledby="print-quality-heading">
      <h4 id="print-quality-heading">Print quality</h4>
      <div className="dpi-meter">
        <span className={`dpi-value ${pass ? 'pass' : 'fail'}`}>
          {Math.round(resolution.effective_dpi)}
          <small> DPI</small>
        </span>
        <Status tone={pass ? 'pass' : 'fail'}>
          {pass ? 'Meets' : 'Below'} the {resolution.minimum_dpi} DPI KDP minimum
        </Status>
      </div>
      <dl className="facts compact-facts">
        <div>
          <dt>Used pixels</dt>
          <dd>
            {Math.round(resolution.used_pixels[0])} × {Math.round(resolution.used_pixels[1])} of{' '}
            {resolution.source_pixels[0]} × {resolution.source_pixels[1]}
          </dd>
        </div>
        <div>
          <dt>Printed size</dt>
          <dd>
            {resolution.printed_inches[0].toFixed(2)} × {resolution.printed_inches[1].toFixed(2)} in
          </dd>
        </div>
        <div>
          <dt>Best possible</dt>
          <dd>{Math.round(resolution.max_dpi)} DPI at zoom 1</dd>
        </div>
      </dl>
      <p className="small muted">
        Effective DPI is the source pixels the crop uses divided by the printed inches. Zooming in
        uses fewer pixels over the same area, so DPI falls; photos are never upscaled.{' '}
        {pass
          ? ''
          : zoomedOut
            ? `Zoom out to reach ${resolution.minimum_dpi} DPI.`
            : `Even at zoom 1 this photograph reaches ${Math.round(resolution.max_dpi)} DPI; use one with more pixels (about ${Math.ceil((resolution.printed_inches[0] * resolution.minimum_dpi) / 100) * 100} px wide).`}
      </p>
    </section>
  );
}

export function PhotoInspector({
  cover,
  resolution,
  center,
  update,
  issues,
}: {
  cover: CoverConfig;
  resolution?: CoverResolution;
  center?: [number, number];
  update: (next: CoverConfig) => void;
  issues: Issue[];
}) {
  const crop = cover.crop;
  const setCrop = (next: Partial<CoverConfig['crop']>) =>
    update({ ...cover, crop: { ...crop, ...next } });
  return (
    <div className="inspector-body" aria-label="Photograph properties">
      <div className="inspector-heading">
        <h3>Photograph</h3>
      </div>
      <p className="small muted photo-name">{cover.image.path.replace('cover-assets/', '')}</p>
      <Group title="Crop and position">
        <Slider
          id="cover-crop-x"
          label="Focal point, left to right"
          path="cover.crop.x"
          issues={issues}
          value={crop.x}
          min={0}
          max={1}
          step={0.005}
          display={`${Math.round(crop.x * 100)}%`}
          onChange={(x) => setCrop({ x })}
        />
        <Slider
          id="cover-crop-y"
          label="Focal point, top to bottom"
          path="cover.crop.y"
          issues={issues}
          value={crop.y}
          min={0}
          max={1}
          step={0.005}
          display={`${Math.round(crop.y * 100)}%`}
          onChange={(y) => setCrop({ y })}
        />
        <Slider
          id="cover-crop-zoom"
          label="Zoom"
          path="cover.crop.zoom"
          issues={issues}
          value={crop.zoom}
          min={1}
          max={4}
          step={0.01}
          display={`${crop.zoom.toFixed(2)}x`}
          onChange={(zoom) => setCrop({ zoom })}
        />
        <button
          type="button"
          className="small-button"
          onClick={() => setCrop({ x: 0.5, y: 0.5, zoom: 1 })}
        >
          Reset crop
        </button>
        {center && (
          <p className="small muted">
            Applied focal point {Math.round(center[0] * 100)}%, {Math.round(center[1] * 100)}% (kept
            inside the photo). It scales evenly and is never stretched.
          </p>
        )}
      </Group>
      {resolution && <PrintQuality resolution={resolution} />}
    </div>
  );
}

function CoverFindings({ report }: { report: CoverReport }) {
  const rules = new Map(report.rules.map((r) => [r.code, r]));
  const groups: [string, PreflightFinding['severity']][] = [
    ['Blocking', 'error'],
    ['Warnings', 'warning'],
  ];
  return (
    <section className="cover-findings" aria-labelledby="cover-findings-heading">
      <h4 id="cover-findings-heading">Cover preflight</h4>
      <p className="small muted">
        Ruleset {report.ruleset.id} v{report.ruleset.version}; KDP rules checked{' '}
        {report.ruleset.kdp_rules_checked}. Amazon KDP remains the final authority.
      </p>
      {report.findings.length === 0 && (
        <p>
          <Status tone="pass">No findings</Status> Every modeled cover check passed.
        </p>
      )}
      {groups.map(([heading, severity]) => {
        const items = report.findings.filter((f) => f.severity === severity);
        if (!items.length) return null;
        return (
          <div key={severity}>
            <h5>
              {heading} ({items.length})
            </h5>
            <ul className="finding-list">
              {items.map((finding, i) => (
                <li key={i}>
                  <div className="finding-head">
                    <Status tone={SEVERITY[severity][0]}>{SEVERITY[severity][1]}</Status>
                    <span className="finding-scope">
                      {finding.scope === 'kdp' ? 'KDP readiness' : 'Structural'}
                    </span>
                  </div>
                  <strong>{rules.get(finding.rule)?.title ?? finding.rule}</strong>
                  <p>{finding.message}</p>
                  {finding.measure && (
                    <p className="finding-measure">{measureText(finding.measure)}</p>
                  )}
                  <p className="finding-meta">
                    <code>{finding.rule}</code>
                  </p>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      <details className="details rule-list">
        <summary>
          Passed and other checks ({report.rules.filter((r) => r.outcome !== 'failed').length})
        </summary>
        <ul>
          {report.rules
            .filter((r) => r.outcome !== 'failed')
            .map((rule) => (
              <li key={rule.code}>
                <strong>{rule.title}</strong>{' '}
                <span className="muted">{rule.outcome.replaceAll('_', ' ')}</span>
                {rule.note && <p>{rule.note}</p>}
                <p className="small muted">
                  {rule.source}
                  {rule.basis === 'kdp_ambiguous' ? ' · official wording is ambiguous' : ''} ·{' '}
                  <code>{rule.code}</code>
                </p>
              </li>
            ))}
        </ul>
      </details>
    </section>
  );
}

const STATE_NOTES: Record<string, ReactNode> = {
  missing: 'No cover has been built. Build cover writes cover.pdf beside the interior.',
  stale: (
    <>
      <strong>The built cover is out of date.</strong> Its photograph, crop, design, text, or the
      interior&apos;s page count or paper changed. Rebuild the cover.
    </>
  ),
  invalid: (
    <>
      <strong>The built cover failed structural checks.</strong> See the blocking findings.
    </>
  ),
};
const SPINE_REASONS: Record<string, string> = {
  page_count: 'Omitted: KDP prints spine text only on books of 80 pages or more.',
  spine_too_narrow: 'Omitted: this spine is too narrow for 7 pt type with KDP clearances.',
  authored: 'Off: this cover has no spine text.',
};

export function Failure({
  stage,
  diagnostics,
}: {
  stage?: string;
  diagnostics: BuildDiagnostic[];
}) {
  return (
    <div role="alert" className="notice error compact-notice">
      <h3>The cover did not build</h3>
      <p>Stage {stage}. Nothing was written; any previous cover is unchanged.</p>
      <ul className="issue-list">
        {diagnostics.map((item, i) => (
          <li key={i}>
            <strong>{item.message}</strong> <code>{item.code}</code>
            {item.actual && ` · measured ${item.actual}; allowed ${item.required}`}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Readiness({
  dirty,
  draft,
  status,
  busy,
  onBuild,
  onSelect,
}: {
  dirty: boolean;
  draft?: CoverDraft;
  status?: CoverStatus;
  busy: boolean;
  onBuild: () => void;
  onSelect: (layer: string | null) => void;
}) {
  const layout = draft?.layout;
  const interior = draft?.interior;
  const report = status?.report;
  const checks = draft?.checks ?? [];
  return (
    <div
      className="inspector-body cover-readiness"
      aria-label="Cover readiness"
      role="complementary"
    >
      <h3>Checks</h3>
      {interior?.stale && (
        <p className="print-state">
          <strong>The interior is out of date.</strong> {interior.stale} The spine uses its last
          build.
        </p>
      )}
      {checks.length > 0 ? (
        <ul className="finding-list cover-checks">
          {checks.map((check, i) => (
            <li key={`${check.code}-${i}`}>
              <Status tone={SEVERITY[check.severity][0]}>{SEVERITY[check.severity][1]}</Status>
              <p>{check.message}</p>
              {check.layer && !check.layer.startsWith('font:') && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => onSelect(check.layer!)}
                >
                  Select {check.layer.replace('_', ' ').replace('extra:', 'text ')}
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        draft?.success && <p className="small muted">No draft findings.</p>
      )}
      {layout && interior && (
        <dl className="facts compact-facts">
          <div>
            <dt>Interior</dt>
            <dd>
              {interior.page_count} pages · {interior.paper} paper · {interior.trim_in[0]} x{' '}
              {interior.trim_in[1]} in
            </dd>
          </div>
          <div>
            <dt>Spine width</dt>
            <dd>
              {layout.geometry.spine_width_in.toFixed(4)} in{' '}
              <span className="muted">
                ({interior.page_count} x {interior.paper === 'cream' ? '0.0025' : '0.002252'} in)
              </span>
            </dd>
          </div>
          <div>
            <dt>Full wrap</dt>
            <dd>
              {layout.geometry.width_in.toFixed(4)} x {layout.geometry.height_in.toFixed(4)} in with
              bleed
            </dd>
          </div>
          <div>
            <dt>Spine text</dt>
            <dd>
              {layout.spine_text.rendered
                ? `Printed at ${layout.spine_text.size} pt`
                : SPINE_REASONS[layout.spine_text.reason ?? 'authored']}
            </dd>
          </div>
        </dl>
      )}
      <h3>Built cover</h3>
      {status && STATE_NOTES[status.state] && (
        <p className={`print-state ${status.state}`}>{STATE_NOTES[status.state]}</p>
      )}
      {report && status?.state !== 'missing' && (
        <dl className="print-verdict" aria-label="Cover preflight status">
          <div>
            <dt>Structural</dt>
            <dd>
              {report.structural.status === 'valid' ? (
                <Status tone="pass">Valid</Status>
              ) : (
                <Status tone="fail">Invalid</Status>
              )}
            </dd>
          </div>
          <div>
            <dt>KDP readiness</dt>
            <dd>
              {report.kdp.status === 'ready' ? (
                <Status tone="pass">Ready</Status>
              ) : (
                <Status tone="fail">Not ready</Status>
              )}
            </dd>
          </div>
        </dl>
      )}
      <button
        type="button"
        className="primary"
        disabled={busy || dirty || !status || draft?.buildable === false}
        onClick={onBuild}
      >
        {status?.state === 'missing' ? 'Build cover' : 'Rebuild cover'}
      </button>
      {dirty && (
        <p className="draft-status small">Save the draft first: covers build from saved source.</p>
      )}
      {!dirty && draft?.buildable === false && (
        <p className="draft-status small">Fix the blocking checks above before building.</p>
      )}
      {status?.build && !status.build.success && (
        <Failure stage={status.build.stage} diagnostics={status.build.diagnostics ?? []} />
      )}
      {report && status?.state !== 'missing' && <CoverFindings report={report} />}
    </div>
  );
}

export function flaggedLayers(checks: CoverCheck[]): Set<string> {
  return new Set(checks.filter((c) => c.severity === 'error' && c.layer).map((c) => c.layer!));
}
