/**
 * Input validation and control clamping shared by the app shell (ARCHITECTURE.md
 * sections 9.2, 11, and 12). Pure functions so AC4 (empty input) and AC6 (rate
 * range) can be unit-tested without a DOM.
 */

import { RATE_RANGE, VOLUME_RANGE } from "../types/contracts";
import type { ErrorInfo } from "../types/contracts";

/**
 * Mirrors `TTS_MAX_INPUT_CHARS` (section 11). The server remains the authority:
 * this only warns the user before a request (FR-01).
 */
export const MAX_INPUT_CHARS = 50_000;

const EMPTY_INPUT_MESSAGE =
  "Enter some text before generating. Paste or upload text and try again.";

const NO_VOICES_INSTALLED_MESSAGE =
  "No voices are installed. Run `tts add-voice <name>` in a terminal, then reload this page.";

function round(value: number, factor: number): number {
  return Math.round(value * factor) / factor;
}

/** Clamps any numeric input into [0.5, 2.0] on the slider's 0.1 step. */
export function clampRate(value: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.min(RATE_RANGE.max, Math.max(RATE_RANGE.min, round(value, 10)));
}

/** Clamps any numeric input into [0.0, 1.0] on the slider's 0.01 step. */
export function clampVolume(value: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.min(VOLUME_RANGE.max, Math.max(VOLUME_RANGE.min, round(value, 100)));
}

/** Message for the FR-01 length warning, matching the server's wording. */
export function inputTooLongMessage(length: number): string {
  return `Input is ${length.toLocaleString()} characters; the limit is ${MAX_INPUT_CHARS.toLocaleString()}.`;
}

/**
 * Local pre-flight check. Returns the error to show without contacting the
 * server, or `null` when the request may proceed (satisfies AC4 and the
 * no-voice guidance of FR-02).
 */
export function validateGeneration(text: string, voiceId: string | null): ErrorInfo | null {
  if (text.trim().length === 0) {
    return { code: "EMPTY_INPUT", message: EMPTY_INPUT_MESSAGE, details: null };
  }
  if (text.length > MAX_INPUT_CHARS) {
    return {
      code: "INPUT_TOO_LONG",
      message: inputTooLongMessage(text.length),
      details: { maxChars: MAX_INPUT_CHARS, receivedChars: text.length },
    };
  }
  if (voiceId === null) {
    return { code: "NO_VOICES_INSTALLED", message: NO_VOICES_INSTALLED_MESSAGE, details: null };
  }
  return null;
}
