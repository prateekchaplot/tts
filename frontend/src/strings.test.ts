import { describe, expect, it } from "vitest";
import { errorGuidance, strings } from "./strings";

/** The fixed section 9.1 error codes (mirrors `src/tts/api/errors.py`). */
const ERROR_CODES = [
  "EMPTY_INPUT",
  "INPUT_TOO_LONG",
  "OUT_OF_RANGE",
  "VOICE_NOT_FOUND",
  "UNSUPPORTED_FILE_TYPE",
  "FILE_TOO_LARGE",
  "DECODE_FAILED",
  "NO_VOICES_INSTALLED",
  "GENERATION_NOT_FOUND",
  "GENERATION_NOT_READY",
  "GENERATION_BUSY",
  "SUBTITLE_FORMAT_UNKNOWN",
  "NOT_FOUND",
  "ENGINE_ERROR",
  "INTERNAL_ERROR",
];

describe("errorGuidance", () => {
  const fallback = errorGuidance("SOMETHING_NOT_IN_THE_FIXED_SET");

  it("gives specific advice for every fixed API error code", () => {
    for (const code of ERROR_CODES) {
      const guidance = errorGuidance(code);
      expect(guidance.length).toBeGreaterThan(20);
      expect(guidance).not.toBe(fallback);
      expect(guidance).toMatch(/\.$/);
    }
  });

  it("states an action rather than restating the problem", () => {
    const action = /^(Reload|Try|Run|Wait|Pick|Check|Save|Shorten|Paste|Upload|Open|Re-save|Use)\b/;
    for (const code of ERROR_CODES) {
      expect(errorGuidance(code)).toMatch(action);
    }
  });

  it("falls back for unknown codes", () => {
    expect(fallback.length).toBeGreaterThan(20);
    expect(fallback).toMatch(/^Try again\./);
  });
});

describe("strings", () => {
  it("counts history entries with correct pluralisation", () => {
    expect(strings.history.countLabel(0)).toBe("0 saved generations");
    expect(strings.history.countLabel(1)).toBe("1 saved generation");
    expect(strings.history.countLabel(20)).toBe("20 saved generations");
  });

  it("builds the character budget line with and without a file name", () => {
    expect(strings.input.characterCount(0, 50_000, null)).toBe("0 / 50,000 characters");
    expect(strings.input.characterCount(42, 50_000, "notes.txt")).toBe(
      "42 / 50,000 characters · loaded from notes.txt",
    );
  });

  it("keeps the frozen history aria-label contracts (T5.1 AC13)", () => {
    expect(strings.history.openLabel("Hello")).toBe("Open generation: Hello");
    expect(strings.history.deleteLabel("Hello")).toBe("Delete generation: Hello");
  });

  it("uses distinct labels for the delete confirmation step", () => {
    expect(strings.history.confirmDeleteLabel("Hello")).toBe("Confirm delete generation: Hello");
    expect(strings.history.keepLabel("Hello")).toBe("Keep generation: Hello");
    expect(strings.history.confirmDelete).not.toBe(strings.history.delete);
    expect(strings.history.confirmPrompt).toContain("cannot be undone");
  });

  it("formats playback metadata", () => {
    expect(strings.playback.duration("00:04")).toBe("00:04 long");
    expect(strings.playback.aligned(91)).toBe("91% of words timed");
  });

  it("builds cue jump labels with the timestamp first", () => {
    expect(strings.subtitles.jumpLabel("00:12", "Hello brave")).toBe("Jump to 00:12: Hello brave");
  });
});
