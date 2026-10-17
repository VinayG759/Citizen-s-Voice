import { useCallback, useRef, useState } from "react";
import { getJson, userMessage } from "./api";

export type Resource<T> = { state: "idle" } | { state: "loading" } | { state: "ok"; data: T } | { state: "error"; message: string };

/**
 * One thing fetched on request, never automatically: for screens whose answer costs something
 * (Gemma writes the headlines). `ensure()` loads it only if it was never loaded; `refresh()` loads
 * it again; `reset()` forgets it. Nothing here runs on a timer or on live events.
 */
export function useResource<T>(path: string) {
  const [resource, setResource] = useState<Resource<T>>({ state: "idle" });
  const started = useRef(false);

  const refresh = useCallback(async () => {
    started.current = true;
    setResource({ state: "loading" });
    try {
      setResource({ state: "ok", data: await getJson<T>(path) });
    } catch (err) {
      started.current = false; // a failed first try may be tried again when the page is reopened
      setResource({ state: "error", message: userMessage(err, "Couldn't load this. Try again.") });
    }
  }, [path]);

  const ensure = useCallback(() => {
    if (!started.current) void refresh();
  }, [refresh]);

  const reset = useCallback(() => {
    started.current = false;
    setResource({ state: "idle" });
  }, []);

  return { resource, ensure, refresh, reset };
}
