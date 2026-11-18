/**
 * Live HTTP client for the contracts in ARCHITECTURE.md section 9.
 *
 * Every non-2xx response is decoded into an `ApiError` carrying the standard
 * error envelope, so callers always see `{code, message, details}` rather
 * than raw fetch failures.
 */

import type {
  ErrorCode,
  ErrorDetails,
  ErrorInfo,
  GenerationCreateRequest,
  GenerationDetail,
  GenerationList,
  GenerationStatus,
  GenerationStatusValue,
  GenerationStreamEvent,
  Health,
  Settings,
  SettingsPatch,
  SubtitleFormat,
  UploadResult,
  VoiceList,
} from "../types/contracts";

export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly details: ErrorDetails;

  constructor(status: number, info: ErrorInfo) {
    super(info.message);
    this.name = "ApiError";
    this.code = info.code;
    this.status = status;
    this.details = info.details;
  }
}

export interface ListGenerationsOptions {
  limit?: number;
  offset?: number;
}

/** Implemented by both the live client and the in-memory mock (section 12). */
export interface ApiInterface {
  getHealth(): Promise<Health>;
  listVoices(): Promise<VoiceList>;
  previewVoice(voiceId: string): Promise<Blob>;
  uploadFile(file: File): Promise<UploadResult>;
  createGeneration(input: GenerationCreateRequest): Promise<GenerationStatus>;
  getGeneration(generationId: string): Promise<GenerationDetail>;
  listGenerations(options?: ListGenerationsOptions): Promise<GenerationList>;
  getAudioBlob(generationId: string): Promise<Blob>;
  getSubtitlesText(generationId: string, format: SubtitleFormat): Promise<string>;
  openEventStream(
    generationId: string,
    onEvent: (event: GenerationStreamEvent) => void,
  ): () => void;
  cancelGeneration(generationId: string): Promise<GenerationStatus>;
  deleteGeneration(generationId: string): Promise<void>;
  getSettings(): Promise<Settings>;
  putSettings(patch: SettingsPatch): Promise<Settings>;
}

const ERROR_CODES: ReadonlySet<string> = new Set<ErrorCode>([
  "EMPTY_INPUT",
  "INPUT_TOO_LONG",
  "OUT_OF_RANGE",
  "VOICE_NOT_FOUND",
  "UNSUPPORTED_FILE_TYPE",
  "FILE_TOO_LARGE",
  "DECODE_FAILED",
  "NO_VOICES_INSTALLED",
  "GENERATION_NOT_FOUND",
  "GENERATION_NOT_READY",
  "GENERATION_BUSY",
  "SUBTITLE_FORMAT_UNKNOWN",
  "NOT_FOUND",
  "ENGINE_ERROR",
  "INTERNAL_ERROR",
]);

const GENERATION_STATES: ReadonlySet<string> = new Set<GenerationStatusValue>([
  "queued",
  "running",
  "cancelling",
  "succeeded",
  "failed",
  "cancelled",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === "string" && ERROR_CODES.has(value);
}

function isGenerationStatusValue(value: unknown): value is GenerationStatusValue {
  return typeof value === "string" && GENERATION_STATES.has(value);
}

function decodeErrorInfo(body: unknown): ErrorInfo | null {
  if (!isRecord(body) || !isRecord(body["error"])) {
    return null;
  }
  const error = body["error"];
  if (!isErrorCode(error["code"]) || typeof error["message"] !== "string") {
    return null;
  }
  const details = error["details"];
  return {
    code: error["code"],
    message: error["message"],
    details: details === undefined ? null : (details as ErrorDetails),
  };
}

/** Wraps any thrown value in an `ApiError` with a corrective-action message. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return new ApiError(0, {
    code: "INTERNAL_ERROR",
    message: "Could not reach the local server. Check that `tts` is running, then try again.",
    details: null,
  });
}

function networkError(): ApiError {
  return toApiError(null);
}

function parseStreamEvent(
  type: GenerationStreamEvent["type"],
  data: string,
): GenerationStreamEvent | null {
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    return null;
  }
  if (!isRecord(payload)) {
    return null;
  }
  const generationId = payload["generationId"];
  const status = payload["status"];
  if (typeof generationId !== "string" || !isGenerationStatusValue(status)) {
    return null;
  }
  switch (type) {
    case "progress": {
      const sentenceIndex = payload["sentenceIndex"];
      const sentenceCount = payload["sentenceCount"];
      if (typeof sentenceIndex !== "number" || typeof sentenceCount !== "number") {
        return null;
      }
      if (status !== "queued" && status !== "running" && status !== "cancelling") {
        return null;
      }
      return {
        type,
        payload: { generationId, status, sentenceIndex, sentenceCount },
      };
    }
    case "succeeded": {
      const durationSeconds = payload["durationSeconds"];
      if (typeof durationSeconds !== "number") {
        return null;
      }
      return { type, payload: { generationId, status: "succeeded", durationSeconds } };
    }
    case "failed": {
      const error = payload["error"];
      if (!isRecord(error) || !isErrorCode(error["code"]) || typeof error["message"] !== "string") {
        return null;
      }
      return {
        type,
        payload: {
          generationId,
          status: "failed",
          error: { code: error["code"], message: error["message"] },
        },
      };
    }
    case "cancelled":
      return { type, payload: { generationId, status: "cancelled" } };
  }
}

export interface LiveClientOptions {
  /** Origin to call; empty (the default) means the page's own origin. */
  baseUrl?: string;
}

export function createLiveClient(options: LiveClientOptions = {}): ApiInterface {
  const apiBase = `${options.baseUrl ?? ""}/api`;

  async function decodeFailure(response: Response): Promise<ApiError> {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    const info = decodeErrorInfo(body);
    if (info !== null) {
      return new ApiError(response.status, info);
    }
    return new ApiError(response.status, {
      code: "INTERNAL_ERROR",
      message:
        "The server returned an unexpected response. Try again, and check the log if it persists.",
      details: null,
    });
  }

  async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${apiBase}${path}`, init);
    } catch {
      throw networkError();
    }
    if (!response.ok) {
      throw await decodeFailure(response);
    }
    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError(response.status, {
        code: "INTERNAL_ERROR",
        message:
          "The server returned unreadable data. Try again, and check the log if it persists.",
        details: null,
      });
    }
  }

  async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
    let response: Response;
    try {
      response = await fetch(`${apiBase}${path}`, init);
    } catch {
      throw networkError();
    }
    if (!response.ok) {
      throw await decodeFailure(response);
    }
    return response.blob();
  }

  async function requestOk(path: string, init?: RequestInit): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(`${apiBase}${path}`, init);
    } catch {
      throw networkError();
    }
    if (!response.ok) {
      throw await decodeFailure(response);
    }
    return response;
  }

  function generationPath(generationId: string, suffix = ""): string {
    return `/generations/${encodeURIComponent(generationId)}${suffix}`;
  }

  return {
    getHealth: () => requestJson<Health>("/health"),

    listVoices: () => requestJson<VoiceList>("/voices"),

    previewVoice: (voiceId) =>
      requestBlob("/voices/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voiceId }),
      }),

    uploadFile: (file) => {
      const form = new FormData();
      form.append("file", file);
      return requestJson<UploadResult>("/uploads", { method: "POST", body: form });
    },

    createGeneration: (input) =>
      requestJson<GenerationStatus>("/generations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }),

    getGeneration: (generationId) => requestJson<GenerationDetail>(generationPath(generationId)),

    listGenerations: ({ limit, offset } = {}) => {
      const query = new URLSearchParams();
      if (limit !== undefined) {
        query.set("limit", String(limit));
      }
      if (offset !== undefined) {
        query.set("offset", String(offset));
      }
      const suffix = query.size > 0 ? `?${query.toString()}` : "";
      return requestJson<GenerationList>(`/generations${suffix}`);
    },

    getAudioBlob: (generationId) => requestBlob(generationPath(generationId, "/audio")),

    getSubtitlesText: async (generationId, format) => {
      const response = await requestOk(
        generationPath(generationId, `/subtitles?format=${encodeURIComponent(format)}`),
      );
      return response.text();
    },

    openEventStream: (generationId, onEvent) => {
      const source = new EventSource(`${apiBase}${generationPath(generationId, "/events")}`);
      const types: GenerationStreamEvent["type"][] = [
        "progress",
        "succeeded",
        "failed",
        "cancelled",
      ];
      const listeners = types.map((type) => {
        const listener = (event: Event): void => {
          if (!(event instanceof MessageEvent)) {
            return;
          }
          const data: unknown = event.data;
          if (typeof data !== "string") {
            return;
          }
          const parsed = parseStreamEvent(type, data);
          if (parsed === null) {
            return;
          }
          onEvent(parsed);
          if (type !== "progress") {
            source.close();
          }
        };
        source.addEventListener(type, listener);
        return [type, listener] as const;
      });
      return () => {
        for (const [type, listener] of listeners) {
          source.removeEventListener(type, listener);
        }
        source.close();
      };
    },

    cancelGeneration: (generationId) =>
      requestJson<GenerationStatus>(generationPath(generationId, "/cancel"), {
        method: "POST",
      }),

    deleteGeneration: async (generationId) => {
      await requestOk(generationPath(generationId), { method: "DELETE" });
    },

    getSettings: () => requestJson<Settings>("/settings"),

    putSettings: (patch) =>
      requestJson<Settings>("/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }),
  };
}
