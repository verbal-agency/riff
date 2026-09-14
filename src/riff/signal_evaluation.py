"""Offline evaluation report for adversarial signal-ranking fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

def evaluate_fixture(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("signal fixture requires schema_version 1 and cases")
    failures = []
    for case in payload["cases"]:
        expected, predicted = case.get("expected_order"), case.get("predicted_order")
        if expected != predicted:
            failures.append({"id": case.get("id"), "expected_order": expected, "predicted_order": predicted})
    total = len(payload["cases"])
    return {"schema_version": 1, "cases": total, "correct": total - len(failures), "accuracy": (total - len(failures)) / total if total else 0.0, "failures": failures}
