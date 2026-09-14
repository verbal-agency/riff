"""Small, field-separated evaluation report for labeled receipt fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .receipts import ReceiptValidationError


FIELDS = (
    "capability_candidates",
    "technology_candidates",
    "organization_company",
    "claims",
    "source_metadata",
    "relevant_spans",
)


def evaluate_labeled_fixture(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptValidationError("evaluation fixture could not be read") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1 or not isinstance(payload.get("examples"), list):
        raise ReceiptValidationError("evaluation fixture requires schema_version 1 and examples")
    scores = {field: {"correct": 0, "total": 0, "accuracy": 0.0} for field in FIELDS}
    for example in payload["examples"]:
        if not isinstance(example, Mapping):
            raise ReceiptValidationError("evaluation example must be an object")
        expected = example.get("expected", {})
        predicted = example.get("predicted", {})
        if not isinstance(expected, Mapping) or not isinstance(predicted, Mapping):
            raise ReceiptValidationError("evaluation expected/predicted values must be objects")
        for field in FIELDS:
            scores[field]["total"] += 1
            if _normalize(expected.get(field)) == _normalize(predicted.get(field)):
                scores[field]["correct"] += 1
    for score in scores.values():
        score["accuracy"] = score["correct"] / score["total"] if score["total"] else 0.0
    return {"schema_version": 1, "examples": len(payload["examples"]), "fields": scores}


def _normalize(value: Any) -> Any:
    if isinstance(value, list):
        return sorted((_normalize(item) for item in value), key=repr)
    if isinstance(value, Mapping):
        return {key: _normalize(item) for key, item in sorted(value.items())}
    return value
