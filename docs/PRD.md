# Product Requirements Document (PRD)

**Project Name:** tts

## 1. Product Overview
<!-- What the product is, what it enables users to accomplish, its primary purpose, and its overall scope. Keep this section concise. -->

tts is a locally hosted web application that converts text or text files into spoken audio using offline voices running on the user's machine. For every generation, it produces an audio file together with timestamped subtitles aligned to the spoken words. Users can listen to the audio directly in the browser while watching subtitles highlight in sync, and can download the audio and subtitle files. A programmatic API and CLI are planned for a future release and are not part of the initial product.

## 2. Problem Statement
<!-- The business problem, current user difficulties, existing workflow limitations, and why a dedicated solution is needed. Focus on the problem, not the proposed implementation. -->

Text-to-speech tools today force users into trade-offs:

- Cloud-based TTS services require sending text to external servers, which is unsuitable for private or sensitive content and requires an internet connection and accounts or API keys.
- Many existing tools produce audio only, without any timing information, so users who want subtitles, karaoke-style highlighting, or word-aligned captions must create them manually.
- Command-line TTS utilities are powerful but unfriendly to non-technical users who prefer a visual interface: selecting voices, adjusting speech settings, generating, playing, and exporting audio involves multiple separate steps and tools.
- When timestamp data does exist, it is rarely surfaced in the interface; users cannot see words being spoken as they listen, nor easily export subtitles in standard formats.

A dedicated local web application is needed so that any user can turn text into speech on their own machine, see and export accurate word-level subtitles, and complete the entire workflow — input, configure, generate, listen, export — in one place, with no data leaving the device.

## 3. Product Goals
<!-- A numbered or bulleted list of measurable or outcome-oriented goals. Each goal should describe a business or user outcome. -->

1. Enable a user to go from pasted text or an uploaded file to a playable, downloadable audio file without any network access to external services.
2. Produce word-level (and sentence-level) timestamps for every generated audio so subtitles are available automatically, not manually.
3. Let users verify audio and subtitle quality instantly through synchronized in-browser playback with live highlighting.
4. Keep all content and generated artifacts on the user's machine (privacy by default).
5. Deliver a workflow simple enough for a non-technical user to complete a first generation within minutes of installation.

## 4. Target Users
<!-- Primary users, secondary users, their responsibilities, and their relationship with the product. Do not invent unnecessary user personas. -->

- **Primary user: individual local user.** A person who wants spoken audio from their own text (notes, articles, stories, documentation) and optionally subtitles for it. They run the application on their own computer and use it through a browser. They are responsible for supplying text, choosing voice and speech settings, and exporting results.
- **Secondary user (future, out of MVP scope): developer/scripted caller.** A user or script that will invoke the same conversion capability through an API or CLI once those interfaces are released.

## 5. Functional Requirements
<!-- Requirements with unique identifiers in the format "FR-01: Requirement Name". For each requirement: describe the expected product behavior, the user's interaction with the system, relevant validation and failure scenarios, and authorization or approval requirements where applicable. Use concise bullet points beneath each requirement. Order requirements according to the primary user workflow. -->

### FR-01: Text Input
The user provides the text to be spoken either by typing/pasting directly or by uploading a plain-text file.

- The input view accepts typed or pasted text of non-trivial length (multi-thousand-character documents) and preserves paragraph structure for readability.
- The user may upload a text file instead of typing; the file's contents are loaded into the input view where the user can review and edit them before generating.
- Only plain-text formats are accepted for upload in the MVP. If the user selects a file of an unsupported type, the system rejects it with a clear message naming the accepted types.
- If the user attempts to generate with empty or whitespace-only input, generation is blocked and a validation message is shown.
- If the input exceeds a defined maximum length, the system warns the user before generation and states the limit (the limit itself is to be established during initial testing).

### FR-02: Voice Selection
The user chooses which offline voice speaks the text.

- The system lists all voices available on the user's machine, including at minimum the voice's name, language, and gender where the underlying engine exposes them.
- The user can preview any voice with a short built-in sample phrase before selecting it.
- A sensible default voice is preselected so a first-time user can generate without configuring anything.
- If no voices are available on the machine, the system explains that voices must be installed and how, and disables generation.

### FR-03: Speech Settings
The user can adjust how the selected voice speaks the text.

- The user can set speaking rate, volume, and pitch using simple controls with numeric or stepped values and the engine's supported ranges.
- Changing settings does not require regenerating from scratch in a separate screen; the user adjusts and regenerates from the same view.
- Settings outside the supported range are prevented or corrected with a visible message rather than silently accepted.

### FR-04: Audio Generation
The system converts the provided text into an audio file using the selected voice and settings.

- The user initiates generation with a single action and sees progress feedback while synthesis runs; the interface remains usable enough to cancel an in-progress generation.
- On completion, the system presents the generated audio for playback and download together with its subtitles.
- If synthesis fails (for example, engine error or exhausted resources), the user is shown an error message describing what failed and generation may be retried; no partial or corrupt audio file is presented as a successful result.
- Cancelling a generation discards its partial output.

### FR-05: Timestamped Subtitles
The system produces subtitles with timestamps aligned to the generated audio.

- For every successful generation, the system produces word-level timing information (which word is spoken at which point in the audio).
- The system also derives sentence-level segments from word timings, so subtitles can be exported as conventional caption cues.
- Timestamps must align with the actual audio: the timing of a word in the subtitle must correspond to when that word is audible (a measurable tolerance is to be established during initial testing).
- The subtitle text matches the input text; omitted or skipped words are reflected honestly in the timing data rather than fabricated.

### FR-06: Synchronized Playback
The user listens to the generated audio in the browser while the corresponding text is visually highlighted in sync.

- The playback view provides standard controls: play, pause, seek (including seeking by clicking a word or sentence), and stop.
- While playing, the word currently being spoken is visibly highlighted, and the view scrolls to keep it visible for long texts.
- Seeking to any position moves the highlight to the word being spoken at that position.
- After playback ends, highlighting is cleared or reset to the beginning.

### FR-07: Export and Download
The user can save the results of a generation.

- The user can download the generated audio as a standard audio file.
- The user can download subtitles in at least one standard caption format suitable for common video players (e.g., SRT or WebVTT).
- Downloaded files use a sensible default name derived from the input, and the user can distinguish repeated generations of the same text (e.g., by timestamped names).
- If a download fails, the user receives an error message and can retry without regenerating the audio.

### FR-08: Generation History
The system keeps a record of recent generations within the application so the user can return to earlier results without regenerating.

- The history lists recent generations with enough information to identify them (input preview or file name, voice, date/time).
- Selecting a history entry restores its audio, subtitle data, and playback view.
- History is bounded (a maximum number of entries, with oldest evicted); the retention limit is to be established during initial testing.
- The user can delete individual history entries.

## 6. Non-Functional Requirements
<!-- Requirements with unique identifiers in the format "NFR-01: Requirement Name". Consider the applicable categories: reliability, security and access control, performance, usability, observability and auditability, maintainability, data integrity, availability. Only include categories relevant to the product. Describe expected quality attributes only. -->

### NFR-01: Offline Operation and Privacy
- All synthesis runs locally; no user text, generated audio, or timing data is transmitted to external services as part of the core workflow.
- The application is usable without an internet connection after installation.

### NFR-02: Performance
- Synthesis time for a typical short text (a few paragraphs) must be short enough for interactive use; concrete targets must be established during initial testing since no baseline exists.
- The interface remains responsive during generation (no frozen page while synthesis runs).

### NFR-03: Data Integrity
- A stored or exported audio file is always complete and playable; partial audio is never exposed as a finished result.
- Exported subtitle timestamps correspond to the exact audio they accompany; regeneration of the same text with the same settings yields consistent timing data.

### NFR-04: Usability
- A first-time user can complete input → generate → play → download without consulting documentation.
- Validation and error messages state the problem and the corrective action in plain language.
- Playback controls are keyboard accessible.

### NFR-05: Reliability
- A failed generation does not corrupt or remove previously generated results or history entries.
- Repeated generation of the same input succeeds consistently.

### NFR-06: Observability
- The application records diagnostics (generation requests, engine errors, failures with reasons) sufficient for a user or supporter to diagnose a failed generation from local logs.

### NFR-07: Portability
- The application runs on the user's machine across common desktop platforms where offline voices exist; the exact platform set is confirmed during architecture design and stated in user documentation.

## 7. MVP Scope
<!-- Divide into "In scope" (essential capabilities required for the initial usable product) and "Out of scope" (advanced capabilities, non-essential integrations, and future enhancements). Ensure the scope is realistic for an initial implementation. -->

### In scope
- Web UI running locally, with local/offline voices only.
- Text input by typing/pasting and by plain-text file upload.
- Voice selection with preview and a usable default.
- Speaking rate, volume, and pitch controls.
- Audio generation with progress feedback, cancellation, and failure handling.
- Word-level timestamps with derived sentence-level subtitle cues.
- Synchronized in-browser playback with live word highlighting and seek-to-word.
- Download of audio file and subtitles in a standard caption format.
- Bounded in-application generation history with delete.

### Out of scope
- HTTP API and CLI interfaces (planned future release).
- Cloud/online TTS engines or accounts.
- Audio formats beyond a standard default (e.g., format conversion or codec options).
- Advanced editing of subtitle cue boundaries by hand.
- Batch conversion of many files at once.
- Document formats beyond plain text (PDF, EPUB, DOCX, Markdown structure parsing).
- Multi-user access, authentication, or hosted deployment.
- Video rendering with embedded subtitles.
- Voice installation management (the app surfaces installed voices; installing voices is the user's OS-level task).

## 8. Acceptance Criteria
<!-- Numbered, objectively verifiable conditions that determine whether the MVP is complete. Cover all critical functional requirements, important failure scenarios, and security and authorization checks where applicable. Describe observable outcomes; avoid implementation-specific instructions. -->

1. Given pasted multi-paragraph text and the default voice, generating produces a playable audio file without any outbound network request; this can be verified with the machine offline.
2. Given an uploaded plain-text file, its content appears in the input view, is editable, and generates audio identical in behavior to typed input.
3. Uploading a file of an unsupported type shows a rejection message naming accepted types, and no generation starts.
4. Attempting to generate with empty input shows a validation message and does not start synthesis.
5. The voice list shows every installed offline voice with its name and language, and previewing a voice plays a sample in that voice.
6. Changing the speaking rate to a value outside the supported range is either prevented or corrected with a visible message; generation never proceeds with an out-of-range value.
7. For a generated audio, the subtitle data contains a timing entry for each spoken word, and spot-checks confirm words highlight at the moment they are audible within the agreed tolerance.
8. During playback, the currently spoken word is highlighted and the view keeps it visible; clicking a word seeks the audio to that word.
9. The downloaded audio file plays completely in a standard media player.
10. The downloaded subtitle file loads in a standard player or caption tool, and its cue timing matches the generated audio.
11. A deliberately forced synthesis failure (e.g., unavailable engine) shows an error message, presents no partial audio as success, and leaves prior history intact.
12. Cancelling an in-progress generation returns the interface to a ready state and produces no partial result in history or downloads.
13. The history list shows recent generations with input preview, voice, and time; selecting an entry restores its audio and subtitles; deleting an entry removes it and leaves other entries intact.
14. No user text, audio, or timing data appears in any outbound network traffic during the full input → generate → play → export workflow.
15. The complete workflow (input, generate, play, download audio and subtitles) is completable using only the keyboard for essential actions and without documentation.

## 9. Success Metrics
<!-- Measurable indicators of product success. For each metric: explain what it measures, how it relates to product goals, and suggest a baseline or target only when supported by available information. If no baseline exists, explicitly state that it must be established during initial testing. -->

1. **Generation success rate** — percentage of generation attempts that complete with audio and valid timestamps. Measures reliability of the core workflow (Goal 1, 2). No baseline exists; establish during initial testing, then target ≥ 99% excluding deliberately cancelled attempts.
2. **Time to first audio** — elapsed time from initiating generation to playback availability for a representative text. Measures interactive responsiveness (Goal 1, 5). No baseline exists; establish during initial testing.
3. **Timestamp alignment accuracy** — measured deviation between word timings and actual audible speech during spot checks. Directly verifies Goal 2; target tolerance to be defined against initial-test measurements.
4. **Workflow completion without help** — share of first-time users completing input → generate → play → download unaided. Measures Goal 5; baseline to be established through initial user testing.
5. **Offline completeness** — full workflow completion with networking disabled. Verifies Goal 4; target 100%.

## 10. Deliverables
<!-- Expected product and project deliverables, such as: working application, user interface, functional documentation, test cases and test results, evaluation report (if applicable), user documentation, demonstration, known limitations and future enhancements. -->

- Working locally hosted web application implementing the MVP scope.
- User-facing web interface: input/configuration view, playback view with synchronized subtitles, history view.
- User documentation: installation and startup instructions, supported platforms and voices, usage walkthrough, troubleshooting.
- Test cases and test results covering the acceptance criteria, including the offline-operation verification.
- Known limitations document (unsupported file types, platform/voice caveats, retention limits, timing tolerance).
- Roadmap notes for future enhancements (API and CLI access, additional formats, batch processing).
