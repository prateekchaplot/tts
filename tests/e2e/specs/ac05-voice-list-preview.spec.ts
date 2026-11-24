/**
 * AC5 (PRD section 8): the voice list shows every installed voice with its
 * name and language, and previewing a voice plays a sample in that voice.
 */

import { expect, test } from "@playwright/test";
import { listVoices } from "../support/api";
import { errorBanner, openApp } from "../support/ui";
import { parseWav } from "../support/wav";

test("AC5: installed voices are listed and previews are playable", async ({
  page,
  request,
}) => {
  await openApp(page);

  const voices = await listVoices(request);
  expect(voices.items.length).toBeGreaterThan(0);

  const options = page.locator("#voice-select option");
  await expect(options).toHaveCount(voices.items.length);

  for (const voice of voices.items) {
    const option = page.locator(`#voice-select option[value="${voice.id}"]`);
    await expect(option).toHaveCount(1);
    await expect(option).toContainText(voice.name);
    await expect(option).toContainText(voice.language);
  }

  const previewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/voices/preview"),
  );
  await page.getByRole("button", { name: "Preview voice" }).click();

  const response = await previewResponse;
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"] ?? "").toContain("audio/wav");
  const wav = parseWav(new Uint8Array(await response.body()));
  expect(wav.channels).toBe(1);
  expect(wav.sampleRate).toBeGreaterThan(0);
  expect(wav.durationSeconds).toBeGreaterThan(0.5);

  // The button leaves its "playing preview" state, and becomes available
  // again, when the sample ends (or fails).
  await expect(page.getByRole("button", { name: "Preview voice" })).toBeEnabled(
    {
      timeout: 30_000,
    },
  );
  await expect(errorBanner(page)).toHaveCount(0);
});
