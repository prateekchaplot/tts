/**
 * RIFF/WAVE inspection for AC9 ("the downloaded audio file plays completely in
 * a standard media player"). The parser walks the chunk table so the specs can
 * assert the file is not truncated and that its declared duration matches the
 * generation detail.
 */

export interface WavInfo {
  /** `1` is PCM, the format the engine writes. */
  audioFormat: number;
  channels: number;
  sampleRate: number;
  byteRate: number;
  blockAlign: number;
  bitsPerSample: number;
  dataBytes: number;
  durationSeconds: number;
  /** `RIFF` size field; must equal `fileBytes - 8` for a complete file. */
  riffSize: number;
}

function ascii(bytes: Uint8Array, offset: number, length: number): string {
  let text = "";
  for (let index = 0; index < length; index += 1) {
    text += String.fromCharCode(bytes[offset + index] ?? 0);
  }
  return text;
}

export function parseWav(bytes: Uint8Array): WavInfo {
  if (bytes.length < 44) {
    throw new Error(`WAV file is too small (${bytes.length} bytes)`);
  }
  if (ascii(bytes, 0, 4) !== "RIFF" || ascii(bytes, 8, 4) !== "WAVE") {
    throw new Error("Not a RIFF/WAVE file");
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const riffSize = view.getUint32(4, true);

  let audioFormat = 0;
  let channels = 0;
  let sampleRate = 0;
  let byteRate = 0;
  let blockAlign = 0;
  let bitsPerSample = 0;
  let dataBytes = -1;

  let offset = 12;
  while (offset + 8 <= bytes.length) {
    const chunkId = ascii(bytes, offset, 4);
    const chunkSize = view.getUint32(offset + 4, true);
    const body = offset + 8;
    if (chunkId === "fmt ") {
      audioFormat = view.getUint16(body, true);
      channels = view.getUint16(body + 2, true);
      sampleRate = view.getUint32(body + 4, true);
      byteRate = view.getUint32(body + 8, true);
      blockAlign = view.getUint16(body + 12, true);
      bitsPerSample = view.getUint16(body + 14, true);
    } else if (chunkId === "data") {
      dataBytes = chunkSize;
    }
    // Chunks are word-aligned: an odd size is followed by one pad byte.
    offset = body + chunkSize + (chunkSize % 2);
  }

  if (channels === 0 || sampleRate === 0 || dataBytes < 0) {
    throw new Error("WAV file is missing its fmt or data chunk");
  }

  return {
    audioFormat,
    channels,
    sampleRate,
    byteRate,
    blockAlign,
    bitsPerSample,
    dataBytes,
    durationSeconds: byteRate === 0 ? 0 : dataBytes / byteRate,
    riffSize,
  };
}

/** Base64 for handing downloaded bytes to the browser for decoding. */
export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const chunk = bytes.subarray(offset, offset + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}
