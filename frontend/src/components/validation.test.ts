import { describe, expect, it } from "vitest";
import {
  MAX_INPUT_CHARS,
  clampRate,
  clampVolume,
  inputTooLongMessage,
  validateGeneration,
} from "./validation";

describe("clampRate", () => {
  it("clamps into the contract range", () => {
    expect(clampRate(0.1)).toBe(0.5);
    expect(clampRate(5)).toBe(2);
    expect(clampRate(1.26)).toBe(1.3);
    expect(clampRate(1)).toBe(1);
  });

  it("falls back to the default for non-numeric input", () => {
    expect(clampRate(Number.NaN)).toBe(1);
    expect(clampRate(Number.POSITIVE_INFINITY)).toBe(1);
  });
});

describe("clampVolume", () => {
  it("clamps into the contract range", () => {
    expect(clampVolume(-1)).toBe(0);
    expect(clampVolume(2)).toBe(1);
    expect(clampVolume(0.734)).toBe(0.73);
    expect(clampVolume(0.5)).toBe(0.5);
  });

  it("falls back to the default for non-numeric input", () => {
    expect(clampVolume(Number.NaN)).toBe(1);
  });
});

describe("validateGeneration", () => {
  it("blocks empty and whitespace-only input without a request (AC4)", () => {
    expect(validateGeneration("", "en_US-lessac-medium")?.code).toBe("EMPTY_INPUT");
    expect(validateGeneration("   \n\t ", "en_US-lessac-medium")?.code).toBe("EMPTY_INPUT");
  });

  it("warns before the server limit is exceeded", () => {
    const text = "a".repeat(MAX_INPUT_CHARS + 1);
    const problem = validateGeneration(text, "en_US-lessac-medium");
    expect(problem).toMatchObject({
      code: "INPUT_TOO_LONG",
      message: inputTooLongMessage(text.length),
      details: { maxChars: MAX_INPUT_CHARS, receivedChars: text.length },
    });
  });

  it("explains the remedy when no voice is installed", () => {
    const problem = validateGeneration("Hello", null);
    expect(problem?.code).toBe("NO_VOICES_INSTALLED");
    expect(problem?.message).toContain("tts add-voice");
  });

  it("allows a valid request", () => {
    expect(validateGeneration("Hello world.", "en_US-lessac-medium")).toBeNull();
  });
});
