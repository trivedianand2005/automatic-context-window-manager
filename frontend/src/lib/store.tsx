import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError, consumeAuthFragment, getToken, onUnauthorized, setToken, waitForApi } from "./api";
import type {
  AuthProviders,
  BenchmarkReport,
  BenchmarkTask,
  BuildRequest,
  ComparisonResult,
  ConfigResponse,
  ContextPackage,
  Health,
  IndexResponse,
  RepositoryDetails,
  SavedPackageSummary,
  User,
} from "./types";

export type Page =
  | "overview" | "repository" | "build" | "results" | "compare" | "benchmarks" | "export" | "saved";
export type ApiStatus = "connecting" | "online" | "offline";

export const EXAMPLE_TASK =
  "Add JWT authentication to the FastAPI application and create tests for protected routes.";

interface Store {
  page: Page;
  setPage: (p: Page) => void;
  apiStatus: ApiStatus;
  wakeAttempt: number;
  health: Health | null;
  config: ConfigResponse | null;
  benchmarkTasks: BenchmarkTask[];
  connect: () => Promise<void>;

  indexPath: string;
  setIndexPath: (p: string) => void;
  repo: IndexResponse | null;
  details: RepositoryDetails | null;
  indexRepo: (path?: string) => Promise<IndexResponse | null>;

  task: string;
  setTask: (t: string) => void;
  pkg: ContextPackage | null;
  buildContext: (req: Omit<BuildRequest, "repository_id">) => Promise<ContextPackage | null>;
  comparison: ComparisonResult | null;
  runComparison: (task: string, budget: number, labels: string[]) => Promise<void>;
  excludedFindings: Set<number>;
  toggleFinding: (index: number) => void;
  benchmark: BenchmarkReport | null;
  runBenchmarks: (budget: number) => Promise<void>;

  user: User | null;
  authProviders: AuthProviders | null;
  authChecked: boolean;
  login: (email: string, password: string) => Promise<boolean>;
  signup: (email: string, password: string, displayName?: string) => Promise<boolean>;
  logout: (message?: string) => void;
  startGithubLogin: () => void;

  saved: SavedPackageSummary[];
  refreshSaved: () => Promise<void>;
  saveCurrentPackage: (title?: string) => Promise<boolean>;
  openSaved: (id: number) => Promise<void>;
  deleteSaved: (id: number) => Promise<void>;

  busy: string | null;
  error: string | null;
  clearError: () => void;
  notice: string | null;
  clearNotice: () => void;
}

const StoreContext = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>("overview");
  const [apiStatus, setApiStatus] = useState<ApiStatus>("connecting");
  const [wakeAttempt, setWakeAttempt] = useState(0);
  const [health, setHealth] = useState<Health | null>(null);
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [benchmarkTasks, setBenchmarkTasks] = useState<BenchmarkTask[]>([]);
  const [indexPath, setIndexPath] = useState("");
  const [repo, setRepo] = useState<IndexResponse | null>(null);
  const [details, setDetails] = useState<RepositoryDetails | null>(null);
  const [task, setTask] = useState(EXAMPLE_TASK);
  const [pkg, setPkg] = useState<ContextPackage | null>(null);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkReport | null>(null);
  const [excludedFindings, setExcludedFindings] = useState<Set<number>>(new Set());
  const toggleFinding = useCallback((i: number) => {
    setExcludedFindings((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }, []);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authProviders, setAuthProviders] = useState<AuthProviders | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [saved, setSaved] = useState<SavedPackageSummary[]>([]);
  const repoRef = useRef<IndexResponse | null>(null);
  const pathRef = useRef("");
  repoRef.current = repo;
  pathRef.current = indexPath;

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));

  const connect = useCallback(async () => {
    setApiStatus("connecting");
    setError(null);
    try {
      const h = await waitForApi(setWakeAttempt);
      setHealth(h);
      const [cfg, bench, providers] = await Promise.all([
        api.config(), api.benchmarks(), api.authProviders(),
      ]);
      setConfig(cfg);
      setBenchmarkTasks(bench.tasks);
      setAuthProviders(providers);
      setIndexPath((p) => p || cfg.sample_repository_path);
      setApiStatus("online");
      // Restore the session (or finish a GitHub login that redirected back with #auth_token).
      const fragment = consumeAuthFragment();
      if (fragment.token) setToken(fragment.token);
      if (fragment.error) setError(fragment.error);
      if (getToken()) {
        try {
          setUser(await api.me());
        } catch {
          setToken(null);
        }
      }
      setAuthChecked(true);
    } catch (e) {
      setApiStatus("offline");
      fail(e);
    }
  }, []);

  useEffect(() => {
    void connect();
  }, [connect]);

  /** Forget everything that belonged to the previous user. */
  const resetWorkspace = useCallback(() => {
    setRepo(null);
    repoRef.current = null;
    setDetails(null);
    setPkg(null);
    setComparison(null);
    setBenchmark(null);
    setSaved([]);
    setExcludedFindings(new Set());
    setTask(EXAMPLE_TASK);
    setPage("overview");
  }, []);

  const logout = useCallback(
    (message?: string) => {
      setToken(null);
      setUser(null);
      resetWorkspace();
      setNotice(null);
      if (message) setError(message);
    },
    [resetWorkspace],
  );

  useEffect(() => {
    onUnauthorized(() => logout("Your session has ended. Please log in again."));
    return () => onUnauthorized(null);
  }, [logout]);

  const finishAuth = useCallback(
    (token: string, u: User) => {
      resetWorkspace();
      setToken(token);
      setUser(u);
      setError(null);
    },
    [resetWorkspace],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      setBusy("Logging in...");
      setError(null);
      try {
        const res = await api.login(email, password);
        finishAuth(res.token, res.user);
        return true;
      } catch (e) {
        fail(e);
        return false;
      } finally {
        setBusy(null);
      }
    },
    [finishAuth],
  );

  const signup = useCallback(
    async (email: string, password: string, displayName?: string) => {
      setBusy("Creating your account...");
      setError(null);
      try {
        const res = await api.signup(email, password, displayName);
        finishAuth(res.token, res.user);
        return true;
      } catch (e) {
        fail(e);
        return false;
      } finally {
        setBusy(null);
      }
    },
    [finishAuth],
  );

  const startGithubLogin = useCallback(() => {
    globalThis.location.assign(api.githubLoginUrl());
  }, []);

  const refreshSaved = useCallback(async () => {
    try {
      setSaved(await api.listPackages());
    } catch (e) {
      fail(e);
    }
  }, []);

  const saveCurrentPackage = useCallback(
    async (title?: string) => {
      if (!pkg) return false;
      setBusy("Saving package...");
      setError(null);
      try {
        const kept = {
          ...pkg,
          research_findings: pkg.research_findings.filter((_, i) => !excludedFindings.has(i)),
        };
        const row = await api.savePackage(kept, title);
        setSaved((prev) => [row, ...prev]);
        setNotice(`Saved "${row.title}" to your account.`);
        return true;
      } catch (e) {
        fail(e);
        return false;
      } finally {
        setBusy(null);
      }
    },
    [pkg, excludedFindings],
  );

  const openSaved = useCallback(async (id: number) => {
    setBusy("Opening saved package...");
    setError(null);
    try {
      const row = await api.getPackage(id);
      setPkg(row.package);
      setTask(row.package.task);
      setExcludedFindings(new Set());
      setPage("results");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  }, []);

  const deleteSaved = useCallback(async (id: number) => {
    setError(null);
    try {
      await api.deletePackage(id);
      setSaved((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      fail(e);
    }
  }, []);

  const doIndex = useCallback(async (path: string) => {
    const res = await api.index(path);
    setRepo(res);
    repoRef.current = res;
    setDetails(await api.repository(res.repository.repository_id));
    return res;
  }, []);

  const indexRepo = useCallback(
    async (path?: string) => {
      const target = (path ?? pathRef.current).trim();
      if (!target) {
        setError("Enter a repository path to index.");
        return null;
      }
      setBusy("Indexing repository...");
      setError(null);
      try {
        return await doIndex(target);
      } catch (e) {
        fail(e);
        return null;
      } finally {
        setBusy(null);
      }
    },
    [doIndex],
  );

  /**
   * Run an operation that needs an indexed repository. Indexes the sample if nothing is
   * indexed yet, and re-indexes once if the server restarted and forgot the index.
   */
  const withRepo = useCallback(
    async <T,>(fn: (repositoryId: string) => Promise<T>): Promise<T> => {
      let current = repoRef.current;
      if (!current) current = await doIndex(pathRef.current || config?.sample_repository_path || "");
      try {
        return await fn(current.repository.repository_id);
      } catch (e) {
        if (e instanceof ApiError && e.code === "repository_not_found") {
          const fresh = await doIndex(pathRef.current || config?.sample_repository_path || "");
          return fn(fresh.repository.repository_id);
        }
        throw e;
      }
    },
    [config, doIndex],
  );

  const buildContext = useCallback(
    async (req: Omit<BuildRequest, "repository_id">) => {
      setBusy("Selecting context...");
      setError(null);
      try {
        const result = await withRepo((id) => api.build({ ...req, repository_id: id }));
        setPkg(result);
        setExcludedFindings(new Set());
        setPage("results");
        // Provider status (e.g. TinyFish's last call) can change after a build.
        api.health().then(setHealth).catch(() => undefined);
        return result;
      } catch (e) {
        fail(e);
        return null;
      } finally {
        setBusy(null);
      }
    },
    [withRepo],
  );

  const runComparison = useCallback(
    async (t: string, budget: number, labels: string[]) => {
      setBusy("Running baseline, dependency and ACWM...");
      setError(null);
      try {
        setComparison(
          await withRepo((id) =>
            api.compare({ repository_id: id, task: t, token_budget: budget, relevant_paths: labels }),
          ),
        );
      } catch (e) {
        fail(e);
      } finally {
        setBusy(null);
      }
    },
    [withRepo],
  );

  const runBenchmarks = useCallback(async (budget: number) => {
    setBusy("Running all benchmark tasks...");
    setError(null);
    try {
      setBenchmark(await api.runBenchmarks(budget));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  }, []);

  const value = useMemo<Store>(
    () => ({
      page, setPage, apiStatus, wakeAttempt, health, config, benchmarkTasks, connect,
      indexPath, setIndexPath, repo, details, indexRepo,
      task, setTask, pkg, buildContext, comparison, runComparison, benchmark, runBenchmarks,
      excludedFindings, toggleFinding,
      user, authProviders, authChecked, login, signup, logout, startGithubLogin,
      saved, refreshSaved, saveCurrentPackage, openSaved, deleteSaved,
      busy, error, clearError: () => setError(null), notice, clearNotice: () => setNotice(null),
    }),
    [page, apiStatus, wakeAttempt, health, config, benchmarkTasks, connect, indexPath, repo,
     details, indexRepo, task, pkg, buildContext, comparison, runComparison, benchmark,
     runBenchmarks, excludedFindings, toggleFinding, user, authProviders, authChecked, login,
     signup, logout, startGithubLogin, saved, refreshSaved, saveCurrentPackage, openSaved,
     deleteSaved, busy, error, notice],
  );
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): Store {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used inside <StoreProvider>");
  return ctx;
}
