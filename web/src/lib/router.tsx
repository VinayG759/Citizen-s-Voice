/** A tiny router: the address bar and the page stay in step without reloading anything.
 *
 * Links call navigate(), which uses history.pushState and tells every hook below. The back and
 * forward buttons arrive as "popstate". Because the page never reloads, the live-updates connection
 * and the live call on screen survive a switch of page. Only what these pages need: no nesting,
 * no loaders.
 */

import { useCallback, useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from "react";

const CHANGED = "cv-navigate";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

// A string, so React compares by value and re-renders only when the address really changed.
const snapshot = () => window.location.pathname + window.location.search;

export function useLocation(): { pathname: string; search: string } {
  const [path, query = ""] = useSyncExternalStore(subscribe, snapshot).split("?");
  return { pathname: path.replace(/\/+$/, "") || "/", search: query };
}

export function navigate(to: string, opts: { replace?: boolean } = {}): void {
  if (to === snapshot()) return;
  window.history[opts.replace ? "replaceState" : "pushState"](null, "", to);
  window.dispatchEvent(new Event(CHANGED));
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { to: string };

/** An ordinary link that, on a plain click, changes page without a reload. Ctrl/Cmd-click still opens a tab. */
export function Link({ to, onClick, target, ...rest }: LinkProps) {
  function click(e: MouseEvent<HTMLAnchorElement>) {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || target) return;
    e.preventDefault();
    navigate(to);
  }
  return <a href={to} target={target} onClick={click} {...rest} />;
}

/** The address's ?query as filters: a link reproduces the view. Changes replace the history entry. */
export function useSearchParams(): [URLSearchParams, (changes: Record<string, string | null>) => void] {
  const { pathname, search } = useLocation();
  const params = new URLSearchParams(search);
  const set = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(window.location.search);
      for (const [key, value] of Object.entries(changes)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      const query = next.toString();
      navigate(pathname + (query ? `?${query}` : ""), { replace: true });
    },
    [pathname],
  );
  return [params, set];
}
