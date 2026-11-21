import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppProvider, type CurrentGeneration } from "../state/appContext";
import type { GenerationDetail } from "../types/contracts";
import { isInteractiveTarget, playbackMessage, PlaybackPanel } from "./PlaybackPanel";

const DETAIL: GenerationDetail = {
  generationId: "11111111-1111-4111-8111-111111111111",
  status: "succeeded",
  createdAt: "2026-11-20T19:04:45Z",
  sourceType: "text",
  inputPreview: "Hello world.",
  inputFilename: null,
  voiceId: "en_US-lessac-medium",
  voiceName: "Lessac",
  rate: 1,
  volume: 1,
  durationSeconds: 1,
  error: null,
  text: "Hello world.",
  sampleRate: 22050,
  alignedWordRatio: 1,
  wordTimings: [{ text: "Hello", startMs: 0, endMs: 400, aligned: true }],
  cues: [{ index: 1, startMs: 0, endMs: 400, text: "Hello" }],
};

function current(overrides: Partial<CurrentGeneration>): CurrentGeneration {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    status: "succeeded",
    sentenceIndex: 0,
    sentenceCount: 0,
    ...overrides,
  };
}

describe("playbackMessage", () => {
  it("prompts for a generation when nothing exists yet", () => {
    expect(playbackMessage(null)).toContain("Generate audio");
  });

  it("has no message for a succeeded entry with details", () => {
    expect(playbackMessage(current({ detail: DETAIL }))).toBeNull();
  });

  it("explains a succeeded entry whose details are missing", () => {
    expect(playbackMessage(current({ detail: undefined }))).toContain(
      "details could not be loaded",
    );
  });

  it("explains failed, cancelled, and in-progress entries", () => {
    expect(playbackMessage(current({ status: "failed" }))).toContain("failed");
    expect(playbackMessage(current({ status: "cancelled" }))).toContain("cancelled");
    expect(playbackMessage(current({ status: "running" }))).toContain("when generation finishes");
  });
});

describe("isInteractiveTarget", () => {
  it("keeps native behavior for form controls and links", () => {
    for (const tagName of ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "a"]) {
      expect(isInteractiveTarget({ tagName })).toBe(true);
    }
    expect(isInteractiveTarget({ isContentEditable: true })).toBe(true);
  });

  it("allows shortcuts on non-interactive targets", () => {
    expect(isInteractiveTarget(null)).toBe(false);
    expect(isInteractiveTarget({ tagName: "DIV" })).toBe(false);
    expect(isInteractiveTarget({})).toBe(false);
  });
});

describe("PlaybackPanel", () => {
  it("renders the section heading and the empty state", () => {
    const html = renderToStaticMarkup(
      <AppProvider>
        <PlaybackPanel />
      </AppProvider>,
    );
    expect(html).toContain("Playback and subtitles");
    expect(html).toContain("Generate audio to play it back here.");
    expect(html).not.toContain("<audio");
  });
});
