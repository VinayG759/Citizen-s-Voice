import { useCallback, useEffect, useState } from "react";
import { Mic, Phone, RefreshCw } from "lucide-react";
import { AppHeader } from "./components/AppHeader";
import { Badge } from "./components/Badge";
import { Button } from "./components/Button";
import { Card } from "./components/Card";
import { EmptyState } from "./components/EmptyState";
import { Toaster } from "./components/Toaster";
import { getJson, userMessage } from "./lib/api";
import { toast } from "./lib/toast";

type Health = { status: "ok" | "degraded"; db: "ok" | "down"; version: string };
type Config = { helpline_number: string; helpline_display: string };

type Status = { state: "loading" } | { state: "ok"; health: Health } | { state: "error"; message: string };

export function App() {
  const [status, setStatus] = useState<Status>({ state: "loading" });
  const [config, setConfig] = useState<Config | null>(null);

  const check = useCallback(async () => {
    setStatus({ state: "loading" });
    try {
      setStatus({ state: "ok", health: await getJson<Health>("/health") });
    } catch (err) {
      const message = userMessage(err);
      setStatus({ state: "error", message });
      toast.error(message);
    }
  }, []);

  useEffect(() => {
    void check();
    getJson<Config>("/api/config").then(setConfig, () => setConfig(null));
  }, [check]);

  return (
    <div className="page">
      <AppHeader>
        <SystemStatus status={status} onRetry={check} />
        <a className="btn btn--primary" href="/try">
          <Mic size={16} aria-hidden="true" /> Try it in your browser
        </a>
      </AppHeader>

      <main className="page__main">
        <Card title="Complaints">
          <EmptyState icon={<Phone size={32} />} title="No complaints yet">
            {config?.helpline_display ? (
              <p>
                Call <a href={`tel:${config.helpline_number}`}>{config.helpline_display}</a> or{" "}
                <a href="/try">talk to it in your browser</a>, and describe the problem in Kannada, Hindi or English.
              </p>
            ) : (
              <p>When citizens call the helpline, their complaints will appear here.</p>
            )}
          </EmptyState>
        </Card>
      </main>

      <Toaster />
    </div>
  );
}

function SystemStatus({ status, onRetry }: { status: Status; onRetry: () => void }) {
  if (status.state === "loading") return <Badge>Checking…</Badge>;
  if (status.state === "error")
    return (
      <div className="status">
        <Badge tone="danger">Server unreachable</Badge>
        <Button size="sm" variant="ghost" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden="true" /> Try again
        </Button>
      </div>
    );
  // The server's overall verdict decides; the database is named only when it is the cause.
  if (status.health.status === "ok") return <Badge tone="success">All systems working</Badge>;
  return (
    <div className="status">
      <Badge tone="warning">{status.health.db === "down" ? "Database unreachable" : "Some services degraded"}</Badge>
      <Button size="sm" variant="ghost" onClick={onRetry}>
        <RefreshCw size={14} aria-hidden="true" /> Try again
      </Button>
    </div>
  );
}
