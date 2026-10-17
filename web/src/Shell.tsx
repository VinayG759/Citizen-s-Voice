import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Building2 } from "lucide-react";
import { EmptyState } from "./components/EmptyState";
import { MobileBar, Sidebar, currentPage } from "./components/Sidebar";
import { useOfficer } from "./components/OfficerSignIn";
import { Toaster } from "./components/Toaster";
import { getJson, userMessage } from "./lib/api";
import type { Complaint } from "./lib/complaints";
import { useResource } from "./lib/resource";
import { Link, useLocation } from "./lib/router";
import type { ClerkEvent } from "./lib/steps";
import { toast } from "./lib/toast";
import { useLiveEvents, type LiveEvent } from "./lib/useLiveEvents";
import {
  ShellContext, type Brief, type Config, type Emerging, type Health, type List, type LiveCall, type ScoreRow, type ShellState, type Status,
} from "./ShellContext";
import { Brief as BriefPage } from "./pages/Brief";
import { Complaints } from "./pages/Complaints";
import { Emerging as EmergingPage } from "./pages/Emerging";
import { LiveDesk } from "./pages/LiveDesk";
import { MapPage } from "./pages/MapPage";
import { Offices } from "./pages/Offices";

const PAGES: Record<string, () => React.JSX.Element> = {
  "/": LiveDesk,
  "/complaints": Complaints,
  "/map": MapPage,
  "/offices": Offices,
  "/emerging": EmergingPage,
  "/brief": BriefPage,
};

/**
 * The officer dashboard: a sidebar and one page per job. Everything the pages share (the complaint list,
 * the live call, the live-updates connection, health) lives here, above the pages, so changing page
 * never drops a call that is on screen. The citizen pages (/try, /c/…) are outside it, with no sidebar.
 */
export function Shell() {
  const { pathname } = useLocation();
  const [status, setStatus] = useState<Status>({ state: "loading" });
  const [config, setConfig] = useState<Config | null>(null);
  const [list, setList] = useState<List>({ state: "loading" });
  const [scores, setScores] = useState<ScoreRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [call, setCall] = useState<LiveCall | null>(null);
  const [version, setVersion] = useState(0);
  const isOfficer = useOfficer();
  const emerging = useResource<Emerging>("/api/emerging?headlines=true");
  const brief = useResource<Brief>("/api/brief");

  const recheck = useCallback(async () => {
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
      setList({ state: "ok", items: await getJson<Complaint[]>("/api/complaints?sort=newest") });
    } catch (err) {
      setList({ state: "error", message: userMessage(err, "Couldn't load complaints.") });
    }
    getJson<ScoreRow[]>("/api/scorecard").then(setScores, () => setScores(null));
  }, []);

  // "Try again" and the like: load the list again, and tell pages that keep their own copy to do the same.
  const reload = useCallback(() => {
    setVersion((v) => v + 1);
    return load();
  }, [load]);

  // Signing in or out changes what is shown (sensitive reports): load again, and tell pages with their own copy.
  const wasOfficer = useRef(isOfficer);
  useEffect(() => {
    void recheck();
    void load();
    getJson<Config>("/api/config").then(setConfig, () => setConfig(null));
    if (wasOfficer.current !== isOfficer) {
      wasOfficer.current = isOfficer;
      setVersion((v) => v + 1);
    }
  }, [recheck, load, isOfficer]);

  // The brief is for officers: signing out forgets it.
  const forgetBrief = brief.reset;
  useEffect(() => {
    if (!isOfficer) forgetBrief();
  }, [isOfficer, forgetBrief]);

  useEffect(() => {
    const page = currentPage(pathname);
    document.title = `${page ? page.label + " · " : ""}Citizen's Voice`;
  }, [pathname]);

  const live = useLiveEvents((e: LiveEvent) => {
    if (e.type === "call_started") {
      const greeting = typeof e.greeting === "string" ? [{ who: "clerk" as const, text: e.greeting }] : [];
      setCall({ callId: Number(e.call_id), channel: String(e.channel), lines: greeting, steps: [] });
    } else if (e.type === "turn") {
      setCall((cur) => {
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
      setCall((cur) => (cur && cur.callId === Number(e.call_id) ? { ...cur, ended: String(e.outcome) } : cur));
    }
  });

  async function addComplaint(trackingId: string) {
    try {
      const c = await getJson<Complaint>(`/api/complaints/${trackingId}`);
      setList((l) => (l.state === "ok" ? { ...l, items: [c, ...l.items.filter((x) => x.tracking_id !== c.tracking_id)] } : l));
      setFresh((f) => new Set(f).add(c.tracking_id));
      setVersion((v) => v + 1);
      toast.success(`New complaint ${c.tracking_id}: ${c.summary_en}`);
    } catch {
      void load();
    }
  }

  async function refreshComplaint(trackingId: string) {
    try {
      const c = await getJson<Complaint>(`/api/complaints/${trackingId}`);
      setList((l) => (l.state === "ok" ? { ...l, items: l.items.map((x) => (x.tracking_id === c.tracking_id ? c : x)) } : l));
      setVersion((v) => v + 1);
      getJson<ScoreRow[]>("/api/scorecard").then(setScores, () => undefined);
    } catch {
      /* the next full load catches up */
    }
  }

  const state: ShellState = useMemo(
    () => ({
      status, recheck, live, config, list, reload, version, scores, selected, select: setSelected, fresh, call, isOfficer,
      emerging: { resource: emerging.resource, ensure: emerging.ensure, refresh: emerging.refresh },
      brief: { resource: brief.resource, ensure: brief.ensure, refresh: brief.refresh },
    }),
    [status, recheck, live, config, list, reload, version, scores, selected, fresh, call, isOfficer, emerging, brief],
  );

  const Page = PAGES[pathname];
  return (
    <ShellContext.Provider value={state}>
      <div className="shell">
        <Sidebar />
        <MobileBar />
        <main className="shell__main">
          {Page ? (
            <Page />
          ) : (
            <div className="page-body">
              <EmptyState icon={<Building2 size={32} />} title="That page doesn't exist">
                <p>
                  <Link to="/">Go to the Live desk</Link>
                </p>
              </EmptyState>
            </div>
          )}
        </main>
        <Toaster />
      </div>
    </ShellContext.Provider>
  );
}
