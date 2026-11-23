/**
 * Every user-visible string in one module (ARCHITECTURE.md section 11,
 * NFR-04). Components read copy from here so future i18n is a file swap and so
 * error advice ("problem + corrective action") stays reviewable in one place.
 *
 * Interpolated entries are functions; static ones are plain strings. Nothing in
 * this module imports React or app state.
 */

/** Plain-language advice keyed by the section 9.1 error code. */
const ERROR_GUIDANCE: Record<string, string> = {
  EMPTY_INPUT: "Paste or type some text, then press Generate audio again.",
  INPUT_TOO_LONG:
    "Shorten the text to 50,000 characters or fewer, or split it into two generations.",
  OUT_OF_RANGE:
    "Check the speaking rate and volume; the allowed range is shown beside each control.",
  VOICE_NOT_FOUND:
    "Pick a voice from the list, or install it with `tts add-voice <name>` and reload.",
  UNSUPPORTED_FILE_TYPE: "Save the text as a plain .txt file, then upload it again.",
  FILE_TOO_LARGE: "Upload a .txt file smaller than 2 MB, or paste the text into the box instead.",
  DECODE_FAILED: "Re-save the file as UTF-8 plain text, then upload it again.",
  NO_VOICES_INSTALLED: "Run `tts add-voice <name>` in a terminal, then reload this page.",
  GENERATION_NOT_FOUND: "Open an entry from History, or create a new generation.",
  GENERATION_NOT_READY: "Wait until the status says Audio ready, then try again.",
  GENERATION_BUSY: "Wait for the current generation to finish, or cancel it first.",
  SUBTITLE_FORMAT_UNKNOWN: "Use one of the subtitle download buttons (SRT or VTT).",
  NOT_FOUND: "Reload the page. If this repeats, check that tts is still running.",
  ENGINE_ERROR:
    "Try a shorter text or a different voice. If it still fails, check the log in your tts data folder.",
  INTERNAL_ERROR:
    "Reload the page and try again. If it still fails, check the log in your tts data folder.",
};

const FALLBACK_GUIDANCE =
  "Try again. If the problem continues, reload the page and check the tts log.";

/** Corrective action for an API error code; never empty. */
export function errorGuidance(code: string): string {
  return ERROR_GUIDANCE[code] ?? FALLBACK_GUIDANCE;
}

export const strings = {
  app: {
    title: "tts",
    tagline: "Local text to speech with synchronized subtitles.",
    mockBadge: "Mock mode: sample data",
    skipLink: "Skip to main content",
    footer: "Everything runs on this machine; nothing is uploaded.",
  },
  error: {
    heading: "Something went wrong",
    guidanceLabel: "What you can do",
    dismiss: "Dismiss",
    dismissLabel: "Dismiss error message",
  },
  input: {
    heading: "Text",
    label: "Text to speak",
    placeholder: "Paste or type the text you want to hear. Paragraph breaks are preserved.",
    uploadLabel: "Upload plain text",
    uploadHelp: "Only plain-text .txt files up to 2 MB are accepted.",
    characterCount: (length: number, max: number, filename: string | null): string =>
      `${length.toLocaleString()} / ${max.toLocaleString()} characters` +
      (filename === null ? "" : ` · loaded from ${filename}`),
    tooLongSuffix: "Shorten the text before generating.",
  },
  validation: {
    emptyInput: "Enter some text before generating. Paste or upload text and try again.",
    noVoices:
      "No voices are installed. Run `tts add-voice <name>` in a terminal, then reload this page.",
    tooLong: (length: number, max: number): string =>
      `Input is ${length.toLocaleString()} characters; the limit is ${max.toLocaleString()}.`,
  },
  voice: {
    heading: "Voice and settings",
    hint: "Choose an installed voice, preview it, and adjust how it speaks. Settings are saved when a control loses focus.",
    noVoicesPrefix: "No voices installed. Run",
    noVoicesSuffix: "in a terminal, then reload this page.",
    selectLabel: "Voice",
    noVoicesOption: "No voices installed",
    preview: "Preview voice",
    previewing: "Playing preview…",
    rateLabel: "Speaking rate",
    volumeLabel: "Volume",
  },
  generate: {
    heading: "Generate",
    hint: "Start a generation, watch progress, and cancel if you change your mind.",
    noVoicesPrefix: "No voices installed, so generation is disabled. Run",
    noVoicesSuffix: "in a terminal, then reload this page.",
    statusEmpty: "Nothing generated yet",
    statusQueued: "Queued. Waiting for the worker.",
    statusGenerating: (index: number, count: number): string =>
      `Generating: ${index} of ${count} sentences done.`,
    statusGeneratingUnknown: "Generating…",
    statusCancelling: "Cancelling…",
    statusMissingDetail: "Finished, but the details could not be loaded. Check the message above.",
    statusReady: "Audio ready.",
    statusFailed: "Generation failed. See the message above.",
    statusCancelled: "Generation cancelled. No audio was saved.",
    generate: "Generate audio",
    cancel: "Cancel generation",
    cancelling: "Cancelling…",
    progressLabel: "Sentences generated",
  },
  playback: {
    heading: "Playback and subtitles",
    empty: "Generate audio to play it back here.",
    missingDetail: "Finished, but the details could not be loaded. Check the message above.",
    failed: "Nothing to play: the generation failed. See the message above.",
    cancelled: "Nothing to play: the generation was cancelled.",
    inProgress: "Playback appears here when generation finishes.",
    audioUnavailable:
      "The audio file could not be loaded, so playback is unavailable. Downloads may still work.",
    audioLabel: "Generated audio",
    play: "Play",
    pause: "Pause",
    playLabel: "Play audio",
    pauseLabel: "Pause audio",
    back: "Back 5 s",
    forward: "Forward 5 s",
    duration: (clock: string): string => `${clock} long`,
    aligned: (percent: number): string => `${percent}% of words timed`,
    hint: "Keyboard: Space plays or pauses, Left and Right arrows skip 5 seconds when focus is outside a control. Click a word or a sentence to jump there.",
  },
  subtitles: {
    wordsLabel: "Words with timings",
    unalignedTitle: "Timing estimated from nearby words",
    noTimings:
      "Timing details are unavailable for this generation, so there is no word highlight. Audio and downloads still work.",
    sentencesHeading: "Sentences",
    jumpLabel: (clock: string, text: string): string => `Jump to ${clock}: ${text}`,
  },
  downloads: {
    heading: "Downloads",
    hint: "Files are named after the first words of the input and when the generation was created.",
    wav: "Download audio (WAV)",
    srt: "Download subtitles (SRT)",
    vtt: "Download subtitles (VTT)",
    preparingWav: "Preparing WAV…",
    preparingSrt: "Preparing SRT…",
    preparingVtt: "Preparing VTT…",
  },
  history: {
    heading: "History",
    countLabel: (total: number): string => `${total} saved generation${total === 1 ? "" : "s"}`,
    empty: "Nothing here yet. Generate audio and it will appear in this list.",
    hint: "Open a finished generation to load its audio and subtitles. Deleting an entry removes only that entry.",
    open: "Open",
    opening: "Opening…",
    delete: "Delete",
    deleting: "Deleting…",
    confirmDelete: "Confirm delete",
    keep: "Keep",
    confirmPrompt: "Delete this entry? This cannot be undone.",
    openLabel: (preview: string): string => `Open generation: ${preview}`,
    deleteLabel: (preview: string): string => `Delete generation: ${preview}`,
    confirmDeleteLabel: (preview: string): string => `Confirm delete generation: ${preview}`,
    keepLabel: (preview: string): string => `Keep generation: ${preview}`,
    noPreview: "(no preview)",
    statusReady: "Ready",
    statusReadyWithDuration: (seconds: number): string => `Ready · ${Math.round(seconds)} s`,
    statusFailed: "Failed",
    statusFailedWithReason: (message: string): string => `Failed: ${message}`,
    statusCancelled: "Cancelled",
    statusQueued: "Queued",
    statusRunning: "Generating…",
    statusCancelling: "Cancelling…",
  },
} as const;
