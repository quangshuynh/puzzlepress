import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, request, upload } from './api';
import { DraftToolbar, type Draft } from './draft';
import { FieldErrors, matchIssues, type Source } from './editor-fields';
import { measureText } from './Print';
import type {
  BuildDiagnostic,
  CoverAsset,
  CoverConfig,
  CoverDraft,
  CoverGeometry,
  CoverLayoutView,
  CoverReport,
  CoverStatus,
  Issue,
  PreflightFinding,
  PtBox,
} from './types';
import { ErrorState, Loading, Status } from './ui';

// Cover Studio. The preview is a PDFium raster of a real cover PDF rendered by
// Python from the draft; geometry, crop windows, DPI, spine eligibility and
// verdicts all come from Python. This view edits semantic values and maps a
// drag or key press onto the normalized focal point; it never lays out a cover.

const VIEWS = [
  ['wrap', 'Full wrap'],
  ['front', 'Front'],
  ['spine', 'Spine'],
  ['back', 'Back'],
] as const;
type View = (typeof VIEWS)[number][0];
const OVERLAYS = [
  ['trim', 'Trim and folds', 'Final size and the two spine folds'],
  ['bleed', 'Bleed', '0.125 in printed beyond the trim, cut away'],
  ['safe', 'KDP safe areas', 'Text 0.125 in inside trim and folds; spine 0.0625 in'],
  ['design', 'Type area', 'PuzzlePress keeps type 0.5 in from panel edges'],
  ['barcode', 'Barcode area', 'Lower-right back corner reserved for KDP'],
  ['text', 'Text bounds', 'Measured extent of every line'],
] as const;
type Overlay = (typeof OVERLAYS)[number][0];
const STYLES: [CoverConfig['type']['style'], string, string][] = [
  ['editorial', 'Editorial', 'Newsreader serif, quiet and bookish'],
  ['bold', 'Bold', 'Capitals in heavy sans, for strong photographs'],
  ['minimal', 'Minimal', 'Light sans, small and restrained'],
];
const SPINE_REASONS: Record<string, string> = {
  page_count: 'Omitted: KDP prints spine text only on books of 80 pages or more.',
  spine_too_narrow: 'Omitted: this spine is too narrow for 7 pt type with KDP clearances.',
  authored: 'Off: this cover has no spine text.',
};
const RESOLUTION: Record<string, [string, 'pass' | 'fail']> = {
  ok: ['Sufficient', 'pass'],
  image_low_effective_dpi: ['Too low: zoom out', 'fail'],
  image_too_small: ['Too low: photo too small', 'fail'],
};
// Layout-independent fallbacks for keys whose `key` value varies by keyboard.
const KEY_CODES: Record<string, string> = {
  Equal: '=',
  NumpadAdd: '+',
  Minus: '-',
  NumpadSubtract: '-',
  Digit0: '0',
  Numpad0: '0',
};
const STEP = 0.01;
const BIG_STEP = 0.05;

function round4(value: number) {
  return Math.round(value * 10000) / 10000;
}
function clamp(value: number, low: number, high: number) {
  return Math.min(high, Math.max(low, value));
}

export function starterCover(image: { path: string; sha256: string }): CoverConfig {
  return {
    version: 1,
    layout: 'full_wrap',
    image,
    crop: { x: 0.5, y: 0.5, zoom: 1 },
    type: { style: 'editorial', position: 'top', align: 'center', tone: 'light' },
    legibility: 'shade',
    background: '#26302b',
    spine_text: 'auto',
  };
}

// The part of the wrap each view shows, in PDF points (origin bottom-left).
export function viewBox(g: CoverGeometry, view: View): PtBox {
  const { media, front, back, spine } = g.regions;
  if (view === 'front')
    return { x: front.x, y: 0, width: media.width - front.x, height: media.height };
  if (view === 'back') return { x: 0, y: 0, width: back.x + back.width, height: media.height };
  if (view === 'spine') {
    const width = Math.min(media.width, Math.max(spine.width + 144, 216));
    const x = clamp(spine.x + spine.width / 2 - width / 2, 0, media.width - width);
    return { x, y: 0, width, height: media.height };
  }
  return media;
}

// A drag of (dx, dy) screen pixels at `scale` px/pt moves the focal point so the
// photograph follows the pointer. Uses Python's applied (clamped) window.
export function dragFocal(layout: CoverLayoutView, dx: number, dy: number, scale: number) {
  const { region, window, center } = layout.photo;
  const du = (-dx / scale / region.width) * (window.right - window.left);
  const dv = (-dy / scale / region.height) * (window.bottom - window.top);
  return { x: round4(clamp(center[0] + du, 0, 1)), y: round4(clamp(center[1] + dv, 0, 1)) };
}

function Rect({ box, className }: { box: PtBox; className: string }) {
  return (
    <rect
      className={className}
      x={box.x}
      y={-(box.y + box.height)}
      width={box.width}
      height={box.height}
      vectorEffect="non-scaling-stroke"
    />
  );
}

function OverlayLayer({
  layout,
  box,
  overlays,
}: {
  layout: CoverLayoutView;
  box: PtBox;
  overlays: Set<Overlay>;
}) {
  const r = layout.geometry.regions;
  const m = r.media;
  return (
    <svg
      className="cover-overlay"
      viewBox={`${box.x} ${-(box.y + box.height)} ${box.width} ${box.height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      data-testid="cover-overlay"
    >
      {overlays.has('bleed') && (
        <path
          className="overlay-bleed"
          fillRule="evenodd"
          d={`M${m.x},${-m.y} H${m.x + m.width} V${-(m.y + m.height)} H${m.x} Z M${r.trim.x},${-r.trim.y} V${-(r.trim.y + r.trim.height)} H${r.trim.x + r.trim.width} V${-r.trim.y} Z`}
        />
      )}
      {overlays.has('trim') && (
        <>
          <Rect box={r.trim} className="overlay-trim" />
          {[r.spine.x, r.spine.x + r.spine.width].map((x) => (
            <line
              key={x}
              className="overlay-fold"
              x1={x}
              x2={x}
              y1={-m.height}
              y2={0}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </>
      )}
      {overlays.has('safe') &&
        (['front_safe', 'back_safe', 'spine_safe'] as const).map((k) => (
          <Rect key={k} box={r[k]} className="overlay-kdp" />
        ))}
      {overlays.has('design') &&
        (['front_design', 'back_design'] as const).map((k) => (
          <Rect key={k} box={r[k]} className="overlay-live" />
        ))}
      {overlays.has('barcode') && (
        <>
          <Rect box={r.barcode_keep_clear} className="overlay-barcode-zone" />
          <Rect box={r.barcode} className="overlay-barcode" />
        </>
      )}
      {overlays.has('text') &&
        layout.texts.map((t, i) => <Rect key={i} box={t.box} className="overlay-element" />)}
    </svg>
  );
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setWidth(element.clientWidth || 720);
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function Stage({
  projectKey,
  layout,
  pdf,
  scales,
  label,
  overlays,
  canCrop,
  onCrop,
  onNudge,
}: {
  projectKey: string;
  layout: CoverLayoutView;
  pdf: string;
  scales: Record<string, number>;
  label: string;
  overlays: Set<Overlay> | null;
  canCrop: boolean;
  onCrop: (focal: { x: number; y: number }) => void;
  onNudge: (key: string, big: boolean) => boolean;
}) {
  const [view, setView] = useState<View>('wrap');
  const [frame, frameWidth] = useWidth();
  const [drag, setDrag] = useState<{ x: number; y: number; dx: number; dy: number } | null>(null);
  const g = layout.geometry;
  const box = viewBox(g, view);
  const viewport = typeof window === 'undefined' ? 900 : window.innerHeight;
  const scale = Math.max(
    0.05,
    Math.min((frameWidth - 2) / box.width, (viewport * 0.62) / box.height),
  );
  const dpr = typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1;
  const size = scale * dpr <= scales.preview * 1.05 ? 'preview' : 'detail';
  const src = `/api/projects/${encodeURIComponent(projectKey)}/cover/preview?size=${size}&pdf=${pdf}`;
  const media = g.regions.media;
  const offset = drag ? `translate(${drag.dx}px, ${drag.dy}px)` : undefined;
  const viewName = VIEWS.find(([v]) => v === view)![1].toLowerCase();
  return (
    <section className="cover-stage" aria-label="Cover preview">
      <div className="print-toolbar" role="toolbar" aria-label="Cover view">
        <div role="group" aria-label="View" className="print-nav">
          {VIEWS.map(([key, name]) => (
            <button
              key={key}
              type="button"
              aria-pressed={view === key}
              onClick={() => setView(key)}
            >
              {name}
            </button>
          ))}
        </div>
        <p className="small muted cover-size">
          {g.width_in.toFixed(3)} x {g.height_in.toFixed(3)} in · spine{' '}
          {g.spine_width_in.toFixed(4)} in
        </p>
      </div>
      <div
        className={`cover-canvas${canCrop ? ' croppable' : ''}`}
        ref={frame}
        tabIndex={0}
        role="group"
        aria-roledescription="cover preview"
        aria-label={`${label}, ${viewName} view. ${
          canCrop
            ? 'Drag to move the photograph. Arrow keys move the focal point (Shift for larger steps); plus and minus zoom; 0 resets the crop.'
            : ''
        }`}
        onKeyDown={(event) => {
          if (!canCrop) return;
          const known = ['+', '=', '-', '0'].includes(event.key) || event.key.startsWith('Arrow');
          const key = known ? event.key : (KEY_CODES[event.code] ?? event.key);
          if (onNudge(key, event.shiftKey)) event.preventDefault();
        }}
        onPointerDown={(event) => {
          if (!canCrop || event.button !== 0) return;
          event.currentTarget.setPointerCapture?.(event.pointerId);
          setDrag({ x: event.clientX, y: event.clientY, dx: 0, dy: 0 });
        }}
        onPointerMove={(event) => {
          if (drag) setDrag({ ...drag, dx: event.clientX - drag.x, dy: event.clientY - drag.y });
        }}
        onPointerUp={() => {
          if (drag && (Math.abs(drag.dx) > 2 || Math.abs(drag.dy) > 2))
            onCrop(dragFocal(layout, drag.dx, drag.dy, scale));
          setDrag(null);
        }}
        onPointerCancel={() => setDrag(null)}
      >
        <div
          className="cover-window"
          style={{ width: box.width * scale, height: box.height * scale }}
        >
          <img
            src={src}
            alt={`${label}: ${viewName} view of the rendered cover PDF`}
            draggable={false}
            width={Math.round(media.width * scale)}
            height={Math.round(media.height * scale)}
            style={{
              left: -box.x * scale,
              top: -(media.height - (box.y + box.height)) * scale,
              transform: offset,
            }}
          />
          {overlays && overlays.size > 0 && !drag && (
            <OverlayLayer layout={layout} box={box} overlays={overlays} />
          )}
        </div>
      </div>
    </section>
  );
}

function Choice<T extends string>({
  legend,
  name,
  value,
  options,
  onChange,
  issues,
  path,
}: {
  legend: string;
  name: string;
  value: T;
  options: [T, string, string?][];
  onChange: (value: T) => void;
  issues: Issue[];
  path: string;
}) {
  const matching = matchIssues(issues, path);
  return (
    <fieldset
      className="choice-group"
      aria-describedby={matching.length ? `${path}-issues` : undefined}
    >
      <legend>{legend}</legend>
      {options.map(([v, text, hint]) => (
        <label key={v}>
          <input
            type="radio"
            name={name}
            value={v}
            checked={value === v}
            onChange={() => onChange(v)}
          />
          <span>
            {text}
            {hint && <small>{hint}</small>}
          </span>
        </label>
      ))}
      <FieldErrors id={path} issues={matching} />
    </fieldset>
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
        onChange={(e) => onChange(round4(Number(e.target.value)))}
      />
      <FieldErrors id={path} issues={matching} />
    </div>
  );
}

function PhotoPicker({
  projectKey,
  current,
  onChoose,
}: {
  projectKey: string;
  current?: string;
  onChoose: (asset: CoverAsset) => void;
}) {
  const [assets, setAssets] = useState<CoverAsset[]>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const base = `/api/projects/${encodeURIComponent(projectKey)}/cover/assets`;
  useEffect(() => {
    const controller = new AbortController();
    request<{ assets: CoverAsset[] }>(base, controller.signal)
      .then((data) => !controller.signal.aborted && setAssets(data.assets))
      .catch((err: Error) => !controller.signal.aborted && setMessage(err.message));
    return () => controller.abort();
  }, [base]);
  const choose = async (file: File) => {
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      setMessage('Choose a JPEG or PNG photograph.');
      return;
    }
    setBusy(true);
    setMessage(`Copying ${file.name} into the project…`);
    try {
      const data = await upload<{ asset: CoverAsset; assets: CoverAsset[] }>(
        `${base}?name=${encodeURIComponent(file.name)}`,
        new AbortController().signal,
        file,
        file.type,
      );
      setAssets(data.assets);
      setMessage(
        data.asset.reused
          ? `${data.asset.path} was already in the project; selected it.`
          : `Imported ${data.asset.path}; the original file is unchanged. Save to keep this choice.`,
      );
      onChoose(data.asset);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'The photograph was not imported.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <fieldset className="choice-group cover-photos">
      <legend>Photograph</legend>
      {assets === undefined ? (
        <p className="small muted">Reading cover-assets…</p>
      ) : assets.length === 0 ? (
        <p className="small muted">No photographs in this project yet.</p>
      ) : (
        assets.map((asset) => (
          <label key={asset.path}>
            <input
              type="radio"
              name="cover-photo"
              checked={asset.path === current}
              disabled={!asset.sha256}
              onChange={() => onChoose(asset)}
            />
            <span>
              {asset.path.replace('cover-assets/', '')}
              <small>
                {asset.pixels
                  ? `${asset.pixels[0]} x ${asset.pixels[1]} px upright · ${asset.format?.toUpperCase()}${
                      asset.orientation && asset.orientation !== 1
                        ? ` · EXIF orientation ${asset.orientation} applied`
                        : ''
                    }`
                  : `Unusable: ${asset.problem?.replaceAll('_', ' ')}`}
              </small>
            </span>
          </label>
        ))
      )}
      <div className="editor-field">
        <label htmlFor="cover-import">Import a photograph (JPEG or PNG)</label>
        <input
          id="cover-import"
          type="file"
          accept="image/jpeg,image/png"
          disabled={busy}
          aria-describedby="cover-import-hint"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (file) void choose(file);
          }}
        />
        <p className="small muted field-hint" id="cover-import-hint">
          Copied byte-for-byte into this project&apos;s cover-assets folder. Crops never change it,
          and camera or location metadata never reaches cover.pdf.
        </p>
      </div>
      <p role="status" aria-live="polite" className="small">
        {message}
      </p>
    </fieldset>
  );
}

function Controls({
  d,
  cover,
  layout,
  issues,
  update,
}: {
  d: Draft;
  cover: CoverConfig;
  layout?: CoverLayoutView;
  issues: Issue[];
  update: (next: Partial<CoverConfig>) => void;
}) {
  const book = d.draft.book;
  const crop = cover.crop;
  const setCrop = (next: Partial<CoverConfig['crop']>) => update({ crop: { ...crop, ...next } });
  const setType = (next: Partial<CoverConfig['type']>) =>
    update({ type: { ...cover.type, ...next } });
  const back = matchIssues(issues, 'cover.back_text');
  return (
    <div className="cover-controls">
      <PhotoPicker
        projectKey={d.key}
        current={cover.image.path}
        onChoose={(asset) =>
          asset.sha256 && update({ image: { path: asset.path, sha256: asset.sha256 } })
        }
      />
      <FieldErrors id="cover.image" issues={matchIssues(issues, 'cover.image')} />
      <Choice
        legend="Layout"
        name="cover-layout"
        path="cover.layout"
        issues={issues}
        value={cover.layout}
        onChange={(layout) => update({ layout })}
        options={[
          ['full_wrap', 'Full-wrap photograph', 'One photo across back, spine and front'],
          [
            'front_photo',
            'Front photograph',
            'Photo on the front; spine and back in the fill color',
          ],
        ]}
      />
      <fieldset className="choice-group">
        <legend>Crop and position</legend>
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
        <button type="button" onClick={() => setCrop({ x: 0.5, y: 0.5, zoom: 1 })}>
          Reset crop
        </button>
        {layout && (
          <p className="small muted">
            Applied focal point {Math.round(layout.photo.center[0] * 100)}%,{' '}
            {Math.round(layout.photo.center[1] * 100)}% (kept inside the photograph). The photo
            scales evenly; it is never stretched.
          </p>
        )}
      </fieldset>
      <Choice
        legend="Type style"
        name="cover-style"
        path="cover.type.style"
        issues={issues}
        value={cover.type.style}
        onChange={(style) => setType({ style })}
        options={STYLES}
      />
      <Choice
        legend="Title position"
        name="cover-position"
        path="cover.type.position"
        issues={issues}
        value={cover.type.position}
        onChange={(position) => setType({ position })}
        options={[
          ['top', 'Top'],
          ['middle', 'Middle'],
          ['bottom', 'Bottom (author above)'],
        ]}
      />
      <Choice
        legend="Alignment"
        name="cover-align"
        path="cover.type.align"
        issues={issues}
        value={cover.type.align}
        onChange={(align) => setType({ align })}
        options={[
          ['center', 'Centered'],
          ['left', 'Left'],
        ]}
      />
      <Choice
        legend="Text tone"
        name="cover-tone"
        path="cover.type.tone"
        issues={issues}
        value={cover.type.tone}
        onChange={(tone) => setType({ tone })}
        options={[
          ['light', 'Light text', 'For darker photographs'],
          ['dark', 'Dark text', 'For lighter photographs'],
        ]}
      />
      <Choice
        legend="Legibility"
        name="cover-legibility"
        path="cover.legibility"
        issues={issues}
        value={cover.legibility}
        onChange={(legibility) => update({ legibility })}
        options={[
          ['shade', 'Shade', 'Darken or lighten the photo gently behind text'],
          ['panel', 'Panel', 'A solid band of the fill color behind text'],
          ['none', 'None', 'Text directly on the photograph'],
        ]}
      />
      <div className="editor-field cover-color">
        <label htmlFor="cover-background">Fill color</label>
        <div>
          <input
            id="cover-background"
            type="color"
            value={
              /^#[0-9a-fA-F]{6}$/.test(cover.background)
                ? cover.background.toLowerCase()
                : '#26302b'
            }
            onChange={(e) => update({ background: e.target.value })}
            aria-describedby="cover-background-hint"
          />
          <input
            aria-label="Fill color as hex"
            value={cover.background}
            onChange={(e) => update({ background: e.target.value.trim() })}
            aria-invalid={matchIssues(issues, 'cover.background').length ? true : undefined}
          />
        </div>
        <p className="small muted field-hint" id="cover-background-hint">
          Used for panels and wherever the photograph does not print.
        </p>
        <FieldErrors id="cover.background" issues={matchIssues(issues, 'cover.background')} />
      </div>
      <Choice
        legend="Spine text"
        name="cover-spine"
        path="cover.spine_text"
        issues={issues}
        value={cover.spine_text}
        onChange={(spine_text) => update({ spine_text })}
        options={[
          ['auto', 'Title and author when allowed', 'KDP needs 80+ pages and room for 7 pt'],
          ['none', 'No spine text'],
        ]}
      />
      <div className="editor-field">
        <label htmlFor="cover-back-text">Back-cover text (optional)</label>
        <textarea
          id="cover-back-text"
          rows={5}
          value={cover.back_text ?? ''}
          aria-invalid={back.length ? true : undefined}
          aria-describedby={`cover-back-hint${back.length ? ' cover.back_text-issues' : ''}`}
          onChange={(e) => update({ back_text: e.target.value || undefined })}
        />
        <p className="small muted field-hint" id="cover-back-hint">
          Plain text, up to 1,200 characters. Nothing else is added to the back: no prices, reviews
          or ISBN.
        </p>
        <FieldErrors id="cover.back_text" issues={back} />
      </div>
      <div className="cover-copy">
        <h3>Cover text from book details</h3>
        <dl className="facts">
          <div>
            <dt>Title</dt>
            <dd>{book.title}</dd>
          </div>
          <div>
            <dt>Subtitle</dt>
            <dd>{book.subtitle ?? 'None'}</dd>
          </div>
          <div>
            <dt>Author</dt>
            <dd>{book.author ?? 'None'}</dd>
          </div>
          <div>
            <dt>Imprint</dt>
            <dd>{book.imprint ?? 'None'}</dd>
          </div>
        </dl>
        <p className="small muted">
          Edit the title in <a href={`/books/${encodeURIComponent(d.key)}/edit`}>Edit</a> and the
          subtitle, author and imprint on the title page in{' '}
          <a href={`/books/${encodeURIComponent(d.key)}/book`}>Book</a>.
        </p>
      </div>
    </div>
  );
}

const SEVERITY = {
  error: ['fail', 'Blocking'],
  warning: ['review', 'Warning'],
  info: ['neutral', 'Note'],
} as const;

function CoverFindings({ report }: { report: CoverReport }) {
  const rules = new Map(report.rules.map((r) => [r.code, r]));
  const groups: [string, PreflightFinding['severity']][] = [
    ['Blocking', 'error'],
    ['Warnings', 'warning'],
  ];
  return (
    <section className="print-findings cover-findings" aria-labelledby="cover-findings-heading">
      <h3 id="cover-findings-heading">Cover preflight</h3>
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
            <h4>
              {heading} ({items.length})
            </h4>
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

function Failure({ stage, diagnostics }: { stage?: string; diagnostics: BuildDiagnostic[] }) {
  return (
    <div role="alert" className="notice error">
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

function Readiness({
  d,
  draft,
  status,
  busy,
  onBuild,
}: {
  d: Draft;
  draft?: CoverDraft;
  status?: CoverStatus;
  busy: boolean;
  onBuild: () => void;
}) {
  const layout = draft?.layout;
  const interior = draft?.interior;
  const resolution = layout?.resolution;
  const report = status?.report;
  return (
    <aside className="cover-readiness" aria-label="Cover readiness">
      <h3>This draft</h3>
      {interior?.stale && (
        <p className="print-state">
          <strong>The interior is out of date.</strong> {interior.stale} The spine below uses its
          last build.
        </p>
      )}
      {layout && interior ? (
        <dl className="facts">
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
            <dt>Full wrap with bleed</dt>
            <dd>
              {layout.geometry.width_in.toFixed(4)} x {layout.geometry.height_in.toFixed(4)} in
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
          {resolution && (
            <div>
              <dt>Photo resolution</dt>
              <dd>
                <Status tone={RESOLUTION[resolution.status][1]}>
                  {Math.round(resolution.effective_dpi)} DPI · {RESOLUTION[resolution.status][0]}
                </Status>
                <span className="small muted cover-dpi-detail">
                  {Math.round(resolution.used_pixels[0])} x {Math.round(resolution.used_pixels[1])}{' '}
                  source px over {resolution.printed_inches[0].toFixed(2)} x{' '}
                  {resolution.printed_inches[1].toFixed(2)} in; KDP needs {resolution.minimum_dpi};
                  this photo reaches {Math.round(resolution.max_dpi)} at most.
                </span>
              </dd>
            </div>
          )}
        </dl>
      ) : (
        <p className="small muted">The draft preview will report spine width and resolution.</p>
      )}
      {(draft?.checks ?? []).length > 0 && (
        <ul className="finding-list cover-checks">
          {draft!.checks!.map((check) => (
            <li key={check.code}>
              <Status tone={SEVERITY[check.severity][0]}>{SEVERITY[check.severity][1]}</Status>
              <p>{check.message}</p>
            </li>
          ))}
        </ul>
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
        disabled={busy || d.dirty || !status}
        onClick={onBuild}
      >
        {status?.state === 'missing' ? 'Build cover' : 'Rebuild cover'}
      </button>
      {d.dirty && (
        <p className="draft-status small">Save the draft first: covers build from saved source.</p>
      )}
      {status?.build && !status.build.success && (
        <Failure stage={status.build.stage} diagnostics={status.build.diagnostics ?? []} />
      )}
      {report && status?.state !== 'missing' && <CoverFindings report={report} />}
    </aside>
  );
}

export function Cover({ d }: { d: Draft }) {
  const cover = d.draft.cover;
  const [status, setStatus] = useState<CoverStatus>();
  const [statusError, setStatusError] = useState<Error>();
  const [attempt, setAttempt] = useState(0);
  const [draft, setDraft] = useState<CoverDraft>();
  const [draftIssues, setDraftIssues] = useState<Issue[]>([]);
  const [draftError, setDraftError] = useState<Error>();
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [source, setSource] = useState<'draft' | 'built'>('draft');
  const [overlays, setOverlays] = useState<Set<Overlay>>(new Set());
  const base = `/api/projects/${encodeURIComponent(d.key)}`;
  const latest = useRef(d.draft);
  latest.current = d.draft;
  const signature = JSON.stringify([cover, d.draft.book]);

  useEffect(() => {
    const controller = new AbortController();
    setStatusError(undefined);
    request<CoverStatus>(`${base}/cover`, controller.signal)
      .then((data) => !controller.signal.aborted && setStatus(data))
      .catch((err: Error) => !controller.signal.aborted && setStatusError(err));
    return () => controller.abort();
  }, [base, d.saved.revision, attempt]);

  useEffect(() => {
    if (!cover) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setPending(true);
      request<CoverDraft>(`${base}/draft/cover`, controller.signal, { source: latest.current })
        .then((data) => {
          if (controller.signal.aborted) return;
          setDraft(data);
          setDraftIssues([]);
          setDraftError(undefined);
        })
        .catch((err: Error) => {
          if (controller.signal.aborted) return;
          if (err instanceof ApiError && err.code === 'invalid_project') setDraftIssues(err.issues);
          else setDraftError(err);
        })
        .finally(() => !controller.signal.aborted && setPending(false));
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // `signature` captures every draft value the cover depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, signature, d.saved.revision, attempt]);

  const update = (next: Partial<CoverConfig>) => {
    if (!cover) return;
    const merged: CoverConfig = { ...cover, ...next };
    if (merged.back_text === undefined) delete merged.back_text;
    d.change({ ...d.draft, cover: merged } as Source);
  };
  const nudge = (key: string, big: boolean) => {
    if (!cover) return false;
    const step = big ? BIG_STEP : STEP;
    const { x, y, zoom } = cover.crop;
    const moves: Record<string, Partial<CoverConfig['crop']>> = {
      ArrowLeft: { x: round4(clamp(x - step, 0, 1)) },
      ArrowRight: { x: round4(clamp(x + step, 0, 1)) },
      ArrowUp: { y: round4(clamp(y - step, 0, 1)) },
      ArrowDown: { y: round4(clamp(y + step, 0, 1)) },
      '+': { zoom: round4(clamp(zoom + (big ? 0.25 : 0.05), 1, 4)) },
      '=': { zoom: round4(clamp(zoom + (big ? 0.25 : 0.05), 1, 4)) },
      '-': { zoom: round4(clamp(zoom - (big ? 0.25 : 0.05), 1, 4)) },
      '0': { x: 0.5, y: 0.5, zoom: 1 },
    };
    const move = moves[key];
    if (!move) return false;
    update({ crop: { ...cover.crop, ...move } });
    return true;
  };
  const build = async () => {
    setBusy(true);
    setMessage(
      'Building the cover from the saved source and the built interior, then running preflight…',
    );
    try {
      const data = await request<CoverStatus>(`${base}/cover/build`, new AbortController().signal, {
        revision: d.saved.revision,
      });
      setStatus(data);
      setMessage(
        data.build?.success
          ? 'Cover built and preflight complete.'
          : 'The cover did not build. Nothing was written.',
      );
      if (data.build?.success) setSource('built');
    } catch (err) {
      setMessage(
        err instanceof ApiError && err.code === 'source_changed'
          ? 'The saved source changed on disk. Reload the project before building.'
          : err instanceof Error
            ? err.message
            : 'The build request did not complete.',
      );
    } finally {
      setBusy(false);
    }
  };

  if (!d.draft.composition)
    return (
      <section className="notice">
        <h2>No book composition</h2>
        <p>
          A cover is sized from the built interior. Compose the book in Book, save, and build the
          interior in Print first.
        </p>
      </section>
    );
  const issues = [...d.issues, ...draftIssues];
  if (!cover)
    return (
      <div className="editor cover-studio">
        <DraftToolbar
          d={d}
          title="Cover"
          jump={{ href: '#cover-start', label: 'Choose a photo' }}
        />
        <section className="cover-start" id="cover-start">
          <h2>Start a cover from your photograph</h2>
          <p>
            Choose or import one of your own photographs. PuzzlePress copies it into this project,
            sizes the full wrap from the built interior, and sets the book&apos;s title, subtitle
            and author over it. Nothing is saved until you save.
          </p>
          <PhotoPicker
            projectKey={d.key}
            onChoose={(asset) =>
              asset.sha256 &&
              d.change({
                ...d.draft,
                cover: starterCover({ path: asset.path, sha256: asset.sha256 }),
              } as Source)
            }
          />
        </section>
      </div>
    );
  const builtLayout = status?.state === 'current' ? (status.layout ?? undefined) : undefined;
  const showBuilt = source === 'built' && status?.preview;
  const stageLayout = showBuilt ? (builtLayout ?? draft?.layout) : draft?.layout;
  const pdf = showBuilt ? status!.preview!.pdf_sha256 : draft?.preview?.pdf_sha256;
  const scales = (showBuilt ? status!.preview!.scales : draft?.preview?.scales) ?? { preview: 1 };
  return (
    <div className="editor cover-studio">
      <DraftToolbar
        d={d}
        title="Cover"
        jump={{ href: '#cover-readiness', label: 'Jump to readiness' }}
      />
      <p role="status" aria-live="polite" className="small">
        {pending ? 'Rendering the draft cover…' : message}
      </p>
      <div className="cover-workspace">
        <Controls d={d} cover={cover} layout={draft?.layout} issues={issues} update={update} />
        <div className="cover-main">
          <div className="cover-source" role="group" aria-label="Preview source">
            <button type="button" aria-pressed={!showBuilt} onClick={() => setSource('draft')}>
              Draft preview
            </button>
            <button
              type="button"
              aria-pressed={Boolean(showBuilt)}
              disabled={!status?.preview}
              onClick={() => setSource('built')}
            >
              Built cover.pdf
            </button>
          </div>
          {draftError && !showBuilt && (
            <ErrorState error={draftError} retry={() => setAttempt((n) => n + 1)} />
          )}
          {draft && !draft.success && !showBuilt && (
            <Failure stage={draft.stage} diagnostics={draft.diagnostics ?? []} />
          )}
          {stageLayout && pdf ? (
            <Stage
              key={showBuilt ? 'built' : 'draft'}
              projectKey={d.key}
              layout={stageLayout}
              pdf={pdf}
              scales={scales}
              label={showBuilt ? 'Built cover.pdf' : 'Draft cover'}
              overlays={showBuilt && !builtLayout ? null : overlays}
              canCrop={!showBuilt && Boolean(draft?.success)}
              onCrop={(focal) => update({ crop: { ...cover.crop, ...focal } })}
              onNudge={nudge}
            />
          ) : (
            !draftError &&
            !(draft && !draft.success) && <Loading>Rendering the draft cover from Python…</Loading>
          )}
          <fieldset
            className="print-overlays"
            disabled={showBuilt ? !builtLayout : !draft?.success}
          >
            <legend>Overlays (preview only, never in the PDF)</legend>
            {OVERLAYS.map(([key, label, hint]) => (
              <label key={key} className="check">
                <input
                  type="checkbox"
                  checked={overlays.has(key)}
                  onChange={(event) => {
                    const next = new Set(overlays);
                    if (event.target.checked) next.add(key);
                    else next.delete(key);
                    setOverlays(next);
                  }}
                />
                <span>
                  <span className={`overlay-key cover-${key}`} aria-hidden="true" />
                  {label}
                  <small>{hint}</small>
                </span>
              </label>
            ))}
          </fieldset>
          <p className="small muted">
            The preview is rasterized from a real cover PDF rendered by Python. The draft preview
            reflects unsaved edits; Built cover.pdf is the file you would upload. Colors are sRGB on
            screen; KDP prints in CMYK, so review a printed proof.
          </p>
        </div>
        <div id="cover-readiness" tabIndex={-1}>
          {statusError ? (
            <ErrorState error={statusError} retry={() => setAttempt((n) => n + 1)} />
          ) : (
            <Readiness
              d={d}
              draft={draft}
              status={status}
              busy={busy}
              onBuild={() => void build()}
            />
          )}
        </div>
      </div>
    </div>
  );
}
