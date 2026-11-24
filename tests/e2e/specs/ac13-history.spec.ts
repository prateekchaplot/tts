/**
 * AC13 (PRD section 8): history shows recent generations with input preview,
 * voice, and time; selecting one restores its audio and subtitles; deleting one
 * removes only that entry.
 */

import { expect, test } from "@playwright/test";
import { getGeneration, listGenerations } from "../support/api";
import { uniqueText } from "../support/run";
import { errorBanner, generateInUi, historyRow, openApp } from "../support/ui";

test("AC13: history restores and deletes one entry at a time", async ({
  page,
  request,
}) => {
  await openApp(page);

  const firstText = uniqueText("Kilo lima history entry one.");
  const secondText = uniqueText("Mike november history entry two.");
  const firstId = await generateInUi(page, firstText);
  const secondId = await generateInUi(page, secondText);

  const firstRow = historyRow(page, firstText);
  const secondRow = historyRow(page, secondText);
  await expect(firstRow).toBeVisible();
  await expect(secondRow).toBeVisible();

  // Preview, voice, and time (PRD AC13).
  await expect(firstRow.locator(".history-preview")).toContainText(
    "Kilo lima history entry one",
  );
  await expect(firstRow.locator(".history-meta")).toContainText(
    "en_US-lessac-medium",
  );
  await expect(firstRow.locator("time")).toHaveAttribute("dateTime", /.+/);
  expect(
    (await firstRow.locator("time").textContent())?.trim().length ?? 0,
  ).toBeGreaterThan(0);
  await expect(page.getByText(/\d+ saved generations?/)).toBeVisible();

  const totalBefore = (await listGenerations(request)).total;

  // Restore the older entry: audio and subtitles load without a new generation.
  await firstRow.getByRole("button", { name: /^Open generation:/ }).click();
  await expect(
    page.locator("audio[aria-label='Generated audio']"),
  ).toBeVisible();
  await expect(page.locator(".word-flow")).toContainText("Kilo");
  await expect(page.locator(".cue").first()).toBeVisible();
  await expect(errorBanner(page)).toHaveCount(0);

  // Delete the other entry only.
  await secondRow.getByRole("button", { name: /^Delete generation:/ }).click();
  await expect(
    secondRow.getByText("Delete this entry? This cannot be undone."),
  ).toBeVisible();
  await secondRow
    .getByRole("button", { name: /^Confirm delete generation:/ })
    .click();
  await expect(secondRow).toHaveCount(0);

  const deleted = await request.get(`/api/generations/${secondId}`);
  expect(deleted.status()).toBe(404);
  const envelope = (await deleted.json()) as { error: { code: string } };
  expect(envelope.error.code).toBe("GENERATION_NOT_FOUND");

  // The surviving entry is untouched and still restorable.
  await expect(firstRow).toBeVisible();
  await firstRow.getByRole("button", { name: /^Open generation:/ }).click();
  await expect(
    page.locator("audio[aria-label='Generated audio']"),
  ).toBeVisible();
  await expect(page.locator(".word-flow")).toContainText("Kilo");

  const totalAfter = (await listGenerations(request)).total;
  expect(totalAfter).toBe(totalBefore - 1);
  const survivor = await getGeneration(request, firstId);
  expect(survivor.status).toBe("succeeded");
  expect(survivor.wordTimings?.length ?? 0).toBeGreaterThan(0);
});
