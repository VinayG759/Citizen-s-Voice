import { Globe, MessageCircle, PhoneCall } from "lucide-react";
import { Badge } from "./Badge";
import { CATEGORY, STATUS_LABEL, timeAgo, urgencyLabel, urgencyTone, type Complaint } from "../lib/complaints";

const CHANNEL_ICON = { phone: PhoneCall, web: Globe, whatsapp: MessageCircle, telegram: MessageCircle };
const CHANNEL_NAME = { phone: "By phone", web: "On the web", whatsapp: "On WhatsApp", telegram: "On Telegram" };

type RowProps = { c: Complaint; selected: boolean; fresh: boolean; showWhy: boolean; onSelect: () => void };

export function ComplaintRow({ c, selected, fresh, showWhy, onSelect }: RowProps) {
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

export function ListSkeleton() {
  return (
    <ol className="feed" aria-busy="true" aria-label="Loading complaints">
      {[0, 1, 2].map((i) => (
        <li key={i} className="feed__item feed__item--skeleton" />
      ))}
    </ol>
  );
}
