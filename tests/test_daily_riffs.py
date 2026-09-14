from datetime import date

import pytest

from riff.riff_evaluation import evaluate_fixture
from riff.riffs import (
    CandidateContext,
    DailyRiffService,
    DeterministicReasoningProvider,
    RiffContext,
    RiffValidationError,
    validate_draft,
)


class FakeRepository:
    def __init__(self):
        self.receipts = {"r1", "r2", "r3", "r4", "r5"}
        self.cached = {}
        self.saved = []

    def eligible_receipts(self, ids):
        return set(ids) & self.receipts

    def existing_run(self, fingerprint):
        return self.cached.get(fingerprint)

    def save_run(self, result, contexts, drafts, **kwargs):
        self.cached[result.input_fingerprint] = result
        self.saved.append((result, contexts, drafts))
        return result


class FakeAssembler:
    def assemble(self, candidate):
        return RiffContext(candidate.candidate_id, candidate.capability_id, candidate.score, candidate.classification, candidate.observation, candidate.receipt_ids, tuple({"receipt_id": item, "summary": f"summary {item}"} for item in candidate.receipt_ids), candidate.profile_slice, candidate.decision_ids, candidate.profile_state, candidate.associated_technologies)


def candidate(index, score=0.9, *, gap="UNKNOWN"):
    return CandidateContext(f"c{index}", f"cap-{index}", score, "TREND_CANDIDATE", f"Observation {index}", (f"r{(index % 5) + 1}",), profile_state=gap)


def test_daily_result_is_bounded_to_three_and_rerun_is_idempotent():
    repository = FakeRepository()
    service = DailyRiffService(repository, DeterministicReasoningProvider(), max_candidates=5)
    service.assembler = FakeAssembler()
    first = service.generate(date(2026, 9, 14), [candidate(index) for index in range(5)])
    second = service.generate(date(2026, 9, 14), [candidate(index) for index in range(5)])
    assert first.status == "COMPLETED"
    assert len(first.riffs) == 3
    assert second.input_fingerprint == first.input_fingerprint
    assert len(repository.saved) == 1


def test_published_riff_has_required_fields():
    repository = FakeRepository()
    service = DailyRiffService(repository, DeterministicReasoningProvider())
    service.assembler = FakeAssembler()
    riff = service.generate(date(2026, 9, 14), [candidate(1)]).riffs[0]
    for field in ("observation", "hypothesis", "why_now", "why_it_matters", "user_relevance", "underlying_capability", "recommendation", "strongest_counterargument", "alternative_explanation"):
        assert getattr(riff, field)
    assert riff.falsification_conditions


def test_context_contains_only_relevant_slices():
    repository = FakeRepository()
    service = DailyRiffService(repository, DeterministicReasoningProvider())
    context = FakeAssembler().assemble(CandidateContext("c1", "cap-1", 0.9, "TREND_CANDIDATE", "Observation", ("r1",), ({"profile_evidence_id": "p1"},), ("decision-1",), "IMPLEMENTATION_GAP"))
    assert context.receipt_ids == ("r1",)
    assert context.profile_slice == ({"profile_evidence_id": "p1"},)
    assert context.decision_ids == ("decision-1",)


def test_no_eligible_candidate_publishes_zero_honestly():
    repository = FakeRepository()
    service = DailyRiffService(repository, DeterministicReasoningProvider(), quality_threshold=0.8)
    service.assembler = FakeAssembler()
    result = service.generate(date(2026, 9, 14), [candidate(1, score=0.2)])
    assert result.status == "EMPTY"
    assert result.riffs == ()
    assert "quality threshold" in result.empty_reason


def test_signaling_gap_gets_artifact_intervention():
    repository = FakeRepository()
    service = DailyRiffService(repository, DeterministicReasoningProvider())
    service.assembler = FakeAssembler()
    result = service.generate(date(2026, 9, 14), [candidate(1, gap="SIGNALING_GAP")])
    assert "artifact" in result.riffs[0].recommendation and "public" in result.riffs[0].recommendation


def test_invalid_citation_blocks_publication():
    context = RiffContext("c1", "cap", 0.9, "TREND_CANDIDATE", "Observed", ("r1",), ({"receipt_id": "r1", "summary": "summary"},), (), (), "UNKNOWN", ())
    output = dict(DeterministicReasoningProvider().generate(context))
    output["supporting_receipt_ids"] = ["unknown"]
    with pytest.raises(RiffValidationError, match="supporting citations"):
        validate_draft(output, context, {"r1"})


def test_weak_counterargument_blocks_publication():
    context = RiffContext("c1", "cap", 0.9, "TREND_CANDIDATE", "Observed", ("r1",), ({"receipt_id": "r1", "summary": "summary"},), (), (), "UNKNOWN", ())
    output = dict(DeterministicReasoningProvider().generate(context))
    output["strongest_counterargument"] = "maybe"
    with pytest.raises(RiffValidationError, match="too weak"):
        validate_draft(output, context, {"r1"})


def test_observation_hypothesis_and_recommendation_are_distinct():
    context = RiffContext("c1", "cap", 0.9, "TREND_CANDIDATE", "Observed", ("r1",), ({"receipt_id": "r1", "summary": "summary"},), (), (), "UNKNOWN", ())
    draft = validate_draft(DeterministicReasoningProvider().generate(context), context, {"r1"})
    assert len({draft.observation, draft.hypothesis, draft.recommendation}) == 3


def test_golden_fixture_is_structurally_bounded():
    report = evaluate_fixture("tests/fixtures/riffs/golden.json")
    assert report["cases"] == 4 and report["all_passed"]
