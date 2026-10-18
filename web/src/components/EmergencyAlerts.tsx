import { useState } from "react";
import { BellRing, Siren, X } from "lucide-react";
import { emergencyKindLabel, type EmergencyKind } from "../lib/complaints";

export type EmergencyAlert = {
  tracking_id: string;
  emergency_kind: EmergencyKind;
  place: string;
  office: string;
  summary: string | null;
};

/** Browser notifications are optional: an officer who says no still sees the red alert on the page. */
export function notificationsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function notifyBrowser(a: EmergencyAlert): void {
  if (!notificationsSupported() || Notification.permission !== "granted") return;
  try {
    const n = new Notification(`Emergency: ${emergencyKindLabel(a.emergency_kind)}`, {
      body: `${a.summary ?? "New emergency"} · ${a.place} · ${a.tracking_id}`,
      tag: a.tracking_id,
    });
    n.onclick = () => {
      window.focus();
      window.location.assign(`/c/${a.tracking_id}`);
    };
  } catch {
    // some browsers only allow notifications from a service worker: the page alert is enough
  }
}

/** Red alerts for new emergencies (live event "emergency"). Each stays until the officer opens or dismisses it. */
export function EmergencyAlerts({ alerts, onDismiss }: { alerts: EmergencyAlert[]; onDismiss: (id: string) => void }) {
  const [permission, setPermission] = useState(() => (notificationsSupported() ? Notification.permission : "denied"));

  async function enable() {
    try {
      setPermission(await Notification.requestPermission());
    } catch {
      setPermission("denied");
    }
  }

  return (
    <div className="emergency-alerts">
      {alerts.map((a) => (
        <div key={a.tracking_id} className={`emergency-alert emergency-alert--${a.emergency_kind}`} role="alert">
          <Siren size={20} aria-hidden="true" />
          <div className="emergency-alert__body">
            <strong>Emergency · {emergencyKindLabel(a.emergency_kind)}</strong>
            <span>
              {a.summary ?? "New emergency"} at {a.place} · {a.office} · {a.tracking_id}
            </span>
          </div>
          <a className="emergency-alert__open" href={`/c/${a.tracking_id}`}>
            Open
          </a>
          <button type="button" className="emergency-alert__close" aria-label={`Dismiss alert for ${a.tracking_id}`}
            onClick={() => onDismiss(a.tracking_id)}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      ))}
      {permission === "default" && (
        <button type="button" className="emergency-alerts__enable" onClick={() => void enable()}>
          <BellRing size={16} aria-hidden="true" /> Enable emergency alerts
        </button>
      )}
    </div>
  );
}
