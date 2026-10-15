---
name: PuzzlePress Studio
description: A calm editorial workspace for reviewing puzzle books.
colors:
  canvas: "#f7f5ef"
  paper: "#fffef9"
  ink: "#252d28"
  muted: "#62665e"
  line: "#d9dbd0"
  primary: "#2c5141"
  primary-hover: "#1d3b2d"
  wash: "#e7ecdf"
  review: "#795319"
  review-background: "#f6edd8"
  failure: "#913c32"
  failure-background: "#faeee9"
typography:
  display:
    fontFamily: "Newsreader Variable, Georgia, serif"
    fontSize: "clamp(30px, 2.6vw, 40px)"
    fontWeight: 450
    lineHeight: 1.14
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Newsreader Variable, Georgia, serif"
    fontSize: "22px"
    fontWeight: 450
    lineHeight: 1.2
  body:
    fontFamily: "Public Sans Variable, sans-serif"
    fontSize: "14px"
    lineHeight: 1.6
rounded:
  control: "4px"
spacing:
  xs: "8px"
  sm: "16px"
  md: "24px"
  lg: "32px"
  xl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.paper}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.primary}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
---

# Design System: PuzzlePress Studio

## Overview

**Creative North Star: "The publishing desk"**

A precise, calm workspace for inspecting authored books. Typography provides
hierarchy; ruled lists carry dense source information. Generated puzzles occupy
an uncluttered paper surface, with their evidence beside them.

**Key Characteristics:**
- Editorial typography with compact interface controls.
- Flat surfaces, warm paper, restrained green and explicit status text.
- Real source and generated analysis, clearly distinguished.

## Colors

Canvas and paper separate workspace from puzzle. Green identifies current
navigation, primary actions and specific successful checks. Amber denotes review;
red denotes failures. Muted text remains readable on its assigned surface.

**The Evidence Rule.** Status color must accompany a precise text label and may
only reflect an existing engine/validation result or explicit local draft state.
Amber may identify unsaved changes; it must not imply a quality finding.

## Typography

Newsreader is the display and editorial heading voice. Public Sans carries controls,
metadata, targets and grids. Both variable fonts are bundled locally. Monospace is
reserved for identities, seeds and developer payloads. Paragraphs stop at 75ch.

## Layout

A 48px app bar (logo, Books, a local-only note) stays at the top; main content uses
28px gutters (20px below 1150px, 16px below 600px) up to 1720px. A project opens
with a one-line header (22px serif title linking to Overview, subtitle, ID,
language and an Unsaved draft mark) and one grouped navigation rule: Overview, then
small-caps group labels Create (Plan, Puzzles, Book, Cover) → Review (Print proof,
Solutions, Quality) → Publish (Publishing). Below 600px the group labels become
screen-reader text and the links wrap. Draft sections share a compact bar sticky
under the app bar. Side columns (puzzle navigator, plan, readiness, previews) stay
in view and scroll on their own instead of lengthening the page. Large grids scroll
within their own region, retaining 15px or larger letters at tested widths.

**The Source and Analysis Rule.** Present authored configuration before generation;
keep generation, verification and quality states distinct in all views.

## Elevation & Depth

No shadows. Single rules and subtle surface changes establish separation. The
puzzle paper is the main bordered artifact; sections do not nest inside cards.

## Shapes

Paper and data surfaces are square. Interactive controls use a 4px radius.
Small status marks differ in shape as well as color. The supplied logo is preserved.

## Components

- Buttons: 36px (34px in toolbars, 30px for small row actions) on desktop and 44px
  on touch screens, explicit verbs, dark-green primary action, bordered secondary
  action. Segmented controls join buttons and fill the chosen one green. Tab lists
  are a ruled row with a green underline and arrow-key movement. Focus is a 3px
  brown outline with a 4px offset.
- Search: visible label, paper surface, thin border, distinct focus outline.
- Navigation: ordinary links, current-page semantics, a bottom rule for project
  sections, grouped by stage with quiet labels and arrows showing the order.
- Draft bar: section name, a round mark for saved and an amber diamond for unsaved,
  the latest status, then Validate, the section's preview, Revert and Save last.
  The canonical-YAML reminder stays visible in small text.
- Puzzle navigator: search, theme and difficulty filters, a scrolling ruled list
  (ordinal, title, theme and level, a review mark) and one puzzle's fields at a
  time with Previous/Next.
- Lists: ruled project and definition rows, real counts, no decorative statistics.
- Inspector: semantic letter table, highlighted solution cells with underlines and
  heavier weight, plus a textual coordinate register.
- Details: native disclosure for developer payloads and less-used configuration.
- Composer: a manuscript outline. Sections open with a heavy ink rule and a serif
  heading; items are ruled rows with compact Up/Down/Remove buttons. The plan is a
  semantic table grouped by section, with side and number as text, uncounted
  numbers in parentheses and blanks on canvas with their reason. It is a logical
  list, never a simulated page spread or print preview. A strip of small blocks
  (one per logical page, in spreads, coloured by section, blanks hatched) sums up
  the sequence; it is a diagram of the plan, not of printed pages.
- Print proof: the rasterized PDF page is the dominant artifact on a neutral
  canvas, flanked by page thumbnails and a ruled findings column. Structural and
  KDP verdicts are separate text statuses, never one badge. Findings state what,
  where, measured and required values, and what they block. Overlays are thin
  dashed SVG lines over the raster, labeled and off by default; the binding edge
  is marked. Passed checks are secondary disclosures.
- Cover studio: an editing workspace with three bordered regions of fixed height:
  tools (Photo, Text, Fonts, Design tabs), the canvas, and an inspector (Properties,
  Checks). The rendered wrap dominates the neutral canvas, a raster of the real
  cover PDF, never an HTML reconstruction. Python's measured text boxes are drawn
  as thin outlines: dashed on hover, solid blue when selected, red when a check
  blocks or a dragged layer leaves its safe area; pink centre guides appear while
  dragging. Text type is never drawn by the browser: every move is an offset Python
  lays out again. The photograph is selected before it can be dragged. Photos are a
  ruled thumbnail list with pixels and a green or red DPI note; fonts show a
  specimen drawn by the cover renderer. Print quality is a large serif DPI figure
  beside its minimum, with the pixels and inches behind it. Below 1200px the tools,
  properties and checks share one tabbed panel beside the canvas, and below 800px
  under it. Overlays are thin labeled lines from Python geometry, off by default.
  Presets stay few and named; overrides are per text layer; there are no effects,
  shapes or free graphics.
- Publishing: a production handoff. A ruled summary (the front panel cropped from
  the real cover raster, book facts, separate text verdicts) above a metadata form
  beside a readiness column. Readiness is an ordered list of what is done and what
  is left, each line saying why and linking where to act, then a ruled checklist
  by stage (Book content, Interior, Cover, Metadata, Rights and AI disclosure, ISBN
  and classification, Final confirmations), open where something blocks, with
  official sources. Python findings sit beside their fields as text.
  Nothing is preselected for the author; export is one deliberate action and its
  summary never implies submission. No success banners or statistics.
- Planning: a research notebook and book blueprint. A ruled section list (with
  counts to fix or review) beside one section's fields and a readiness column with
  each gate as a text verdict, the approval and feasibility items saying how each
  is known. Research notes say what kind of statement they are; nothing implies a
  verified market; verified sources carry a solid green label and every other
  kind a dashed amber "not verified" label. Charts are semantic tables of Python's numbers in one green,
  values as text, level progression as numbered cells. Approval is one deliberate
  action on the saved plan; nothing is preselected or approved for the author.
- States: text and recovery actions for errors, meaningful empty states, polite
  loading status. A single loading-line animation respects reduced motion.

## Do's and Don'ts

### Do:
- Do preserve author-defined ordering and exact seed strings.
- Do use real placements for solutions and state coordinate conventions.
- Do keep source text escaped and long identities wrap-safe.
- Do preserve keyboard controls, focus visibility and non-color status cues.

### Don't:
- Don't fabricate publishing or financial status, or cover content beyond what the
  author wrote.
- Don't present Cover Studio as an image editor or imply AI generation, and don't
  draw cover type in the browser.
- Don't let a hidden or restyled cover layer change book metadata.
- Don't introduce gradients, glass effects, decorative charts or nested cards.
- Don't imply that no quality findings means publication readiness.
- Don't present future workflows as working navigation.
- Don't imply preflight readiness means Amazon will accept a book.
- Don't preselect a declaration, confirmation or ISBN choice for the author, or
  present a local export as a KDP submission.
- Don't present research notes as verified market findings, invent comparable
  books or metrics, or imply planning approval is publishing approval.
