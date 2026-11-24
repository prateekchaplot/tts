/**
 * AC14 (PRD section 8): no user text, audio, or timing data appears in any
 * outbound network traffic during the full input → generate → play → export
 * workflow.
 *
 * ARCHITECTURE.md section 15 prescribes Playwright `page.route` interception:
 * every non-local request is aborted and recorded, and the spec asserts the
 * list is empty after the whole workflow has run.
 */

import { expect, test } from "@playwright/test";
import { uniqueText } from "../support/run";
import {
  audioState,
  generateInUi,
  historyRow,
  installLocalOnlyNetwork,
  openApp,
  resourceOrigins,
} from "../support/ui";

const DOWNLOADS: Array<{ label: string; extension: string }> = [
  { label: "Download audio (WAV)", extension: ".wav" },
  { label: "Download subtitles (SRT)", extension: ".srt" },
  { label: "Download subtitles (VTT)", extension: ".vtt" },
];

test("AC14: input, generate, play, and export stay on this machine", async ({
  page,
}) => {
  const network = await installLocalOnlyNetwork(page);
  await openApp(page);

  const text = uniqueText("Offline export check for the whole workflow.");
  await generateInUi(page, text);

  await page.getByRole("button", { name: "Play audio" }).click();
  await expect
    .poll(async () => (await audioState(page))?.currentTime ?? 0, {
      timeout: 30_000,
    })
    .toBeGreaterThan(0.2);
  await page.getByRole("button", { name: "Pause audio" }).click();

  for (const { label, extension } of DOWNLOADS) {
    const pending = page.waitForEvent("download");
    await page.getByRole("button", { name: label }).click();
    const download = await pending;
    expect(download.suggestedFilename().endsWith(extension)).toBe(true);
    await expect(page.getByRole("button", { name: label })).toBeEnabled();
  }

  // History restore is part of the workflow too.
  const row = historyRow(page, text);
  await row.getByRole("button", { name: /^Open generation:/ }).click();
  await expect(
    page.locator("audio[aria-label='Generated audio']"),
  ).toBeVisible();
  await expect(page.locator(".cue").first()).toBeVisible();

  expect(network.external).toEqual([]);
  const origins = await resourceOrigins(page);
  expect(
    origins.filter((origin) => !origin.startsWith("http://127.0.0.1")),
  ).toEqual([]);
});
