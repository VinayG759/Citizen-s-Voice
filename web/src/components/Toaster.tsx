import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { dismiss, subscribe, type Toast } from "../lib/toast";

/** Mounted once. Announces messages to screen readers; errors interrupt (role="alert"). */
export function Toaster() {
  const [items, setItems] = useState<Toast[]>([]);
  useEffect(() => subscribe(setItems), []);

  return (
    <div className="toaster" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast toast--${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          <span className="toast__message">{t.message}</span>
          <button type="button" className="toast__close" aria-label="Dismiss message" onClick={() => dismiss(t.id)}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  );
}
