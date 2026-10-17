import { ComplaintMap } from "../components/ComplaintMap";
import { PageHeader } from "../components/PageHeader";
import { CATEGORY, passes } from "../lib/complaints";
import { useSearchParams } from "../lib/router";
import { useShell } from "../ShellContext";

/** The whole map, filled to the page, narrowed by the same Category filter as the list. */
export function MapPage() {
  const { list, selected, select } = useShell();
  const [params, setParams] = useSearchParams();
  const category = params.get("category") ?? "";
  const items = list.state === "ok" ? list.items : [];
  const shown = items.filter((c) => passes(c, { category }));
  const unplaced = shown.filter((c) => c.lat == null || c.lon == null).length;

  const counts: Record<string, number> = {};
  for (const c of items) counts[c.category] = (counts[c.category] ?? 0) + 1;
  const categories = Object.keys(CATEGORY).filter((k) => counts[k] || k === category);

  return (
    <>
      <PageHeader
        title="Map"
        actions={
          <select aria-label="Category" className="input filters__select" value={category}
            onChange={(e) => setParams({ category: e.target.value || null })}>
            <option value="">All categories</option>
            {categories.map((k) => <option key={k} value={k}>{`${CATEGORY[k].label} (${counts[k] ?? 0})`}</option>)}
          </select>
        }
      >
        {list.state === "loading" ? "Loading complaints…" : `${shown.length - unplaced} complaint${shown.length - unplaced === 1 ? "" : "s"} on the map`}
        {unplaced > 0 ? `, ${unplaced} without an exact place` : ""}. Pins are coloured by urgency.
      </PageHeader>
      <div className="mapview">
        <div className="mapview__map">
          <ComplaintMap complaints={shown} selected={selected} onSelect={select} />
        </div>
      </div>
    </>
  );
}
