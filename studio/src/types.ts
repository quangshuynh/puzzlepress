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
