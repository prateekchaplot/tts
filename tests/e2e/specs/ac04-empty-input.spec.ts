/**
 * AC4 (PRD section 8): generating with empty input shows a validation message
 * and sends no request. The check is local, so nothing reaches the server.
 */

import { expect, test } from "@playwright/test";
import { errorBanner, generateStatus, openApp } from "../support/ui";

test("AC4: empty input is caught before a request", async ({ page }) => {
  await openApp(page);

  const posts: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST") {
      posts.push(`${request.method()} ${request.url()}`);
    }
  });

  await page.getByRole("button", { name: "Generate audio" }).click();

  const banner = errorBanner(page);
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Enter some text before generating");
  await expect(banner).toContainText("What you can do");
  await expect(generateStatus(page)).toHaveText("Nothing generated yet");
  expect(posts).toEqual([]);

  // Whitespace-only input is empty too.
  await page.locator("#input-text").fill("   \n\t  ");
  await page.getByRole("button", { name: "Generate audio" }).click();
  await expect(banner).toContainText("Enter some text before generating");
  expect(posts).toEqual([]);
});
