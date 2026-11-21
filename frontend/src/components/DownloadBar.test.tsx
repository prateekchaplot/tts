import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppProvider } from "../state/appContext";
import type { GenerationDetail } from "../types/contracts";
import { DownloadBar, downloadFilename, downloadStem, downloadTimestamp } from "./DownloadBar";

const DETAIL: GenerationDetail = {
  generationId: "11111111-1111-4111-8111-111111111111",
  status: "succeeded",
  createdAt: "2026-11-20T19:04:45Z",
  sourceType: "text",
  inputPreview: "Hello world.",
  inputFilename: null,
  voiceId: "en_US-lessac-medium",
  voiceName: "Lessac",
  rate: 1,
  volume: 1,
  durationSeconds: 12.5,
  error: null,
  text: "Hello world.",
  sampleRate: 22050,
  alignedWordRatio: 1,
  wordTimings: [],
  cues: [],
};

describe("downloadTimestamp", () => {
  it("formats the creation time in UTC", () => {
    expect(downloadTimestamp("2026-11-20T19:04:45.123456Z")).toBe("20261120-190445");
  });

  it("converts offset timestamps to UTC", () => {
    expect(downloadTimestamp("2026-11-20T20:04:45+01:00")).toBe("20261120-190445");
  });
});

describe("downloadStem", () => {
  it("takes at most six words, lowercased and hyphen-joined", () => {
    expect(
      downloadStem("Hello, world! This is a test of the filename builder.", "2026-11-20T19:04:45Z"),
    ).toBe("hello-world-this-is-a-test_20261120-190445");
  });

  it("ignores non-ASCII characters the same way the API regex does", () => {
    expect(downloadStem("Über café", "2026-11-20T19:04:45Z")).toBe("ber-caf_20261120-190445");
  });

  it("falls back to speech when the input has no usable characters", () => {
    expect(downloadStem("   ", "2026-11-20T19:04:45Z")).toBe("speech_20261120-190445");
  });
});

describe("downloadFilename", () => {
  it("appends the file extension", () => {
    expect(downloadFilename("Hello world.", "2026-11-20T19:04:45Z", "wav")).toBe(
      "hello-world_20261120-190445.wav",
    );
    expect(downloadFilename("Hello world.", "2026-11-20T19:04:45Z", "srt")).toBe(
      "hello-world_20261120-190445.srt",
    );
    expect(downloadFilename("Hello world.", "2026-11-20T19:04:45Z", "vtt")).toBe(
      "hello-world_20261120-190445.vtt",
    );
  });
});

describe("DownloadBar", () => {
  it("offers all three downloads", () => {
    const html = renderToStaticMarkup(
      <AppProvider>
        <DownloadBar detail={DETAIL} />
      </AppProvider>,
    );
    expect(html).toContain("Download audio (WAV)");
    expect(html).toContain("Download subtitles (SRT)");
    expect(html).toContain("Download subtitles (VTT)");
    expect(html).toContain("first words of the input");
  });
});
