import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { CV1004, FakeEventSource, NEWEST, PRIORITY, config, fetched, healthy, mockFetch, renderAt } from "./test-utils";

// The test browser can't draw Leaflet maps; the map gets its own manual check.
vi.mock("./components/ComplaintMap", () => ({
  ComplaintMap: ({ selected, complaints }: { selected?: string | null; complaints: unknown[] }) => (
    <div data-testid="map" data-count={complaints.length}>{selected ?? "none"}</div>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

test("the Live desk shows saved complaints, healthy status and selects one on the map", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [CV1004] });
  renderAt("/");
  expect(await screen.findByText("All systems working")).toBeInTheDocument();
  expect(await screen.findByText("Potholes in front of St. Mary's School")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Live desk" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /CV-1004/ }));
  expect(screen.getByTestId("map")).toHaveTextContent("CV-1004");
  expect(screen.getByRole("link", { name: "Details" })).toHaveAttribute("href", "/c/CV-1004");
});

test("empty list says how to file the first complaint", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [] });
  renderAt("/");
  expect(await screen.findByText("No complaints yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "080 6535 6055" })).toHaveAttribute("href", "tel:+918065356055");
});

test("says the database is unreachable instead of pretending all is well", async () => {
  mockFetch({ "/health": { status: "degraded", db: "down", version: "0.1.0" }, "/api/config": {}, [NEWEST]: [] });
  renderAt("/");
  expect(await screen.findByText("Database unreachable")).toBeInTheDocument();
});

test("a network failure gives a plain-language message and a retry", async () => {
  mockFetch({ "/health": new TypeError("x"), "/api/config": new TypeError("x"), [NEWEST]: new TypeError("x") });
  renderAt("/");
  expect(await screen.findByText("Server unreachable")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server");
});

test("a live call appears as it happens, and a filed complaint joins the list", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [], "/api/complaints/CV-1004": CV1004 });
  renderAt("/");
  expect(await screen.findByText("Waiting for a call")).toBeInTheDocument();
  act(() => {
    FakeEventSource.last.push({ type: "call_started", call_id: 5, channel: "phone" });
    FakeEventSource.last.push({
      type: "turn", call_id: 5, channel: "phone", caller: "ಹೌದು", reply: "Tracking ID C V 1 0 0 4",
      steps: [{ kind: "tool_call", tool: "file_complaint" }], complaint: { tracking_id: "CV-1004" },
    });
  });
  expect(await screen.findByText("Live call — phone")).toBeInTheDocument();
  expect(screen.getByText("Tracking ID C V 1 0 0 4")).toBeInTheDocument();
  expect(screen.getByText("Filing the complaint")).toBeInTheDocument();
  expect(await screen.findByText("Potholes in front of St. Mary's School")).toBeInTheDocument();
  expect(screen.getByTestId("map")).toHaveAttribute("data-count", "1"); // and its pin is on the same screen
});

test("each complaint says which office it went to; overdue and emergency ones are flagged", async () => {
  const late = { ...CV1004, tracking_id: "CV-1005", overdue: true, escalated: true };
  const wire = { ...CV1004, tracking_id: "CV-1006", is_emergency: true, urgency: 5 };
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [CV1004, late, wire] });
  renderAt("/");
  expect(await screen.findAllByText("To: BBMP (city corporation)")).toHaveLength(3);
  expect(screen.getByText("Overdue")).toBeInTheDocument();
  expect(screen.getByText(/1 past the office deadline/)).toBeInTheDocument();
  expect(screen.getByText(/1 open emergency report/)).toBeInTheDocument();
});

test("most urgent first shows the server's order untouched, with the working behind it", async () => {
  const wire = { ...CV1004, tracking_id: "CV-1006", summary_en: "Live wire down", is_emergency: true, priority: 8, priority_why: "emergency" };
  const pothole = { ...CV1004, tracking_id: "CV-1007", summary_en: "Old pothole", priority: 83, priority_why: "urgency 4 · 4 reports" };
  // The browser must not re-rank: whatever order the server sends (the rule lives in officer.rank_key) is the order shown.
  // This order is deliberately NOT what a score-only sort would give, to prove nothing is re-sorted here.
  const fetchMock = mockFetch({
    "/health": healthy, "/api/config": config, [NEWEST]: [wire, pothole], [PRIORITY]: [pothole, wire],
  });
  renderAt("/complaints");
  await screen.findByText("Old pothole");
  expect(screen.queryByText(/Why here/)).not.toBeInTheDocument();
  expect(fetched(fetchMock, PRIORITY)).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "Most urgent first" }));
  expect(await screen.findByText("Why here: urgency 4 · 4 reports")).toBeInTheDocument();
  expect(fetched(fetchMock, PRIORITY)).toBe(1);
  const order = screen.getAllByRole("button", { name: /CV-100/ }).map((b) => b.textContent);
  expect(order[0]).toContain("Old pothole");
  expect(order[1]).toContain("Live wire down");
  expect(window.location.search).toBe("?sort=priority");
});

test("the Offices page counts each office's open and overdue complaints", async () => {
  mockFetch({
    "/health": healthy, "/api/config": config, [NEWEST]: [],
    "/api/scorecard": [{ department: "bescom", office: "BESCOM (electricity)", filed: 3, open: 2, fixed: 1, overdue: 1, deadline_days: 2, median_days_to_fix: 1.5 }],
  });
  renderAt("/offices");
  expect(await screen.findByText("Office scorecard")).toBeInTheDocument();
  expect(screen.getByText("deadline 2 days")).toBeInTheDocument();
  expect(screen.getByText("1.5 d")).toBeInTheDocument();
});
