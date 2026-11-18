/**
 * Selects the live client or the in-memory mock (section 11/12).
 * `VITE_API_MODE` defaults to `live`.
 */

import { createLiveClient, type ApiInterface } from "./client";
import { MockApi } from "./mock";

export type ApiMode = "live" | "mock";

function resolveMode(): ApiMode {
  return import.meta.env.VITE_API_MODE === "mock" ? "mock" : "live";
}

export const apiMode: ApiMode = resolveMode();

export const api: ApiInterface = apiMode === "mock" ? new MockApi() : createLiveClient();

export { ApiError } from "./client";
export type { ApiInterface, ListGenerationsOptions } from "./client";
