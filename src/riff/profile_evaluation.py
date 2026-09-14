"""Offline evaluation report for profile gap-classification fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .profile import ProfileValidationError


def evaluate_fixture(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileValidationError("profile evaluation fixture could not be read") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ProfileValidationError("fixture requires schema_version 1 and cases")
    failures = []
    for case in payload["cases"]:
        if not isinstance(case, Mapping) or case.get("expected") is None or case.get("predicted") is None:
            raise ProfileValidationError("each case requires expected and predicted")
        if case["expected"] != case["predicted"]:
            failures.append({"id": case.get("id"), "expected": case["expected"], "predicted": case["predicted"]})
    total = len(payload["cases"])
    return {"schema_version": 1, "cases": total, "correct": total - len(failures), "accuracy": (total - len(failures)) / total if total else 0.0, "failures": failures}
