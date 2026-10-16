import { useEffect, useRef, useState } from "react";

export type LiveEvent = { type: string; at: number; [key: string]: unknown };

/**
 * Listens to the server's live feed (/api/events). The browser reconnects by itself if the
 * connection drops; `connected` lets the page say so instead of silently showing stale data.
 */
export function useLiveEvents(onEvent: (e: LiveEvent) => void): boolean | null {
  // null: not connected yet (or the browser has no EventSource); false: connection lost.
  const [connected, setConnected] = useState<boolean | null>(null);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/events");
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (m) => {
      try {
        handler.current(JSON.parse(m.data) as LiveEvent);
      } catch {
        // ignore a malformed message rather than breaking the page
      }
    };
    return () => source.close();
  }, []);

  return connected;
}
