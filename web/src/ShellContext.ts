import { createContext, useContext } from "react";
import type { Complaint } from "./lib/complaints";
import type { Resource } from "./lib/resource";
import type { ClerkEvent } from "./lib/steps";

export type Health = { status: "ok" | "degraded"; db: "ok" | "down"; version: string };
export type Config = { helpline_number: string; helpline_display: string };
export type Status = { state: "loading" } | { state: "ok"; health: Health } | { state: "error"; message: string };
export type List = { state: "loading" } | { state: "ok"; items: Complaint[] } | { state: "error"; message: string };

export type ScoreRow = {
  department: string;
  office: string;
  filed: number;
  open: number;
  fixed: number;
  overdue: number;
  deadline_days: number;
  median_days_to_fix: number | null;
};

export type LiveCall = {
  callId: number;
  channel: string;
  lines: { who: "caller" | "clerk"; text: string }[];
  steps: ClerkEvent[];
  ended?: string;
};

export type EmergingItem = {
  kind: "spike" | "cluster";
  headline: string;
  headline_by: "gemma" | "template";
  reports: number;
  window_hours: number;
  category?: string;
  area?: string;
  usual?: number;
  times_usual?: number | null;
  complaint_ids: string[];
};
export type Emerging = { generated_at: string; windows_hours: number[]; history_days: number; items: EmergingItem[] };

export type Brief = {
  facts: {
    window_hours: number;
    new: number;
    new_emergencies: number;
    fixed: number;
    open: number;
    overdue: number;
    worst_office: { office: string; overdue: number; open: number; deadline_days: number } | null;
    clusters: { category: string; area: string; complaints: number; reports: number }[];
  };
  summary_en: string;
  summary_local: string | null;
  source: "gemma" | "template";
  numbers_checked: boolean;
  rejected_numbers: string[];
};

/** A costly answer, fetched only when asked for (see lib/resource.ts). */
export type OnRequest<T> = { resource: Resource<T>; ensure: () => void; refresh: () => void };

/** Everything the pages share. It lives in the shell, above the pages, so switching page loses nothing. */
export type ShellState = {
  status: Status;
  recheck: () => void;
  live: boolean | null; // the live-updates connection
  config: Config | null;
  list: List;
  reload: () => void;
  /** Goes up whenever the list changed (a filing, an update, a sign-in change, Try again): a page showing its own copy fetches again. */
  version: number;
  scores: ScoreRow[] | null;
  selected: string | null;
  select: (trackingId: string | null) => void;
  fresh: Set<string>;
  call: LiveCall | null;
  isOfficer: boolean;
  emerging: OnRequest<Emerging>;
  brief: OnRequest<Brief>;
};

export const ShellContext = createContext<ShellState | null>(null);

export function useShell(): ShellState {
  const s = useContext(ShellContext);
  if (!s) throw new Error("useShell must be used inside <Shell>");
  return s;
}
