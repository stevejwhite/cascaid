import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { BlueprintMatrix } from "../components/blueprint-matrix";
import type { BlueprintMatrix as Matrix } from "../lib/api";

const matrix: Matrix = {
  source_id: "mrcpsych_casc", version: "March 2023 | sha256:pinned",
  stations_per_running_order: { history: 5, examination: 5, management: 6 },
  minimum_specialty: { general: 4, old_age: 1 }, reading_seconds: { morning: 240, afternoon: 90 },
  subdivisions: [
    { skill: "history", id: "collateral_history", label: "Collateral history", minimum_percentage: 100 },
    { skill: "examination", id: "physical_examination", label: "Physical examination", minimum_percentage: 50 },
  ],
  stations: [
    { code: "A11", running_order: "A", session: "afternoon", skill: "history", subdivision: "collateral_history",
      specialty: "old_age", title: "Memory collateral", case_id: "memory-collateral-history", unavailable_reason: null,
      clinically_validated: false },
    { code: "B08", running_order: "B", session: "morning", skill: "examination", subdivision: "physical_examination",
      specialty: "general", title: "Physical examination station", case_id: null,
      unavailable_reason: "Physical examination is not supported by the simulator.", clinically_validated: false },
  ],
};

test("places selectable and unavailable stations in the correct blueprint cells", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(matrix))));
  render(<BlueprintMatrix />);
  const table = await screen.findByRole("table");
  const row = within(table).getByRole("rowheader", { name: /Collateral history/ }).closest("tr")!;
  const link = within(row).getByRole("link", { name: /A11/ });
  expect(link).toHaveAttribute("href", "/?station=memory-collateral-history");
  expect(link.closest("td")).toBe(row.children[3]); // old age, after general
  expect(screen.queryByRole("link", { name: /B08/ })).not.toBeInTheDocument();
  expect(screen.getByText(/Unavailable: Physical examination/)).toBeInTheDocument();
  expect(screen.getByText("1 runnable / 2 planned stations")).toBeInTheDocument();
  expect(screen.getAllByText("Not clinically validated")).toHaveLength(2);
  await userEvent.selectOptions(screen.getByLabelText("Mock exam"), "A");
  expect(screen.getByText("1 runnable / 1 planned stations")).toBeInTheDocument();
  expect(screen.queryByText(/B08/)).not.toBeInTheDocument();
  expect(screen.getByText("50%")).toBeInTheDocument(); // pinned minimum remains, even with no matching station
  await userEvent.selectOptions(screen.getByLabelText("Mock exam"), "B");
  expect(screen.queryByRole("link", { name: /A11/ })).not.toBeInTheDocument();
  expect(screen.getByText("0 runnable / 1 planned stations")).toBeInTheDocument();
});

test("reports an API failure and can retry", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("{}", { status: 503 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(matrix))));
  render(<BlueprintMatrix />);
  expect(await screen.findByRole("alert")).toHaveTextContent("blueprint could not be loaded");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByRole("table")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
