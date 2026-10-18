import { ShieldCheck } from "lucide-react";
import { Card } from "../components/Card";
import { ComplaintFeed } from "../components/ComplaintFeed";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import type { Complaint } from "../lib/complaints";
import { useShell } from "../ShellContext";

/** Open emergencies only, so an officer can act on them in one place. They stay in Complaints and on the map
 * as before; this page is a shortcut. Danger to life first, then resource loss, each by priority. */
export function Emergencies() {
  const { list } = useShell();
  const open = (list.state === "ok" ? list.items : [])
    .filter((c) => c.is_emergency && c.status !== "fixed")
    .sort((a, b) => b.priority - a.priority);
  const danger = open.filter((c) => c.emergency_kind !== "loss");
  const loss = open.filter((c) => c.emergency_kind === "loss");

  const section = (title: string, hint: string, items: Complaint[]) =>
    items.length > 0 && (
      <Card title={`${title} (${items.length})`}>
        <p className="emergencies__hint">{hint}</p>
        <ComplaintFeed items={items} showWhy />
      </Card>
    );

  return (
    <>
      <PageHeader title="Emergencies">Open emergencies only: danger to life first, then resource loss.</PageHeader>
      <div className="page-body">
        {list.state === "ok" && open.length === 0 ? (
          <Card title="Emergencies">
            <EmptyState icon={<ShieldCheck size={32} />} title="No open emergencies">
              <p>When a caller reports a live wire, a gas leak or a burst water main, it appears here at once.</p>
            </EmptyState>
          </Card>
        ) : list.state !== "ok" ? (
          <Card title="Emergencies">
            <ComplaintFeed items={[]} />
          </Card>
        ) : (
          <div className="emergencies">
            {section("Danger to life", "Live wire, gas leak, open manhole, collapsing wall: act first.", danger)}
            {section("Resource loss", "Water being wasted by the minute: a burst main or a gushing pipe.", loss)}
          </div>
        )}
      </div>
    </>
  );
}
