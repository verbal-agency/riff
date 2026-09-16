"""Scoped, read-only GitHub account observation and repository selection (G33)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from psycopg.types.json import Jsonb

from .db import connection
from .github_ingestion import GitHubPermanentError, GitHubRateLimitError, GitHubResponse, GitHubTransientError, HttpGitHubFetcher
from .project_map import ProjectMapError, ProjectMapRepository


class GitHubAccountError(ValueError):
    """A scoped account observation or selection is invalid."""


class AccountFetcher(Protocol):
    def fetch(self, path: str, *, params: Mapping[str, object] | None = None) -> GitHubResponse:
        ...


class AccountScope:
    PUBLIC_METADATA = "PUBLIC_METADATA"
    PUBLIC_METADATA_AND_ACTIVITY = "PUBLIC_METADATA_AND_ACTIVITY"


class AccountStatus:
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    SCOPE_NARROWED = "SCOPE_NARROWED"


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode("utf-8")
    return str(value or "").strip()


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (bytes, str)):
        try:
            return json.loads(value.decode() if isinstance(value, bytes) else value)
        except (TypeError, ValueError):
            return default
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RepositoryCandidate:
    provider_repository_id: str
    full_name: str
    canonical_url: str
    visibility: str
    availability: str
    is_fork: bool
    is_archived: bool
    aliases: tuple[str, ...]
    observation_id: str
    observed_at: datetime
    omitted_fields: tuple[str, ...]
    uncertainty: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["aliases"] = list(self.aliases)
        value["omitted_fields"] = list(self.omitted_fields)
        return value


@dataclass(frozen=True, slots=True)
class AccountObservation:
    observation_id: str
    provider: str
    provider_account_id: str
    username: str
    scope: str
    scope_version: int
    status: str
    consented_at: datetime
    observed_at: datetime
    last_success_at: datetime | None
    omitted_fields: tuple[str, ...]
    repository_count: int

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["omitted_fields"] = list(self.omitted_fields)
        return value


def _candidate_payload(item: Mapping[str, Any], observation_id: str, observed_at: datetime) -> RepositoryCandidate:
    full_name = _text(item.get("full_name"))
    name = _text(item.get("name"))
    owner = _text((item.get("owner") or {}).get("login")) if isinstance(item.get("owner"), Mapping) else ""
    if not full_name:
        full_name = f"{owner}/{name}" if owner and name else name or "unknown/unknown"
    provider_id = _text(item.get("id"))
    canonical_url = _text(item.get("html_url")) or f"https://github.com/{full_name}"
    visibility = _text(item.get("visibility")).upper() or ("PUBLIC" if item.get("private") is False else "UNKNOWN")
    if visibility not in {"PUBLIC", "PRIVATE", "UNKNOWN"}:
        visibility = "UNKNOWN"
    accessible = item.get("accessible", True) is not False
    availability = "AVAILABLE" if visibility == "PUBLIC" and accessible else "OMITTED" if not accessible or visibility == "PRIVATE" else "UNKNOWN"
    omitted: list[str] = []
    for field in ("description", "language", "pushed_at", "updated_at"):
        if field not in item:
            omitted.append(field)
    uncertainty: dict[str, Any] = {}
    if availability == "OMITTED":
        uncertainty["reason"] = "private" if visibility == "PRIVATE" else "inaccessible"
    if not provider_id:
        provider_id = "omitted:" + hashlib.sha256(full_name.encode()).hexdigest()[:24]
        omitted.append("provider_repository_id")
        uncertainty["identity"] = "synthetic_omission_key"
    aliases = tuple(dict.fromkeys(str(value).strip() for value in (item.get("aliases") or []) if str(value).strip()))
    return RepositoryCandidate(
        provider_repository_id=provider_id,
        full_name=full_name,
        canonical_url=canonical_url,
        visibility=visibility,
        availability=availability,
        is_fork=bool(item.get("fork", item.get("is_fork", False))),
        is_archived=bool(item.get("archived", item.get("is_archived", False))),
        aliases=aliases,
        observation_id=observation_id,
        observed_at=observed_at,
        omitted_fields=tuple(sorted(set(omitted))),
        uncertainty=uncertainty,
    )


class FixtureAccountFetcher:
    """Replay a versioned account fixture without network access."""

    def __init__(self, payload: Mapping[str, Any]):
        self.payload = dict(payload)
        self.calls: list[tuple[str, int]] = []

    def fetch(self, path: str, *, params: Mapping[str, object] | None = None) -> GitHubResponse:
        page = int((params or {}).get("page", 1))
        self.calls.append((path, page))
        if path == "/user":
            return GitHubResponse(self.payload.get("user", {}), {})
        pages = self.payload.get("repository_pages", self.payload.get("repositories", []))
        if isinstance(pages, list) and (not pages or isinstance(pages[0], Mapping)):
            pages = [pages]
        if page <= len(pages):
            return GitHubResponse(pages[page - 1], {})
        return GitHubResponse([], {})


class GitHubAccountRepository:
    """Persist account observations while keeping credentials process-only."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def observe(
        self,
        fetcher: AccountFetcher,
        *,
        scope: str = AccountScope.PUBLIC_METADATA,
        consented_at: datetime | None = None,
        provider_account_id: str | None = None,
        username: str | None = None,
        max_pages: int = 10,
        retry_limit: int = 1,
    ) -> AccountObservation:
        if scope not in {AccountScope.PUBLIC_METADATA, AccountScope.PUBLIC_METADATA_AND_ACTIVITY}:
            raise GitHubAccountError("unsupported account observation scope")
        if max_pages < 1 or retry_limit < 0:
            raise GitHubAccountError("observation bounds must be positive")
        user = self._fetch_with_retry(fetcher, "/user", retry_limit=retry_limit)
        account_id = _text(provider_account_id) or _text(user.data.get("id")) if isinstance(user.data, Mapping) else ""
        login = _text(username) or _text(user.data.get("login")) if isinstance(user.data, Mapping) else ""
        if not account_id or not login:
            raise GitHubAccountError("GitHub account response must include id and login")
        with connection(self.database_url) as conn:
            current = conn.execute("SELECT status FROM github_account_observations WHERE provider = 'GITHUB' AND provider_account_id = %s ORDER BY scope_version DESC LIMIT 1", (account_id,)).fetchone()
        if current is not None and _text(current[0]) != AccountStatus.ACTIVE:
            raise GitHubAccountError("revoked or scope-narrowed account cannot be observed again without a new authorization")
        observed_at = _now()
        rows: list[Mapping[str, Any]] = []
        for page in range(1, max_pages + 1):
            response = self._fetch_with_retry(fetcher, "/user/repos", params={"visibility": "public", "affiliation": "owner", "per_page": 100, "page": page}, retry_limit=retry_limit)
            if not isinstance(response.data, list):
                raise GitHubAccountError("GitHub repository response must be a list")
            if not response.data:
                break
            rows.extend(item for item in response.data if isinstance(item, Mapping))
        omitted_fields = tuple(sorted(set(_text(item.get("reason")) for item in rows if item.get("reason"))))
        normalized: dict[str, RepositoryCandidate] = {}
        for item in rows:
            candidate = _candidate_payload(item, "pending", observed_at)
            prior = normalized.get(candidate.provider_repository_id)
            if prior:
                aliases = tuple(dict.fromkeys((*prior.aliases, prior.full_name, prior.canonical_url, *candidate.aliases, candidate.full_name, candidate.canonical_url)))
                candidate = RepositoryCandidate(**{**candidate.to_dict(), "aliases": aliases, "observation_id": "pending"})
            normalized[candidate.provider_repository_id] = candidate
        fingerprint_repositories = []
        for item in normalized.values():
            stable = item.to_dict()
            stable.pop("observation_id", None)
            stable.pop("observed_at", None)
            fingerprint_repositories.append(stable)
        fingerprint = hashlib.sha256(json.dumps({"account": account_id, "username": login, "scope": scope, "repositories": fingerprint_repositories}, sort_keys=True, default=str).encode()).hexdigest()
        consented_at = consented_at or observed_at
        with connection(self.database_url) as conn:
            prior = conn.execute("SELECT observation_id, scope_version, input_fingerprint FROM github_account_observations WHERE provider = 'GITHUB' AND provider_account_id = %s ORDER BY scope_version DESC LIMIT 1", (account_id,)).fetchone()
            if prior and _text(prior[2]) == fingerprint and int(prior[1]) > 0:
                return self.get(_text(prior[0]))
            version = int(prior[1]) + 1 if prior else 1
            observation_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO github_account_observations (observation_id, provider, provider_account_id, username, scope, scope_version, status, consented_at, observed_at, last_success_at, input_fingerprint, omitted_fields) VALUES (%s, 'GITHUB', %s, %s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s)",
                (observation_id, account_id, login, scope, version, consented_at, observed_at, observed_at, fingerprint, Jsonb(list(omitted_fields))),
            )
            source_id = f"github-account:{account_id}"
            conn.execute("INSERT INTO sources (source_id, source_type, name, canonical_root, enabled) VALUES (%s, 'GITHUB', %s, 'https://github.com', FALSE) ON CONFLICT (source_id) DO NOTHING", (source_id, f"GitHub account {login}"))
            for raw in normalized.values():
                candidate = RepositoryCandidate(**{**raw.to_dict(), "observation_id": observation_id})
                conn.execute(
                    "INSERT INTO github_account_observation_repositories (observation_id, provider_repository_id, full_name, canonical_url, visibility, availability, is_fork, is_archived, aliases, omitted_fields, uncertainty, observed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (observation_id, candidate.provider_repository_id, candidate.full_name, candidate.canonical_url, candidate.visibility, candidate.availability, candidate.is_fork, candidate.is_archived, Jsonb(list(candidate.aliases)), Jsonb(list(candidate.omitted_fields)), Jsonb(candidate.uncertainty), candidate.observed_at),
                )
                if candidate.availability == "AVAILABLE":
                    conn.execute(
                        "INSERT INTO github_repositories (provider_repository_id, source_id, owner_login, organization_login, name, canonical_url, is_fork, is_mirror, stars, metadata, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL, %s, %s) ON CONFLICT (provider_repository_id) DO UPDATE SET name = EXCLUDED.name, owner_login = EXCLUDED.owner_login, canonical_url = EXCLUDED.canonical_url, is_fork = EXCLUDED.is_fork, metadata = github_repositories.metadata || EXCLUDED.metadata, updated_at = EXCLUDED.updated_at",
                        (candidate.provider_repository_id, source_id, candidate.full_name.split("/", 1)[0], None, candidate.full_name.split("/", 1)[-1], candidate.canonical_url, candidate.is_fork, Jsonb({"visibility": "public", "archived": candidate.is_archived, "account_observation_id": observation_id}), observed_at),
                    )
                    for alias in candidate.aliases:
                        alias_url = alias if alias.startswith("http") else f"https://github.com/{alias}"
                        conn.execute("INSERT INTO github_repository_aliases (provider_repository_id, owner_login, name, canonical_url, observed_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (candidate.provider_repository_id, candidate.full_name.split("/", 1)[0], candidate.full_name.split("/", 1)[-1], alias_url, observed_at))
            conn.execute("INSERT INTO github_account_observation_events (event_id, observation_id, event_type, previous_status, new_status, previous_scope, new_scope, reason) VALUES (%s, %s, 'OBSERVED', NULL, 'ACTIVE', NULL, %s, %s)", (str(uuid.uuid4()), observation_id, scope, "user-authorized account observation"))
        return self.get(observation_id)

    def _fetch_with_retry(self, fetcher: AccountFetcher, path: str, *, params: Mapping[str, object] | None = None, retry_limit: int) -> GitHubResponse:
        attempts = 0
        while True:
            try:
                return fetcher.fetch(path, params=params)
            except (GitHubRateLimitError, GitHubTransientError) as exc:
                if attempts >= retry_limit:
                    raise GitHubAccountError("GitHub account observation could not complete after bounded retries") from exc
                attempts += 1

    def get(self, observation_id: str) -> AccountObservation:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT observation_id, provider, provider_account_id, username, scope, scope_version, status, consented_at, observed_at, last_success_at, omitted_fields, (SELECT count(*) FROM github_account_observation_repositories r WHERE r.observation_id = o.observation_id) FROM github_account_observations o WHERE observation_id = %s", (observation_id,)).fetchone()
        if row is None:
            raise GitHubAccountError("account observation not found")
        return AccountObservation(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), _text(row[4]), int(row[5]), _text(row[6]), row[7], row[8], row[9], tuple(_text(v) for v in _json(row[10], [])), int(row[11]))

    def current(self) -> AccountObservation:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT observation_id FROM github_account_observations WHERE provider = 'GITHUB' ORDER BY scope_version DESC, observed_at DESC LIMIT 1").fetchone()
        if row is None:
            raise GitHubAccountError("no GitHub account observation exists")
        return self.get(_text(row[0]))

    def status(self) -> dict[str, Any]:
        current = self.current()
        with connection(self.database_url) as conn:
            events = conn.execute("SELECT event_type, previous_status, new_status, previous_scope, new_scope, reason, created_at FROM github_account_observation_events WHERE observation_id = %s ORDER BY created_at", (current.observation_id,)).fetchall()
        return {"observation": current.to_dict(), "events": [{"event_type": _text(row[0]), "previous_status": _text(row[1]) or None, "new_status": _text(row[2]), "previous_scope": _text(row[3]) or None, "new_scope": _text(row[4]), "reason": _text(row[5]) or None, "created_at": row[6]} for row in events]}

    def repositories(self, observation_id: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        observation = self.get(observation_id) if observation_id else self.current()
        if limit < 1 or limit > 100:
            raise GitHubAccountError("repository limit must be between 1 and 100")
        with connection(self.database_url) as conn:
            rows = conn.execute("SELECT provider_repository_id, full_name, canonical_url, visibility, availability, is_fork, is_archived, aliases, omitted_fields, uncertainty, observed_at FROM github_account_observation_repositories WHERE observation_id = %s ORDER BY full_name, provider_repository_id LIMIT %s", (observation.observation_id, limit)).fetchall()
        return [RepositoryCandidate(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), _text(row[4]), bool(row[5]), bool(row[6]), tuple(_text(v) for v in _json(row[7], [])), observation.observation_id, row[10], tuple(_text(v) for v in _json(row[8], [])), dict(_json(row[9], {}))).to_dict() for row in rows]

    def _resolve(self, observation: AccountObservation, reference: str) -> dict[str, Any]:
        needle = _text(reference).casefold()
        candidates = self.repositories(observation.observation_id, limit=100)
        matches = []
        for item in candidates:
            names = {
                str(item["provider_repository_id"]).casefold(),
                str(item["full_name"]).casefold(),
                str(item["canonical_url"]).casefold(),
                str(item["full_name"]).rsplit("/", 1)[-1].casefold(),
                *(str(alias).casefold() for alias in item["aliases"]),
                *(str(alias).rsplit("/", 1)[-1].casefold() for alias in item["aliases"]),
            }
            if needle in names or any(needle in name for name in names if "/" in name or name == str(item["full_name"]).casefold()):
                matches.append(item)
        if not matches:
            raise GitHubAccountError("repository not found in the bounded account observation")
        if len(matches) > 1:
            raise GitHubAccountError("ambiguous repository reference; choose one of: " + ", ".join(item["full_name"] for item in matches[:5]))
        if matches[0]["availability"] != "AVAILABLE":
            raise GitHubAccountError("repository is omitted or inaccessible and cannot be onboarded")
        return matches[0]

    def _observation_or_current(self, observation_id: str | None) -> AccountObservation:
        return self.get(observation_id) if _text(observation_id) else self.current()

    def propose_selection(self, observation_id: str | None, reference: str, *, selected_by: str = "user", reason: str | None = None) -> dict[str, Any]:
        observation = self._observation_or_current(observation_id)
        observation_id = observation.observation_id
        if observation.status != AccountStatus.ACTIVE:
            raise GitHubAccountError("revoked or scope-narrowed account cannot select repositories")
        candidate = self._resolve(observation, reference)
        selection_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            existing = conn.execute("SELECT selection_id, status, project_id FROM github_account_repository_selections WHERE observation_id = %s AND provider_repository_id = %s", (observation_id, candidate["provider_repository_id"])).fetchone()
            if existing:
                return {"selection_id": _text(existing[0]), "observation_id": observation_id, "provider_repository_id": candidate["provider_repository_id"], "status": _text(existing[1]), "project_id": _text(existing[2]) or None, "repository": candidate}
            conn.execute("INSERT INTO github_account_repository_selections (selection_id, observation_id, provider_repository_id, status, selected_by, reason) VALUES (%s, %s, %s, 'PROPOSED', %s, %s)", (selection_id, observation_id, candidate["provider_repository_id"], _text(selected_by) or "user", reason))
        return {"selection_id": selection_id, "observation_id": observation_id, "provider_repository_id": candidate["provider_repository_id"], "status": "PROPOSED", "project_id": None, "repository": candidate}

    def onboard_selection(self, observation_id: str | None, reference: str, *, selected_by: str = "user", reason: str | None = None) -> dict[str, Any]:
        proposed = self.propose_selection(observation_id, reference, selected_by=selected_by, reason=reason)
        if proposed["status"] == "ONBOARDED":
            return proposed
        try:
            project = ProjectMapRepository(self.database_url).onboard(proposed["provider_repository_id"], display_name=proposed["repository"]["full_name"], reviewed_by=selected_by)
        except ProjectMapError as exc:
            raise GitHubAccountError(str(exc)) from exc
        with connection(self.database_url) as conn:
            conn.execute("UPDATE github_account_repository_selections SET status = 'ONBOARDED', project_id = %s, updated_at = now() WHERE selection_id = %s", (project.project_id, proposed["selection_id"]))
            conn.execute("UPDATE github_project_inventory SET account_observation_id = %s, account_selection_id = %s WHERE project_id = %s", (proposed["observation_id"], proposed["selection_id"], project.project_id))
        return {**proposed, "status": "ONBOARDED", "project_id": project.project_id}

    def decline_selection(self, observation_id: str | None, reference: str, *, selected_by: str = "user", reason: str | None = None) -> dict[str, Any]:
        proposed = self.propose_selection(observation_id, reference, selected_by=selected_by, reason=reason)
        with connection(self.database_url) as conn:
            conn.execute("UPDATE github_account_repository_selections SET status = 'DECLINED', updated_at = now() WHERE selection_id = %s", (proposed["selection_id"],))
        return {**proposed, "status": "DECLINED"}

    def revoke(self, observation_id: str | None = None, *, reason: str = "user revoked GitHub account observation") -> AccountObservation:
        return self._transition(self._observation_or_current(observation_id).observation_id, AccountStatus.REVOKED, reason=reason)

    def narrow_scope(self, observation_id: str | None = None, *, reason: str = "user narrowed GitHub account observation scope") -> AccountObservation:
        observation = self._observation_or_current(observation_id)
        if observation.scope == AccountScope.PUBLIC_METADATA:
            raise GitHubAccountError("account observation is already at the narrowest scope")
        return self._transition(observation_id, AccountStatus.SCOPE_NARROWED, new_scope=AccountScope.PUBLIC_METADATA, reason=reason)

    def _transition(self, observation_id: str, status: str, *, new_scope: str | None = None, reason: str) -> AccountObservation:
        observation = self.get(observation_id)
        if observation.status != AccountStatus.ACTIVE:
            raise GitHubAccountError("account observation is no longer active")
        scope = new_scope or observation.scope
        event_type = "REVOKED" if status == AccountStatus.REVOKED else "SCOPE_NARROWED"
        with connection(self.database_url) as conn:
            conn.execute("UPDATE github_account_observations SET status = %s, scope = %s, updated_at = now() WHERE observation_id = %s", (status, scope, observation_id))
            conn.execute("INSERT INTO github_account_observation_events (event_id, observation_id, event_type, previous_status, new_status, previous_scope, new_scope, reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (str(uuid.uuid4()), observation_id, event_type, observation.status, status, observation.scope, scope, reason))
        return self.get(observation_id)


__all__ = ["AccountScope", "AccountStatus", "AccountObservation", "RepositoryCandidate", "FixtureAccountFetcher", "GitHubAccountError", "GitHubAccountRepository", "HttpGitHubFetcher"]
