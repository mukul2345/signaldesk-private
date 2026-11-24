import { FormEvent, ReactNode, useState } from "react";
import { cloudMode, currentSession, signIn } from "../auth/supabaseAuth";

export function AuthGate({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(() => !cloudMode || Boolean(currentSession()));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (authenticated) return <>{children}</>;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try { await signIn(String(data.get("email")), String(data.get("password"))); setAuthenticated(true); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Sign in failed"); }
    finally { setBusy(false); }
  };
  return <main className="auth-shell"><form className="auth-card" onSubmit={submit}>
    <span className="eyebrow">PRIVATE PAPER-RESEARCH TERMINAL</span>
    <h1>Sign in to SignalDesk</h1>
    <p>Your Supabase session protects alerts, paper positions and portfolio records.</p>
    <label>Email<input name="email" type="email" autoComplete="username" required/></label>
    <label>Password<input name="password" type="password" autoComplete="current-password" required/></label>
    {error && <p className="auth-error" role="alert">{error}</p>}
    <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    <small>Paper research only. Returns are never guaranteed.</small>
  </form></main>;
}
