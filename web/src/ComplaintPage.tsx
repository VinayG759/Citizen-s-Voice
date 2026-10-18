import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ArrowLeft, Camera, Play, RefreshCw, RotateCcw, SearchX, Send } from "lucide-react";
import { AppHeader } from "./components/AppHeader";
import { Badge } from "./components/Badge";
import { Button } from "./components/Button";
import { Card } from "./components/Card";
import { ComplaintMap } from "./components/ComplaintMap";
import { EmptyState } from "./components/EmptyState";
import { OfficerSignIn, useOfficer } from "./components/OfficerSignIn";
import { Toaster } from "./components/Toaster";
import { ApiError, getJson, postForm, postJson, userMessage } from "./lib/api";
import {
  CATEGORY,
  CHANNEL_LABEL,
  OFFICES,
  STATUS_LABEL,
  urgencyLabel,
  urgencyTone,
  type ComplaintDetail,
  type LinkedReport,
  type PhotoMeta,
  type TranscriptLine,
} from "./lib/complaints";
import { describe } from "./lib/steps";
import { toast } from "./lib/toast";

type State =
  | { state: "loading" }
  | { state: "ok"; c: ComplaintDetail }
  | { state: "missing" }
  | { state: "error"; message: string };

const LANGUAGE: Record<string, string> = { kn: "Kannada", hi: "Hindi", en: "English" };

export function ComplaintPage({ trackingId }: { trackingId: string }) {
  const [s, setS] = useState<State>({ state: "loading" });
  const isOfficer = useOfficer();

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
  }, [load, isOfficer]);

  return (
    <div className="page">
      <AppHeader>
        <a className="btn btn--secondary" href="/">
          <ArrowLeft size={16} aria-hidden="true" /> All complaints
        </a>
        <OfficerSignIn />
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
        {s.state === "ok" && <Detail c={s.c} officer={isOfficer} onChanged={load} />}
      </main>
      <Toaster />
    </div>
  );
}

const when = (iso: string) => new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

function reporter(r: Pick<LinkedReport, "channel" | "caller_last4" | "language">) {
  return (
    (CHANNEL_LABEL[r.channel] ?? r.channel) +
    (r.caller_last4 ? ` · number ending ${r.caller_last4}` : "") +
    (r.language ? ` · ${LANGUAGE[r.language.split("-")[0]] ?? r.language}` : "")
  );
}

function Transcript({ lines }: { lines: TranscriptLine[] }) {
  if (lines.length === 0) return <p className="live__none">No conversation recorded.</p>;
  return (
    <ol className="chat">
      {lines.map((t, i) => (
        <li key={i} className={`chat__line chat__line--${t.speaker}`}>
          <span className="chat__who">{t.speaker === "caller" ? "Caller" : "Clerk (Gemma 4)"}</span>
          <p className="chat__text">{t.text}</p>
        </li>
      ))}
    </ol>
  );
}

/** Everyone else who reported the same problem, in their own words: the details above are the
 * FIRST report's, so without this a later reporter's chat looks like it was replaced by someone else's. */
function LinkedReports({ reports, hidden }: { reports: LinkedReport[]; hidden: boolean }) {
  return (
    <Card title={`Also reported by ${reports.length} more ${reports.length === 1 ? "person" : "people"}`}>
      <ol className="linked">
        {reports.map((r, i) => (
          <li key={i} className="linked__item">
            <p className="linked__who">
              <strong>Report {i + 2}</strong> · {reporter(r)} · {when(r.created_at)}
            </p>
            {!hidden && (
              <>
                <p className="detail__summary">{r.summary_en}</p>
                {r.summary_local && <p className="detail__local">{r.summary_local}</p>}
                <dl className="facts">
                  <dt>Place</dt>
                  <dd>
                    {r.place_name ?? "Unknown"}
                    {r.landmark ? ` (${r.landmark})` : ""}
                  </dd>
                  <dt>Since</dt>
                  <dd>{r.since_when ?? "Not said"}</dd>
                </dl>
                <details className="linked__chat">
                  <summary>Their conversation</summary>
                  <Transcript lines={r.transcript} />
                </details>
              </>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function Detail({ c, officer, onChanged }: { c: ComplaintDetail; officer: boolean; onChanged: () => void }) {
  const Icon = CATEGORY[c.category]?.icon ?? CATEGORY.other.icon;
  const filed = when(c.created_at);
  const linked = c.linked_reports ?? [];
  const hidden = c.sensitive && !officer;
  return (
    <div className="detail__grid">
      <div className="detail__main">
        <Card>
          <div className="detail__head">
            <Icon size={20} aria-hidden="true" />
            <h2 className="detail__id">{c.tracking_id}</h2>
            <Badge tone={urgencyTone(c)}>{urgencyLabel(c)}</Badge>
            <Badge tone={c.status === "fixed" ? "success" : "neutral"}>{STATUS_LABEL[c.status]}</Badge>
            {c.overdue && <Badge tone="warning">Overdue · escalated</Badge>}
            {c.status === "fixed" && !c.photos.some((p) => p.kind === "fix") && (
              <Badge tone="warning">No fix photo · the citizen's answer decides</Badge>
            )}
          </div>
          <p className="detail__summary">{c.summary_en}</p>
          {c.summary_local && <p className="detail__local">{c.summary_local}</p>}
          <dl className="facts">
            <dt>Sent to</dt>
            <dd>{c.office}</dd>
            <dt>Deadline</dt>
            <dd>
              {c.deadline_days} day{c.deadline_days > 1 ? "s" : ""} from filing
              {c.overdue ? " — overdue, shown to the senior officer" : ""}
            </dd>
            <dt>Category</dt>
            <dd>{CATEGORY[c.category]?.label ?? c.category}</dd>
            <dt>Place</dt>
            <dd>
              {c.place_name ?? "Unknown"}
              {c.landmark ? ` (${c.landmark})` : ""}
            </dd>
            <dt>Since</dt>
            <dd>{c.since_when ?? "Not said"}</dd>
            <dt>{linked.length ? "First reported by" : "Reported by"}</dt>
            <dd>{reporter(c)}</dd>
            <dt>Filed</dt>
            <dd>{filed}</dd>
            {linked.length > 0 && (
              <>
                <dt>Reports</dt>
                <dd>{linked.length + 1} people · the details above are the first report's, the others are below</dd>
              </>
            )}
          </dl>
        </Card>

        <Card title="What has happened">
          <ol className="timeline">
            {c.timeline.map((t, i) => (
              <li key={i} className={`timeline__item timeline__item--${t.status}`}>
                <strong>{STATUS_LABEL[t.status]}</strong>
                <span className="timeline__when">
                  {new Date(t.at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })} · by {t.by}
                </span>
                {t.note && <p className="timeline__note">{t.note}</p>}
              </li>
            ))}
          </ol>
        </Card>

        {c.photos.length > 0 && <PhotoCheck trackingId={c.tracking_id} photos={c.photos} />}

        {officer && <OfficerActions c={c} onChanged={onChanged} />}

        <Card title={linked.length ? "Conversation (first report)" : "Conversation"}>
          {hidden ? (
            <p className="live__none">Sensitive report: details are visible only to officers.</p>
          ) : (
            <Transcript lines={c.transcript} />
          )}
        </Card>

        {linked.length > 0 && <LinkedReports reports={linked} hidden={hidden} />}
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

const LOOKS = { yes: "looks fixed", no: "not fixed", unclear: "can't tell" } as const;

/** The citizen's photo and the fix photo side by side, with Gemma's comparison of the two.
 * Gemma's check is advice: the citizen's call-back answer decides (vision.py). */
function PhotoCheck({ trackingId, photos }: { trackingId: string; photos: PhotoMeta[] }) {
  // The same pair Gemma compared: the citizen's first photo (repo.citizen_photo) and the latest fix.
  const citizen = photos.find((p) => p.kind === "citizen");
  const fix = [...photos].reverse().find((p) => p.kind === "fix");
  const others = photos.filter((p) => p !== citizen && p !== fix);
  const seen = citizen?.verdict;
  const v = fix?.verdict;
  const tone = v?.looks_fixed === "yes" ? "success" : v?.looks_fixed === "no" ? "danger" : "neutral";
  const compared = !!citizen && v?.compared_with_citizen_photo !== false;
  const samePlace = !compared
    ? "No citizen photo to compare"
    : v?.same_place_likely === true ? "Yes" : v?.same_place_likely === false ? "No" : "Can't tell";
  return (
    <Card title={fix ? "Photo check" : "Photos"}>
      <div className="photos">
        {citizen && (
          <Photo trackingId={trackingId} p={citizen}>
            {seen?.what_i_see && <span>Gemma saw: {seen.what_i_see}</span>}
            {seen?.severity && <span>Severity {seen.severity} of 5</span>}
          </Photo>
        )}
        {fix && <Photo trackingId={trackingId} p={fix} />}
        {others.map((p) => (
          <Photo key={p.id} trackingId={trackingId} p={p} />
        ))}
      </div>
      {fix && (
        <>
          {v?.looks_fixed ? (
            <dl className="facts">
              <dt>Gemma's verdict</dt>
              <dd>
                <Badge tone={tone}>{LOOKS[v.looks_fixed]}</Badge>
              </dd>
              <dt>Same place</dt>
              <dd>{samePlace}</dd>
              {compared && !!v.matching?.length && (
                <>
                  <dt>What matches</dt>
                  <dd>{v.matching.join(" · ")}</dd>
                </>
              )}
              {compared && !!v.differences?.length && (
                <>
                  <dt>What differs</dt>
                  <dd>{v.differences.join(" · ")}</dd>
                </>
              )}
              {v.confidence && (
                <>
                  <dt>Confidence</dt>
                  <dd>{v.confidence}</dd>
                </>
              )}
              {v.reason && (
                <>
                  <dt>Why</dt>
                  <dd>{v.reason}</dd>
                </>
              )}
              {v.model && (
                <>
                  <dt>Model</dt>
                  <dd>{v.model}</dd>
                </>
              )}
            </dl>
          ) : (
            <p className="live__none">Gemma did not check this photo.</p>
          )}
          <p className="actions__hint">Gemma's check is advice. The citizen's answer decides.</p>
        </>
      )}
    </Card>
  );
}

function Photo({ trackingId, p, children }: { trackingId: string; p: PhotoMeta; children?: ReactNode }) {
  return (
    <figure className="photo">
      <img
        src={`/api/complaints/${trackingId}/photos/${p.id}`}
        alt={p.kind === "fix" ? "Photo sent by the officer after the fix" : "Photo sent by the citizen"}
        loading="lazy"
      />
      <figcaption>
        {p.kind === "fix" ? "After the fix (officer)" : "From the citizen"}
        {children && <span className="photo__verdict">{children}</span>}
      </figcaption>
    </figure>
  );
}

/** Officer-only: move the complaint forward. "Fixed" always needs a photo, which Gemma checks. */
function OfficerActions({ c, onChanged }: { c: ComplaintDetail; onChanged: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [office, setOffice] = useState(c.department);
  const [photo, setPhoto] = useState<File | null>(null);
  const base = `/api/complaints/${c.tracking_id}`;

  async function run(name: string, action: () => Promise<unknown>, done: string) {
    setBusy(name);
    try {
      await action();
      toast.success(done);
      setNote("");
      setPhoto(null);
      onChanged();
    } catch (err) {
      toast.error(userMessage(err, "Couldn't update the complaint. Try again."));
    } finally {
      setBusy(null);
    }
  }

  function markFixed(e: FormEvent) {
    e.preventDefault();
    const form = new FormData();
    if (photo) form.append("photo", photo); // optional: not every fix can be photographed
    if (note.trim()) form.append("note", note.trim());
    void run(
      "fixed",
      () => postForm(`${base}/fixed`, form),
      photo
        ? "Marked fixed. Gemma checked the photo; the citizen will be asked to confirm."
        : "Marked fixed without a photo; the citizen will be asked to confirm.",
    );
  }

  const note_ = note.trim() || null;
  return (
    <Card title="Officer actions">
      <div className="actions">
        <label className="field__label" htmlFor="note">
          Note (optional)
        </label>
        <input id="note" className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Crew sent, work starts Monday" aria-describedby="note-hint" />
        <p id="note-hint" className="actions__hint">Shown on the public timeline and sent to the citizen.</p>

        <div className="actions__row">
          {c.status !== "in_progress" && c.status !== "fixed" && (
            <Button
              loading={busy === "start"}
              disabled={!!busy}
              onClick={() => run("start", () => postJson(`${base}/status`, { status: "in_progress", note: note_ }), "Marked in progress.")}
            >
              <Play size={14} aria-hidden="true" /> Start work
            </Button>
          )}
          {c.status === "fixed" && (
            <Button
              loading={busy === "reopen"}
              disabled={!!busy}
              onClick={() => run("reopen", () => postJson(`${base}/status`, { status: "reopened", note: note_ }), "Reopened.")}
            >
              <RotateCcw size={14} aria-hidden="true" /> Reopen
            </Button>
          )}
        </div>

        {c.status !== "fixed" && (
          <form className="actions__row" onSubmit={markFixed}>
            <label className="btn btn--secondary">
              <Camera size={14} aria-hidden="true" /> {photo ? photo.name : "Add photo (optional)"}
              <input
                type="file"
                accept="image/*"
                className="visually-hidden"
                onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
              />
            </label>
            <Button type="submit" variant="primary" loading={busy === "fixed"} disabled={!!busy}>
              Mark fixed
            </Button>
          </form>
        )}

        <div className="actions__row">
          <label className="visually-hidden" htmlFor="office">
            Office
          </label>
          <select id="office" className="input" value={office} onChange={(e) => setOffice(e.target.value)}>
            {Object.entries(OFFICES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <Button
            loading={busy === "route"}
            disabled={!!busy || office === c.department}
            onClick={() => run("route", () => postJson(`${base}/route`, { department: office, note: note_ }), `Sent to ${OFFICES[office]}.`)}
          >
            <Send size={14} aria-hidden="true" /> Send to this office
          </Button>
        </div>
      </div>
    </Card>
  );
}
