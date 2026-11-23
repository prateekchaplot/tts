/**
 * Audio and subtitle downloads (ARCHITECTURE.md sections 9.2 and 12, FR-07).
 *
 * The browser cannot read the server's `Content-Disposition` header through
 * `fetch`, so the download name is rebuilt with the same §9.2 rule the API
 * uses: first ≤ 6 words of the input, lowercased, joined by `-`, plus the UTC
 * `createdAt` timestamp as `YYYYMMDD-HHMMSS`.
 */

import { useState } from "react";
import { api } from "../api";
import { toApiError } from "../api/client";
import { strings } from "../strings";
import { useApp } from "../state/appContext";
import type { GenerationDetail, SubtitleFormat } from "../types/contracts";

export type DownloadKind = "wav" | SubtitleFormat;

const SLUG_WORDS = 6;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** UTC `YYYYMMDD-HHMMSS`, the timestamp half of the §9.2 download name. */
export function downloadTimestamp(createdAt: string): string {
  const date = new Date(createdAt);
  const safe = Number.isNaN(date.getTime()) ? new Date() : date;
  return (
    `${safe.getUTCFullYear()}${pad(safe.getUTCMonth() + 1)}${pad(safe.getUTCDate())}` +
    `-${pad(safe.getUTCHours())}${pad(safe.getUTCMinutes())}${pad(safe.getUTCSeconds())}`
  );
}

/** The `{slug}_{timestamp}` stem shared by all three download files. */
export function downloadStem(input: string, createdAt: string): string {
  const words = (input.match(/[A-Za-z0-9]+/g) ?? []).slice(0, SLUG_WORDS);
  const slug =
    words
      .join("-")
      .toLowerCase()
      .replace(/[^a-z0-9-]/g, "")
      .replace(/^-+|-+$/g, "") || "speech";
  return `${slug}_${downloadTimestamp(createdAt)}`;
}

export function downloadFilename(
  input: string,
  createdAt: string,
  extension: DownloadKind,
): string {
  return `${downloadStem(input, createdAt)}.${extension}`;
}

/** Triggers a browser download for an already-fetched blob. */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 0);
}

export interface DownloadBarProps {
  detail: GenerationDetail;
}

export function DownloadBar({ detail }: DownloadBarProps) {
  const { dispatch } = useApp();
  const [busy, setBusy] = useState<DownloadKind | null>(null);
  const input = detail.text ?? detail.inputPreview;

  function dispatchFailure(error: unknown): void {
    const failure = toApiError(error);
    dispatch({
      type: "SET_ERROR",
      error: { code: failure.code, message: failure.message, details: failure.details },
    });
  }

  async function downloadAudio(): Promise<void> {
    setBusy("wav");
    try {
      const blob = await api.getAudioBlob(detail.generationId);
      saveBlob(blob, downloadFilename(input, detail.createdAt, "wav"));
    } catch (error) {
      dispatchFailure(error);
    } finally {
      setBusy(null);
    }
  }

  async function downloadSubtitles(format: SubtitleFormat): Promise<void> {
    setBusy(format);
    try {
      const text = await api.getSubtitlesText(detail.generationId, format);
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      saveBlob(blob, downloadFilename(input, detail.createdAt, format));
    } catch (error) {
      dispatchFailure(error);
    } finally {
      setBusy(null);
    }
  }

  const disabled = busy !== null;

  return (
    <div className="download-block">
      <h3>{strings.downloads.heading}</h3>
      <p className="hint">{strings.downloads.hint}</p>
      <div className="button-row download-row">
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            void downloadAudio();
          }}
        >
          {busy === "wav" ? strings.downloads.preparingWav : strings.downloads.wav}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={disabled}
          onClick={() => {
            void downloadSubtitles("srt");
          }}
        >
          {busy === "srt" ? strings.downloads.preparingSrt : strings.downloads.srt}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={disabled}
          onClick={() => {
            void downloadSubtitles("vtt");
          }}
        >
          {busy === "vtt" ? strings.downloads.preparingVtt : strings.downloads.vtt}
        </button>
      </div>
    </div>
  );
}
