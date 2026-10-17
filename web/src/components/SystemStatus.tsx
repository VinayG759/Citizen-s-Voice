import { RefreshCw } from "lucide-react";
import { Badge } from "./Badge";
import { Button } from "./Button";
import type { Status } from "../ShellContext";

export function SystemStatus({ status, onRetry, live }: { status: Status; onRetry: () => void; live: boolean | null }) {
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
  if (status.health.status === "ok")
    return (
      <div className="status">
        <Badge tone="success">All systems working</Badge>
        {live === false && <Badge tone="warning">Reconnecting to live updates…</Badge>}
      </div>
    );
  return (
    <div className="status">
      <Badge tone="warning">{status.health.db === "down" ? "Database unreachable" : "Some services degraded"}</Badge>
      <Button size="sm" variant="ghost" onClick={onRetry}>
        <RefreshCw size={14} aria-hidden="true" /> Try again
      </Button>
    </div>
  );
}
