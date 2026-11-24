/**
 * Environment and path constants for the Playwright suite (ARCHITECTURE.md
 * sections 14.2 T5.1 and 15).
 *
 * The suite runs against a real `tts` server and the real Piper voice. It never
 * touches the user's own data directory: locally the data lives in the
 * gitignored `.venv/e2e-data`, in CI under `$RUNNER_TEMP` where the workflow
 * already keeps the cached voice.
 */

import { existsSync } from "node:fs";
import path from "node:path";

/** Repository root (`tests/e2e/support` -> three levels up). */
export const REPO_ROOT = path.resolve(__dirname, "../../..");

const RUNNER_TEMP = process.env["RUNNER_TEMP"];

/**
 * Data directory of the server the UI talks to. In CI the workflow starts the
 * server with `TTS_DATA_DIR=$RUNNER_TEMP/tts-data` before Playwright runs, so
 * the same convention is mirrored here.
 */
export const MAIN_DATA_DIR =
  process.env["TTS_E2E_DATA_DIR"] ??
  (RUNNER_TEMP === undefined
    ? path.join(REPO_ROOT, ".venv", "e2e-data")
    : path.join(RUNNER_TEMP, "tts-data"));

/**
 * Data directory of the fault-armed server used by AC11. It is kept separate
 * so a deliberately failed generation never writes to the main database.
 */
export const FAULT_DATA_DIR =
  process.env["TTS_E2E_FAULT_DATA_DIR"] ??
  (RUNNER_TEMP === undefined
    ? path.join(REPO_ROOT, ".venv", "e2e-fault-data")
    : path.join(RUNNER_TEMP, "tts-e2e-fault-data"));

/**
 * Directory the E2E servers copy `voices/` from when their own data dir has
 * none. Locally that is the developer's voice store, which the integration
 * suite already uses; in CI it is the cache the workflow restores into the
 * main data directory, so the fault server can start without a download.
 */
function voiceSource(): string {
  const explicit = process.env["TTS_E2E_VOICE_SOURCE"];
  if (explicit !== undefined && explicit.length > 0) {
    return explicit;
  }
  const candidates = [
    path.join(REPO_ROOT, ".venv", "tts-data", "voices"),
    path.join(MAIN_DATA_DIR, "voices"),
  ];
  return (
    candidates.find((candidate) => existsSync(candidate)) ?? candidates[0]!
  );
}

export const VOICE_SOURCE = voiceSource();

export const MAIN_PORT = process.env["TTS_E2E_PORT"] ?? "8321";
export const FAULT_PORT = process.env["TTS_E2E_FAULT_PORT"] ?? "8322";
export const MAIN_URL = `http://127.0.0.1:${MAIN_PORT}`;
export const FAULT_URL = `http://127.0.0.1:${FAULT_PORT}`;

/**
 * Python that has `tts` installed. Locally the repo virtualenv wins; CI runs
 * `pip install -e .` into the interpreter on PATH.
 */
function pythonCommand(): string {
  const explicit = process.env["TTS_E2E_PYTHON"];
  if (explicit !== undefined && explicit.length > 0) {
    return explicit;
  }
  const venvPython =
    process.platform === "win32"
      ? path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")
      : path.join(REPO_ROOT, ".venv", "bin", "python");
  if (existsSync(venvPython)) {
    return venvPython;
  }
  // CI has no repository virtualenv: `pip install -e .` targets the interpreter
  // that `actions/setup-python` puts first on PATH.
  return process.platform === "win32" ? "python" : "python3";
}

export const PYTHON = pythonCommand();

/** Voice the suite generates with; the default of the shipped configuration. */
export const VOICE_ID = "en_US-lessac-medium";

/**
 * Word-start tolerance for AC7, in milliseconds.
 *
 * ARCHITECTURE.md section 15 hands the final number to T5.3 (measurement). Until
 * that report exists this uses assumption A-3's ±100 ms target; T5.3 confirms
 * or revises it and this constant follows.
 */
export const WORD_START_TOLERANCE_MS = 100;
