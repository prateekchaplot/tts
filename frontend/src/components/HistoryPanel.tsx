/**
 * Generation history (ARCHITECTURE.md section 12, FR-08, AC13).
 *
 * Lists recent generations with preview, voice, and time; restores the audio
 * and subtitle view of a finished entry without opening an SSE stream; and
 * deletes individual entries. The list is a native `<details>` disclosure so
 * keyboard operation comes for free, collapsed by default on narrow viewports.
 */

import { useCallback, useEffect, useRef, useState, type Dispatch } from "react";
import { api } from "../api";
import { toApiError } from "../api/client";
import { useApp, type AppAction } from "../state/appContext";
import type { GenerationDetail, GenerationSummary } from "../types/contracts";

/** Below this width the panel starts collapsed (section 12). */
export const HISTORY_NARROW_QUERY = "(max-width: 700px)";

export type HistoryBusy = { id: string; kind: "restore" | "delete" } | null;

/** Finished generations can be opened; active ones cannot (section 9.2). */
export function canRestore(item: GenerationSummary): boolean {
  return item.status === "succeeded";
}

/** Only terminal rows can be deleted; the API answers 409 while active. */
export function canDelete(item: GenerationSummary): boolean {
  return item.status === "succeeded" || item.status === "failed" || item.status === "cancelled";
}

/** One-line status for a history row. */
export function historyStatusText(item: GenerationSummary): string {
  switch (item.status) {
    case "succeeded":
      return item.durationSeconds === null
        ? "Ready"
        : `Ready · ${Math.round(item.durationSeconds)} s`;
    case "failed":
      return item.error === null ? "Failed" : `Failed: ${item.error.message}`;
    case "cancelled":
      return "Cancelled";
    case "queued":
      return "Queued";
    case "running":
      return "Generating…";
    case "cancelling":
      return "Cancelling…";
  }
}

/** Local date and time for the row; malformed timestamps render verbatim. */
export function formatHistoryTime(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) {
    return createdAt;
  }
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** Text shown for a row's input: the preview, or its file name as fallback. */
export function historyPreview(item: GenerationSummary): string {
  if (item.inputPreview.trim().length > 0) {
    return item.inputPreview;
  }
  return item.inputFilename ?? "(no preview)";
}

/** Wide viewports open the panel; narrow ones start collapsed (section 12). */
export function historyStartsOpen(isNarrow: boolean): boolean {
  return !isNarrow;
}

function readNarrowViewport(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(HISTORY_NARROW_QUERY).matches;
}

function dispatchFailure(dispatch: Dispatch<AppAction>, error: unknown): void {
  const failure = toApiError(error);
  dispatch({
    type: "SET_ERROR",
    error: { code: failure.code, message: failure.message, details: failure.details },
  });
}

export interface HistoryListProps {
  items: GenerationSummary[];
  total: number;
  busy: HistoryBusy;
  onRestore: (item: GenerationSummary) => void;
  onDelete: (item: GenerationSummary) => void;
}

/** Presentational list; kept separate so it can be tested without effects. */
export function HistoryList({ items, total, busy, onRestore, onDelete }: HistoryListProps) {
  const countLabel = `${total} saved generation${total === 1 ? "" : "s"}`;

  if (items.length === 0) {
    return (
      <>
        <p className="stat">{countLabel}</p>
        <p className="hint">Nothing here yet. Generate audio and it will appear in this list.</p>
      </>
    );
  }

  return (
    <>
      <p className="stat">{countLabel}</p>
      <p className="hint">
        Open a finished generation to load its audio and subtitles. Deleting an entry removes only
        that entry.
      </p>
      <ul className="history-list">
        {items.map((item) => {
          const preview = historyPreview(item);
          const restorable = canRestore(item) && busy === null;
          const deletable = canDelete(item) && busy === null;
          const restoring =
            busy !== null && busy.id === item.generationId && busy.kind === "restore";
          const deleting = busy !== null && busy.id === item.generationId && busy.kind === "delete";
          return (
            <li key={item.generationId} className="history-item">
              <div className="history-body">
                <p className="history-preview">{preview}</p>
                <p className="hint history-meta">
                  {item.voiceName} ·{" "}
                  <time dateTime={item.createdAt}>{formatHistoryTime(item.createdAt)}</time>
                  {item.inputFilename === null ? "" : ` · ${item.inputFilename}`}
                </p>
                <p className="stat history-status">{historyStatusText(item)}</p>
              </div>
              <div className="button-row history-actions">
                <button
                  type="button"
                  disabled={!restorable}
                  aria-label={`Open generation: ${preview}`}
                  onClick={() => {
                    onRestore(item);
                  }}
                >
                  {restoring ? "Opening…" : "Open"}
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={!deletable}
                  aria-label={`Delete generation: ${preview}`}
                  onClick={() => {
                    onDelete(item);
                  }}
                >
                  {deleting ? "Deleting…" : "Delete"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}

export function HistoryPanel() {
  const { state, dispatch } = useApp();
  const [busy, setBusy] = useState<HistoryBusy>(null);
  const [isOpen, setIsOpen] = useState(() => historyStartsOpen(readNarrowViewport()));
  const restoredUrlRef = useRef<string | null>(null);
  const refreshedRef = useRef<string | null>(null);
  const current = state.current;
  const historyItems = state.history.items;
  const currentAudioUrl = current?.audioUrl;

  const loadHistory = useCallback(async (): Promise<void> => {
    try {
      const list = await api.listGenerations();
      dispatch({ type: "HISTORY_LOADED", items: list.items, total: list.total });
    } catch (error) {
      dispatchFailure(dispatch, error);
    }
  }, [dispatch]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  // Include a just-finished generation once, so the list follows the current
  // playback item without polling.
  useEffect(() => {
    if (current === null) {
      return;
    }
    if (
      current.status !== "succeeded" &&
      current.status !== "failed" &&
      current.status !== "cancelled"
    ) {
      return;
    }
    if (historyItems.some((item) => item.generationId === current.id)) {
      return;
    }
    if (refreshedRef.current === current.id) {
      return;
    }
    refreshedRef.current = current.id;
    void loadHistory();
  }, [current, historyItems, loadHistory]);

  // Release the restored object URL when playback moves on or the panel goes.
  useEffect(() => {
    if (restoredUrlRef.current !== null && restoredUrlRef.current !== currentAudioUrl) {
      URL.revokeObjectURL(restoredUrlRef.current);
      restoredUrlRef.current = null;
    }
  }, [currentAudioUrl]);

  useEffect(() => {
    return () => {
      if (restoredUrlRef.current !== null) {
        URL.revokeObjectURL(restoredUrlRef.current);
        restoredUrlRef.current = null;
      }
    };
  }, []);

  async function handleRestore(item: GenerationSummary): Promise<void> {
    setBusy({ id: item.generationId, kind: "restore" });
    let detail: GenerationDetail;
    try {
      detail = await api.getGeneration(item.generationId);
    } catch (error) {
      dispatchFailure(dispatch, error);
      setBusy(null);
      return;
    }

    let audioUrl: string | undefined;
    try {
      const blob = await api.getAudioBlob(item.generationId);
      audioUrl = URL.createObjectURL(blob);
    } catch (error) {
      // The detail still restores the subtitle view; report the missing audio.
      dispatchFailure(dispatch, error);
    }

    if (audioUrl !== undefined) {
      if (restoredUrlRef.current !== null) {
        URL.revokeObjectURL(restoredUrlRef.current);
      }
      restoredUrlRef.current = audioUrl;
    }
    dispatch({ type: "SELECT_HISTORY_ITEM", detail, audioUrl });
    setBusy(null);
  }

  async function handleDelete(item: GenerationSummary): Promise<void> {
    setBusy({ id: item.generationId, kind: "delete" });
    try {
      await api.deleteGeneration(item.generationId);
      dispatch({ type: "HISTORY_DELETED", id: item.generationId });
    } catch (error) {
      dispatchFailure(dispatch, error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="section history-section" aria-labelledby="history-heading">
      <details
        className="history"
        open={isOpen}
        onToggle={(event) => {
          setIsOpen(event.currentTarget.open);
        }}
      >
        <summary>
          <h2 id="history-heading">History</h2>
        </summary>
        <HistoryList
          items={state.history.items}
          total={state.history.total}
          busy={busy}
          onRestore={(item) => {
            void handleRestore(item);
          }}
          onDelete={(item) => {
            void handleDelete(item);
          }}
        />
      </details>
    </section>
  );
}
