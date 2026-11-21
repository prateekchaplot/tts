/**
 * Playback panel (ARCHITECTURE.md sections 10.3 and 12, FR-06/FR-07).
 *
 * Reads the current generation from the app store and embeds the subtitle view
 * and download bar. The panel renders an explicit ready state instead of
 * assuming audio exists: GenerateBar can dispatch a succeeded entry without an
 * `audioUrl` when the detail or blob fetch fails (T3.1 downstream contract).
 */

import { useEffect } from "react";
import { usePlayback } from "../hooks/usePlayback";
import { useApp, type CurrentGeneration } from "../state/appContext";
import { DownloadBar } from "./DownloadBar";
import { formatClock, SubtitleView } from "./SubtitleView";

/** Why playback is not available yet; null when there is something to play. */
export function playbackMessage(current: CurrentGeneration | null): string | null {
  if (current === null) {
    return "Generate audio to play it back here.";
  }
  switch (current.status) {
    case "succeeded":
      return current.detail === undefined
        ? "Finished, but the details could not be loaded. Check the message above."
        : null;
    case "failed":
      return "Nothing to play: the generation failed. See the message above.";
    case "cancelled":
      return "Nothing to play: the generation was cancelled.";
    default:
      return "Playback appears here when generation finishes.";
  }
}

/**
 * Space and the arrow keys must not hijack typing or activation of another
 * control, so interactive targets keep their native behavior.
 */
export function isInteractiveTarget(target: unknown): boolean {
  if (target === null || typeof target !== "object") {
    return false;
  }
  const element = target as { tagName?: unknown; isContentEditable?: unknown };
  if (element.isContentEditable === true) {
    return true;
  }
  const tag = typeof element.tagName === "string" ? element.tagName.toUpperCase() : "";
  return (
    tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "BUTTON" || tag === "A"
  );
}

export function PlaybackPanel() {
  const { state } = useApp();
  const current = state.current;
  const detail = current?.detail ?? null;
  const wordTimings = detail?.wordTimings ?? null;
  const cues = detail?.cues ?? null;
  const { audioRef, activeIndex, isPlaying, toggle, skip, seekToWord } = usePlayback(wordTimings);

  const audioUrl = current?.audioUrl;
  const audioReady = audioUrl !== undefined && detail !== null;
  const message = playbackMessage(current);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (
        !audioReady ||
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        isInteractiveTarget(event.target)
      ) {
        return;
      }
      if (event.key === " " || event.key === "Spacebar") {
        event.preventDefault();
        toggle();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        skip(-5);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        skip(5);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [audioReady, skip, toggle]);

  const duration =
    detail !== null && detail.durationSeconds !== null
      ? `${formatClock(detail.durationSeconds * 1000)} long`
      : null;
  const aligned =
    detail !== null && detail.alignedWordRatio !== null && detail.alignedWordRatio >= 0
      ? `${Math.round(detail.alignedWordRatio * 100)}% of words timed`
      : null;

  return (
    <section className="section" aria-labelledby="playback-heading">
      <h2 id="playback-heading">Playback and subtitles</h2>

      {message !== null ? <p className="stat">{message}</p> : null}

      {detail !== null && current?.status === "succeeded" ? (
        <>
          {audioReady && audioUrl !== undefined ? (
            <audio
              ref={audioRef}
              src={audioUrl}
              controls
              preload="metadata"
              aria-label="Generated audio"
            />
          ) : (
            <p className="stat warning">
              The audio file could not be loaded, so playback is unavailable. Downloads may still
              work.
            </p>
          )}

          <div className="button-row playback-controls">
            <button
              type="button"
              disabled={!audioReady}
              onClick={toggle}
              aria-label={isPlaying ? "Pause audio" : "Play audio"}
            >
              {isPlaying ? "Pause" : "Play"}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!audioReady}
              onClick={() => {
                skip(-5);
              }}
            >
              Back 5 s
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!audioReady}
              onClick={() => {
                skip(5);
              }}
            >
              Forward 5 s
            </button>
            {duration !== null || aligned !== null ? (
              <p className="stat playback-meta">
                {[duration, aligned].filter((part) => part !== null).join(" · ")}
              </p>
            ) : null}
          </div>

          <p className="hint">
            Keyboard: Space plays or pauses, Left and Right arrows skip 5 seconds when focus is
            outside a control. Click a word or a sentence to jump there.
          </p>

          <SubtitleView
            wordTimings={wordTimings}
            cues={cues}
            activeIndex={activeIndex}
            onSeekWord={seekToWord}
          />

          <DownloadBar detail={detail} />
        </>
      ) : null}
    </section>
  );
}
