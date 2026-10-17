/** Every request to our own server goes through here, so errors are handled one way. */

import { officerToken, setOfficerToken } from "./officer";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(init.headers as Record<string, string>) };
  const token = officerToken();
  if (token) headers.Authorization = `Bearer ${token}`; // signed-in officers see and do more
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "network");
  }
  if (response.status === 401 && token) setOfficerToken(null); // expired: back to the public view
  if (!response.ok) throw new ApiError(response.status, `HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function getBlob(path: string): Promise<Blob> {
  const token = officerToken();
  let response: Response;
  try {
    response = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch {
    throw new ApiError(0, "network");
  }
  if (response.status === 401 && token) setOfficerToken(null);
  if (!response.ok) throw new ApiError(response.status, `HTTP ${response.status}`);
  return response.blob();
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

/** POST form data (text fields and files). */
export function postForm<T>(path: string, form?: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body: form });
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
}

/** Turn any error into a sentence a person can act on. Never shows raw server text (UI rule 5). */
export function userMessage(err: unknown, fallback = "Something went wrong. Try again."): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return "Can't reach the server. Check your internet connection and try again.";
    if (err.status === 429) return "Too many messages in a short time. Wait a few minutes and try again.";
    if (err.status === 401) return "Officer sign-in needed, or it has expired. Sign in again.";
    if (err.status === 413) return "That was too large to send. Use a shorter recording or a smaller photo.";
    if (err.status === 422) return "We didn't catch anything. Speak a little louder or closer, or type instead.";
    if (err.status === 502) return "We couldn't make out the recording. Please try again, or type instead.";
    if (err.status >= 500) return "The server had a problem. Try again in a moment.";
    if (err.status === 404) return "That wasn't found. It may have been removed.";
  }
  return fallback;
}
