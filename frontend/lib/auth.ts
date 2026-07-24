// Client-side admin session. Real enforcement is server-side (upload-api uses
// HTTP Basic on the write endpoints); this just stores the credentials the
// browser sends with upload / create-movie requests.
const KEY = "streamsre-admin";

export function setAdminToken(username: string, password: string): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(KEY, btoa(`${username}:${password}`));
}

export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(KEY);
}

export function clearAdminToken(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(KEY);
}

export function isAuthed(): boolean {
  return getAdminToken() !== null;
}

export function authHeader(): Record<string, string> {
  const token = getAdminToken();
  return token ? { Authorization: `Basic ${token}` } : {};
}
