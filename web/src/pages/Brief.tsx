import { useEffect, useState } from "react";
import { Download, Lock, RefreshCw } from "lucide-react";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { OfficerSignIn } from "../components/OfficerSignIn";
import { PageHeader } from "../components/PageHeader";
import { getBlob, userMessage } from "../lib/api";
import { CATEGORY } from "../lib/complaints";
import { Link } from "../lib/router";
import { toast } from "../lib/toast";
import { useShell, type Brief as BriefData } from "../ShellContext";

/** Today's brief for officers: the numbers are counted by code, the sentences written by Gemma and every number checked. */
export function Brief() {
  const { brief, isOfficer } = useShell();
  const { resource, ensure, refresh } = brief;

  // Only an officer's browser asks for it, and only once when the page opens.
  useEffect(() => {
    if (isOfficer) ensure();
  }, [isOfficer, ensure]);

  if (!isOfficer)
    return (
      <>
        <PageHeader title="Morning brief">Today's numbers and what needs attention first, for officers.</PageHeader>
        <div className="page-body">
          <Card>
            <EmptyState icon={<Lock size={32} />} title="Officers only">
              <p>Sign in with the officer passcode to see the morning brief and download the complaints as a spreadsheet.</p>
              <div className="brief__signin">
                <OfficerSignIn />
              </div>
            </EmptyState>
          </Card>
        </div>
      </>
    );

  return (
    <>
      <PageHeader
        title="Morning brief"
        actions={
          <>
            <DownloadCsv />
            <Button size="sm" onClick={refresh} loading={resource.state === "loading"}>
              <RefreshCw size={14} aria-hidden="true" /> Refresh
            </Button>
          </>
        }
      >
        Today's numbers and what needs attention first.
      </PageHeader>
      <div className="page-body">
        {resource.state === "idle" || resource.state === "loading" ? (
          <p className="live__none" aria-busy="true">Preparing the brief…</p>
        ) : resource.state === "error" ? (
          <div className="dash__error" role="alert">
            <p>{resource.message}</p>
            <Button size="sm" onClick={refresh}>
              <RefreshCw size={14} aria-hidden="true" /> Try again
            </Button>
          </div>
        ) : (
          <BriefBody data={resource.data} />
        )}
      </div>
    </>
  );
}

function BriefBody({ data }: { data: BriefData }) {
  const f = data.facts;
  // Each number opens the complaints behind it. No overdue or emergency filter exists: "Most urgent first"
  // ranks emergencies, then overdue complaints, at the top (officer.rank_key).
  const tiles: [string, number, string][] = [
    [`New (${f.window_hours} h)`, f.new, "/complaints"],
    ["Emergencies", f.new_emergencies, "/complaints?sort=priority"],
    ["Fixed", f.fixed, "/complaints?status=fixed"],
    ["Open now", f.open, "/complaints?status=open"],
    ["Past deadline", f.overdue, "/complaints?sort=priority"],
  ];
  return (
    <div className="brief">
      <Card title="Summary">
        <p className="brief__summary">{data.summary_en}</p>
        {data.summary_local && <p className="brief__local" lang="kn">{data.summary_local}</p>}
        <p className="brief__source">
          <Badge tone={data.source === "gemma" ? "success" : "neutral"}>{data.source === "gemma" ? "Written by Gemma, numbers checked" : "Plain summary"}</Badge>
          {data.rejected_numbers.length > 0 && " Gemma's wording used a number that is not in the data, so the plain summary is shown."}
        </p>
      </Card>
      <ul className="tiles" aria-label="Today's numbers">
        {tiles.map(([label, value, to]) => (
          <li key={label}>
            <Link to={to} className="tile tile--link" aria-label={`${value} ${label}: show these complaints`}>
              <span className="tile__value">{value}</span>
              <span className="tile__label">{label}</span>
            </Link>
          </li>
        ))}
      </ul>
      {f.worst_office && (
        <Card title="Most overdue office">
          <p>
            <strong>{f.worst_office.office}</strong>: {f.worst_office.overdue} of its {f.worst_office.open} open complaints are past
            the {f.worst_office.deadline_days}-day deadline. <Link to="/complaints?sort=priority">See the most urgent first</Link>
          </p>
        </Card>
      )}
      {f.clusters.length > 0 && (
        <Card title="Open complaints close together">
          <ul className="brief__clusters">
            {f.clusters.map((c, i) => (
              <li key={i}>
                <Link to={`/complaints?category=${encodeURIComponent(c.category)}`}>
                  {c.complaints} open {CATEGORY[c.category]?.label.toLowerCase() ?? c.category} complaints near {c.area}
                </Link>{" "}
                ({c.reports} reports)
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

/** The complaints as a spreadsheet, for forwarding to official systems. The officer's sign-in travels in a header, so it is fetched then saved. */
function DownloadCsv() {
  const [busy, setBusy] = useState(false);
  async function download() {
    setBusy(true);
    try {
      const url = URL.createObjectURL(await getBlob("/api/export.csv"));
      const a = document.createElement("a");
      a.href = url;
      a.download = "citizens-voice-complaints.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(userMessage(err, "Couldn't download the spreadsheet. Try again."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Button size="sm" onClick={download} loading={busy}>
      <Download size={14} aria-hidden="true" /> Download CSV
    </Button>
  );
}
