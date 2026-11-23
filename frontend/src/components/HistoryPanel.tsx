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
import { strings } from "../strings";
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
        ? strings.history.statusReady
        : strings.history.statusReadyWithDuration(item.durationSeconds);
    case "failed":
      return item.error === null
        ? strings.history.statusFailed
        : strings.history.statusFailedWithReason(item.error.message);
    case "cancelled":
      return strings.history.statusCancelled;
    case "queued":
      return strings.history.statusQueued;
    case "running":
      return strings.history.statusRunning;
    case "cancelling":
      return strings.history.statusCancelling;
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
  return item.inputFilename ?? strings.history.noPreview;
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
  /** Row awaiting delete confirmation, or null. */
  confirmingId: string | null;
  /** Row whose Delete button should take focus after a cancelled confirmation. */
  focusDeleteId: string | null;
  onRestore: (item: GenerationSummary) => void;
  onRequestDelete: (item: GenerationSummary) => void;
  onConfirmDelete: (item: GenerationSummary) => void;
  onKeep: () => void;
}

/** Presentational list; kept separate so it can be tested without effects. */
export function HistoryList({
  items,
  total,
  busy,
  confirmingId,
  focusDeleteId,
  onRestore,
  onRequestDelete,
  onConfirmDelete,
  onKeep,
}: HistoryListProps) {
  const countLabel = strings.history.countLabel(total);
  const restoreFocusRef = useRef<HTMLButtonElement | null>(null);

  // Focus returns to Delete after "Keep" (and only then), so a keyboard user
  // does not land on the document body when the confirm buttons unmount.
  useEffect(() => {
    if (focusDeleteId !== null) {
      restoreFocusRef.current?.focus();
    }
  }, [focusDeleteId]);

  if (items.length === 0) {
    return (
      <>
        <p className="stat">{countLabel}</p>
        <p className="hint">{strings.history.empty}</p>
      </>
    );
  }

  return (
    <>
      <p className="stat">{countLabel}</p>
      <p className="hint">{strings.history.hint}</p>
      <ul className="history-list">
        {items.map((item) => {
          const preview = historyPreview(item);
          const confirming = confirmingId === item.generationId;
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
                  disabled={!restorable || confirming}
                  aria-label={strings.history.openLabel(preview)}
                  onClick={() => {
                    onRestore(item);
                  }}
                >
                  {restoring ? strings.history.opening : strings.history.open}
                </button>
                {confirming ? (
                  <>
                    <button
                      type="button"
                      autoFocus
                      disabled={!deletable}
                      aria-label={strings.history.confirmDeleteLabel(preview)}
                      onClick={() => {
                        onConfirmDelete(item);
                      }}
                    >
                      {deleting ? strings.history.deleting : strings.history.confirmDelete}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy !== null}
                      aria-label={strings.history.keepLabel(preview)}
                      onClick={onKeep}
                    >
                      {strings.history.keep}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="secondary"
                    ref={focusDeleteId === item.generationId ? restoreFocusRef : undefined}
                    disabled={!deletable}
                    aria-label={strings.history.deleteLabel(preview)}
                    onClick={() => {
                      onRequestDelete(item);
                    }}
                  >
                    {strings.history.delete}
                  </button>
                )}
              </div>
              {confirming ? (
                <p className="hint history-confirm" role="status">
                  {strings.history.confirmPrompt}
                </p>
              ) : null}
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
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [focusDeleteId, setFocusDeleteId] = useState<string | null>(null);
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
    setConfirmingId(null);
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
    setConfirmingId(null);
    setFocusDeleteId(null);
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
          <h2 id="history-heading">{strings.history.heading}</h2>
        </summary>
        <HistoryList
          items={state.history.items}
          total={state.history.total}
          busy={busy}
          confirmingId={confirmingId}
          focusDeleteId={focusDeleteId}
          onRestore={(item) => {
            void handleRestore(item);
          }}
          onRequestDelete={(item) => {
            setFocusDeleteId(null);
            setConfirmingId(item.generationId);
          }}
          onConfirmDelete={(item) => {
            void handleDelete(item);
          }}
          onKeep={() => {
            setFocusDeleteId(confirmingId);
            setConfirmingId(null);
          }}
        />
      </details>
    </section>
  );
}
