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
    publishing?: PublishingConfig;
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
  // Version 2: per-layer overrides, extra layers and imported fonts.
  text?: Partial<Record<TextRole, TextLayer>>;
  extra?: ExtraLayer[];
  fonts?: CoverFont[];
}
export type TextRole = 'title' | 'subtitle' | 'author' | 'back_text' | 'imprint';
export interface TextLayer {
  visible?: boolean;
  text?: string;
  font?: string;
  size?: number;
  color?: string;
  align?: 'left' | 'center' | 'right';
  line_spacing?: number;
  letter_spacing?: number;
  case?: 'as_written' | 'upper';
  offset?: { x: number; y: number };
}
export interface ExtraLayer extends Omit<TextLayer, 'text'> {
  id: string;
  panel: 'front' | 'back';
  text: string;
}
export interface CoverFont {
  id: string;
  path: string;
  sha256: string;
  license?: string | null;
  source?: string | null;
}
export interface FontFacts {
  path: string;
  problem: string | null;
  message?: string | null;
  sha256?: string;
  bytes?: number;
  container?: string;
  postscript_name?: string;
  family?: string;
  style?: string;
  full_name?: string;
  weight?: number;
  italic?: boolean;
  glyphs?: number;
  embedding?: 'installable' | 'editable' | 'preview_print';
  missing?: string[];
  reused?: boolean;
}
export interface PhotoOption extends CoverAsset {
  dpi?: { effective: number; max: number; zoom: number; minimum: number; sufficient: boolean };
}
export interface CoverLibrary {
  photos: PhotoOption[];
  fonts: FontFacts[];
  bundled_fonts: { key: string; family: string; style: string; missing: string[] }[];
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
    layer: string; // title, subtitle, author, back_text, imprint, spine or extra:<id>.
    text: string;
    panel: string;
    size: number;
    face: string;
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
  layer?: string;
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
  buildable?: boolean;
  display?: Record<'title' | 'subtitle' | 'author' | 'imprint', string | null>;
  library?: CoverLibrary;
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
// Publishing. Metadata rules, readiness verdicts and the package come from Python.
export type ContentOrigin = 'unknown' | 'human' | 'ai_assisted' | 'ai_generated' | 'none';
export type ConfirmationName = 'rights' | 'ai_disclosure' | 'metadata' | 'isbn';
// Version 2 stores the review identity Python reported for the confirmed content, or
// null; version 1 stored booleans, which Python never treats as current confirmations.
export type StoredConfirmation = string | boolean | null;
export interface PublishingConfig {
  version: number;
  description: string | null;
  keywords: string[];
  categories: string[];
  contributors: { role: string; name: string }[];
  audience: {
    sexually_explicit: boolean | null;
    reading_age: { minimum: number | null; maximum: number | null };
  };
  low_content: boolean | null;
  isbn: { mode: 'undecided' | 'kdp_free' | 'own' | 'none'; value: string | null };
  edition: number | null;
  series: { title: string; number: number | null } | null;
  ai_disclosure: { text: ContentOrigin; images: ContentOrigin; translations: ContentOrigin };
  attestations: Record<ConfirmationName, StoredConfirmation>;
  notes: string | null;
}
export interface Confirmation {
  name: ConfirmationName;
  statement: string;
  covers: string;
  required: boolean;
  state: 'confirmed' | 'stale' | 'unconfirmed' | 'legacy';
  current: string;
  confirmed: string | null;
  message: string;
}
export interface PublishingFinding {
  code: string;
  severity: 'error' | 'warning' | 'info';
  scope: string;
  basis: string;
  source: { title: string; url: string };
  message: string;
  field: string | null;
  artifact: string | null;
  actual: number | string | null;
  required: number | string | null;
  action: string | null;
  area: 'publishing' | 'edit' | 'book' | 'print' | 'cover';
  related: string | null;
}
export interface PublishingRule {
  code: string;
  scope: string;
  severity: 'error' | 'warning' | 'info';
  title: string;
  basis: string;
  source: { title: string; url: string };
  outcome: 'passed' | 'failed' | 'not_applicable' | 'not_evaluated';
  findings: number;
  note: string | null;
}
export interface ArtifactVerdict {
  state: string;
  structural: string;
  kdp: string;
}
export interface PublishingVerdicts {
  metadata: 'missing' | 'valid' | 'invalid';
  disclosure: 'complete' | 'incomplete';
  attestations: 'complete' | 'incomplete';
  interior?: ArtifactVerdict;
  cover?: ArtifactVerdict;
  artifacts?: string;
  package?: 'ready' | 'not_ready';
}
export interface MetadataReport {
  ruleset: { id: string; version: number; kdp_rules_checked: string };
  publishing_identity: string | null;
  verdicts: PublishingVerdicts;
  confirmations: Confirmation[];
  findings: PublishingFinding[];
  rules: PublishingRule[];
}
export interface PublishingDraftCheck {
  metadata: MetadataReport;
  // The section as version 2, every confirmation unconfirmed; only for version 1.
  upgrade: PublishingConfig | null;
}
export interface ReadinessReport extends MetadataReport {
  statement: string;
  identities: Record<string, unknown>;
  print: {
    format: string;
    profile: { id: string; version: number };
    trim_in: [number, number];
    ink: string;
    paper: string;
    interior_bleed: boolean;
    page_count: number;
    cover: { width_in: number; height_in: number; spine_width_in: number; bleed_in: number } | null;
  } | null;
}
export interface PublishingStatus {
  key: string;
  revision: string;
  readiness: ReadinessReport;
  metadata_record: Record<string, unknown>;
  checklist: string;
  package: {
    identity: string | null;
    export: {
      state: 'none' | 'current' | 'stale' | 'damaged';
      identity: string | null;
      problem: string | null;
    };
    location: string;
    archive: string;
    files: { name: string; purpose: string }[];
  };
  cover_preview: { pdf_sha256: string } | null;
  export?: {
    success: boolean;
    code?: string;
    message?: string;
    identity?: string;
    archive?: boolean;
    files?: { name: string; sha256: string; bytes: number; purpose: string }[];
  };
}

// Book planning (planning.yaml). Python validates, analyses and decides readiness;
// these are the document and report as Python serializes them.
export type Evidence =
  | 'unknown'
  | 'verified_source'
  | 'unverified_source'
  | 'author_observation'
  | 'hypothesis'
  | 'preference';
export type WordSource =
  'unknown' | 'human' | 'public_reference' | 'licensed' | 'ai_assisted' | 'ai_generated';
export interface PlanWord {
  word: string;
  source: WordSource | null;
  reference: string | null;
  note: string | null;
}
export interface PlanPool {
  theme: string;
  source: WordSource;
  reference: string | null;
  entries: PlanWord[];
}
export interface PlanTheme {
  id: string;
  label: string;
  parent: string | null;
  required: boolean;
  puzzles: number | null;
  notes: string | null;
}
export interface PlanLevel {
  id: string;
  label: string;
  profile: string | null;
  width: number | null;
  height: number | null;
  directions: string[];
  words: { min: number | null; max: number | null };
  notes: string | null;
}
export interface PlannedPuzzle {
  id: string;
  theme: string;
  level: string | null;
  title: string | null;
  words: string[];
  notes: string | null;
}
export interface PlanQuestion {
  id: string;
  question: string;
  blocking: boolean;
  resolution: string | null;
}
export interface PlanNote {
  id: string;
  question: string | null;
  observation: string;
  evidence: Evidence;
  confidence: 'low' | 'medium' | 'high' | null;
  source: { citation: string | null; url: string | null; type: string | null };
  observed: string | null;
  relevance: string | null;
  notes: string | null;
  decision: string | null;
}
export interface PlanComparable {
  id: string;
  title: string;
  contributor: string | null;
  url: string | null;
  citation: string | null;
  format: string | null;
  trim: string | null;
  pages: number | null;
  puzzles: number | null;
  price: { amount: string; currency: string } | null;
  audience: string | null;
  strengths: string[];
  weaknesses: string[];
  positioning: string | null;
  observed: string | null;
  evidence: Evidence;
}
export interface PlanningSource {
  planning_version: number;
  concept: {
    summary: string | null;
    subject: string | null;
    reader_experience: string | null;
    scope: string | null;
  };
  positioning: {
    primary_audience: string | null;
    secondary_audience: string | null;
    candidate_audiences: string[];
    familiarity: string;
    tone: string | null;
    use_case: string | null;
    main_benefit: string | null;
    differentiation: string | null;
    evidence: string[];
    claims: { text: string; evidence: string[] }[];
  };
  structure: {
    puzzle_type: string | null;
    target_puzzles: number | null;
    print_profile: string | null;
    solutions: string;
    solutions_per_page: number | null;
    front_matter_pages: number | null;
    back_matter_pages: number | null;
  };
  difficulty: { strategy: string; levels: PlanLevel[] };
  themes: PlanTheme[];
  vocabulary: PlanPool[];
  puzzles: PlannedPuzzle[];
  constraints: {
    min_letters: number | null;
    max_letters: number | null;
    max_word_reuse: number | null;
    prohibited_words: string[];
    notes: string[];
  };
  questions: PlanQuestion[];
  research: PlanNote[];
  comparables: PlanComparable[];
  approval: string | null;
}
export interface PlanFinding {
  code: string;
  gate: string;
  severity: 'error' | 'warning' | 'info';
  basis: string;
  message: string;
  path: string | null;
  actual: string | number | null;
  expected: string | number | null;
  action: string | null;
  subjects: string[];
}
export type PlanningState =
  | 'draft'
  | 'needs_research'
  | 'needs_content'
  | 'structurally_valid'
  | 'production_feasible'
  | 'ready_for_approval'
  | 'approved';
export interface PlanningReport {
  report_version: number;
  ruleset: { id: string; version: number };
  book: { id: string; title: string };
  planning_identity: string;
  state: PlanningState;
  statement: string;
  gates: { gate: string; label: string; passed: boolean; blocking: string[] }[];
  approval: {
    status: 'none' | 'current' | 'stale';
    approved_identity: string | null;
    counts: boolean;
  };
  summary: {
    target_puzzles: number | null;
    allocated_puzzles: number;
    specified_puzzles: number;
    themes: number;
    levels: number;
    candidate_words: number;
    findings: { error: number; warning: number; info: number };
  };
  allocation: {
    id: string;
    label: string;
    parent: string | null;
    depth: number;
    required: boolean;
    allocated: number | null;
    specified: number;
    share: number | null;
  }[];
  levels: {
    id: string;
    label: string;
    rank: number;
    origin: string;
    width: number | null;
    height: number | null;
    directions: string[];
    words: { min: number; max: number };
    puzzles: number;
    supported: boolean;
  }[];
  progression: {
    id: string;
    title: string | null;
    theme: string;
    level: string | null;
    rank: number | null;
    words: number;
  }[];
  vocabulary: {
    theme: string;
    label: string | null;
    entries: number;
    usable: number;
    invalid: number;
    duplicates: number;
    shared: number;
    assigned: number;
    needed: number | null;
    sources: Record<string, number>;
    words: {
      word: string;
      search: string | null;
      source: WordSource;
      valid: boolean;
      duplicate: boolean;
      shared: boolean;
    }[];
  }[];
  research: {
    notes: number;
    evidence: Record<Evidence, number>;
    questions: number;
    open_questions: number;
    blocking_questions: number;
    comparables: number;
    sourced_comparables: number;
  };
  feasibility: {
    code: string;
    label: string;
    status: 'verified' | 'estimate' | 'unknown' | 'unsupported';
    detail: string;
    actual: string | number | null;
    limit: string | number | null;
  }[];
  page_estimate: {
    minimum: number | null;
    maximum: number | null;
    parts: Record<string, number | null>;
  };
  findings: PlanFinding[];
  boundary: string;
}
export interface PlanningStatus {
  key: string;
  book: { id: string; title: string };
  revision: string | null;
  source: PlanningSource | null;
  report: PlanningReport | null;
  options: PlanningOptions;
}
export interface PlanningOptions {
  print_profiles: { id: string; description: string }[];
  puzzle_types: string[];
  directions: string[];
}
