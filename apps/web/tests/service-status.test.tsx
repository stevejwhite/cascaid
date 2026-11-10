import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ServiceStatus } from "../components/service-status";
import type { Readiness } from "../lib/api";

const status: Readiness = {
  status: "ready", model_backend: "fake", speech_backend: "off", tts_backend: "off", checked_at: "2026-10-16T09:00:00Z",
  registry: { status: "ready", detail: "7 sources registered." },
  cases: { status: "ready", detail: "61 station cases available." },
  generation: { status: "unavailable", detail: "Local model service is not ready." },
  speech: { status: "disabled", detail: "Speech input is off; typing works." },
  voice: { status: "disabled", detail: "Character voice is off; browser voices work." },
};

test("shows the service cards on a separate page with home navigation", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(status))));
  render(<ServiceStatus />);
  const cards = await screen.findByRole("region", { name: "Service status" });
  expect(within(cards).getAllByRole("article")).toHaveLength(5);
  expect(within(cards).getByText("61 station cases available.")).toBeInTheDocument();
  expect(within(cards).getByText("Generation · Deterministic fake model")).toBeInTheDocument();
  expect(within(cards).getAllByText("Off")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: /Back to home/ })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: "Status" })).toHaveAttribute("aria-current", "page");
});

test("missing checks in an older API are labelled restart needed", async () => {
  const old: Partial<Readiness> = { ...status };
  delete old.speech;
  delete old.speech_backend;
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(old))));
  render(<ServiceStatus />);
  const card = (await screen.findByText("Speech recognition")).closest("article")!;
  expect(within(card).getByText("Restart needed")).toBeInTheDocument();
  expect(within(card).getByText(/older than this page/)).toBeInTheDocument();
});

test("a failed refresh removes stale ready states and can be retried", async () => {
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(status)))
    .mockResolvedValueOnce(new Response("{}", { status: 503 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(status))));
  render(<ServiceStatus />);
  await screen.findByText("61 station cases available.");
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("local API is unavailable");
  expect(screen.queryByText("Ready")).not.toBeInTheDocument();
  expect(screen.getAllByText("Not checked")).toHaveLength(5);
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByText("61 station cases available.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
