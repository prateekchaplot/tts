/**
 * AC10 (PRD section 8): the downloaded subtitle files load in a standard player
 * or caption tool, and their cue timing matches the generated audio.
 *
 * The specs parse the actual downloaded bytes (not the API body) and compare
 * every cue against the generation detail the audio was rendered from.
 */

import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { getGeneration } from "../support/api";
import { uniqueText } from "../support/run";
import { parseSrt, parseVtt } from "../support/subtitles";
import { generateInUi, openApp } from "../support/ui";

/**
 * Piper pads each sentence with leading silence, so the first word - and the
 * first cue derived from it - starts a little after the file begins. Anything
 * beyond this bound would mean the cue is offset from the audio rather than
 * tracking it.
 */
const MAX_FIRST_CUE_START_MS = 1000;

async function downloadText(
  page: Page,
  label: string,
): Promise<{ name: string; text: string }> {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: label }).click();
  const download = await pending;
  const filePath = await download.path();
  expect(filePath).not.toBeNull();
  return {
    name: download.suggestedFilename(),
    text: new TextDecoder("utf-8").decode(readFileSync(filePath ?? "")),
  };
}

test("AC10: downloaded SRT/VTT parse and match the audio timing", async ({
  page,
  request,
}) => {
  await openApp(page);

  const text = uniqueText(
    "Hello world. This is a subtitle check. Cue timing must match the audio.",
  );
  const generationId = await generateInUi(page, text);
  const detail = await getGeneration(request, generationId);
  const cues = detail.cues ?? [];
  expect(cues.length).toBeGreaterThan(0);
  const durationMs = (detail.durationSeconds ?? 0) * 1000;

  const srtFile = await downloadText(page, "Download subtitles (SRT)");
  const vttFile = await downloadText(page, "Download subtitles (VTT)");

  expect(srtFile.name).toMatch(
    /^hello-world-this-is-a-subtitle_\d{8}-\d{6}\.srt$/,
  );
  expect(vttFile.name).toMatch(
    /^hello-world-this-is-a-subtitle_\d{8}-\d{6}\.vtt$/,
  );

  const srt = parseSrt(srtFile.text);
  const vtt = parseVtt(vttFile.text);

  expect(srt.length).toBe(cues.length);
  expect(vtt.length).toBe(cues.length);

  for (const [index, cue] of cues.entries()) {
    expect(srt[index]?.startMs).toBe(cue.startMs);
    expect(srt[index]?.endMs).toBe(cue.endMs);
    expect(srt[index]?.text).toBe(cue.text);
    expect(vtt[index]?.startMs).toBe(cue.startMs);
    expect(vtt[index]?.endMs).toBe(cue.endMs);
    expect(vtt[index]?.text).toBe(cue.text);
  }

  // What a caption tool checks: begins at the start of the audio, monotonic,
  // inside the audio. The first cue follows the first audible word rather than
  // snapping to zero, so it may sit inside piper's leading silence.
  for (const captions of [srt, vtt]) {
    expect(captions[0]?.startMs ?? -1).toBeGreaterThanOrEqual(0);
    expect(captions[0]?.startMs ?? Infinity).toBeLessThanOrEqual(
      MAX_FIRST_CUE_START_MS,
    );
    for (let index = 1; index < captions.length; index += 1) {
      const previous = captions[index - 1];
      const current = captions[index];
      expect(current?.startMs ?? 0).toBeGreaterThanOrEqual(
        (previous?.endMs ?? 0) - 1,
      );
    }
    expect(captions[captions.length - 1]?.endMs ?? 0).toBeLessThanOrEqual(
      durationMs + 50,
    );
  }
});
