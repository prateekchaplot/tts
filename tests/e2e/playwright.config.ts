/**
 * Playwright configuration for the acceptance suite (ARCHITECTURE.md section
 * 14.2 T5.1, section 15).
 *
 * Two `tts` servers back the run:
 *
 * - the main server on `TTS_E2E_PORT` (8321), which CI starts itself before
 *   Playwright and which this config starts locally when it is absent;
 * - a fault-armed server on `TTS_E2E_FAULT_PORT` (8322) with `TTS_FAULT=engine`
 *   for AC11. Fault injection is a `Settings` value read at startup, so one
 *   long-running process cannot switch modes.
 *
 * The suite is serial: synthesis is single-worker by design and the history
 * assertions describe a shared library.
 */

import path from "node:path";
import { defineConfig, devices } from "@playwright/test";
import {
  FAULT_DATA_DIR,
  FAULT_PORT,
  FAULT_URL,
  MAIN_DATA_DIR,
  MAIN_PORT,
  MAIN_URL,
  PYTHON,
  REPO_ROOT,
  VOICE_SOURCE,
} from "./support/env";

const SEED_SCRIPT = path.join(__dirname, "scripts", "ensure-data.mjs");

/** Seed the data dir, then run `tts` from the repository root. */
function serverCommand(): string {
  return `"${process.execPath}" "${SEED_SCRIPT}" && "${PYTHON}" -m tts`;
}

const commonEnv = {
  ...process.env,
  TTS_HOST: "127.0.0.1",
};

export default defineConfig({
  testDir: "./specs",
  // Failure artifacts (traces, screenshots) go to the repository's ignored
  // scratch directory instead of the frontend working directory.
  outputDir: path.join(REPO_ROOT, ".venv", "e2e-artifacts"),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: process.env["CI"] !== undefined,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter:
    process.env["CI"] !== undefined ? [["list"], ["github"]] : [["list"]],
  use: {
    baseURL: MAIN_URL,
    acceptDownloads: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    launchOptions: { args: ["--autoplay-policy=no-user-gesture-required"] },
  },
  webServer: [
    {
      command: serverCommand(),
      url: `${MAIN_URL}/api/health`,
      cwd: REPO_ROOT,
      // CI starts this server itself; locally Playwright starts it on demand.
      reuseExistingServer: true,
      timeout: 180_000,
      env: {
        ...commonEnv,
        TTS_DATA_DIR: MAIN_DATA_DIR,
        TTS_PORT: MAIN_PORT,
        TTS_E2E_SEED_DIR: MAIN_DATA_DIR,
        TTS_E2E_SEED_SOURCE: VOICE_SOURCE,
      },
    },
    {
      command: serverCommand(),
      url: `${FAULT_URL}/api/health`,
      cwd: REPO_ROOT,
      // A stale server may be unarmed or hold stale history, so never reuse one.
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        ...commonEnv,
        TTS_DATA_DIR: FAULT_DATA_DIR,
        TTS_PORT: FAULT_PORT,
        TTS_FAULT: "engine",
        TTS_E2E_SEED_DIR: FAULT_DATA_DIR,
        TTS_E2E_SEED_SOURCE: VOICE_SOURCE,
      },
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
