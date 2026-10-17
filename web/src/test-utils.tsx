import { render } from "@testing-library/react";
import { vi, type Mock } from "vitest";
import { Shell } from "./Shell";

export const CV1004 = {
  tracking_id: "CV-1004", status: "open", category: "road", summary_en: "Potholes in front of St. Mary's School",
  summary_local: null, language: "kn-IN", urgency: 3, is_emergency: false, is_incomplete: false,
  place_name: "St. Mary's School", landmark: null, lat: 13.04, lon: 77.51, since_when: "5 years",
  report_count: 1, channel: "phone", caller_last4: "2659", created_at: new Date().toISOString(),
  department: "bbmp", sensitive: false, office: "BBMP (city corporation)", deadline_days: 7, overdue: false,
  escalated: false, priority: 15, priority_why: "urgency 3 · open 0 days",
};

export const healthy = { status: "ok", db: "ok", version: "0.1.0" };
export const config = { helpline_number: "+918065356055", helpline_display: "080 6535 6055" };
export const NEWEST = "/api/complaints?sort=newest";
export const PRIORITY = "/api/complaints?sort=priority";

/** Answers each address with the body given for it; an Error is a network failure, anything unlisted is a 404. */
export function mockFetch(routes: Record<string, unknown | Error>): Mock {
  const fetchMock = vi.fn(async (path: string) => {
    const body = routes[path];
    if (body instanceof Error) throw body;
    if (body === undefined) return new Response("{}", { status: 404 });
    return new Response(JSON.stringify(body), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** How many times the page asked for this address. */
export function fetched(fetchMock: Mock, path: string): number {
  return fetchMock.mock.calls.filter((c) => c[0] === path).length;
}

/** A stand-in for the browser's EventSource that the test can push events through. */
export class FakeEventSource {
  static last: FakeEventSource;
  static count = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  constructor() {
    FakeEventSource.last = this;
    FakeEventSource.count += 1;
  }
  close() {}
  push(event: object) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

/** The dashboard, opened at an address (the page picks its screen from the address bar). */
export function renderAt(address: string) {
  window.history.pushState(null, "", address);
  return render(<Shell />);
}
