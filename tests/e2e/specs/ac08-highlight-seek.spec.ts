/**
 * AC8 (PRD section 8): during playback the spoken word is highlighted and kept
 * visible, and clicking a word seeks the audio to that word.
 */

import { expect, test } from "@playwright/test";
import { getGeneration } from "../support/api";
import { uniqueText } from "../support/run";
import {
  activeWordIndex,
  audioState,
  generateInUi,
  openApp,
} from "../support/ui";

test("AC8: playback highlights and seeks by word and sentence", async ({
  page,
  request,
}) => {
  await openApp(page);
  // A short viewport forces the word flow to scroll as playback advances.
  await page.setViewportSize({ width: 1000, height: 420 });

  const text = uniqueText(
    "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima.",
  );
  const generationId = await generateInUi(page, text);
  const detail = await getGeneration(request, generationId);
  const timings = detail.wordTimings ?? [];
  expect(timings.length).toBeGreaterThan(8);

  const words = page.locator(".word-flow .word");
  await expect(words).toHaveCount(timings.length);

  await page.getByRole("button", { name: "Play audio" }).click();
  await expect
    .poll(async () => activeWordIndex(page), { timeout: 30_000 })
    .toBeGreaterThanOrEqual(1);

  // The active word is inside the viewport: the view keeps it visible.
  const activeBox = await page.locator(".word-flow .word.active").boundingBox();
  const viewport = page.viewportSize();
  expect(activeBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  if (activeBox !== null && viewport !== null) {
    expect(activeBox.y).toBeGreaterThanOrEqual(0);
    // One pixel of slack for fractional layout heights.
    expect(activeBox.y + activeBox.height).toBeLessThanOrEqual(
      viewport.height + 1,
    );
  }

  await page.getByRole("button", { name: "Pause audio" }).click();

  // Clicking a word seeks the audio to that word and highlights it.
  const target = timings.findIndex(
    (timing) => timing.aligned && timing.startMs > 1200,
  );
  expect(target).toBeGreaterThan(0);
  await words.nth(target).click();
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
    .toBeLessThanOrEqual(400);
  expect(await activeWordIndex(page)).toBe(target);

  // Sentence cues are the keyboard-friendly seek path (T4.2); clicking one
  // moves playback to the cue's first word.
  await page.locator(".cue").first().click();
  await expect
    .poll(
      async () =>
        (await audioState(page))?.currentTime ?? Number.POSITIVE_INFINITY,
      {
        timeout: 15_000,
      },
    )
    .toBeLessThan(0.4);
});
