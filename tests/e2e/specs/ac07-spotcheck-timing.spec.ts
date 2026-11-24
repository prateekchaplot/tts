/**
 * AC7 (PRD section 8): the subtitle data carries a timing entry for each spoken
 * word, and spot checks confirm words track the audio within the agreed
 * tolerance.
 *
 * ARCHITECTURE.md section 15 keeps the human listening spot check in T5.3's
 * `MEASUREMENTS.md`. This spec owns the machine-checkable half: structure,
 * monotonicity, bounds, end-of-speech accuracy, and the seek/highlight mapping.
 * The tolerance constant is shared with T5.3.
 */

import { expect, test } from "@playwright/test";
import { getGeneration } from "../support/api";
import { WORD_START_TOLERANCE_MS } from "../support/env";
import { uniqueText } from "../support/run";
import {
  activeWordIndex,
  audioState,
  generateInUi,
  openApp,
} from "../support/ui";

test("AC7: word timings exist, are monotonic, and track the audio", async ({
  page,
  request,
}) => {
  await openApp(page);

  const text = uniqueText(
    "Numbers like 42 stay honest in a timing spot check.",
  );
  const generationId = await generateInUi(page, text);
  const detail = await getGeneration(request, generationId);

  const timings = detail.wordTimings ?? [];
  expect(timings.length).toBeGreaterThan(4);
  const durationMs = (detail.durationSeconds ?? 0) * 1000;
  expect(durationMs).toBeGreaterThan(500);

  let previousEnd = 0;
  for (const timing of timings) {
    expect(timing.text.length).toBeGreaterThan(0);
    expect(timing.startMs).toBeGreaterThanOrEqual(0);
    expect(timing.endMs).toBeGreaterThanOrEqual(timing.startMs);
    // Integer millisecond rounding may touch the previous boundary.
    expect(timing.startMs).toBeGreaterThanOrEqual(previousEnd - 1);
    expect(timing.endMs).toBeLessThanOrEqual(durationMs + 1);
    previousEnd = timing.endMs;
  }

  // Speech ends inside the file: Piper pads the final sentence with a little
  // silence, so the last word may stop short of the file duration. The ±100 ms
  // AC7 tolerance is about word *starts* versus audible speech, which the seek
  // check below measures; this bound only rejects a truncated timing table.
  const last = timings[timings.length - 1];
  expect(durationMs - last.endMs).toBeGreaterThanOrEqual(0);
  expect(durationMs - last.endMs).toBeLessThanOrEqual(500);

  // Clicking a word seeks to its start within tolerance; the highlight follows.
  const target = timings.findIndex(
    (timing) => timing.aligned && timing.startMs > 300,
  );
  expect(target).toBeGreaterThan(0);
  await page.locator(".word-flow .word").nth(target).click();
  await expect
    .poll(
      async () => {
        const state = await audioState(page);
        return Math.abs(
          (state?.currentTime ?? 0) * 1000 - (timings[target]?.startMs ?? 0),
        );
      },
      { timeout: 15_000 },
    )
    .toBeLessThanOrEqual(WORD_START_TOLERANCE_MS);
  expect(await activeWordIndex(page)).toBe(target);

  // While playing, the highlight advances with the audio instead of standing still.
  await page.getByRole("button", { name: "Play audio" }).click();
  await expect
    .poll(async () => activeWordIndex(page), { timeout: 30_000 })
    .toBeGreaterThan(target);
  await page.getByRole("button", { name: "Pause audio" }).click();
});
