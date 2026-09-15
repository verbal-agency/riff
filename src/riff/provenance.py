"""Deterministic provenance-quality and epistemic-confidence policy.

Candidate relevance is intentionally kept separate from evidence quality.  The
policy is pure so it can be exercised offline and replayed when a policy or
receipt changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import Any, Mapping, Sequence


POLICY_VERSION = "provenance-policy-v1"
MAX_EPISTEMIC_CONFIDENCE = 0.95


@dataclass(frozen=True, slots=True)
class ProvenanceQuality:
    evidence_quality: float
    epistemic_confidence: float
    state: str
    promotion_allowed: bool
    summary: dict[str, Any]
    limitations: tuple[str, ...]
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_quality": self.evidence_quality,
            "epistemic_confidence": self.epistemic_confidence,
            "state": self.state,
            "promotion_allowed": self.promotion_allowed,
            "policy_version": self.policy_version,
            "summary": self.summary,
            "limitations": list(self.limitations),
        }


def assess_provenance(
    supporting: Sequence[Mapping[str, Any]],
    counterevidence: Sequence[Mapping[str, Any]] = (),
    *,
    candidate_score: float | None = None,
    generated_confidence: float | None = None,
    policy_version: str = POLICY_VERSION,
) -> ProvenanceQuality:
    """Assess support without treating receipt volume as independence.

    Inputs are bounded receipt projections, not arbitrary corpus rows.  Missing
    metadata remains unknown and is surfaced in ``limitations``.
    """

    support = [_normalize(item) for item in supporting]
    counter = [_normalize(item) for item in counterevidence]
    all_items = support + counter
    fixture_count = sum(1 for item in support if item["fixture"])
    roots = {item["independence_key"] for item in support if item["independence_key"]}
    source_types = {item["source_type"] for item in support if item["source_type"]}
    organizations = {item["organization"] for item in support if item["organization"]}
    authors = {item["author"] for item in support if item["author"]}
    content_hashes = [item["content_hash"] for item in support if item["content_hash"]]
    duplicate_content = len(content_hashes) - len(set(content_hashes))
    repost_count = sum(1 for item in support if item["repost"])
    citation_complete = sum(1 for item in support if item["citation_complete"])

    missing: list[str] = []
    for label, values in (("root source", roots), ("author", authors), ("organization", organizations)):
        if support and not values:
            missing.append(f"unknown {label} coverage")
    if support and citation_complete < len(support):
        missing.append(f"{len(support) - citation_complete} receipt(s) have incomplete citation metadata")

    if not support:
        state = "INSUFFICIENT"
        quality = 0.0
    elif fixture_count == len(support):
        state = "FIXTURE_ONLY"
        quality = 0.05
        missing.append("all supporting receipts are synthetic fixtures, not production evidence")
    elif counter:
        state = "CONTRADICTORY"
        quality = 0.35
    elif len(roots) < 2:
        state = "SINGLE_SOURCE"
        quality = 0.35
    else:
        state = "SUPPORTED"
        quality = 0.55 + min(0.20, (len(roots) - 2) * 0.05)
        quality += min(0.10, max(0, len(source_types) - 1) * 0.05)
        quality += min(0.10, max(0, len(organizations) - 1) * 0.05)
        quality += min(0.05, max(0, len(authors) - 1) * 0.025)
        if len(support) and citation_complete == len(support):
            quality += 0.05
    if duplicate_content or repost_count:
        quality = max(0.0, quality - min(0.20, 0.10 * max(duplicate_content, repost_count)))
        missing.append("reposts or duplicate content are downweighted")
    if counter:
        missing.append("counterevidence is present; the claim needs resolution before promotion")
    quality = round(min(1.0, quality), 4)

    ceiling = {
        "FIXTURE_ONLY": 0.20,
        "SINGLE_SOURCE": 0.55,
        "CONTRADICTORY": 0.45,
        "INSUFFICIENT": 0.20,
    }.get(state, MAX_EPISTEMIC_CONFIDENCE)
    raw_confidence = generated_confidence if generated_confidence is not None else candidate_score
    if raw_confidence is None:
        raw_confidence = 0.0
    epistemic = round(min(float(raw_confidence), quality, ceiling), 4)
    promotion_allowed = state == "SUPPORTED" and quality >= 0.70 and not counter and not missing
    summary = {
        "supporting_receipt_count": len(support),
        "counterevidence_count": len(counter),
        "fixture_receipt_count": fixture_count,
        "independent_root_count": len(roots),
        "source_type_count": len(source_types),
        "organization_count": len(organizations),
        "author_count": len(authors),
        "duplicate_content_count": duplicate_content,
        "repost_count": repost_count,
        "citation_complete_count": citation_complete,
        "observed_source_types": sorted(source_types),
        "observed_roots": sorted(roots),
        "unknown_provenance_fields": sorted(set(missing)),
        "evidence_quality": quality,
        "epistemic_confidence_ceiling": ceiling,
    }
    if state == "FIXTURE_ONLY":
        summary["interpretation"] = "Interesting hypothesis, but not supported by production evidence; do not promote on this evidence alone."
    elif state == "SINGLE_SOURCE":
        summary["interpretation"] = "Worth investigating, but one provenance root is insufficient for an established claim."
    elif state == "CONTRADICTORY":
        summary["interpretation"] = "Interesting but disputed; resolve counterevidence before promotion."
    elif state == "SUPPORTED":
        summary["interpretation"] = "Evidence is converging across independent provenance roots."
    else:
        summary["interpretation"] = "Insufficient provenance to assess the claim."
    return ProvenanceQuality(quality, epistemic, state, promotion_allowed, summary, tuple(sorted(set(missing))), policy_version)


def _normalize(item: Mapping[str, Any]) -> dict[str, Any]:
    metadata = item.get("source_metadata")
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    url = str(item.get("canonical_url") or "").strip()
    parsed = urlsplit(url) if url else None
    host = (parsed.hostname or "").lower() if parsed else ""
    fixture = bool(metadata.get("fixture") or metadata.get("synthetic") or host == "fixture.riff.local")
    root = _first(metadata, "canonical_root", "source_root", "root_source", "correlation_group")
    if not root:
        root = f"host:{host}" if host else _first(metadata, "source_id")
    organization = _first(metadata, "organization", "organization_at_publication", "company", "company_name", "employer")
    author = _first(metadata, "author", "author_name", "person_name")
    source_type = _first(metadata, "source_type")
    content_hash = _first(item, "content_hash") or _first(metadata, "content_hash")
    repost = bool(metadata.get("repost") or metadata.get("syndicated") or metadata.get("content_equivalent"))
    return {
        "fixture": fixture,
        "independence_key": str(root).strip() if root else None,
        "source_type": str(source_type).strip() if source_type else None,
        "organization": str(organization).strip().lower() if organization else None,
        "author": str(author).strip().lower() if author else None,
        "content_hash": str(content_hash).strip().lower() if content_hash else None,
        "repost": repost,
        "citation_complete": bool(url and item.get("title") and source_type),
    }


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return value
    return None
