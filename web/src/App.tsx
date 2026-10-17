import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Globe, MessageCircle, Mic, Phone, PhoneCall, RefreshCw, Search } from "lucide-react";
import { AppHeader } from "./components/AppHeader";
import { Badge } from "./components/Badge";
import { Button } from "./components/Button";
import { Card } from "./components/Card";
import { ComplaintMap } from "./components/ComplaintMap";
import { EmptyState } from "./components/EmptyState";
import { OfficerSignIn, useOfficer } from "./components/OfficerSignIn";
import { Toaster } from "./components/Toaster";
import { getJson, userMessage } from "./lib/api";
import { CATEGORY, STATUS_LABEL, timeAgo, urgencyLabel, urgencyTone, type Complaint } from "./lib/complaints";
import { describe, type ClerkEvent } from "./lib/steps";
import { toast } from "./lib/toast";
import { useLiveEvents, type LiveEvent } from "./lib/useLiveEvents";

type Health = { status: "ok" | "degraded"; db: "ok" | "down"; version: string };
type Config = { helpline_number: string; helpline_display: string };
type Status = { state: "loading" } | { state: "ok"; health: Health } | { state: "error"; message: string };
type List = { state: "loading" } | { state: "ok"; items: Complaint[] } | { state: "error"; message: string };
type Sort = "newest" | "priority";
type ScoreRow = {
  department: string;
  office: string;
  filed: number;
  open: number;
  fixed: number;
  overdue: number;
  deadline_days: number;
  median_days_to_fix: number | null;
};

type LiveCall = {
  callId: number;
  channel: string;
  lines: { who: "caller" | "clerk"; text: string }[];
  steps: ClerkEvent[];
  ended?: string;
};

export function App() {
  const [status, setStatus] = useState<Status>({ state: "loading" });
  const [config, setConfig] = useState<Config | null>(null);
  const [list, setList] = useState<List>({ state: "loading" });
  const [selected, setSelected] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [live, setLive] = useState<LiveCall | null>(null);
  const [sort, setSort] = useState<Sort>("newest");
  const [scores, setScores] = useState<ScoreRow[] | null>(null);
  const isOfficer = useOfficer();

  const check = useCallback(async () => {
    setStatus({ state: "loading" });
    try {
      setStatus({ state: "ok", health: await getJson<Health>("/health") });
    } catch (err) {
      setStatus({ state: "error", message: userMessage(err) });
    }
  }, []);

  const load = useCallback(async () => {
    setList({ state: "loading" });
    try {
      setList({ state: "ok", items: await getJson<Complaint[]>(`/api/complaints?sort=${sort}`) });
    } catch (err) {
      setList({ state: "error", message: userMessage(err, "Couldn't load complaints.") });
    }
    getJson<ScoreRow[]>("/api/scorecard").then(setScores, () => setScores(null));
  }, [sort]);

  useEffect(() => {
    void check();
    void load();
    getJson<Config>("/api/config").then(setConfig, () => setConfig(null));
  }, [check, load, isOfficer]); // signing in or out changes what is shown (sensitive reports)

  const connected = useLiveEvents((e: LiveEvent) => {
    if (e.type === "call_started") {
      const greeting = typeof e.greeting === "string" ? [{ who: "clerk" as const, text: e.greeting }] : [];
      setLive({ callId: Number(e.call_id), channel: String(e.channel), lines: greeting, steps: [] });
    } else if (e.type === "turn") {
      setLive((cur) => {
        const base = cur && cur.callId === Number(e.call_id) ? cur
          : { callId: Number(e.call_id), channel: String(e.channel), lines: [], steps: [] };
        return {
          ...base,
          lines: [...base.lines, { who: "caller", text: String(e.caller) }, { who: "clerk", text: String(e.reply) }],
          steps: [...base.steps, ...((e.steps as ClerkEvent[]) ?? [])],
        };
      });
      const filed = e.complaint as { tracking_id: string } | null;
      if (filed) void addComplaint(filed.tracking_id);
    } else if (e.type === "complaint_updated") {
      void refreshComplaint(String(e.tracking_id));
    } else if (e.type === "call_ended") {
      setLive((cur) => (cur && cur.callId === Number(e.call_id) ? { ...cur, ended: String(e.outcome) } : cur));
    }
  });

  async function addComplaint(trackingId: string) {
    try {
      const c = await getJson<Complaint>(`/api/complaints/${trackingId}`);
      setList((l) => (l.state === "ok" ? { ...l, items: [c, ...l.items.filter((x) => x.tracking_id !== c.tracking_id)] } : l));
      setFresh((f) => new Set(f).add(c.tracking_id));
      toast.success(`New complaint ${c.tracking_id}: ${c.summary_en}`);
    } catch {
      void load();
    }
  }

  async function refreshComplaint(trackingId: string) {
    try {
      const c = await getJson<Complaint>(`/api/complaints/${trackingId}`);
      setList((l) => (l.state === "ok" ? { ...l, items: l.items.map((x) => (x.tracking_id === c.tracking_id ? c : x)) } : l));
      getJson<ScoreRow[]>("/api/scorecard").then(setScores, () => undefined);
    } catch {
      /* the next full load catches up */
    }
  }

  const items = list.state === "ok" ? list.items : [];
  const emergencies = items.filter((c) => c.is_emergency && c.status !== "fixed").length;
  const overdue = items.filter((c) => c.overdue).length;

  return (
    <div className="page">
      <AppHeader>
        <SystemStatus status={status} onRetry={check} live={connected} />
        <TrackBox />
        <OfficerSignIn />
        <a className="btn btn--primary" href="/try">
          <Mic size={16} aria-hidden="true" /> Try it in your browser
        </a>
      </AppHeader>

      <main className="dash">
        <section className="dash__list" aria-label="Complaints">
          <Card title={list.state === "ok" ? `Complaints (${items.length})` : "Complaints"}>
            <div className="sort" role="group" aria-label="Order complaints">
              <Button size="sm" variant={sort === "newest" ? "primary" : "ghost"} aria-pressed={sort === "newest"} onClick={() => setSort("newest")}>
                Newest
              </Button>
              <Button size="sm" variant={sort === "priority" ? "primary" : "ghost"} aria-pressed={sort === "priority"} onClick={() => setSort("priority")}>
                Most urgent first
              </Button>
            </div>
            {emergencies > 0 && (
              <p className="dash__alert" role="alert">
                {emergencies} open emergency{emergencies > 1 ? " reports" : " report"}
              </p>
            )}
            {overdue > 0 && (
              <p className="dash__warn">
                {overdue} past the office deadline, so shown to the senior officer
              </p>
            )}
            {list.state === "loading" && <ListSkeleton />}
            {list.state === "error" && (
              <div className="dash__error" role="alert">
                <p>{list.message}</p>
                <Button size="sm" onClick={load}>
                  <RefreshCw size={14} aria-hidden="true" /> Try again
                </Button>
              </div>
            )}
            {list.state === "ok" && items.length === 0 && (
              <EmptyState icon={<Phone size={32} />} title="No complaints yet">
                <p>
                  Call {config?.helpline_display ? <a href={`tel:${config.helpline_number}`}>{config.helpline_display}</a> : "the helpline"}{" "}
                  or <a href="/try">talk to it in your browser</a>.
                </p>
              </EmptyState>
            )}
            {items.length > 0 && (
              <ol className="feed">
                {items.map((c) => (
                  <ComplaintRow
                    key={c.tracking_id}
                    c={c}
                    selected={c.tracking_id === selected}
                    fresh={fresh.has(c.tracking_id)}
                    showWhy={sort === "priority"}
                    onSelect={() => setSelected(c.tracking_id)}
                  />
                ))}
              </ol>
            )}
          </Card>
        </section>

        <section className="dash__map" aria-label="Map">
          <ComplaintMap complaints={items} selected={selected} onSelect={setSelected} />
        </section>

        <aside className="dash__live" aria-label="Live call">
          <LivePanel live={live} config={config} />
          <Scorecard rows={scores} />
        </aside>
      </main>
      <Toaster />
    </div>
  );
}

const CHANNEL_ICON = { phone: PhoneCall, web: Globe, whatsapp: MessageCircle, telegram: MessageCircle };
const CHANNEL_NAME = { phone: "By phone", web: "On the web", whatsapp: "On WhatsApp", telegram: "On Telegram" };

type RowProps = { c: Complaint; selected: boolean; fresh: boolean; showWhy: boolean; onSelect: () => void };

function ComplaintRow({ c, selected, fresh, showWhy, onSelect }: RowProps) {
  const Channel = CHANNEL_ICON[c.channel] ?? Globe;
  const Icon = CATEGORY[c.category]?.icon ?? CATEGORY.other.icon;
  return (
    <li className={`feed__item${selected ? " feed__item--selected" : ""}${fresh ? " feed__item--fresh" : ""}`}>
      <button type="button" className="feed__select" onClick={onSelect} aria-pressed={selected}>
        <span className="feed__top">
          <Icon size={16} aria-hidden="true" />
          <strong>{c.tracking_id}</strong>
          <Badge tone={urgencyTone(c)}>{urgencyLabel(c)}</Badge>
          {c.status !== "open" && <Badge tone={c.status === "fixed" ? "success" : "neutral"}>{STATUS_LABEL[c.status]}</Badge>}
          {c.overdue && <Badge tone="warning">Overdue</Badge>}
          <span className="feed__time">{timeAgo(c.created_at)}</span>
        </span>
        <span className="feed__summary">{c.summary_en}</span>
        <span className="feed__meta">
          <Channel size={12} aria-label={CHANNEL_NAME[c.channel] ?? c.channel} />
          {c.place_name ?? "Place unknown"}
          {c.since_when ? ` · since ${c.since_when}` : ""}
          {c.report_count > 1 ? ` · ${c.report_count} reports` : ""}
        </span>
        <span className="feed__meta">To: {c.office}</span>
        {showWhy && <span className="feed__why">Why here: {c.priority_why}</span>}
      </button>
      <a className="feed__open" href={`/c/${c.tracking_id}`}>
        Details
      </a>
    </li>
  );
}

function LivePanel({ live, config }: { live: LiveCall | null; config: Config | null }) {
  if (!live)
    return (
      <Card title="Live call">
        <EmptyState icon={<PhoneCall size={28} />} title="Waiting for a call">
          <p>
            When someone calls {config?.helpline_display ?? "the helpline"} or uses the browser page, the conversation
            and every step Gemma takes appear here as they happen.
          </p>
        </EmptyState>
      </Card>
    );
  return (
    <Card title={live.channel === "phone" ? "Live call — phone" : "Live call — browser"}>
      {live.ended && <Badge tone={live.ended === "filed" ? "success" : "neutral"}>Call ended: {live.ended}</Badge>}
      <ol className="chat chat--compact">
        {live.lines.map((l, i) => (
          <li key={i} className={`chat__line chat__line--${l.who}`}>
            <span className="chat__who">{l.who === "caller" ? "Caller" : "Clerk (Gemma 4)"}</span>
            <p className="chat__text">{l.text}</p>
          </li>
        ))}
      </ol>
      <h3 className="live__steps-title">Gemma's steps</h3>
      {live.steps.length === 0 ? (
        <p className="live__none">No steps yet.</p>
      ) : (
        <ol className="steps">
          {live.steps.map((e, i) => (
            <li key={i} className={`steps__item steps__item--${e.kind}`}>
              {describe(e)}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

/** "Which office is keeping its promises?" Counted by the server, not guessed by the AI. */
function Scorecard({ rows }: { rows: ScoreRow[] | null }) {
  if (!rows || rows.length === 0) return null;
  return (
    <Card title="Office scorecard">
      <table className="score">
        <thead>
          <tr>
            <th scope="col">Office</th>
            <th scope="col">Open</th>
            <th scope="col">Overdue</th>
            <th scope="col">Fixed</th>
            <th scope="col">Typical fix</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.department}>
              <th scope="row">
                {r.office}
                <span className="score__deadline">
                  deadline {r.deadline_days} day{r.deadline_days > 1 ? "s" : ""}
                </span>
              </th>
              <td>{r.open}</td>
              <td className={r.overdue > 0 ? "score__bad" : undefined}>{r.overdue}</td>
              <td>{r.fixed}</td>
              <td>{r.median_days_to_fix === null ? "—" : `${r.median_days_to_fix} d`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/** Anyone with a tracking number can see where their complaint is. */
function TrackBox() {
  const [value, setValue] = useState("");
  function go(e: FormEvent) {
    e.preventDefault();
    const digits = value.replace(/\D/g, "");
    if (digits) window.location.href = `/c/CV-${digits}`;
  }
  return (
    <form className="track" onSubmit={go} role="search">
      <input
        className="input input--sm"
        aria-label="Tracking number"
        placeholder="Track: CV-1004"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <Button size="sm" type="submit" aria-label="Track complaint">
        <Search size={14} aria-hidden="true" />
      </Button>
    </form>
  );
}

function ListSkeleton() {
  return (
    <ol className="feed" aria-busy="true" aria-label="Loading complaints">
      {[0, 1, 2].map((i) => (
        <li key={i} className="feed__item feed__item--skeleton" />
      ))}
    </ol>
  );
}

function SystemStatus({ status, onRetry, live }: { status: Status; onRetry: () => void; live: boolean | null }) {
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
