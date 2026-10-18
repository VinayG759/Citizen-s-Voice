import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { TryPage } from "./TryPage";
import { describe as describeStep } from "./lib/steps";

afterEach(() => vi.unstubAllGlobals());

function mockServer(turn: unknown | number) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      if (path === "/api/try/start")
        return new Response(JSON.stringify({ session_id: "s1", greeting: "ನಮಸ್ಕಾರ", greeting_audio: null }));
      if (path === "/api/try/speak") return new Response("", { status: 404 }); // jsdom can't play audio
      if (path === "/api/try/contact") return new Response(JSON.stringify({ ok: true, last4: "2345" }));
      if (typeof turn === "number") return new Response("{}", { status: turn });
      return new Response(JSON.stringify(turn));
    }),
  );
}

test("typing a complaint shows the clerk's reply, Gemma's steps and the filed complaint", async () => {
  mockServer({
    caller_text: "road alli potholes",
    language: "en-IN",
    reply: "Complaint filed, C V 1 0 0 1",
    events: [
      { kind: "tool_call", tool: "find_place", args: { query: "Presidency University", area: "Rajanukunte" } },
      { kind: "tool_result", tool: "find_place", result: { matches: [{ name: "Presidency University" }] } },
    ],
    complaint: { tracking_id: "CV-1001" },
    ended: false,
    timings: { stt_ms: 0, llm_ms: 1900 },
  });
  render(<TryPage />);
  fireEvent.click(screen.getByRole("button", { name: "Start talking" }));
  const box = await screen.findByLabelText("Or type your message");
  fireEvent.change(box, { target: { value: "road alli potholes" } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText("Complaint filed, C V 1 0 0 1")).toBeInTheDocument();
  expect(screen.getByText("Looking up “Presidency University” near Rajanukunte")).toBeInTheDocument();
  expect(screen.getByText("Found: Presidency University")).toBeInTheDocument();
  expect(screen.getByText(/now appears on the/).closest("[role=status]")).toHaveTextContent("CV-1001");
});

test("after filing, a browser citizen can leave a number for the call-back", async () => {
  mockServer({
    caller_text: "x", language: "en-IN", reply: "Filed", events: [], complaint: { tracking_id: "CV-1001" },
    ended: false, timings: { stt_ms: 0, llm_ms: 1 },
  });
  render(<TryPage />);
  fireEvent.click(screen.getByRole("button", { name: "Start talking" }));
  fireEvent.change(await screen.findByLabelText("Or type your message"), { target: { value: "x" } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  const phone = await screen.findByLabelText(/Want a call when it's fixed/);
  fireEvent.change(phone, { target: { value: "98450 12345" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("We'll call the number ending 2345 when it's marked fixed.")).toBeInTheDocument();
});

test("too many messages gives a plain-language message", async () => {
  mockServer(429);
  render(<TryPage />);
  fireEvent.click(screen.getByRole("button", { name: "Start talking" }));
  fireEvent.change(await screen.findByLabelText("Or type your message"), { target: { value: "hello" } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Too many messages");
});

test("a refused filing is explained, not hidden", () => {
  expect(
    describeStep({ kind: "tool_result", tool: "file_complaint", result: { ok: false, fix: ["the caller has not confirmed the read-back yet"] } }),
  ).toBe("Not filed yet: the caller has not confirmed the read-back yet");
});

test("survives browsers whose scrollIntoView returns a Promise (newer Chrome)", async () => {
  Element.prototype.scrollIntoView = vi.fn(() => Promise.resolve()) as unknown as Element["scrollIntoView"];
  mockServer({
    caller_text: "hi", language: "en-IN", reply: "Which area?", events: [],
    complaint: null, ended: false, timings: { stt_ms: 0, llm_ms: 1 },
  });
  render(<TryPage />);
  fireEvent.click(screen.getByRole("button", { name: "Start talking" }));
  fireEvent.change(await screen.findByLabelText("Or type your message"), { target: { value: "hi" } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText("Which area?")).toBeInTheDocument(); // the page did not go blank
  delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
});
