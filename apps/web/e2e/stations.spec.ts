import { existsSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { FAKE_MICROPHONE } from "./global-setup";

// Requires the running stack: npm run dev.
test("the station list shows the shipped case without hidden facts", async ({ page }) => {
  await page.goto("/");
  const card = page.getByRole("article", { name: "Elevated mood — history" });
  await expect(card).toBeVisible();
  await expect(card.getByText("Not clinically validated")).toBeVisible();
  await expect(page.getByRole("region", { name: "Service status" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Status", exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("three hours a night");
});

// Works with either backend; the local model can take several seconds per reply.
test("a station runs from reading to debrief", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/");
  await page.getByRole("article", { name: "Alcohol use — history" }).getByRole("button", { name: "Start station" }).click();
  await expect(page.getByRole("timer", { name: "Reading time remaining" })).toBeVisible();
  await page.getByRole("button", { name: "Begin interview now" }).click();
  const box = page.getByLabel("What you say to Chris");
  await box.fill("How much do you drink on a typical day?");
  await box.press("Enter");
  await expect(page.locator(".transcript .character:not(.waiting)")).toHaveCount(2, { timeout: 60_000 });
  await page.getByRole("button", { name: "End station" }).click();
  await expect(page.getByRole("heading", { name: "Feedback" })).toBeVisible();
  await expect(page.getByText("Key information elicited")).toBeVisible();
  await expect(page.getByText("not a CASC mark", { exact: false })).toBeVisible();
});

test("speech from the microphone is transcribed locally and answered", async ({ page, request }) => {
  test.setTimeout(120_000);
  const status = await (await request.get("/backend/api/status")).json();
  test.skip(status.speech.status !== "ready" || status.speech_backend !== "local", "Local speech recognition is not running");
  test.skip(!existsSync(FAKE_MICROPHONE), "No synthesised microphone clip (macOS `say` unavailable)");
  await page.goto("/");
  await page.getByRole("article", { name: "Alcohol use — history" }).getByRole("button", { name: "Start station" }).click();
  await page.getByRole("button", { name: "Begin interview now" }).click();
  await page.getByRole("button", { name: "Speak to Chris" }).click();
  await expect(page.getByRole("button", { name: /Stop and transcribe/ })).toBeVisible();
  // The fake device loops the clip from an arbitrary point; two loops contain one whole sentence.
  await page.waitForTimeout(8500);
  await page.getByRole("button", { name: /Stop and transcribe/ }).click();
  const box = page.getByLabel("What you say to Chris");
  await expect(box).toHaveValue(/how much do you drink/i, { timeout: 30_000 });
  await box.press("Enter");
  await expect(page.locator(".transcript .character:not(.waiting)")).toHaveCount(2, { timeout: 60_000 });
});
