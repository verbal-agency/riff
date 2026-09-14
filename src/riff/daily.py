"""Local fixture-backed daily Riff smoke entry point."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .db import connection
from .evidence import content_hash
from .riffs import CandidateContext, DailyRiffService, DeterministicReasoningProvider, RiffRepository, daily_input_fingerprint


@dataclass(frozen=True, slots=True)
class DailyFixture:
    run_date: date
    policy_version: str
    candidates: tuple[CandidateContext, ...]
    receipts: tuple[dict[str, Any], ...]


def load_fixture(path: str | Path, *, run_date: date | None = None, policy_version: str | None = None) -> DailyFixture:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("daily fixture requires schema_version 1")
    try:
        fixture_date = date.fromisoformat(payload["run_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("daily fixture requires run_date YYYY-MM-DD") from exc
    entries = payload.get("candidates")
    if not isinstance(entries, list) or len(entries) > 20:
        raise ValueError("daily fixture candidates must be a list of at most 20 items")
    receipts = payload.get("receipts", [])
    if not isinstance(receipts, list):
        raise ValueError("daily fixture receipts must be a list")
    known = {item.get("receipt_id") for item in receipts if isinstance(item, dict)}
    candidates = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("each daily candidate must be an object")
        required = ("candidate_id", "capability_id", "score", "classification", "observation", "receipt_ids")
        if any(key not in item for key in required):
            raise ValueError("daily candidate is missing a required field")
        ids = item["receipt_ids"]
        if not isinstance(ids, list) or len(ids) > 20 or any(not isinstance(value, str) for value in ids):
            raise ValueError("candidate receipt_ids must be a list of at most 20 strings")
        if not set(ids).issubset(known):
            missing = sorted(set(ids) - known)
            raise ValueError(f"candidate references unknown fixture receipt(s): {', '.join(missing)}")
        profile = item.get("profile_slice", [])
        decisions = item.get("decision_ids", [])
        if not isinstance(profile, list) or len(profile) > 20 or not isinstance(decisions, list) or len(decisions) > 20:
            raise ValueError("profile_slice and decision_ids must be bounded lists")
        candidates.append(CandidateContext(str(item["candidate_id"]), str(item["capability_id"]), float(item["score"]), str(item["classification"]), str(item["observation"]), tuple(ids), tuple(profile), tuple(str(value) for value in decisions), str(item.get("profile_state", "UNKNOWN")), tuple(str(value) for value in item.get("associated_technologies", []))))
    return DailyFixture(run_date or fixture_date, policy_version or str(payload.get("policy_version", "riff-policy-v1")), tuple(candidates), tuple(receipts))


def seed_fixture(database_url: str, fixture: DailyFixture) -> None:
    """Insert only the fixture's raw evidence and successful receipts, idempotently."""
    source_id = "riff-daily-fixture-source"
    now = datetime.now(timezone.utc)
    with connection(database_url) as conn:
        conn.execute("INSERT INTO sources (source_id, source_type, name) VALUES (%s, 'TECHNICAL_WRITING', %s) ON CONFLICT DO NOTHING", (source_id, "Riff daily fixture"))
        for item in fixture.receipts:
            receipt_id = str(item["receipt_id"])
            raw = str(item.get("raw_content", item.get("summary", "fixture evidence")))
            evidence_id = f"riff-fixture-evidence-{receipt_id}"
            source_item_id = f"riff-fixture-item-{receipt_id}"
            digest = content_hash(raw)
            conn.execute("INSERT INTO source_items (source_item_id, source_id, native_id, canonical_url, title) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (source_item_id, source_id, receipt_id, f"https://fixture.riff.local/evidence/{receipt_id}", item.get("title", receipt_id)))
            conn.execute("INSERT INTO evidence_versions (evidence_id, source_item_id, content_hash, retrieved_at, raw_content, schema_version) VALUES (%s, %s, %s, %s, %s, 1) ON CONFLICT DO NOTHING", (evidence_id, source_item_id, digest, now, raw))
            conn.execute("INSERT INTO retrievals (retrieval_id, evidence_id, retrieved_at, outcome, metadata) VALUES (%s, %s, %s, 'SUCCESS', %s) ON CONFLICT DO NOTHING", (str(uuid.uuid5(uuid.NAMESPACE_URL, evidence_id)), evidence_id, now, Jsonb({"fixture": True})))
            conn.execute("""INSERT INTO evidence_receipts
                (receipt_id, evidence_id, content_hash, extractor_version, schema_version, status,
                 summary, relevant_spans, capability_candidates, technology_candidates, claims,
                 signal_strength, source_metadata, uncertainty)
                VALUES (%s, %s, %s, 'fixture-v1', 1, 'SUCCEEDED', %s, '[]', '[]', '[]', '[]', '{}', %s, '{}')
                ON CONFLICT (receipt_id) DO NOTHING""", (receipt_id, evidence_id, digest, str(item.get("summary", raw[:240])), Jsonb({"source_type": "TECHNICAL_WRITING", "fixture": True})))


def run_fixture(database_url: str, fixture: DailyFixture) -> dict[str, Any]:
    seed_fixture(database_url, fixture)
    repository = RiffRepository(database_url)
    fingerprint = daily_input_fingerprint(fixture.run_date, fixture.policy_version, fixture.candidates)
    cached = repository.existing_run(fingerprint) is not None
    result = DailyRiffService(repository, DeterministicReasoningProvider(), policy_version=fixture.policy_version).generate(fixture.run_date, fixture.candidates)
    return {"run_id": result.daily_run_id, "status": result.status, "published_count": len(result.riffs), "provider_calls": 0 if cached else result.provider_calls, "cached": cached, "result_url": f"/riffs/daily/{fixture.run_date.isoformat()}"}
