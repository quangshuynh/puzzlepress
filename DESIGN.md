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
    fontSize: "clamp(34px, 3.4vw, 48px)"
    fontWeight: 450
    lineHeight: 1.14
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Newsreader Variable, Georgia, serif"
    fontSize: "29px"
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
    padding: "10px 18px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.paper}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.primary}"
    rounded: "{rounded.control}"
    padding: "10px 18px"
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

Desktop uses a 222px library rail, 66px context header, and 48px main gutters.
The rail narrows to 185px below 1150px and becomes a compact top header at 850px.
At 600px, main gutters become 20px and inspector columns stack. Large grids scroll
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

- Buttons: 44px minimum height, explicit verbs, dark-green primary action,
  bordered secondary action. Focus is a 3px brown outline with a 4px offset.
- Search: visible label, paper surface, thin border, distinct focus outline.
- Navigation: ordinary links, current-page semantics, a bottom rule for project tabs.
- Lists: ruled project and definition rows, real counts, no decorative statistics.
- Inspector: semantic letter table, highlighted solution cells with underlines and
  heavier weight, plus a textual coordinate register.
- Details: native disclosure for developer payloads and less-used configuration.
- Composer: a manuscript outline. Sections open with a heavy ink rule and a serif
  heading; items are ruled rows with compact Up/Down/Remove buttons. The plan is a
  semantic table grouped by section, with side and number as text, uncounted
  numbers in parentheses and blanks on canvas with their reason. It is a logical
  list, never a simulated page spread or print preview.
- Print proof: the rasterized PDF page is the dominant artifact on a neutral
  canvas, flanked by page thumbnails and a ruled findings column. Structural and
  KDP verdicts are separate text statuses, never one badge. Findings state what,
  where, measured and required values, and what they block. Overlays are thin
  dashed SVG lines over the raster, labeled and off by default; the binding edge
  is marked. Passed checks are secondary disclosures.
- States: text and recovery actions for errors, meaningful empty states, polite
  loading status. A single loading-line animation respects reduced motion.

## Do's and Don'ts

### Do:
- Do preserve author-defined ordering and exact seed strings.
- Do use real placements for solutions and state coordinate conventions.
- Do keep source text escaped and long identities wrap-safe.
- Do preserve keyboard controls, focus visibility and non-color status cues.

### Don't:
- Don't fabricate cover, publishing or financial status.
- Don't introduce gradients, glass effects, decorative charts or nested cards.
- Don't imply that no quality findings means publication readiness.
- Don't present future workflows as working navigation.
- Don't imply preflight readiness means Amazon will accept a book.
