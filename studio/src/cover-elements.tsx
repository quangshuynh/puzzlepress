import { useEffect, useState } from 'react';
import { ApiError, request } from './api';
import {
  ALLOWED,
  KIND_NAMES,
  MAX_ELEMENTS,
  REGION_NAMES,
  addElement,
  designed,
  duplicateElement,
  elementLayer,
  elementName,
  elementOf,
  moveInStack,
  movable,
  removeElement,
  resetStyle,
  setRegion,
  updateElement,
} from './cover-elements-model';
import { ROLES, layerOf, round, setLayer } from './cover-model';
import { BUNDLED, Group, NumberField, PhotoInspector, SEVERITY, Slider } from './cover-inspector';
import { ColorField, EyeIcon, Segmented } from './cover-tools';
import { FieldErrors, matchIssues, type Source } from './editor-fields';
import type {
  CoverCheck,
  CoverConfig,
  CoverConversion,
  CoverElement,
  CoverLayoutView,
  CoverLibrary,
  CoverPreset,
  ElementBox,
  ElementRegion,
  Issue,
  PanelRegion,
} from './types';
import { Status } from './ui';

// Version 3 region designs: the region picker, the layer stack, shape tools, the
// element and region inspectors, conversion and presets. Every value edited here
// is authored (region coordinates in points from the region's trim corner, y up);
// Python lays out, flattens and validates the result and renders the preview.

export function RegionPicker({
  region,
  onChange,
}: {
  region: ElementRegion;
  onChange: (region: ElementRegion) => void;
}) {
  return (
    <div role="group" aria-label="Region" className="segmented-inline region-picker">
      {REGION_NAMES.map(([key, name]) => (
        <button
          key={key}
          type="button"
          aria-pressed={region === key}
          aria-label={`${name} region`}
          onClick={() => onChange(key)}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

function elementIndex(cover: CoverConfig, id: string) {
  return (cover.elements ?? []).findIndex((element) => element.id === id);
}

export function LayersTab({
  cover,
  selected,
  onSelect,
  update,
  onConvert,
}: {
  cover: CoverConfig;
  selected: string | null;
  onSelect: (layer: string | null) => void;
  update: (next: CoverConfig) => void;
  onConvert: () => void;
}) {
  const elements = cover.elements ?? [];
  // Top of the stack first, as people read a layer list.
  const stack = [...elements].reverse();
  return (
    <div className="tool-section">
      <div className="tool-heading">
        <h3>Layers</h3>
      </div>
      {!designed(cover) ? (
        <ConvertCard onConvert={onConvert}>
          This cover uses the {cover.layout === 'front_photo' ? 'front photo' : 'full-wrap'} layout:
          one photograph and the book text. Convert it to a region design to stack shapes, lines,
          text boxes and more photographs.
        </ConvertCard>
      ) : (
        <>
          <p className="small muted">
            Top of the stack first. Book text is always drawn above these layers.
          </p>
          {stack.length === 0 ? (
            <p className="small muted">No elements yet. Add one from Shapes or Photos.</p>
          ) : (
            <ul className="layer-list element-layers" aria-label="Design layers, top first">
              {stack.map((element) => {
                const layer = elementLayer(element.id);
                const index = elementIndex(cover, element.id);
                const name = elementName(element);
                const hidden = element.visible === false;
                return (
                  <li key={element.id} className={layer === selected ? 'selected' : undefined}>
                    <button
                      type="button"
                      className="layer-select"
                      aria-pressed={layer === selected}
                      onClick={() => onSelect(layer)}
                    >
                      <span className="layer-name">{name}</span>
                      <span className={`layer-text${hidden ? ' hidden-text' : ''}`}>
                        {KIND_NAMES[element.type]} · {element.region}
                        {hidden ? ' · hidden' : ''}
                        {element.locked ? ' · locked' : ''}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-pressed={!hidden}
                      aria-label={`${hidden ? 'Show' : 'Hide'} ${name}`}
                      onClick={() =>
                        update(
                          updateElement(cover, element.id, { visible: hidden ? undefined : false }),
                        )
                      }
                    >
                      <EyeIcon open={!hidden} />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-pressed={Boolean(element.locked)}
                      aria-label={`${element.locked ? 'Unlock' : 'Lock'} ${name}`}
                      onClick={() =>
                        update(
                          updateElement(cover, element.id, {
                            locked: element.locked ? undefined : true,
                          }),
                        )
                      }
                    >
                      <LockIcon locked={Boolean(element.locked)} />
                    </button>
                    <div className="stack-buttons" role="group" aria-label={`Order of ${name}`}>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Bring ${name} forward`}
                        disabled={index === elements.length - 1}
                        onClick={() => update(moveInStack(cover, element.id, true))}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Send ${name} backward`}
                        disabled={index === 0}
                        onClick={() => update(moveInStack(cover, element.id, false))}
                      >
                        ↓
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
      <h4 className="tool-subheading">Book text</h4>
      <ul className="layer-list" aria-label="Book text layers">
        {ROLES.map(([role, name]) => {
          const hidden = layerOf(cover, role).visible === false;
          return (
            <li key={role} className={role === selected ? 'selected' : undefined}>
              <button
                type="button"
                className="layer-select"
                aria-pressed={role === selected}
                onClick={() => onSelect(role)}
              >
                <span className="layer-name">{name}</span>
                <span className="layer-text">
                  {hidden ? 'Hidden on the cover' : 'From the book details'}
                </span>
              </button>
              <button
                type="button"
                className="icon-button"
                aria-pressed={!hidden}
                aria-label={`${hidden ? 'Show' : 'Hide'} ${name.toLowerCase()} on the cover`}
                onClick={() => update(setLayer(cover, role, { visible: hidden }))}
              >
                <EyeIcon open={!hidden} />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function LockIcon({ locked }: { locked: boolean }) {
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
      <rect x="5" y="11" width="14" height="9" rx="1.5" />
      <path d={locked ? 'M8 11V8a4 4 0 0 1 8 0v3' : 'M8 11V8a4 4 0 0 1 7.5-2'} />
    </svg>
  );
}

function ConvertCard({
  onConvert,
  children,
}: {
  onConvert: () => void;
  children: string[] | string;
}) {
  return (
    <div className="convert-card">
      <p className="small">{children}</p>
      <button type="button" className="small-button" onClick={onConvert}>
        Preview region design…
      </button>
    </div>
  );
}

export function ShapesTab({
  cover,
  layout,
  region,
  update,
  onSelect,
  onConvert,
}: {
  cover: CoverConfig;
  layout?: CoverLayoutView;
  region: ElementRegion;
  update: (next: CoverConfig) => void;
  onSelect: (layer: string) => void;
  onConvert: () => void;
}) {
  if (!designed(cover))
    return (
      <div className="tool-section">
        <div className="tool-heading">
          <h3>Shapes and text boxes</h3>
        </div>
        <ConvertCard onConvert={onConvert}>
          Shapes, lines and text boxes need a region design. Converting keeps this cover exactly as
          it looks now; Python verifies that both render the same PDF.
        </ConvertCard>
      </div>
    );
  const full = (cover.elements?.length ?? 0) >= MAX_ELEMENTS;
  const kinds: CoverElement['type'][] = ['rect', 'ellipse', 'line', 'text'];
  return (
    <div className="tool-section">
      <div className="tool-heading">
        <h3>Shapes and text boxes</h3>
      </div>
      <p className="small muted">
        Added to the {REGION_NAMES.find(([key]) => key === region)?.[1].toLowerCase()} region,
        centered. Move them on the canvas or type exact positions in Properties.
      </p>
      <div className="button-grid">
        {kinds.map((kind) => {
          const allowed = ALLOWED[kind].includes(region);
          return (
            <button
              key={kind}
              type="button"
              className="small-button"
              disabled={!layout || full || !allowed}
              title={
                allowed ? undefined : `A ${KIND_NAMES[kind].toLowerCase()} cannot go on this region`
              }
              onClick={() => {
                if (!layout) return;
                const [next, layer] = addElement(cover, kind, region, layout);
                update(next);
                onSelect(layer);
              }}
            >
              Add {KIND_NAMES[kind].toLowerCase()}
            </button>
          );
        })}
      </div>
      {region === 'spine' && (
        <p className="small muted">
          The spine takes rectangles and lines only, kept between the folds. Binding can shift a
          fold by 1/16 in, so Python warns about edges close to it.
        </p>
      )}
      {full && <p className="small field-errors">A cover holds at most {MAX_ELEMENTS} elements.</p>}
    </div>
  );
}

function BoxFields({
  box,
  path,
  issues,
  disabled,
  onChange,
}: {
  box: ElementBox;
  path: string;
  issues: Issue[];
  disabled: boolean;
  onChange: (box: ElementBox) => void;
}) {
  const field = (key: keyof ElementBox, label: string) => (
    <NumberField
      id={`${path}-${key}`.replaceAll('.', '-')}
      label={label}
      value={box[key]}
      min={key === 'width' || key === 'height' ? 1 : -1500}
      max={3000}
      step={1}
      unit="pt"
      issues={issues}
      path={`${path}.${key}`}
      onChange={(value) => value !== undefined && onChange({ ...box, [key]: round(value, 2) })}
    />
  );
  return (
    <fieldset className="field-grid" disabled={disabled}>
      <legend className="sr-only">Position and size</legend>
      {field('x', 'X from left')}
      {field('y', 'Y from bottom')}
      {field('width', 'Width')}
      {field('height', 'Height')}
    </fieldset>
  );
}

export function ElementInspector({
  element,
  cover,
  layout,
  library,
  checks,
  issues,
  update,
  onSelect,
}: {
  element: CoverElement;
  cover: CoverConfig;
  layout?: CoverLayoutView;
  library?: CoverLibrary;
  checks: CoverCheck[];
  issues: Issue[];
  update: (next: CoverConfig) => void;
  onSelect: (layer: string | null) => void;
}) {
  const index = elementIndex(cover, element.id);
  const path = `cover.elements.${index}`;
  const layer = elementLayer(element.id);
  const name = elementName(element);
  const set = (patch: Partial<CoverElement>) => update(updateElement(cover, element.id, patch));
  const locked = Boolean(element.locked);
  const elementChecks = checks.filter((check) => check.layer === layer);
  const view = layout?.photos?.find((photo) => photo.layer === layer);
  const size = layout ? (layout.regions?.[element.region]?.origin ?? null) : null;
  const fontKeys = [
    ...BUNDLED,
    ...(cover.fonts ?? []).map((font): [string, string] => {
      const facts = library?.fonts.find((f) => f.path === font.path);
      return [font.id, `${facts?.full_name ?? font.id} (imported)`];
    }),
  ];
  const general = (
    <>
      <div className="editor-field">
        <label htmlFor="element-name">Layer name</label>
        <input
          id="element-name"
          value={element.name ?? ''}
          placeholder={name}
          aria-describedby="element-name-hint"
          onChange={(e) => set({ name: e.target.value || undefined })}
        />
        <p className="small muted field-hint" id="element-name-hint">
          For the layer list and screen readers only; never printed.
        </p>
        <FieldErrors id={`${path}.name`} issues={matchIssues(issues, `${path}.name`)} />
      </div>
      <div className="button-row">
        <button
          type="button"
          className="small-button"
          aria-pressed={locked}
          onClick={() => set({ locked: locked ? undefined : true })}
        >
          {locked ? 'Unlock' : 'Lock'}
        </button>
        <button
          type="button"
          className="small-button"
          disabled={(cover.elements?.length ?? 0) >= MAX_ELEMENTS}
          onClick={() => {
            const [next, copy] = duplicateElement(cover, element.id);
            update(next);
            onSelect(copy);
          }}
        >
          Duplicate
        </button>
        <button
          type="button"
          className="small-button"
          disabled={locked}
          onClick={() => set(resetStyle(element))}
        >
          Reset style
        </button>
        <button
          type="button"
          className="small-button danger"
          disabled={locked}
          onClick={() => {
            if (window.confirm(`Delete “${name}” from this cover draft? Undo can bring it back.`)) {
              update(removeElement(cover, element.id));
              onSelect(null);
            }
          }}
        >
          Delete
        </button>
      </div>
      {locked && (
        <p className="small muted">
          Locked: the canvas will not move it and its properties are read-only. Unlock to edit.
        </p>
      )}
    </>
  );
  const heading = (
    <>
      {elementChecks.map((check, i) => (
        <p key={`${check.code}-${i}`} className={`inspector-check ${check.severity}`}>
          <Status tone={SEVERITY[check.severity][0]}>{SEVERITY[check.severity][1]}</Status>{' '}
          {check.message}
        </p>
      ))}
    </>
  );
  if (element.type === 'photo')
    return (
      <PhotoInspector
        heading={name}
        name={element.image.path}
        crop={element.crop}
        path={`${path}.crop`}
        resolution={view?.resolution}
        center={view?.center}
        issues={issues}
        onCrop={(crop) => !locked && set({ crop })}
      >
        {heading}
        <Group title="Frame">
          <label className="check">
            <input
              type="checkbox"
              disabled={locked}
              checked={element.box === undefined}
              onChange={(e) =>
                set({
                  box: e.target.checked
                    ? undefined
                    : {
                        x: 36,
                        y: 36,
                        width: round((size?.width ?? 612) - 72, 2),
                        height: round((size?.height ?? 792) - 72, 2),
                      },
                })
              }
            />
            <span>Fill the whole region, bleed included</span>
          </label>
          {element.box && (
            <BoxFields
              box={element.box}
              path={`${path}.box`}
              issues={issues}
              disabled={locked}
              onChange={(box) => set({ box })}
            />
          )}
        </Group>
        {general}
      </PhotoInspector>
    );
  return (
    <div className="inspector-body" aria-label={`${name} properties`}>
      <div className="inspector-heading">
        <h3>{name}</h3>
        <button
          type="button"
          className="icon-button"
          aria-pressed={element.visible !== false}
          aria-label={`${element.visible === false ? 'Show' : 'Hide'} ${name}`}
          onClick={() => set({ visible: element.visible === false ? undefined : false })}
        >
          <EyeIcon open={element.visible !== false} />
        </button>
      </div>
      {heading}
      <fieldset className="inspector-fields" disabled={locked}>
        <legend className="sr-only">{name}</legend>
        {element.type === 'text' && (
          <Group title="Text">
            <div className="editor-field">
              <label htmlFor="element-text">Text</label>
              <textarea
                id="element-text"
                rows={4}
                value={element.text}
                aria-describedby="element-text-hint"
                aria-invalid={matchIssues(issues, `${path}.text`).length ? true : undefined}
                onChange={(e) => set({ text: e.target.value })}
              />
              <p className="small muted field-hint" id="element-text-hint">
                Your own words, wrapped to the box width; line breaks are kept. Text that does not
                fit is reported, never cut off. This is not the book title or author.
              </p>
              <FieldErrors id={`${path}.text`} issues={matchIssues(issues, `${path}.text`)} />
            </div>
            <div className="editor-field">
              <label htmlFor="element-font">Font</label>
              <select
                id="element-font"
                value={element.font ?? ''}
                onChange={(e) => set({ font: e.target.value || undefined })}
              >
                <option value="">Preset body face</option>
                {fontKeys.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field-grid">
              <NumberField
                id="element-size"
                label="Size"
                value={element.size}
                min={4}
                max={160}
                step={0.5}
                unit="pt"
                issues={issues}
                path={`${path}.size`}
                onChange={(size) => size !== undefined && set({ size })}
              />
              <NumberField
                id="element-leading"
                label="Line spacing"
                value={element.line_spacing}
                min={0.8}
                max={3}
                step={0.05}
                unit="×"
                issues={issues}
                path={`${path}.line_spacing`}
                onChange={(line_spacing) => line_spacing !== undefined && set({ line_spacing })}
              />
              <NumberField
                id="element-tracking"
                label="Letter spacing"
                value={element.letter_spacing}
                placeholder="0"
                min={-2}
                max={20}
                step={0.25}
                unit="pt"
                issues={issues}
                path={`${path}.letter_spacing`}
                onChange={(letter_spacing) => set({ letter_spacing: letter_spacing || undefined })}
              />
            </div>
            <Segmented
              legend="Alignment"
              value={element.align}
              options={[
                ['left', 'Left'],
                ['center', 'Center'],
                ['right', 'Right'],
              ]}
              onChange={(align) => set({ align })}
            />
            <Segmented
              legend="Case"
              value={element.case ?? 'as_written'}
              options={[
                ['as_written', 'As written'],
                ['upper', 'Capitals'],
              ]}
              onChange={(value) => set({ case: value === 'as_written' ? undefined : value })}
            />
            <ColorField
              id="element-color"
              label="Text color"
              value={element.color}
              fallback="#f4efe4"
              issues={matchIssues(issues, `${path}.color`)}
              path={`${path}.color`}
              onChange={(color) => set({ color })}
            />
          </Group>
        )}
        {(element.type === 'rect' || element.type === 'ellipse') && (
          <Group title="Fill and stroke">
            <label className="check">
              <input
                type="checkbox"
                checked={element.fill !== null}
                onChange={(e) => set({ fill: e.target.checked ? '#f4efe4' : null })}
              />
              <span>Fill</span>
            </label>
            {element.fill !== null && (
              <ColorField
                id="element-fill"
                label="Fill color"
                value={element.fill}
                fallback="#f4efe4"
                issues={matchIssues(issues, `${path}.fill`)}
                path={`${path}.fill`}
                onChange={(fill) => set({ fill })}
              />
            )}
            <label className="check">
              <input
                type="checkbox"
                checked={element.stroke !== null}
                disabled={(element.opacity ?? 1) < 1}
                onChange={(e) => set({ stroke: e.target.checked ? '#1d2a44' : null })}
              />
              <span>Stroke (drawn inside the edge)</span>
            </label>
            {element.stroke !== null && (
              <>
                <ColorField
                  id="element-stroke"
                  label="Stroke color"
                  value={element.stroke}
                  fallback="#1d2a44"
                  issues={matchIssues(issues, `${path}.stroke`)}
                  path={`${path}.stroke`}
                  onChange={(stroke) => set({ stroke })}
                />
                <NumberField
                  id="element-stroke-width"
                  label="Stroke width"
                  value={element.stroke_width ?? 1}
                  min={0.75}
                  max={72}
                  step={0.25}
                  unit="pt"
                  issues={issues}
                  path={`${path}.stroke_width`}
                  onChange={(stroke_width) => stroke_width !== undefined && set({ stroke_width })}
                />
              </>
            )}
            <Slider
              id="element-opacity"
              label="Opacity"
              value={element.opacity ?? 1}
              min={0.05}
              max={1}
              step={0.05}
              display={`${Math.round((element.opacity ?? 1) * 100)}%`}
              issues={issues}
              path={`${path}.opacity`}
              onChange={(opacity) => set({ opacity: opacity >= 1 ? undefined : opacity })}
            />
            <p className="small muted">
              KDP covers cannot use transparency, so Python flattens a translucent shape: blended
              into one solid region color, or baked into the one photograph beneath it. Anything
              else is reported. A translucent shape has no stroke.
            </p>
          </Group>
        )}
        {element.type === 'line' && (
          <Group title="Line">
            <div className="field-grid">
              {(['from', 'to'] as const).flatMap((end) =>
                (['x', 'y'] as const).map((axis) => (
                  <NumberField
                    key={`${end}-${axis}`}
                    id={`element-${end}-${axis}`}
                    label={`${end === 'from' ? 'Start' : 'End'} ${axis.toUpperCase()}`}
                    value={element[end][axis]}
                    min={-1500}
                    max={1500}
                    step={1}
                    unit="pt"
                    issues={issues}
                    path={`${path}.${end}.${axis}`}
                    onChange={(value) =>
                      value !== undefined &&
                      set({ [end]: { ...element[end], [axis]: round(value, 2) } })
                    }
                  />
                )),
              )}
              <NumberField
                id="element-width"
                label="Weight"
                value={element.width}
                min={0.75}
                max={72}
                step={0.25}
                unit="pt"
                issues={issues}
                path={`${path}.width`}
                onChange={(width) => width !== undefined && set({ width })}
              />
            </div>
            <ColorField
              id="element-line-color"
              label="Line color"
              value={element.color}
              fallback="#f4efe4"
              issues={matchIssues(issues, `${path}.color`)}
              path={`${path}.color`}
              onChange={(color) => set({ color })}
            />
          </Group>
        )}
        {element.type !== 'line' && (
          <Group title="Position and size">
            {element.type !== 'text' && (
              <label className="check">
                <input
                  type="checkbox"
                  checked={element.box === undefined}
                  onChange={(e) =>
                    set({
                      box: e.target.checked ? undefined : { x: 36, y: 36, width: 144, height: 72 },
                      rotation: undefined,
                    })
                  }
                />
                <span>Fill the whole region, bleed included</span>
              </label>
            )}
            {element.box && (
              <BoxFields
                box={element.box}
                path={`${path}.box`}
                issues={issues}
                disabled={locked}
                onChange={(box) => set({ box })}
              />
            )}
            {element.type !== 'text' && element.box && (
              <NumberField
                id="element-rotation"
                label="Rotation"
                value={element.rotation}
                placeholder="0"
                min={-180}
                max={180}
                step={1}
                unit="°"
                issues={issues}
                path={`${path}.rotation`}
                onChange={(rotation) => set({ rotation: rotation || undefined })}
              />
            )}
            <p className="small muted">
              Points from the {element.region} region&apos;s bottom-left trim corner; 72 pt is one
              inch. {!movable(element) && 'A region-filling element follows the region exactly.'}
            </p>
          </Group>
        )}
      </fieldset>
      {general}
    </div>
  );
}

export function RegionInspector({
  cover,
  region,
  issues,
  update,
}: {
  cover: CoverConfig;
  region: ElementRegion;
  issues: Issue[];
  update: (next: CoverConfig) => void;
}) {
  if (!cover.regions)
    return (
      <div className="inspector-body">
        <h3>Regions</h3>
        <p className="small muted">
          Version 1 and 2 covers share one fill color. Convert to a region design to color the back,
          spine and front independently.
        </p>
      </div>
    );
  const panels: PanelRegion[] = region === 'wrap' ? ['back', 'spine', 'front'] : [region];
  return (
    <div className="inspector-body" aria-label="Region backgrounds">
      <div className="inspector-heading">
        <h3>
          {region === 'wrap'
            ? 'Region backgrounds'
            : `${region[0].toUpperCase()}${region.slice(1)} background`}
        </h3>
      </div>
      <p className="small muted">
        Region sizes come from the built interior: the spine is its page count times the paper
        thickness. They are never typed in.
      </p>
      {panels.map((panel) => {
        const style = cover.regions![panel];
        const path = `cover.regions.${panel}`;
        return (
          <Group key={panel} title={`${panel[0].toUpperCase()}${panel.slice(1)}`}>
            <ColorField
              id={`region-${panel}-color`}
              label={style.gradient ? 'Top or left color' : 'Color'}
              value={style.color}
              fallback="#1d2a44"
              issues={matchIssues(issues, `${path}.color`)}
              path={`${path}.color`}
              onChange={(color) => update(setRegion(cover, panel, { color }))}
            />
            <label className="check">
              <input
                type="checkbox"
                checked={Boolean(style.gradient)}
                onChange={(e) =>
                  update(
                    setRegion(cover, panel, {
                      gradient: e.target.checked
                        ? { to: '#000000', direction: 'vertical' }
                        : undefined,
                    }),
                  )
                }
              />
              <span>Two-color gradient</span>
            </label>
            {style.gradient && (
              <>
                <ColorField
                  id={`region-${panel}-to`}
                  label="Bottom or right color"
                  value={style.gradient.to}
                  fallback="#000000"
                  issues={matchIssues(issues, `${path}.gradient.to`)}
                  path={`${path}.gradient.to`}
                  onChange={(to) =>
                    update(setRegion(cover, panel, { gradient: { ...style.gradient!, to } }))
                  }
                />
                <Segmented
                  legend="Direction"
                  value={style.gradient.direction}
                  options={[
                    ['vertical', 'Top to bottom'],
                    ['horizontal', 'Left to right'],
                  ]}
                  onChange={(direction) =>
                    update(setRegion(cover, panel, { gradient: { ...style.gradient!, direction } }))
                  }
                />
              </>
            )}
          </Group>
        );
      })}
      {region !== 'wrap' && region !== 'spine' && (
        <p className="small muted">
          A color that differs from the spine&apos;s at a fold is flagged: binding can shift the
          fold by up to 1/16 in.
        </p>
      )}
    </div>
  );
}

// Explicit conversion: Python renders the draft both ways and says whether the PDFs match.
export function ConvertDialog({
  projectKey,
  source,
  onUse,
  onClose,
}: {
  projectKey: string;
  source: Source;
  onUse: (cover: CoverConfig) => void;
  onClose: () => void;
}) {
  const [result, setResult] = useState<CoverConversion>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    const controller = new AbortController();
    request<CoverConversion>(
      `/api/projects/${encodeURIComponent(projectKey)}/draft/cover/convert`,
      controller.signal,
      { source },
    )
      .then((data) => !controller.signal.aborted && setResult(data))
      .catch(
        (err: Error) =>
          !controller.signal.aborted &&
          setError(err instanceof ApiError ? err.message : 'The conversion did not complete.'),
      );
    return () => controller.abort();
    // The dialog converts the draft it opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="dialog-backdrop">
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="convert-heading"
        onKeyDown={(event) => event.key === 'Escape' && onClose()}
      >
        <h2 id="convert-heading">Convert to a region design</h2>
        <p>
          The back, spine and front become separate regions with their own backgrounds, and the
          photograph becomes a layer you can stack shapes and text boxes around. Nothing is saved
          until you save the draft, and Undo reverses it.
        </p>
        {error && <p className="field-errors">{error}</p>}
        {!result && !error && <p role="status">Rendering both versions in Python…</p>}
        {result && !result.success && (
          <p className="field-errors">
            The draft cover does not render ({result.stage}):{' '}
            {result.diagnostics?.map((d) => d.message).join(' ')}
          </p>
        )}
        {result?.success && result.preview && (
          <>
            <img
              className="convert-preview"
              src={`/api/projects/${encodeURIComponent(projectKey)}/cover/preview?size=preview&pdf=${result.preview.pdf_sha256}`}
              alt="The converted region design, rendered by Python"
            />
            <p role="status">
              {result.identical ? (
                <Status tone="pass">Identical</Status>
              ) : (
                <Status tone="review">Differs</Status>
              )}{' '}
              {result.identical
                ? 'Python rendered the current cover and its region design: the PDFs are byte-identical.'
                : 'The region design renders differently from the current cover; compare before using it.'}
            </p>
          </>
        )}
        <div className="button-row">
          <button
            type="button"
            className="primary"
            disabled={!result?.success || !result.cover}
            onClick={() => result?.cover && onUse(result.cover)}
          >
            Use region design
          </button>
          <button type="button" onClick={onClose} autoFocus>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export function PresetsSection({
  projectKey,
  source,
  cover,
  update,
}: {
  projectKey: string;
  source: Source;
  cover: CoverConfig;
  update: (next: CoverConfig) => void;
}) {
  const [presets, setPresets] = useState<CoverPreset[]>();
  const [error, setError] = useState('');
  const load = () => {
    setError('');
    request<{ presets: CoverPreset[] }>(
      `/api/projects/${encodeURIComponent(projectKey)}/draft/cover/presets`,
      new AbortController().signal,
      { source },
    )
      .then((data) => setPresets(data.presets))
      .catch((err: Error) => setError(err.message));
  };
  return (
    <div className="presets">
      <h4 className="tool-subheading">Design presets</h4>
      <p className="small muted">
        Starting points built from this cover&apos;s photograph and colors. Applying one replaces
        the region backgrounds and layers (Undo restores them); the book text stays.
      </p>
      {!presets ? (
        <button type="button" className="small-button" onClick={load}>
          Show presets
        </button>
      ) : (
        <ul className="preset-list">
          {presets.map((preset) => (
            <li key={preset.id}>
              <div>
                <strong>{preset.name}</strong>
                <p className="small muted">{preset.description}</p>
              </div>
              <button
                type="button"
                className="small-button"
                onClick={() => {
                  if (
                    !designed(cover) ||
                    (cover.elements?.length ?? 0) === 0 ||
                    window.confirm(`Replace this cover's layers with “${preset.name}”?`)
                  )
                    update(preset.cover);
                }}
              >
                Apply
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="small field-errors">{error}</p>}
    </div>
  );
}

export function selectedElement(cover: CoverConfig, layer: string | null) {
  return elementOf(cover, layer);
}
