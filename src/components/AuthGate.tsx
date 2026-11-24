import { FormEvent, ReactNode, useEffect, useState } from "react";
import { cloudMode, isRecoveryLink, requestPasswordReset, restoreSession, signIn, signUp, signupEnabled, updatePassword } from "../auth/supabaseAuth";

export function AuthGate({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(() => !cloudMode);
  const [checking, setChecking] = useState(cloudMode);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"sign-in" | "sign-up" | "forgot" | "reset">(() => isRecoveryLink() ? "reset" : "sign-in");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!cloudMode) return;
    void restoreSession()
      .then(session => setAuthenticated(Boolean(session)))
      .catch(reason => setError(reason instanceof Error ? reason.message : "Cloud authentication is unavailable"))
      .finally(() => setChecking(false));
  }, []);
  if (authenticated) return <>{children}</>;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "");
    const password = String(data.get("password") ?? "");
    if ((mode === "sign-up" || mode === "reset") && password.length < 8) {
      setBusy(false); setError("Use at least 8 characters for your password."); return;
    }
    try {
      if (mode === "sign-in") { await signIn(email, password); setAuthenticated(true); }
      if (mode === "sign-up") { await signUp(email, password); setNotice("Check your email to confirm the account, then sign in."); setMode("sign-in"); }
      if (mode === "forgot") { await requestPasswordReset(email); setNotice("If the account exists, a password-reset email has been sent."); setMode("sign-in"); }
      if (mode === "reset") { await updatePassword(password); setNotice("Password updated. Sign in with your new password."); setMode("sign-in"); }
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Sign in failed"); }
    finally { setBusy(false); }
  };
  const title = mode === "sign-up" ? "Create account" : mode === "forgot" ? "Reset password" : mode === "reset" ? "Choose a new password" : "Sign in to SignalDesk";
  return <main className="auth-shell"><form className="auth-card" onSubmit={submit}>
    <span className="eyebrow">PRIVATE PAPER-RESEARCH TERMINAL</span>
    <h1>{title}</h1>
    <p>{mode === "forgot" ? "We will email a secure reset link if this account exists." : "Your Supabase session protects alerts, paper positions and portfolio records."}</p>
    {mode !== "reset" && <label>Email<input name="email" type="email" autoComplete="username" required disabled={checking}/></label>}
    {mode !== "forgot" && <label>Password<input name="password" type="password" autoComplete={mode === "sign-up" || mode === "reset" ? "new-password" : "current-password"} required disabled={checking}/></label>}
    {error && <p className="auth-error" role="alert">{error}</p>}
    {notice && <p className="auth-notice" role="status">{notice}</p>}
    <button type="submit" disabled={busy || checking}>{checking ? "Checking session…" : busy ? "Please wait…" : mode === "sign-up" ? "Create account" : mode === "forgot" ? "Send reset link" : mode === "reset" ? "Update password" : "Sign in"}</button>
    {mode === "sign-in" && <div className="auth-links"><button type="button" onClick={() => { setMode("forgot"); setError(""); }}>Forgot password?</button>{signupEnabled && <button type="button" onClick={() => { setMode("sign-up"); setError(""); }}>Create account</button>}</div>}
    {(mode === "sign-up" || mode === "forgot") && <div className="auth-links"><button type="button" onClick={() => { setMode("sign-in"); setError(""); }}>Back to sign in</button></div>}
    <small>{signupEnabled ? "Email confirmation is required for new accounts." : "Private access only. Registration is currently invite-only."} Paper research only; returns are never guaranteed.</small>
  </form></main>;
}
