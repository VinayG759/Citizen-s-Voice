import { Phone, RefreshCw, SearchX } from "lucide-react";
import { Button } from "./Button";
import { ComplaintRow, ListSkeleton } from "./ComplaintRow";
import { EmptyState } from "./EmptyState";
import { useShell, type List } from "../ShellContext";
import type { Complaint } from "../lib/complaints";

type Props = {
  /** The complaints to show (already filtered and ordered by the page). */
  items: Complaint[];
  showWhy?: boolean;
  /** True when the page is narrowing the list: an empty result then means "nothing matches", not "no complaints". */
  filtered?: boolean;
  onClear?: () => void;
  /** Where loading and error come from. Default: the shell's list. */
  source?: List;
};

/** The complaint list with its loading, error and empty states, shared by the Live desk and Complaints. */
export function ComplaintFeed({ items, showWhy = false, filtered = false, onClear, source }: Props) {
  const shell = useShell();
  const { reload, config, selected, select, fresh } = shell;
  const list = source ?? shell.list;

  if (list.state === "loading") return <ListSkeleton />;
  if (list.state === "error")
    return (
      <div className="dash__error" role="alert">
        <p>{list.message}</p>
        <Button size="sm" onClick={reload}>
          <RefreshCw size={14} aria-hidden="true" /> Try again
        </Button>
      </div>
    );
  if (items.length === 0 && filtered)
    return (
      <EmptyState icon={<SearchX size={32} />} title="No complaints match these filters">
        {onClear && (
          <Button size="sm" onClick={onClear}>
            Clear filters
          </Button>
        )}
      </EmptyState>
    );
  if (items.length === 0)
    return (
      <EmptyState icon={<Phone size={32} />} title="No complaints yet">
        <p>
          Call {config?.helpline_display ? <a href={`tel:${config.helpline_number}`}>{config.helpline_display}</a> : "the helpline"}{" "}
          or <a href="/try">talk to it in your browser</a>.
        </p>
      </EmptyState>
    );
  return (
    <ol className="feed">
      {items.map((c) => (
        <ComplaintRow
          key={c.tracking_id}
          c={c}
          selected={c.tracking_id === selected}
          fresh={fresh.has(c.tracking_id)}
          showWhy={showWhy}
          onSelect={() => select(c.tracking_id)}
        />
      ))}
    </ol>
  );
}
