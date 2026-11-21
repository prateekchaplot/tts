/**
 * Playback synchronization (ARCHITECTURE.md section 10.3 and section 12).
 *
 * Owns the `<audio>` element binding, the requestAnimationFrame highlight
 * loop, the binary search for the active word, and seeking. The pure helpers
 * are exported so they can be unit-tested without a DOM.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { WordTiming } from "../types/contracts";

/**
 * Index of the last word whose `startMs <= timeMs`, or -1 when the time falls
 * before the first word, after the word's `endMs`, or inside a gap.
 */
export function findActiveWordIndex(timings: readonly WordTiming[], timeMs: number): number {
  if (timings.length === 0 || !Number.isFinite(timeMs)) {
    return -1;
  }
  let low = 0;
  let high = timings.length - 1;
  let found = -1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    if (timings[mid].startMs <= timeMs) {
      found = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  if (found < 0) {
    return -1;
  }
  return timeMs <= timings[found].endMs ? found : -1;
}

/**
 * Word a cue or a seek belongs to: the first word that starts at or after
 * `timeMs`. Falls back to the last word when the time is past the end.
 */
export function firstWordIndexAtOrAfter(timings: readonly WordTiming[], timeMs: number): number {
  if (timings.length === 0) {
    return -1;
  }
  let low = 0;
  let high = timings.length;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (timings[mid].startMs < timeMs) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  return low < timings.length ? low : timings.length - 1;
}

/** Clamps a seek target into `[0, durationSeconds]` when the duration is known. */
export function clampSeconds(seconds: number, durationSeconds: number): number {
  if (!Number.isFinite(seconds)) {
    return 0;
  }
  if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    return Math.max(0, seconds);
  }
  return Math.min(Math.max(0, seconds), durationSeconds);
}

export interface PlaybackControls {
  /** Callback ref for the `<audio>` element. */
  audioRef: (node: HTMLAudioElement | null) => void;
  activeIndex: number;
  isPlaying: boolean;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seekTo: (seconds: number) => void;
  /** Seeks by a signed offset, used by the ±5 s keyboard shortcuts. */
  skip: (deltaSeconds: number) => void;
  seekToWord: (index: number) => void;
}

export function usePlayback(wordTimings: readonly WordTiming[] | null): PlaybackControls {
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const timingsRef = useRef<readonly WordTiming[]>(wordTimings ?? []);
  const elementRef = useRef<HTMLAudioElement | null>(null);
  const detachRef = useRef<(() => void) | null>(null);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    timingsRef.current = wordTimings ?? [];
  }, [wordTimings]);

  const stopLoop = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  const refreshFromElement = useCallback((element: HTMLAudioElement) => {
    setActiveIndex(findActiveWordIndex(timingsRef.current, element.currentTime * 1000));
  }, []);

  const startLoop = useCallback(
    (element: HTMLAudioElement) => {
      stopLoop();
      const tick = (): void => {
        setActiveIndex(findActiveWordIndex(timingsRef.current, element.currentTime * 1000));
        frameRef.current = requestAnimationFrame(tick);
      };
      frameRef.current = requestAnimationFrame(tick);
    },
    [stopLoop],
  );

  const attachListeners = useCallback(
    (element: HTMLAudioElement) => {
      const handlePlay = (): void => {
        setIsPlaying(true);
        startLoop(element);
      };
      const handlePause = (): void => {
        setIsPlaying(false);
        stopLoop();
        refreshFromElement(element);
      };
      const handleEnded = (): void => {
        setIsPlaying(false);
        stopLoop();
        setActiveIndex(-1);
      };
      const handleSeek = (): void => {
        refreshFromElement(element);
      };

      element.addEventListener("play", handlePlay);
      element.addEventListener("playing", handlePlay);
      element.addEventListener("pause", handlePause);
      element.addEventListener("ended", handleEnded);
      element.addEventListener("timeupdate", handleSeek);
      element.addEventListener("seeking", handleSeek);
      element.addEventListener("seeked", handleSeek);
      element.addEventListener("loadedmetadata", handleSeek);
      element.addEventListener("emptied", handleSeek);

      detachRef.current = () => {
        element.removeEventListener("play", handlePlay);
        element.removeEventListener("playing", handlePlay);
        element.removeEventListener("pause", handlePause);
        element.removeEventListener("ended", handleEnded);
        element.removeEventListener("timeupdate", handleSeek);
        element.removeEventListener("seeking", handleSeek);
        element.removeEventListener("seeked", handleSeek);
        element.removeEventListener("loadedmetadata", handleSeek);
        element.removeEventListener("emptied", handleSeek);
        stopLoop();
      };
    },
    [refreshFromElement, startLoop, stopLoop],
  );

  const audioRef = useCallback(
    (node: HTMLAudioElement | null) => {
      detachRef.current?.();
      detachRef.current = null;
      elementRef.current = node;
      if (node !== null) {
        attachListeners(node);
      }
    },
    [attachListeners],
  );

  useEffect(() => {
    return () => {
      detachRef.current?.();
      detachRef.current = null;
      elementRef.current = null;
    };
  }, []);

  const play = useCallback(() => {
    const element = elementRef.current;
    if (element === null) {
      return;
    }
    void element.play().catch(() => {
      // The browser may reject playback; the native controls remain usable.
    });
  }, []);

  const pause = useCallback(() => {
    elementRef.current?.pause();
  }, []);

  const toggle = useCallback(() => {
    const element = elementRef.current;
    if (element === null) {
      return;
    }
    if (element.paused) {
      play();
    } else {
      pause();
    }
  }, [pause, play]);

  const seekTo = useCallback(
    (seconds: number) => {
      const element = elementRef.current;
      if (element === null) {
        return;
      }
      element.currentTime = clampSeconds(seconds, element.duration);
      refreshFromElement(element);
    },
    [refreshFromElement],
  );

  const skip = useCallback(
    (deltaSeconds: number) => {
      const element = elementRef.current;
      if (element === null) {
        return;
      }
      seekTo(element.currentTime + deltaSeconds);
    },
    [seekTo],
  );

  const seekToWord = useCallback(
    (index: number) => {
      const timing = timingsRef.current[index];
      if (timing === undefined) {
        return;
      }
      seekTo(timing.startMs / 1000);
      setActiveIndex(index);
    },
    [seekTo],
  );

  return {
    audioRef,
    activeIndex,
    isPlaying,
    play,
    pause,
    toggle,
    seekTo,
    skip,
    seekToWord,
  };
}
