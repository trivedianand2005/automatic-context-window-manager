// Mirrors the Pydantic models served by the ACWM FastAPI backend.

export type Mode = "acwm" | "dependency" | "baseline";
export type Compression = "extractive" | "llm" | "none";
export type ExportFormat = "markdown" | "json" | "txt";

export interface Weights {
  lexical: number;
  filename: number;
  symbol: number;
  dependency: number;
  test: number;
  config: number;
  semantic: number;
}

export interface ExampleRepository {
  name: string;
  path: string;
  description: string;
}

export interface ConfigResponse {
  sample_repository_path: string;
  example_repositories: ExampleRepository[];
  budget: {
    total_tokens: number;
    reserved_system_tokens: number;
    reserved_response_tokens: number;
    safety_margin_ratio: number;
    per_item_overhead_tokens: number;
  };
  weights: Weights;
  expansion_depth: number;
  modes: Record<Mode, string>;
  tokenizer_encoding: string;
  providers: Record<string, string>;
}

export interface Health {
  status: "ok";
  version: string;
  providers: Record<string, string>;
}

export interface ExcludedFile {
  path: string;
  reason: string;
}

export interface IndexingReport {
  root: string;
  total_discovered: number;
  indexed: number;
  skipped: number;
  excluded: ExcludedFile[];
  file_types: Record<string, number>;
  languages: Record<string, number>;
  total_tokens: number;
  total_bytes: number;
  parse_warnings: string[];
  limit_reached: string | null;
  tokenizer: string;
  duration_ms: number;
}

export interface RepositorySummary {
  repository_id: string;
  root_name: string;
  fingerprint: string;
  indexed_files: number;
  languages: Record<string, number>;
  file_types: Record<string, number>;
  total_tokens: number;
  module_count: number;
  symbol_count: number;
  dependency_edges: number;
}

export interface IndexResponse {
  repository: RepositorySummary;
  report: IndexingReport;
}

export interface FileInfo {
  path: string;
  file_type: string;
  language: string;
  tokens: number;
  line_count: number;
  symbol_count: number;
  parse_error: string | null;
}

export interface SymbolInfo {
  id: string;
  qualname: string;
  kind: string;
  signature: string;
  start_line: number;
  end_line: number;
  docstring: string | null;
}

export interface GraphNode {
  id: string;
  kind: string;
  path: string;
  file_type: string;
  language: string;
  tokens: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  confidence: "high" | "medium" | "low";
  relations?: string[];
}

export interface RepositoryDetails {
  repository: RepositorySummary;
  report: IndexingReport;
  files: FileInfo[] | null;
  symbols: Record<string, SymbolInfo[]> | null;
  graph: { nodes: GraphNode[]; edges: GraphEdge[] } | null;
}

export interface ScoreBreakdown {
  lexical: number;
  filename: number;
  symbol: number;
  dependency: number;
  test: number;
  config: number;
  semantic: number;
}

export interface ContextItem {
  path: string;
  kind: "full" | "excerpt" | "outline" | "summary";
  is_partial: boolean;
  language: string;
  file_type: string;
  line_ranges: [number, number][];
  total_lines: number;
  symbols: string[];
  tokens: number;
  full_file_tokens: number;
  combined_score: number;
  scores: ScoreBreakdown;
  reasons: string[];
  selection_note: string;
  required: boolean;
  dependency_path: string[];
  content: string;
}

export interface TokenStats {
  tokenizer: string;
  exact_for_target_model: boolean;
  total_indexed_tokens: number;
  candidate_tokens: number;
  selected_tokens: number;
  rendered_context_tokens: number;
  total_budget: number;
  reserved_system_tokens: number;
  reserved_task_tokens: number;
  reserved_response_tokens: number;
  safety_margin_tokens: number;
  usable_tokens: number;
  remaining_tokens: number;
  utilization: number;
  reduction_vs_full_repository: number | null;
  reduction_vs_baseline: number | null;
}

export interface ResearchFinding {
  title: string;
  url: string;
  snippet: string;
  source: string;
  provider_status: string;
}

export interface ContextPackage {
  schema_version: string;
  task: string;
  analysis: {
    keywords: string[];
    technical_terms: string[];
    component_names: string[];
    expanded_terms: string[];
    wants_tests: boolean;
    config_terms: string[];
    analyzer: string;
  };
  repository: RepositorySummary;
  configuration: {
    mode: string;
    weights: Record<string, number>;
    expansion_depth: number;
    compression: string;
    semantic: string;
    llm: string;
    analyzer: string;
    required_paths: string[];
  };
  items: ContextItem[];
  dependencies: { source: string; target: string; relation: string; confidence: string }[];
  tests: string[];
  config_files: string[];
  excluded: { path: string; tokens: number; combined_score: number; reason: string }[];
  omissions: string[];
  warnings: string[];
  token_stats: TokenStats;
  research_findings: ResearchFinding[];
  latency_ms: number;
  disclaimer: string;
}

export interface MethodResult {
  mode: Mode;
  label: string;
  selected: string[];
  kinds: Record<string, string>;
  rendered_tokens: number;
  usable_tokens: number;
  utilization: number;
  budget_violation: boolean;
  latency_ms: number;
  precision_at_k: number | null;
  recall_at_k: number | null;
  mrr: number | null;
  coverage: number | null;
  full_coverage: number | null;
  missing_relevant: string[];
}

export interface ComparisonResult {
  task: string;
  k: number;
  relevant_paths: string[];
  methods: MethodResult[];
  notes: string[];
}

export interface BenchmarkTask {
  id: string;
  task: string;
  relevant: string[];
  rationale: string;
}

export interface BenchmarkReport {
  repository: string;
  token_budget: number;
  k: number;
  tasks: ComparisonResult[];
  aggregate: Record<Mode, Record<string, number | null>>;
  tokenizer: string;
  notes: string[];
}

export interface RunInfo {
  timestamp: number;
  repository_id: string;
  task: string;
  mode: string;
  selected_files: number;
  rendered_tokens: number;
  usable_tokens: number;
  latency_ms: number;
}

export interface BuildRequest {
  repository_id: string;
  task: string;
  mode?: Mode;
  token_budget?: number;
  expansion_depth?: number;
  compression?: Compression;
  weights?: Weights;
  include_research?: boolean;
  redundancy_penalty?: boolean;
  required_paths?: string[];
}

// ------------------------------------------------------------------ accounts
export interface User {
  id: number;
  display_name: string;
  email: string | null;
  github_login: string | null;
  created_at: string;
}

export interface AuthResponse {
  token: string;
  token_type: "bearer";
  expires_in_minutes: number;
  user: User;
}

export interface AuthProviders {
  email_password: boolean;
  github: boolean;
  require_auth: boolean;
  database: string;
}

export interface SavedPackageSummary {
  id: number;
  title: string;
  task: string;
  repository_name: string;
  item_count: number;
  rendered_tokens: number;
  created_at: string;
}

export interface SavedPackageFull extends SavedPackageSummary {
  package: ContextPackage;
}

// ------------------------------------------------------------ conversation manager
export type ConversationStrategy = "full" | "truncation" | "acwm";
export type ConversationBudgetStatus = "ok" | "over_target" | "over_budget";

export interface ConversationBudgetEvent {
  turn: number;
  status: Exclude<ConversationBudgetStatus, "ok">;
  message: string;
}

export interface ConversationModelStatus {
  backend: string;
  model: string;
  real_model: boolean;
  status: string;
}

export interface ConversationStatus {
  manager: ConversationModelStatus;
  main_model: ConversationModelStatus;
  live_runs_enabled: boolean;
  live_available: boolean;
  default_budget_tokens: number;
  context: Record<string, number>;
}

export interface ConversationSummary {
  strategy: ConversationStrategy;
  turns_completed: number;
  overflow_turn: number | null;
  main_input_tokens: number;
  main_output_tokens: number;
  manager_input_tokens: number;
  manager_output_tokens: number;
  total_tokens: number;
  main_cost_usd: number;
  manager_cost_usd: number;
  total_cost_usd: number;
  manager_calls: number;
  manager_latency_ms: number;
  compactions: number;
  manager_failures: number;
  budget_exceeded_turns: number;
  over_target_turns: number;
  recall_correct: number;
  recall_total: number;
  recall_accuracy: number;
}

export interface ConversationTurn {
  turn: number;
  context_tokens: number;
  usage_ratio: number;
  main_model: string;
  main_input_tokens: number;
  main_output_tokens: number;
  main_cost_usd: number;
  manager_calls: number;
  manager_input_tokens: number;
  manager_output_tokens: number;
  manager_latency_ms: number;
  manager_cost_usd: number;
  compaction: "llm" | "heuristic" | null;
  budget_status: ConversationBudgetStatus;
  budget_exceeded: boolean;
}

export interface ConversationAnswer {
  question_id: string;
  turn: number;
  fact_turn: number;
  question: string;
  expected_keywords: string[];
  answer: string;
  correct: boolean;
}

export interface ConversationResults {
  mode: string;
  budget_tokens: number;
  main_model: string;
  manager_model: string;
  judge: string;
  turns: number;
  recall_questions: number;
  summary: ConversationSummary[];
  per_turn: Record<ConversationStrategy, ConversationTurn[]>;
  answers: Record<ConversationStrategy, ConversationAnswer[]>;
  budget_events: Record<ConversationStrategy, ConversationBudgetEvent[]>;
}

/** `details` of a 422 `budget_exceeded` error from POST /context/build. */
export interface BudgetIssue {
  reason: "reservations" | "required_files";
  message: string;
  total_budget: number;
  needed_tokens: number;
  available_tokens: number;
  shortfall_tokens: number;
  reservations: { system: number; task: number; response: number; safety_margin: number };
  suggested_budget: number;
}
