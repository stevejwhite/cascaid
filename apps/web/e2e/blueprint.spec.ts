import { expect, test } from "@playwright/test";

test("filter stations by search and specialty, then clear the filters", async ({ page }) => {
  await page.goto("/");
  const search = page.getByRole("searchbox", { name: "Search stations" });
  await search.fill("clozapine");
  await page.getByRole("combobox", { name: "Specialty", exact: true }).selectOption("general");
  const cards = page.locator(".station-list article");
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText(/clozapine/i);
  await search.fill("no-such-station-987654");
  await expect(page.getByText(/No stations match these filters/)).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByRole("article", { name: "Alcohol use — history" })).toBeVisible();
});

test("select a mock-exam station from the blueprint and start its reading time", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Matrix", exact: true }).click();
  await expect(page).toHaveURL(/\/blueprint$/);
  await page.getByRole("combobox", { name: "Mock exam", exact: true }).selectOption("B");
  await expect(page.getByRole("link", { name: /^A09/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /^B08/ })).toHaveCount(0);
  await expect(page.getByText(/Unavailable: Physical examination/)).toBeVisible();
  await page.getByRole("combobox", { name: "Mock exam", exact: true }).selectOption("A");
  await page.getByRole("link", { name: /^A09/ }).click();
  await expect(page).toHaveURL(/station=alcohol-history/);
  await expect(page.getByRole("heading", { name: "Alcohol use — history" })).toBeVisible();
  await expect(page.getByRole("timer", { name: "Reading time remaining" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link")).toHaveText(["Home", "Matrix", "Status"]);
  await page.getByRole("button", { name: "Begin interview now" }).click();
  await page.getByRole("button", { name: "End station", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Feedback" })).toBeVisible();
  await page.getByRole("button", { name: "Back to stations" }).click();
  await expect(page).not.toHaveURL(/station=/);
  await expect(page.getByRole("link", { name: "Matrix", exact: true })).toBeVisible();
});

test("the matrix is usable on a small screen without overflowing the page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/blueprint");
  await expect(page.getByRole("table")).toBeVisible();
  const dimensions = await page.evaluate(() => {
    const matrix = document.querySelector(".matrix-scroll")!;
    return { viewport: window.innerWidth, page: document.documentElement.scrollWidth,
      matrixWidth: matrix.clientWidth, matrixScroll: matrix.scrollWidth };
  });
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport);
  expect(dimensions.matrixScroll).toBeGreaterThan(dimensions.matrixWidth);
});

test("home, matrix and status have clear return navigation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("searchbox", { name: "Search stations" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Service status" })).toHaveCount(0);
  await page.getByRole("link", { name: "Status", exact: true }).click();
  await expect(page).toHaveURL(/\/status$/);
  await expect(page.getByRole("region", { name: "Service status" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Speech recognition" })).toBeVisible();
  await page.getByRole("link", { name: /Back to home/ }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole("link", { name: "Matrix", exact: true }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await page.getByRole("link", { name: "Home", exact: true }).click();
  await expect(page.getByRole("heading", { name: "CASC stations" })).toBeVisible();
});
