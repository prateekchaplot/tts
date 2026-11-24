/**
 * Wire types and API helpers for the acceptance suite (ARCHITECTURE.md
 * section 9). Only the fields the specs assert on are mirrored here; the
 * binding contracts live in `frontend/src/types/contracts.ts`.
 */

import type { APIRequestContext, APIResponse } from "@playwright/test";
import { MAIN_URL, VOICE_ID } from "./env";

export type GenerationStatusValue =
  "queued" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled";

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

export interface GenerationErrorInfo {
  code: string;
  message: string;
}

export interface GenerationSummary {
  generationId: string;
  status: GenerationStatusValue;
  createdAt: string;
  inputPreview: string;
  inputFilename: string | null;
  voiceId: string;
  voiceName: string;
  durationSeconds: number | null;
  error: GenerationErrorInfo | null;
}

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

export interface VoiceInfo {
  id: string;
  name: string;
  language: string;
}

export interface VoiceList {
  items: VoiceInfo[];
  total: number;
  defaultVoiceId: string;
}

export interface ErrorEnvelope {
  error: { code: string; message: string; details: unknown };
}

export interface CreateOptions {
  voiceId?: string;
  rate?: number;
  volume?: number;
}

export const TERMINAL_STATUSES: ReadonlySet<GenerationStatusValue> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);

/** Fail loudly on a non-2xx response instead of returning an opaque body. */
async function bodyAsJson<T>(response: APIResponse, label: string): Promise<T> {
  if (!response.ok()) {
    throw new Error(
      `${label} -> HTTP ${response.status()}: ${await response.text()}`,
    );
  }
  return (await response.json()) as T;
}

export async function listVoices(
  request: APIRequestContext,
  base: string = MAIN_URL,
): Promise<VoiceList> {
  return bodyAsJson<VoiceList>(
    await request.get(`${base}/api/voices`),
    "GET /api/voices",
  );
}

export async function getHealth(
  request: APIRequestContext,
  base: string = MAIN_URL,
): Promise<{ status: string; version: string; voicesInstalled: number }> {
  return bodyAsJson(await request.get(`${base}/api/health`), "GET /api/health");
}

export async function listGenerations(
  request: APIRequestContext,
  base: string = MAIN_URL,
  limit = 100,
): Promise<GenerationList> {
  return bodyAsJson<GenerationList>(
    await request.get(`${base}/api/generations?limit=${limit}`),
    "GET /api/generations",
  );
}

export async function getGeneration(
  request: APIRequestContext,
  generationId: string,
  base: string = MAIN_URL,
): Promise<GenerationDetail> {
  return bodyAsJson<GenerationDetail>(
    await request.get(`${base}/api/generations/${generationId}`),
    "GET /api/generations/{id}",
  );
}

export async function createGeneration(
  request: APIRequestContext,
  text: string,
  options: CreateOptions = {},
  base: string = MAIN_URL,
): Promise<{ generationId: string; status: GenerationStatusValue }> {
  return bodyAsJson(
    await request.post(`${base}/api/generations`, {
      data: {
        text,
        voiceId: options.voiceId ?? VOICE_ID,
        rate: options.rate ?? 1,
        volume: options.volume ?? 1,
      },
    }),
    "POST /api/generations",
  );
}

/** Polls until the row reaches a terminal state; returns the final detail. */
export async function waitForTerminal(
  request: APIRequestContext,
  generationId: string,
  base: string = MAIN_URL,
  timeoutMs = 180_000,
): Promise<GenerationDetail> {
  const deadline = Date.now() + timeoutMs;
  let last: GenerationDetail | null = null;
  while (Date.now() < deadline) {
    last = await getGeneration(request, generationId, base);
    if (TERMINAL_STATUSES.has(last.status)) {
      return last;
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(
    `Generation ${generationId} did not finish in ${timeoutMs} ms (last status: ${last?.status ?? "unknown"})`,
  );
}

/** Creates a generation over the API and waits for it to finish. */
export async function generateViaApi(
  request: APIRequestContext,
  text: string,
  options: CreateOptions = {},
  base: string = MAIN_URL,
): Promise<GenerationDetail> {
  const created = await createGeneration(request, text, options, base);
  return waitForTerminal(request, created.generationId, base);
}

export async function getAudioResponse(
  request: APIRequestContext,
  generationId: string,
  base: string = MAIN_URL,
): Promise<APIResponse> {
  return request.get(`${base}/api/generations/${generationId}/audio`);
}

export async function getSubtitles(
  request: APIRequestContext,
  generationId: string,
  format: "srt" | "vtt",
  base: string = MAIN_URL,
): Promise<string> {
  const response = await request.get(
    `${base}/api/generations/${generationId}/subtitles?format=${format}`,
  );
  if (!response.ok()) {
    throw new Error(`GET subtitles ${format} -> HTTP ${response.status()}`);
  }
  return response.text();
}

export async function deleteGeneration(
  request: APIRequestContext,
  generationId: string,
  base: string = MAIN_URL,
): Promise<APIResponse> {
  return request.delete(`${base}/api/generations/${generationId}`);
}
