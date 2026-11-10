import { expect, test } from "@playwright/test";

// Needs a development server started with AUTHORING_ENABLED=true; skipped otherwise.
test("revise a copy of the alcohol case, preview its rules and export it", async ({ page, request }) => {
  test.skip((await request.get("/backend/api/authoring/options")).status() !== 200, "The case editor is not enabled");
  const before = (await (await request.get("/backend/api/cases")).json()).find((c: { id: string }) => c.id === "alcohol-history");

  await page.goto("/authoring");
  await page.getByLabel("Your name (recorded on drafts)").fill("E2E author");
  await page.getByLabel("Case", { exact: true }).selectOption("alcohol-history");
  await page.getByLabel(/A revision/).check();
  await page.getByRole("button", { name: "Open a draft" }).click();
  await expect(page).toHaveURL(/\/authoring\/[0-9a-f]{32}$/);
  await expect(page.getByText("Not clinically validated. Original fictional cases only.")).toBeVisible();

  const first = page.getByRole("article", { name: /^Fact 1:/ });
  await first.getByLabel("What the character says").fill("About a litre of vodka every day, more at weekends.");
  await page.getByLabel("New fact: its main question label").fill("hiding bottles");
  await page.getByRole("button", { name: "Add fact" }).click();
  const added = page.getByRole("article", { name: /hiding bottles/ });
  await added.getByLabel("What the character says").fill("I keep a bottle in the garage so my daughter won't see it.");
  await added.getByLabel("Feedback area").fill("alcohol");
  await added.getByLabel("When it may be shared").selectOption("after_rapport");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toHaveText("Draft saved");
  await expect(page.getByText("The case passes the runtime schema checks.")).toBeVisible();

  await page.getByRole("button", { name: "Start rule preview" }).click();
  await page.getByRole("checkbox", { name: "hiding bottles" }).check();
  await page.getByRole("button", { name: "Add turn" }).click();
  await expect(page.getByText(/Needs rapport level 1/)).toBeVisible();
  await page.getByRole("combobox", { name: "Empathy" }).selectOption("1");
  await page.getByRole("button", { name: "Add turn" }).click();
  await expect(page.getByText(/at least the 0.5 needed for level 1: released/)).toBeVisible();

  await page.reload();
  await expect(page.getByRole("article", { name: /hiding bottles/ })).toBeVisible();
  await page.getByRole("button", { name: "Export case" }).click();
  await expect(page.getByText(/Exported alcohol-history.yaml/)).toBeVisible();
  await page.getByText("Review sheet", { exact: true }).click();
  await expect(page.locator(".review-sheet")).toContainText("facts: added `hiding-bottles`");
  await expect(page.locator(".review-sheet")).toContainText("Before this case can be used for practice");

  const after = (await (await request.get("/backend/api/cases")).json()).find((c: { id: string }) => c.id === "alcohol-history");
  expect(after).toEqual(before);  // the active station is unchanged
});
