# EGM 101 (OpenCode, project scope)

EGM = **Elephant-Goldfish Model** — a spec-driven development protocol.
The **Elephant** holds rich context (docs/designs); **Goldfish** reviewers
run in fresh, isolated contexts to catch hallucinations. Humans own decisions.

All 7 skills set `disable-model-invocation: true`, so invoke explicitly.

## How to invoke in OpenCode

- Mention in prompt: `@egm-brainstorm`, `@egm-draft`, etc.
- Ask plainly: "load the egm-review skill and run it on docs/designs/foo.md".
- IDs match directory names exactly.

## The 7 skills

| Skill | Purpose | Key input |
|---|---|---|
| `egm-brainstorm` | Interactive ideation → `concepts_brief.md` | feature idea (chat) |
| `egm-draft` | Turn brief/notes into `docs/designs/<feature>.md` | `Context File` (optional; defaults to `concepts_brief.md`) |
| `egm-review` | Multi-stage Goldfish review (Stages 5–9) | `TargetFile` (required), optional preset /
| `egm-review-loop` | Reusable antagonistic loop | `TargetFile`, reviewers, standards |
| `egm-resolve` | Triage findings; apply approved edits | `TargetFile`, `LineRange`, `FindingsList` |
| `egm-drift-report` | Design/code drift check | design/README directory |
| `egm-bootstrap` | Generate/correct READMEs (Peanuts/Hay) | `path` (required) |

## Core workflow

1. `/egm-brainstorm` → clarifying questions → `concepts_brief.md`
2. `/egm-draft` → `design_draft.md` → `docs/designs/<feature>.md`
3. `/egm-review docs/designs/<feature>.md` → reports; fix with `/egm-resolve`
4. Human review (PR)
5. Implement to plan
6. `/egm-drift-report <designs>` weekly

## Bootstrapping

`/egm-bootstrap <path>` creates bottom-up README contracts.
>15 subdirs triggers an approval gate. Writes docs only; never commits.

## Artifact locations

- Briefs/drafts/reports → working dir (or set `EGM artifact directory`)
- Designs → `docs/designs/` (with `SITEMAP.md` index)
- Bootstrap READMEs → alongside source

## OpenCode gotchas

- Hidden skills: invoke explicitly (no auto-discovery).
- Subagents (`subagent` tool) required for fresh-context Goldfish reviews; `.opencode/agents/egm-*.md` personas are registered.
- Dependencies: user runs `uv sync`; agent does not auto-install.
- EGM never runs `git commit/add`.
