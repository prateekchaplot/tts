import { describe, expect, it } from "vitest";
import type { WordTiming } from "../types/contracts";
import { clampSeconds, findActiveWordIndex, firstWordIndexAtOrAfter } from "./usePlayback";

const TIMINGS: WordTiming[] = [
  { text: "One", startMs: 0, endMs: 400, aligned: true },
  { text: "two", startMs: 500, endMs: 900, aligned: true },
  { text: "three", startMs: 900, endMs: 1200, aligned: false },
];

describe("findActiveWordIndex", () => {
  it("returns -1 for an empty list", () => {
    expect(findActiveWordIndex([], 0)).toBe(-1);
  });

  it("returns -1 before the first word", () => {
    expect(findActiveWordIndex(TIMINGS, -1)).toBe(-1);
  });

  it("includes the start and end boundaries of a word", () => {
    expect(findActiveWordIndex(TIMINGS, 0)).toBe(0);
    expect(findActiveWordIndex(TIMINGS, 400)).toBe(0);
    expect(findActiveWordIndex(TIMINGS, 500)).toBe(1);
    expect(findActiveWordIndex(TIMINGS, 900)).toBe(2);
    expect(findActiveWordIndex(TIMINGS, 1200)).toBe(2);
  });

  it("returns -1 inside a gap between words", () => {
    expect(findActiveWordIndex(TIMINGS, 450)).toBe(-1);
    expect(findActiveWordIndex(TIMINGS, 1250)).toBe(-1);
  });

  it("returns -1 for non-finite times", () => {
    expect(findActiveWordIndex(TIMINGS, Number.NaN)).toBe(-1);
    expect(findActiveWordIndex(TIMINGS, Number.POSITIVE_INFINITY)).toBe(-1);
  });

  it("matches a linear scan over a long timing list", () => {
    const long: WordTiming[] = Array.from({ length: 257 }, (_, index) => ({
      text: `w${index}`,
      startMs: index * 300,
      endMs: index * 300 + 250,
      aligned: index % 5 !== 0,
    }));
    const linear = (timeMs: number): number => {
      let found = -1;
      for (let index = 0; index < long.length; index += 1) {
        if (long[index].startMs <= timeMs) {
          found = index;
        }
      }
      if (found < 0) {
        return -1;
      }
      return timeMs <= long[found].endMs ? found : -1;
    };
    for (let timeMs = -50; timeMs < 77_000; timeMs += 37) {
      expect(findActiveWordIndex(long, timeMs)).toBe(linear(timeMs));
    }
  });
});

describe("firstWordIndexAtOrAfter", () => {
  it("returns -1 for an empty list", () => {
    expect(firstWordIndexAtOrAfter([], 0)).toBe(-1);
  });

  it("finds the exact word at a cue start", () => {
    expect(firstWordIndexAtOrAfter(TIMINGS, 0)).toBe(0);
    expect(firstWordIndexAtOrAfter(TIMINGS, 500)).toBe(1);
  });

  it("finds the next word when a time falls before it", () => {
    expect(firstWordIndexAtOrAfter(TIMINGS, 450)).toBe(1);
  });

  it("falls back to the last word when the time is past the end", () => {
    expect(firstWordIndexAtOrAfter(TIMINGS, 99_000)).toBe(2);
  });
});

describe("clampSeconds", () => {
  it("keeps values inside the audio duration", () => {
    expect(clampSeconds(3, 10)).toBe(3);
    expect(clampSeconds(-2, 10)).toBe(0);
    expect(clampSeconds(20, 10)).toBe(10);
  });

  it("only enforces a lower bound when the duration is unknown", () => {
    expect(clampSeconds(5, Number.NaN)).toBe(5);
    expect(clampSeconds(5, 0)).toBe(5);
    expect(clampSeconds(Number.NaN, 10)).toBe(0);
  });
});
