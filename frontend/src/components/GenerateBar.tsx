/**
 * Generate/cancel controls and progress (ARCHITECTURE.md section 12, FR-04).
 *
 * This is the only component that opens the SSE stream: it maps stream events
 * to reducer actions and loads the detail + audio blob on success, as the
 * "Data fetching" contract in section 12 requires.
 */

import { useEffect, useRef } from "react";
import { api } from "../api";
import { toApiError } from "../api/client";
import { strings } from "../strings";
import { useApp, type CurrentGeneration } from "../state/appContext";
import type { GenerationDetail, GenerationStreamEvent } from "../types/contracts";
import { validateGeneration } from "./validation";

function statusLabel(current: CurrentGeneration | null): string {
  if (current === null) {
    return strings.generate.statusEmpty;
  }
  switch (current.status) {
    case "queued":
      return strings.generate.statusQueued;
    case "running":
      return current.sentenceCount > 0
        ? strings.generate.statusGenerating(current.sentenceIndex, current.sentenceCount)
        : strings.generate.statusGeneratingUnknown;
    case "cancelling":
      return strings.generate.statusCancelling;
    case "succeeded":
      return current.detail === undefined
        ? strings.generate.statusMissingDetail
        : strings.generate.statusReady;
    case "failed":
      return strings.generate.statusFailed;
    case "cancelled":
      return strings.generate.statusCancelled;
  }
}

function isActive(current: CurrentGeneration | null): boolean {
  return (
    current !== null &&
    (current.status === "queued" || current.status === "running" || current.status === "cancelling")
  );
}

export function GenerateBar() {
  const { state, dispatch } = useApp();
  const closeStreamRef = useRef<(() => void) | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const currentIdRef = useRef<string | null>(null);
  const progressRef = useRef({ sentenceIndex: 0, sentenceCount: 0 });
  const current = state.current;

  useEffect(() => {
    currentIdRef.current = current?.id ?? null;
    progressRef.current = {
      sentenceIndex: current?.sentenceIndex ?? 0,
      sentenceCount: current?.sentenceCount ?? 0,
    };
  }, [current]);

  useEffect(() => {
    return () => {
      closeStreamRef.current?.();
      closeStreamRef.current = null;
      if (audioUrlRef.current !== null) {
        URL.revokeObjectURL(audioUrlRef.current);
        audioUrlRef.current = null;
      }
    };
  }, []);

  function closeStream(): void {
    closeStreamRef.current?.();
    closeStreamRef.current = null;
  }

  function releaseAudio(): void {
    if (audioUrlRef.current !== null) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  }

  function dispatchFailure(error: unknown): void {
    const failure = toApiError(error);
    dispatch({
      type: "SET_ERROR",
      error: { code: failure.code, message: failure.message, details: failure.details },
    });
  }

  async function loadResult(generationId: string): Promise<void> {
    let detail: GenerationDetail;
    try {
      detail = await api.getGeneration(generationId);
    } catch (error) {
      dispatchFailure(error);
      if (currentIdRef.current === generationId) {
        dispatch({
          type: "GENERATION_PROGRESS",
          id: generationId,
          status: "succeeded",
          ...progressRef.current,
        });
      }
      return;
    }

    let audioUrl: string | undefined;
    try {
      const blob = await api.getAudioBlob(generationId);
      if (currentIdRef.current !== generationId) {
        return;
      }
      audioUrl = URL.createObjectURL(blob);
    } catch (error) {
      dispatchFailure(error);
    }

    if (currentIdRef.current !== generationId) {
      if (audioUrl !== undefined) {
        URL.revokeObjectURL(audioUrl);
      }
      return;
    }
    if (audioUrl !== undefined) {
      releaseAudio();
      audioUrlRef.current = audioUrl;
    }
    dispatch({ type: "GENERATION_SUCCEEDED", id: generationId, detail, audioUrl });
  }

  async function handleStreamEvent(event: GenerationStreamEvent): Promise<void> {
    switch (event.type) {
      case "progress":
        dispatch({
          type: "GENERATION_PROGRESS",
          id: event.payload.generationId,
          status: event.payload.status,
          sentenceIndex: event.payload.sentenceIndex,
          sentenceCount: event.payload.sentenceCount,
        });
        return;
      case "cancelled":
        closeStream();
        dispatch({ type: "GENERATION_CANCELLED", id: event.payload.generationId });
        return;
      case "failed":
        closeStream();
        dispatch({
          type: "GENERATION_FAILED",
          id: event.payload.generationId,
          error: event.payload.error,
        });
        return;
      case "succeeded":
        closeStream();
        await loadResult(event.payload.generationId);
        return;
    }
  }

  async function handleGenerate(): Promise<void> {
    const problem = validateGeneration(state.inputText, state.selectedVoiceId);
    if (problem !== null) {
      dispatch({ type: "SET_ERROR", error: problem });
      return;
    }

    closeStream();
    releaseAudio();
    try {
      const status = await api.createGeneration({
        text: state.inputText,
        voiceId: state.selectedVoiceId ?? undefined,
        rate: state.rate,
        volume: state.volume,
      });
      dispatch({ type: "GENERATION_CREATED", id: status.generationId, status: status.status });
      currentIdRef.current = status.generationId;
      progressRef.current = { sentenceIndex: 0, sentenceCount: 0 };
      closeStreamRef.current = api.openEventStream(status.generationId, (event) => {
        void handleStreamEvent(event);
      });
    } catch (error) {
      dispatchFailure(error);
    }
  }

  async function handleCancel(): Promise<void> {
    const current = state.current;
    if (current === null || current.status === "cancelling") {
      return;
    }
    try {
      const status = await api.cancelGeneration(current.id);
      if (status.status === "cancelled") {
        closeStream();
        dispatch({ type: "GENERATION_CANCELLED", id: current.id });
        return;
      }
      dispatch({
        type: "GENERATION_PROGRESS",
        id: current.id,
        status: status.status,
        sentenceIndex: current.sentenceIndex,
        sentenceCount: current.sentenceCount,
      });
    } catch (error) {
      dispatchFailure(error);
    }
  }

  const active = isActive(current);
  const hasVoices = state.voices.length > 0;

  return (
    <section className="section" aria-labelledby="generate-heading" aria-busy={active}>
      <h2 id="generate-heading">{strings.generate.heading}</h2>

      {hasVoices ? (
        <p className="hint">{strings.generate.hint}</p>
      ) : (
        <p className="stat warning">
          {strings.generate.noVoicesPrefix} <code>tts add-voice &lt;name&gt;</code>{" "}
          {strings.generate.noVoicesSuffix}
        </p>
      )}

      <p className="stat" aria-live="polite">
        {statusLabel(current)}
      </p>
      {active && current !== null && current.sentenceCount > 0 ? (
        <progress
          aria-label={strings.generate.progressLabel}
          aria-valuetext={`${current.sentenceIndex} of ${current.sentenceCount} sentences`}
          value={current.sentenceIndex}
          max={current.sentenceCount}
        />
      ) : null}

      <div className="button-row">
        <button
          type="button"
          disabled={active || !hasVoices}
          onClick={() => {
            void handleGenerate();
          }}
        >
          {strings.generate.generate}
        </button>
        {active ? (
          <button
            type="button"
            className="secondary"
            disabled={current?.status === "cancelling"}
            onClick={() => {
              void handleCancel();
            }}
          >
            {current?.status === "cancelling"
              ? strings.generate.cancelling
              : strings.generate.cancel}
          </button>
        ) : null}
      </div>
    </section>
  );
}
