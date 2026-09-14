"""Contracts and parsing/fetching primitives for incremental source ingestion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx


class FeedError(Exception):
    """Base class for source-fetch or feed-parse failures."""


class TransientFeedError(FeedError):
    """A failure that can safely be retried without changing the cursor."""


class PermanentFeedError(FeedError):
    """A source/configuration/parse failure requiring correction or quarantine."""


@dataclass(frozen=True, slots=True)
class FeedResponse:
    body: bytes
    fetched_at: datetime
    final_url: str | None = None


@dataclass(frozen=True, slots=True)
class FeedEntry:
    native_id: str
    link: str | None
    title: str | None
    content: str | None
    observed_at: datetime
    raw_xml: str


class FeedFetcher(Protocol):
    def fetch(self, endpoint: str) -> FeedResponse:
        """Fetch one feed without mutating Riff state."""


class HttpFeedFetcher:
    """Small bounded HTTP client for source-owned RSS/Atom feeds."""

    def __init__(self, *, timeout_seconds: float = 15.0, max_bytes: int = 2_000_000):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def fetch(self, endpoint: str) -> FeedResponse:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Riff/0.1 technical-writing collector"},
            ) as client:
                response = client.get(endpoint)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TransientFeedError(f"feed request failed transiently: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise PermanentFeedError(f"feed request failed: {type(exc).__name__}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise TransientFeedError(f"feed returned retryable HTTP {response.status_code}")
        if response.status_code >= 400:
            raise PermanentFeedError(f"feed returned HTTP {response.status_code}")
        body = response.content
        if len(body) > self.max_bytes:
            raise PermanentFeedError("feed response exceeded configured size limit")
        return FeedResponse(body=body, fetched_at=datetime.now(timezone.utc), final_url=str(response.url))


def parse_feed(body: bytes, *, fetched_at: datetime, base_url: str | None = None) -> list[FeedEntry]:
    """Parse RSS 2.x or Atom into normalized entries without network access."""

    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise PermanentFeedError("feed XML could not be parsed") from exc

    root_name = _local_name(root.tag)
    if root_name == "feed":
        nodes = [node for node in root if _local_name(node.tag) == "entry"]
        atom = True
    elif root_name in {"rss", "RDF", "RDF".lower()} or any(
        _local_name(node.tag) == "item" for node in root.iter()
    ):
        nodes = [node for node in root.iter() if _local_name(node.tag) == "item"]
        atom = False
    else:
        raise PermanentFeedError("unsupported feed document; expected RSS or Atom")

    entries: list[FeedEntry] = []
    for node in nodes:
        link = _entry_link(node, atom=atom)
        native_id = _first_text(node, {"id", "guid"}) or link
        native_id = native_id.strip() if native_id and native_id.strip() else ""
        title = _first_text(node, {"title"})
        content = _first_text(node, {"content", "encoded", "description", "summary"})
        date_text = _first_text(node, {"updated", "published", "pubDate", "date"})
        observed_at = _parse_datetime(date_text) if date_text else fetched_at
        entries.append(
            FeedEntry(
                native_id=native_id,
                link=urljoin(base_url or link, link) if link else None,
                title=title.strip() if title and title.strip() else None,
                content=content.strip() if content and content.strip() else None,
                observed_at=observed_at,
                raw_xml=ET.tostring(node, encoding="unicode"),
            )
        )
    entries.sort(key=lambda entry: (entry.observed_at, entry.native_id))
    return entries


def cursor_marker(entry: FeedEntry) -> str:
    """Encode a deterministic timestamp/native-ID cursor."""

    return json.dumps(
        {"observed_at": entry.observed_at.astimezone(timezone.utc).isoformat(), "native_id": entry.native_id},
        separators=(",", ":"),
        sort_keys=True,
    )


def marker_after(entry: FeedEntry, cursor_value: str | None) -> bool:
    if not cursor_value:
        return True
    try:
        marker = json.loads(cursor_value)
        cursor_time = datetime.fromisoformat(marker["observed_at"])
        cursor_id = str(marker["native_id"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise PermanentFeedError("stored feed cursor is invalid") from exc
    if cursor_time.tzinfo is None:
        cursor_time = cursor_time.replace(tzinfo=timezone.utc)
    return (entry.observed_at.astimezone(timezone.utc), entry.native_id) > (
        cursor_time.astimezone(timezone.utc),
        cursor_id,
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_text(node: ET.Element, names: set[str]) -> str | None:
    for child in node.iter():
        if _local_name(child.tag) in names and child.text:
            return child.text
    return None


def _entry_link(node: ET.Element, *, atom: bool) -> str | None:
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        rel = child.attrib.get("rel")
        if href and (not atom or rel in {None, "alternate"}):
            return href.strip()
        if child.text and child.text.strip():
            return child.text.strip()
    # Some valid RSS feeds expose the article permalink only in a GUID. Treat
    # it as a link only when the feed explicitly marks the GUID as permalink;
    # ordinary IDs must remain invalid and be quarantined by the runner.
    if not atom:
        for child in node:
            if _local_name(child.tag) != "guid" or child.attrib.get("isPermaLink", "true").lower() != "true":
                continue
            if child.text and child.text.strip() and child.text.strip().lower().startswith(("http://", "https://")):
                return child.text.strip()
    return None


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PermanentFeedError("feed entry has an invalid publication date") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
