import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { ComplaintPage } from "./ComplaintPage";
import { setOfficerToken } from "./lib/officer";

vi.mock("./components/ComplaintMap", () => ({ ComplaintMap: () => <div data-testid="map" /> }));

const DETAIL = {
  tracking_id: "CV-1004", status: "open", category: "road", summary_en: "Potholes in front of St. Mary's School",
  summary_local: null, language: "kn-IN", urgency: 3, is_emergency: false, is_incomplete: false,
  place_name: "St. Mary's School", landmark: null, lat: 13.04, lon: 77.51, since_when: "5 years",
  report_count: 1, channel: "telegram", caller_last4: null, created_at: "2026-10-10T10:00:00+00:00",
  department: "bbmp", sensitive: false, office: "BBMP (city corporation)", deadline_days: 7, overdue: true,
  escalated: true, priority: 60, priority_why: "urgency 3 · open 7 days · overdue by 1 day",
  timeline: [
    { status: "open", by: "system", note: null, at: "2026-10-10T10:00:00+00:00" },
    { status: "in_progress", by: "officer", note: "Crew sent", at: "2026-10-11T10:00:00+00:00" },
  ],
  photos: [{ id: 9, kind: "fix", verdict: { looks_fixed: "no", reason: "The pothole is still visible" }, at: "2026-10-12T10:00:00+00:00" }],
  transcript: [], steps: [],
};

const calls: { path: string; init?: RequestInit }[] = [];

function mockFetch(routes: Record<string, unknown>) {
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      calls.push({ path, init });
      const body = routes[path];
      if (body === undefined) return new Response("{}", { status: 404 });
      return new Response(JSON.stringify(body), { status: body === "denied" ? 401 : 200 });
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  setOfficerToken(null);
});

test("anyone can see where a complaint is: office, deadline, timeline and Gemma's photo check", async () => {
  mockFetch({ "/api/complaints/CV-1004": DETAIL });
  render(<ComplaintPage trackingId="CV-1004" />);
  expect(await screen.findByText("BBMP (city corporation)")).toBeInTheDocument();
  expect(screen.getByText("Overdue · escalated")).toBeInTheDocument();
  expect(screen.getByText(/7 days from filing — overdue/)).toBeInTheDocument();
  expect(screen.getByText("Crew sent")).toBeInTheDocument();
  expect(screen.getByText("Photo check")).toBeInTheDocument();
  expect(screen.getByText("not fixed")).toBeInTheDocument();
  expect(screen.getByText("The pothole is still visible")).toBeInTheDocument();
  expect(screen.getByText(/^Telegram/)).toBeInTheDocument();
  expect(screen.queryByText("Officer actions")).not.toBeInTheDocument();
});

test("a second person's report shows their own details and words, not only the first caller's", async () => {
  // Tester's report, 17 Oct: a Telegram report ("10 years") was added to a phone complaint ("5 years");
  // the page showed only the phone call, so it looked like the chat had been made up.
  const second = {
    channel: "telegram", language: "en-IN", caller_last4: null, summary_en: "Potholes near St. Mary's School for ten years",
    summary_local: null, place_name: "St. Mary's School", landmark: null, since_when: "10 years",
    created_at: "2026-10-17T13:38:00+00:00",
    transcript: [{ speaker: "caller", text: "pothole near St. Mary's school, ten years", language: "en-IN", at: "2026-10-17T13:37:00+00:00" }],
  };
  mockFetch({ "/api/complaints/CV-1004": { ...DETAIL, channel: "phone", report_count: 2, linked_reports: [second] } });
  render(<ComplaintPage trackingId="CV-1004" />);
  expect(await screen.findByText("Also reported by 1 more person")).toBeInTheDocument();
  expect(screen.getByText("First reported by")).toBeInTheDocument();
  expect(screen.getByText("10 years")).toBeInTheDocument();
  expect(screen.getByText(/Telegram · English/)).toBeInTheDocument();
  expect(screen.getByText("pothole near St. Mary's school, ten years")).toBeInTheDocument();
});

test("the photo check shows both photos side by side and Gemma's comparison", async () => {
  const photos = [
    { id: 3, kind: "citizen", at: "2026-10-10T10:00:00+00:00",
      verdict: { is_civic_problem: true, what_i_see: "A deep pothole beside a blue wall", severity: 4 } },
    { id: 9, kind: "fix", at: "2026-10-12T10:00:00+00:00",
      verdict: { looks_fixed: "yes", reason: "Fresh asphalt where the pothole was", same_place_likely: true,
                 matching: ["blue wall", "neem tree"], differences: ["pothole filled"], confidence: "high",
                 compared_with_citizen_photo: true, model: "gemma-4-31b-it" } },
  ];
  mockFetch({ "/api/complaints/CV-1004": { ...DETAIL, status: "fixed", photos } });
  render(<ComplaintPage trackingId="CV-1004" />);
  expect(await screen.findByText("Photo check")).toBeInTheDocument();
  expect(screen.getByAltText("Photo sent by the citizen")).toHaveAttribute("src", "/api/complaints/CV-1004/photos/3");
  expect(screen.getByAltText("Photo sent by the officer after the fix")).toHaveAttribute("src", "/api/complaints/CV-1004/photos/9");
  expect(screen.getByText("Gemma saw: A deep pothole beside a blue wall")).toBeInTheDocument();
  expect(screen.getByText("Severity 4 of 5")).toBeInTheDocument();
  expect(screen.getByText("looks fixed")).toBeInTheDocument();
  expect(screen.getByText("Yes")).toBeInTheDocument();
  expect(screen.getByText("blue wall · neem tree")).toBeInTheDocument();
  expect(screen.getByText("pothole filled")).toBeInTheDocument();
  expect(screen.getByText("high")).toBeInTheDocument();
  expect(screen.getByText("gemma-4-31b-it")).toBeInTheDocument();
  expect(screen.getByText("Gemma's check is advice. The citizen's answer decides.")).toBeInTheDocument();
  expect(screen.queryByText("No fix photo · the citizen's answer decides")).not.toBeInTheDocument();
});

test("without a citizen photo the check says there was nothing to compare", async () => {
  // An old verdict (before 18 Oct): no matching, differences, confidence or compared flag.
  mockFetch({ "/api/complaints/CV-1004": DETAIL });
  render(<ComplaintPage trackingId="CV-1004" />);
  expect(await screen.findByText("No citizen photo to compare")).toBeInTheDocument();
  expect(screen.queryByText("What matches")).not.toBeInTheDocument();
  expect(screen.queryByText("Confidence")).not.toBeInTheDocument();
});

test("a sensitive report hides the conversation from the public", async () => {
  mockFetch({ "/api/complaints/CV-1004": { ...DETAIL, sensitive: true } });
  render(<ComplaintPage trackingId="CV-1004" />);
  expect(await screen.findByText(/visible only to officers/)).toBeInTheDocument();
});

test("an officer signs in, sees the actions, and the token goes with each request", async () => {
  mockFetch({ "/api/complaints/CV-1004": DETAIL, "/api/officer/login": { token: "123.abc" }, "/api/complaints/CV-1004/status": DETAIL });
  render(<ComplaintPage trackingId="CV-1004" />);
  fireEvent.click(await screen.findByRole("button", { name: /Officer sign-in/ }));
  fireEvent.change(screen.getByLabelText("Passcode"), { target: { value: "secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Officer actions")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Start work/ }));
  await screen.findByText("Marked in progress.");
  const sent = calls.find((c) => c.path === "/api/complaints/CV-1004/status");
  expect((sent?.init?.headers as Record<string, string>).Authorization).toBe("Bearer 123.abc");
  expect(JSON.parse(String(sent?.init?.body))).toEqual({ status: "in_progress", note: null });
});

test("an officer can mark fixed without a photo, and the page says no photo was given", async () => {
  // 18 Oct: not every fix can be photographed (a pension paid); the photo is optional.
  setOfficerToken("123.abc");
  mockFetch({ "/api/complaints/CV-1004": DETAIL, "/api/complaints/CV-1004/fixed": { ...DETAIL, status: "fixed" } });
  render(<ComplaintPage trackingId="CV-1004" />);
  expect(await screen.findByText("Shown on the public timeline and sent to the citizen.")).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("button", { name: "Mark fixed" }));
  expect(await screen.findByText("Marked fixed without a photo; the citizen will be asked to confirm.")).toBeInTheDocument();
  const sent = calls.find((c) => c.path === "/api/complaints/CV-1004/fixed");
  expect((sent?.init?.body as FormData).has("photo")).toBe(false);
});

test("a complaint fixed without a photo says so publicly", async () => {
  mockFetch({ "/api/complaints/CV-1004": { ...DETAIL, status: "fixed", photos: [] } });
  render(<ComplaintPage trackingId="CV-1004" />);
  expect(await screen.findByText("No fix photo · the citizen's answer decides")).toBeInTheDocument();
});

test("a wrong passcode says so and stays signed out", async () => {
  mockFetch({ "/api/complaints/CV-1004": DETAIL, "/api/officer/login": "denied" });
  render(<ComplaintPage trackingId="CV-1004" />);
  fireEvent.click(await screen.findByRole("button", { name: /Officer sign-in/ }));
  fireEvent.change(screen.getByLabelText("Passcode"), { target: { value: "wrong" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("That passcode is wrong.")).toHaveAttribute("role", "alert");
  expect(screen.queryByText("Officer actions")).not.toBeInTheDocument();
});
