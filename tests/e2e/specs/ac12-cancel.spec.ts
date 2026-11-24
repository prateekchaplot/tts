/**
 * AC12 (PRD section 8): cancelling an in-progress generation returns the
 * interface to a ready state and produces no partial result in history or
 * downloads.
 *
 * A deliberately long text at the slowest rate keeps the job running long
 * enough to cancel. The row becomes `cancelled` with no audio; the `.part` file
 * the worker streamed is removed (ARCHITECTURE.md section 7.4).
 */

import { existsSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { getAudioResponse, getGeneration } from "../support/api";
import { MAIN_DATA_DIR } from "../support/env";
import { readFixtureText } from "../support/fixtures";
import { RUN_TOKEN } from "../support/run";
import {
  CANCELLED_STATUS,
  errorBanner,
  openApp,
  startGeneration,
  waitForStatus,
} from "../support/ui";

test("AC12: cancelling leaves no partial audio", async ({ page, request }) => {
  await openApp(page);

  const longText = `${readFixtureText("sample-5000.txt")} Acceptance run ${RUN_TOKEN}.`;
  await page.locator("#input-text").fill(longText);
  await expect(page.locator("#input-count")).toContainText("5,");

  // Slowest supported rate keeps the long job in flight.
  await page.locator("#rate-slider").focus();
  await page.keyboard.press("Home");
  await expect(page.locator("#rate-value")).toHaveText("0.5×");

  const generationId = await startGeneration(page);
  const cancel = page.getByRole("button", { name: "Cancel generation" });
  await expect(cancel).toBeVisible();
  await cancel.click();

  await waitForStatus(page, CANCELLED_STATUS, 120_000);

  // Ready state again: nothing playable, nothing downloadable.
  await expect(
    page.getByText("Nothing to play: the generation was cancelled."),
  ).toBeVisible();
  await expect(page.locator("audio")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Downloads" })).toHaveCount(0);
  await expect(errorBanner(page)).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Generate audio" }),
  ).toBeEnabled();

  // The row is terminal and carries no audio anywhere.
  const detail = await getGeneration(request, generationId);
  expect(detail.status).toBe("cancelled");
  expect(detail.durationSeconds).toBeNull();
  expect(detail.wordTimings).toBeNull();
  expect(detail.cues).toBeNull();

  const audio = await getAudioResponse(request, generationId);
  expect(audio.status()).toBe(409);
  const envelope = (await audio.json()) as { error: { code: string } };
  expect(envelope.error.code).toBe("GENERATION_NOT_READY");

  const audioDir = path.join(MAIN_DATA_DIR, "generations");
  expect(existsSync(path.join(audioDir, `${generationId}.wav`))).toBe(false);
  expect(existsSync(path.join(audioDir, `${generationId}.wav.part`))).toBe(
    false,
  );

  // The cancelled row is the newest entry; its preview is the first 120 chars of
  // the long text, so it is found by position rather than by token.
  const row = page.locator(".history-item").first();
  await expect(row.locator(".history-status")).toHaveText("Cancelled");
  await expect(
    row.getByRole("button", { name: /^Open generation:/ }),
  ).toBeDisabled();
});
