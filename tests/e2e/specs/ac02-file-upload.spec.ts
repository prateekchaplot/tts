/**
 * AC2 (PRD section 8): an uploaded plain-text file fills the input view, stays
 * editable, and generates audio like typed input. Uploading on its own never
 * starts a generation (ARCHITECTURE.md section 9.2).
 */

import { expect, test } from "@playwright/test";
import { fixturePath } from "../support/fixtures";
import {
  startGeneration,
  openApp,
  READY_STATUS,
  waitForStatus,
} from "../support/ui";

test("AC2: an uploaded plain-text file behaves like typed input", async ({
  page,
}) => {
  await openApp(page);

  await page
    .locator("#input-file")
    .setInputFiles(fixturePath("texts", "sample-200.txt"));

  const input = page.locator("#input-text");
  await expect(page.getByText("loaded from sample-200.txt")).toBeVisible();
  await expect(input).toHaveValue(
    /proves the upload path reaches the same input box/,
  );
  await expect(page.locator("#input-count")).toContainText("characters");

  // Editable: append a sentence by keyboard before generating.
  await input.press("End");
  await page.keyboard.type(" Edited by hand.");
  await expect(input).toHaveValue(/Edited by hand\.$/);

  // The generation is the explicit second step, not part of the upload.
  await expect(page.locator("audio[aria-label='Generated audio']")).toHaveCount(
    0,
  );
  await startGeneration(page);
  await waitForStatus(page, READY_STATUS);
  await expect(
    page.locator("audio[aria-label='Generated audio']"),
  ).toBeVisible();
});
