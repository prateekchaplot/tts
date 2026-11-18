import { describe, expect, it } from "vitest";
import type { GenerationDetail, GenerationSummary, Voice } from "../types/contracts";
import { appReducer, initialState, type AppState } from "./appContext";

const voice: Voice = {
  id: "en_US-lessac-medium",
  name: "en_US-lessac-medium",
  language: "en_US",
  gender: null,
  sampleRate: 22050,
};

const summary: GenerationSummary = {
  generationId: "6f0c8e2a-0000-4000-8000-000000000001",
  status: "succeeded",
  createdAt: "2026-11-17T14:25:30Z",
  sourceType: "text",
  inputPreview: "Hello world.",
  inputFilename: null,
  voiceId: voice.id,
  voiceName: voice.name,
  rate: 1,
  volume: 1,
  durationSeconds: 1.2,
  error: null,
};

const detail: GenerationDetail = {
  ...summary,
  text: "Hello world.",
  sampleRate: 22050,
  alignedWordRatio: 1,
  wordTimings: [
    { text: "Hello", startMs: 0, endMs: 500, aligned: true },
    { text: "world.", startMs: 500, endMs: 1200, aligned: true },
  ],
  cues: [{ index: 1, startMs: 0, endMs: 1200, text: "Hello world." }],
};

function withError(state: AppState): AppState {
  return appReducer(state, {
    type: "SET_ERROR",
    error: { code: "INTERNAL_ERROR", message: "boom", details: null },
  });
}

describe("appReducer", () => {
  it("starts empty with the documented defaults", () => {
    expect(initialState).toMatchObject({
      inputText: "",
      sourceFilename: null,
      voices: [],
      selectedVoiceId: null,
      rate: 1,
      volume: 1,
      current: null,
      history: { items: [], total: 0 },
      error: null,
    });
  });

  it("sets input and clears a previous error", () => {
    const next = appReducer(withError(initialState), { type: "SET_INPUT", text: "Hello" });
    expect(next.inputText).toBe("Hello");
    expect(next.error).toBeNull();
  });

  it("tracks the source filename", () => {
    const next = appReducer(initialState, { type: "SET_SOURCE_FILE", filename: "notes.txt" });
    expect(next.sourceFilename).toBe("notes.txt");
    expect(appReducer(next, { type: "SET_SOURCE_FILE", filename: null }).sourceFilename).toBeNull();
  });

  it("selects the first voice when none was selected", () => {
    const next = appReducer(initialState, { type: "VOICES_LOADED", voices: [voice] });
    expect(next.selectedVoiceId).toBe(voice.id);
  });

  it("keeps a still-installed selection and drops a removed one", () => {
    const selected = appReducer(initialState, { type: "SET_VOICE", voiceId: voice.id });
    expect(appReducer(selected, { type: "VOICES_LOADED", voices: [voice] }).selectedVoiceId).toBe(
      voice.id,
    );

    const other = { ...voice, id: "de_DE-thorsten-medium", language: "de_DE" };
    expect(appReducer(selected, { type: "VOICES_LOADED", voices: [other] }).selectedVoiceId).toBe(
      other.id,
    );
  });

  it("handles empty voice lists", () => {
    const next = appReducer(appReducer(initialState, { type: "SET_VOICE", voiceId: voice.id }), {
      type: "VOICES_LOADED",
      voices: [],
    });
    expect(next.selectedVoiceId).toBeNull();
  });

  it("sets voice, rate, and volume", () => {
    const next = appReducer(
      appReducer(appReducer(initialState, { type: "SET_VOICE", voiceId: voice.id }), {
        type: "SET_RATE",
        rate: 1.5,
      }),
      { type: "SET_VOLUME", volume: 0.4 },
    );
    expect(next.selectedVoiceId).toBe(voice.id);
    expect(next.rate).toBe(1.5);
    expect(next.volume).toBe(0.4);
  });

  it("creates a current generation and clears errors", () => {
    const next = appReducer(withError(initialState), {
      type: "GENERATION_CREATED",
      id: summary.generationId,
      status: "queued",
    });
    expect(next.current).toEqual({
      id: summary.generationId,
      status: "queued",
      sentenceIndex: 0,
      sentenceCount: 0,
    });
    expect(next.error).toBeNull();
  });

  it("applies progress only to the current generation", () => {
    const created = appReducer(initialState, {
      type: "GENERATION_CREATED",
      id: summary.generationId,
      status: "queued",
    });
    const progress = appReducer(created, {
      type: "GENERATION_PROGRESS",
      id: summary.generationId,
      status: "running",
      sentenceIndex: 3,
      sentenceCount: 12,
    });
    expect(progress.current).toMatchObject({
      status: "running",
      sentenceIndex: 3,
      sentenceCount: 12,
    });

    const ignored = appReducer(progress, {
      type: "GENERATION_PROGRESS",
      id: "other",
      status: "running",
      sentenceIndex: 4,
      sentenceCount: 12,
    });
    expect(ignored).toBe(progress);
  });

  it("stores detail and audio on success", () => {
    const created = appReducer(initialState, {
      type: "GENERATION_CREATED",
      id: summary.generationId,
      status: "running",
    });
    const next = appReducer(created, {
      type: "GENERATION_SUCCEEDED",
      id: summary.generationId,
      detail,
      audioUrl: "blob:local/1",
    });
    expect(next.current).toMatchObject({
      id: summary.generationId,
      status: "succeeded",
      detail,
      audioUrl: "blob:local/1",
    });
  });

  it("ignores success for a different generation", () => {
    const created = appReducer(initialState, {
      type: "GENERATION_CREATED",
      id: "other",
      status: "running",
    });
    expect(
      appReducer(created, { type: "GENERATION_SUCCEEDED", id: summary.generationId, detail }),
    ).toBe(created);
  });

  it("surfaces a failure as the banner error", () => {
    const created = appReducer(initialState, {
      type: "GENERATION_CREATED",
      id: summary.generationId,
      status: "running",
    });
    const next = appReducer(created, {
      type: "GENERATION_FAILED",
      id: summary.generationId,
      error: { code: "ENGINE_ERROR", message: "synthesis failed" },
    });
    expect(next.current?.status).toBe("failed");
    expect(next.error).toEqual({
      code: "ENGINE_ERROR",
      message: "synthesis failed",
      details: null,
    });
  });

  it("marks a cancelled generation", () => {
    const created = appReducer(initialState, {
      type: "GENERATION_CREATED",
      id: summary.generationId,
      status: "running",
    });
    expect(
      appReducer(created, { type: "GENERATION_CANCELLED", id: summary.generationId }).current
        ?.status,
    ).toBe("cancelled");
  });

  it("selects a history item into the current generation", () => {
    const next = appReducer(initialState, {
      type: "SELECT_HISTORY_ITEM",
      detail,
      audioUrl: "blob:local/2",
    });
    expect(next.current).toMatchObject({
      id: summary.generationId,
      status: "succeeded",
      detail,
      audioUrl: "blob:local/2",
    });
    expect(next.error).toBeNull();
  });

  it("loads the history list", () => {
    const next = appReducer(initialState, {
      type: "HISTORY_LOADED",
      items: [summary],
      total: 1,
    });
    expect(next.history).toEqual({ items: [summary], total: 1 });
  });

  it("deletes one history entry and clears a matching selection", () => {
    const loaded = appReducer(initialState, {
      type: "HISTORY_LOADED",
      items: [summary, { ...summary, generationId: "other" }],
      total: 2,
    });
    const selected = appReducer(loaded, { type: "SELECT_HISTORY_ITEM", detail });

    const next = appReducer(selected, { type: "HISTORY_DELETED", id: summary.generationId });
    expect(next.history.items.map((item) => item.generationId)).toEqual(["other"]);
    expect(next.history.total).toBe(1);
    expect(next.current).toBeNull();
  });

  it("leaves the total alone when deleting an unknown id", () => {
    const loaded = appReducer(initialState, { type: "HISTORY_LOADED", items: [summary], total: 1 });
    const next = appReducer(loaded, { type: "HISTORY_DELETED", id: "missing" });
    expect(next.history).toEqual({ items: [summary], total: 1 });
  });

  it("sets and clears the banner error", () => {
    const failed = withError(initialState);
    expect(failed.error?.message).toBe("boom");
    expect(appReducer(failed, { type: "CLEAR_ERROR" }).error).toBeNull();
  });
});
