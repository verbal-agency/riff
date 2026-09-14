import os
from pathlib import Path

import pytest

from riff.capabilities import CapabilityRepository
from riff.db import connection, migrate
from riff.profile import ProfileRepository, ProfileValidationError
from riff.profile_evaluation import evaluate_fixture


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "profile"


@pytest.fixture()
def profile():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    with connection(database_url) as conn:
        conn.execute("DELETE FROM gap_assessments")
        conn.execute("DELETE FROM profile_history")
        conn.execute("DELETE FROM experience_ledger")
        conn.execute("DELETE FROM profile_evidence")
        conn.execute("DELETE FROM normalization_decisions")
        conn.execute("DELETE FROM capability_relationships")
        conn.execute("DELETE FROM capability_mappings")
        conn.execute("DELETE FROM capability_aliases")
        conn.execute("DELETE FROM capability_patterns")
        conn.execute("DELETE FROM capability_concepts")
        conn.execute("DELETE FROM technologies")
        conn.execute("DELETE FROM capabilities")
    capability = CapabilityRepository(database_url).upsert_capability("durable execution")
    return database_url, ProfileRepository(database_url), capability


@pytest.mark.postgres
def test_private_without_public_is_signaling_gap(profile):
    _, repository, capability = profile
    entry = repository.create_ledger_entry(capability.capability_id, "I operate durable workflows professionally.", employer_or_context="client work")
    assessment = repository.assess(capability.capability_id)
    assert assessment.classification == "SIGNALING_GAP"
    assert entry.attestation_state == "USER_ATTESTED"
    assert repository.view(capability.capability_id, public=True).evidence == []
    assert len(repository.view(capability.capability_id).evidence) == 1


@pytest.mark.postgres
def test_user_attested_entry_is_redacted_from_public_view(profile):
    _, repository, capability = profile
    entry = repository.create_ledger_entry(capability.capability_id, "PRIVATE client delivery details")
    public = repository.list_evidence(capability.capability_id, view="PUBLIC")
    personal = repository.list_evidence(capability.capability_id, view="PERSONAL")
    assert public == []
    assert personal[0].description == "PRIVATE client delivery details"
    assert personal[0].attestation_state == "USER_ATTESTED"
    assert entry.profile_evidence_id == personal[0].profile_evidence_id


@pytest.mark.postgres
def test_github_technology_mention_is_not_hands_on_proof(profile):
    _, repository, capability = profile
    repository.create_evidence(capability.capability_id, evidence_level="UNKNOWN", visibility="PUBLIC", origin="GITHUB", confidence=0.4, description="Temporal appears in a dependency file.", reference="https://github.com/example/repo")
    assessment = repository.assess(capability.capability_id)
    assert assessment.classification == "UNKNOWN"
    assert all(item.evidence_level != "HANDS_ON_PERSONAL" for item in repository.list_evidence(capability.capability_id))


@pytest.mark.postgres
def test_correction_and_archive_recompute_with_history(profile):
    _, repository, capability = profile
    evidence = repository.create_evidence(capability.capability_id, evidence_level="STUDIED", visibility="PRIVATE", origin="MANUAL", confidence=0.7, description="Read about durable execution.")
    assert repository.assess(capability.capability_id).classification == "IMPLEMENTATION_GAP"
    repository.update_evidence(evidence.profile_evidence_id, evidence_level="HANDS_ON_PERSONAL", reason="confirmed build work")
    assert repository.assess(capability.capability_id).classification == "NO_MEANINGFUL_GAP"
    repository.archive_evidence(evidence.profile_evidence_id, reason="remove stale entry")
    assert repository.assess(capability.capability_id).classification == "UNKNOWN"
    assert [event["action"] for event in repository.history(evidence.profile_evidence_id)] == ["CREATE", "CORRECT", "ARCHIVE"]


@pytest.mark.postgres
def test_completed_artifact_requires_explicit_assessment(profile):
    _, repository, capability = profile
    repository.create_evidence(capability.capability_id, evidence_level="UNKNOWN", visibility="PRIVATE", origin="RIFF_ARTIFACT", confidence=0.8, description="A completed Riff artifact demonstrates a prototype.", reference="riff:artifact-1")
    assert repository.assess(capability.capability_id).classification == "UNKNOWN"
    with pytest.raises(ProfileValidationError):
        repository.create_evidence(capability.capability_id, evidence_level="HANDS_ON_PERSONAL", visibility="PRIVATE", origin="RIFF_ARTIFACT", confidence=1.0, description="artifact promoted without assessment")


@pytest.mark.postgres
def test_sparse_conflicting_evidence_is_unknown(profile):
    _, repository, capability = profile
    repository.create_evidence(capability.capability_id, evidence_level="UNKNOWN", visibility="PUBLIC", origin="GITHUB", confidence=0.3, description="A repository mentions an orchestration package.")
    repository.create_evidence(capability.capability_id, evidence_level="CONCEPTUALLY_FAMILIAR", visibility="PRIVATE", origin="MANUAL", confidence=0.4, description="I may understand the concept.")
    assessment = repository.assess(capability.capability_id)
    assert assessment.classification == "UNKNOWN"
    assert "insufficient" in assessment.rationale.lower() or "mention" in assessment.rationale.lower()


@pytest.mark.postgres
def test_profile_query_is_capability_scoped_and_redacted(profile):
    _, repository, capability = profile
    other = CapabilityRepository(profile[0]).upsert_capability("other capability")
    repository.create_ledger_entry(capability.capability_id, "secret selected capability")
    repository.create_ledger_entry(other.capability_id, "secret unrelated capability")
    public = repository.view(capability.capability_id, public=True)
    assert public.capability_id == capability.capability_id
    assert public.evidence == []
    assert all("secret" not in str(item) for item in public.evidence)


@pytest.mark.postgres
def test_public_fixture_import_and_ledger_crud_are_bounded(profile, tmp_path):
    _, repository, capability = profile
    fixture = tmp_path / "public.json"
    fixture.write_text(
        '{"schema_version": 1, "items": [{"capability_id": "%s", "origin": "WEBSITE", "description": "public project"}, {"capability_id": "%s", "origin": "GITHUB", "description": "repository mention"}]}'
        % (capability.capability_id, capability.capability_id), encoding="utf-8"
    )
    imported = repository.import_public_fixture(str(fixture), limit=1)
    assert len(imported) == 1 and imported[0].visibility == "PUBLIC"
    entry = repository.create_ledger_entry(capability.capability_id, "initial private note")
    updated = repository.update_ledger_entry(entry.ledger_id, "corrected private note", employer_or_context="context")
    assert updated.entry_text == "corrected private note"
    assert len(repository.list_ledger_entries()) == 1
    archived = repository.archive_ledger_entry(entry.ledger_id)
    assert archived.status == "ARCHIVED"


def test_profile_evaluation_fixture_is_offline():
    report = evaluate_fixture(FIXTURE_DIR / "gap_cases.json")
    assert report["cases"] == 5
    assert report["accuracy"] == 1.0
