import { defineConfig, devices } from "@playwright/test";
import { FAKE_MICROPHONE } from "./e2e/global-setup";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  use: { baseURL: process.env.WEB_TEST_URL ?? "http://127.0.0.1:3105", trace: "retain-on-failure" },
  projects: [{
    name: "chromium",
    use: {
      ...devices["Desktop Chrome"],
      permissions: ["microphone"],
      // Feed a synthesised question through the real recorder in place of a microphone.
      launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        `--use-file-for-fake-audio-capture=${FAKE_MICROPHONE}`] },
    },
  }],
  // Start the stack with `npm run dev` first, so tests never take ownership of other services.
});
