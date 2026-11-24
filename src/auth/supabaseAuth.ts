type Session = { access_token: string; refresh_token: string; expires_at?: number; expires_in?: number };
type AuthError = { error_description?: string; msg?: string; error?: string };

const url = import.meta.env.VITE_SUPABASE_URL ?? "";
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
const storageKey = "signaldesk.supabase.session";

export const cloudMode = import.meta.env.VITE_CLOUD_MODE === "true";
// Registration is available unless an operator explicitly disables it for maintenance.
export const signupEnabled = import.meta.env.VITE_ALLOW_SIGNUP !== "false";

function configurationError(): Error | null {
  if (!cloudMode) return null;
  if (!url || !key) return new Error("Cloud authentication is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in Vercel, then redeploy.");
  return null;
}

function saveSession(session: Session): Session {
  const expiresAt = session.expires_at ?? Math.floor(Date.now() / 1000) + (session.expires_in ?? 3600);
  const normalized = { ...session, expires_at: expiresAt };
  localStorage.setItem(storageKey, JSON.stringify(normalized));
  return normalized;
}

export function currentSession(): Session | null {
  try { return JSON.parse(localStorage.getItem(storageKey) ?? "null") as Session | null; }
  catch { return null; }
}

function tokenIsUsable(session: Session): boolean {
  return Boolean(session.expires_at && session.expires_at > Math.floor(Date.now() / 1000) + 30);
}

async function tokenRequest(grantType: "password" | "refresh_token", body: Record<string, string>): Promise<Session> {
  const response = await fetch(`${url}/auth/v1/token?grant_type=${grantType}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: key },
    body: JSON.stringify(body)
  });
  const payload = await response.json() as Session & AuthError;
  if (!response.ok) throw new Error(payload.error_description ?? payload.msg ?? payload.error ?? "Supabase sign-in failed");
  return saveSession(payload);
}

async function authRequest(path: string, init: RequestInit): Promise<void> {
  const response = await fetch(`${url}/auth/v1/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", apikey: key, ...init.headers }
  });
  const payload = await response.json().catch(() => ({})) as AuthError;
  if (!response.ok) throw new Error(payload.error_description ?? payload.msg ?? payload.error ?? "Authentication request failed");
}

export function isRecoveryLink(): boolean {
  return new URLSearchParams(window.location.hash.slice(1)).get("type") === "recovery";
}

function importSessionFromHash(): Session | null {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const access_token = params.get("access_token");
  const refresh_token = params.get("refresh_token");
  if (!access_token || !refresh_token) return null;
  const expires_at = Number(params.get("expires_at") ?? 0) || undefined;
  const session = saveSession({ access_token, refresh_token, expires_at });
  window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.search}`);
  return session;
}

export async function restoreSession(): Promise<Session | null> {
  const configuration = configurationError();
  if (configuration) throw configuration;
  const session = importSessionFromHash() ?? currentSession();
  if (!session) return null;
  if (tokenIsUsable(session)) return session;
  try {
    return await tokenRequest("refresh_token", { refresh_token: session.refresh_token });
  } catch {
    localStorage.removeItem(storageKey);
    return null;
  }
}

export async function accessToken(): Promise<string | null> { return (await restoreSession())?.access_token ?? null; }

export async function signIn(email: string, password: string): Promise<void> {
  const configuration = configurationError();
  if (configuration) throw configuration;
  await tokenRequest("password", { email, password });
}

export async function signUp(email: string, password: string): Promise<void> {
  const configuration = configurationError();
  if (configuration) throw configuration;
  if (!signupEnabled) throw new Error("New account registration is not enabled for this private deployment.");
  await authRequest("signup", {
    method: "POST",
    headers: { redirect_to: window.location.origin },
    body: JSON.stringify({ email, password })
  });
}

export async function requestPasswordReset(email: string): Promise<void> {
  const configuration = configurationError();
  if (configuration) throw configuration;
  // This endpoint deliberately returns the same success response for unknown emails.
  await authRequest("recover", {
    method: "POST",
    headers: { redirect_to: window.location.origin },
    body: JSON.stringify({ email })
  });
}

export async function updatePassword(password: string): Promise<void> {
  const token = await accessToken();
  if (!token) throw new Error("Your recovery session is invalid or expired. Request a new reset link.");
  await authRequest("user", {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ password })
  });
}

export function signOut(): void { localStorage.removeItem(storageKey); location.reload(); }
