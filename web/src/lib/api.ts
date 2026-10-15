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

/** Turn any error into a sentence a person can act on. Never shows raw server text (UI rule 5). */
export function userMessage(err: unknown, fallback = "Something went wrong. Try again."): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return "Can't reach the server. Check your internet connection and try again.";
    if (err.status >= 500) return "The server had a problem. Try again in a moment.";
    if (err.status === 404) return "That wasn't found. It may have been removed.";
  }
  return fallback;
}
