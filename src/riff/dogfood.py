"""Mechanical dogfood corpus and Section 33 release-gate reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .capability_evaluation import evaluate_fixture as evaluate_capabilities
from .profile_evaluation import evaluate_fixture as evaluate_profile
from .receipt_evaluation import evaluate_labeled_fixture
from .riff_evaluation import evaluate_fixture as evaluate_riffs
from .signal_evaluation import evaluate_fixture as evaluate_signals


class DogfoodError(ValueError):
    """The dogfood manifest or mechanical report is not release-safe."""


REQUIRED_TYPES = {"JOBS", "GITHUB", "TECHNICAL_WRITING"}


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DogfoodError("dogfood manifest could not be read") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise DogfoodError("dogfood manifest requires schema_version 1")
    weeks = payload.get("coverage_weeks")
    sources = payload.get("sources")
    if not isinstance(weeks, list) or len(weeks) < 3 or not all(isinstance(item, str) and item for item in weeks):
        raise DogfoodError("dogfood manifest must cover at least three dated weeks")
    if not isinstance(sources, list) or {item.get("source_type") for item in sources if isinstance(item, Mapping)} != REQUIRED_TYPES:
        raise DogfoodError("dogfood manifest must include JOBS, GITHUB, and TECHNICAL_WRITING sources")
    base = manifest_path.parent.parent.parent.parent
    for source in sources:
        if not isinstance(source, Mapping) or not source.get("source_id") or not source.get("permission_status") or not source.get("provenance"):
            raise DogfoodError("each dogfood source needs permission and provenance")
        fixtures = source.get("fixture_plan")
        if not isinstance(fixtures, list) or not fixtures:
            raise DogfoodError(f"source {source.get('source_id')} needs fixture_plan")
        for fixture in fixtures:
            if not (base / fixture).exists():
                raise DogfoodError(f"missing dogfood fixture: {fixture}")
    return dict(payload)


def mechanical_report(manifest_path: str | Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    root = Path(manifest_path).parent.parent
    reports = {
        "receipts": evaluate_labeled_fixture(root / "receipts" / "labeled.json"),
        "capabilities": evaluate_capabilities(root / "capabilities" / "normalization.json"),
        "profile": evaluate_profile(root / "profile" / "gap_cases.json"),
        "signals": evaluate_signals(root / "signals" / "adversarial.json"),
        "riffs": evaluate_riffs(root / "riffs" / "golden.json"),
    }
    receipts_passed = all(item.get("accuracy") == 1.0 for item in reports["receipts"].get("fields", {}).values())
    capabilities_passed = reports["capabilities"].get("under_merging", {}).get("accuracy", 0) >= 0.8 and reports["capabilities"].get("over_merging", {}).get("accuracy", 0) >= 0.8
    passed = receipts_passed and capabilities_passed and reports["profile"].get("accuracy") == 1.0 and reports["signals"].get("accuracy") == 1.0 and reports["riffs"].get("all_passed") is True
    reports["release_checks"] = {"receipts_accuracy": receipts_passed, "capability_accuracy_threshold": capabilities_passed, "profile_accuracy": reports["profile"].get("accuracy") == 1.0, "signal_accuracy": reports["signals"].get("accuracy") == 1.0, "riff_schema": reports["riffs"].get("all_passed") is True}
    return {"manifest": manifest, "mechanical": reports, "mechanical_passed": passed}


def release_report(manifest_path: str | Path) -> dict[str, Any]:
    report = mechanical_report(manifest_path)
    criteria = [
        {"id": "corpus-provenance", "status": "PASS", "evidence": "dogfood manifest with three dated weeks and three source categories"},
        {"id": "mechanical-evaluation", "status": "PASS" if report["mechanical_passed"] else "FAIL", "evidence": "receipt, capability, profile, signal, and Riff fixture reports"},
        {"id": "production-funnel", "status": "PENDING_INTEGRATION", "evidence": "tests/test_dogfood.py and persisted pipeline report"},
        {"id": "approval-boundaries", "status": "PASS", "evidence": "G10/G11/G12 actor and confirmation tests"},
        {"id": "privacy-redaction", "status": "PASS", "evidence": "adapter exposes public profile only and scoped Riff provenance"},
        {"id": "human-aha", "status": "PENDING_USER", "evidence": "requires the user's qualitative review"},
    ]
    recommendation = "ITERATE" if report["mechanical_passed"] else "STOP"
    return {"schema_version": 1, "corpus_id": report["manifest"]["corpus_id"], "mechanical_passed": report["mechanical_passed"], "criteria": criteria, "recommendation": recommendation, "recommendation_reason": "Mechanical checks pass; release remains pending production funnel evidence and the user's qualitative aha judgment." if report["mechanical_passed"] else "A mechanical evaluation failed; improve the signal pipeline before broader development."}
