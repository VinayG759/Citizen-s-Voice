/** Gemma's steps (tool calls, results, decisions) as one plain sentence each. Shared by the
    try-it page and the dashboard. */

export type ClerkEvent = {
  kind: "thought" | "tool_call" | "tool_result" | "decision";
  tool?: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  text?: string;
  provider?: string;
  ms?: number;
};

/** One plain sentence per step. */
export function describe(e: ClerkEvent): string {
  if (e.kind === "thought") return `Thinking: ${e.text}`;
  if (e.kind === "decision") return e.text === "spoke" ? `Replied${e.ms ? ` in ${(e.ms / 1000).toFixed(1)} s` : ""}` : (e.text ?? "Decided");
  if (e.kind === "tool_call") {
    if (e.tool === "find_place") return `Looking up “${e.args?.query}”${e.args?.area ? ` near ${e.args.area}` : ""}`;
    if (e.tool === "file_complaint") return "Filing the complaint";
    if (e.tool === "get_complaint_status") return `Checking complaint ${e.args?.tracking_id}`;
    if (e.tool === "raise_emergency") return `EMERGENCY: ${e.args?.reason}`;
    return `Using ${e.tool}`;
  }
  const r = e.result ?? {};
  if (e.tool === "find_place") {
    const m = (r.matches as { name: string }[] | undefined) ?? [];
    return m.length ? `Found: ${m.map((x) => x.name).join(", ")}` : "No matching place — will ask for a landmark";
  }
  if (e.tool === "file_complaint")
    return r.ok ? `Filed as ${r.tracking_id}` : `Not filed yet: ${((r.fix as string[]) ?? []).join("; ")}`;
  if (e.tool === "get_complaint_status") return r.found ? `${r.tracking_id} is ${String(r.status).replace("_", " ")}` : "No such complaint";
  if (e.tool === "raise_emergency") return "Marked as an emergency — flagged on the dashboard once filed";
  return "Done";
}
