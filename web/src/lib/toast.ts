/** A tiny toast store: any code can call toast.success(...) / toast.error(...); <Toaster/> renders them. */

export type Toast = { id: number; kind: "info" | "success" | "error"; message: string };

type Listener = (toasts: Toast[]) => void;

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<Listener>();

function emit() {
  for (const l of listeners) l(toasts);
}

function push(kind: Toast["kind"], message: string, ms = 6000) {
  const id = nextId++;
  toasts = [...toasts, { id, kind, message }];
  emit();
  window.setTimeout(() => dismiss(id), ms);
  return id;
}

export function dismiss(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  listener(toasts);
  return () => listeners.delete(listener);
}

export const toast = {
  info: (m: string) => push("info", m),
  success: (m: string) => push("success", m),
  error: (m: string) => push("error", m, 10000),
};
