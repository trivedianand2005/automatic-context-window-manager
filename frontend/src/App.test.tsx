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

const convTurn = (turn: number, context_tokens: number, compaction: "llm" | null = null) => ({
  turn, context_tokens, usage_ratio: context_tokens / 4000, main_model: "claude-opus-5-5", main_input_tokens: context_tokens,
  main_output_tokens: 20, main_cost_usd: 0.001, manager_calls: compaction ? 1 : 0, manager_input_tokens: compaction ? 900 : 0,
  manager_output_tokens: compaction ? 200 : 0, manager_latency_ms: compaction ? 850 : 0, manager_cost_usd: compaction ? 0.0002 : 0, compaction,
  budget_status: compaction ? "over_target" : "ok", budget_exceeded: false,
});
const convSummary = (strategy: string, recall_correct: number, overflow_turn: number | null = null) => ({
  strategy, turns_completed: overflow_turn ? overflow_turn - 1 : 3, overflow_turn, main_input_tokens: 9000, main_output_tokens: 60,
  manager_input_tokens: strategy === "acwm" ? 900 : 0, manager_output_tokens: strategy === "acwm" ? 200 : 0, total_tokens: 9260,
  main_cost_usd: 0.04, manager_cost_usd: strategy === "acwm" ? 0.0002 : 0, total_cost_usd: 0.0402, manager_calls: strategy === "acwm" ? 1 : 0,
  manager_latency_ms: 850, compactions: strategy === "acwm" ? 1 : 0, manager_failures: 0, recall_correct, recall_total: 1,
  recall_accuracy: recall_correct, budget_exceeded_turns: overflow_turn ? 1 : 0, over_target_turns: strategy === "acwm" ? 1 : 0,
});
const convAnswer = (correct: boolean) => ({
  question_id: "q3", turn: 3, fact_turn: 1, question: "What is the project codename again?", expected_keywords: ["bluejay"], answer: "(context echo)", correct,
});
const convResults = {
  mode: "dry-run (mock models; accuracy = fact retention in context)", budget_tokens: 4000, main_model: "claude-opus-5-5",
  manager_model: "claude-haiku-5-5", judge: "keyword", turns: 3, recall_questions: 1,
  summary: [convSummary("full", 0, 3), convSummary("truncation", 0), convSummary("acwm", 1)],
  per_turn: { full: [convTurn(1, 1000), convTurn(2, 3900)], truncation: [convTurn(1, 1000), convTurn(2, 3900), convTurn(3, 3990)], acwm: [convTurn(1, 1000), convTurn(2, 1900, "llm"), convTurn(3, 2100)] },
  answers: { full: [], truncation: [convAnswer(false)], acwm: [convAnswer(true)] },
  budget_events: {
    full: [{ turn: 3, status: "over_budget", message: "Budget exceeded: the context is 4,100 tokens but the budget is 4,000." }],
    truncation: [],
    acwm: [{ turn: 2, status: "over_target", message: "Compaction could not reach the 50% target (2,000 tokens)." }],
  },
};
const convStatus = {
  manager: { backend: "anthropic", model: "claude-haiku-5-5", real_model: false, status: "heuristic mode (add ANTHROPIC_API_KEY to use claude-haiku-5-5)" },
  main_model: { backend: "anthropic", model: "claude-opus-5-5", real_model: false, status: "not available (add ANTHROPIC_API_KEY to use claude-opus-5-5)" },
  live_runs_enabled: false, live_available: false, default_budget_tokens: 4000,
  context: { compact_threshold: 0.75, compact_target: 0.5, keep_recent_turns: 4, cooldown_turns: 3 },
};

interface FakeAccount { id: number; email: string; password: string; name: string }

/** A small fake ACWM server: accounts, bearer tokens and per-user saved packages. */
function mockApi(opts: { github?: boolean; seed?: FakeAccount[] } = {}) {
  const calls: string[] = [];
  const accounts: FakeAccount[] = [...(opts.seed ?? [])];
  const saved = new Map<number, { id: number; title: string }[]>();
  let nextPkg = 1;
  const userOut = (a: FakeAccount) => ({ id: a.id, display_name: a.name, email: a.email, github_login: null, created_at: "2026-10-21T00:00:00Z" });
  const tokenFor = (a: FakeAccount) => `token-${a.id}`;

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    calls.push(`${method} ${path}`);
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
    const err = (status: number, code: string, message: string) => json({ error: { code, message } }, status);
    const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
    const me = accounts.find((a) => auth === `Bearer ${tokenFor(a)}`);
    const body = init?.body ? JSON.parse(String(init.body)) : {};

    if (path === "/health") return json({ status: "ok", version: "0.1.0", providers: { conversation_manager: convStatus.manager.status } });
    if (path === "/conversation/status") return json(convStatus);
    if (path === "/config") return json({ sample_repository_path: "/srv/examples/sample_fastapi_repo", example_repositories: [], budget: { total_tokens: 8000, reserved_system_tokens: 400, reserved_response_tokens: 1500, safety_margin_ratio: 0.05, per_item_overhead_tokens: 24 }, weights: { lexical: 0.35, filename: 0.1, symbol: 0.15, dependency: 0.2, test: 0.1, config: 0.05, semantic: 0 }, expansion_depth: 2, modes: {}, tokenizer_encoding: "cl100k_base", providers: {} });
    if (path === "/benchmarks") return json({ repository: "examples/sample_fastapi_repo", tasks: [{ id: "jwt-auth", task: "Add JWT authentication", relevant: [], rationale: "" }], labeling_notes: "" });
    if (path === "/auth/providers") return json({ email_password: true, github: !!opts.github, require_auth: true, database: "postgresql" });
    if (path === "/auth/signup") {
      if (accounts.some((a) => a.email === body.email)) return err(409, "account_exists", "An account with this email already exists. Please log in.");
      const a = { id: accounts.length + 1, email: body.email, password: body.password, name: body.display_name || body.email.split("@")[0] };
      accounts.push(a);
      return json({ token: tokenFor(a), token_type: "bearer", expires_in_minutes: 10080, user: userOut(a) }, 201);
    }
    if (path === "/auth/login") {
      const a = accounts.find((x) => x.email === body.email && x.password === body.password);
      if (!a) return err(401, "not_authenticated", "Incorrect email or password.");
      return json({ token: tokenFor(a), token_type: "bearer", expires_in_minutes: 10080, user: userOut(a) });
    }
    if (!me) return err(401, "not_authenticated", "Please log in to use ACWM.");
    if (path === "/auth/me") return json(userOut(me));
    if (path.startsWith("/runs")) return json([]);
    if (path === "/repositories/index") return json({ repository: summary, report });
    if (path.startsWith("/repositories/abc123")) return json({ repository: summary, report, files: [], symbols: {}, graph: { nodes: [], edges: [] } });
    if (path === "/context/build" && body.token_budget < 2000) {
      return json({ error: { code: "budget_exceeded", message: "Token budget is too small after reserving system, task, response and safety margin tokens. Try at least 2,500 tokens.", details: {
        reason: "reservations", total_budget: body.token_budget, needed_tokens: 256, available_tokens: 0, shortfall_tokens: 256,
        reservations: { system: 400, task: 31, response: 1500, safety_margin: 50 }, suggested_budget: 2500,
      } } }, 422);
    }
    if (path === "/context/build") return json(pkg);
    if (path === "/conversation/benchmark") return json(convResults);
    const mine = saved.get(me.id) ?? [];
    const summaryOf = (p: { id: number; title: string }) => ({ id: p.id, title: p.title, task: pkg.task, repository_name: "sample_fastapi_repo", item_count: 2, rendered_tokens: 1850, created_at: "2026-10-21T00:00:00Z" });
    if (path === "/packages" && method === "GET") return json(mine.map(summaryOf));
    if (path === "/packages" && method === "POST") {
      const row = { id: nextPkg++, title: body.title || body.package.task };
      saved.set(me.id, [row, ...mine]);
      return json(summaryOf(row), 201);
    }
    const m = path.match(/^\/packages\/(\d+)$/);
    if (m) {
      const row = mine.find((p) => p.id === Number(m[1]));
      if (!row) return err(404, "not_found", "Saved package not found.");
      if (method === "DELETE") {
        saved.set(me.id, mine.filter((p) => p !== row));
        return new Response(null, { status: 204 });
      }
      return json({ ...summaryOf(row), package: pkg });
    }
    return err(404, "not_found", "nope");
  });
  return calls;
}

async function signUp(user: ReturnType<typeof userEvent.setup>, email: string, name = "Anand") {
  await screen.findByRole("heading", { name: /Welcome back|Create your account/ });
  await user.click(screen.getByRole("tab", { name: "Sign up" }));
  await user.type(screen.getByLabelText("Name (optional)"), name);
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), "correct-horse");
  await user.click(screen.getByRole("button", { name: "Create account" }));
  await screen.findByRole("button", { name: "Log out" });
}

const nav = () => within(screen.getByRole("navigation", { name: "Main" }));

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.replaceState(null, "", "/");
  });
  afterEach(() => vi.restoreAllMocks());

  it("requires login before the workspace is shown", async () => {
    mockApi();
    render(<StoreProvider><App /></StoreProvider>);
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run the demo" })).not.toBeInTheDocument();
    // GitHub button is disabled with an explanation when the server has no GitHub app.
    expect(screen.getByRole("button", { name: /Continue with GitHub/ })).toBeDisabled();
    expect(screen.getByText(/GitHub login is not configured/)).toBeInTheDocument();
  });

  it("signs up, runs the demo and shows explained results", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    render(<StoreProvider><App /></StoreProvider>);
    await signUp(user, "anand@example.com");
    expect(screen.getByText("Anand")).toBeInTheDocument();
    expect(localStorage.getItem("acwm-auth-token")).toBe("token-1");

    await user.click(screen.getByRole("button", { name: "Run the demo" }));
    expect(await screen.findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(calls).toContain("POST /repositories/index");
    expect(calls).toContain("POST /context/build");
    expect(screen.getByText("shopapi/api/dependencies.py")).toBeInTheDocument();
    expect(screen.getAllByText("1,850").length).toBeGreaterThanOrEqual(2);

    await user.click(screen.getByRole("button", { name: /shopapi\/api\/dependencies\.py/ }));
    expect(screen.getByText("Score components")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Omissions & warnings/ }));
    expect(screen.getByText("Token counts are estimates.")).toBeInTheDocument();
  });

  it("shows a clear error for a wrong password", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<StoreProvider><App /></StoreProvider>);
    await screen.findByRole("heading", { name: "Welcome back" });
    await user.type(screen.getByLabelText("Email"), "nobody@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(localStorage.getItem("acwm-auth-token")).toBeNull();
  });

  it("saves packages per user, and another user cannot see them", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<StoreProvider><App /></StoreProvider>);
    await signUp(user, "a@example.com", "Alice");
    await user.click(screen.getByRole("button", { name: "Run the demo" }));
    await screen.findByRole("heading", { name: "Results" });
    await user.click(screen.getByRole("button", { name: /Save to my account/ }));
    await user.type(screen.getByLabelText("Package name"), "Alice JWT context");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Alice JWT context");

    await user.click(nav().getByRole("button", { name: "Saved packages" }));
    expect(await screen.findByText("Alice JWT context")).toBeInTheDocument();

    // Log out: the previous user's workspace is cleared, then a second user signs up.
    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(localStorage.getItem("acwm-auth-token")).toBeNull();
    await signUp(user, "b@example.com", "Bob");
    await user.click(nav().getByRole("button", { name: "Saved packages" }));
    expect(await screen.findByText("No saved packages yet")).toBeInTheDocument();
    expect(screen.queryByText("Alice JWT context")).not.toBeInTheDocument();
    await user.click(nav().getByRole("button", { name: "Results" }));
    expect(screen.getByText("No context package yet")).toBeInTheDocument();
  });

  it("finishes a GitHub login from the redirect fragment and cleans the URL", async () => {
    mockApi({ github: true, seed: [{ id: 1, email: "gh@example.com", password: "x", name: "Octo" }] });
    window.history.replaceState(null, "", "/#auth_token=token-1");
    render(<StoreProvider><App /></StoreProvider>);
    expect(await screen.findByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(screen.getByText("Octo")).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(localStorage.getItem("acwm-auth-token")).toBe("token-1");
  });

  it("runs the conversation benchmark and shows strategies, compactions and recall", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    render(<StoreProvider><App /></StoreProvider>);
    await signUp(user, "conv@example.com");
    await user.click(nav().getByRole("button", { name: "Conversation" }));
    expect(await screen.findByRole("heading", { name: "Conversation manager" })).toBeInTheDocument();
    expect(await screen.findByText(/heuristic mode \(add ANTHROPIC_API_KEY/)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Live \(disabled on this server\)/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Run benchmark" }));
    expect(await screen.findByText("ACWM compaction events")).toBeInTheDocument();
    expect(calls).toContain("POST /conversation/benchmark");
    expect(screen.getByText("What is the project codename again?")).toBeInTheDocument();
    expect(screen.getByText(/overflow at 3/)).toBeInTheDocument();
    expect(screen.getByText("manager LLM")).toBeInTheDocument();
    expect(screen.getByLabelText("correct")).toBeInTheDocument();
    // Budget reporting: summary column and the budget events list.
    expect(screen.getByText("1 turn")).toBeInTheDocument();
    expect(screen.getByText(/Budget exceeded: the context is 4,100 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/could not reach the 50% target/)).toBeInTheDocument();
  });

  it("explains a budget-exceeded build and rebuilds with the suggested budget", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    render(<StoreProvider><App /></StoreProvider>);
    await signUp(user, "budget@example.com");
    await user.click(nav().getByRole("button", { name: "Build context" }));
    const budget = await screen.findByLabelText("Total token budget");
    await user.clear(budget);
    await user.type(budget, "1000");
    await user.click(within(screen.getByRole("main")).getByRole("button", { name: "Build context" }));

    const panel = await screen.findByRole("alert", { name: "Budget exceeded" });
    expect(within(panel).getByText(/Try at least 2,500 tokens/)).toBeInTheDocument();
    expect(within(panel).getByText("Short by")).toBeInTheDocument();
    expect(within(panel).getByText("1,500")).toBeInTheDocument(); // reserved response

    await user.click(within(panel).getByRole("button", { name: /Use 2,500 tokens and rebuild/ }));
    expect(await screen.findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(calls.filter((c) => c === "POST /context/build")).toHaveLength(2);
  });

  it("shows the GitHub error message from the redirect fragment", async () => {
    mockApi({ github: true });
    window.history.replaceState(null, "", "/#auth_error=GitHub%20login%20was%20cancelled.");
    render(<StoreProvider><App /></StoreProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("GitHub login was cancelled.");
    expect(window.location.hash).toBe("");
  });
});
