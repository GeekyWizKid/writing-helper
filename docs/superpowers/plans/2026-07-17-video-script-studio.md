# Video Script Studio Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, test, install, and exercise a production-ready Codex Skill that guides users from video brief through research, concepts, outline, script, storyboard, production assets, publishing material, and independent review across five video types.

**Architecture:** Keep repository-owned Skill source under `skills/video-script-studio/`; keep persistent creator profiles outside the Skill at `~/.codex/video-script-studio/profiles/`; generate projects under the caller's `video-projects/` directory. `SKILL.md` is a compact state-machine router, focused references supply type-specific creative guidance, and standard-library Python CLIs enforce deterministic boundaries.

**Tech Stack:** Codex Skill Markdown, YAML metadata, Python 3.11+ standard library, `unittest`, `uv` for isolated PyYAML validation, Codex CLI 0.142+, Git and GitHub CLI.

---

## Scope and terminal acceptance

In scope: five primary routes (`short-form`, `long-form`, `narrative`, `commercial`, `visual-essay`), optional secondary expression labels, explicit approval gates, resumable project state, isolated versioned creator profiles, claim/source integrity, type-specific duration estimation, complete production-pack validation, capability-based tool routing, and a real Codex CLI smoke test.

Out of scope: media generation, platform publishing, analytics access, performance promises, a frontend/API/database, and multi-agent behavior inside the user-facing Skill.

Done means: deterministic tests pass; the official Skill validator passes; a clean temporary Codex installation completes a real visual-essay project; independent spec and quality reviews have no unresolved high-severity findings; the PR is green, merged, and present on remote `main`.

## Repository file map

```text
skills/video-script-studio/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── discovery.md
│   ├── tool-routing.md
│   ├── research.md
│   ├── short-form.md
│   ├── long-form.md
│   ├── narrative.md
│   ├── commercial.md
│   ├── visual-essay.md
│   ├── storyboard.md
│   ├── publishing.md
│   └── quality-rubric.md
├── assets/
│   ├── brief-template.md
│   ├── profile-template.md
│   ├── project-state-template.yaml
│   └── production-pack-template.md
├── scripts/
│   ├── __init__.py
│   ├── common.py
│   ├── init_project.py
│   ├── state_manager.py
│   ├── profile_manager.py
│   ├── estimate_duration.py
│   ├── validate_sources.py
│   └── validate_pack.py
└── tests/
    ├── __init__.py
    ├── helpers.py
    ├── test_scaffold_contract.py
    ├── test_init_project.py
    ├── test_state_manager.py
    ├── test_profile_manager.py
    ├── test_estimate_duration.py
    ├── test_validate_sources.py
    ├── test_validate_pack.py
    ├── test_reference_contracts.py
    └── test_scenarios.py
scripts/verify-video-script-studio-e2e.sh
```

## Dependencies and parallel boundaries

```text
Task 1 scaffold
  ├─ Task 2 project initialization ─ Task 3 state machine
  ├─ Task 4 profiles
  ├─ Task 5 duration
  └─ Task 6 sources
Tasks 2-6 ─ Task 7 pack validation
Tasks 1-7 ─ Task 8 references/templates + Task 9 router (parallel)
Tasks 8-9 ─ Task 10 scenarios ─ Task 11 real E2E ─ Task 12 PR/merge
```

After Task 1, Tasks 2, 4, 5, and 6 may run in parallel because they own disjoint files. Task 3 depends on Task 2. Tasks 8 and 9 may run in parallel only after deterministic interfaces settle. No two subagents edit the same file concurrently; the coordinator integrates shared files and performs both review gates.

## Task 1: Scaffold the Skill and lock structural contracts

**Files:**
- Create: `skills/video-script-studio/SKILL.md`
- Create: `skills/video-script-studio/agents/openai.yaml`
- Create: `skills/video-script-studio/scripts/__init__.py`
- Create: `skills/video-script-studio/scripts/common.py`
- Create: `skills/video-script-studio/tests/__init__.py`
- Create: `skills/video-script-studio/tests/helpers.py`
- Create: `skills/video-script-studio/tests/test_scaffold_contract.py`

- [ ] **Step 1: Write the failing scaffold contract test**

```python
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ScaffoldContractTests(unittest.TestCase):
    def test_required_top_level_files_exist(self):
        required = ["SKILL.md", "agents/openai.yaml", "scripts/__init__.py",
                    "scripts/common.py", "tests/__init__.py", "tests/helpers.py"]
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_skill_name_is_stable(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name: video-script-studio$")

    def test_no_unresolved_placeholders(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b(TBD|TODO|FIXME)\b", text))
```

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_scaffold_contract.py' -v`

Expected: FAIL because the package/files are absent.

- [ ] **Step 3: Generate the standard scaffold**

```bash
python3 /Users/apulu/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  video-script-studio --path skills --resources scripts,references,assets \
  --interface 'display_name=Video Script Studio' \
  --interface 'short_description=分阶段创作可拍摄的视频脚本与完整制作包' \
  --interface 'default_prompt=使用 $video-script-studio 从需求诊断开始创建一个可恢复的视频脚本项目。'
```

- [ ] **Step 4: Implement common primitives**

`common.py` exposes these exact public contracts:

| Symbol | Contract |
|---|---|
| `StudioError` | Domain exception whose message is safe for CLI JSON output |
| `utc_now_iso() -> str` | UTC ISO-8601 timestamp with seconds and `Z` suffix |
| `safe_slug(value: str) -> str` | Safe Chinese/English/digit/hyphen slug or `untitled-video` |
| `atomic_write_text(path: Path, text: str) -> None` | Parent creation, same-directory temporary file, `os.replace` |
| `read_json(path: Path) -> dict` | UTF-8 JSON object or `StudioError` |
| `write_json(path: Path, value: dict) -> None` | Stable UTF-8 JSON through atomic write |
| `dump_state_yaml(value: dict) -> str` | Deterministic YAML-subset serialization |
| `load_state_yaml(path: Path) -> dict` | YAML-subset parsing with schema/type errors |

Use a dependency-free YAML subset (strings, booleans, nulls, nested mappings). `tests/helpers.py` loads scripts with `importlib.util.spec_from_file_location` because the Skill directory is hyphenated.

- [ ] **Step 5: Run GREEN and validate**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -v
uv run --with pyyaml python /Users/apulu/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/video-script-studio
```

Expected: tests PASS and validator prints `Skill is valid!`.

- [ ] **Step 6: Commit**

```bash
git add skills/video-script-studio
git commit -m "feat: scaffold video script studio skill"
```

## Task 2: Initialize deterministic, resumable projects

**Files:**
- Create: `skills/video-script-studio/scripts/init_project.py`
- Create: `skills/video-script-studio/tests/test_init_project.py`
- Create: `skills/video-script-studio/assets/project-state-template.yaml`

- [ ] **Step 1: Write failing tests** covering safe Chinese/English slugs, `untitled-video`, `-02` collisions, all required artifacts, `history/`, invalid type rejection, and JSON CLI output.

```python
def test_initializes_complete_project_skeleton(self):
    result = init_project(root=self.tmp, title="寻找个人风格", primary_type="visual-essay")
    project = Path(result["path"])
    self.assertEqual(result["status"], "created")
    self.assertTrue((project / "project.yaml").is_file())
    for name in REQUIRED_ARTIFACTS:
        self.assertTrue((project / name).is_file(), name)
    self.assertTrue((project / "history").is_dir())
```

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_init_project.py' -v`

Expected: FAIL because `init_project.py` is absent.

- [ ] **Step 3: Implement the initializer**

Define `PRIMARY_TYPES` as exactly `short-form`, `long-form`, `narrative`, `commercial`, and `visual-essay`. Define `REQUIRED_ARTIFACTS` as `brief.md`, `research.md`, `concepts.md`, `outline.md`, `script.md`, `storyboard.md`, `assets.md`, `publish.md`, `sources.md`, and `review.md`.

Public signature: `init_project(root: Path, title: str, primary_type: str, secondary_type: str | None = None, platform: str = "unspecified", profile_id: str | None = None, date: str | None = None) -> dict`. It returns `status`, `project_id`, and absolute `path`.

New projects begin at `brief_pending`; all approvals are `pending`; files are atomic; existing directories are never overwritten.

- [ ] **Step 4: Implement CLI** with `--root`, `--title`, `--primary-type`, `--secondary-type`, `--platform`, and `--profile-id`. Success prints one JSON object and exits `0`; invalid input prints sanitized JSON and exits `2`.

- [ ] **Step 5: Run GREEN**

Run: `python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_init_project.py' -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/video-script-studio/scripts/init_project.py skills/video-script-studio/assets/project-state-template.yaml skills/video-script-studio/tests/test_init_project.py
git commit -m "feat: initialize resumable video projects"
```

## Task 3: Enforce approvals and downstream invalidation

**Files:**
- Create: `skills/video-script-studio/scripts/state_manager.py`
- Create: `skills/video-script-studio/tests/test_state_manager.py`
- Modify: `skills/video-script-studio/scripts/common.py`

- [ ] **Step 1: Write failing tests** for ordered `brief → research → concept → outline → script` approvals, skipped-stage rejection, idempotency, upstream reopen, history manifest, and downstream invalidation.

```python
def test_reopening_concept_invalidates_downstream(self):
    for stage in ("brief", "research", "concept", "outline", "script"):
        approve(self.project, stage)
    (self.project / "outline.md").write_text("approved outline", encoding="utf-8")
    reopen(self.project, "concept", reason="核心命题改变")
    state = load_state(self.project)
    self.assertEqual(state["approvals"]["concept"], "pending")
    self.assertEqual(state["approvals"]["outline"], "invalidated")
    self.assertEqual(state["approvals"]["script"], "invalidated")
    self.assertTrue(any((self.project / "history").iterdir()))
```

- [ ] **Step 2: Run RED** with `python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_state_manager.py' -v`.

- [ ] **Step 3: Implement exact interfaces**

Define `STAGES` as exactly `brief`, `research`, `concept`, `outline`, and `script`. Expose `load_state(project: Path) -> dict`, `save_state(project: Path, state: dict) -> None`, `approve(project: Path, stage: str) -> dict`, `reopen(project: Path, stage: str, reason: str) -> dict`, and `status(project: Path) -> dict`.

`reopen` snapshots affected non-empty files under `history/<timestamp>-<stage>/`, records the reason, sets selected stage to `pending`, and later stages to `invalidated`.

- [ ] **Step 4: Add CLI subcommands** `approve`, `reopen`, and `status`; run the focused suite and expect PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/video-script-studio/scripts/common.py skills/video-script-studio/scripts/state_manager.py skills/video-script-studio/tests/test_state_manager.py
git commit -m "feat: enforce video project approval gates"
```

## Task 4: Manage isolated, versioned creator profiles

**Files:**
- Create: `skills/video-script-studio/scripts/profile_manager.py`
- Create: `skills/video-script-studio/tests/test_profile_manager.py`
- Create: `skills/video-script-studio/assets/profile-template.md`

- [ ] **Step 1: Write failing tests** for safe IDs, traversal rejection, isolated directories, explicit update confirmation, monotonically increasing versions, sample directory creation, and list/read behavior.

```python
def test_update_requires_explicit_confirmation(self):
    create_profile(self.root, "main", "主账号")
    with self.assertRaises(StudioError):
        update_profile(self.root, "main", "new content", confirmed=False, change_note="test")
```

- [ ] **Step 2: Run RED** with the focused `test_profile_manager.py` suite.

- [ ] **Step 3: Implement**

Expose `create_profile(root: Path, profile_id: str, display_name: str) -> dict`, `read_profile(root: Path, profile_id: str) -> dict`, `update_profile(root: Path, profile_id: str, content: str, confirmed: bool, change_note: str) -> dict`, and `list_profiles(root: Path) -> list[dict]`.

Each profile contains `profile.md`, `style-analysis.md`, `constraints.md`, `samples/`, and `versions/manifest.json`; confirmed updates snapshot all three Markdown files under `versions/vNNN/`.

- [ ] **Step 4: Add CLI, run GREEN, and commit**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_profile_manager.py' -v
git add skills/video-script-studio/scripts/profile_manager.py skills/video-script-studio/assets/profile-template.md skills/video-script-studio/tests/test_profile_manager.py
git commit -m "feat: add versioned creator profiles"
```

## Task 5: Estimate duration by primary type

**Files:**
- Create: `skills/video-script-studio/scripts/estimate_duration.py`
- Create: `skills/video-script-studio/tests/test_estimate_duration.py`

- [ ] **Step 1: Write failing tests** for Chinese/English speech, pauses, shot durations, narrative action/response time, visual-essay scene sums, commercial target warnings, and malformed rows.

```python
def test_visual_essay_uses_scene_duration_not_voiceover_words(self):
    result = estimate({"primary_type": "visual-essay", "segments": [
        {"id": "S1", "duration_seconds": 12, "voiceover": "开始"},
        {"id": "S2", "duration_seconds": 18, "voiceover": ""}]})
    self.assertEqual(result["estimated_seconds"], 30)
```

- [ ] **Step 2: Run RED** with the focused duration test.

- [ ] **Step 3: Implement** `estimate(payload: dict) -> dict`. Spoken routes use configurable rates plus pauses; narrative uses dialogue/action/response seconds; visual essay sums scenes; commercial emits `over_target`/`under_target`; malformed segments return field-specific errors.

- [ ] **Step 4: Add JSON CLI, run GREEN, and commit**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_estimate_duration.py' -v
git add skills/video-script-studio/scripts/estimate_duration.py skills/video-script-studio/tests/test_estimate_duration.py
git commit -m "feat: estimate video duration by format"
```

## Task 6: Validate claims and source provenance

**Files:**
- Create: `skills/video-script-studio/scripts/validate_sources.py`
- Create: `skills/video-script-studio/tests/test_validate_sources.py`

- [ ] **Step 1: Write failing tests** for unique claim IDs, required source fields, URL/file provenance, dates, completeness, community-only factual claims, unresolved script markers, and explicit no-research records.

```python
def test_rejects_search_snippet_as_complete_source(self):
    manifest = valid_manifest()
    manifest["sources"][0]["body_status"] = "search-snippet"
    manifest["sources"][0]["capture_status"] = "complete"
    result = validate(manifest, script_text="事实 [C01]")
    self.assertIn("snippet_cannot_be_complete", result["error_codes"])
```

- [ ] **Step 2: Run RED** with the focused source test.

- [ ] **Step 3: Implement**

Define `SOURCE_LEVELS` as `primary`, `authoritative-secondary`, `expert`, and `community`; define `CONFIDENCE_LEVELS` as `high`, `medium`, and `low`. Expose `validate(manifest: dict, script_text: str = "") -> dict`.

Return `{valid, errors, warnings, error_codes, claim_count, source_count}`. Community-only support is invalid unless claim type is `audience-language` or `anecdote`. `research_required: false` requires `decision_reason` and no factual markers.

- [ ] **Step 4: Add CLI, run GREEN, and commit**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_validate_sources.py' -v
git add skills/video-script-studio/scripts/validate_sources.py skills/video-script-studio/tests/test_validate_sources.py
git commit -m "feat: validate video research provenance"
```

## Task 7: Validate complete production packs

**Files:**
- Create: `skills/video-script-studio/scripts/validate_pack.py`
- Create: `skills/video-script-studio/tests/test_validate_pack.py`
- Modify: `skills/video-script-studio/scripts/state_manager.py`

- [ ] **Step 1: Write failing tests** for missing files, empty required headings, unresolved placeholders, bad claim markers, unapproved stages, total score below `80`, any core dimension below `7`, failed base gates, and a fully valid pack.

```python
def test_complete_pack_requires_approved_script(self):
    project = make_complete_project(self.tmp)
    state = load_state(project)
    state["approvals"]["script"] = "pending"
    save_state(project, state)
    result = validate_pack(project)
    self.assertFalse(result["valid"])
    self.assertIn("script_not_approved", result["error_codes"])
```

- [ ] **Step 2: Run RED** with `python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_validate_pack.py' -v`.

- [ ] **Step 3: Implement** `validate_pack(project: Path) -> dict`. Require eleven project files plus `history/`; verify approvals; parse `review.md` frontmatter fields `total_score`, `core_dimensions`, and `base_gates`; call source validation; require route-specific headings; reject `TBD`, `TODO`, and `FIXME`.

- [ ] **Step 4: Add completion transition** `complete(project: Path) -> dict` in `state_manager.py`. It calls `validate_pack`; invalid packs cannot become `complete`.

- [ ] **Step 5: Run GREEN and commit**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_validate_pack.py' -v
python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_state_manager.py' -v
git add skills/video-script-studio/scripts/validate_pack.py skills/video-script-studio/scripts/state_manager.py skills/video-script-studio/tests/test_validate_pack.py
git commit -m "feat: validate complete video production packs"
```

## Task 8: Author templates and professional references

**Files:**
- Create: every file under `skills/video-script-studio/references/`
- Create: `skills/video-script-studio/assets/brief-template.md`
- Create: `skills/video-script-studio/assets/production-pack-template.md`
- Create: `skills/video-script-studio/tests/test_reference_contracts.py`

- [ ] **Step 1: Write failing reference contracts** requiring all eleven references, no placeholder tokens, and these route anchors:

```python
REQUIRED_ANCHORS = {
    "short-form.md": ["观看理由", "中段推进", "结尾兑现"],
    "long-form.md": ["核心问题", "子问题链", "章节回报"],
    "narrative.md": ["人物目标", "阻力", "潜台词"],
    "commercial.md": ["唯一核心承诺", "证据", "合规"],
    "visual-essay.md": ["可见行动", "视觉母题", "环境声", "旁白克制"],
}
```

- [ ] **Step 2: Run RED** with the focused reference test.

- [ ] **Step 3: Write shared references**. Each of `discovery.md`, `tool-routing.md`, `research.md`, `storyboard.md`, `publishing.md`, and `quality-rubric.md` must state purpose, required inputs, ordered procedure, output contract, rejection conditions, and next-stage handoff. The quality rubric includes base gates, five scorecards, independent-context review, and the two-revision ceiling.

- [ ] **Step 4: Write five route references**. Each route file includes route signals, anti-signals, brief fields, structural workflow, script format, duration method, weights, failure modes, and a miniature accepted-output example. `visual-essay.md` encodes action over image, image over explanation, and voiceover only for invisible thought/memory/change.

- [ ] **Step 5: Write templates** with the exact headings and machine-readable fields expected by project, source, and pack validators.

- [ ] **Step 6: Run GREEN and commit**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_reference_contracts.py' -v
git add skills/video-script-studio/references skills/video-script-studio/assets skills/video-script-studio/tests/test_reference_contracts.py
git commit -m "docs: add video script creative workflows"
```

## Task 9: Implement the compact Skill router and metadata

**Files:**
- Modify: `skills/video-script-studio/SKILL.md`
- Modify: `skills/video-script-studio/agents/openai.yaml`
- Modify: `skills/video-script-studio/tests/test_scaffold_contract.py`

- [ ] **Step 1: Extend the failing contract** to require trigger language, all five routes, one-question discovery, explicit approvals, resume behavior, project/profile commands, progressive reference loading, external-tool declarations, no silent degradation, and no implicit profile updates. Enforce at most 350 lines in `SKILL.md`.

- [ ] **Step 2: Run RED** with the scaffold contract.

- [ ] **Step 3: Implement this exact router sequence**

```text
detect new/resume → initialize/load project → load profile → diagnose route
→ confirm brief → decide/research → confirm research → propose 3 concepts
→ confirm concept → build experience-node outline → confirm outline
→ write clean+execution script → confirm script → storyboard/assets/publish
→ independent review → max two revisions → deterministic validation → complete
```

The router names the reference files required at each stage and forbids loading unrelated route modules.

- [ ] **Step 4: Finalize `openai.yaml`**

```yaml
interface:
  display_name: "Video Script Studio"
  short_description: "分阶段创作可拍摄的视频脚本与完整制作包"
  default_prompt: "使用 $video-script-studio 从需求诊断开始创建一个可恢复的视频脚本项目。"
```

- [ ] **Step 5: Run GREEN, validate, and commit**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_scaffold_contract.py' -v
uv run --with pyyaml python /Users/apulu/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/video-script-studio
git add skills/video-script-studio/SKILL.md skills/video-script-studio/agents/openai.yaml skills/video-script-studio/tests/test_scaffold_contract.py
git commit -m "feat: orchestrate staged video script creation"
```

Expected: tests PASS and validator prints `Skill is valid!`.

## Task 10: Add five-route and failure-mode scenarios

**Files:**
- Create: `skills/video-script-studio/tests/test_scenarios.py`
- Create: `skills/video-script-studio/tests/fixtures/short-form.json`
- Create: `skills/video-script-studio/tests/fixtures/long-form.json`
- Create: `skills/video-script-studio/tests/fixtures/narrative.json`
- Create: `skills/video-script-studio/tests/fixtures/commercial.json`
- Create: `skills/video-script-studio/tests/fixtures/visual-essay.json`

- [ ] **Step 1: Write five route fixtures** containing input intent, expected primary/secondary route, research disposition, artifact headings, duration payload, review weights, and forbidden failure pattern. The visual-essay fixture uses an original premise—creating one artwork from two personal interests—with visible trial, failure, visual motif, environment sound, sparse voiceover, and thematic recovery.

- [ ] **Step 2: Write failing scenario tests** that initialize each route and verify research behavior, duration method, required sections, review thresholds, and completion. Add failure scenarios for skipped approval, unavailable research, conflicting sources, missing transcript, changed concept, two-profile isolation, and interrupted resume.

- [ ] **Step 3: Run RED**

Run: `python3 -m unittest discover -s skills/video-script-studio/tests -p 'test_scenarios.py' -v`

Expected: FAIL wherever integration contracts are incomplete.

- [ ] **Step 4: Make minimal integration corrections**. Only fix mismatched fields, headings, transitions, or validation boundaries exposed by a failing scenario; add no product scope.

- [ ] **Step 5: Run the complete suite and commit**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -v
git add skills/video-script-studio
git commit -m "test: cover video script studio scenarios"
```

Expected: all tests PASS.

## Task 11: Install and perform real Codex E2E validation

**Files:**
- Create: `scripts/verify-video-script-studio-e2e.sh`
- Create: `skills/video-script-studio/tests/e2e/visual-essay-prompt.md`
- Create: `skills/video-script-studio/tests/e2e/expected-result.schema.json`

- [ ] **Step 1: Write an E2E harness that first proves isolation**. It creates a temporary `CODEX_HOME` and git workspace. Before copying the Skill, it asserts the Skill is absent so a global installation cannot make the test pass accidentally. It copies only the existing Codex authentication file from the original home into the temporary home with mode `0600`, never prints it, and registers a `trap` that deletes the temporary home on exit.

- [ ] **Step 2: Install from repository source** by copying `skills/video-script-studio/` into `$TMP_CODEX_HOME/skills/video-script-studio/`; never mutate the user's current `~/.codex/skills`. Run the official validator and deterministic suite on the copied package.

- [ ] **Step 3: Run a real Codex session**

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
CODEX_HOME="$TMP_CODEX_HOME" codex exec \
  --ephemeral --dangerously-bypass-approvals-and-sandbox \
  --skip-git-repo-check \
  --output-schema "$REPO_ROOT/skills/video-script-studio/tests/e2e/expected-result.schema.json" \
  -C "$TMP_WORKSPACE" -o "$TMP_WORKSPACE/result.json" \
  - < "$REPO_ROOT/skills/video-script-studio/tests/e2e/visual-essay-prompt.md"
```

The prompt explicitly invokes `$video-script-studio`, provides a creator profile and all approvals in advance for automation, and asks for an original Gawx-type visual essay without copying Gawx wording or a specific work.

- [ ] **Step 4: Assert real output**: one project exists; route is `visual-essay`; required artifacts are non-empty; script separates performance/execution; storyboard includes visible actions and environment sound with sparse voiceover; research disposition is recorded; review contains base gates and weighted scores; deterministic pack validation returns `valid: true`; project status is `complete`; final JSON reports the real path.

- [ ] **Step 5: Run twice**

```bash
bash scripts/verify-video-script-studio-e2e.sh
bash scripts/verify-video-script-studio-e2e.sh
```

Expected: both runs PASS in isolated paths with no prior-state dependency.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify-video-script-studio-e2e.sh skills/video-script-studio/tests/e2e
git commit -m "test: verify video script studio end to end"
```

## Task 12: Verify, review, open PR, pass CI, and merge

**Files:**
- Modify only files required by verified review findings.

- [ ] **Step 1: Run clean local verification**

```bash
python3 -m unittest discover -s skills/video-script-studio/tests -v
uv run --with pyyaml python /Users/apulu/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/video-script-studio
git diff --check origin/main...HEAD
bash scripts/verify-video-script-studio-e2e.sh
```

Expected: all PASS; validator prints `Skill is valid!`; diff check is empty; E2E prints its success marker.

- [ ] **Step 2: Run independent spec review** with a fresh agent given design, plan, and diff. Require requirement-by-requirement file/line evidence. Fix every critical/high finding by first adding a failing regression test, then implementation, then full verification.

- [ ] **Step 3: Run independent quality review** with another fresh agent. Review path traversal, atomicity, state consistency, error sanitization, duplication, reference clarity, and test adequacy. Address verified findings through TDD and record evidence for rejected findings.

- [ ] **Step 4: Verify hygiene**

```bash
git status --short
git diff --check origin/main...HEAD
git log --oneline origin/main..HEAD
```

Expected: only intentional branch changes; unrelated user-owned files remain untouched.

- [ ] **Step 5: Push and create PR**

```bash
git push -u origin feat/video-script-studio
gh pr create --base main --head feat/video-script-studio \
  --title "feat: add staged video script studio skill" \
  --body-file /tmp/video-script-studio-pr.md
```

PR body includes architecture, five routes, TDD evidence, real E2E evidence, limitations, and exact verification commands.

- [ ] **Step 6: Wait for checks**

Run: `gh pr checks --watch --fail-fast`

Expected: every required check PASS. On failure, inspect logs, reproduce locally, write a failing regression test, fix correctly, push, and wait again. Never bypass checks.

- [ ] **Step 7: Merge only while green and mergeable**

```bash
gh pr view --json mergeStateStatus,reviewDecision,statusCheckRollup,url
gh pr merge --merge --delete-branch
```

- [ ] **Step 8: Verify remote main**

```bash
git fetch origin main
git log -1 --oneline origin/main
gh pr view --json state,mergedAt,mergeCommit,url
```

Expected: state `MERGED`, non-null `mergedAt`, and remote `main` contains the merge commit. Only then notify the user for manual acceptance.

## Plan self-review checklist

- [ ] Every design section maps to Tasks 1–11.
- [ ] All five routes have references, scenarios, and rubric anchors.
- [ ] State, profiles, duration, sources, pack, degradation, install, and E2E have tests.
- [ ] Every implementation starts with RED and ends with GREEN.
- [ ] Shared-file ownership and parallel dependencies are explicit.
- [ ] No media generation, publishing, analytics, or multi-agent runtime scope was added.
- [ ] PR, green checks, merge, and remote-main verification are terminal gates.
