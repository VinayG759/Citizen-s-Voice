import { Building2 } from "lucide-react";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import type { ScoreRow } from "../ShellContext";

/** "Which office is keeping its promises?" Counted by the server, not guessed by the AI. */
export function Scorecard({ rows }: { rows: ScoreRow[] | null }) {
  if (!rows || rows.length === 0)
    return (
      <Card title="Office scorecard">
        <EmptyState icon={<Building2 size={28} />} title="No complaints to count yet">
          <p>Once complaints are filed, each office's open, overdue and fixed counts appear here.</p>
        </EmptyState>
      </Card>
    );
  return (
    <Card title="Office scorecard">
      <div className="score-wrap">
      <table className="score">
        <thead>
          <tr>
            <th scope="col">Office</th>
            <th scope="col">Filed</th>
            <th scope="col">Open</th>
            <th scope="col">Overdue</th>
            <th scope="col">Fixed</th>
            <th scope="col">Typical fix</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.department}>
              <th scope="row">
                {r.office}
                <span className="score__deadline">
                  deadline {r.deadline_days} day{r.deadline_days > 1 ? "s" : ""}
                </span>
              </th>
              <td>{r.filed}</td>
              <td>{r.open}</td>
              <td className={r.overdue > 0 ? "score__bad" : undefined}>{r.overdue}</td>
              <td>{r.fixed}</td>
              <td>{r.median_days_to_fix === null ? "—" : `${r.median_days_to_fix} d`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </Card>
  );
}
