import { ComplaintFeed } from "../components/ComplaintFeed";
import { ComplaintMap } from "../components/ComplaintMap";
import { Card } from "../components/Card";
import { LivePanel } from "../components/LivePanel";
import { PageHeader } from "../components/PageHeader";
import { Link } from "../lib/router";
import { useShell } from "../ShellContext";

const NEWEST = 8; // the rest are on the Complaints page

/** The demo screen: a call happens, the complaint and its map pin appear. */
export function LiveDesk() {
  const { list, call, config, selected, select } = useShell();
  const items = list.state === "ok" ? list.items : [];
  const open = items.filter((c) => c.is_emergency && c.status !== "fixed");
  const emergencies = open.length;
  const danger = open.filter((c) => c.emergency_kind !== "loss").length;
  const loss = emergencies - danger;
  const overdue = items.filter((c) => c.overdue).length;

  return (
    <>
      <PageHeader title="Live desk">Calls and complaints appear here as they happen.</PageHeader>
      <div className="desk">
        <section className="desk__map" aria-label="Map">
          <ComplaintMap complaints={items} selected={selected} onSelect={select} />
        </section>
        <div className="desk__side">
          {emergencies > 0 && (
            <p className="dash__alert" role="alert">
              {emergencies} open emergency{emergencies > 1 ? " reports" : " report"}:{" "}
              {[danger && `${danger} danger to life`, loss && `${loss} resource loss`].filter(Boolean).join(", ")}
            </p>
          )}
          {overdue > 0 && (
            <p className="dash__warn">
              {overdue} past the office deadline, so shown to the senior officer
            </p>
          )}
          <LivePanel live={call} config={config} />
          <Card title="Newest complaints">
            <ComplaintFeed items={items.slice(0, NEWEST)} />
            {items.length > NEWEST && (
              <p className="desk__more">
                <Link to="/complaints">All {items.length} complaints</Link>
              </p>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
