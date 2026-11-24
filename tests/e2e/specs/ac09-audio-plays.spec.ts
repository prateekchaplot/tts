/**
 * AC9 (PRD section 8): the downloaded audio file plays completely in a standard
 * media player.
 *
 * "Plays completely" is checked structurally (a well-formed RIFF/WAVE file whose
 * declared sizes match the bytes on disk, so nothing is truncated) and
 * functionally (Chromium decodes the downloaded file as an independent blob and
 * reports the same duration).
 */

import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { getGeneration } from "../support/api";
import { uniqueText } from "../support/run";
import { generateInUi, openApp } from "../support/ui";
import { parseWav, toBase64 } from "../support/wav";

test("AC9: the downloaded WAV is complete and playable", async ({
  page,
  request,
}) => {
  await openApp(page);

  const text = uniqueText(
    "Hello world. This is a live check. Numbers like 42 stay honest.",
  );
  const generationId = await generateInUi(page, text);
  const detail = await getGeneration(request, generationId);
  expect(detail.sampleRate).not.toBeNull();
  expect(detail.durationSeconds).not.toBeNull();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download audio (WAV)" }).click();
  const download = await downloadPromise;

  // Section 9.2 naming: first six words, lowercased, plus the UTC timestamp.
  expect(download.suggestedFilename()).toMatch(
    /^hello-world-this-is-a-live_\d{8}-\d{6}\.wav$/,
  );

  const filePath = await download.path();
  expect(filePath).not.toBeNull();
  const bytes = readFileSync(filePath ?? "");
  const wav = parseWav(bytes);

  expect(wav.audioFormat).toBe(1);
  expect(wav.channels).toBe(1);
  expect(wav.bitsPerSample).toBe(16);
  expect(wav.sampleRate).toBe(detail.sampleRate);
  expect(wav.dataBytes).toBeGreaterThan(0);
  expect(wav.riffSize).toBe(bytes.length - 8);
  expect(wav.durationSeconds).toBeCloseTo(
    detail.durationSeconds ?? Number.NaN,
    1,
  );

  // Decode the downloaded bytes, not the app's object URL.
  const decoded = await page.evaluate(async (base64) => {
    const response = await fetch(`data:audio/wav;base64,${base64}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    try {
      const audio = new Audio();
      audio.src = url;
      await new Promise<void>((resolve, reject) => {
        audio.addEventListener("loadedmetadata", () => resolve(), {
          once: true,
        });
        audio.addEventListener(
          "error",
          () => reject(new Error("decode failed")),
          { once: true },
        );
      });
      return audio.duration;
    } finally {
      URL.revokeObjectURL(url);
    }
  }, toBase64(bytes));

  expect(decoded).toBeCloseTo(wav.durationSeconds, 1);
});
