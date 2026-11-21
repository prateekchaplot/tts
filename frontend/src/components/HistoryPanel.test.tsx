import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppProvider } from "../state/appContext";
import type { GenerationSummary } from "../types/contracts";
import {
  canDelete,
  canRestore,
  formatHistoryTime,
  historyPreview,
  historyStartsOpen,
  historyStatusText,
  HistoryList,
  HistoryPanel,
} from "./HistoryPanel";

const SUCCEEDED: GenerationSummary = {
  generationId: "6f0c8e2a-0000-4000-8000-000000000001",
  status: "succeeded",
  createdAt: "2026-11-17T14:25:30Z",
  sourceType: "text",
  inputPreview: "Hello world.",
  inputFilename: null,
  voiceId: "en_US-lessac-medium",
  voiceName: "en_US-lessac-medium",
  rate: 1,
  volume: 1,
  durationSeconds: 1.2,
  error: null,
};

const FAILED: GenerationSummary = {
  ...SUCCEEDED,
  generationId: "6f0c8e2a-0000-4000-8000-000000000002",
  status: "failed",
  durationSeconds: null,
  error: { code: "ENGINE_ERROR", message: "The speech engine produced no audio for this text." },
};

const RUNNING: GenerationSummary = {
  ...SUCCEEDED,
  generationId: "6f0c8e2a-0000-4000-8000-000000000003",
  status: "running",
  durationSeconds: null,
};

const FILE_SOURCE: GenerationSummary = {
  ...SUCCEEDED,
  generationId: "6f0c8e2a-0000-4000-8000-000000000004",
  sourceType: "file",
  inputPreview: "   ",
  inputFilename: "notes.txt",
};

function renderList(items: GenerationSummary[], total = items.length): string {
  return renderToStaticMarkup(
    <HistoryList
      items={items}
      total={total}
      busy={null}
      onRestore={() => undefined}
      onDelete={() => undefined}
    />,
  );
}

describe("history row rules", () => {
  it("restores only finished generations", () => {
    expect(canRestore(SUCCEEDED)).toBe(true);
    expect(canRestore(FAILED)).toBe(false);
    expect(canRestore(RUNNING)).toBe(false);
    expect(canRestore({ ...SUCCEEDED, status: "cancelled" })).toBe(false);
  });

  it("deletes only terminal generations", () => {
    expect(canDelete(SUCCEEDED)).toBe(true);
    expect(canDelete(FAILED)).toBe(true);
    expect(canDelete({ ...SUCCEEDED, status: "cancelled" })).toBe(true);
    for (const status of ["queued", "running", "cancelling"] as const) {
      expect(canDelete({ ...SUCCEEDED, status })).toBe(false);
    }
  });

  it("describes every status, including the failure reason", () => {
    expect(historyStatusText(SUCCEEDED)).toBe("Ready · 1 s");
    expect(historyStatusText({ ...SUCCEEDED, durationSeconds: null })).toBe("Ready");
    expect(historyStatusText(FAILED)).toContain("produced no audio");
    expect(historyStatusText({ ...FAILED, error: null })).toBe("Failed");
    expect(historyStatusText({ ...SUCCEEDED, status: "cancelled" })).toBe("Cancelled");
    expect(historyStatusText(RUNNING)).toBe("Generating…");
    expect(historyStatusText({ ...SUCCEEDED, status: "queued" })).toBe("Queued");
    expect(historyStatusText({ ...SUCCEEDED, status: "cancelling" })).toBe("Cancelling…");
  });

  it("falls back to the file name when the preview is blank", () => {
    expect(historyPreview(SUCCEEDED)).toBe("Hello world.");
    expect(historyPreview(FILE_SOURCE)).toBe("notes.txt");
    expect(historyPreview({ ...SUCCEEDED, inputPreview: "  " })).toBe("(no preview)");
  });

  it("opens on wide viewports and starts collapsed when narrow", () => {
    expect(historyStartsOpen(false)).toBe(true);
    expect(historyStartsOpen(true)).toBe(false);
  });

  it("formats valid timestamps locally and keeps malformed ones verbatim", () => {
    const expected = new Date(SUCCEEDED.createdAt).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
    expect(formatHistoryTime(SUCCEEDED.createdAt)).toBe(expected);
    expect(formatHistoryTime("not-a-date")).toBe("not-a-date");
  });
});

describe("HistoryList", () => {
  it("explains the empty state and counts entries", () => {
    const empty = renderList([]);
    expect(empty).toContain("0 saved generations");
    expect(empty).toContain("Generate audio and it will appear in this list.");
    expect(renderList([SUCCEEDED])).toContain("1 saved generation");
  });

  it("renders preview, voice, time, and status for each entry", () => {
    const html = renderList([SUCCEEDED, FAILED]);
    expect(html).toContain("Hello world.");
    expect(html).toContain("en_US-lessac-medium");
    expect(html).toContain("<time");
    expect(html).toContain("Ready · 1 s");
    expect(html).toContain("Failed: The speech engine produced no audio");
    expect(html.match(/<li/g)).toHaveLength(2);
  });

  it("enables Open only for finished rows and Delete only for terminal ones", () => {
    const html = renderList([SUCCEEDED, { ...RUNNING, inputPreview: "Still generating." }]);
    expect(html).toMatch(
      /<button[^>]*aria-label="Open generation: Hello world\."[^>]*>Open<\/button>/,
    );
    expect(html).not.toMatch(/<button[^>]*disabled[^>]*aria-label="Open generation: Hello world\./);
    expect(html).toMatch(
      /<button[^>]*disabled[^>]*aria-label="Open generation: Still generating\.[^>]*>Open<\/button>/,
    );
    expect(html).toMatch(
      /<button[^>]*aria-label="Delete generation: Hello world\.[^>]*>Delete<\/button>/,
    );
    expect(html).toMatch(
      /<button[^>]*disabled[^>]*aria-label="Delete generation: Still generating\.[^>]*>Delete<\/button>/,
    );
  });
});

describe("HistoryPanel", () => {
  it("renders an open disclosure with the empty list", () => {
    const html = renderToStaticMarkup(
      <AppProvider>
        <HistoryPanel />
      </AppProvider>,
    );
    expect(html).toContain("<details");
    expect(html).toMatch(/<details[^>]*open/);
    expect(html).toContain('id="history-heading"');
    expect(html).toContain("0 saved generations");
  });
});
