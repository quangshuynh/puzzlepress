// Transport views only. Python owns all validation, generation and quality rules.
export interface Issue {
  path: string;
  code: string;
  message: string;
}
export interface Definition {
  id: string;
  title: string;
  theme: string;
  bank: string;
  target_ids: string[];
  difficulty: string;
}
export interface Profile {
  id: string;
  width: number;
  height: number;
  directions: string[];
  max_restarts: number;
  max_attempts: number;
}
export interface QualityConfig {
  max_word_reuse: number;
  target_similarity_threshold: number;
  grid_similarity_threshold: number;
  prohibited_words: string[];
}
export interface MatterItem {
  kind: string;
  title?: string;
  text?: string;
}
export interface Composition {
  front_matter: MatterItem[];
  puzzles: { start: string };
  solutions: { placement: string; title?: string; per_page?: number; start?: string };
  back_matter: MatterItem[];
  page_numbers: {
    scheme: string;
    show_front_matter: boolean;
    show_solutions: boolean;
    show_back_matter: boolean;
  };
}
export interface Project {
  key: string;
  revision?: string;
  identity?: string;
  engine_version?: string;
  validation: { valid: boolean; issues: Issue[] };
  source?: {
    schema_version: number;
    book: {
      id: string;
      title: string;
      language: string;
      subtitle: string | null;
      description: string | null;
      author: string | null;
      imprint: string | null;
    };
    build: { seed: string };
    content: { items: string[] };
    output: { directory: string };
    word_search?: {
      banks: { id: string; entries: { id: string; display: string }[] }[];
      profiles: Profile[];
      puzzles: Definition[];
      quality: QualityConfig;
    };
    composition?: Composition;
    cover?: CoverConfig;
  };
}
export interface Cell {
  x: number;
  y: number;
}
export interface Finding {
  code: string;
  message: string;
  puzzle_ids: string[];
  words: string[];
  severity: string;
}
export interface Scan {
  occurrences: { word: string; coordinates: Cell[] }[];
  truncated: boolean;
}
export interface PuzzleResult {
  id: string;
  title: string;
  theme: string;
  difficulty: string;
  seed: string;
  errors: Issue[];
  failure_stats: { attempts: number; restarts: number } | null;
  quality: {
    accidental_targets: Scan;
    prohibited: Scan;
    prohibited_screening_enabled: boolean;
  } | null;
  puzzle: {
    grid: string[];
    config: Omit<Profile, 'id'>;
    targets: { id: string; display: string; search: string }[];
    placements: { target_id: string; search: string; start: Cell; end: Cell; direction: string }[];
    stats: { attempts: number; restarts: number };
  } | null;
}
export interface Generation {
  report: {
    identity: string;
    success: boolean;
    clean: boolean;
    pipeline_version: number;
    puzzles: PuzzleResult[];
    findings: Finding[];
    quality_config: QualityConfig;
    reuse: { word: string; puzzle_ids: string[] }[];
    similarities: {
      left_id: string;
      right_id: string;
      shared_words: string[];
      target_jaccard: number;
      target_overlap: number;
      grid_agreement: number | null;
      identical_targets: boolean;
    }[];
  };
  verification: Record<string, { valid: boolean; issues: Issue[] } | null>;
  solution_cells: Record<string, Record<string, Cell[]>>;
}
export interface PlanPuzzle {
  id: string;
  ordinal: number;
  title: string;
  theme: string;
  seed: string;
  digest: string | null;
}
export interface PlanPage {
  index: number;
  side: 'recto' | 'verso';
  section: 'front_matter' | 'puzzles' | 'solutions' | 'back_matter';
  kind: string;
  number: { value: number; style: string; label: string; displayed: boolean };
  heading: string | null;
  matter: {
    title: string | null;
    subtitle: string | null;
    author: string | null;
    imprint: string | null;
    text: string | null;
  } | null;
  puzzle: PlanPuzzle | null;
  solution_page: number | null;
  solutions: { puzzle: PlanPuzzle; puzzle_page: number }[];
  blank: { reason: string; before_section: string | null } | null;
}
export interface PlanResult {
  plan: {
    plan_version: number;
    identity: string;
    book_id: string;
    complete: boolean;
    pages: PlanPage[];
    statistics: {
      logical_pages: number;
      front_matter_pages: number;
      puzzle_pages: number;
      solution_pages: number;
      back_matter_pages: number;
      blank_pages: number;
      puzzles: number;
      solutions: number;
      first_puzzle_page: number | null;
      first_solution_page: number | null;
    };
    diagnostics: Issue[];
  };
  verification: { valid: boolean; issues: Issue[] };
  generation: { success: boolean; clean: boolean; quality_findings: number };
}
// Print preview and preflight. Verdicts, geometry and page meaning come from Python.
export interface PtBox {
  x: number;
  y: number;
  width: number;
  height: number;
}
export interface Measure {
  actual: number | string;
  required: number | string | null;
  unit: string | null;
  comparison: string | null;
}
export interface PreflightFinding {
  rule: string;
  severity: 'error' | 'warning' | 'info';
  scope: 'structural' | 'kdp';
  category: string;
  message: string;
  physical_page: number | null;
  logical_page: number | null;
  page_kind: string | null;
  side: 'recto' | 'verso' | null;
  folio: string | null;
  subject: string | null;
  region: string | null;
  bounds: PtBox | null;
  measure: Measure | null;
}
export interface PreflightRule {
  code: string;
  scope: 'structural' | 'kdp';
  category: string;
  severity: 'error' | 'warning' | 'info';
  title: string;
  description: string;
  basis: string;
  source: string;
  help: string;
  outcome: 'passed' | 'failed' | 'not_applicable' | 'not_evaluated';
  findings: number;
  note: string | null;
  measure: Measure | null;
}
export interface PreviewPage {
  physical_page: number;
  logical_page: number | null;
  kind: string | null;
  side: 'recto' | 'verso' | null;
  folio: string | null;
  description?: string;
  findings: { error: number; warning: number; info: number };
}
export interface PageGeometry {
  physical_page: number;
  trim: PtBox;
  live: PtBox;
  kdp_safe: PtBox | null;
  elements: { role: string; box: PtBox }[];
}
export interface PreflightReport {
  report_version: number;
  ruleset: { id: string; version: number; kdp_rules_checked: string };
  book_id: string;
  source_identity: string;
  profile: {
    id: string;
    version: number;
    description: string;
    trim: { name: string; width_in: number; height_in: number };
    bleed: boolean;
  } | null;
  artifacts: {
    pdf: { sha256: string; bytes: number } | null;
    manifest: { sha256: string; bytes: number } | null;
    interior_identity: string | null;
    expected_interior_identity: string | null;
    matches_layout: boolean;
  };
  page_count: number | null;
  structural: { status: 'valid' | 'invalid' };
  kdp: { status: 'ready' | 'not_ready' };
  counts: { severity: Record<string, number>; outcome: Record<string, number> };
  findings: PreflightFinding[];
  rules: PreflightRule[];
  pages: PreviewPage[];
}
export interface BuildDiagnostic {
  code: string;
  message: string;
  page: number | null;
  physical_page: number | null;
  kind: string | null;
  subject: string | null;
  region: string | null;
  actual: string | null;
  required: string | null;
}
export interface InteriorStatus {
  key: string;
  revision: string;
  ruleset: number;
  profiles?: { id: string; description: string; paper: string }[];
  profile?: string;
  state: 'missing' | 'current' | 'stale' | 'invalid';
  report: PreflightReport | null;
  preview: {
    pdf_sha256: string;
    page_count: number;
    scales: Record<string, number>;
    pages: PreviewPage[];
    geometry: PageGeometry[] | null;
  } | null;
  build?: { success: boolean; stage?: string; diagnostics?: BuildDiagnostic[] };
}
// Cover Studio. Geometry, crop windows, resolution and verdicts come from Python.
export interface CoverConfig {
  version: number;
  layout: 'full_wrap' | 'front_photo';
  image: { path: string; sha256: string };
  crop: { x: number; y: number; zoom: number };
  type: {
    style: 'editorial' | 'bold' | 'minimal';
    position: 'top' | 'middle' | 'bottom';
    align: 'center' | 'left';
    tone: 'light' | 'dark';
  };
  legibility: 'shade' | 'panel' | 'none';
  background: string;
  spine_text: 'auto' | 'none';
  back_text?: string;
}
export interface CoverAsset {
  path: string;
  problem: string | null;
  sha256?: string;
  format?: string;
  bytes?: number;
  pixels?: [number, number];
  orientation?: number;
  color?: string;
  reused?: boolean;
}
export type CoverRegion =
  | 'media'
  | 'trim'
  | 'back'
  | 'spine'
  | 'front'
  | 'back_safe'
  | 'front_safe'
  | 'spine_safe'
  | 'back_design'
  | 'front_design'
  | 'barcode'
  | 'barcode_keep_clear';
export interface CoverGeometry {
  page_count: number;
  paper: string;
  bleed_in: number;
  spine_width_in: number;
  spine_width_pt: number;
  width_in: number;
  height_in: number;
  spine_text_allowed: boolean;
  regions: Record<CoverRegion, PtBox>;
}
export interface CoverResolution {
  source_pixels: [number, number];
  used_pixels: [number, number];
  printed_inches: [number, number];
  effective_dpi: number;
  max_dpi: number;
  minimum_dpi: number;
  status: 'ok' | 'image_low_effective_dpi' | 'image_too_small';
}
export interface CoverSpine {
  allowed_by_page_count: boolean;
  rendered: boolean;
  reason: 'authored' | 'page_count' | 'spine_too_narrow' | null;
  size: number | null;
}
export interface CoverLayoutView {
  geometry: CoverGeometry;
  texts: {
    role: string;
    text: string;
    panel: string;
    size: number;
    rotated: boolean;
    box: PtBox;
  }[];
  panels: { role: string; box: PtBox }[];
  photo: {
    region: PtBox;
    window: { left: number; top: number; right: number; bottom: number };
    center: [number, number];
    pixels: [number, number, number, number];
  };
  resolution: CoverResolution;
  spine_text: CoverSpine;
}
export interface CoverCheck {
  code: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
}
export interface CoverDraft {
  success: boolean;
  stage?: string;
  diagnostics?: BuildDiagnostic[];
  interior?: {
    page_count: number;
    profile_id: string;
    paper: string;
    ink: string;
    trim_in: [number, number];
    stale: string | null;
  };
  cover_identity?: string;
  layout?: CoverLayoutView;
  checks?: CoverCheck[];
  preview?: { pdf_sha256: string; scales: Record<string, number> };
}
export interface CoverReport {
  report_version: number;
  ruleset: { id: string; version: number; kdp_rules_checked: string };
  state: string;
  cover_identity: { recorded: string | null; expected: string | null };
  interior: { page_count: number; paper: string; profile_id: string } | null;
  artifacts: {
    pdf: { sha256: string; bytes: number } | null;
    manifest: { sha256: string; bytes: number } | null;
    matches_render: boolean;
  };
  structural: { status: 'valid' | 'invalid' };
  kdp: { status: 'ready' | 'not_ready' };
  findings: PreflightFinding[];
  rules: PreflightRule[];
}
export interface CoverStatus {
  key: string;
  revision: string;
  state: 'no_config' | 'missing' | 'current' | 'stale' | 'invalid';
  report: CoverReport | null;
  layout?: CoverLayoutView | null;
  preview: { pdf_sha256: string; scales: Record<string, number> } | null;
  build?: { success: boolean; stage?: string; diagnostics?: BuildDiagnostic[] };
}
