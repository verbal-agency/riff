"""Deterministic, bounded retrieval packets for conversational riffing (G39)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .db import connection

POLICY_VERSION = "riff-context-policy-v1"
DEFAULT_RECEIPT_LIMIT = 5
DEFAULT_CHAR_BUDGET = 8_000
MAX_RECEIPT_LIMIT = 10
MAX_CHAR_BUDGET = 20_000


class ContextPacketError(ValueError):
    pass


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode("utf-8")
    return str(value or "").strip()


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (bytes, str)):
        try:
            return json.loads(value.decode() if isinstance(value, bytes) else value)
        except (TypeError, ValueError):
            return default
    return value if value is not None else default


def _tokens(chars: int) -> int:
    return max(1, (int(chars) + 3) // 4)


def _terms(value: str) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9][a-z0-9-]{2,}", value.lower()) if item not in {"the", "and", "for", "with", "from", "that", "this"}}


def _redact(value: str) -> str:
    value = re.sub(r"(?i)(authorization|api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", value)
    value = re.sub(r"https?://[^\s/@]+:[^\s/@]+@", "https://[REDACTED]@", value)
    return value


def _excerpt(value: str, limit: int = 1200) -> str:
    cleaned = _redact(re.sub(r"\s+", " ", value).strip())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def _freshness(value: Any) -> tuple[float, int | None]:
    raw = value
    if isinstance(raw, str):
        try:
            raw = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return 0.0, None
    if not hasattr(raw, "tzinfo"):
        return 0.0, None
    if raw.tzinfo is None:
        raw = raw.replace(tzinfo=timezone.utc)
    days = max(0, (datetime.now(timezone.utc) - raw.astimezone(timezone.utc)).days)
    return (1.0 if days <= 180 else 0.5 if days <= 730 else 0.0), days


def select_context_packet(
    query: str,
    candidates: Sequence[Mapping[str, Any]],
    *,
    project: Mapping[str, Any] | None = None,
    goal: Mapping[str, Any] | None = None,
    limit: int = DEFAULT_RECEIPT_LIMIT,
    char_budget: int = DEFAULT_CHAR_BUDGET,
    page: int = 0,
    seen_evidence_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Select diverse compact receipts without passing raw source bodies."""
    query = _text(query)
    if not query or len(query) > 500:
        raise ContextPacketError("query must be non-empty and under 500 characters")
    if not 1 <= int(limit) <= MAX_RECEIPT_LIMIT:
        raise ContextPacketError(f"limit must be between 1 and {MAX_RECEIPT_LIMIT}")
    if not 256 <= int(char_budget) <= MAX_CHAR_BUDGET:
        raise ContextPacketError(f"char_budget must be between 256 and {MAX_CHAR_BUDGET}")
    if int(page) < 0 or int(page) > 3:
        raise ContextPacketError("page must be between 0 and 3")
    seen = {_text(item) for item in seen_evidence_ids if _text(item)}
    query_terms = _terms(query)
    context_terms = _terms(" ".join(
        _text(value)
        for value in (
            (project or {}).get("repository") if isinstance(project, Mapping) else "",
            (project or {}).get("purpose") if isinstance(project, Mapping) else "",
            (goal or {}).get("title") if isinstance(goal, Mapping) else "",
        )
    ))
    ranked: list[tuple[float, int, Mapping[str, Any]]] = []
    for index, item in enumerate(candidates):
        evidence_id = _text(item.get("evidence_id"))
        if not evidence_id or evidence_id in seen:
            continue
        corpus = " ".join(_text(item.get(key)) for key in ("title", "summary", "raw_content", "signal_class", "source_type", "source_name"))
        overlap = len(query_terms & _terms(corpus))
        if query_terms and overlap == 0:
            continue
        source_root = _text(item.get("canonical_root") or item.get("source_name") or item.get("source_type") or "unknown")
        correlation = _text(item.get("correlation_group")) or source_root
        freshness_score, freshness_days = _freshness(item.get("published_at"))
        context_overlap = len(context_terms & _terms(corpus))
        score = float(overlap) * 10.0
        score += float(context_overlap) * 3.0
        score += freshness_score
        if _text(item.get("evidence_role")) == "PRIMARY_EVIDENCE": score += 2.0
        if _text(item.get("canonical_url")): score += 0.5
        ranked.append((score, index, {**dict(item), "_root": source_root, "_correlation": correlation, "_query_overlap": overlap, "_context_overlap": context_overlap, "_freshness_score": freshness_score, "_freshness_days": freshness_days}))
    ranked.sort(key=lambda entry: (-entry[0], entry[1]))
    start = int(page) * int(limit)
    window = ranked[start : start + int(limit) * 3]
    selected: list[dict[str, Any]] = []
    correlations: set[str] = set()
    used_chars = 0
    deferred: list[dict[str, Any]] = []
    for score, _, item in window:
        excerpt = _excerpt(_text(item.get("summary") or item.get("raw_content")))
        citation = {
            "evidence_id": _text(item.get("evidence_id")),
            "title": _text(item.get("title")) or "Untitled evidence",
            "summary": _excerpt(_text(item.get("summary")) or excerpt, 500),
            "excerpt": excerpt,
            "canonical_url": _text(item.get("canonical_url")),
            "source_type": _text(item.get("source_type")),
            "source_name": _text(item.get("source_name")),
            "canonical_root": _text(item.get("canonical_root")),
            "published_at": item.get("published_at").isoformat() if hasattr(item.get("published_at"), "isoformat") else (_text(item.get("published_at")) or None),
            "evidence_role": _text(item.get("evidence_role")) or "UNKNOWN",
            "correlation_group": _text(item.get("correlation_group")) or None,
            "selection_score": round(score, 3),
            "freshness_days": item["_freshness_days"],
            "selection_reasons": sorted(set(( 
                (["query_overlap"] if item["_query_overlap"] else [])
                + (["project_goal_fit"] if item["_context_overlap"] else [])
                + (["fresh"] if item["_freshness_score"] else [])
                + (["primary_evidence"] if _text(item.get("evidence_role")) == "PRIMARY_EVIDENCE" else [])
            ))),
        }
        cost = len(json.dumps(citation, sort_keys=True, default=str))
        if used_chars + cost > int(char_budget):
            deferred.append({"evidence_id": citation["evidence_id"], "reason": "context_char_budget"})
            continue
        if item["_correlation"] in correlations:
            deferred.append({"evidence_id": citation["evidence_id"], "reason": "correlated_source"})
            continue
        correlations.add(item["_correlation"])
        selected.append(citation)
        used_chars += cost
        if len(selected) >= int(limit):
            break
    for _, _, item in window:
        evidence_id = _text(item.get("evidence_id"))
        if evidence_id and evidence_id not in {entry["evidence_id"] for entry in selected} and not any(entry["evidence_id"] == evidence_id for entry in deferred):
            deferred.append({"evidence_id": evidence_id, "reason": "selection_limit"})
    context_items: list[dict[str, Any]] = []
    if project:
        context_items.append({"kind": "project", "reference": _text(project.get("repository") or project.get("display_name") or project.get("project_id")), "purpose": _excerpt(_text(project.get("purpose")), 500)})
    if goal:
        context_items.append({"kind": "goal", "title": _text(goal.get("title")), "status": _text(goal.get("status")) or "UNKNOWN", "evidence_ids": list(goal.get("source_evidence_ids", []))[:5]})
    packet_payload = {"query": query, "page": int(page), "evidence_ids": [item["evidence_id"] for item in selected], "project": context_items}
    packet_id = "context-" + hashlib.sha256(json.dumps(packet_payload, sort_keys=True, default=str).encode()).hexdigest()[:24]
    uncertainty = []
    if not selected: uncertainty.append("no_matching_evidence_in_bounded_ledger")
    if deferred: uncertainty.append("additional_evidence_was_omitted_by_budget_or_correlation")
    if any(item.get("evidence_role") in {"USER_LEAD", "SECONDARY_SYNTHESIS"} for item in selected): uncertainty.append("selected_lead_or_secondary_source_requires_validation")
    return {"packet_id": packet_id, "policy_version": POLICY_VERSION, "query": query, "page": int(page), "evidence": selected, "project_goal_context": context_items, "omitted": deferred[:20], "more_available": bool(len(ranked) > start + len(selected)), "uncertainty": sorted(set(uncertainty)), "usage": {"character_count": used_chars, "estimated_input_tokens": _tokens(used_chars), "estimated_context_tokens": _tokens(used_chars + len(query) + 600), "char_budget": int(char_budget), "receipt_limit": int(limit)}}


class ContextPacketRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def candidates(self, query: str, *, limit: int = 100) -> list[dict[str, Any]]:
        value = _text(query)
        if not value: raise ContextPacketError("query is required")
        terms = sorted(_terms(value))[:12]
        if not terms:
            raise ContextPacketError("query must contain searchable terms")
        clauses = " OR ".join("(e.raw_content ILIKE %s OR si.title ILIKE %s OR s.name ILIKE %s)" for _ in terms)
        params: list[Any] = []
        for term in terms:
            pattern = f"%{term}%"
            params.extend((pattern, pattern, pattern))
        params.append(min(max(int(limit), 1), 200))
        with connection(self.database_url) as conn:
            rows = conn.execute(f"""SELECT e.evidence_id,si.title,si.canonical_url,e.raw_content,e.published_at,
                       s.source_type,s.name,s.canonical_root,r.metadata
                FROM evidence_versions e JOIN source_items si USING (source_item_id)
                JOIN sources s USING (source_id)
                LEFT JOIN LATERAL (SELECT metadata FROM retrievals rr WHERE rr.evidence_id=e.evidence_id ORDER BY rr.retrieved_at DESC LIMIT 1) r ON TRUE
                WHERE {clauses}
                ORDER BY e.retrieved_at DESC LIMIT %s""", tuple(params)).fetchall()
        result = []
        for row in rows:
            metadata = _json(row[8], {})
            result.append({"evidence_id": _text(row[0]), "title": _text(row[1]), "canonical_url": _text(row[2]), "raw_content": _text(row[3]), "published_at": row[4], "source_type": _text(row[5]), "source_name": _text(row[6]), "canonical_root": _text(row[7]) or _text(metadata.get("canonical_root")), "signal_class": _text(metadata.get("signal_class")), "evidence_role": _text(metadata.get("evidence_role")) or "UNKNOWN", "correlation_group": _text(metadata.get("correlation_group")), "summary": _text(metadata.get("summary"))})
        return result

    def build(self, query: str, *, project: Mapping[str, Any] | None = None, goal: Mapping[str, Any] | None = None, limit: int = DEFAULT_RECEIPT_LIMIT, char_budget: int = DEFAULT_CHAR_BUDGET, page: int = 0, seen_evidence_ids: Sequence[str] = ()) -> dict[str, Any]:
        return select_context_packet(query, self.candidates(query), project=project, goal=goal, limit=limit, char_budget=char_budget, page=page, seen_evidence_ids=seen_evidence_ids)
