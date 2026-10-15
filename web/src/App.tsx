import { useCallback, useEffect, useState } from "react";
import { Phone, RefreshCw } from "lucide-react";
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
      <header className="page__header">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={32} height={32} />
          <div>
            <h1 className="brand__name">Citizen's Voice</h1>
            <p className="brand__tagline">Report civic problems by phone, in your own language</p>
          </div>
        </div>
        <SystemStatus status={status} onRetry={check} />
      </header>

      <main className="page__main">
        <Card title="Complaints">
          <EmptyState icon={<Phone size={32} />} title="No complaints yet">
            {config?.helpline_display ? (
              <p>
                Call <a href={`tel:${config.helpline_number}`}>{config.helpline_display}</a> and describe the problem in
                Kannada, Hindi or English. It will appear here.
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
  return status.health.db === "ok" ? (
    <Badge tone="success">All systems working</Badge>
  ) : (
    <div className="status">
      <Badge tone="warning">Database unreachable</Badge>
      <Button size="sm" variant="ghost" onClick={onRetry}>
        <RefreshCw size={14} aria-hidden="true" /> Try again
      </Button>
    </div>
  );
}
