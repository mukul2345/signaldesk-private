type Session = { access_token: string; refresh_token: string; expires_at?: number; expires_in?: number };
type AuthError = { error_description?: string; msg?: string; error?: string };

const url = import.meta.env.VITE_SUPABASE_URL ?? "";
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
const storageKey = "signaldesk.supabase.session";

export const cloudMode = import.meta.env.VITE_CLOUD_MODE === "true";

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

export async function restoreSession(): Promise<Session | null> {
  const configuration = configurationError();
  if (configuration) throw configuration;
  const session = currentSession();
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

export function signOut(): void { localStorage.removeItem(storageKey); location.reload(); }
