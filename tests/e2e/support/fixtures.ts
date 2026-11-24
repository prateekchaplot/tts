/**
 * Fixture access. Everything the suite uploads lives under
 * `tests/e2e/fixtures`, inside this task's owned area (ARCHITECTURE.md
 * section 14.2).
 */

import { readFileSync } from "node:fs";
import path from "node:path";

export const FIXTURES_DIR = path.join(__dirname, "..", "fixtures");

export function fixturePath(...parts: string[]): string {
  return path.join(FIXTURES_DIR, ...parts);
}

/** UTF-8 text of a fixture; CRLF is normalised so assertions are stable. */
export function readFixtureText(name: string): string {
  const bytes = readFileSync(fixturePath("texts", name));
  return new TextDecoder("utf-8").decode(bytes).replace(/\r\n/g, "\n");
}
