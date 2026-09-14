import os
from datetime import datetime, timedelta, timezone

import pytest

from riff.capabilities import CapabilityRepository
from riff.db import connection, migrate
from riff.evidence import EvidenceSubmission, SourceType
from riff.evidence_repository import EvidenceRepository
from riff.signal_evaluation import evaluate_fixture
from riff.signals import SignalObservation, SignalRanker, SignalRepository


WINDOW_END = datetime(2026, 9, 14, tzinfo=timezone.utc)
WINDOW_START = WINDOW_END - timedelta(days=30)


@pytest.fixture()
def graph():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    with connection(database_url) as conn:
        conn.execute("DELETE FROM signal_explanations")
        conn.execute("DELETE FROM signal_features")
        conn.execute("DELETE FROM candidate_signals")
        conn.execute("DELETE FROM correlation_members")
        conn.execute("DELETE FROM correlation_groups")
        conn.execute("DELETE FROM rank_runs")
        conn.execute("DELETE FROM rank_configs")
    evidence = EvidenceRepository(database_url)
    capabilities = CapabilityRepository(database_url)
    return database_url, evidence, capabilities


def _observations(database_url, evidence, capabilities, count, *, capability_name, source_type="GITHUB", organization_prefix="org", root_prefix="root", changed=True, established=False, profile_state="UNKNOWN", relevance=1.0, constant_organization=False, constant_root=False):
    capability = capabilities.upsert_capability(capability_name)
    source = evidence.create_source(SourceType(source_type), f"signal-{capability_name}-{source_type}-{count}-{os.urandom(2).hex()}")
    output = []
    for index in range(count):
        item = evidence.ingest(EvidenceSubmission(source_id=source.source_id, canonical_url=f"https://example.com/signal/{os.urandom(6).hex()}", raw_content=f"signal {capability_name} {index}"))
        organization = organization_prefix if constant_organization else f"{organization_prefix}-{index}"
        root = root_prefix if constant_root else f"{root_prefix}-{index}"
        output.append(SignalObservation(item.evidence_id, capability.capability_id, WINDOW_END - timedelta(days=index % 10), source_type, organization, f"repo-{index}", f"author-{index}", root, changed, established, profile_state, 1.0, relevance))
    return output, capability


@pytest.mark.postgres
def test_reposts_do_not_win_by_count(graph):
    database_url, evidence, capabilities = graph
    reposts, _ = _observations(database_url, evidence, capabilities, 40, capability_name="repost", source_type="TECHNICAL_WRITING", organization_prefix="same", root_prefix="announcement", changed=False, constant_organization=True, constant_root=True)
    cross = []
    for source_type, root in (("TECHNICAL_WRITING", "root-a"), ("GITHUB", "root-b"), ("JOBS", "root-c")):
        items, _ = _observations(database_url, evidence, capabilities, 1, capability_name="cross-source", source_type=source_type, organization_prefix=source_type, root_prefix=root)
        cross.extend(items)
    result = SignalRanker(SignalRepository(database_url)).rank(reposts + cross, window_start=WINDOW_START, window_end=WINDOW_END)
    assert [candidate.capability_id for candidate in result.candidates[:1]] == [capabilities.upsert_capability("cross-source").capability_id]


@pytest.mark.postgres
def test_single_employer_burst_is_downweighted(graph):
    database_url, evidence, capabilities = graph
    burst, _ = _observations(database_url, evidence, capabilities, 20, capability_name="single-employer", organization_prefix="same-employer", root_prefix="job-root", constant_organization=True, constant_root=True)
    independent, _ = _observations(database_url, evidence, capabilities, 3, capability_name="independent-employers", organization_prefix="different", root_prefix="independent")
    result = SignalRanker(SignalRepository(database_url)).rank(burst + independent, window_start=WINDOW_START, window_end=WINDOW_END)
    by_name = {candidate.capability_id: candidate for candidate in result.candidates}
    assert by_name[capabilities.upsert_capability("independent-employers").capability_id].score > by_name[capabilities.upsert_capability("single-employer").capability_id].score


@pytest.mark.postgres
def test_steady_volume_is_not_novel(graph):
    database_url, evidence, capabilities = graph
    items, capability = _observations(database_url, evidence, capabilities, 10, capability_name="established", source_type="GITHUB", root_prefix="roots", established=True, changed=False)
    result = SignalRanker(SignalRepository(database_url)).rank(items, window_start=WINDOW_START, window_end=WINDOW_END)
    candidate = result.candidates[0]
    assert candidate.features["novelty"] == 0 and candidate.classification != "TREND_CANDIDATE"


@pytest.mark.postgres
def test_frameworks_share_capability_signal(graph):
    database_url, evidence, capabilities = graph
    first, capability = _observations(database_url, evidence, capabilities, 1, capability_name="durable-execution", source_type="GITHUB", root_prefix="langgraph")
    second, _ = _observations(database_url, evidence, capabilities, 1, capability_name="durable-execution", source_type="TECHNICAL_WRITING", root_prefix="temporal")
    result = SignalRanker(SignalRepository(database_url)).rank(first + second, window_start=WINDOW_START, window_end=WINDOW_END)
    assert len(result.candidates) == 1 and result.candidates[0].capability_id == capability.capability_id


@pytest.mark.postgres
def test_profile_state_changes_personal_novelty(graph):
    database_url, evidence, capabilities = graph
    demonstrated, _ = _observations(database_url, evidence, capabilities, 2, capability_name="demonstrated", profile_state="PUBLICLY_DEMONSTRATED", root_prefix="demo")
    signaling, _ = _observations(database_url, evidence, capabilities, 2, capability_name="signaling", profile_state="SIGNALING_GAP", root_prefix="gap")
    result = SignalRanker(SignalRepository(database_url)).rank(demonstrated + signaling, window_start=WINDOW_START, window_end=WINDOW_END)
    by_id = {candidate.capability_id: candidate for candidate in result.candidates}
    assert by_id[capabilities.upsert_capability("signaling").capability_id].score > by_id[capabilities.upsert_capability("demonstrated").capability_id].score


@pytest.mark.postgres
def test_shared_root_articles_form_one_group(graph):
    database_url, evidence, capabilities = graph
    items, _ = _observations(database_url, evidence, capabilities, 10, capability_name="rooted", source_type="TECHNICAL_WRITING", root_prefix="paper-42", constant_root=True)
    result = SignalRanker(SignalRepository(database_url)).rank(items, window_start=WINDOW_START, window_end=WINDOW_END)
    with connection(database_url) as conn:
        count = conn.execute("SELECT count(*) FROM correlation_groups WHERE rank_run_id = %s", (result.rank_run_id,)).fetchone()[0]
    assert count == 1


@pytest.mark.postgres
def test_one_source_type_is_observation(graph):
    database_url, evidence, capabilities = graph
    items, _ = _observations(database_url, evidence, capabilities, 3, capability_name="single-type", source_type="GITHUB", root_prefix="one", constant_root=True)
    result = SignalRanker(SignalRepository(database_url)).rank(items, window_start=WINDOW_START, window_end=WINDOW_END)
    assert result.candidates[0].classification == "INSUFFICIENT_TREND_EVIDENCE"


@pytest.mark.postgres
def test_identical_rank_run_is_idempotent(graph):
    database_url, evidence, capabilities = graph
    items, _ = _observations(database_url, evidence, capabilities, 2, capability_name="repeat", source_type="GITHUB", root_prefix="r1")
    ranker = SignalRanker(SignalRepository(database_url))
    first = ranker.rank(items, window_start=WINDOW_START, window_end=WINDOW_END)
    second = ranker.rank(items, window_start=WINDOW_START, window_end=WINDOW_END)
    assert first.rank_run_id == second.rank_run_id
    with connection(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM rank_runs WHERE input_fingerprint = %s", (first.input_fingerprint,)).fetchone()[0] == 1


def test_signal_evaluation_fixture_is_offline():
    report = evaluate_fixture("tests/fixtures/signals/adversarial.json")
    assert report["cases"] == 4 and report["accuracy"] == 1.0
