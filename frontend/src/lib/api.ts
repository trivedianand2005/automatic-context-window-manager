import type {
  BenchmarkReport,
  BenchmarkTask,
  BuildRequest,
  ComparisonResult,
  ConfigResponse,
  AuthProviders,
  AuthResponse,
  ContextPackage,
  ConversationResults,
  ConversationStatus,
  ExportFormat,
  Health,
  IndexResponse,
  RepositoryDetails,
  RunInfo,
  SavedPackageFull,
  SavedPackageSummary,
  User,
} from "./types";

export const API_URL: string = (
  (import.meta.env.VITE_API_URL as string | undefined) || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const SESSION_KEY = "acwm-session-id";
export const SESSION_HEADER = "X-ACWM-Session";

/** Stable per-browser id so the API keeps this visitor's indexes separate from others. */
export function getSessionId(storage: Storage | undefined = globalThis.localStorage): string {
  try {
    const existing = storage?.getItem(SESSION_KEY);
    if (existing && /^[A-Za-z0-9-]{8,64}$/.test(existing)) return existing;
  } catch {
    /* storage unavailable (private mode) - fall through to an in-memory id */
  }
  const id =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  try {
    storage?.setItem(SESSION_KEY, id);
  } catch {
    /* ignore */
  }
  return id;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Turn the backend's {"error": {...}} body (or anything else) into an ApiError. */
export async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* non-JSON error page */
  }
  const err = (body as { error?: { code?: string; message?: string; details?: unknown } })?.error;
  if (err?.message) {
    const detail =
      Array.isArray(err.details) && err.details.length
        ? `: ${(err.details as { loc?: unknown[]; msg?: string }[])
            .map((d) => `${(d.loc ?? []).slice(1).join(".")} ${d.msg ?? ""}`.trim())
            .join("; ")}`
        : "";
    return new ApiError(err.message + detail, response.status, err.code ?? "error", err.details);
  }
  return new ApiError(
    `Request failed with HTTP ${response.status}`,
    response.status,
    "http_error",
  );
}

// ------------------------------------------------------------------ login token
const TOKEN_KEY = "acwm-auth-token";

export function getToken(): string | null {
  try {
    return globalThis.localStorage?.getItem(TOKEN_KEY) ?? null;
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) globalThis.localStorage?.setItem(TOKEN_KEY, token);
    else globalThis.localStorage?.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

let unauthorizedHandler: (() => void) | null = null;

/** Called when the server rejects our login token (expired, revoked, server secret changed). */
export function onUnauthorized(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

/**
 * After GitHub login the API redirects to `/#auth_token=...` (or `#auth_error=...`).
 * Read it once, then remove it from the address bar so it is not bookmarked or shared.
 */
export function consumeAuthFragment(): { token?: string; error?: string } {
  const hash = globalThis.location?.hash ?? "";
  if (!hash.startsWith("#auth_")) return {};
  const params = new URLSearchParams(hash.slice(1));
  globalThis.history?.replaceState(null, "", globalThis.location.pathname + globalThis.location.search);
  const token = params.get("auth_token") ?? undefined;
  const error = params.get("auth_error") ?? undefined;
  return { token, error };
}

interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  timeoutMs?: number;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 120_000);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: opts.method ?? "GET",
      headers: {
        [SESSION_HEADER]: getSessionId(),
        ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    const aborted = (e as Error).name === "AbortError";
    throw new ApiError(
      aborted
        ? "The server took too long to respond. It may be waking up - please try again."
        : "Cannot reach the ACWM API. It may be starting up or offline.",
      0,
      aborted ? "timeout" : "network_error",
    );
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    const err = await toApiError(response);
    if (response.status === 401 && err.code === "not_authenticated" && getToken()) {
      setToken(null);
      unauthorizedHandler?.();
    }
    throw err;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * Poll /health until the API answers. Free hosting tiers sleep when idle and can take
 * up to about a minute to start, so the UI shows progress instead of failing.
 */
export async function waitForApi(
  onAttempt?: (attempt: number) => void,
  // ~4-5 minutes in total: a cold start on the free tier can take a couple of minutes.
  { attempts = 50, delayMs = 5000 }: { attempts?: number; delayMs?: number } = {},
): Promise<Health> {
  let lastError: unknown;
  for (let i = 1; i <= attempts; i++) {
    onAttempt?.(i);
    try {
      return await request<Health>("/health", { timeoutMs: 15_000 });
    } catch (e) {
      lastError = e;
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw lastError instanceof Error ? lastError : new Error("API unavailable");
}

export const api = {
  authProviders: () => request<AuthProviders>("/auth/providers"),
  signup: (email: string, password: string, display_name?: string) =>
    request<AuthResponse>("/auth/signup", { method: "POST", body: { email, password, display_name } }),
  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request<User>("/auth/me"),
  githubLoginUrl: () => `${API_URL}/auth/github/login`,
  listPackages: () => request<SavedPackageSummary[]>("/packages"),
  savePackage: (pkg: ContextPackage, title?: string) =>
    request<SavedPackageSummary>("/packages", { method: "POST", body: { title, package: pkg } }),
  getPackage: (id: number) => request<SavedPackageFull>(`/packages/${id}`),
  deletePackage: (id: number) => request<void>(`/packages/${id}`, { method: "DELETE" }),
  health: () => request<Health>("/health", { timeoutMs: 15_000 }),
  config: () => request<ConfigResponse>("/config"),
  runs: () => request<RunInfo[]>("/runs?limit=10"),
  index: (path: string) =>
    request<IndexResponse>("/repositories/index", { method: "POST", body: { path } }),
  repository: (id: string) =>
    request<RepositoryDetails>(
      `/repositories/${encodeURIComponent(id)}?include_files=true&include_symbols=true&include_graph=true`,
    ),
  build: (body: BuildRequest) =>
    request<ContextPackage>("/context/build", { method: "POST", body }),
  compare: (body: BuildRequest & { relevant_paths: string[]; k?: number }) =>
    request<ComparisonResult>("/context/compare", { method: "POST", body }),
  exportPackage: (format: ExportFormat, pkg: ContextPackage) =>
    request<{ format: string; filename: string; mime_type: string; content: string }>(
      "/context/export",
      { method: "POST", body: { format, package: pkg } },
    ),
  benchmarks: () =>
    request<{ repository: string; tasks: BenchmarkTask[]; labeling_notes: string }>("/benchmarks"),
  runBenchmarks: (token_budget: number) =>
    request<BenchmarkReport>("/benchmarks/run", {
      method: "POST",
      body: { token_budget },
      timeoutMs: 180_000,
    }),
  conversationStatus: () => request<ConversationStatus>("/conversation/status"),
  runConversationBenchmark: (mode: "dry-run" | "live", budget_tokens: number) =>
    request<ConversationResults>("/conversation/benchmark", {
      method: "POST",
      body: { mode, budget_tokens },
      // Live runs make real model calls and can take a few minutes.
      timeoutMs: mode === "live" ? 660_000 : 120_000,
    }),
};
