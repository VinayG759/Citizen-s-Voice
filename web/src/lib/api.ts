/** Every request to our own server goes through here, so errors are handled one way. */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function getJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError(0, "network");
  }
  if (!response.ok) throw new ApiError(response.status, `HTTP ${response.status}`);
  return (await response.json()) as T;
}

/** POST form data (text fields and files). */
export async function postForm<T>(path: string, form?: FormData): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { method: "POST", body: form, headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError(0, "network");
  }
  if (!response.ok) throw new ApiError(response.status, `HTTP ${response.status}`);
  return (await response.json()) as T;
}

/** Turn any error into a sentence a person can act on. Never shows raw server text (UI rule 5). */
export function userMessage(err: unknown, fallback = "Something went wrong. Try again."): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return "Can't reach the server. Check your internet connection and try again.";
    if (err.status === 429) return "Too many messages in a short time. Wait a few minutes and try again.";
    if (err.status === 413) return "That recording was too long. Keep each message under 30 seconds.";
    if (err.status === 422) return "We didn't catch anything. Speak a little louder or closer, or type instead.";
    if (err.status === 502) return "We couldn't make out the recording. Please try again, or type instead.";
    if (err.status >= 500) return "The server had a problem. Try again in a moment.";
    if (err.status === 404) return "That wasn't found. It may have been removed.";
  }
  return fallback;
}
