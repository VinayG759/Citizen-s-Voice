import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, RefreshCw, SearchX } from "lucide-react";
import { AppHeader } from "./components/AppHeader";
import { Badge } from "./components/Badge";
import { Button } from "./components/Button";
import { Card } from "./components/Card";
import { ComplaintMap } from "./components/ComplaintMap";
import { EmptyState } from "./components/EmptyState";
import { ApiError, getJson, userMessage } from "./lib/api";
import { CATEGORY, STATUS_LABEL, urgencyLabel, urgencyTone, type ComplaintDetail } from "./lib/complaints";
import { describe } from "./lib/steps";

type State =
  | { state: "loading" }
  | { state: "ok"; c: ComplaintDetail }
  | { state: "missing" }
  | { state: "error"; message: string };

const LANGUAGE: Record<string, string> = { kn: "Kannada", hi: "Hindi", en: "English" };

export function ComplaintPage({ trackingId }: { trackingId: string }) {
  const [s, setS] = useState<State>({ state: "loading" });

  const load = useCallback(async () => {
    setS({ state: "loading" });
    try {
      setS({ state: "ok", c: await getJson<ComplaintDetail>(`/api/complaints/${encodeURIComponent(trackingId)}`) });
    } catch (err) {
      setS(err instanceof ApiError && err.status === 404 ? { state: "missing" } : { state: "error", message: userMessage(err) });
    }
  }, [trackingId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page">
      <AppHeader>
        <a className="btn btn--secondary" href="/">
          <ArrowLeft size={16} aria-hidden="true" /> All complaints
        </a>
      </AppHeader>
      <main className="page__main detail">
        {s.state === "loading" && <p aria-busy="true">Loading {trackingId}…</p>}
        {s.state === "missing" && (
          <Card>
            <EmptyState icon={<SearchX size={32} />} title={`No complaint ${trackingId}`}>
              <p>
                Check the tracking number, or go back to <a href="/">all complaints</a>.
              </p>
            </EmptyState>
          </Card>
        )}
        {s.state === "error" && (
          <Card>
            <div className="dash__error" role="alert">
              <p>{s.message}</p>
              <Button size="sm" onClick={load}>
                <RefreshCw size={14} aria-hidden="true" /> Try again
              </Button>
            </div>
          </Card>
        )}
        {s.state === "ok" && <Detail c={s.c} />}
      </main>
    </div>
  );
}

function Detail({ c }: { c: ComplaintDetail }) {
  const Icon = CATEGORY[c.category]?.icon ?? CATEGORY.other.icon;
  const filed = new Date(c.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
  return (
    <div className="detail__grid">
      <div className="detail__main">
        <Card>
          <div className="detail__head">
            <Icon size={20} aria-hidden="true" />
            <h2 className="detail__id">{c.tracking_id}</h2>
            <Badge tone={urgencyTone(c)}>{urgencyLabel(c)}</Badge>
            <Badge>{STATUS_LABEL[c.status]}</Badge>
          </div>
          <p className="detail__summary">{c.summary_en}</p>
          {c.summary_local && <p className="detail__local">{c.summary_local}</p>}
          <dl className="facts">
            <dt>Category</dt>
            <dd>{CATEGORY[c.category]?.label ?? c.category}</dd>
            <dt>Place</dt>
            <dd>
              {c.place_name ?? "Unknown"}
              {c.landmark ? ` (${c.landmark})` : ""}
            </dd>
            <dt>Since</dt>
            <dd>{c.since_when ?? "Not said"}</dd>
            <dt>Reported by</dt>
            <dd>
              {c.channel === "phone" ? "Phone call" : "Browser"}
              {c.caller_last4 ? ` · number ending ${c.caller_last4}` : ""}
              {c.language ? ` · ${LANGUAGE[c.language.split("-")[0]] ?? c.language}` : ""}
            </dd>
            <dt>Filed</dt>
            <dd>{filed}</dd>
          </dl>
        </Card>

        <Card title="Conversation">
          {c.transcript.length === 0 ? (
            <p className="live__none">No conversation recorded.</p>
          ) : (
            <ol className="chat">
              {c.transcript.map((t, i) => (
                <li key={i} className={`chat__line chat__line--${t.speaker}`}>
                  <span className="chat__who">{t.speaker === "caller" ? "Caller" : "Clerk (Gemma 4)"}</span>
                  <p className="chat__text">{t.text}</p>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      <div className="detail__side">
        <Card title="Where">
          <ComplaintMap complaints={[c]} selected={c.tracking_id} height={260} zoom={15} />
        </Card>
        <Card title="Gemma's steps">
          {c.steps.length === 0 ? (
            <p className="live__none">No steps recorded.</p>
          ) : (
            <ol className="steps">
              {c.steps.map((e, i) => (
                <li key={i} className={`steps__item steps__item--${e.kind}`}>
                  {describe(e)}
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </div>
  );
}
