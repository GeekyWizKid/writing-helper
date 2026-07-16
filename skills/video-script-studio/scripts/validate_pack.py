"""Validate a complete Video Script Studio production pack."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

from common import StudioError, parse_state_yaml
from state_manager import (
    MAX_REASON_CHARS,
    STAGES,
    STAGE_FILES,
    _QUARANTINE_PATTERN,
    _SNAPSHOT_PATTERN,
    _locked_project,
    _open_history,
    _read_regular_at,
    _validate_state,
    _verify_empty_tombstone_at,
)
from validate_sources import validate as validate_sources


ARTIFACT_FILES = (
    "brief.md",
    "research.md",
    "concepts.md",
    "outline.md",
    "script.md",
    "storyboard.md",
    "assets.md",
    "publish.md",
    "sources.md",
    "review.md",
)
REQUIRED_FILES = ("project.yaml", *ARTIFACT_FILES)
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PACK_BYTES = 32 * 1024 * 1024

BASE_GATES = (
    "factual_integrity",
    "logical_consistency",
    "brief_alignment",
    "profile_constraints",
    "duration_feasible",
    "production_feasible",
    "risk_disclosure",
)
ROUTE_DIMENSIONS = {
    "short-form": ("viewing_reason", "pace_progression", "information_density", "natural_delivery", "ending_payoff"),
    "long-form": ("research_depth", "question_chain", "chapter_value", "evidence_opinion_separation", "long_range_retention"),
    "narrative": ("character_desire", "conflict_escalation", "scene_function", "subtext", "emotional_payoff"),
    "commercial": ("audience_insight", "single_promise", "proof_strength", "product_integration", "action_drive", "compliance"),
    "visual-essay": ("visible_action", "visual_storytelling", "inner_outer_change", "sound_design", "voiceover_restraint", "aesthetic_consistency"),
}
ROUTE_ANCHORS = {
    "short-form": {"brief.md": ("观看理由",), "outline.md": ("中段推进", "结尾兑现")},
    "long-form": {"brief.md": ("核心问题",), "outline.md": ("子问题链", "章节回报")},
    "narrative": {"brief.md": ("人物目标",), "outline.md": ("阻力",), "script.md": ("潜台词",)},
    "commercial": {"brief.md": ("唯一核心承诺",), "research.md": ("证据",), "review.md": ("合规",)},
    "visual-essay": {"storyboard.md": ("可见行动", "视觉母题", "环境声"), "script.md": ("旁白克制",)},
}
SCRIPT_HEADINGS = (
    "最终命题",
    "目标",
    "预计时长",
    "干净表演稿",
    "制作执行稿",
    "待人工确认事项",
    "可删段落",
    "短版本切点",
)

_ALLOWED_TOP_LEVEL = frozenset((*REQUIRED_FILES, "history", ".video-script-studio-state.lock"))
_PLACEHOLDER = re.compile(r"(?<![A-Za-z0-9_])(?:TBD|TODO|FIXME)(?![A-Za-z0-9_])", re.I)
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", re.M | re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
_REVIEW_KEYS = frozenset(
    ("schema_version", "passed", "total_score", "core_dimensions", "base_gates", "revision_count")
)
_REVIEW_REQUIRED_KEYS = _REVIEW_KEYS - {"revision_count"}

_MESSAGES = {
    "missing_file": "A required project file is missing.",
    "missing_history": "The required history directory is missing.",
    "unexpected_project_entry": "The project contains an unexpected top-level entry.",
    "invalid_state": "The project state document is invalid.",
    "non_substantive_artifact": "A required artifact has no substantive content.",
    "unresolved_placeholder": "A required artifact contains an unresolved placeholder.",
    "missing_required_heading": "The script is missing a required heading.",
    "empty_required_heading": "A required script heading has no substantive content.",
    "missing_route_anchor": "A route-specific heading is missing from its assigned artifact.",
    "empty_route_anchor": "A route-specific heading has no substantive content.",
    "invalid_sources_frontmatter": "The sources frontmatter must be a strict JSON object.",
    "invalid_review_frontmatter": "The review frontmatter must be a strict JSON object.",
    "invalid_review_schema": "The review frontmatter schema is invalid.",
    "invalid_review_dimensions": "The review dimensions do not exactly match the selected route.",
    "invalid_review_weights": "Review dimension weights must be non-negative and total 100.",
    "review_total_below_80": "The review total score is below 80.",
    "review_core_dimension_below_7": "A core review dimension is below 7.",
    "review_base_gate_failed": "A mandatory base gate failed.",
    "review_not_passed": "The independent review is not marked passed.",
    "review_total_mismatch": "The review total does not match its weighted dimensions.",
    "invalid_history_entry": "History contains an unrecognized entry.",
    "invalid_history_snapshot": "A public history snapshot is invalid.",
}


class _Problems:
    def __init__(self) -> None:
        self.codes: list[str] = []
        self.errors: list[str] = []

    def add(self, code: str, message: str | None = None) -> None:
        if code in self.codes:
            return
        self.codes.append(code)
        self.errors.append(message or _MESSAGES.get(code, code.replace("_", " ")))


def _strict_json(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def constant(name: str) -> None:
        raise ValueError(f"non-finite JSON constant: {name}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing frontmatter")
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValueError("unterminated frontmatter")
    value = _strict_json("".join(lines[1:end]))
    if not isinstance(value, dict):
        raise ValueError("frontmatter root is not an object")
    return value, "".join(lines[end + 1 :])


def _visible_markdown(text: str, *, remove_frontmatter: bool = False) -> str:
    if remove_frontmatter:
        try:
            _, text = _frontmatter(text)
        except ValueError:
            pass
    text = _COMMENT.sub("", text)
    return _FENCE.sub("", text)


def _meaningful(text: str) -> bool:
    text = _HEADING.sub("", text)
    text = re.sub(r"[\s#>*_`~\-|:：。，、；;!?！？()（）\[\]{}]", "", text)
    return len(text) >= 2 and not _PLACEHOLDER.search(text)


def _heading_sections(text: str) -> dict[str, list[str]]:
    visible = _visible_markdown(text, remove_frontmatter=True)
    matches = list(_HEADING.finditer(visible))
    sections: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).strip().rstrip("#").strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(visible)
        sections.setdefault(heading, []).append(visible[match.end() : end])
    return sections


def _snapshot_files_at(
    project_fd: int,
    problems: _Problems,
    *,
    state_already_read: bool = False,
    initial_byte_count: int = 0,
) -> tuple[dict[str, str], int]:
    try:
        names = set(os.listdir(project_fd))
    except OSError as exc:
        raise StudioError("Could not inspect the project safely.") from exc
    for name in sorted(names - _ALLOWED_TOP_LEVEL):
        try:
            metadata = os.stat(name, dir_fd=project_fd, follow_symlinks=False)
        except OSError as exc:
            raise StudioError("Could not inspect an unexpected project entry safely.") from exc
        if stat.S_ISLNK(metadata.st_mode) or not (
            stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)
        ):
            raise StudioError("The project contains an unsafe unexpected entry.")
        problems.add("unexpected_project_entry")
    if "history" not in names:
        problems.add("missing_history")

    files: dict[str, str] = {}
    total = initial_byte_count
    names_to_read = ARTIFACT_FILES if state_already_read else REQUIRED_FILES
    for name in names_to_read:
        if name not in names:
            problems.add("missing_file", f"Required file is missing: {name}.")
            continue
        raw = _read_regular_at(project_fd, name, MAX_FILE_BYTES, name)
        total += len(raw)
        if total > MAX_PACK_BYTES:
            raise StudioError("The production pack exceeds the aggregate size limit.")
        try:
            files[name] = raw.decode("utf-8")
        except UnicodeError as exc:
            raise StudioError(f"The {name} file is not valid UTF-8.") from exc
    return files, len(files) + (1 if state_already_read else 0)


def _validate_history_at(project_fd: int, problems: _Problems) -> None:
    try:
        history_fd = _open_history(project_fd)
    except StudioError:
        # Missing is already a normal pack-content failure; unsafe existing paths
        # remain trust-boundary errors.
        try:
            os.stat("history", dir_fd=project_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise
    try:
        for name in sorted(os.listdir(history_fd)):
            try:
                entry = os.stat(name, dir_fd=history_fd, follow_symlinks=False)
            except OSError as exc:
                raise StudioError("Could not inspect a history entry safely.") from exc
            if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
                raise StudioError("The project history contains an unsafe entry.")
            if _QUARANTINE_PATTERN.fullmatch(name):
                _verify_empty_tombstone_at(history_fd, name)
                continue
            if not _SNAPSHOT_PATTERN.fullmatch(name):
                problems.add("invalid_history_entry", f"Invalid history entry: {name}.")
                continue
            descriptor: int | None = None
            try:
                descriptor = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=history_fd,
                )
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISDIR(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) & 0o022
                ):
                    raise StudioError("A public history snapshot is unsafe.")
                entries = set(os.listdir(descriptor))
                if "manifest.json" not in entries:
                    problems.add("invalid_history_snapshot")
                    continue
                raw = _read_regular_at(descriptor, "manifest.json", 1024 * 1024, "history manifest")
                try:
                    manifest = _strict_json(raw.decode("utf-8"))
                except (UnicodeError, ValueError):
                    problems.add("invalid_history_snapshot")
                    continue
                if not isinstance(manifest, dict) or set(manifest) != {
                    "affected_artifacts", "reason", "stage"
                }:
                    problems.add("invalid_history_snapshot")
                    continue
                affected = manifest.get("affected_artifacts")
                stage = manifest.get("stage")
                reason = manifest.get("reason")
                if (
                    not isinstance(affected, list)
                    or any(item not in STAGE_FILES.values() for item in affected)
                    or len(affected) != len(set(affected))
                    or affected != sorted(affected)
                    or stage not in STAGES
                    or not name.endswith(f"-{stage}")
                    or not isinstance(reason, str)
                    or not reason.strip()
                    or len(reason) > MAX_REASON_CHARS
                    or entries != {"manifest.json", *affected}
                ):
                    problems.add("invalid_history_snapshot")
                    continue
                for artifact in affected:
                    _read_regular_at(descriptor, artifact, MAX_FILE_BYTES, "history artifact")
            except StudioError:
                raise
            except OSError as exc:
                raise StudioError("Could not inspect a history snapshot safely.") from exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)
    finally:
        os.close(history_fd)


def _validate_artifacts(files: dict[str, str], problems: _Problems) -> None:
    for filename in ARTIFACT_FILES:
        text = files.get(filename)
        if text is None:
            continue
        visible = _visible_markdown(
            text, remove_frontmatter=filename in {"sources.md", "review.md"}
        )
        if _PLACEHOLDER.search(visible):
            problems.add("unresolved_placeholder", f"Unresolved placeholder in {filename}.")
        if not _meaningful(visible):
            problems.add("non_substantive_artifact", f"Artifact is not substantive: {filename}.")


def _validate_headings(files: dict[str, str], route: str | None, problems: _Problems) -> None:
    script_sections = _heading_sections(files.get("script.md", ""))
    for heading in SCRIPT_HEADINGS:
        sections = script_sections.get(heading)
        if not sections:
            problems.add("missing_required_heading", f"script.md is missing heading: {heading}.")
        elif not any(_meaningful(section) for section in sections):
            problems.add("empty_required_heading", f"script.md heading is empty: {heading}.")
    if route not in ROUTE_ANCHORS:
        return
    for filename, headings in ROUTE_ANCHORS[route].items():
        sections = _heading_sections(files.get(filename, ""))
        for heading in headings:
            values = sections.get(heading)
            if not values:
                problems.add("missing_route_anchor", f"{filename} is missing route heading: {heading}.")
            elif not any(_meaningful(value) for value in values):
                problems.add("empty_route_anchor", f"{filename} route heading is empty: {heading}.")


def _validate_review(text: str | None, route: str | None, problems: _Problems) -> None:
    if text is None:
        return
    try:
        review, _ = _frontmatter(text)
    except ValueError:
        problems.add("invalid_review_frontmatter")
        return
    if not (_REVIEW_REQUIRED_KEYS <= set(review) <= _REVIEW_KEYS):
        problems.add("invalid_review_schema")
    if type(review.get("schema_version")) is not int or review.get("schema_version") != 1:
        problems.add("invalid_review_schema")
    if type(review.get("passed")) is not bool:
        problems.add("invalid_review_schema")
    elif not review["passed"]:
        problems.add("review_not_passed")
    revision = review.get("revision_count", 0)
    if type(revision) is not int or not 0 <= revision <= 2:
        problems.add("invalid_review_schema")

    total = review.get("total_score")
    if type(total) not in (int, float) or not 0 <= total <= 100:
        problems.add("invalid_review_schema")
    elif total < 80:
        problems.add("review_total_below_80")

    dimensions = review.get("core_dimensions")
    expected = ROUTE_DIMENSIONS.get(route or "")
    weighted_terms: list[float] = []
    if not isinstance(dimensions, dict):
        problems.add("invalid_review_dimensions")
    else:
        if expected is None or set(dimensions) != set(expected):
            problems.add("invalid_review_dimensions")
        weights: list[float] = []
        for value in dimensions.values():
            if not isinstance(value, dict) or set(value) != {"score", "weight"}:
                problems.add("invalid_review_schema")
                continue
            score = value.get("score")
            weight = value.get("weight")
            if type(score) not in (int, float) or not 0 <= score <= 10:
                problems.add("invalid_review_schema")
            elif score < 7:
                problems.add("review_core_dimension_below_7")
            if type(weight) not in (int, float) or weight <= 0:
                problems.add("invalid_review_weights")
            else:
                weights.append(weight)
            if type(score) in (int, float) and type(weight) in (int, float):
                weighted_terms.append(score * weight / 10)
        if len(weights) != len(dimensions) or abs(sum(weights) - 100) > 1e-9:
            problems.add("invalid_review_weights")
        elif (
            type(total) in (int, float)
            and len(weighted_terms) == len(dimensions)
            and abs(sum(weighted_terms) - total) > 0.01
        ):
            problems.add("review_total_mismatch")

    gates = review.get("base_gates")
    if not isinstance(gates, dict) or set(gates) != set(BASE_GATES) or any(
        type(value) is not bool for value in gates.values()
    ):
        problems.add("invalid_review_schema")
    elif not all(gates.values()):
        problems.add("review_base_gate_failed")


def _validate_sources(text: str | None, script: str, problems: _Problems) -> tuple[int, int, list[str]]:
    if text is None:
        return 0, 0, []
    try:
        manifest, _ = _frontmatter(text)
    except ValueError:
        problems.add("invalid_sources_frontmatter")
        return 0, 0, []
    result = validate_sources(manifest, script)
    for code, message in zip(result["error_codes"], result["errors"]):
        problems.add(code, message)
    return result["source_count"], result["claim_count"], list(result.get("warnings", []))


def _validate_pack_at(
    project_fd: int,
    *,
    state: dict[str, Any] | None = None,
    state_byte_count: int = 0,
) -> dict[str, Any]:
    """Validate while the caller holds the trusted project lock."""
    problems = _Problems()
    files, checked = _snapshot_files_at(
        project_fd,
        problems,
        state_already_read=state is not None,
        initial_byte_count=state_byte_count,
    )
    _validate_history_at(project_fd, problems)

    parsed_state = state
    if parsed_state is None and "project.yaml" in files:
        try:
            parsed_state = _validate_state(parse_state_yaml(files["project.yaml"]))
        except StudioError:
            problems.add("invalid_state")
    route: str | None = None
    if parsed_state is not None:
        try:
            parsed_state = _validate_state(parsed_state)
            route = parsed_state["project"]["primary_type"]
            if route not in ROUTE_DIMENSIONS:
                problems.add("invalid_state", "The project primary route is unsupported.")
                route = None
            for stage in STAGES:
                if parsed_state["approvals"][stage] != "approved":
                    problems.add(f"{stage}_not_approved", f"The {stage} approval is not approved.")
        except StudioError:
            problems.add("invalid_state")

    _validate_artifacts(files, problems)
    _validate_headings(files, route, problems)
    _validate_review(files.get("review.md"), route, problems)
    source_count, claim_count, warnings = _validate_sources(
        files.get("sources.md"), files.get("script.md", ""), problems
    )
    return {
        "valid": not problems.codes,
        "errors": problems.errors,
        "warnings": warnings,
        "error_codes": problems.codes,
        "checked_file_count": checked,
        "source_count": source_count,
        "claim_count": claim_count,
    }


def validate_pack(project: Path) -> dict[str, Any]:
    """Return a deterministic validation report for a trusted project."""
    with _locked_project(project) as (_, project_fd):
        return _validate_pack_at(project_fd)


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise StudioError("Invalid command-line arguments.")


def main(argv: list[str] | None = None) -> int:
    parser = _JsonArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    try:
        arguments = parser.parse_args(argv)
        payload = validate_pack(Path(arguments.project))
        code = 0
    except StudioError as exc:
        payload = {"error": str(exc), "status": "error"}
        code = 2
    except Exception:
        payload = {"error": "Could not validate the production pack.", "status": "error"}
        code = 2
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
