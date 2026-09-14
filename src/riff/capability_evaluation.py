"""Field-separated evaluation for capability normalization fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .capabilities import NormalizationError


def evaluate_fixture(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NormalizationError("capability evaluation fixture could not be read") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise NormalizationError("fixture requires schema_version 1 and cases")
    under, over = [], []
    for case in payload["cases"]:
        if not isinstance(case, Mapping) or not isinstance(case.get("expected_groups"), list) or not isinstance(case.get("predicted_groups"), list):
            raise NormalizationError("each case requires expected_groups and predicted_groups")
        expected = {_key(group) for group in case["expected_groups"]}
        predicted = {_key(group) for group in case["predicted_groups"]}
        missing = sorted(expected - predicted)
        extra = sorted(predicted - expected)
        if missing:
            under.append({"id": case.get("id"), "missing": missing})
        if extra:
            over.append({"id": case.get("id"), "extra": extra})
    return {
        "schema_version": 1,
        "cases": len(payload["cases"]),
        "under_merging": {"correct": len(payload["cases"]) - len(under), "total": len(payload["cases"]), "accuracy": (len(payload["cases"]) - len(under)) / len(payload["cases"]) if payload["cases"] else 0.0, "failures": under},
        "over_merging": {"correct": len(payload["cases"]) - len(over), "total": len(payload["cases"]), "accuracy": (len(payload["cases"]) - len(over)) / len(payload["cases"]) if payload["cases"] else 0.0, "failures": over},
    }


def _key(group: Any) -> str:
    if isinstance(group, list):
        return "|".join(sorted(str(item).strip().lower() for item in group))
    return str(group).strip().lower()
