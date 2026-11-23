/**
 * Voice selection, preview, and speech settings (ARCHITECTURE.md section 12,
 * FR-02/FR-03). The last-used settings are persisted through `putSettings` on
 * blur so the next visit starts where the user left off.
 */

import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { toApiError } from "../api/client";
import { strings } from "../strings";
import { useApp } from "../state/appContext";
import { RATE_RANGE, VOLUME_RANGE } from "../types/contracts";
import type { Voice } from "../types/contracts";
import { clampRate, clampVolume } from "./validation";

/** Option label: name, language, and gender where the engine exposes it. */
export function voiceLabel(voice: Voice): string {
  const parts = [voice.name, voice.language];
  if (voice.gender !== null) {
    parts.push(voice.gender);
  }
  return parts.join(" · ");
}

export function VoicePanel() {
  const { state, dispatch } = useApp();
  const [previewing, setPreviewing] = useState(false);
  const previewUrlRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const hasVoices = state.voices.length > 0;

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      audioRef.current = null;
      if (previewUrlRef.current !== null) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }
    };
  }, []);

  function releasePreview(): void {
    if (previewUrlRef.current !== null) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    audioRef.current = null;
  }

  function dispatchFailure(error: unknown): void {
    const failure = toApiError(error);
    dispatch({
      type: "SET_ERROR",
      error: { code: failure.code, message: failure.message, details: failure.details },
    });
  }

  function persistSettings(): void {
    if (!hasVoices) {
      return;
    }
    api
      .putSettings({
        rate: state.rate,
        volume: state.volume,
        ...(state.selectedVoiceId === null ? {} : { defaultVoiceId: state.selectedVoiceId }),
      })
      .catch((error: unknown) => {
        dispatchFailure(error);
      });
  }

  async function handlePreview(): Promise<void> {
    if (state.selectedVoiceId === null) {
      return;
    }
    setPreviewing(true);
    try {
      const blob = await api.previewVoice(state.selectedVoiceId);
      audioRef.current?.pause();
      releasePreview();

      const url = URL.createObjectURL(blob);
      previewUrlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      const finish = (): void => {
        releasePreview();
        setPreviewing(false);
      };
      audio.addEventListener("ended", finish);
      audio.addEventListener("error", finish);
      await audio.play();
    } catch (error) {
      releasePreview();
      setPreviewing(false);
      dispatchFailure(error);
    }
  }

  return (
    <section className="section" aria-labelledby="voice-heading">
      <h2 id="voice-heading">{strings.voice.heading}</h2>

      {hasVoices ? (
        <p className="hint">{strings.voice.hint}</p>
      ) : (
        <p className="stat warning">
          {strings.voice.noVoicesPrefix} <code>tts add-voice &lt;name&gt;</code>{" "}
          {strings.voice.noVoicesSuffix}
        </p>
      )}

      <div className="field">
        <label htmlFor="voice-select">{strings.voice.selectLabel}</label>
        <div className="field-row">
          <select
            id="voice-select"
            value={state.selectedVoiceId ?? ""}
            disabled={!hasVoices}
            onChange={(event) => {
              dispatch({ type: "SET_VOICE", voiceId: event.target.value });
            }}
            onBlur={persistSettings}
          >
            {hasVoices ? (
              state.voices.map((voice) => (
                <option key={voice.id} value={voice.id}>
                  {voiceLabel(voice)}
                </option>
              ))
            ) : (
              <option value="">{strings.voice.noVoicesOption}</option>
            )}
          </select>
          <button
            type="button"
            disabled={!hasVoices || state.selectedVoiceId === null || previewing}
            onClick={() => {
              void handlePreview();
            }}
          >
            {previewing ? strings.voice.previewing : strings.voice.preview}
          </button>
        </div>
      </div>

      <div className="field">
        <div className="slider-row">
          <label htmlFor="rate-slider">{strings.voice.rateLabel}</label>
          <input
            id="rate-slider"
            type="range"
            min={RATE_RANGE.min}
            max={RATE_RANGE.max}
            step={0.1}
            value={state.rate}
            aria-describedby="rate-value"
            onChange={(event) => {
              dispatch({ type: "SET_RATE", rate: clampRate(Number(event.target.value)) });
            }}
            onBlur={persistSettings}
          />
          <output id="rate-value" htmlFor="rate-slider">
            {state.rate.toFixed(1)}×
          </output>
        </div>

        <div className="slider-row">
          <label htmlFor="volume-slider">{strings.voice.volumeLabel}</label>
          <input
            id="volume-slider"
            type="range"
            min={VOLUME_RANGE.min}
            max={VOLUME_RANGE.max}
            step={0.05}
            value={state.volume}
            aria-describedby="volume-value"
            onChange={(event) => {
              dispatch({ type: "SET_VOLUME", volume: clampVolume(Number(event.target.value)) });
            }}
            onBlur={persistSettings}
          />
          <output id="volume-value" htmlFor="volume-slider">
            {Math.round(state.volume * 100)}%
          </output>
        </div>
      </div>
    </section>
  );
}
