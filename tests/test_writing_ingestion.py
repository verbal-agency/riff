from datetime import datetime, timezone
from pathlib import Path

import pytest

from riff.ingestion import PermanentFeedError, cursor_marker, marker_after, parse_feed


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "feeds"


def test_rss_fixture_parses_and_orders_entries():
    entries = parse_feed(
        (FIXTURE_DIR / "initial.xml").read_bytes(),
        fetched_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    assert [entry.native_id for entry in entries] == ["article-1", "article-2"]
    assert entries[0].link == "https://example.com/articles/durable?utm_source=feed"
    assert entries[0].content.startswith("Recovery and replay")


def test_atom_fixture_resolves_relative_link_against_final_url():
    entries = parse_feed(
        (FIXTURE_DIR / "atom.xml").read_bytes(),
        fetched_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        base_url="https://example.com/feed.xml",
    )
    assert entries[0].link == "https://example.com/articles/atom-1"
    assert entries[0].observed_at == datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def test_missing_link_is_retained_as_an_invalid_entry_for_quarantine():
    entries = parse_feed(
        (FIXTURE_DIR / "malformed-entry.xml").read_bytes(),
        fetched_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    assert entries[1].native_id == "missing-link"
    assert entries[1].link is None


def test_invalid_xml_and_unsupported_document_are_permanent_errors():
    with pytest.raises(PermanentFeedError, match="could not be parsed"):
        parse_feed(b"<rss>", fetched_at=datetime.now(timezone.utc))
    with pytest.raises(PermanentFeedError, match="unsupported"):
        parse_feed(b"<html />", fetched_at=datetime.now(timezone.utc))


def test_cursor_marker_rejects_older_entries_and_invalid_cursor():
    entries = parse_feed(
        (FIXTURE_DIR / "initial.xml").read_bytes(),
        fetched_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    assert marker_after(entries[0], None)
    assert not marker_after(entries[0], cursor_marker(entries[1]))
    with pytest.raises(PermanentFeedError, match="cursor"):
        marker_after(entries[0], "not-json")
