import os

import pytest

from riff.db import migrate
from riff.provenance import (
    backfill_receipt_metadata,
    derive_stale_run_status,
    recalibrate_riffs,
    reconcile_stale_collection_runs,
    source_coverage_report,
)


def test_stale_run_without_items_is_failed():
    assert derive_stale_run_status(()) == ("FAILED", "STALE_RUN_NO_ITEM_RESULTS")


def test_stale_run_with_failures_is_partial():
    assert derive_stale_run_status(("STORED", "FAILED_TRANSIENT")) == ("PARTIAL", "STALE_RUN_WITH_FAILURES")


def test_stale_run_with_only_successful_items_is_reconciled_success():
    assert derive_stale_run_status(("STORED", "DUPLICATE", "SKIPPED")) == ("SUCCEEDED", "STALE_RUN_RECONCILED")


@pytest.mark.postgres
def test_data_quality_repair_is_idempotent_and_bounded():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    first = {
        "metadata": backfill_receipt_metadata(database_url),
        "runs": reconcile_stale_collection_runs(database_url),
        "riffs": recalibrate_riffs(database_url),
    }
    second = {
        "metadata": backfill_receipt_metadata(database_url),
        "runs": reconcile_stale_collection_runs(database_url),
        "riffs": recalibrate_riffs(database_url),
    }
    assert second["metadata"]["rows_updated"] == 0
    assert second["runs"]["reconciled"] == 0
    assert second["riffs"]["recalibrated"] == 0
    report = source_coverage_report(database_url, limit=3)
    assert report["total"] >= report["returned"] == 3
