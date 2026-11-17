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

## Doing

| ID | Task | Branch | Verification | Status |
|---|---|---|---|---|
_(empty — next up: T0.3)_

## Remaining

### P0 — Foundation contracts

| ID | Task | Files | Deps | Acceptance criteria (summary) |
|---|---|---|---|---|
| T0.3 | Error envelope + API skeleton | `src/tts/api/`, `src/tts/app.py`, `src/tts/types.py`, `tests/unit/test_errors.py` | T0.2 | Health response and exact error envelope behavior |
| T0.4 | DB schema + DAL skeleton | `src/tts/history/`, `tests/unit/test_dal.py` | T0.2 | Schema migration, CRUD, active-row eviction protection, delete-with-file |
| T0.5 | Frontend scaffold + contracts | `frontend/` | T0.1 | Build, mock placeholder, strict TypeScript check |
| T0.6 | CI | `.github/workflows/ci.yml` | T0.1 | Four-stage CI with voice cache step |

### P1 — Service layer

| ID | Task | Files | Deps | Acceptance criteria (summary) |
|---|---|---|---|---|
| T1.1 | Voice store | `src/tts/voices/store.py` | T0.2 | Sorted voice metadata, alignment support, valid short preview WAV |
| T1.2 | Engine wrapper | `src/tts/engine/piper_engine.py` | T0.2, T0.3 | Sentence synthesis, sample totals, rate effect, pre-start cancellation |
| T1.3 | Timing reconcile | `src/tts/timing/reconcile.py` | T0.3 | Monotonic timings, honest degraded alignment, zero-phoneme handling |
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
