/**
 * Word highlighting, click-to-seek, and sentence cues
 * (ARCHITECTURE.md sections 10.3 and 12, FR-06).
 *
 * Presentational: the parent owns the `<audio>` element and playback state.
 */

import { useEffect, useRef } from "react";
import { firstWordIndexAtOrAfter } from "../hooks/usePlayback";
import { strings } from "../strings";
import type { Cue, WordTiming } from "../types/contracts";

export interface SubtitleViewProps {
  wordTimings: readonly WordTiming[] | null;
  cues: readonly Cue[] | null;
  activeIndex: number;
  onSeekWord: (index: number) => void;
}

/** `mm:ss` timeline label; hours are added only when needed. */
export function formatClock(milliseconds: number): string {
  const safe = Math.max(0, Math.round(milliseconds));
  const hours = Math.floor(safe / 3_600_000);
  const minutes = Math.floor((safe % 3_600_000) / 60_000);
  const seconds = Math.floor((safe % 60_000) / 1000);
  const pad = (value: number): string => String(value).padStart(2, "0");
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`;
}

export function SubtitleView({ wordTimings, cues, activeIndex, onSeekWord }: SubtitleViewProps) {
  const activeRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    // Instant scroll: the highlight transition is already disabled under
    // `prefers-reduced-motion` (styles.css), and smooth scrolling would fight
    // the ~60 ms highlight cadence.
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "auto" });
  }, [activeIndex]);

  const hasWords = wordTimings !== null && wordTimings.length > 0;
  const playableCues = cues !== null && cues.length > 0 ? cues : [];

  return (
    <div className="subtitle-view">
      {hasWords ? (
        <p className="word-flow" aria-label={strings.subtitles.wordsLabel}>
          {wordTimings.map((word, index) => {
            const classes = ["word"];
            if (index === activeIndex) {
              classes.push("active");
            }
            if (!word.aligned) {
              classes.push("unaligned");
            }
            return (
              <span key={`${index}-${word.startMs}`}>
                <span
                  ref={index === activeIndex ? activeRef : undefined}
                  className={classes.join(" ")}
                  title={word.aligned ? undefined : strings.subtitles.unalignedTitle}
                  onClick={() => {
                    onSeekWord(index);
                  }}
                >
                  {word.text}
                </span>{" "}
              </span>
            );
          })}
        </p>
      ) : (
        <p className="stat warning">{strings.subtitles.noTimings}</p>
      )}

      {playableCues.length > 0 ? (
        <div className="cue-block">
          <h3>{strings.subtitles.sentencesHeading}</h3>
          <ol className="cue-list">
            {playableCues.map((cue) => {
              const firstWord =
                wordTimings === null ? -1 : firstWordIndexAtOrAfter(wordTimings, cue.startMs);
              return (
                <li key={`${cue.index}-${cue.startMs}`}>
                  <button
                    type="button"
                    className="cue"
                    disabled={firstWord < 0}
                    aria-label={strings.subtitles.jumpLabel(formatClock(cue.startMs), cue.text)}
                    onClick={() => {
                      onSeekWord(firstWord);
                    }}
                  >
                    <span className="cue-time">{formatClock(cue.startMs)}</span>
                    <span className="cue-text">{cue.text}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      ) : null}
    </div>
  );
}
