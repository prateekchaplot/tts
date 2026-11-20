# tts — Task Tracker

Source of truth for task definitions: `docs/ARCHITECTURE.md` §14.
This file tracks status only; the architecture document is binding.

**Working mode:** hold-after-every-task

Statuses: done (PR merged) · doing (branch open, pending review) · remaining · cut (with date + reason)

## Done

| ID | Branch | PR | Merge commit | Verified |
|---|---|---|---|---|
| T0.1 | `arch/tts/t0.1` | [#1](https://github.com/prateekchaplot/tts/pull/1) | `0018cb8db3a3e169021a70d010325a6d2a19dfaa` | Editable install on Python 3.12; `tts --version` → `0.1.0`; `npm ci`; `git diff --check` |
| T0.2 | `arch/tts/t0.2` | [#2](https://github.com/prateekchaplot/tts/pull/2) | `9839b9ef8c4e5adea2b5e6e87f6fa5af017ccce1` | 5 unit tests; Ruff check/format; strict mypy; `git diff --check` |
| T0.3 | `arch/tts/t0.3` | [#3](https://github.com/prateekchaplot/tts/pull/3) | `40d2296e5bb18973fa7bb1878e2407db9d1d8ea6` | 14 unit tests; Ruff check/format; strict mypy; `git diff --check` |
| T0.4 | `arch/tts/t0.4` | [#4](https://github.com/prateekchaplot/tts/pull/4) | `0817306b0ec9dea1959ed146675fa3a23dc90915` | 32 unit tests; Ruff check/format; strict mypy; `git diff --check` |
| T0.5 | `arch/tts/t0.5` | [#5](https://github.com/prateekchaplot/tts/pull/5) | `a479bc1c1f85f8580e1875e3012f668da9b35291` | 34 vitest tests; `tsc --noEmit`; ESLint; Prettier; `vite build`; mock-mode build; 32 pytest; Ruff; strict mypy; `git diff --check` |
| T0.6 | `arch/tts/t0.6` | [#6](https://github.com/prateekchaplot/tts/pull/6) | `cacfd8de820c503ab074b5b33f2cccd4d7a392d3` | Workflow YAML parses (4 jobs); Ruff check/format on `src/tts tests`; strict mypy; 32 pytest; ESLint; `tsc --noEmit`; 34 vitest; PR CI green (lint, unit ubuntu+windows, integration, e2e); voice cache saved (58 MB) |
| T1.1 | `arch/tts/t1.1` | [#7](https://github.com/prateekchaplot/tts/pull/7) | `c6363891b660cc7cb013a16a01fe284676316931` | 43 unit tests (11 new); 3 integration tests vs `en_US-lessac-medium` (alignments supported, 2.73 s preview WAV); Ruff check/format; strict mypy; PR CI green (lint, unit ubuntu+windows, integration) |
| T1.2 | `arch/tts/t1.2` | [#8](https://github.com/prateekchaplot/tts/pull/8) | `bbc90d5db39cca15a2520bfbfa4cd1a2d3dd4016` | 52 unit tests (9 new); 6 integration tests vs `en_US-lessac-medium` (3 new); Ruff check/format; strict mypy; PR CI green (lint, unit ubuntu+windows, integration, e2e) |

## Doing

| ID | Task | Branch | Verification | Status |
|---|---|---|---|---|
| T1.3 | Timing reconcile | `arch/tts/t1.3` | 66 unit tests (14 new); Ruff check/format; strict mypy; 6 integration tests; real-voice manual check (`en_US-lessac-medium`, ratio 0.909, monotonic) | branch open, pending review |

## Remaining

### P0 — Foundation contracts

_All P0 tasks done._

### P1 — Service layer

| ID | Task | Files | Deps | Acceptance criteria (summary) |
|---|---|---|---|---|
| T1.4 | Subtitles | `src/tts/subtitles/` | T0.3 | Cue boundary rules and byte-exact SRT/VTT fixtures |
| T1.5 | History DAL completion | `src/tts/history/dal.py` | T0.4 | Consistent transactional deletion, eviction ordering, settings seeding |
| T1.6 | Jobs manager | `src/tts/jobs/` | T1.2, T1.3, T1.4, T1.5 | Progress/success, atomic failure cleanup, cancellation, sequential jobs |

### P2 — HTTP surface

| ID | Task | Files | Deps | Acceptance criteria (summary) |
|---|---|---|---|---|
| T2.1 | Uploads + voices routes | `src/tts/api/routes/uploads.py`, `voices.py` | T0.3, T1.1 | Upload validation, preview WAV, no-voice response |
| T2.2 | Generations routes | `src/tts/api/routes/generations.py` | T0.3, T1.6 | Create/SSE/cancel/delete, validation/errors, audio and subtitle exports |
| T2.3 | Settings route + first-run bootstrap | `src/tts/api/routes/settings.py`, `src/tts/jobs/manager.py` | T0.3, T1.6 | Lazy defaults, partial persistence, invalid voice rejection, offline startup |

### P3 — UI against contracts

| ID | Task | Files | Deps | Acceptance criteria (summary) |
|---|---|---|---|---|
| T3.1 | App shell + input + voice + generate | `frontend/src/App.tsx`, components, state wiring | T0.5 | Input/upload, validation, settings ranges, voice preview, no-voice guidance |
| T3.2 | Playback + downloads | `frontend/src/` playback components and hook | T0.5 | Highlight/seek/reset behavior and correctly named downloads |
| T3.3 | History | `frontend/src/` history component | T0.5 | History preview, restore, and individual deletion |

### P4 — Integration

| ID | Task | Files | Deps | Acceptance criteria (summary) |
|---|---|---|---|---|
| T4.1 | Live wiring + eviction + settings persistence | `frontend/src/api/index.ts`, `frontend/src/state/appContext.tsx`, `src/tts/history/dal.py` | P2, P3 | Live browser flow, persisted settings, bounded history eviction |
| T4.2 | Accessibility + error-copy pass | `frontend/src/components/`, `frontend/src/strings.ts` | T3.1–T3.3 | Keyboard-only workflow manually verified and recorded |
| T4.3 | Observability polish | `src/tts/config.py`, `src/tts/jobs/manager.py` | P2 | Failure reason logged without full input text |

### P5 — Verification + docs

| ID | Task | Files | Deps | Acceptance criteria (summary) |
|---|---|---|---|---|
| T5.1 | E2E suite | `tests/e2e/` | T4.1 | All 15 acceptance criteria tested or recorded as manual checks |
| T5.2 | Docs | `README.md`, `docs/USER_GUIDE.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/PRD.md` | T5.1 | Fresh-machine workflow completes using README alone |
| T5.3 | Measurement | `tests/measure.py`, `docs/MEASUREMENTS.md` | T4.1 | Performance and timing measurements with hardware note |

## Notes

- Architecture deviation: `@vitejs/plugin-react` has no 7.x release. Used 5.2.x, whose peer range supports Vite 7; confirmed against npm registry metadata.
- `npm ci` reports three dev dependency advisories through Vitest: one moderate and two critical. Fix requires Vitest 5.x, outside the architecture's specified 3.x stack; recorded for review without changing that decision.
- T0.2: no architecture deviations. Verification ran on Python 3.12; pytest used `.venv/pytest-tmp` because the default system temp directory was inaccessible.
- T0.3: §9.1 has no generic request-validation code; pydantic `RequestValidationError` maps to 422 `OUT_OF_RANGE` with `{field, reason}`, and unmapped HTTP errors map 404/405 → `NOT_FOUND`, others → `INTERNAL_ERROR`. Health counts `*.onnx` files directly to avoid depending on the T1.1 voice store. Error envelopes always carry a `details` key (`null` when absent).
- T0.4 decisions: `Dal` takes an optional keyword `history_limit` (default 20) because §7.7 fixes `Dal(data_dir)` but eviction needs the `TTS_HISTORY_LIMIT` value; jobs/app pass `settings.history_limit` in later tasks. `get_settings`/`put_settings` are a pure kv store — lazy seeding with voice discovery stays in the T2.3 settings route so `history` does not import `voices`; T1.5 adds the NFR-05 consistency property tests. `get()` returns raw snake_case rows with JSON columns as strings; API-layer mapping to camelCase happens in P2. `delete()`/eviction remove the audio file before the row (idempotent on retry) inside the single RLock, and never inspect status — active-row gating is the caller's job.
- T0.5 decisions: §12 lists `voices` in state but its action set had no way to populate it; added `VOICES_LOADED` to `appContext.tsx` and synced §12 in this PR (T3.1 depends on it). Added the frontend lint toolchain (`typescript-eslint`, `eslint-plugin-react-hooks`, `@eslint/js`, `globals`, flat `eslint.config.js`, Prettier config, `lint`/`format:check` scripts) because T0.6's CI runs eslint/prettier and no other task owns those files; §5's lint row names the packages. `package.json` changes follow the shared-file protocol and affect T0.6.
- T0.5 mock: `api/mock.ts` is a working in-memory `ApiInterface` (sorted voices, valid silent-WAV preview, upload type/size checks, generate → progress → succeeded with synthetic timings/cues, SRT/VTT, settings validation, cancel/delete rules), not a stub, so P3 can build against it. `openEventStream(generationId, onEvent)` returns an unsubscribe function and emits typed events; components dispatch reducer actions, keeping `api/client.ts` React-free.
- T0.5 build switch: `api/index.ts` exports `apiMode`; the shell shows a "Mock mode" badge so `VITE_API_MODE=mock` is observable in a build. Verified the live bundle tree-shakes the mock and vice versa. `frontend/dist` stays gitignored.
- T0.6: `.github/workflows/ci.yml` chains lint → unit (ubuntu+windows) → integration → e2e with pip/npm/voice caches; voice cache key is `piper-voice-en_US-lessac-medium-v1`. Integration/e2e test steps are guarded because those suites land in T1.6/T5.1, so the skeleton repo is green while the stages stay wired. Downstream contract: T5.1 must add `tests/e2e/playwright.config.ts` (Playwright's default `testDir` is the config's own directory) and the workflow runs `npx playwright test` from `frontend/`. Ruff in CI is scoped to `src/tts tests` because ruff 0.17.5 reformats the Python block inside `docs/ARCHITECTURE.md`; prettier's `format:check` only passes on an LF checkout (this Windows clone uses `core.autocrlf=true`). Actions use current majors (checkout v7, setup-python v7, setup-node v7, cache v6) so no Node 20 deprecation warnings appear.
- T1.1 environment finding: importing `onnxruntime` 1.32 crashed with an access violation on this machine because `C:\Windows\System32\MSVCP140.dll` was 14.27 (VS 2019 redist) while the pinned runtime needs a current one. Installing the latest VC++ 2015–2022 x64 redistributable (now 14.52) fixed it; `import piper` and real-voice tests run. T5.2 must document the VC++ redistributable as an install prerequisite (README/KNOWN_LIMITATIONS), since the packaged app fails the same way on a machine with an old redist.
- T1.1 decisions: `store.py` follows §7.3's no-settings signatures by using a module-level voices dir set by `ensure_data_dirs(settings)`; using the store before that raises `RuntimeError`. Unknown/unsafe voice ids raise `VoiceNotFoundError` (a `LookupError`), which T2.1 maps to 422 `VOICE_NOT_FOUND` / 409 `NO_VOICES_INSTALLED`. `piper` is imported lazily inside `load_voice`/`preview_wav`/`install_voice`, so unit tests and the API import path never pay the onnxruntime cost. `supports_alignments` is read from the loaded session having a second output (the patched phoneme-width tensor, `/Ceil_output_0` on `en_US-lessac-medium`); a model without it loads unpatched and reports `False`. `VoiceInfo.language` comes from the config's `language.code`, falling back to the id prefix; voices with a missing/invalid `.onnx.json` are logged and skipped. Install delegate is `piper.download_voices.download_voice(name, voices_dir)`.
- T1.1 shared file: `pyproject.toml` gains the `integration` pytest marker (append-only `[tool.pytest.ini_options]` config). Dependent tasks: T1.2–T1.6, T2.x, T4.1, T5.1, T5.3 add tests under `tests/integration` and must keep the marker registered. Consequence: T0.6's guarded integration CI stage now finds tests and runs `pytest tests/integration` against the cached voice.
- T1.2 decisions: `char_offset_map` is authoritative — the engine validates each span (in bounds, non-overlapping) and calls `voice.synthesize(text[start:end])` per span rather than passing the whole text to piper's internal espeak splitter, which exposes no offsets and could disagree with the caller's segmentation. A span that piper renders as multiple chunks is concatenated (samples and alignments) so one span always yields one `SentenceAudio`; a span with no audio stays as an empty `SentenceAudio` with `supports_alignments=false`. `piper`/`SynthesisConfig` are imported lazily inside `synthesize` so `tts.engine` stays off the onnxruntime import path; unit tests stub `sys.modules["piper"]` to preserve T1.1's `preview_wav` isolation assertion.
- T1.2 deviation (measurement): piper 1.8's stochastic duration predictor is sublinear at `length_scale=2` — rate 0.5 measures ~1.73x the rate 1.0 duration on `en_US-lessac-medium`, outside the AC's 10% band, so the strict duration-ratio check uses rate 1.25 (nominal 0.8x, measured ~0.82x) averaged over 3 runs; the rate→`length_scale=1/rate` mapping itself is unit-tested and slower rates still produce measurably longer audio. T5.3 should measure real rate/duration scaling before documenting it.
- T1.2 environment note: a bare `pytest` run fails collection because `tests/unit/test_voices_store.py` and `tests/integration/test_voices_store.py` share a basename and neither directory is a package; CI passes because it runs each directory separately. New test files use unique names.
- T1.2 local integration voice: `en_US-lessac-medium` was downloaded to the gitignored `.venv/tts-data/voices` and integration tests ran with `TTS_DATA_DIR=.venv/tts-data`.
- T1.3 decisions: `timing/` also ships an `__init__.py` (a package needs one; §6 lists only `reconcile.py`). `split_words` is exported so callers group text with the same whitespace tokenizer; because a sentence below threshold collapses to exactly one entry, T1.6 should take per-sentence entry counts by deriving on a single-sentence `SynthesisResult` rather than assuming one entry per token. Matching removes piper's `^`/`$`/`_` and espeak's `" "` from both sequences — the space removal is required because espeak expands numbers into several words (`42` → `fˈɔːɹti tˈuː`) while punctuation-only tokens such as `—` phonemize to nothing. A word counts as aligned when the longest contiguous `difflib` match covers ≥ 60% of its phonemes; the sentence collapse threshold is the same 60% and is inclusive (`3/5` stays, `2/5` collapses). `aligned_word_ratio` counts every token, so a collapsed sentence contributes its token count as unaligned; `-1.0` is returned only when `SynthesisResult.supports_alignments` is false or there are no sentences, and in that case no phonemization is attempted. Timing is accumulated in exact milliseconds across sentences and rounded half-up per word, then clamped into `[previous_end, sentence_end]`, so integer rounding cannot break monotonicity.
- T1.3 real-voice check: manual run on `en_US-lessac-medium` with "Emoji 🙂 stays honest. Yes — indeed, the 42 dogs rest!" reconciled 10/11 tokens (ratio 0.909), monotonic; `—` produced the expected zero-width unaligned entry, and espeak expands 🙂 into "slightly smiling face", which reconciles honestly. The emoji unit fixture uses a synthetic zero-phoneme voice because real espeak speaks emoji names.
- T1.3 environment note: `.venv/pytest-tmp` became undeletable (`WinError 5`) on this machine, so verification used fresh `--basetemp .venv/ptmp-*` directories; the default system temp directory remains inaccessible (see T0.2).
