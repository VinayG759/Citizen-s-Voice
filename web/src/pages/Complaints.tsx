import { useEffect, useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ComplaintFeed } from "../components/ComplaintFeed";
import { PageHeader } from "../components/PageHeader";
import { getJson, userMessage } from "../lib/api";
import {
  CATEGORY, CHANNEL_LABEL, FILTER_KEYS, OFFICES, STATUS_LABEL, passes, type Complaint, type Filters,
} from "../lib/complaints";
import { useSearchParams } from "../lib/router";
import { useShell, type List } from "../ShellContext";

/** Every complaint, narrowed by filters that live in the address (?category=water), so a link shows the same view. */
export function Complaints() {
  const { list, version } = useShell();
  const [params, setParams] = useSearchParams();
  const filters: Filters = {
    category: params.get("category") ?? "", office: params.get("office") ?? "",
    status: params.get("status") ?? "", channel: params.get("channel") ?? "",
  };
  const sort = params.get("sort") === "priority" ? "priority" : "newest";
  const active = FILTER_KEYS.some((k) => filters[k]);

  // "Most urgent first" is the server's order (officer.rank_key): the rule lives in one place. This page asks
  // for that list, and asks again whenever the list changes, so a new complaint lands where the server ranks it.
  const [ranked, setRanked] = useState<List>({ state: "loading" });
  useEffect(() => {
    if (sort !== "priority") return;
    let current = true;
    getJson<Complaint[]>("/api/complaints?sort=priority").then(
      (items) => current && setRanked({ state: "ok", items }),
      (err) => current && setRanked({ state: "error", message: userMessage(err, "Couldn't load complaints.") }),
    );
    return () => {
      current = false;
    };
  }, [sort, version]);

  const source = sort === "priority" ? ranked : list;
  const items = source.state === "ok" ? source.items : [];
  const shown = items.filter((c) => passes(c, filters)); // filters apply here, on top of the server's order

  // How many each category would show with the OTHER filters applied, so the numbers match what choosing it gives.
  const counts: Record<string, number> = {};
  for (const c of items) if (passes(c, filters, "category")) counts[c.category] = (counts[c.category] ?? 0) + 1;
  const categories = Object.keys(CATEGORY).filter((k) => counts[k] || k === filters.category);

  const clear = () => setParams({ category: null, office: null, status: null, channel: null });
  const select = (key: keyof Filters, label: string, options: [string, string][], all: string) => (
    <select aria-label={label} className="input filters__select" value={filters[key]}
      onChange={(e) => setParams({ [key]: e.target.value || null })}>
      <option value="">{all}</option>
      {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
    </select>
  );

  return (
    <>
      <PageHeader title="Complaints">Every complaint filed, with the office it was sent to.</PageHeader>
      <div className="page-body">
        <Card title={active ? `Complaints (${shown.length} of ${items.length})` : `Complaints (${items.length})`}>
          <div className="filters">
            {select("category", "Category", categories.map((k) => [k, `${CATEGORY[k].label} (${counts[k] ?? 0})`]), "All categories")}
            {select("office", "Office", Object.entries(OFFICES), "All offices")}
            {select("status", "Status", Object.entries(STATUS_LABEL), "Any status")}
            {select("channel", "Channel", Object.entries(CHANNEL_LABEL), "Any channel")}
            {active && (
              <Button size="sm" variant="ghost" onClick={clear}>
                Clear filters
              </Button>
            )}
          </div>
          <div className="sort" role="group" aria-label="Order complaints">
            <Button size="sm" variant={sort === "newest" ? "primary" : "ghost"} aria-pressed={sort === "newest"}
              onClick={() => setParams({ sort: null })}>
              Newest
            </Button>
            <Button size="sm" variant={sort === "priority" ? "primary" : "ghost"} aria-pressed={sort === "priority"}
              onClick={() => setParams({ sort: "priority" })}>
              Most urgent first
            </Button>
          </div>
          <ComplaintFeed items={shown} source={source} showWhy={sort === "priority"} filtered={active} onClear={clear} />
        </Card>
      </div>
    </>
  );
}
