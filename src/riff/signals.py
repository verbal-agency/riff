"""Deterministic, explainable candidate-signal generation and ranking."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from psycopg.types.json import Jsonb

from .db import connection
from .evidence import EvidenceValidationError


DEFAULT_CONFIG_VERSION = "rank-v1"
DEFAULT_WEIGHTS = {
    "recency": 0.15,
    "change": 0.20,
    "source_diversity": 0.15,
    "independence": 0.20,
    "novelty": 0.15,
    "relevance": 0.15,
}


@dataclass(frozen=True, slots=True)
class SignalObservation:
    evidence_id: str
    capability_id: str
    observed_at: datetime
    source_type: str
    organization: str | None = None
    repository: str | None = None
    author: str | None = None
    root_source: str | None = None
    changed: bool = True
    established: bool = False
    profile_state: str = "UNKNOWN"
    quality: float = 1.0
    relevance: float = 1.0


@dataclass(frozen=True, slots=True)
class SignalCandidate:
    signal_id: str
    rank_run_id: str
    capability_id: str
    classification: str
    rank: int
    score: float
    features: dict[str, float]
    contributions: dict[str, float]
    eligibility_reason: str


@dataclass(frozen=True, slots=True)
class RankRunResult:
    rank_run_id: str
    config_version: str
    input_fingerprint: str
    candidates: list[SignalCandidate]


class SignalRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def ensure_config(self, config_version: str = DEFAULT_CONFIG_VERSION, weights: Mapping[str, float] | None = None, *, min_source_types: int = 2) -> None:
        values = dict(weights or DEFAULT_WEIGHTS)
        if not values or any(not isinstance(value, (int, float)) or value < 0 for value in values.values()) or min_source_types < 1:
            raise EvidenceValidationError("invalid rank configuration")
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO rank_configs (config_version, weights, min_source_types) VALUES (%s, %s, %s) ON CONFLICT (config_version) DO NOTHING",
                (config_version, Jsonb(values), min_source_types),
            )

    def existing_run(self, input_fingerprint: str) -> RankRunResult | None:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT rank_run_id, config_version, input_fingerprint FROM rank_runs WHERE input_fingerprint = %s", (input_fingerprint,)).fetchone()
            if row is None:
                return None
            signals = conn.execute(
                "SELECT s.signal_id, s.rank_run_id, s.capability_id, s.classification, s.rank, s.score, f.features, e.contributions, e.eligibility_reason FROM candidate_signals s JOIN signal_features f ON f.signal_id = s.signal_id JOIN signal_explanations e ON e.signal_id = s.signal_id WHERE s.rank_run_id = %s ORDER BY s.rank", (row[0],)
            ).fetchall()
        return RankRunResult(_text(row[0]), _text(row[1]), _text(row[2]), [_candidate(item) for item in signals])

    def save_run(self, result: RankRunResult, observations: list[SignalObservation], *, window_start: datetime, window_end: datetime, weights: Mapping[str, float], min_source_types: int) -> RankRunResult:
        with connection(self.database_url) as conn:
            conn.execute("INSERT INTO rank_configs (config_version, weights, min_source_types) VALUES (%s, %s, %s) ON CONFLICT (config_version) DO NOTHING", (result.config_version, Jsonb(dict(weights)), min_source_types))
            conn.execute("INSERT INTO rank_runs (rank_run_id, config_version, input_fingerprint, window_start, window_end) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (input_fingerprint) DO NOTHING", (result.rank_run_id, result.config_version, result.input_fingerprint, window_start, window_end))
            for observation in observations:
                group_key = observation.root_source or observation.evidence_id
                conn.execute("INSERT INTO correlation_groups (group_id, rank_run_id, root_source) VALUES (%s, %s, %s) ON CONFLICT (rank_run_id, root_source) DO NOTHING", (str(uuid.uuid5(uuid.NAMESPACE_URL, result.rank_run_id + group_key)), result.rank_run_id, group_key))
                group_id = conn.execute("SELECT group_id FROM correlation_groups WHERE rank_run_id = %s AND root_source = %s", (result.rank_run_id, group_key)).fetchone()[0]
                conn.execute("INSERT INTO correlation_members (group_id, evidence_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (group_id, observation.evidence_id))
            for candidate in result.candidates:
                conn.execute("INSERT INTO candidate_signals (signal_id, rank_run_id, capability_id, classification, rank, score, window_start, window_end) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (candidate.signal_id, result.rank_run_id, candidate.capability_id, candidate.classification, candidate.rank, candidate.score, window_start, window_end))
                conn.execute("INSERT INTO signal_features (signal_id, features) VALUES (%s, %s) ON CONFLICT DO NOTHING", (candidate.signal_id, Jsonb(candidate.features)))
                conn.execute("INSERT INTO signal_explanations (signal_id, weights, contributions, eligibility_reason) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING", (candidate.signal_id, Jsonb(dict(weights)), Jsonb(candidate.contributions), candidate.eligibility_reason))
        return result

    def list_signals(self, rank_run_id: str, *, limit: int = 100) -> list[SignalCandidate]:
        if not 1 <= limit <= 500:
            raise EvidenceValidationError("limit must be between 1 and 500")
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT s.signal_id, s.rank_run_id, s.capability_id, s.classification, s.rank, s.score, f.features, e.contributions, e.eligibility_reason FROM candidate_signals s JOIN signal_features f ON f.signal_id = s.signal_id JOIN signal_explanations e ON e.signal_id = s.signal_id WHERE s.rank_run_id = %s ORDER BY s.rank LIMIT %s", (rank_run_id, limit)
            ).fetchall()
        return [_candidate(row) for row in rows]


class SignalRanker:
    def __init__(self, repository: SignalRepository, *, config_version: str = DEFAULT_CONFIG_VERSION, weights: Mapping[str, float] | None = None, min_source_types: int = 2):
        self.repository = repository
        self.config_version = config_version
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.min_source_types = min_source_types

    def rank(self, observations: Iterable[SignalObservation], *, window_start: datetime, window_end: datetime) -> RankRunResult:
        items = [item for item in observations if window_start <= item.observed_at <= window_end]
        if window_end < window_start:
            raise EvidenceValidationError("window_end must be after window_start")
        fingerprint = _fingerprint(items, self.config_version, window_start, window_end)
        cached = self.repository.existing_run(fingerprint)
        if cached:
            return cached
        groups: dict[str, list[SignalObservation]] = {}
        for item in items:
            groups.setdefault(item.capability_id, []).append(item)
        run_id = str(uuid.uuid4())
        candidates = []
        for capability_id, group in groups.items():
            features = _features(group, window_end)
            contributions = {name: self.weights.get(name, 0.0) * features.get(name, 0.0) for name in self.weights}
            score = sum(contributions.values()) * features["volume_adjustment"] * features["profile_adjustment"]
            source_types = int(features["source_type_count"])
            roots = int(features["root_count"])
            if source_types < self.min_source_types:
                classification, reason = "INSUFFICIENT_TREND_EVIDENCE", f"only {source_types} source type(s); requires {self.min_source_types}"
            elif roots < 2 or features["novelty"] <= 0:
                classification, reason = "OBSERVATION", "evidence is not sufficiently independent or recently changed"
            else:
                classification, reason = "TREND_CANDIDATE", "meets source-diversity, independence, and novelty policy"
            candidates.append((score, capability_id, classification, reason, features, contributions))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        output = [SignalCandidate(str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint + capability_id)), run_id, capability_id, classification, rank, round(score, 6), features, contributions, reason) for rank, (score, capability_id, classification, reason, features, contributions) in enumerate(candidates, 1)]
        result = RankRunResult(run_id, self.config_version, fingerprint, output)
        return self.repository.save_run(result, items, window_start=window_start, window_end=window_end, weights=self.weights, min_source_types=self.min_source_types)


def _features(group: list[SignalObservation], window_end: datetime) -> dict[str, float]:
    count = len(group)
    unique = lambda attr: len({getattr(item, attr) for item in group if getattr(item, attr)})
    age = max(0.0, (window_end - max(item.observed_at for item in group)).total_seconds() / 86400)
    source_type_count, root_count = unique("source_type"), unique("root_source")
    change = sum(item.changed for item in group) / count if count else 0.0
    established = sum(item.established for item in group) / count if count else 0.0
    profile_states = {item.profile_state for item in group}
    profile_adjustment = 0.25 if "PUBLICLY_DEMONSTRATED" in profile_states else 0.85 if "SIGNALING_GAP" in profile_states else 0.65
    return {
        "recency": max(0.0, 1.0 - age / 30.0), "change": change, "source_diversity": min(1.0, source_type_count / 2.0),
        "independence": sum(unique(attr) / count for attr in ("organization", "repository", "author", "root_source")) / 4 if count else 0.0,
        "novelty": change * (1.0 - established), "relevance": sum(item.relevance for item in group) / count if count else 0.0,
        "quality": sum(item.quality for item in group) / count if count else 0.0, "frequency": float(count), "source_type_count": float(source_type_count), "root_count": float(root_count),
        "volume_adjustment": min(1.0, 3.0 / math.sqrt(count)) if count else 0.0, "profile_adjustment": profile_adjustment,
    }


def _fingerprint(items: list[SignalObservation], config_version: str, window_start: datetime, window_end: datetime) -> str:
    payload = [{key: getattr(item, key) for key in ("evidence_id", "capability_id", "observed_at", "source_type", "organization", "repository", "author", "root_source", "changed", "established", "profile_state", "quality", "relevance")} for item in sorted(items, key=lambda value: (value.capability_id, value.evidence_id))]
    return hashlib.sha256(json.dumps({"config": config_version, "start": window_start.isoformat(), "end": window_end.isoformat(), "items": payload}, sort_keys=True, default=str).encode()).hexdigest()


def _candidate(row) -> SignalCandidate:
    return SignalCandidate(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), int(row[4]), float(row[5]), _json(row[6]), _json(row[7]), _text(row[8]))


def _json(value):
    if isinstance(value, (bytes, str)):
        return json.loads(value.decode() if isinstance(value, bytes) else value)
    return value


def _text(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return value
