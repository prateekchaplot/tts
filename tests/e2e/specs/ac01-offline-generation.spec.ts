/**
 * AC1 (PRD section 8): pasted multi-paragraph text generates playable audio
 * with no outbound network request.
 *
 * CI cannot physically disconnect the machine, so "offline" is proven the way
 * ARCHITECTURE.md section 15 prescribes: every request is intercepted, and any
 * non-local one is aborted and recorded. AC14 repeats the guard across the full
 * export workflow; this spec covers generation and playback.
 */

import { expect, test } from "@playwright/test";
import { getGeneration } from "../support/api";
import { uniqueText } from "../support/run";
import {
  audioState,
  generateInUi,
  installLocalOnlyNetwork,
  openApp,
  resourceOrigins,
} from "../support/ui";

test("AC1: generation and playback make no outbound request", async ({
  page,
  request,
}) => {
  const network = await installLocalOnlyNetwork(page);
  await openApp(page);

  const text = uniqueText(
    "Hello world. This is the offline acceptance check.\n\nParagraph breaks are preserved.",
  );
  const generationId = await generateInUi(page, text);

  const before = await audioState(page);
  expect(before).not.toBeNull();
  expect(before?.duration ?? 0).toBeGreaterThan(0.5);

  await page.getByRole("button", { name: "Play audio" }).click();
  await expect
    .poll(async () => (await audioState(page))?.currentTime ?? 0, {
      timeout: 30_000,
    })
    .toBeGreaterThan(0.2);
  await page.getByRole("button", { name: "Pause audio" }).click();

  const detail = await getGeneration(request, generationId);
  expect(detail.status).toBe("succeeded");
  expect(detail.durationSeconds ?? 0).toBeGreaterThan(0.5);
  expect(detail.wordTimings?.length ?? 0).toBeGreaterThan(0);

  expect(network.external).toEqual([]);
  const origins = await resourceOrigins(page);
  expect(
    origins.filter((origin) => !origin.startsWith("http://127.0.0.1")),
  ).toEqual([]);
});
