/**
 * UI helpers shared by the acceptance specs.
 *
 * Locators are text- and role-based on purpose: the specs then double as a
 * check of the labels frozen by T2.2/T3.3/T4.2 (ARCHITECTURE.md sections 9.2
 * and 12) instead of binding to CSS-only hooks.
 */

import { expect, type Page } from "@playwright/test";
import { MAIN_URL } from "./env";

export const READY_STATUS = "Audio ready.";
export const CANCELLED_STATUS = "Generation cancelled. No audio was saved.";
export const FAILED_STATUS = "Generation failed. See the message above.";

/** Opens the app and waits for its bootstrap (voices listed, no mock badge). */
export async function openApp(
  page: Page,
  baseUrl: string = MAIN_URL,
): Promise<void> {
  await page.goto(baseUrl);
  await expect(
    page.getByRole("heading", { level: 1, name: "tts" }),
  ).toBeVisible();
  await expect(page.getByText("Mock mode: sample data")).toHaveCount(0);
  await expect(page.locator("#voice-select")).toBeEnabled();
  await expect(page.locator("#voice-select option").first()).toBeAttached();
}

/** The generate section's status line. */
export function generateStatus(page: Page) {
  return page.locator(
    "section[aria-labelledby='generate-heading'] p[aria-live='polite']",
  );
}

/** The error banner (role `alert`, ARCHITECTURE.md section 11). */
export function errorBanner(page: Page) {
  return page.getByRole("alert");
}

/** One history row, found by text that only this generation contains. */
export function historyRow(page: Page, text: string) {
  return page.locator(".history-item").filter({ hasText: text }).first();
}

/** Clicks Generate and returns the id from the 202 response. */
export async function startGeneration(page: Page): Promise<string> {
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/generations") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate audio" }).click();
  const response = await created;
  expect(response.status()).toBe(202);
  const body = (await response.json()) as { generationId: string };
  return body.generationId;
}

export async function waitForStatus(
  page: Page,
  expected: string | RegExp,
  timeout = 180_000,
): Promise<void> {
  await expect(generateStatus(page)).toHaveText(expected, { timeout });
}

/** Fills the input, generates, and waits for playback to become available. */
export async function generateInUi(page: Page, text: string): Promise<string> {
  await page.locator("#input-text").fill(text);
  const generationId = await startGeneration(page);
  await waitForStatus(page, READY_STATUS);
  await expect(
    page.locator("audio[aria-label='Generated audio']"),
  ).toBeVisible();
  return generationId;
}

export interface AudioState {
  currentTime: number;
  duration: number;
  paused: boolean;
  readyState: number;
}

export async function audioState(page: Page): Promise<AudioState | null> {
  return page.evaluate(() => {
    const element = document.querySelector("audio");
    if (element === null) {
      return null;
    }
    return {
      currentTime: element.currentTime,
      duration: element.duration,
      paused: element.paused,
      readyState: element.readyState,
    };
  });
}

/** Index of the highlighted word, or -1 when nothing is highlighted. */
export async function activeWordIndex(page: Page): Promise<number> {
  return page.evaluate(() => {
    const words = Array.from(document.querySelectorAll(".word-flow .word"));
    return words.findIndex((word) => word.classList.contains("active"));
  });
}

export interface FocusedElement {
  tag: string;
  id: string;
  label: string;
  text: string;
}

export async function focusedElement(page: Page): Promise<FocusedElement> {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!(element instanceof HTMLElement)) {
      return { tag: "", id: "", label: "", text: "" };
    }
    return {
      tag: element.tagName,
      id: element.id,
      label: element.getAttribute("aria-label") ?? "",
      text: (element.textContent ?? "").trim(),
    };
  });
}

export interface FocusMatcher {
  tag?: string;
  id?: string;
  text?: string;
  label?: string;
  labelStartsWith?: string;
}

function focusMatches(element: FocusedElement, matcher: FocusMatcher): boolean {
  if (matcher.tag !== undefined && element.tag !== matcher.tag) {
    return false;
  }
  if (matcher.id !== undefined && element.id !== matcher.id) {
    return false;
  }
  if (matcher.text !== undefined && element.text !== matcher.text) {
    return false;
  }
  if (matcher.label !== undefined && element.label !== matcher.label) {
    return false;
  }
  if (
    matcher.labelStartsWith !== undefined &&
    !element.label.startsWith(matcher.labelStartsWith)
  ) {
    return false;
  }
  return true;
}

/**
 * Tabs forward until the focused element matches, so keyboard specs describe
 * intent ("reach Play") without hard-coding a tab-stop count that changes with
 * copy or markup.
 */
export async function tabUntil(
  page: Page,
  matcher: FocusMatcher,
  maxTabs = 40,
): Promise<FocusedElement> {
  let previous = "";
  let repeats = 0;
  for (let index = 0; index < maxTabs; index += 1) {
    await page.keyboard.press("Tab");
    const focused = await focusedElement(page);
    if (focusMatches(focused, matcher)) {
      return focused;
    }
    // A native media element holds focus across several Tab presses while its
    // own controls cycle; anything longer than that means Tab is trapped.
    const key = `${focused.tag}|${focused.id}|${focused.label}|${focused.text}`;
    repeats = key === previous ? repeats + 1 : 0;
    previous = key;
    if (repeats >= 8) {
      throw new Error(
        `Tab appears trapped on ${JSON.stringify(focused)} while looking for ${JSON.stringify(matcher)}`,
      );
    }
  }
  throw new Error(
    `No focusable element matched ${JSON.stringify(matcher)} after ${maxTabs} tabs; last focus: ${JSON.stringify(await focusedElement(page))}`,
  );
}

export interface NetworkGuard {
  /** Every non-local URL the page tried to reach; must stay empty. */
  external: string[];
}

function isLocalUrl(rawUrl: string): boolean {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return true;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return true;
  }
  return (
    url.hostname === "127.0.0.1" ||
    url.hostname === "localhost" ||
    url.hostname === "[::1]" ||
    url.hostname === "::1"
  );
}

/**
 * Aborts and records every outbound request that is not to a local server
 * (AC14, and the "machine offline" half of AC1 which CI cannot physically
 * disconnect). Install before `page.goto`.
 */
export async function installLocalOnlyNetwork(
  page: Page,
): Promise<NetworkGuard> {
  const external: string[] = [];
  await page.route("**/*", async (route) => {
    const url = route.request().url();
    if (isLocalUrl(url)) {
      await route.continue();
      return;
    }
    external.push(url);
    await route.abort("blockedbyclient");
  });
  return { external };
}

/** Origins of every resource the page fetched, for the AC14 cross-check. */
export async function resourceOrigins(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const origins = new Set<string>();
    for (const entry of performance.getEntriesByType("resource")) {
      try {
        origins.add(new URL(entry.name).origin);
      } catch {
        // Non-URL entries cannot be external.
      }
    }
    return Array.from(origins);
  });
}
