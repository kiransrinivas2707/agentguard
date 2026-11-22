import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { User } from "../types";

interface Props {
  onAuth: (user: User) => void;
}

export function AuthPage({ onAuth }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const user = mode === "login" ? await api.login(email, password) : await api.register(email, password);
      onAuth(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="brand brand-large">
          <span className="brand-mark" aria-hidden="true">
            ◈
          </span>
          <div>
            <h1 id="auth-title">AI File Organizer</h1>
            <p className="muted">Drop anything. Find it later.</p>
          </div>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="Account action">
          <button
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "tab active" : "tab"}
            onClick={() => setMode("login")}
            type="button"
          >
            Sign in
          </button>
          <button
            role="tab"
            aria-selected={mode === "register"}
            className={mode === "register" ? "tab active" : "tab"}
            onClick={() => setMode("register")}
            type="button"
          >
            Create account
          </button>
        </div>

        <form onSubmit={submit} className="stack">
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              minLength={mode === "register" ? 8 : 1}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
            />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="btn primary full" disabled={busy} type="submit">
            {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p className="muted small">
          Files stay in this app's local storage. AI classification uses your configured model, and
          you approve every move.
        </p>
      </section>
    </div>
  );
}
