import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { CV1004, FakeEventSource, NEWEST, PRIORITY, config, fetched, healthy, mockFetch, renderAt } from "./test-utils";

vi.mock("./components/ComplaintMap", () => ({
  ComplaintMap: ({ selected, complaints }: { selected?: string | null; complaints: unknown[] }) => (
    <div data-testid="map" data-count={complaints.length}>{selected ?? "none"}</div>
  ),
}));

beforeEach(() => {
  FakeEventSource.count = 0;
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

const EMERGING = "/api/emerging?headlines=true";
const water = (n: number) => ({ ...CV1004, tracking_id: `CV-${2000 + n}`, category: "water", department: "bwssb", summary_en: `No water ${n}` });
const road = { ...CV1004, tracking_id: "CV-3000", summary_en: "Pothole on the main road" };
const emergingBody = {
  generated_at: new Date().toISOString(), windows_hours: [24], history_days: 9,
  items: [{ kind: "spike", category: "water", headline: "4 water reports in 24 hours (usually about 1)", headline_by: "template",
            reports: 4, window_hours: 24, usual: 1, times_usual: 4, complaint_ids: ["CV-2001", "CV-2002"] }],
};

test("switching page changes the screen and the address without a reload, and keeps the live connection", async () => {
  const fetchMock = mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [CV1004], "/api/scorecard": [] });
  renderAt("/");
  await screen.findByRole("heading", { name: "Live desk" });
  expect(FakeEventSource.count).toBe(1);

  fireEvent.click(screen.getByRole("link", { name: "Offices" }));
  expect(await screen.findByRole("heading", { name: "Offices" })).toBeInTheDocument();
  expect(window.location.pathname).toBe("/offices");
  expect(screen.getByRole("link", { name: "Offices" })).toHaveAttribute("aria-current", "page");

  fireEvent.click(screen.getByRole("link", { name: "Complaints" }));
  expect(await screen.findByText("Potholes in front of St. Mary's School")).toBeInTheDocument();

  // Nothing was fetched again and no second live connection was opened: the page never reloaded.
  expect(fetched(fetchMock, "/health")).toBe(1);
  expect(fetched(fetchMock, NEWEST)).toBe(1);
  expect(FakeEventSource.count).toBe(1);

  await act(async () => window.history.back()); // the browser's Back button
  await waitFor(() => expect(screen.getByRole("heading", { name: "Offices" })).toBeInTheDocument());
});

test("a live call survives a change of page", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [], "/api/scorecard": [] });
  renderAt("/");
  await screen.findByText("Waiting for a call");
  act(() => {
    FakeEventSource.last.push({ type: "call_started", call_id: 7, channel: "phone" });
    FakeEventSource.last.push({ type: "turn", call_id: 7, channel: "phone", caller: "hello", reply: "Which area?", steps: [] });
  });
  await screen.findByText("Which area?");
  fireEvent.click(screen.getByRole("link", { name: "Offices" }));
  await screen.findByRole("heading", { name: "Offices" });
  fireEvent.click(screen.getByRole("link", { name: "Live desk" }));
  expect(await screen.findByText("Which area?")).toBeInTheDocument();
});

test("the Category filter narrows the list, counts what it will show, and lives in the address", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [water(1), water(2), road] });
  renderAt("/complaints");
  expect(await screen.findByText("Complaints (3)")).toBeInTheDocument();
  const select = screen.getByLabelText("Category");
  expect(within(select).getByRole("option", { name: "Water (2)" })).toBeInTheDocument();
  expect(within(select).getByRole("option", { name: "Road (1)" })).toBeInTheDocument();
  expect(within(select).queryByRole("option", { name: /Noise/ })).not.toBeInTheDocument(); // none of those: not offered

  fireEvent.change(select, { target: { value: "water" } });
  expect(await screen.findByText("Complaints (2 of 3)")).toBeInTheDocument();
  expect(screen.queryByText("Pothole on the main road")).not.toBeInTheDocument();
  expect(screen.getByText("No water 1")).toBeInTheDocument();
  expect(window.location.search).toBe("?category=water");

  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(await screen.findByText("Complaints (3)")).toBeInTheDocument();
  expect(window.location.search).toBe("");
});

test("opening a filtered link shows that view, and a filter nothing matches says so", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [water(1), road] });
  renderAt("/complaints?category=road");
  expect(await screen.findByText("Pothole on the main road")).toBeInTheDocument();
  expect(screen.queryByText("No water 1")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Category")).toHaveValue("road");
  fireEvent.change(screen.getByLabelText("Office"), { target: { value: "bwssb" } });
  expect(await screen.findByText("No complaints match these filters")).toBeInTheDocument();
});

test("the Map page narrows its pins by the same Category filter", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [water(1), water(2), road] });
  renderAt("/map");
  await waitFor(() => expect(screen.getByTestId("map")).toHaveAttribute("data-count", "3"));
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "water" } });
  await waitFor(() => expect(screen.getByTestId("map")).toHaveAttribute("data-count", "2"));
  expect(window.location.search).toBe("?category=water");
});

test("Emerging issues is fetched once when the page opens, never on live events, and again only on Refresh", async () => {
  const fetchMock = mockFetch({
    "/health": healthy, "/api/config": config, [NEWEST]: [], "/api/scorecard": [], [EMERGING]: emergingBody,
    "/api/complaints/CV-2001": water(1),
  });
  renderAt("/emerging");
  expect(await screen.findByText("4 water reports in 24 hours (usually about 1)")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "CV-2001" })).toHaveAttribute("href", "/c/CV-2001");
  expect(fetched(fetchMock, EMERGING)).toBe(1);

  // Calls, filings and updates arrive over the live connection: none of them may ask Gemma for headlines.
  act(() => {
    FakeEventSource.last.push({ type: "turn", call_id: 1, channel: "phone", caller: "a", reply: "b", steps: [], complaint: { tracking_id: "CV-2001" } });
    FakeEventSource.last.push({ type: "complaint_updated", tracking_id: "CV-2001", status: "fixed" });
    FakeEventSource.last.push({ type: "call_ended", call_id: 1, outcome: "filed" });
  });
  await waitFor(() => expect(fetched(fetchMock, "/api/complaints/CV-2001")).toBeGreaterThan(0));
  expect(fetched(fetchMock, EMERGING)).toBe(1);

  // Leaving and coming back keeps what was loaded.
  fireEvent.click(screen.getByRole("link", { name: "Offices" }));
  await screen.findByRole("heading", { name: "Offices" });
  fireEvent.click(screen.getByRole("link", { name: "Emerging issues" }));
  expect(await screen.findByText("4 water reports in 24 hours (usually about 1)")).toBeInTheDocument();
  expect(fetched(fetchMock, EMERGING)).toBe(1);

  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() => expect(fetched(fetchMock, EMERGING)).toBe(2));
});

test("Emerging issues is not fetched at all while another page is open", async () => {
  const fetchMock = mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [CV1004], "/api/scorecard": [], [EMERGING]: emergingBody });
  renderAt("/");
  await screen.findByText("Potholes in front of St. Mary's School");
  expect(fetched(fetchMock, EMERGING)).toBe(0);
});

test("the Morning brief does not call the server when nobody is signed in, and asks for a sign-in", async () => {
  const fetchMock = mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [], "/api/scorecard": [], "/api/brief": {} });
  renderAt("/brief");
  expect(await screen.findByText("Officers only")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Download CSV/ })).not.toBeInTheDocument();
  expect(fetched(fetchMock, "/api/brief")).toBe(0);
});

test("a signed-in officer gets the brief once, and a spreadsheet button", async () => {
  sessionStorage.setItem("cv-officer-token", "test-token");
  const brief = {
    facts: { window_hours: 24, new: 5, new_emergencies: 1, fixed: 2, open: 9, overdue: 3,
             worst_office: { office: "BBMP (city corporation)", overdue: 3, open: 6, deadline_days: 7 }, clusters: [] },
    summary_en: "In the last 24 hours: 5 new complaints.", summary_local: null, source: "template",
    numbers_checked: true, rejected_numbers: [],
  };
  const fetchMock = mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [], "/api/scorecard": [], "/api/brief": brief });
  renderAt("/brief");
  expect(await screen.findByText("In the last 24 hours: 5 new complaints.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Download CSV/ })).toBeInTheDocument();
  expect(within(screen.getByRole("list", { name: "Today's numbers" })).getByText("Past deadline")).toBeInTheDocument();
  expect(fetched(fetchMock, "/api/brief")).toBe(1);
});

test("each number on the brief opens the complaints behind it", async () => {
  sessionStorage.setItem("cv-officer-token", "test-token");
  const brief = {
    facts: { window_hours: 24, new: 5, new_emergencies: 1, fixed: 2, open: 9, overdue: 3, worst_office: null,
             clusters: [{ category: "water", area: "Jayanagar", complaints: 3, reports: 4 }] },
    summary_en: "In the last 24 hours: 5 new complaints.", summary_local: null, source: "template",
    numbers_checked: true, rejected_numbers: [],
  };
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [], "/api/scorecard": [], "/api/brief": brief });
  renderAt("/brief");
  const fixed = await screen.findByRole("link", { name: "2 Fixed: show these complaints" });
  expect(fixed).toHaveAttribute("href", "/complaints?status=fixed");
  expect(screen.getByRole("link", { name: "1 Emergencies: show these complaints" })).toHaveAttribute("href", "/emergencies");
  expect(screen.getByRole("link", { name: /open water complaints near Jayanagar/ })).toHaveAttribute("href", "/complaints?category=water");
  fireEvent.click(fixed);
  expect(window.location.pathname + window.location.search).toBe("/complaints?status=fixed");
});

test("the phone menu opens, closes on Escape and returns focus to its button", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [], "/api/scorecard": [] });
  renderAt("/");
  const open = screen.getByRole("button", { name: "Open menu" });
  fireEvent.click(open);
  const menu = screen.getByRole("dialog", { name: "Menu" });
  expect(within(menu).getByRole("link", { name: "Map" })).toBeInTheDocument();
  await waitFor(() => expect(within(menu).getByRole("button", { name: "Close menu" })).toHaveFocus());
  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Menu" })).not.toBeInTheDocument());
  expect(open).toHaveFocus();

  fireEvent.click(open);
  fireEvent.click(within(screen.getByRole("dialog", { name: "Menu" })).getByRole("link", { name: "Offices" }));
  expect(await screen.findByRole("heading", { name: "Offices" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "Menu" })).not.toBeInTheDocument(); // choosing a page closes it
});

test("a complaint filed while sorted by urgency appears, where the server ranks it", async () => {
  const wire = { ...CV1004, tracking_id: "CV-5000", summary_en: "Live wire down", is_emergency: true };
  const routes: Record<string, unknown> = {
    "/health": healthy, "/api/config": config, [NEWEST]: [road], [PRIORITY]: [road], "/api/complaints/CV-5000": wire,
  };
  const fetchMock = mockFetch(routes);
  renderAt("/complaints?sort=priority");
  expect(await screen.findByText("Pothole on the main road")).toBeInTheDocument();
  expect(fetched(fetchMock, PRIORITY)).toBe(1);

  routes[PRIORITY] = [wire, road]; // the server now ranks the new emergency first
  act(() => {
    FakeEventSource.last.push({
      type: "turn", call_id: 9, channel: "phone", caller: "a", reply: "b", steps: [], complaint: { tracking_id: "CV-5000" },
    });
  });
  expect(await screen.findByText("Live wire down")).toBeInTheDocument();
  expect(fetched(fetchMock, PRIORITY)).toBe(2); // asked again because the list changed
  const order = screen.getAllByRole("button", { name: /CV-/ }).map((b) => b.textContent);
  expect(order[0]).toContain("Live wire down");
});


test("the Emergencies page lists open emergencies only, danger to life before resource loss", async () => {
  const wire = { ...CV1004, tracking_id: "CV-1060", category: "electricity", summary_en: "Live wire on the road",
    is_emergency: true, emergency_kind: "danger", priority: 90 };
  const pipe = { ...CV1004, tracking_id: "CV-1061", category: "water", summary_en: "Burst water main",
    is_emergency: true, emergency_kind: "loss", priority: 75 };
  const fixed = { ...wire, tracking_id: "CV-1062", summary_en: "Fixed wire", status: "fixed" };
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [pipe, CV1004, fixed, wire] });
  renderAt("/emergencies");
  expect(await screen.findByText("Danger to life (1)")).toBeInTheDocument();
  expect(screen.getByText("Resource loss (1)")).toBeInTheDocument();
  expect(screen.getByText("Live wire on the road")).toBeInTheDocument();
  expect(screen.getByText("Burst water main")).toBeInTheDocument();
  expect(screen.queryByText("Potholes in front of St. Mary's School")).not.toBeInTheDocument();
  expect(screen.queryByText("Fixed wire")).not.toBeInTheDocument();
});

test("the Emergencies page says so when there are none", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, [NEWEST]: [CV1004] });
  renderAt("/emergencies");
  expect(await screen.findByText("No open emergencies")).toBeInTheDocument();
});
