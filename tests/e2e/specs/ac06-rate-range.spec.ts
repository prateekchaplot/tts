/**
 * AC6 (PRD section 8): a rate outside the supported range is prevented or
 * corrected with a visible value, and generation never proceeds with an
 * out-of-range value.
 *
 * Two attack paths are exercised: keyboard driving of the native range control
 * (cannot leave the range) and a DOM-level write that bypasses the browser's
 * slider (React re-clamps it, ARCHITECTURE.md section 12's `clampRate`).
 */

import { expect, test } from "@playwright/test";
import { uniqueText } from "../support/run";
import {
  errorBanner,
  openApp,
  READY_STATUS,
  waitForStatus,
} from "../support/ui";

test("AC6: out-of-range rate is corrected and never sent", async ({ page }) => {
  await openApp(page);

  const rate = page.locator("#rate-slider");
  const volume = page.locator("#volume-slider");
  expect(await rate.getAttribute("min")).toBe("0.5");
  expect(await rate.getAttribute("max")).toBe("2");
  expect(await volume.getAttribute("min")).toBe("0");
  expect(await volume.getAttribute("max")).toBe("1");

  await rate.focus();
  await page.keyboard.press("End");
  await expect(rate).toHaveValue("2");
  await expect(page.locator("#rate-value")).toHaveText("2.0×");
  await page.keyboard.press("Home");
  await expect(rate).toHaveValue("0.5");
  await expect(page.locator("#rate-value")).toHaveText("0.5×");

  // Bypass the input's own min/max: the app must still clamp.
  await page.evaluate(() => {
    const slider = document.querySelector("#rate-slider");
    if (!(slider instanceof HTMLInputElement)) {
      throw new Error("rate slider missing");
    }
    slider.value = "9";
    slider.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(rate).toHaveValue("2");
  await expect(page.locator("#rate-value")).toHaveText("2.0×");

  await volume.focus();
  await page.keyboard.press("Home");
  await expect(volume).toHaveValue("0");
  await page.evaluate(() => {
    const slider = document.querySelector("#volume-slider");
    if (!(slider instanceof HTMLInputElement)) {
      throw new Error("volume slider missing");
    }
    slider.value = "4";
    slider.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(volume).toHaveValue("1");
  await expect(page.locator("#volume-value")).toHaveText("100%");

  await page.locator("#input-text").fill(uniqueText("Range check."));
  const posted = page.waitForRequest(
    (request) =>
      request.method() === "POST" && request.url().endsWith("/api/generations"),
  );
  await page.getByRole("button", { name: "Generate audio" }).click();
  const request = await posted;
  const payload = JSON.parse(request.postData() ?? "{}") as {
    rate: number;
    volume: number;
  };
  expect(payload.rate).toBeGreaterThanOrEqual(0.5);
  expect(payload.rate).toBeLessThanOrEqual(2);
  expect(payload.volume).toBeGreaterThanOrEqual(0);
  expect(payload.volume).toBeLessThanOrEqual(1);

  await waitForStatus(page, READY_STATUS);
  await expect(errorBanner(page)).toHaveCount(0);
});
