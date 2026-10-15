import { render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { App } from "./App";

function mockFetch(routes: Record<string, unknown | Error>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const body = routes[path];
      if (body instanceof Error) throw body;
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

test("shows the helpline number and a healthy status", async () => {
  mockFetch({
    "/health": { status: "ok", db: "ok", version: "0.1.0" },
    "/api/config": { helpline_number: "+918065356055", helpline_display: "080 6535 6055" },
  });
  render(<App />);
  expect(await screen.findByText("All systems working")).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "080 6535 6055" })).toHaveAttribute("href", "tel:+918065356055");
});

test("says the database is unreachable instead of pretending all is well", async () => {
  mockFetch({ "/health": { status: "degraded", db: "down", version: "0.1.0" }, "/api/config": {} });
  render(<App />);
  expect(await screen.findByText("Database unreachable")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
});

test("a network failure gives a plain-language message, not raw error text", async () => {
  mockFetch({ "/health": new TypeError("Failed to fetch"), "/api/config": new TypeError("Failed to fetch") });
  render(<App />);
  expect(await screen.findByText("Server unreachable")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server");
});
