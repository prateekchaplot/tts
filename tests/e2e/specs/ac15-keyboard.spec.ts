/**
 * AC15 (PRD section 8): the complete workflow (input, generate, play, download
 * audio and subtitles) and a history delete are completable using only the
 * keyboard, without documentation.
 *
 * Every interaction here is a `Tab`, `Shift+Tab`, `Enter`, `Space`, or typed
 * character. T4.2 recorded the same flow by hand; this spec freezes it.
 */

import { expect, test } from "@playwright/test";
import { uniqueText } from "../support/run";
import {
  audioState,
  errorBanner,
  focusedElement,
  historyRow,
  openApp,
  READY_STATUS,
  tabUntil,
  waitForStatus,
} from "../support/ui";

const DOWNLOADS: Array<{ label: string; extension: string }> = [
  { label: "Download audio (WAV)", extension: ".wav" },
  { label: "Download subtitles (SRT)", extension: ".srt" },
  { label: "Download subtitles (VTT)", extension: ".vtt" },
];

test("AC15: the workflow and a history delete work from the keyboard", async ({
  page,
}) => {
  await openApp(page);

  // First tab stop is the skip link; Enter jumps to the main landmark.
  await page.keyboard.press("Tab");
  expect((await focusedElement(page)).text).toBe("Skip to main content");
  await page.keyboard.press("Enter");
  expect((await focusedElement(page)).id).toBe("main");

  await tabUntil(page, { id: "input-text" });
  const text = uniqueText("Keyboard only acceptance run.");
  await page.keyboard.type(text);
  await expect(page.locator("#input-text")).toHaveValue(text);

  await tabUntil(page, { text: "Generate audio" });
  await page.keyboard.press("Enter");
  await waitForStatus(page, READY_STATUS);

  // While the job runs the Generate button is replaced, so focus returns to the
  // document. The skip link is the documented way back to a non-control
  // landmark; from there Space uses the global playback shortcut (section 10.3)
  // instead of tabbing through the media element's own controls.
  await tabUntil(page, { text: "Skip to main content" }, 120);
  await page.keyboard.press("Enter");
  expect((await focusedElement(page)).id).toBe("main");
  await page.keyboard.press("Space");
  await expect
    .poll(async () => (await audioState(page))?.paused ?? true)
    .toBe(false);
  await page.keyboard.press("Space");
  await expect
    .poll(async () => (await audioState(page))?.paused ?? false)
    .toBe(true);

  for (const { label, extension } of DOWNLOADS) {
    await tabUntil(page, { text: label }, 40);
    const pending = page.waitForEvent("download");
    await page.keyboard.press("Enter");
    const download = await pending;
    expect(download.suggestedFilename().endsWith(extension)).toBe(true);
    await expect(page.getByRole("button", { name: label })).toBeEnabled();
  }

  // History: the disclosure starts open at this viewport width, and its rows
  // follow the export controls in tab order.
  await tabUntil(page, { text: "History" }, 10);
  expect(
    await page
      .locator("details.history")
      .evaluate((element) => (element as HTMLDetailsElement).open),
  ).toBe(true);
  await tabUntil(page, { labelStartsWith: "Open generation:" }, 10);
  await page.keyboard.press("Enter");
  await expect(
    page.locator("audio[aria-label='Generated audio']"),
  ).toBeVisible();
  await expect(page.locator(".word-flow")).toContainText("Keyboard only");

  // Inline delete confirmation, still keyboard-only.
  await expect(historyRow(page, text)).toBeVisible();
  await tabUntil(page, { text: "Delete" }, 10);
  await page.keyboard.press("Enter");
  const prompt = page.getByText("Delete this entry? This cannot be undone.");
  await expect(prompt).toBeVisible();
  // The confirmation button takes focus as soon as it appears.
  await expect
    .poll(async () => (await focusedElement(page)).label)
    .toContain("Confirm delete generation:");
  await page.keyboard.press("Enter");
  await expect(prompt).toHaveCount(0);
  await expect(historyRow(page, text)).toHaveCount(0);

  await expect(errorBanner(page)).toHaveCount(0);
});
