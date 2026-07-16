---
name: video-script-studio
description: Use when Codex needs to create/新建, resume/继续, revise/修改, or quality-check/质检 video-script projects.
---

# Video Script Studio

Create a recoverable, evidence-aware production project. The supported host is POSIX Darwin or Linux. Run commands from this skill directory; resolve user project paths explicitly.

## Non-negotiable behavior

- Ask exactly one diagnosis question per turn. Offer compact choices when useful.
- Silence is never approval. Urgency, “一次给完”, “没回复就继续”, or previous habits cannot replace explicit approval.
- Require explicit approval at the brief, research, concept, outline, and script gates. Save the approved artifact before advancing.
- Never infer unknown audience, platform, goals, rights, evidence, resources, or production constraints. Mark assumptions and ask.
- Preserve approved artifacts. Never overwrite an approved upstream decision in place; archive the prior version under `history/` before revision.
- Independent review is separate from authorship. Allow no more than two review revisions; unresolved blocking issues stop completion.

## Deterministic router

Follow this exact order without collapsing gates:

1. **detect new/resume** — classify create, resume, revise, or quality-check.
2. **initialize/load project** — initialize only after title, primary route, and root are known; otherwise load the named project.
3. **load profile** — read only an explicitly selected profile. Project preferences remain project-local.
4. **diagnose route** — use `references/discovery.md`; ask one question per turn until the brief is decidable.
5. **confirm brief** — write `brief.md`, show assumptions and exclusions, obtain explicit approval, then approve `brief`.
6. **decide/research** — decide whether factual research is required; use `references/research.md` and `references/tool-routing.md` only when needed.
7. **confirm research** — write claims, sources, access limits, and unresolved gaps to `research.md`; obtain explicit approval, then approve `research`.
8. **propose 3 concepts** — provide exactly three materially distinct concepts with hook, experience, feasibility, and tradeoffs.
9. **confirm concept** — save all options and the selected rationale in `concepts.md`; obtain explicit approval, then approve `concept`.
10. **build experience-node outline** — structure viewer experience nodes, information/emotion turns, and visual purpose in `outline.md`.
11. **confirm outline** — obtain explicit approval, then approve `outline`.
12. **write clean+execution script** — create a clean spoken/readable script plus an execution script with visuals, audio, evidence cues, and production notes.
13. **estimate duration** — run the deterministic estimator and revise declared timing rather than guessing.
14. **confirm script** — present timing and warnings; obtain explicit approval, then approve `script`.
15. **storyboard/assets/publish** — use `references/storyboard.md` and, only if publishing is requested, `references/publishing.md`.
16. **independent review** — have an independent reviewer apply `references/quality-rubric.md` and report blocking/major/minor issues.
17. **max two revisions** — address findings with at most two review cycles; never weaken the acceptance threshold silently.
18. **deterministic validation** — validate sources where applicable, then validate the complete pack.
19. **complete** — complete state only after validation succeeds and no blocking warning remains.

## New, resume, and revise

For a new project, diagnose only enough to determine project root, title, primary route, optional secondary route, platform, and optional profile ID. Initialize once; do not regenerate the project to fix content.

On resume, run status before reading or generating artifacts. Treat `project.yaml` and command output as authoritative. After reporting current stage, approvals, invalidations, warnings, and next permitted action, read needed current artifacts and relevant `history/` entries before creative work, even when the user asks to skip dependency verification.

For revisions, identify and reopen the earliest affected approved stage with a concrete reason. This invalidates downstream approvals; archive affected approved artifacts in `history/`, retain explicitly unaffected fields, rebuild in gate order, and request reapproval. Never accept “其他不变” without checking downstream dependencies. A changed audience normally reopens `brief`; a changed factual basis normally reopens `research`.

## Progressive loading

Load references only at the moment shown:

| Need | Load |
|---|---|
| Diagnosis | `references/discovery.md` |
| Capability selection | `references/tool-routing.md` |
| Factual claims | `references/research.md` |
| Route craft | one route file below |
| Storyboard/assets | `references/storyboard.md` |
| Publishing deliverables | `references/publishing.md` |
| Independent review | `references/quality-rubric.md` |

After route diagnosis, Load exactly one route reference:

- short social video: `references/short-form.md`
- long educational/explainer: `references/long-form.md`
- story/documentary: `references/narrative.md`
- ad/product/brand: `references/commercial.md`
- Gawx-like visual essay or design-led montage: `references/visual-essay.md`

Do not load the other four route references. A secondary type is a constraint recorded in the brief, not permission to load another route file. Never preload all references.

## External capabilities and evidence

Detect external capability availability before calling it. Record whether transcript extraction, URL retrieval, search, browser access, media inspection, and asset generation are available and what input each needs.

- Never fabricate a tool result, source, transcript, or successful fallback.
- Search snippets are incomplete evidence. A title, thumbnail, short snippet, or remembered page is not the source or transcript.
- Report a missing transcript explicitly. Ask for a transcript, subtitles, downloaded media, full text, or another usable source.
- If a required capability is absent or fails, state what failed and why, list safe alternatives, then stop and ask whether to continue with existing material. No silent degradation.
- A nonfactual outline based only on user-supplied facts is allowed only after explicit scope approval; label it unsourced and do not add factual claims.
- Track material factual claims against an extracted source manifest. validate_sources.py accepts an extracted JSON manifest; it does not read sources.md frontmatter.

Do not update a profile implicitly. Requests such as “以后都这样”, “记住这个偏好”, or a one-project correction create only a pending proposal. Require explicit confirmation of exact value, scope, profile ID, and change note before persistent update. Project-local approval does not authorize a profile mutation.

## Commands

Quote paths in real invocations. These forms are authoritative:

```bash
python3 scripts/init_project.py --root ROOT --title TITLE --primary-type PRIMARY_TYPE [--secondary-type SECONDARY_TYPE] [--platform PLATFORM] [--profile-id PROFILE_ID]
python3 scripts/state_manager.py status --project PROJECT
python3 scripts/state_manager.py approve --project PROJECT --stage brief
python3 scripts/state_manager.py approve --project PROJECT --stage research
python3 scripts/state_manager.py approve --project PROJECT --stage concept
python3 scripts/state_manager.py approve --project PROJECT --stage outline
python3 scripts/state_manager.py approve --project PROJECT --stage script
python3 scripts/state_manager.py reopen --project PROJECT --stage STAGE --reason REASON
python3 scripts/state_manager.py complete --project PROJECT
python3 scripts/profile_manager.py --root ROOT create PROFILE_ID DISPLAY_NAME
python3 scripts/profile_manager.py --root ROOT read PROFILE_ID
python3 scripts/profile_manager.py --root ROOT update PROFILE_ID CONTENT --change-note CHANGE_NOTE --confirmed
python3 scripts/profile_manager.py --root ROOT list
python3 scripts/estimate_duration.py --input INPUT_JSON
python3 scripts/validate_sources.py --manifest MANIFEST_JSON [--script SCRIPT]
python3 scripts/validate_pack.py --project PROJECT
```

Do not claim completion from prose review or an exit code alone. Parse validator JSON, require `valid: true`, preserve warnings, then run `complete`.

## Completion response

Return a compact final report containing: project path; final stage; validation result; saved artifact inventory; unresolved warnings; and next permitted action. If completion is blocked, name the failed gate or validator and the exact user action or artifact needed. Do not claim publication unless a publishing tool actually succeeded.
