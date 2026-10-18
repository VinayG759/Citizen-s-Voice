import {
  Banknote,
  Building2,
  Bus,
  CircleAlert,
  Construction,
  Dog,
  Droplets,
  Factory,
  GraduationCap,
  HeartPulse,
  Lightbulb,
  ShieldAlert,
  ShoppingBasket,
  Siren,
  Trash2,
  TrafficCone,
  TreePine,
  Volume2,
  Waves,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { ClerkEvent } from "./steps";

export type Complaint = {
  tracking_id: string;
  status: "open" | "in_progress" | "fixed" | "reopened";
  category: string;
  summary_en: string;
  summary_local: string | null;
  language: string | null;
  urgency: number;
  is_emergency: boolean;
  emergency_kind?: EmergencyKind | null; // set by the server (officer.emergency_kind) for emergencies
  is_incomplete: boolean;
  place_name: string | null;
  landmark: string | null;
  lat: number | null;
  lon: number | null;
  since_when: string | null;
  report_count: number;
  channel: "phone" | "web" | "whatsapp" | "telegram";
  caller_last4: string | null;
  created_at: string;
  department: string;
  sensitive: boolean;
  // what happens next (computed by the server, rules not AI)
  office: string;
  deadline_days: number;
  overdue: boolean;
  escalated: boolean;
  priority: number;
  priority_why: string;
};

export type TimelineEntry = { status: Complaint["status"]; by: "officer" | "citizen" | "system"; note: string | null; at: string };
/** What Gemma said about a photo (vision.py). Every field is optional: verdicts saved before
 * 18 Oct have no matching / differences / confidence. */
export type PhotoVerdict = {
  // fix photo (check_fix)
  looks_fixed?: "yes" | "no" | "unclear";
  reason?: string;
  same_place_likely?: boolean | null;
  matching?: string[];
  differences?: string[];
  confidence?: "low" | "medium" | "high" | null;
  compared_with_citizen_photo?: boolean;
  // citizen photo (look_at_problem)
  what_i_see?: string;
  severity?: number | null;
  model?: string;
};

export type PhotoMeta = {
  id: number;
  kind: "citizen" | "fix";
  verdict: PhotoVerdict | null;
  at: string;
};

export type TranscriptLine = { speaker: "caller" | "clerk"; text: string; language: string | null; at: string };

/** Another person who reported the same problem: their own details and words. */
export type LinkedReport = {
  channel: Complaint["channel"];
  language: string | null;
  caller_last4: string | null;
  summary_en: string;
  summary_local: string | null;
  place_name: string | null;
  landmark: string | null;
  since_when: string | null;
  created_at: string;
  transcript: TranscriptLine[];
};

export type ComplaintDetail = Complaint & {
  timeline: TimelineEntry[];
  photos: PhotoMeta[];
  transcript: TranscriptLine[];
  steps: ClerkEvent[];
  linked_reports?: LinkedReport[];
};

/** Same word for the same thing everywhere (UI rule 1). */
export const CATEGORY: Record<string, { label: string; icon: LucideIcon }> = {
  road: { label: "Road", icon: Construction },
  water: { label: "Water", icon: Droplets },
  electricity: { label: "Electricity", icon: Zap },
  garbage: { label: "Garbage", icon: Trash2 },
  drainage: { label: "Drainage", icon: Waves },
  streetlight: { label: "Streetlight", icon: Lightbulb },
  trees: { label: "Trees", icon: TreePine },
  animals: { label: "Animals", icon: Dog },
  noise: { label: "Noise", icon: Volume2 },
  pollution: { label: "Pollution", icon: Factory },
  traffic: { label: "Traffic", icon: TrafficCone },
  transport: { label: "Buses", icon: Bus },
  health: { label: "Health", icon: HeartPulse },
  education: { label: "Schools", icon: GraduationCap },
  ration: { label: "Ration shop", icon: ShoppingBasket },
  pension: { label: "Pension", icon: Banknote },
  safety: { label: "Safety", icon: ShieldAlert },
  building: { label: "Building", icon: Building2 },
  corruption: { label: "Corruption", icon: Siren },
  other: { label: "Other", icon: CircleAlert },
};

/** Offices a complaint can be sent to — same names as the server (app/officer.py). */
export const OFFICES: Record<string, string> = {
  bbmp: "BBMP (city corporation)",
  bescom: "BESCOM (electricity)",
  bwssb: "BWSSB (water)",
  bmtc: "BMTC (buses)",
  traffic_police: "Traffic Police",
  police: "Police (non-emergency)",
  health: "Health Department",
  education: "Education Department",
  food_civil_supplies: "Food & Civil Supplies (ration shops)",
  revenue: "Revenue (pensions, certificates)",
  pollution_board: "Pollution Control Board",
  panchayat: "Gram Panchayat",
  lokayukta: "Lokayukta (corruption)",
  unrouted: "Not yet routed",
};

export const CHANNEL_LABEL: Record<Complaint["channel"], string> = {
  phone: "Phone call",
  web: "Browser",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
};

export const STATUS_LABEL: Record<Complaint["status"], string> = {
  open: "Open",
  in_progress: "In progress",
  fixed: "Fixed",
  reopened: "Reopened",
};

export function urgencyTone(c: Pick<Complaint, "urgency" | "is_emergency">): "neutral" | "warning" | "danger" {
  if (c.is_emergency || c.urgency >= 5) return "danger";
  return c.urgency >= 4 ? "warning" : "neutral";
}

/** Two kinds of emergency: danger to life first, then a resource wasted by the minute (a burst water main). */
export type EmergencyKind = "danger" | "loss";

export function emergencyKindLabel(kind: EmergencyKind | null | undefined): string {
  return kind === "loss" ? "resource loss" : "danger to life";
}

export function urgencyLabel(c: Pick<Complaint, "urgency" | "is_emergency">): string {
  if (c.is_emergency) return "Emergency";
  return ["", "Low", "Low", "Medium", "High", "Urgent"][c.urgency] ?? "Medium";
}

/** What the Complaints and Map pages can narrow the list by. An empty string means "all". */
export type Filters = { category: string; office: string; status: string; channel: string };
export const FILTER_KEYS = ["category", "office", "status", "channel"] as const;

/** True if the complaint passes every filter (`skip` leaves one out, to count what choosing it would show). */
export function passes(c: Complaint, f: Partial<Filters>, skip?: keyof Filters): boolean {
  return (
    (skip === "category" || !f.category || c.category === f.category) &&
    (skip === "office" || !f.office || c.department === f.office) &&
    (skip === "status" || !f.status || c.status === f.status) &&
    (skip === "channel" || !f.channel || c.channel === f.channel)
  );
}

export function timeAgo(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
