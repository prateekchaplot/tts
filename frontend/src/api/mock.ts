/**
 * In-memory implementation of `ApiInterface` selected with `VITE_API_MODE=mock`.
 *
 * It mirrors the section 9 contracts with synthetic data so the UI tasks
 * (P3) can be built and tested before the HTTP routes exist. It is a
 * deliverable, not a test-only hack (section 15).
 */

import { ApiError, type ApiInterface, type ListGenerationsOptions } from "./client";
import type {
  Cue,
  ErrorDetails,
  ErrorCode,
  GenerationCreateRequest,
  GenerationDetail,
  GenerationList,
  GenerationProgress,
  GenerationStatus,
  GenerationStreamEvent,
  GenerationSummary,
  Health,
  Settings,
  SettingsPatch,
  SubtitleFormat,
  UploadResult,
  Voice,
  VoiceList,
  WordTiming,
} from "../types/contracts";
import { RATE_RANGE, VOLUME_RANGE } from "../types/contracts";

const SAMPLE_RATE = 22050;
const PREVIEW_SECONDS = 0.6;
const MAX_INPUT_CHARS = 50000;
const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
const INPUT_PREVIEW_CHARS = 120;

export const MOCK_VOICES: Voice[] = [
  {
    id: "en_US-lessac-medium",
    name: "en_US-lessac-medium",
    language: "en_US",
    gender: null,
    sampleRate: SAMPLE_RATE,
  },
  {
    id: "de_DE-thorsten-medium",
    name: "de_DE-thorsten-medium",
    language: "de_DE",
    gender: null,
    sampleRate: SAMPLE_RATE,
  },
];

export const MOCK_DEFAULT_VOICE_ID = "en_US-lessac-medium";

type Subscriber = (event: GenerationStreamEvent) => void;

interface StoredGeneration {
  summary: GenerationSummary;
  detail: GenerationDetail;
  pendingText: string;
  sentenceCount: number;
}

function lastOrNull<T>(items: readonly T[]): T | null {
  return items.length === 0 ? null : (items[items.length - 1] as T);
}

function durationOf(timings: WordTiming[]): number {
  const last = lastOrNull(timings);
  return last === null ? 0 : last.endMs / 1000;
}

function fail(
  status: number,
  code: ErrorCode,
  message: string,
  details: ErrorDetails = null,
): ApiError {
  return new ApiError(status, { code, message, details });
}

function cloneVoiceList(voices: Voice[], defaultVoiceId: string): VoiceList {
  const items = [...voices]
    .sort((a, b) => a.language.localeCompare(b.language) || a.id.localeCompare(b.id))
    .map((voice) => ({ ...voice }));
  return { items, total: items.length, defaultVoiceId };
}

function cloneDetail(detail: GenerationDetail): GenerationDetail {
  return {
    ...detail,
    error: detail.error === null ? null : { ...detail.error },
    wordTimings:
      detail.wordTimings === null ? null : detail.wordTimings.map((word) => ({ ...word })),
    cues: detail.cues === null ? null : detail.cues.map((cue) => ({ ...cue })),
  };
}

function buildWordTimings(text: string): WordTiming[] {
  const words = text
    .trim()
    .split(/\s+/)
    .filter((word) => word.length > 0);
  let cursor = 0;
  return words.map((word) => {
    const duration = 220 + Math.min(word.length, 10) * 45;
    const timing: WordTiming = {
      text: word,
      startMs: cursor,
      endMs: cursor + duration,
      aligned: true,
    };
    cursor += duration;
    return timing;
  });
}

function buildCues(timings: WordTiming[]): Cue[] {
  const cues: Cue[] = [];
  let current: WordTiming[] = [];
  const flush = (): void => {
    const first = current[0];
    const last = current[current.length - 1];
    if (first === undefined || last === undefined) {
      return;
    }
    cues.push({
      index: cues.length + 1,
      startMs: first.startMs,
      endMs: last.endMs,
      text: current.map((word) => word.text).join(" "),
    });
    current = [];
  };
  for (const timing of timings) {
    const start = current[0]?.startMs ?? timing.startMs;
    const candidateText = [...current.map((word) => word.text), timing.text].join(" ");
    const tooLong = candidateText.length > 84;
    const tooSlow = timing.endMs - start > 5000;
    if (current.length > 0 && (tooLong || tooSlow)) {
      flush();
    }
    current.push(timing);
  }
  flush();
  return cues;
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

/** Builds a valid RIFF/WAVE blob of silence, used for previews and audio. */
export function silentWav(durationSeconds: number, sampleRate = SAMPLE_RATE): Blob {
  const sampleCount = Math.max(1, Math.round(durationSeconds * sampleRate));
  const dataBytes = sampleCount * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataBytes, true);
  return new Blob([buffer], { type: "audio/wav" });
}

function formatTimestamp(milliseconds: number, separator: "," | "."): string {
  const safe = Math.max(0, Math.round(milliseconds));
  const hours = Math.floor(safe / 3_600_000);
  const minutes = Math.floor((safe % 3_600_000) / 60_000);
  const seconds = Math.floor((safe % 60_000) / 1000);
  const millis = safe % 1000;
  const pad = (value: number, length = 2): string => String(value).padStart(length, "0");
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}${separator}${pad(millis, 3)}`;
}

function formatSubtitles(cues: Cue[], format: SubtitleFormat): string {
  if (format === "vtt") {
    const blocks = cues.map(
      (cue) =>
        `${formatTimestamp(cue.startMs, ".")} --> ${formatTimestamp(cue.endMs, ".")}\n${cue.text}`,
    );
    return `WEBVTT\n\n${blocks.join("\n\n")}\n`;
  }
  const blocks = cues.map(
    (cue) =>
      `${cue.index}\n${formatTimestamp(cue.startMs, ",")} --> ${formatTimestamp(cue.endMs, ",")}\n${cue.text}`,
  );
  return `${blocks.join("\n\n")}\n`;
}

function previewOf(text: string): string {
  const trimmed = text.trim();
  return trimmed.length > INPUT_PREVIEW_CHARS
    ? `${trimmed.slice(0, INPUT_PREVIEW_CHARS)}…`
    : trimmed;
}

export class MockApi implements ApiInterface {
  private readonly voices: Voice[];
  private readonly defaultVoiceId: string;
  private readonly generations = new Map<string, StoredGeneration>();
  private readonly subscribers = new Map<string, Set<Subscriber>>();
  private settings: Settings;

  constructor(voices: Voice[] = MOCK_VOICES, defaultVoiceId = MOCK_DEFAULT_VOICE_ID) {
    this.voices = voices.map((voice) => ({ ...voice }));
    this.defaultVoiceId = defaultVoiceId;
    this.settings = { defaultVoiceId, rate: 1, volume: 1 };
  }

  getHealth(): Promise<Health> {
    return Promise.resolve({
      status: "ok",
      version: "0.1.0",
      voicesInstalled: this.voices.length,
      defaultVoiceId: this.voices.length > 0 ? this.settings.defaultVoiceId : this.defaultVoiceId,
    });
  }

  listVoices(): Promise<VoiceList> {
    return Promise.resolve(cloneVoiceList(this.voices, this.settings.defaultVoiceId));
  }

  previewVoice(voiceId: string): Promise<Blob> {
    if (this.voices.length === 0) {
      return Promise.reject(
        fail(
          409,
          "NO_VOICES_INSTALLED",
          "No voices are installed. Run `tts add-voice <name>` and reload.",
        ),
      );
    }
    if (!this.voices.some((voice) => voice.id === voiceId)) {
      return Promise.reject(
        fail(422, "VOICE_NOT_FOUND", `Voice "${voiceId}" is not installed. Pick another voice.`),
      );
    }
    return Promise.resolve(silentWav(PREVIEW_SECONDS));
  }

  async uploadFile(file: File): Promise<UploadResult> {
    if (!file.name.toLowerCase().endsWith(".txt")) {
      throw fail(
        415,
        "UNSUPPORTED_FILE_TYPE",
        "Only plain-text .txt files are accepted. Choose a .txt file and try again.",
      );
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      throw fail(413, "FILE_TOO_LARGE", "The file is larger than 2 MB. Split it and try again.");
    }
    const text = await file.text();
    return { text, filename: file.name, sizeBytes: file.size };
  }

  async createGeneration(input: GenerationCreateRequest): Promise<GenerationStatus> {
    if (input.text.trim().length === 0) {
      throw fail(
        422,
        "EMPTY_INPUT",
        "Enter some text before generating. Paste or upload text and try again.",
      );
    }
    if (input.text.length > MAX_INPUT_CHARS) {
      throw fail(
        422,
        "INPUT_TOO_LONG",
        `Input is ${input.text.length.toLocaleString()} characters; the limit is ${MAX_INPUT_CHARS.toLocaleString()}.`,
        { maxChars: MAX_INPUT_CHARS, receivedChars: input.text.length },
      );
    }
    const voiceId = input.voiceId ?? this.settings.defaultVoiceId;
    if (this.voices.length === 0) {
      throw fail(
        409,
        "NO_VOICES_INSTALLED",
        "No voices are installed. Run `tts add-voice <name>`.",
      );
    }
    const voice = this.voices.find((candidate) => candidate.id === voiceId);
    if (voice === undefined) {
      throw fail(
        422,
        "VOICE_NOT_FOUND",
        `Voice "${voiceId}" is not installed. Pick another voice.`,
      );
    }
    const rate = input.rate ?? this.settings.rate;
    const volume = input.volume ?? this.settings.volume;
    if (rate < RATE_RANGE.min || rate > RATE_RANGE.max) {
      throw fail(
        422,
        "OUT_OF_RANGE",
        `Rate must be between ${RATE_RANGE.min} and ${RATE_RANGE.max}.`,
        {
          field: "rate",
          min: RATE_RANGE.min,
          max: RATE_RANGE.max,
          value: rate,
        },
      );
    }
    if (volume < VOLUME_RANGE.min || volume > VOLUME_RANGE.max) {
      throw fail(
        422,
        "OUT_OF_RANGE",
        `Volume must be between ${VOLUME_RANGE.min} and ${VOLUME_RANGE.max}.`,
        { field: "volume", min: VOLUME_RANGE.min, max: VOLUME_RANGE.max, value: volume },
      );
    }

    const generationId = crypto.randomUUID();
    const sentenceCount = Math.max(1, Math.ceil(input.text.trim().split(/\n+/).length));
    const summary: GenerationSummary = {
      generationId,
      status: "queued",
      createdAt: new Date().toISOString(),
      sourceType: "text",
      inputPreview: previewOf(input.text),
      inputFilename: null,
      voiceId: voice.id,
      voiceName: voice.name,
      rate,
      volume,
      durationSeconds: null,
      error: null,
    };
    const detail: GenerationDetail = {
      ...summary,
      text: null,
      sampleRate: null,
      alignedWordRatio: null,
      wordTimings: null,
      cues: null,
    };
    this.generations.set(generationId, { summary, detail, pendingText: input.text, sentenceCount });
    this.scheduleSynthesis(generationId);
    return { generationId, status: "queued" };
  }

  getGeneration(generationId: string): Promise<GenerationDetail> {
    const stored = this.generations.get(generationId);
    if (stored === undefined) {
      return Promise.reject(
        fail(404, "GENERATION_NOT_FOUND", "That generation no longer exists. Refresh the history."),
      );
    }
    return Promise.resolve(cloneDetail(stored.detail));
  }

  listGenerations(options: ListGenerationsOptions = {}): Promise<GenerationList> {
    const limit = options.limit ?? 20;
    const offset = options.offset ?? 0;
    const items = [...this.generations.values()]
      .map((stored) => ({ ...stored.summary }))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    return Promise.resolve({ items: items.slice(offset, offset + limit), total: items.length });
  }

  getAudioBlob(generationId: string): Promise<Blob> {
    const stored = this.generations.get(generationId);
    if (stored === undefined) {
      return Promise.reject(
        fail(404, "GENERATION_NOT_FOUND", "That generation no longer exists. Refresh the history."),
      );
    }
    if (stored.detail.status !== "succeeded") {
      return Promise.reject(
        fail(409, "GENERATION_NOT_READY", "Audio is not ready yet. Wait for generation to finish."),
      );
    }
    return Promise.resolve(silentWav(stored.detail.durationSeconds ?? 1));
  }

  getSubtitlesText(generationId: string, format: SubtitleFormat): Promise<string> {
    const stored = this.generations.get(generationId);
    if (format !== "srt" && format !== "vtt") {
      return Promise.reject(
        fail(400, "SUBTITLE_FORMAT_UNKNOWN", 'Subtitles are available as "srt" or "vtt".'),
      );
    }
    if (stored === undefined) {
      return Promise.reject(
        fail(404, "GENERATION_NOT_FOUND", "That generation no longer exists. Refresh the history."),
      );
    }
    if (stored.detail.status !== "succeeded" || stored.detail.cues === null) {
      return Promise.reject(
        fail(
          409,
          "GENERATION_NOT_READY",
          "Subtitles are not ready yet. Wait for generation to finish.",
        ),
      );
    }
    return Promise.resolve(formatSubtitles(stored.detail.cues, format));
  }

  openEventStream(
    generationId: string,
    onEvent: (event: GenerationStreamEvent) => void,
  ): () => void {
    const stored = this.generations.get(generationId);
    if (stored === undefined) {
      throw fail(
        404,
        "GENERATION_NOT_FOUND",
        "That generation no longer exists. Refresh the history.",
      );
    }
    const listeners = this.subscribers.get(generationId) ?? new Set<Subscriber>();
    listeners.add(onEvent);
    this.subscribers.set(generationId, listeners);

    const current = stored.detail;
    if (current.status === "succeeded") {
      onEvent({
        type: "succeeded",
        payload: {
          generationId,
          status: "succeeded",
          durationSeconds: current.durationSeconds ?? 0,
        },
      });
    } else if (current.status === "failed" && current.error !== null) {
      onEvent({
        type: "failed",
        payload: { generationId, status: "failed", error: { ...current.error } },
      });
    } else if (current.status === "cancelled") {
      onEvent({ type: "cancelled", payload: { generationId, status: "cancelled" } });
    } else {
      const status =
        current.status === "cancelling"
          ? "cancelling"
          : current.status === "running"
            ? "running"
            : "queued";
      onEvent({
        type: "progress",
        payload: {
          generationId,
          status,
          sentenceIndex: status === "queued" ? 0 : 1,
          sentenceCount: stored.sentenceCount,
        },
      });
    }

    return () => {
      const currentListeners = this.subscribers.get(generationId);
      currentListeners?.delete(onEvent);
    };
  }

  cancelGeneration(generationId: string): Promise<GenerationStatus> {
    const stored = this.generations.get(generationId);
    if (stored === undefined) {
      return Promise.reject(
        fail(404, "GENERATION_NOT_FOUND", "That generation no longer exists. Refresh the history."),
      );
    }
    if (isTerminal(stored.detail.status)) {
      return Promise.reject(
        fail(
          409,
          "GENERATION_BUSY",
          "That generation already finished, so it cannot be cancelled.",
        ),
      );
    }
    this.updateStatus(generationId, "cancelled");
    this.emit(generationId, { type: "cancelled", payload: { generationId, status: "cancelled" } });
    return Promise.resolve({ generationId, status: "cancelled" });
  }

  deleteGeneration(generationId: string): Promise<void> {
    const stored = this.generations.get(generationId);
    if (stored === undefined) {
      return Promise.reject(
        fail(404, "GENERATION_NOT_FOUND", "That generation no longer exists. Refresh the history."),
      );
    }
    if (!isTerminal(stored.detail.status)) {
      return Promise.reject(
        fail(409, "GENERATION_BUSY", "Cancel the running generation before deleting it."),
      );
    }
    this.generations.delete(generationId);
    this.subscribers.delete(generationId);
    return Promise.resolve();
  }

  getSettings(): Promise<Settings> {
    return Promise.resolve({ ...this.settings });
  }

  putSettings(patch: SettingsPatch): Promise<Settings> {
    const next: Settings = { ...this.settings, ...patch };
    if (
      patch.defaultVoiceId !== undefined &&
      !this.voices.some((voice) => voice.id === patch.defaultVoiceId)
    ) {
      return Promise.reject(
        fail(
          422,
          "VOICE_NOT_FOUND",
          `Voice "${patch.defaultVoiceId}" is not installed. Pick another voice.`,
        ),
      );
    }
    if (next.rate < RATE_RANGE.min || next.rate > RATE_RANGE.max) {
      return Promise.reject(
        fail(422, "OUT_OF_RANGE", `Rate must be between ${RATE_RANGE.min} and ${RATE_RANGE.max}.`, {
          field: "rate",
          min: RATE_RANGE.min,
          max: RATE_RANGE.max,
          value: next.rate,
        }),
      );
    }
    if (next.volume < VOLUME_RANGE.min || next.volume > VOLUME_RANGE.max) {
      return Promise.reject(
        fail(
          422,
          "OUT_OF_RANGE",
          `Volume must be between ${VOLUME_RANGE.min} and ${VOLUME_RANGE.max}.`,
          { field: "volume", min: VOLUME_RANGE.min, max: VOLUME_RANGE.max, value: next.volume },
        ),
      );
    }
    this.settings = next;
    return Promise.resolve({ ...this.settings });
  }

  private scheduleSynthesis(generationId: string): void {
    const stored = this.generations.get(generationId);
    if (stored === undefined) {
      return;
    }
    setTimeout(() => {
      const running = this.generations.get(generationId);
      if (running === undefined || running.detail.status !== "queued") {
        return;
      }
      this.updateStatus(generationId, "running");
      const progress: GenerationProgress = {
        generationId,
        status: "running",
        sentenceIndex: running.sentenceCount,
        sentenceCount: running.sentenceCount,
      };
      this.emit(generationId, { type: "progress", payload: progress });
    }, 30);

    setTimeout(() => {
      const current = this.generations.get(generationId);
      if (current === undefined || current.detail.status !== "running") {
        return;
      }
      this.succeed(generationId);
    }, 80);
  }

  private succeed(generationId: string): void {
    const stored = this.generations.get(generationId);
    if (stored === undefined) {
      return;
    }
    const timings = buildWordTimings(stored.pendingText);
    const cues = buildCues(timings);
    const durationSeconds = durationOf(timings);
    const succeeded: GenerationDetail = {
      ...stored.detail,
      status: "succeeded",
      durationSeconds,
      text: stored.pendingText,
      sampleRate: SAMPLE_RATE,
      alignedWordRatio: 1,
      wordTimings: timings,
      cues,
      error: null,
    };
    this.generations.set(generationId, {
      summary: { ...stored.summary, status: "succeeded", durationSeconds, error: null },
      detail: succeeded,
      pendingText: stored.pendingText,
      sentenceCount: stored.sentenceCount,
    });
    this.emit(generationId, {
      type: "succeeded",
      payload: { generationId, status: "succeeded", durationSeconds },
    });
  }

  private updateStatus(generationId: string, status: GenerationSummary["status"]): void {
    const stored = this.generations.get(generationId);
    if (stored === undefined) {
      return;
    }
    stored.summary = { ...stored.summary, status };
    stored.detail = { ...stored.detail, status };
  }

  private emit(generationId: string, event: GenerationStreamEvent): void {
    for (const listener of this.subscribers.get(generationId) ?? []) {
      listener(event);
    }
  }
}

function isTerminal(status: GenerationSummary["status"]): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}
