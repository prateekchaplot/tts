/**
 * AC11 (PRD section 8): a deliberately forced synthesis failure shows an error,
 * presents no partial audio as success, and leaves prior history intact.
 *
 * Fault injection is a `Settings` value read once at startup (T4.3), so the
 * suite runs a second, fault-armed server on 8322 (see playwright.config.ts).
 * The user-visible library lives on the main server: it must be untouched, and
 * its prior entry must still restore after the failure.
 */

import { existsSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import {
  generateViaApi,
  getAudioResponse,
  getGeneration,
  listGenerations,
} from "../support/api";
import { FAULT_DATA_DIR, FAULT_URL } from "../support/env";
import { uniqueText } from "../support/run";
import {
  errorBanner,
  FAILED_STATUS,
  historyRow,
  openApp,
  startGeneration,
  waitForStatus,
} from "../support/ui";

test("AC11: a forced engine failure never becomes a success", async ({
  page,
  request,
}) => {
  // A finished generation that must survive the failure.
  const priorText = uniqueText(
    "Kilo prior history entry survives the injected fault.",
  );
  const prior = await generateViaApi(request, priorText);
  const beforeTotal = (await listGenerations(request)).total;

  await openApp(page, FAULT_URL);
  const failingText = uniqueText("Mike this generation is meant to fail.");
  await page.locator("#input-text").fill(failingText);
  const generationId = await startGeneration(page);
  await waitForStatus(page, FAILED_STATUS, 120_000);

  // Honest error, with a corrective action, and nothing playable.
  const banner = errorBanner(page);
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(
    "The speech engine could not render this text.",
  );
  await expect(banner).toContainText("What you can do");
  await expect(banner).toContainText("check the log in your tts data folder");
  await expect(
    page.getByText("Nothing to play: the generation failed."),
  ).toBeVisible();
  await expect(page.locator("audio")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Downloads" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /^Download audio/ }),
  ).toHaveCount(0);

  // The failed row is real but not restorable, and the API agrees.
  const row = historyRow(page, failingText);
  await expect(row).toBeVisible();
  await expect(row.locator(".history-status")).toContainText("Failed");
  await expect(
    row.getByRole("button", { name: /^Open generation:/ }),
  ).toBeDisabled();

  const detail = await getGeneration(request, generationId, FAULT_URL);
  expect(detail.status).toBe("failed");
  expect(detail.durationSeconds).toBeNull();
  expect(detail.wordTimings).toBeNull();
  expect(detail.error?.code).toBe("ENGINE_ERROR");
  expect(detail.error?.message).toBe(
    "The speech engine could not render this text.",
  );

  const audio = await getAudioResponse(request, generationId, FAULT_URL);
  expect(audio.status()).toBe(409);
  const envelope = (await audio.json()) as { error: { code: string } };
  expect(envelope.error.code).toBe("GENERATION_NOT_READY");

  // No partial artifact on disk: neither the finished file nor the `.part`.
  const audioDir = path.join(FAULT_DATA_DIR, "generations");
  expect(existsSync(path.join(audioDir, `${generationId}.wav`))).toBe(false);
  expect(existsSync(path.join(audioDir, `${generationId}.wav.part`))).toBe(
    false,
  );

  // Prior history on the library the user actually sees is unchanged.
  const afterTotal = (await listGenerations(request)).total;
  expect(afterTotal).toBe(beforeTotal);

  await openApp(page);
  const priorRow = historyRow(page, priorText);
  await expect(priorRow).toBeVisible();
  await expect(priorRow.locator(".history-status")).toContainText("Ready");
  await priorRow.getByRole("button", { name: /^Open generation:/ }).click();
  await expect(
    page.locator("audio[aria-label='Generated audio']"),
  ).toBeVisible();
  await expect(page.locator(".word-flow")).toContainText("Kilo");
  expect(prior.status).toBe("succeeded");
});
