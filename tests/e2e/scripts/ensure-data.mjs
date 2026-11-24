/**
 * Seeds an E2E data directory with the Piper voice before `tts` starts.
 *
 * Both E2E servers need `voices/` in their data directory: the main one so the
 * UI lists a voice without a first-run download, the fault-armed one (AC11) so
 * it can render its first sentence and then trip the injected fault. Copying
 * the developer's cached voice keeps the suite offline and fast.
 *
 * Inputs (set by playwright.config.ts):
 *   TTS_E2E_SEED_DIR    - data directory to seed
 *   TTS_E2E_SEED_SOURCE - existing voices directory to copy from
 *
 * Exits 0 when the directory already holds a voice, when a copy succeeded, or
 * when no source exists (the server then bootstraps the default voice).
 */

import { cpSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import path from "node:path";

const target = process.env["TTS_E2E_SEED_DIR"];
const source = process.env["TTS_E2E_SEED_SOURCE"];

if (!target) {
  console.error("ensure-data: TTS_E2E_SEED_DIR is required");
  process.exit(1);
}

const voices = path.join(target, "voices");
const hasVoice = () =>
  existsSync(voices) &&
  readdirSync(voices).some((name) => name.endsWith(".onnx"));

if (hasVoice()) {
  process.exit(0);
}

mkdirSync(voices, { recursive: true });

if (
  source &&
  existsSync(source) &&
  readdirSync(source).some((name) => name.endsWith(".onnx"))
) {
  cpSync(source, voices, { recursive: true });
  console.log(`ensure-data: copied voices into ${voices}`);
  process.exit(0);
}

console.log(
  `ensure-data: no voice source at ${source ?? "(unset)"}; the server will bootstrap one.`,
);
