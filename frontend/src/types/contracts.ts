/**
 * TypeScript mirror of the wire contracts in ARCHITECTURE.md section 9.
 *
 * This file is the single source of types for the frontend. It is a shared
 * file: change it only through the shared-file protocol (section 14.4) and
 * keep it in lockstep with `src/tts/api/schemas.py`.
 */

/** Every error code of section 9.1, in the order the document lists them. */
export type ErrorCode =
  | "EMPTY_INPUT"
  | "INPUT_TOO_LONG"
  | "OUT_OF_RANGE"
  | "VOICE_NOT_FOUND"
  | "UNSUPPORTED_FILE_TYPE"
  | "FILE_TOO_LARGE"
  | "DECODE_FAILED"
  | "NO_VOICES_INSTALLED"
  | "GENERATION_NOT_FOUND"
  | "GENERATION_NOT_READY"
  | "GENERATION_BUSY"
  | "SUBTITLE_FORMAT_UNKNOWN"
  | "NOT_FOUND"
  | "ENGINE_ERROR"
  | "INTERNAL_ERROR";

/** `details` is always present in the envelope; `null` when the error has none. */
export type ErrorDetails = Record<string, unknown> | null;

export interface ErrorInfo {
  code: ErrorCode;
  message: string;
  details: ErrorDetails;
}

export interface ErrorEnvelope {
  error: ErrorInfo;
}

// -- Health ----------------------------------------------------------------

export interface Health {
  status: "ok";
  version: string;
  voicesInstalled: number;
  defaultVoiceId: string;
}

// -- Voices ----------------------------------------------------------------

export interface Voice {
  id: string;
  name: string;
  language: string;
  gender: string | null;
  sampleRate: number;
}

export interface VoiceList {
  items: Voice[];
  total: number;
  defaultVoiceId: string;
}

// -- Timings and cues ------------------------------------------------------

export interface WordTiming {
  text: string;
  startMs: number;
  endMs: number;
  aligned: boolean;
}

export interface Cue {
  index: number;
  startMs: number;
  endMs: number;
  text: string;
}

// -- Generations -----------------------------------------------------------

export type GenerationStatusValue =
  "queued" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled";

export type GenerationSourceType = "text" | "file";

export interface GenerationStatus {
  generationId: string;
  status: GenerationStatusValue;
}

export interface GenerationError {
  code: ErrorCode;
  message: string;
}

export interface GenerationSummary {
  generationId: string;
  status: GenerationStatusValue;
  createdAt: string;
  sourceType: GenerationSourceType;
  inputPreview: string;
  inputFilename: string | null;
  voiceId: string;
  voiceName: string;
  rate: number;
  volume: number;
  durationSeconds: number | null;
  error: GenerationError | null;
}

/** Detail fields are `null` until the generation has succeeded (section 9.2). */
export interface GenerationDetail extends GenerationSummary {
  text: string | null;
  sampleRate: number | null;
  alignedWordRatio: number | null;
  wordTimings: WordTiming[] | null;
  cues: Cue[] | null;
}

export interface GenerationList {
  items: GenerationSummary[];
  total: number;
}

export interface GenerationCreateRequest {
  text: string;
  voiceId?: string;
  rate?: number;
  volume?: number;
}

// -- SSE stream (GET /api/generations/{id}/events) --------------------------

export interface GenerationProgress extends GenerationStatus {
  status: "queued" | "running" | "cancelling";
  sentenceIndex: number;
  sentenceCount: number;
}

export interface GenerationSucceeded extends GenerationStatus {
  status: "succeeded";
  durationSeconds: number;
}

export interface GenerationFailed extends GenerationStatus {
  status: "failed";
  error: GenerationError;
}

export interface GenerationCancelled extends GenerationStatus {
  status: "cancelled";
}

/** One named SSE event, discriminated by its `event:` line. */
export type GenerationStreamEvent =
  | { type: "progress"; payload: GenerationProgress }
  | { type: "succeeded"; payload: GenerationSucceeded }
  | { type: "failed"; payload: GenerationFailed }
  | { type: "cancelled"; payload: GenerationCancelled };

// -- Uploads ---------------------------------------------------------------

export interface UploadResult {
  text: string;
  filename: string;
  sizeBytes: number;
}

// -- Settings --------------------------------------------------------------

export interface Settings {
  defaultVoiceId: string;
  rate: number;
  volume: number;
}

/** Partial update: omitted keys stay unchanged (section 9.2). */
export type SettingsPatch = Partial<Settings>;

// -- Subtitles -------------------------------------------------------------

export type SubtitleFormat = "srt" | "vtt";

// -- Validation ranges mirrored by the UI (section 9.2, AC6) ---------------

export const RATE_RANGE = { min: 0.5, max: 2.0 } as const;
export const VOLUME_RANGE = { min: 0.0, max: 1.0 } as const;
