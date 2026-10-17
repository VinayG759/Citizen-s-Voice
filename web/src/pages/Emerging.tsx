import { useEffect } from "react";
import { RefreshCw, TrendingUp } from "lucide-react";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { CATEGORY } from "../lib/complaints";
import { useShell, type EmergingItem } from "../ShellContext";

/** What is rising or bunching up. Counted by code, with its evidence; Gemma only words the headline. */
export function Emerging() {
  const { emerging } = useShell();
  const { resource, ensure, refresh } = emerging;

  // Once, when the page opens. Never on a live event or a timer: the headlines cost an AI call.
  useEffect(() => ensure(), [ensure]);

  return (
    <>
      <PageHeader
        title="Emerging issues"
        actions={
          <Button size="sm" onClick={refresh} loading={resource.state === "loading"}>
            <RefreshCw size={14} aria-hidden="true" /> Refresh
          </Button>
        }
      >
        Problems reported far more than usual, or reports bunching up in one place. Updated when you open this page or press Refresh.
      </PageHeader>
      <div className="page-body">
        {resource.state === "idle" || resource.state === "loading" ? (
          <p className="live__none" aria-busy="true">Looking at recent reports…</p>
        ) : resource.state === "error" ? (
          <div className="dash__error" role="alert">
            <p>{resource.message}</p>
            <Button size="sm" onClick={refresh}>
              <RefreshCw size={14} aria-hidden="true" /> Try again
            </Button>
          </div>
        ) : resource.data.items.length === 0 ? (
          <Card>
            <EmptyState icon={<TrendingUp size={32} />} title="Nothing unusual right now">
              <p>No category or area is being reported well above its usual rate, and no group of reports has formed close together.</p>
            </EmptyState>
          </Card>
        ) : (
          <>
            <ul className="emerging">
              {resource.data.items.map((item, i) => (
                <li key={i}>
                  <EmergingCard item={item} />
                </li>
              ))}
            </ul>
            <p className="live__none">
              Based on the last {resource.data.history_days} days of reports. Generated {new Date(resource.data.generated_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}.
            </p>
          </>
        )}
      </div>
    </>
  );
}

function EmergingCard({ item }: { item: EmergingItem }) {
  const what = item.category ? (CATEGORY[item.category]?.label ?? item.category) : item.area;
  return (
    <Card>
      <div className="emerging__top">
        <Badge tone={item.kind === "cluster" ? "warning" : "neutral"}>{item.kind === "cluster" ? "Cluster" : "Spike"}</Badge>
        <span className="emerging__what">{what}</span>
        <span className="emerging__source">{item.headline_by === "gemma" ? "Headline by Gemma" : "Plain headline"}</span>
      </div>
      <p className="emerging__headline">{item.headline}</p>
      <p className="emerging__facts">
        {item.reports} reports in the last {item.window_hours} hours
        {item.times_usual ? ` · ${item.times_usual}× the usual rate` : ""}
      </p>
      <p className="emerging__evidence">
        Evidence:{" "}
        {item.complaint_ids.map((id, i) => (
          <span key={id}>
            {i > 0 && ", "}
            <a href={`/c/${id}`}>{id}</a>
          </span>
        ))}
      </p>
    </Card>
  );
}
