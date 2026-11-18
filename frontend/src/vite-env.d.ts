/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Selects the live HTTP client or the in-memory mock (section 11/12). */
  readonly VITE_API_MODE?: "live" | "mock";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
