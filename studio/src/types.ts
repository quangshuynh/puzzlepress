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
