import {
  CircleAlert,
  Construction,
  Droplets,
  Lightbulb,
  Trash2,
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
  is_incomplete: boolean;
  place_name: string | null;
  landmark: string | null;
  lat: number | null;
  lon: number | null;
  since_when: string | null;
  report_count: number;
  channel: "phone" | "web" | "whatsapp";
  caller_last4: string | null;
  created_at: string;
};

export type ComplaintDetail = Complaint & {
  transcript: { speaker: "caller" | "clerk"; text: string; language: string | null; at: string }[];
  steps: ClerkEvent[];
};

/** Same word for the same thing everywhere (UI rule 1). */
export const CATEGORY: Record<string, { label: string; icon: LucideIcon }> = {
  road: { label: "Road", icon: Construction },
  water: { label: "Water", icon: Droplets },
  electricity: { label: "Electricity", icon: Zap },
  garbage: { label: "Garbage", icon: Trash2 },
  drainage: { label: "Drainage", icon: Waves },
  streetlight: { label: "Streetlight", icon: Lightbulb },
  other: { label: "Other", icon: CircleAlert },
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

export function urgencyLabel(c: Pick<Complaint, "urgency" | "is_emergency">): string {
  if (c.is_emergency) return "Emergency";
  return ["", "Low", "Low", "Medium", "High", "Urgent"][c.urgency] ?? "Medium";
}

export function timeAgo(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
