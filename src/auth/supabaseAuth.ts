type Session = { access_token: string; refresh_token: string; expires_at?: number };

const url = import.meta.env.VITE_SUPABASE_URL ?? "";
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
const storageKey = "signaldesk.supabase.session";

export const cloudMode = import.meta.env.VITE_CLOUD_MODE === "true";

export function currentSession(): Session | null {
  try { return JSON.parse(localStorage.getItem(storageKey) ?? "null") as Session | null; }
  catch { return null; }
}

export function accessToken(): string | null { return currentSession()?.access_token ?? null; }

export async function signIn(email: string, password: string): Promise<void> {
  if (!url || !key) throw new Error("Supabase browser configuration is missing");
  const response = await fetch(`${url}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: key },
    body: JSON.stringify({ email, password })
  });
  const body = await response.json() as Session & { error_description?: string; msg?: string };
  if (!response.ok) throw new Error(body.error_description ?? body.msg ?? "Sign in failed");
  localStorage.setItem(storageKey, JSON.stringify(body));
}

export function signOut(): void { localStorage.removeItem(storageKey); location.reload(); }
