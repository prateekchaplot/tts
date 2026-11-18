import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { MOCK_DEFAULT_VOICE_ID, MockApi, silentWav } from "./mock";

function readAscii(blob: Blob, offset: number, length: number): Promise<string> {
  return blob.slice(offset, offset + length).text();
}

async function captureApiError(action: () => Promise<unknown>): Promise<ApiError> {
  try {
    await action();
  } catch (error) {
    if (error instanceof ApiError) {
      return error;
    }
    throw error;
  }
  throw new Error("Expected the call to reject with an ApiError.");
}

afterEach(() => {
  vi.useRealTimers();
});

describe("MockApi", () => {
  it("lists voices sorted by language then id", async () => {
    const api = new MockApi();
    const list = await api.listVoices();
    expect(list.total).toBe(2);
    expect(list.defaultVoiceId).toBe(MOCK_DEFAULT_VOICE_ID);
    expect(list.items.map((voice) => voice.id)).toEqual([
      "de_DE-thorsten-medium",
      "en_US-lessac-medium",
    ]);
  });

  it("reports health with the installed voice count", async () => {
    const api = new MockApi();
    await expect(api.getHealth()).resolves.toMatchObject({
      status: "ok",
      version: "0.1.0",
      voicesInstalled: 2,
      defaultVoiceId: MOCK_DEFAULT_VOICE_ID,
    });
  });

  it("returns a valid RIFF preview and rejects unknown voices", async () => {
    const api = new MockApi();
    const preview = await api.previewVoice(MOCK_DEFAULT_VOICE_ID);
    expect(preview.type).toBe("audio/wav");
    expect(await readAscii(preview, 0, 4)).toBe("RIFF");
    expect(preview.size).toBeLessThanOrEqual(44 + 22050 * 5 * 2);

    const error = await captureApiError(() => api.previewVoice("missing"));
    expect(error.code).toBe("VOICE_NOT_FOUND");
    expect(error.status).toBe(422);
  });

  it("accepts .txt uploads and rejects other extensions", async () => {
    const api = new MockApi();
    const textFile = new File(["Hello there"], "notes.txt", { type: "text/plain" });
    await expect(api.uploadFile(textFile)).resolves.toEqual({
      text: "Hello there",
      filename: "notes.txt",
      sizeBytes: textFile.size,
    });

    const pdf = new File(["%PDF-1.7"], "notes.pdf", { type: "application/pdf" });
    const error = await captureApiError(() => api.uploadFile(pdf));
    expect(error.code).toBe("UNSUPPORTED_FILE_TYPE");
    expect(error.status).toBe(415);
    expect(error.message).toContain(".txt");
  });

  it("validates generation input in the documented order", async () => {
    const api = new MockApi();

    expect((await captureApiError(() => api.createGeneration({ text: "   " }))).code).toBe(
      "EMPTY_INPUT",
    );

    const tooLong = await captureApiError(() => api.createGeneration({ text: "a".repeat(50001) }));
    expect(tooLong.code).toBe("INPUT_TOO_LONG");
    expect(tooLong.details).toEqual({ maxChars: 50000, receivedChars: 50001 });

    const unknownVoice = await captureApiError(() =>
      api.createGeneration({ text: "Hello", voiceId: "missing" }),
    );
    expect(unknownVoice.code).toBe("VOICE_NOT_FOUND");

    const badRate = await captureApiError(() => api.createGeneration({ text: "Hello", rate: 3 }));
    expect(badRate.code).toBe("OUT_OF_RANGE");
    expect(badRate.details).toEqual({ field: "rate", min: 0.5, max: 2, value: 3 });
  });

  it("runs a generation through progress to success", async () => {
    vi.useFakeTimers();
    const api = new MockApi();
    const events: string[] = [];
    const created = await api.createGeneration({ text: "Hello world. This is a test." });
    expect(created.status).toBe("queued");

    const unsubscribe = api.openEventStream(created.generationId, (event) => {
      events.push(event.type);
    });
    expect(events).toEqual(["progress"]);

    await vi.advanceTimersByTimeAsync(200);
    expect(events).toEqual(["progress", "progress", "succeeded"]);
    unsubscribe();

    const detail = await api.getGeneration(created.generationId);
    expect(detail.status).toBe("succeeded");
    expect(detail.text).toBe("Hello world. This is a test.");
    expect(detail.wordTimings).toHaveLength(6);
    expect(detail.cues?.length).toBeGreaterThan(0);
    expect(detail.durationSeconds).toBeGreaterThan(0);

    const audio = await api.getAudioBlob(created.generationId);
    expect(await readAscii(audio, 0, 4)).toBe("RIFF");

    const vtt = await api.getSubtitlesText(created.generationId, "vtt");
    expect(vtt.startsWith("WEBVTT\n\n")).toBe(true);
    expect(vtt).toContain("-->");

    const srt = await api.getSubtitlesText(created.generationId, "srt");
    expect(srt.startsWith("1\n")).toBe(true);
    expect(srt).toContain("-->");
    expect(srt).toContain(",");
  });

  it("refuses to delete a queued generation until it is cancelled", async () => {
    vi.useFakeTimers();
    const api = new MockApi();
    const created = await api.createGeneration({ text: "Hello" });

    const busy = await captureApiError(() => api.deleteGeneration(created.generationId));
    expect(busy.code).toBe("GENERATION_BUSY");

    const notReady = await captureApiError(() => api.getAudioBlob(created.generationId));
    expect(notReady.code).toBe("GENERATION_NOT_READY");

    await expect(api.cancelGeneration(created.generationId)).resolves.toEqual({
      generationId: created.generationId,
      status: "cancelled",
    });
    await expect(api.deleteGeneration(created.generationId)).resolves.toBeUndefined();

    const gone = await captureApiError(() => api.getGeneration(created.generationId));
    expect(gone.code).toBe("GENERATION_NOT_FOUND");
    expect(gone.status).toBe(404);
  });

  it("tracks settings and applies partial updates", async () => {
    const api = new MockApi();
    await expect(api.getSettings()).resolves.toEqual({
      defaultVoiceId: MOCK_DEFAULT_VOICE_ID,
      rate: 1,
      volume: 1,
    });
    await expect(api.putSettings({ rate: 1.4 })).resolves.toEqual({
      defaultVoiceId: MOCK_DEFAULT_VOICE_ID,
      rate: 1.4,
      volume: 1,
    });
    const unknownVoice = await captureApiError(() =>
      api.putSettings({ defaultVoiceId: "missing" }),
    );
    expect(unknownVoice.code).toBe("VOICE_NOT_FOUND");
    const badVolume = await captureApiError(() => api.putSettings({ volume: 2 }));
    expect(badVolume.code).toBe("OUT_OF_RANGE");
  });

  it("rejects unknown generations on every detail call", async () => {
    const api = new MockApi();
    for (const call of [
      () => api.getGeneration("missing"),
      () => api.getAudioBlob("missing"),
      () => api.getSubtitlesText("missing", "srt"),
      () => api.cancelGeneration("missing"),
      () => api.deleteGeneration("missing"),
    ]) {
      expect((await captureApiError(call)).code).toBe("GENERATION_NOT_FOUND");
    }
    expect(() => api.openEventStream("missing", () => undefined)).toThrow(ApiError);
  });
});

describe("silentWav", () => {
  it("writes a valid 16-bit mono RIFF header", async () => {
    const blob = silentWav(0.25);
    expect(blob.type).toBe("audio/wav");
    expect(await readAscii(blob, 0, 4)).toBe("RIFF");
    expect(await readAscii(blob, 8, 4)).toBe("WAVE");
    expect(await readAscii(blob, 12, 4)).toBe("fmt ");
    expect(await readAscii(blob, 36, 4)).toBe("data");
    expect(blob.size).toBe(44 + Math.round(0.25 * 22050) * 2);
  });
});
