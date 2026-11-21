import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Cue, WordTiming } from "../types/contracts";
import { formatClock, SubtitleView } from "./SubtitleView";

const TIMINGS: WordTiming[] = [
  { text: "Hello", startMs: 0, endMs: 400, aligned: true },
  { text: "brave", startMs: 500, endMs: 900, aligned: true },
  { text: "world", startMs: 900, endMs: 1400, aligned: false },
];

const CUES: Cue[] = [
  { index: 1, startMs: 0, endMs: 900, text: "Hello brave" },
  { index: 2, startMs: 1400, endMs: 2000, text: "world" },
];

function render(activeIndex = -1, wordTimings: WordTiming[] | null = TIMINGS): string {
  return renderToStaticMarkup(
    <SubtitleView
      wordTimings={wordTimings}
      cues={CUES}
      activeIndex={activeIndex}
      onSeekWord={() => undefined}
    />,
  );
}

describe("formatClock", () => {
  it("formats minutes and seconds, adding hours only when needed", () => {
    expect(formatClock(0)).toBe("00:00");
    expect(formatClock(65_000)).toBe("01:05");
    expect(formatClock(3_725_000)).toBe("1:02:05");
  });

  it("clamps negative values to zero", () => {
    expect(formatClock(-10)).toBe("00:00");
  });
});

describe("SubtitleView", () => {
  it("renders every word and marks the active one", () => {
    const html = render(1);
    expect(html).toContain("Hello");
    expect(html).toContain("brave");
    expect(html).toContain("world");
    expect(html).toContain('class="word active"');
  });

  it("marks words without reliable alignment", () => {
    expect(render()).toContain('class="word unaligned"');
    expect(render()).toContain("Timing estimated from nearby words");
  });

  it("renders a keyboard-reachable button per cue with its timestamp", () => {
    const html = render();
    expect(html).toContain('class="cue"');
    expect(html).toContain("00:00");
    expect(html).toContain("00:01");
    expect(html).toContain("Jump to 00:00: Hello brave");
  });

  it("explains the degraded state when there are no timings", () => {
    const html = render(-1, null);
    expect(html).toContain("Timing details are unavailable");
    expect(html).not.toContain('class="word');
    expect(html).toContain("<button");
    expect(html).toContain("disabled");
  });
});
