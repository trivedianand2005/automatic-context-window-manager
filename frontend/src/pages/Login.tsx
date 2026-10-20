import { Github, Layers, LogIn, UserPlus } from "lucide-react";
import { useState } from "react";
import { Spinner, Tabs } from "../components/ui";
import { useStore } from "../lib/store";

type Mode = "login" | "signup";

/** Shown until the visitor logs in. Every account gets its own private workspace. */
export function LoginPage() {
  const { login, signup, startGithubLogin, authProviders, busy, error, clearError, apiStatus } = useStore();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "login") await login(email, password);
    else await signup(email, password, name || undefined);
  };
  const github = authProviders?.github ?? false;
  const disabled = !!busy || apiStatus !== "online";

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center">
      <div className="mb-6 text-center">
        <div className="mx-auto mb-3 inline-flex items-center gap-2 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs font-medium text-sky-300">
          <Layers className="size-3.5" /> Automatic Context Window Manager
        </div>
        <h1 className="text-2xl font-semibold text-zinc-50">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Each account has its own private workspace and saved context packages.
        </p>
      </div>

      <div className="card p-6">
        <Tabs<Mode>
          value={mode}
          onChange={(m) => { setMode(m); clearError(); }}
          items={[{ value: "login", label: "Log in" }, { value: "signup", label: "Sign up" }]}
        />
        {error && (
          <div role="alert" className="mb-4 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        )}
        <form onSubmit={submit} className="space-y-4">
          {mode === "signup" && (
            <div>
              <label className="label" htmlFor="name">Name (optional)</label>
              <input id="name" className="input" autoComplete="name" maxLength={100}
                value={name} onChange={(e) => setName(e.target.value)} />
            </div>
          )}
          <div>
            <label className="label" htmlFor="email">Email</label>
            <input id="email" type="email" className="input" autoComplete="email" required
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="password">Password</label>
            <input id="password" type="password" className="input" required minLength={mode === "signup" ? 8 : 1}
              maxLength={128} autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password} onChange={(e) => setPassword(e.target.value)} />
            {mode === "signup" && <p className="mt-1 text-xs text-zinc-500">At least 8 characters.</p>}
          </div>
          <button type="submit" className="btn-primary w-full" disabled={disabled}>
            {busy ? <Spinner label={busy} /> : mode === "login"
              ? <><LogIn className="size-4" /> Log in</>
              : <><UserPlus className="size-4" /> Create account</>}
          </button>
        </form>

        <div className="my-5 flex items-center gap-3 text-xs text-zinc-500">
          <div className="h-px flex-1 bg-zinc-800" /> or <div className="h-px flex-1 bg-zinc-800" />
        </div>
        <button className="btn-ghost w-full" onClick={startGithubLogin} disabled={disabled || !github}
          title={github ? undefined : "GitHub login is not configured on this server yet"}>
          <Github className="size-4" /> Continue with GitHub
        </button>
        {!github && authProviders && (
          <p className="mt-2 text-center text-xs text-zinc-500">GitHub login is not configured on this server yet.</p>
        )}
      </div>
      <p className="mt-4 text-center text-xs text-zinc-600">
        Passwords are stored only as salted scrypt hashes. Sessions last 7 days.
      </p>
    </div>
  );
}
