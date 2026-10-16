import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { App } from "./App";

// The test browser can't draw Leaflet maps; the map gets its own manual check.
vi.mock("./components/ComplaintMap", () => ({
  ComplaintMap: ({ selected }: { selected?: string | null }) => <div data-testid="map">{selected ?? "none"}</div>,
}));

const CV1004 = {
  tracking_id: "CV-1004", status: "open", category: "road", summary_en: "Potholes in front of St. Mary's School",
  summary_local: null, language: "kn-IN", urgency: 3, is_emergency: false, is_incomplete: false,
  place_name: "St. Mary's School", landmark: null, lat: 13.04, lon: 77.51, since_when: "5 years",
  report_count: 1, channel: "phone", caller_last4: "2659", created_at: new Date().toISOString(),
};

function mockFetch(routes: Record<string, unknown | Error>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const body = routes[path];
      if (body instanceof Error) throw body;
      if (body === undefined) return new Response("{}", { status: 404 });
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
}

/** A stand-in for the browser's EventSource that the test can push events through. */
class FakeEventSource {
  static last: FakeEventSource;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  constructor() {
    FakeEventSource.last = this;
  }
  close() {}
  push(event: object) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

afterEach(() => vi.unstubAllGlobals());

const healthy = { status: "ok", db: "ok", version: "0.1.0" };
const config = { helpline_number: "+918065356055", helpline_display: "080 6535 6055" };

test("shows saved complaints, healthy status and selects one on the map", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, "/api/complaints": [CV1004] });
  render(<App />);
  expect(await screen.findByText("All systems working")).toBeInTheDocument();
  expect(await screen.findByText("Potholes in front of St. Mary's School")).toBeInTheDocument();
  expect(screen.getByText("Complaints (1)")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /CV-1004/ }));
  expect(screen.getByTestId("map")).toHaveTextContent("CV-1004");
  expect(screen.getByRole("link", { name: "Details" })).toHaveAttribute("href", "/c/CV-1004");
});

test("empty list says how to file the first complaint", async () => {
  mockFetch({ "/health": healthy, "/api/config": config, "/api/complaints": [] });
  render(<App />);
  expect(await screen.findByText("No complaints yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "080 6535 6055" })).toHaveAttribute("href", "tel:+918065356055");
});

test("says the database is unreachable instead of pretending all is well", async () => {
  mockFetch({ "/health": { status: "degraded", db: "down", version: "0.1.0" }, "/api/config": {}, "/api/complaints": [] });
  render(<App />);
  expect(await screen.findByText("Database unreachable")).toBeInTheDocument();
});

test("a network failure gives a plain-language message and a retry", async () => {
  mockFetch({ "/health": new TypeError("x"), "/api/config": new TypeError("x"), "/api/complaints": new TypeError("x") });
  render(<App />);
  expect(await screen.findByText("Server unreachable")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server");
});

test("a live call appears as it happens, and a filed complaint joins the list", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  mockFetch({ "/health": healthy, "/api/config": config, "/api/complaints": [], "/api/complaints/CV-1004": CV1004 });
  render(<App />);
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
});
