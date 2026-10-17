import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { StoreProvider } from "./lib/store";

// recharts / React Flow need ResizeObserver, which jsdom lacks.
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;

const summary = {
  repository_id: "abc123", root_name: "sample_fastapi_repo", fingerprint: "f", indexed_files: 49,
  languages: { python: 41 }, file_types: { source: 32 }, total_tokens: 9794, module_count: 41,
  symbol_count: 145, dependency_edges: 57,
};
const report = {
  root: "/x", total_discovered: 49, indexed: 49, skipped: 0, excluded: [], file_types: {}, languages: {},
  total_tokens: 9794, total_bytes: 1, parse_warnings: [], limit_reached: null, tokenizer: "tiktoken:cl100k_base", duration_ms: 5,
};
const scores = { lexical: 0.9, filename: 0.5, symbol: 0.9, dependency: 0.6, test: 0, config: 0, semantic: 0 };
const pkg = {
  schema_version: "1.0", task: "Add JWT authentication",
  analysis: { keywords: ["jwt", "authentication"], technical_terms: [], component_names: [], expanded_terms: [], wants_tests: true, config_terms: [], analyzer: "deterministic" },
  repository: summary,
  configuration: { mode: "Full ACWM (hybrid)", weights: {}, expansion_depth: 2, compression: "extractive", semantic: "disabled", llm: "not used", analyzer: "deterministic", required_paths: [] },
  items: [
    { path: "shopapi/api/dependencies.py", kind: "full", is_partial: false, language: "python", file_type: "source", line_ranges: [[1, 30]], total_lines: 30, symbols: [], tokens: 225, full_file_tokens: 201, combined_score: 0.67, scores, reasons: ["BM25 match on auth"], selection_note: "full file", required: false, dependency_path: [], content: "def get_current_user():\n    pass\n" },
    { path: "tests/conftest.py", kind: "excerpt", is_partial: true, language: "python", file_type: "test", line_ranges: [[3, 12]], total_lines: 36, symbols: [], tokens: 190, full_file_tokens: 203, combined_score: 0.62, scores, reasons: ["test file linked to relevant code"], selection_note: "excerpt", required: false, dependency_path: [], content: "# --- lines 3-12 ---\nimport pytest\n" },
  ],
  dependencies: [], tests: ["tests/conftest.py"], config_files: [], excluded: [], omissions: ["Some files are partial excerpts."], warnings: ["Token counts are estimates."],
  token_stats: { tokenizer: "tiktoken:cl100k_base", exact_for_target_model: false, total_indexed_tokens: 9794, candidate_tokens: 9000, selected_tokens: 415, rendered_context_tokens: 1850, total_budget: 4000, reserved_system_tokens: 400, reserved_task_tokens: 31, reserved_response_tokens: 1500, safety_margin_tokens: 200, usable_tokens: 1869, remaining_tokens: 19, utilization: 0.99, reduction_vs_full_repository: 0.81, reduction_vs_baseline: null },
  research_findings: [], latency_ms: 51, disclaimer: "Heuristic selection.",
};

function mockApi() {
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push(`${init?.method ?? "GET"} ${url.replace(/^https?:\/\/[^/]+/, "")}`);
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
    if (url.endsWith("/health")) return json({ status: "ok", version: "0.1.0", providers: { llm: "unconfigured" } });
    if (url.endsWith("/config")) return json({ sample_repository_path: "/srv/examples/sample_fastapi_repo", budget: { total_tokens: 8000, reserved_system_tokens: 400, reserved_response_tokens: 1500, safety_margin_ratio: 0.05, per_item_overhead_tokens: 24 }, weights: { lexical: 0.35, filename: 0.1, symbol: 0.15, dependency: 0.2, test: 0.1, config: 0.05, semantic: 0 }, expansion_depth: 2, modes: {}, tokenizer_encoding: "cl100k_base", providers: {} });
    if (url.endsWith("/benchmarks")) return json({ repository: "examples/sample_fastapi_repo", tasks: [{ id: "jwt-auth", task: "Add JWT authentication", relevant: [], rationale: "" }], labeling_notes: "" });
    if (url.includes("/runs")) return json([]);
    if (url.endsWith("/repositories/index")) return json({ repository: summary, report });
    if (url.includes("/repositories/abc123")) return json({ repository: summary, report, files: [], symbols: {}, graph: { nodes: [], edges: [] } });
    if (url.endsWith("/context/build")) return json(pkg);
    return json({ error: { code: "not_found", message: "nope" } }, 404);
  });
  return calls;
}

describe("App", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("connects, runs the demo and shows explained results", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    render(<StoreProvider><App /></StoreProvider>);

    expect(await screen.findByText(/API online/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run the demo" }));

    expect(await screen.findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(calls).toContain("POST /repositories/index"); // sample indexed automatically
    expect(calls).toContain("POST /context/build");
    expect(screen.getByText("shopapi/api/dependencies.py")).toBeInTheDocument();
    expect(screen.getAllByText("1,850").length).toBeGreaterThanOrEqual(2); // stat + budget meter
    expect(screen.getByText("99%")).toBeInTheDocument();

    // Expanding an item shows its score breakdown and code.
    await user.click(screen.getByRole("button", { name: /shopapi\/api\/dependencies\.py/ }));
    expect(screen.getByText("Score components")).toBeInTheDocument();
    expect(screen.getByText(/get_current_user/)).toBeInTheDocument();

    // Warnings are surfaced, not hidden.
    await user.click(screen.getByRole("tab", { name: /Omissions & warnings/ }));
    expect(screen.getByText("Token counts are estimates.")).toBeInTheDocument();
  });

  it("shows the backend's error message when indexing is rejected", async () => {
    mockApi();
    vi.mocked(globalThis.fetch).mockImplementationOnce(async () =>
      new Response(JSON.stringify({ status: "ok", version: "0.1.0", providers: {} }), { status: 200 }));
    const user = userEvent.setup();
    render(<StoreProvider><App /></StoreProvider>);
    expect(await screen.findByText(/API online/)).toBeInTheDocument();

    vi.mocked(globalThis.fetch).mockImplementation(async () =>
      new Response(JSON.stringify({ error: { code: "path_not_allowed", message: "Repository path is outside the allowed roots." } }), { status: 403 }));
    const nav = screen.getByRole("navigation", { name: "Main" });
    await user.click(within(nav).getByRole("button", { name: "Repository" }));
    await user.click(screen.getByRole("button", { name: "Index repository" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("outside the allowed roots");
  });
});
