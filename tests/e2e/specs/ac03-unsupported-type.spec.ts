/**
 * AC3 (PRD section 8): an unsupported upload is rejected with a message naming
 * the accepted type, and no generation starts.
 */

import { expect, test } from "@playwright/test";
import { fixturePath } from "../support/fixtures";
import { errorBanner, generateStatus, openApp } from "../support/ui";

test("AC3: an unsupported upload names the accepted type", async ({ page }) => {
  await openApp(page);

  const generationPosts: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().endsWith("/api/generations")
    ) {
      generationPosts.push(request.url());
    }
  });

  await page
    .locator("#input-file")
    .setInputFiles(fixturePath("unsupported.md"));

  const banner = errorBanner(page);
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Unsupported file type");
  await expect(banner).toContainText("only plain-text .txt files are accepted");
  await expect(banner).toContainText("What you can do");
  await expect(banner).toContainText("plain .txt file");

  await expect(page.locator("#input-text")).toHaveValue("");
  await expect(generateStatus(page)).toHaveText("Nothing generated yet");
  expect(generationPosts).toEqual([]);
});
