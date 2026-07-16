---
name: video-script-studio
description: Create resumable, production-ready video script projects through staged requirements diagnosis, scripting, review, and packaging. Use when Codex needs to turn an idea, brief, article, or source material into a shootable video script and complete production package while preserving project state between sessions.
---

# Video Script Studio

Create a video script as a staged, recoverable project. Confirm the current stage and saved state before advancing so users can review decisions without losing prior work.

## Core workflow

1. Diagnose the audience, platform, objective, duration, format, voice, source constraints, and deliverables.
2. Create or resume a project state before producing substantial content.
3. Develop the premise, structure, scenes, narration or dialogue, visuals, and production notes in reviewable stages.
4. Pause at material creative decisions and incorporate user feedback into the saved state.
5. Validate continuity, timing, shootability, and requested deliverables.
6. Package the approved script with the supporting production artifacts requested by the user.

## Project data

Use `scripts/common.py` for stable JSON, state YAML, timestamps, slugs, and atomic text writes. Keep generated project files inside the user-approved project location. Treat malformed state as a recoverable domain error and ask before replacing user-authored data.

## Output quality

- Make every line serve story, information, emotion, or production clarity.
- Separate spoken content from visual direction and production notes.
- Flag assumptions, missing source facts, rights concerns, and impractical shots.
- Preserve approved wording and decisions unless the user requests a revision.
- End with a concise inventory of saved artifacts and the next available stage.
