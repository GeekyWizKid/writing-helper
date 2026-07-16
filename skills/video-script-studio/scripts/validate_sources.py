"""Validate research claims and source provenance.

The manifest is JSON-shaped data.  Validation never raises for content errors;
the command-line wrapper reserves exit status 2 for unreadable or malformed
input and emits validation failures with exit status 0.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SOURCE_LEVELS = ("primary", "authoritative-secondary", "expert", "community")
CONFIDENCE_LEVELS = ("high", "medium", "low")
CLAIM_TYPES = ("factual", "analysis", "opinion", "audience-language", "anecdote")
CAPTURE_STATUSES = ("complete", "partial", "unavailable")
BODY_STATUSES = ("full-text", "search-snippet", "metadata-only", "unavailable")
MAX_INPUT_BYTES = 10 * 1024 * 1024

_CLAIM_ID = re.compile(r"^C[0-9]{2}$")
_SOURCE_ID = re.compile(r"^S[0-9]{2}$")
_SCRIPT_MARKER = re.compile(r"\[(C\d+)\]")
_COMMUNITY_ONLY_ALLOWED_TYPES = ("audience-language", "anecdote")
_REQUIRED_MANIFEST_FIELDS = (
    "schema_version",
    "research_required",
    "decision_reason",
    "sources",
    "claims",
)
_REQUIRED_SOURCE_FIELDS = (
    "id",
    "title",
    "provenance",
    "level",
    "capture_status",
    "body_status",
    "accessed_at",
)
_REQUIRED_CLAIM_FIELDS = (
    "claim_id",
    "text",
    "claim_type",
    "source_ids",
    "confidence",
)

_ERROR_MESSAGES = {
    "invalid_manifest_schema": "The manifest does not match the required object schema.",
    "invalid_schema_version": "The schema version must be the integer 1.",
    "missing_decision_reason": "A no-research decision requires a non-empty reason.",
    "missing_source_field": "A source is missing a required field.",
    "invalid_source_id": "A source ID must use the S01 form.",
    "duplicate_source_id": "Source IDs must be unique.",
    "invalid_source_provenance": "A source requires exactly one safe HTTP(S) URL or file path.",
    "invalid_source_level": "A source has an unsupported evidence level.",
    "invalid_capture_status": "A source has an unsupported capture status.",
    "invalid_body_status": "A source has an unsupported body status.",
    "invalid_accessed_at": "A source access date must be a real ISO calendar date.",
    "snippet_cannot_be_complete": "A search snippet cannot be marked as a complete capture.",
    "missing_claim_field": "A claim is missing a required field.",
    "invalid_claim_id": "A claim ID must use the C01 form.",
    "duplicate_claim_id": "Claim IDs must be unique.",
    "invalid_claim": "A claim contains an invalid field value.",
    "invalid_claim_type": "A claim has an unsupported claim type.",
    "invalid_confidence": "A claim has an unsupported confidence value.",
    "duplicate_source_reference": "A claim cannot reference the same source more than once.",
    "unknown_source_reference": "A claim references a source that is not in the manifest.",
    "incomplete_claim_support": "A factual claim requires at least one complete full-text source.",
    "community_only_unsupported_claim": "This claim type cannot rely only on community sources.",
    "unresolved_script_marker": "The script contains a claim marker absent from the manifest.",
    "claim_missing_from_script": "A manifest claim is not referenced by the script.",
    "duplicate_script_marker": "A script claim marker may appear only once.",
    "factual_marker_without_research": "A no-research script cannot contain factual claim markers.",
}


class _Problems:
    """Collect error codes once, in deterministic validation order."""

    def __init__(self) -> None:
        self.codes: list[str] = []

    def add(self, code: str) -> None:
        if code not in self.codes:
            self.codes.append(code)

    @property
    def messages(self) -> list[str]:
        return [_ERROR_MESSAGES[code] for code in self.codes]


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_control_character(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _valid_hostname(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", hostname):
        return False
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError:
        return False
    if not ascii_hostname or len(ascii_hostname) > 253:
        return False
    labels = ascii_hostname.split(".")
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )


def _valid_provenance(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) not in ({"url"}, {"file"}):
        return False
    if "file" in value:
        file_value = value["file"]
        if not _nonempty_text(file_value) or _has_control_character(file_value):
            return False
        try:
            Path(file_value)
        except (OSError, TypeError, ValueError):
            return False
        # Provenance can describe a file that will be captured later; existence is not required.
        return True
    url = value.get("url")
    if (
        not _nonempty_text(url)
        or any(character.isspace() for character in url)
        or "\\" in url
    ):
        return False
    if _has_control_character(url):
        return False
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and "@" not in parsed.netloc
        and hostname is not None
        and _valid_hostname(hostname)
        and (port is None or 0 <= port <= 65535)
    )


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _validate_source(source: Any, problems: _Problems) -> tuple[str | None, dict | None]:
    if not isinstance(source, dict):
        problems.add("invalid_manifest_schema")
        return None, None
    if any(field not in source for field in _REQUIRED_SOURCE_FIELDS):
        problems.add("missing_source_field")

    source_id = source.get("id")
    valid_id = isinstance(source_id, str) and bool(_SOURCE_ID.fullmatch(source_id))
    if not valid_id:
        problems.add("invalid_source_id")
    if not _nonempty_text(source.get("title")):
        problems.add("missing_source_field")
    if not _valid_provenance(source.get("provenance")):
        problems.add("invalid_source_provenance")
    if source.get("level") not in SOURCE_LEVELS:
        problems.add("invalid_source_level")
    if source.get("capture_status") not in CAPTURE_STATUSES:
        problems.add("invalid_capture_status")
    if source.get("body_status") not in BODY_STATUSES:
        problems.add("invalid_body_status")
    if not _valid_date(source.get("accessed_at")):
        problems.add("invalid_accessed_at")
    if (
        source.get("capture_status") == "complete"
        and source.get("body_status") == "search-snippet"
    ):
        problems.add("snippet_cannot_be_complete")
    return source_id if valid_id else None, source


def _validate_claim(claim: Any, problems: _Problems) -> tuple[str | None, dict | None]:
    if not isinstance(claim, dict):
        problems.add("invalid_manifest_schema")
        return None, None
    if any(field not in claim for field in _REQUIRED_CLAIM_FIELDS):
        problems.add("missing_claim_field")

    claim_id = claim.get("claim_id")
    valid_id = isinstance(claim_id, str) and bool(_CLAIM_ID.fullmatch(claim_id))
    if not valid_id:
        problems.add("invalid_claim_id")
    if not _nonempty_text(claim.get("text")) or not _nonempty_text(claim.get("claim_type")):
        problems.add("invalid_claim")
    if claim.get("claim_type") not in CLAIM_TYPES:
        problems.add("invalid_claim_type")
    if claim.get("confidence") not in CONFIDENCE_LEVELS:
        problems.add("invalid_confidence")
    source_ids = claim.get("source_ids")
    if not isinstance(source_ids, list) or any(
        not isinstance(source_id, str) for source_id in source_ids
    ):
        problems.add("invalid_claim")
    return claim_id if valid_id else None, claim


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def validate(manifest: dict, script_text: str = "") -> dict:
    """Validate a manifest and matching script without raising content errors."""
    problems = _Problems()
    if not isinstance(manifest, dict):
        problems.add("invalid_manifest_schema")
        manifest = {}
    if not isinstance(script_text, str):
        problems.add("invalid_manifest_schema")
        script_text = ""

    if any(field not in manifest for field in _REQUIRED_MANIFEST_FIELDS):
        problems.add("invalid_manifest_schema")

    schema_version = manifest.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        problems.add("invalid_schema_version")

    research_required = manifest.get("research_required")
    if not isinstance(research_required, bool):
        problems.add("invalid_manifest_schema")
    decision_reason = manifest.get("decision_reason")
    if not isinstance(decision_reason, str):
        problems.add("invalid_manifest_schema")
    if research_required is False and not _nonempty_text(decision_reason):
        problems.add("missing_decision_reason")

    raw_sources = manifest.get("sources")
    raw_claims = manifest.get("claims")
    if not isinstance(raw_sources, list) or not isinstance(raw_claims, list):
        problems.add("invalid_manifest_schema")
    sources = _safe_list(raw_sources)
    claims = _safe_list(raw_claims)

    source_by_id: dict[str, dict] = {}
    for source in sources:
        source_id, source_record = _validate_source(source, problems)
        if source_id is not None and source_record is not None:
            if source_id in source_by_id:
                problems.add("duplicate_source_id")
            else:
                source_by_id[source_id] = source_record

    claim_ids: list[str] = []
    valid_claims: list[dict] = []
    for claim in claims:
        claim_id, claim_record = _validate_claim(claim, problems)
        if claim_id is not None:
            if claim_id in claim_ids:
                problems.add("duplicate_claim_id")
            else:
                claim_ids.append(claim_id)
        if claim_record is not None:
            valid_claims.append(claim_record)

    for claim in valid_claims:
        source_ids = claim.get("source_ids")
        if not isinstance(source_ids, list) or any(
            not isinstance(source_id, str) for source_id in source_ids
        ):
            continue
        if len(source_ids) != len(set(source_ids)):
            problems.add("duplicate_source_reference")
        if any(source_id not in source_by_id for source_id in source_ids):
            problems.add("unknown_source_reference")

        referenced = [source_by_id[source_id] for source_id in source_ids if source_id in source_by_id]
        claim_type = claim.get("claim_type")
        if claim_type == "factual":
            complete = any(
                source.get("capture_status") == "complete"
                and source.get("body_status") == "full-text"
                for source in referenced
            )
            if not complete:
                problems.add("incomplete_claim_support")
        if (
            claim_type not in _COMMUNITY_ONLY_ALLOWED_TYPES
            and referenced
            and all(source.get("level") == "community" for source in referenced)
        ):
            problems.add("community_only_unsupported_claim")

    markers = _SCRIPT_MARKER.findall(script_text)
    exact_markers = [marker for marker in markers if _CLAIM_ID.fullmatch(marker)]
    if len(exact_markers) != len(set(exact_markers)):
        problems.add("duplicate_script_marker")
    if any(marker not in claim_ids for marker in markers):
        problems.add("unresolved_script_marker")
    if any(claim_id not in exact_markers for claim_id in claim_ids):
        problems.add("claim_missing_from_script")
    if research_required is False and markers:
        problems.add("factual_marker_without_research")

    return {
        "valid": not problems.codes,
        "errors": problems.messages,
        "warnings": [],
        "error_codes": problems.codes,
        "claim_count": len(claims),
        "source_count": len(sources),
    }


def _invalid_input() -> int:
    print(json.dumps({"valid": False, "error": "invalid_input"}, sort_keys=True))
    return 2


def _read_input_text(path: Path) -> str:
    """Read at most ``MAX_INPUT_BYTES`` of UTF-8 text from an input file."""
    with path.open("rb") as stream:
        content = stream.read(MAX_INPUT_BYTES + 1)
    if len(content) > MAX_INPUT_BYTES:
        raise ValueError("input is too large")
    return content.decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--script", type=Path)
    args = parser.parse_args(argv)

    def reject_non_finite(_constant: str) -> None:
        raise ValueError("non-finite number")

    try:
        manifest = json.loads(
            _read_input_text(args.manifest), parse_constant=reject_non_finite
        )
        if not isinstance(manifest, dict):
            return _invalid_input()
        script_text = _read_input_text(args.script) if args.script else ""
    except (OSError, UnicodeError, ValueError):
        return _invalid_input()

    print(json.dumps(validate(manifest, script_text), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
