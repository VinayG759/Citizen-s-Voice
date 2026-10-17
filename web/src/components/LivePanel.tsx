import { PhoneCall } from "lucide-react";
import { Badge } from "./Badge";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import type { Config, LiveCall } from "../ShellContext";
import { describe } from "../lib/steps";

export function LivePanel({ live, config }: { live: LiveCall | null; config: Config | null }) {
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
