"""Offline structural checks for the G09 golden cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate_fixture(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("Riff fixture requires schema_version 1 and cases")
    reports = []
    for case in payload["cases"]:
        riffs = case.get("riffs", [])
        reports.append({"name": case.get("name"), "published_count": len(riffs), "bounded": 0 <= len(riffs) <= 3, "typed": all(riff.get("observation") and riff.get("hypothesis") and riff.get("recommendation") for riff in riffs)})
    return {"schema_version": 1, "cases": len(reports), "reports": reports, "all_passed": all(item["bounded"] and item["typed"] for item in reports)}
