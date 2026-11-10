import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { RecordPrompts } from "../components/record";
import type { RecordingPrompts } from "../lib/api";

const prompts: RecordingPrompts = {
  enabled: true, consent: "I agree to my voice being recorded.",
  prompts: [{ item: 1, case_id: "a", text: "How much do you drink?" }, { item: 2, case_id: "a", text: "Do you smoke?" }],
};
const recorder = () => vi.fn(async () => ({ stop: async () => new Blob([new Uint8Array(44)]), cancel: vi.fn() }));

test("recording needs consent and a pseudonym, saves, then advances", async () => {
  const fetch = vi.fn(async (url: string) => url.includes("/prompts")
    ? Response.json(prompts) : Response.json({ item: 1, recorded: 1, duration_ms: 1500 }));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<RecordPrompts record={recorder()} />);
  const button = await screen.findByRole("button", { name: "Record" });
  expect(button).toBeDisabled();
  await user.click(screen.getByRole("checkbox"));
  await user.type(screen.getByLabelText(/Pseudonym/), "speaker-01");
  expect(button).toBeEnabled();
  await user.click(button);
  await user.click(screen.getByRole("button", { name: "Stop and save" }));
  expect(await screen.findByText("Do you smoke?")).toBeInTheDocument();
  const [url] = fetch.mock.calls.find(([u]) => !u.includes("/prompts"))!;
  expect(url).toBe("/backend/api/recordings?speaker=speaker-01&item=1&consent=true");
});

test("explains how to enable recording when it is off", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ ...prompts, enabled: false })));
  render(<RecordPrompts record={recorder()} />);
  expect(await screen.findByText(/Recording is turned off/)).toBeInTheDocument();
});
