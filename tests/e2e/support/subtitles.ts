/**
 * SRT/VTT parsing for AC10 ("the downloaded subtitle file loads in a standard
 * player or caption tool, and its cue timing matches the generated audio").
 *
 * The renderers in `src/tts/subtitles` emit SRT blocks with an index line and
 * VTT blocks without one, separated by a blank line, so a small block parser
 * covers both.
 */

export interface SubtitleCue {
  startMs: number;
  endMs: number;
  text: string;
}

const TIMING_LINE =
  /^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/;

function toMillis(
  hours: string,
  minutes: string,
  seconds: string,
  millis: string,
): number {
  return (
    Number(hours) * 3_600_000 +
    Number(minutes) * 60_000 +
    Number(seconds) * 1000 +
    Number(millis)
  );
}

function parseBlocks(text: string): SubtitleCue[] {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (normalized.length === 0) {
    return [];
  }
  const cues: SubtitleCue[] = [];
  for (const block of normalized.split(/\n{2,}/)) {
    const lines = block.split("\n").map((line) => line.trim());
    const timingIndex = lines.findIndex((line) => TIMING_LINE.test(line));
    if (timingIndex < 0) {
      // `WEBVTT` header or another non-cue block.
      continue;
    }
    const match = TIMING_LINE.exec(lines[timingIndex] ?? "");
    if (match === null) {
      continue;
    }
    cues.push({
      startMs: toMillis(
        match[1] ?? "0",
        match[2] ?? "0",
        match[3] ?? "0",
        match[4] ?? "0",
      ),
      endMs: toMillis(
        match[5] ?? "0",
        match[6] ?? "0",
        match[7] ?? "0",
        match[8] ?? "0",
      ),
      text: lines
        .slice(timingIndex + 1)
        .join(" ")
        .trim(),
    });
  }
  return cues;
}

export function parseSrt(text: string): SubtitleCue[] {
  return parseBlocks(text);
}

export function parseVtt(text: string): SubtitleCue[] {
  if (!text.replace(/\r\n/g, "\n").startsWith("WEBVTT")) {
    throw new Error("VTT file does not start with WEBVTT");
  }
  return parseBlocks(text);
}
