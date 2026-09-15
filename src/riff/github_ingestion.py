"""Bounded, read-only GitHub collection built on the G02 ingestion contracts."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

import httpx
from psycopg.types.json import Jsonb

from .db import connection
from .evidence import EvidenceSubmission, EvidenceValidationError
from .evidence_repository import EvidenceRepository
from .ingestion import cursor_marker, marker_after
from .ingestion_repository import CollectionSummary, IngestionRepository, ItemOutcome, RunStatus


def _text(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return value


class GitHubError(RuntimeError):
    """Base class for typed GitHub adapter failures."""


class GitHubTransientError(GitHubError):
    """A request can be retried without changing the configured source."""

    def __init__(self, message: str, *, reset_at: str | None = None):
        super().__init__(message)
        self.reset_at = reset_at


class GitHubRateLimitError(GitHubTransientError):
    """GitHub rejected a request because the rate limit was exhausted."""


class GitHubPermanentError(GitHubError):
    """Authentication, configuration, or response validation failure."""


class GitHubArtifactType(str, Enum):
    REPOSITORY = "REPOSITORY"
    RELEASE = "RELEASE"
    README_CHANGE = "README_CHANGE"
    ISSUE = "ISSUE"
    DISCUSSION = "DISCUSSION"
    DEPENDENCY = "DEPENDENCY"
    ACTIVITY = "ACTIVITY"


@dataclass(frozen=True, slots=True)
class GitHubResponse:
    data: Any
    headers: Mapping[str, str]


class GitHubFetcher(Protocol):
    def fetch(self, path: str, *, params: Mapping[str, object] | None = None) -> GitHubResponse:
        ...


class HttpGitHubFetcher:
    """Read-only GitHub REST client with token-safe errors and bounded bodies."""

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        timeout: float = 20.0,
        max_bytes: int = 2_000_000,
        client: httpx.Client | None = None,
    ):
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)
        self._client.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "riff/0.1",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            }
        )
        self.max_bytes = max_bytes

    def fetch(self, path: str, *, params: Mapping[str, object] | None = None) -> GitHubResponse:
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise GitHubTransientError("GitHub request timed out") from exc
        except httpx.HTTPError as exc:
            raise GitHubTransientError("GitHub request failed") from exc
        if len(response.content) > self.max_bytes:
            raise GitHubPermanentError("GitHub response exceeded configured byte bound")
        headers = {key.lower(): value for key, value in response.headers.items()}
        if response.status_code == 429 or (
            response.status_code == 403 and headers.get("x-ratelimit-remaining") == "0"
        ):
            raise GitHubRateLimitError(
                "GitHub rate limit exhausted",
                reset_at=headers.get("x-ratelimit-reset"),
            )
        if response.status_code >= 500:
            raise GitHubTransientError(f"GitHub server error ({response.status_code})")
        if response.status_code in {401, 403, 404}:
            raise GitHubPermanentError(f"GitHub request rejected ({response.status_code})")
        if response.status_code >= 400:
            raise GitHubPermanentError(f"GitHub request failed ({response.status_code})")
        try:
            return GitHubResponse(response.json(), headers)
        except ValueError as exc:
            raise GitHubPermanentError("GitHub returned malformed JSON") from exc


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    provider_repository_id: str
    source_id: str
    owner_login: str
    organization_login: str | None
    name: str
    canonical_url: str
    is_fork: bool
    is_mirror: bool
    stars: int | None


@dataclass(frozen=True, slots=True)
class GitHubArtifact:
    provider_artifact_id: str
    artifact_type: GitHubArtifactType
    repository: GitHubRepository
    canonical_url: str
    title: str | None
    observed_at: datetime
    content: str
    author_login: str | None
    author_type: str | None
    metadata: dict[str, object]


class GitHubMetadataRepository:
    """Persistence for provider identities that should not be inferred later."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def upsert_repository(self, source_id: str, payload: Mapping[str, Any], *, observed_at: datetime) -> GitHubRepository:
        repository = _repository_from_payload(source_id, payload)
        metadata = {
            "default_branch": payload.get("default_branch"),
            "description": payload.get("description"),
            "archived": bool(payload.get("archived", False)),
            "visibility": payload.get("visibility"),
        }
        with connection(self.database_url) as conn:
            old = conn.execute(
                "SELECT canonical_url, owner_login, name FROM github_repositories "
                "WHERE provider_repository_id = %s",
                (repository.provider_repository_id,),
            ).fetchone()
            if old:
                old = tuple(_text(value) for value in old)
            conn.execute(
                """
                INSERT INTO github_repositories
                (provider_repository_id, source_id, owner_login, organization_login, name,
                 canonical_url, is_fork, is_mirror, stars, metadata, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (provider_repository_id) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    owner_login = EXCLUDED.owner_login,
                    organization_login = EXCLUDED.organization_login,
                    name = EXCLUDED.name,
                    canonical_url = EXCLUDED.canonical_url,
                    is_fork = EXCLUDED.is_fork,
                    is_mirror = EXCLUDED.is_mirror,
                    stars = EXCLUDED.stars,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    repository.provider_repository_id,
                    source_id,
                    repository.owner_login,
                    repository.organization_login,
                    repository.name,
                    repository.canonical_url,
                    repository.is_fork,
                    repository.is_mirror,
                    repository.stars,
                    Jsonb(metadata),
                    observed_at,
                ),
            )
            if old and old[0] != repository.canonical_url:
                conn.execute(
                    "INSERT INTO github_repository_aliases "
                    "(provider_repository_id, owner_login, name, canonical_url, observed_at) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (repository.provider_repository_id, old[1], old[2], old[0], observed_at),
                )
            conn.execute(
                "INSERT INTO github_repository_aliases "
                "(provider_repository_id, owner_login, name, canonical_url, observed_at) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    repository.provider_repository_id,
                    repository.owner_login,
                    repository.name,
                    repository.canonical_url,
                    observed_at,
                ),
            )
        return repository

    def record_artifact(
        self,
        *,
        evidence_id: str,
        source_id: str,
        artifact: GitHubArtifact,
        bounded: bool,
    ) -> None:
        with connection(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO github_artifacts
                (evidence_id, source_id, provider_artifact_id, artifact_type,
                 provider_repository_id, author_login, author_type, observed_at,
                 canonical_url, bounded, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (evidence_id) DO UPDATE SET
                    author_login = EXCLUDED.author_login,
                    author_type = EXCLUDED.author_type,
                    observed_at = EXCLUDED.observed_at,
                    canonical_url = EXCLUDED.canonical_url,
                    bounded = EXCLUDED.bounded,
                    metadata = EXCLUDED.metadata
                """,
                (
                    evidence_id,
                    source_id,
                    artifact.provider_artifact_id,
                    artifact.artifact_type.value,
                    artifact.repository.provider_repository_id,
                    artifact.author_login,
                    artifact.author_type,
                    artifact.observed_at,
                    artifact.canonical_url,
                    bounded,
                    Jsonb(artifact.metadata),
                ),
            )


class GitHubIngestionRunner:
    """Collect repository metadata and bounded releases, README, and issues."""

    def __init__(
        self,
        ingestion: IngestionRepository,
        evidence: EvidenceRepository,
        fetcher: GitHubFetcher,
        *,
        max_pages: int = 10,
        page_size: int = 100,
        content_limit: int = 20_000,
    ):
        if max_pages < 1 or page_size < 1 or content_limit < 1:
            raise ValueError("GitHub collection bounds must be positive")
        self.ingestion = ingestion
        self.evidence = evidence
        self.fetcher = fetcher
        self.max_pages = max_pages
        self.page_size = page_size
        self.content_limit = content_limit
        self.metadata = GitHubMetadataRepository(ingestion.database_url)

    def run(
        self,
        *,
        source_ids: list[str] | None = None,
        source_type=None,
        policy_version: str = "github-v1",
    ) -> CollectionSummary:
        if source_type is not None and str(source_type) not in {"GITHUB", "SourceType.GITHUB"}:
            raise EvidenceValidationError("GitHub ingestion requires source_type=GITHUB")
        sources = self.ingestion.list_sources(source_ids=source_ids, source_type="GITHUB")
        run = self.ingestion.start_run([source.source_id for source in sources], policy_version)
        counts = {"stored": 0, "duplicates": 0, "skipped": 0, "failed_transient": 0, "failed_permanent": 0}
        any_success = False
        any_failure = False
        try:
            for source in sources:
                if not source.enabled:
                    self.ingestion.record_item_result(run.run_id, source.source_id, ItemOutcome.SKIPPED, error_code="SOURCE_DISABLED")
                    counts["skipped"] += 1
                    continue
                source_success, source_failure = self._collect_source(run.run_id, source, counts)
                any_success = any_success or source_success
                any_failure = any_failure or source_failure
            status = RunStatus.PARTIAL if any_failure and any_success else RunStatus.FAILED if any_failure else RunStatus.SUCCEEDED
            self.ingestion.finish_run(run.run_id, status)
        except Exception:
            raise
        return CollectionSummary(run.run_id, status, **counts)

    def _collect_source(self, run_id: str, source, counts: dict[str, int]) -> tuple[bool, bool]:
        owner, name = _repository_scope(source.endpoint)
        repo_path = f"/repos/{owner}/{name}"
        source_success = False
        source_failure = False
        try:
            repo_response = self.fetcher.fetch(repo_path)
            if not isinstance(repo_response.data, Mapping):
                raise GitHubPermanentError("repository response must be an object")
            repository = self.metadata.upsert_repository(source.source_id, repo_response.data, observed_at=_now())
            repository_artifact = _repository_artifact(repository, repo_response.data)
            self._store_artifact(run_id, source, repository_artifact, counts, cursor_kind=None)
            source_success = True
        except (GitHubTransientError, GitHubPermanentError, GitHubError) as exc:
            source_failure = True
            self._record_source_failure(run_id, source.source_id, exc, counts)
            return source_success, source_failure

        endpoint_specs = (
            ("releases", f"{repo_path}/releases", GitHubArtifactType.RELEASE),
            ("issues", f"{repo_path}/issues", GitHubArtifactType.ISSUE),
        )
        for kind, path, artifact_type in endpoint_specs:
            try:
                self._collect_pages(run_id, source, repository, kind, path, artifact_type, counts)
                source_success = True
            except (GitHubTransientError, GitHubPermanentError, GitHubError) as exc:
                source_failure = True
                self._record_source_failure(run_id, source.source_id, exc, counts)

        try:
            readme_response = self.fetcher.fetch(f"{repo_path}/contents/README.md")
            readme = _readme_artifact(repository, readme_response.data)
            if readme is not None:
                self._collect_artifacts(run_id, source, "readme", [readme], counts)
            source_success = True
        except (GitHubTransientError, GitHubPermanentError, GitHubError) as exc:
            source_failure = True
            self._record_source_failure(run_id, source.source_id, exc, counts)
        return source_success, source_failure

    def _collect_pages(self, run_id, source, repository, kind, path, artifact_type, counts) -> None:
        cursor_kind = f"github:{kind}"
        for page in range(1, self.max_pages + 1):
            response = self.fetcher.fetch(path, params={"page": page, "per_page": self.page_size})
            if not isinstance(response.data, list):
                raise GitHubPermanentError(f"GitHub {kind} response must be a list")
            if not response.data:
                return
            artifacts = [_event_artifact(repository, item, artifact_type) for item in response.data]
            artifacts = [item for item in artifacts if item is not None]
            # GitHub pages are newest-first and can shift when a new event is
            # published. Replaying a completed page is safe because G01
            # deduplicates by provider ID/content hash; advancing only after the
            # whole page is durable prevents a mid-page failure from skipping it.
            self._collect_artifacts(run_id, source, None, artifacts, counts)
            self.ingestion.update_cursor(source.source_id, cursor_kind, _page_marker(page))

    def _collect_artifacts(self, run_id, source, cursor_kind, artifacts, counts, *, cursor=None) -> None:
        for artifact in sorted(artifacts, key=lambda item: (item.observed_at, item.provider_artifact_id)):
            if cursor_kind and not _marker_after(artifact, cursor):
                continue
            self._store_artifact(run_id, source, artifact, counts, cursor_kind=cursor_kind)
            if cursor_kind:
                cursor = self.ingestion.get_cursor(source.source_id, cursor_kind)

    def _store_artifact(self, run_id, source, artifact, counts, *, cursor_kind: str | None) -> None:
        bounded_content, truncated = _bounded(artifact.content, self.content_limit)
        # Carry the reviewed source-scope provenance into every retrieval so a
        # promoted discovery candidate remains traceable after G03 collection.
        retrieval_metadata = dict(source.metadata)
        retrieval_metadata.update(
            {
                "adapter": "github_rest",
                "artifact_type": artifact.artifact_type.value,
                "provider_repository_id": artifact.repository.provider_repository_id,
                "organization_login": artifact.repository.organization_login,
                "author_login": artifact.author_login,
                "author_type": artifact.author_type,
                "is_fork": artifact.repository.is_fork,
                "is_mirror": artifact.repository.is_mirror,
                "truncated": truncated,
                **artifact.metadata,
            }
        )
        result = self.evidence.ingest(
            EvidenceSubmission(
                source_id=source.source_id,
                canonical_url=artifact.canonical_url,
                native_id=artifact.provider_artifact_id,
                title=artifact.title,
                published_at=artifact.observed_at,
                raw_content=bounded_content,
                snapshot_ref=artifact.canonical_url if truncated else None,
                retrieval_metadata=retrieval_metadata,
            )
        )
        self.metadata.record_artifact(evidence_id=result.evidence_id, source_id=source.source_id, artifact=artifact, bounded=truncated)
        outcome = ItemOutcome.STORED if result.created else ItemOutcome.DUPLICATE
        self.ingestion.record_item_result(
            run_id,
            source.source_id,
            outcome,
            canonical_url=artifact.canonical_url,
            source_native_id=artifact.provider_artifact_id,
            evidence_id=result.evidence_id,
        )
        counts["stored" if result.created else "duplicates"] += 1
        if cursor_kind:
            self.ingestion.update_cursor(source.source_id, cursor_kind, _marker(artifact))

    def _record_source_failure(self, run_id, source_id, error: GitHubError, counts: dict[str, int]) -> None:
        transient = isinstance(error, GitHubTransientError)
        outcome = ItemOutcome.FAILED_TRANSIENT if transient else ItemOutcome.FAILED_PERMANENT
        key = "failed_transient" if transient else "failed_permanent"
        counts[key] += 1
        error_code = type(error).__name__.upper()
        if isinstance(error, GitHubRateLimitError) and error.reset_at:
            error_code = f"{error_code}:RESET_{error.reset_at}"
        self.ingestion.record_item_result(run_id, source_id, outcome, error_code=error_code)


def _repository_scope(endpoint: str) -> tuple[str, str]:
    parsed = urlsplit(endpoint)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "repos":
        owner, name = parts[1], parts[2]
    elif len(parts) == 2 and parsed.netloc in {"github.com", "www.github.com"}:
        owner, name = parts
    else:
        raise GitHubPermanentError("GitHub source endpoint must identify one repository")
    if not owner.strip() or not name.strip() or "?" in name:
        raise GitHubPermanentError("GitHub repository scope is invalid")
    return owner, name.removesuffix(".git")


def _repository_from_payload(source_id: str, payload: Mapping[str, Any]) -> GitHubRepository:
    provider_id = payload.get("id")
    owner = payload.get("owner") if isinstance(payload.get("owner"), Mapping) else {}
    organization = payload.get("organization") if isinstance(payload.get("organization"), Mapping) else {}
    full_name = str(payload.get("full_name") or "")
    if not provider_id or not full_name or "/" not in full_name or not payload.get("html_url"):
        raise GitHubPermanentError("repository response lacks stable identity fields")
    owner_login = str(owner.get("login") or full_name.split("/", 1)[0])
    organization_login = str(organization.get("login")) if organization.get("login") else (
        owner_login if owner.get("type") == "Organization" else None
    )
    return GitHubRepository(
        provider_repository_id=str(provider_id),
        source_id=source_id,
        owner_login=owner_login,
        organization_login=organization_login,
        name=full_name.split("/", 1)[1],
        canonical_url=str(payload["html_url"]),
        is_fork=bool(payload.get("fork", False)),
        is_mirror=bool(payload.get("mirror_url")),
        stars=int(payload["stargazers_count"]) if payload.get("stargazers_count") is not None else None,
    )


def _repository_artifact(repository: GitHubRepository, payload: Mapping[str, Any]) -> GitHubArtifact:
    stable = {
        "provider_repository_id": repository.provider_repository_id,
        "full_name": f"{repository.owner_login}/{repository.name}",
        "canonical_url": repository.canonical_url,
        "owner_login": repository.owner_login,
        "organization_login": repository.organization_login,
        "is_fork": repository.is_fork,
        "is_mirror": repository.is_mirror,
        "default_branch": payload.get("default_branch"),
        "description": payload.get("description"),
    }
    return GitHubArtifact(
        provider_artifact_id=f"repo:{repository.provider_repository_id}",
        artifact_type=GitHubArtifactType.REPOSITORY,
        repository=repository,
        canonical_url=repository.canonical_url,
        title=f"{repository.owner_login}/{repository.name}",
        observed_at=_parse_time(payload.get("updated_at") or payload.get("created_at")) or _now(),
        content=json.dumps(stable, sort_keys=True, separators=(",", ":")),
        author_login=repository.owner_login,
        author_type="Organization" if repository.organization_login else "User",
        metadata={"stars": repository.stars},
    )


def _event_artifact(repository: GitHubRepository, payload: Any, artifact_type: GitHubArtifactType) -> GitHubArtifact | None:
    if not isinstance(payload, Mapping):
        raise GitHubPermanentError("GitHub artifact must be an object")
    if artifact_type == GitHubArtifactType.ISSUE and payload.get("pull_request"):
        return None
    provider_id = payload.get("id")
    canonical_url = payload.get("html_url") or payload.get("url")
    if not provider_id or not canonical_url:
        raise GitHubPermanentError("GitHub artifact lacks stable identity fields")
    user = payload.get("author") or payload.get("user") or {}
    user = user if isinstance(user, Mapping) else {}
    observed_at = _parse_time(payload.get("published_at") or payload.get("created_at") or payload.get("updated_at"))
    if observed_at is None:
        raise GitHubPermanentError("GitHub artifact lacks a valid timestamp")
    title = payload.get("name") or payload.get("title") or payload.get("tag_name")
    body = payload.get("body") or payload.get("body_text") or payload.get("message") or ""
    content = json.dumps(
        {
            "provider_artifact_id": str(provider_id),
            "artifact_type": artifact_type.value,
            "title": title,
            "body": body,
            "tag_name": payload.get("tag_name"),
            "state": payload.get("state"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return GitHubArtifact(
        provider_artifact_id=str(provider_id),
        artifact_type=artifact_type,
        repository=repository,
        canonical_url=str(canonical_url),
        title=str(title) if title is not None else None,
        observed_at=observed_at,
        content=content,
        author_login=str(user.get("login")) if user.get("login") else None,
        author_type=str(user.get("type")) if user.get("type") else None,
        metadata={
            "node_id": payload.get("node_id"),
            "draft": payload.get("draft"),
            "state": payload.get("state"),
        },
    )


def _readme_artifact(repository: GitHubRepository, payload: Any) -> GitHubArtifact | None:
    if not isinstance(payload, Mapping) or not payload.get("sha") or not payload.get("html_url"):
        raise GitHubPermanentError("README response lacks stable identity fields")
    encoded = payload.get("content")
    if encoded:
        try:
            content = base64.b64decode(str(encoded).replace("\n", "")).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubPermanentError("README content is not valid base64") from exc
    else:
        content = str(payload.get("download_url") or payload.get("sha"))
    observed_at = _parse_time(payload.get("updated_at")) or _now()
    return GitHubArtifact(
        provider_artifact_id=f"readme:{payload['sha']}",
        artifact_type=GitHubArtifactType.README_CHANGE,
        repository=repository,
        canonical_url=str(payload["html_url"]),
        title="README.md",
        observed_at=observed_at,
        content=content,
        author_login=None,
        author_type=None,
        metadata={"sha": str(payload["sha"]), "path": payload.get("path", "README.md")},
    )


def _bounded(content: str, limit: int) -> tuple[str, bool]:
    if len(content) <= limit:
        return content, False
    return content[:limit], True


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _marker(artifact: GitHubArtifact) -> str:
    return cursor_marker(
        type("Marker", (), {"observed_at": artifact.observed_at, "native_id": artifact.provider_artifact_id})()
    )


def _marker_after(artifact: GitHubArtifact, cursor: str | None) -> bool:
    return marker_after(
        type("Marker", (), {"observed_at": artifact.observed_at, "native_id": artifact.provider_artifact_id})(),
        cursor,
    )


def _page_marker(page: int) -> str:
    return json.dumps({"page": page}, separators=(",", ":"), sort_keys=True)
