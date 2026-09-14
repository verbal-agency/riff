"""Bounded job fetchers and deterministic listing decomposition."""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from .evidence import canonicalize_url
from .job_source_policy import JobPolicyError, JobSource


class JobFetchError(RuntimeError):
    """Base class for bounded job fetch failures."""


class JobTransientError(JobFetchError):
    """A fetch may be retried without advancing a source cursor."""


class JobPermanentError(JobFetchError):
    """A source, URL, or response cannot be retried safely."""


class JobDecompositionError(JobPermanentError):
    """A listing has no safe structured representation."""


@dataclass(frozen=True, slots=True)
class JobFetchResponse:
    body: bytes
    fetched_at: datetime
    final_url: str
    headers: Mapping[str, str]


class JobFetcher(Protocol):
    def fetch(self, url: str, source: JobSource) -> JobFetchResponse:
        ...


def validate_target_url(url: str, source: JobSource, *, resolve: bool = True) -> str:
    """Validate scheme, credentials, host allowlist, and public address."""

    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise JobPolicyError("listing URL is malformed") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise JobPolicyError("listing URL must use HTTP(S)")
    if parsed.username or parsed.password:
        raise JobPolicyError("listing URL must not contain credentials")
    host = parsed.hostname.lower().rstrip(".")
    if not any(host == allowed.lower().rstrip(".") or host.endswith("." + allowed.lower().rstrip(".")) for allowed in source.allowlist):
        raise JobPolicyError("listing URL host is not in the source allowlist")
    _reject_private_host(host, resolve=resolve)
    try:
        normalized = canonicalize_url(url)
    except ValueError as exc:
        raise JobPolicyError("listing URL is not canonicalizable") from exc
    return normalized


def _reject_private_host(host: str, *, resolve: bool) -> None:
    addresses: set[str] = set()
    try:
        direct = ipaddress.ip_address(host)
        addresses.add(str(direct))
    except ValueError:
        if resolve:
            try:
                addresses.update(item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM))
            except OSError as exc:
                raise JobPolicyError("listing host could not be resolved safely") from exc
    for value in addresses:
        address = ipaddress.ip_address(value)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
            raise JobPolicyError("listing URL resolves to a non-public address")


class HttpJobFetcher:
    """Read-only HTTP client with manual, revalidated redirect handling."""

    def __init__(self, *, user_agent: str = "Riff/0.1 job collector", client: httpx.Client | None = None):
        self.user_agent = user_agent
        self.client = client

    def fetch(self, url: str, source: JobSource) -> JobFetchResponse:
        current = validate_target_url(url, source)
        max_redirects = source.bounds["max_redirects"]
        try:
            owned_client = self.client is None
            client_context = self.client or httpx.Client(timeout=source.bounds["timeout_seconds"], follow_redirects=False, headers={"User-Agent": self.user_agent})
            with client_context if owned_client else _NullContext(client_context) as client:
                for redirect_count in range(max_redirects + 1):
                    response = client.get(current)
                    headers = {key.lower(): value for key, value in response.headers.items()}
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = headers.get("location")
                        if not location or redirect_count >= max_redirects:
                            raise JobPermanentError("redirect limit exceeded or location missing")
                        current = validate_target_url(urljoin(current, location), source)
                        continue
                    if response.status_code == 429 or response.status_code >= 500:
                        raise JobTransientError(f"job source returned retryable HTTP {response.status_code}")
                    if response.status_code >= 400:
                        raise JobPermanentError(f"job source returned HTTP {response.status_code}")
                    if len(response.content) > source.bounds["max_body_bytes"]:
                        raise JobPermanentError("job response exceeded configured body limit")
                    return JobFetchResponse(response.content, datetime.now(timezone.utc), current, headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise JobTransientError(f"job request failed transiently: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise JobPermanentError(f"job request failed: {type(exc).__name__}") from exc
        raise JobPermanentError("job response did not complete")


class _NullContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *_):
        return False


class FixtureJobFetcher:
    """Fetch one recorded response without touching the network."""

    def __init__(self, fixture_root: str | Path | None = None):
        self.fixture_root = Path(fixture_root) if fixture_root else None
        self.calls: list[str] = []

    def fetch(self, url: str, source: JobSource) -> JobFetchResponse:
        self.calls.append(url)
        path = Path(source.fixture_reference)
        if self.fixture_root and not path.is_absolute():
            path = self.fixture_root / path
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise JobPermanentError("job fixture could not be read") from exc
        if len(body) > source.bounds["max_body_bytes"]:
            raise JobPermanentError("job fixture exceeded configured body limit")
        return JobFetchResponse(body, datetime(2026, 9, 14, tzinfo=timezone.utc), url, {"content-type": "text/html"})


class _ListingHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.json_ld: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self.headings: list[str] = []
        self.text_parts: list[str] = []
        self._tag = ""
        self._script_type: str | None = None
        self._script_parts: list[str] = []
        self._capture_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        self._tag = tag.lower()
        if self._tag == "meta" and attrs_map.get("content"):
            key = attrs_map.get("name") or attrs_map.get("property")
            if key:
                self.meta[key.lower()] = attrs_map["content"]
        if self._tag == "script":
            self._script_type = attrs_map.get("type", "").lower()
            self._script_parts = []
        if self._tag in {"h1", "h2"}:
            self._capture_heading = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._script_type == "application/ld+json":
            self.json_ld.append("".join(self._script_parts))
            self._script_type = None
            self._script_parts = []
        if tag in {"h1", "h2"}:
            self._capture_heading = False
        self._tag = ""

    def handle_data(self, data: str) -> None:
        if self._script_type == "application/ld+json":
            self._script_parts.append(data)
            return
        value = " ".join(data.split())
        if not value:
            return
        if self._tag == "title":
            self.title = value
        if self._capture_heading:
            self.headings.append(value)
        self.text_parts.append(value)


def decompose_listing(body: bytes, *, final_url: str, fetched_at: datetime, allow_html_fallback: bool = True) -> dict[str, Any]:
    parser = _ListingHTMLParser()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise JobDecompositionError("listing HTML could not be parsed") from exc
    listing = _json_ld_jobposting(parser.json_ld)
    parser_version = "jobposting-jsonld-v1" if listing else "job-html-fallback-v1"
    if not listing and not allow_html_fallback:
        raise JobDecompositionError("listing has no JobPosting JSON-LD")
    if not listing:
        listing = _html_listing(parser)
    title = _text(listing.get("title") or listing.get("role_title"))
    if not title:
        raise JobDecompositionError("listing has no role title")
    canonical = _canonical_listing_url(listing.get("url") or parser.meta.get("og:url") or final_url, final_url)
    description = _text(listing.get("description") or listing.get("responsibilities"))
    observed = fetched_at.astimezone(timezone.utc) if fetched_at.tzinfo else fetched_at.replace(tzinfo=timezone.utc)
    metadata = {
        "adapter": "job_url",
        "parser_version": parser_version,
        "decomposition_version": "job-decomposition-v1",
        "source_url": final_url,
        "technologies": listing.get("technologies") or [],
        "skills": listing.get("skills") or [],
        "employment_type": listing.get("employment_type"),
        "raw_content_hash": __import__("hashlib").sha256(body).hexdigest(),
    }
    return {
        "provider_posting_id": _identifier(listing.get("identifier")),
        "canonical_url": canonical,
        "role_title": title,
        "company_name": _organization_name(listing.get("hiringOrganization") or listing.get("company_name")),
        "seniority": _text(listing.get("seniority")),
        "compensation": _compensation(listing.get("baseSalary") or listing.get("compensation")),
        "location": _location(listing.get("jobLocation") or listing.get("location")),
        "published_at": listing.get("datePosted") or listing.get("published_at"),
        "description": description or None,
        "responsibilities": _text(listing.get("responsibilities")) or None,
        "expired": _expired(listing.get("validThrough")),
        "provider": "url",
        "observed_at": observed.isoformat(),
        "metadata": metadata,
    }


def _json_ld_jobposting(scripts: list[str]) -> dict[str, Any] | None:
    for raw in scripts:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        values = payload if isinstance(payload, list) else payload.get("@graph", []) if isinstance(payload, Mapping) else []
        if isinstance(payload, Mapping):
            values = [payload] + (values if isinstance(values, list) else [])
        for item in values:
            if not isinstance(item, Mapping):
                continue
            types = item.get("@type", [])
            types = types if isinstance(types, list) else [types]
            if any(str(value).lower() == "jobposting" for value in types):
                return dict(item)
    return None


def _html_listing(parser: _ListingHTMLParser) -> dict[str, Any]:
    return {
        "title": parser.meta.get("og:title") or (parser.headings[0] if parser.headings else parser.title),
        "company_name": parser.meta.get("company") or parser.meta.get("og:site_name"),
        "location": parser.meta.get("joblocation") or parser.meta.get("location"),
        "description": parser.meta.get("description") or " ".join(parser.text_parts),
    }


def _canonical_listing_url(value: Any, fallback: str) -> str:
    try:
        candidate = canonicalize_url(str(value))
    except ValueError:
        candidate = canonicalize_url(fallback)
    return candidate


def _identifier(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("value") or value.get("name")
    return _text(value)


def _organization_name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _text(value.get("name"))
    return _text(value)


def _location(value: Any) -> str | None:
    if isinstance(value, list):
        return "; ".join(filter(None, (_location(item) for item in value))) or None
    if isinstance(value, Mapping):
        address = value.get("address") if isinstance(value.get("address"), Mapping) else value
        parts = [address.get(key) for key in ("addressLocality", "addressRegion", "addressCountry") if address.get(key)]
        return ", ".join(str(item) for item in parts) or _text(value.get("name"))
    return _text(value)


def _compensation(value: Any) -> str | None:
    if isinstance(value, Mapping):
        amount = value.get("value")
        if isinstance(amount, Mapping):
            low, high = amount.get("minValue"), amount.get("maxValue")
            amount = f"{low}-{high}" if low is not None and high is not None else low or high
        currency = value.get("currency") or value.get("currencyCode")
        unit = amount and (value.get("unitText") or (value.get("value") or {}).get("unitText") if isinstance(value.get("value"), Mapping) else None)
        return " ".join(str(item) for item in (amount, currency, unit) if item) or None
    return _text(value)


def _expired(value: Any) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed < datetime.now(timezone.utc)
    except ValueError:
        return False


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = unescape(str(value)).strip()
    return value or None
