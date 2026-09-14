"""Bounded, user-approved Exploration lifecycle for Riffs (G11)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from .db import connection
from .decisions import DecisionRepository, Investigation


class ExplorationError(ValueError):
    """An invalid Exploration request or lifecycle transition."""


REQUIRED_LEARNING_STEPS = ("understand", "implement", "inspect", "compare", "demonstrate")
SELECTION_RULES = ("useful", "capability_driven", "concrete", "discussable", "completable", "portfolio_capable")


@dataclass(frozen=True, slots=True)
class Experiment:
    experiment_id: str
    exploration_id: str
    title: str
    description: str
    target_capability_id: str
    technology_ids: tuple[str, ...]
    learning_steps: tuple[str, ...]
    effort_hours: float
    effort_assumptions: tuple[str, ...]
    artifact_or_measurement: str
    competence_evidence: tuple[str, ...]
    selection_rules: dict[str, Any]
    status: str = "PROPOSED"


@dataclass(frozen=True, slots=True)
class Exploration:
    exploration_id: str
    riff_id: str
    approval_decision_id: str
    status: str
    thesis: str
    why_it_matters: str
    what_i_want_to_understand: str
    capability_targets: tuple[str, ...]
    technology_targets: tuple[str, ...]
    open_questions: tuple[str, ...]
    possible_experiments: tuple[Experiment, ...]
    estimated_effort: dict[str, Any]
    evidence_of_competence: tuple[str, ...]
    version: int
    selected_experiment_id: str | None = None
    history: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_experiment(experiment: Experiment) -> None:
    """Enforce the PRD's bounded, useful, capability-driven experiment contract."""
    if not experiment.title.strip() or not experiment.description.strip():
        raise ExplorationError("experiment title and description are required")
    if not experiment.target_capability_id.strip() or not experiment.technology_ids:
        raise ExplorationError("experiment must target a capability and representative technology")
    if not 4 <= float(experiment.effort_hours) <= 20:
        raise ExplorationError("experiment effort must be between 4 and 20 focused hours")
    steps = " ".join(experiment.learning_steps).lower()
    missing = [step for step in REQUIRED_LEARNING_STEPS if step not in steps]
    if missing:
        raise ExplorationError(f"experiment learning pipeline is missing: {', '.join(missing)}")
    if not experiment.artifact_or_measurement.strip():
        raise ExplorationError("experiment must name an artifact or measurement")
    if not experiment.competence_evidence:
        raise ExplorationError("experiment must name evidence of competence")
    missing_rules = [rule for rule in SELECTION_RULES if experiment.selection_rules.get(rule) is not True]
    if missing_rules:
        raise ExplorationError(f"experiment fails project-selection rules: {', '.join(missing_rules)}")


class DeterministicExplorationGenerator:
    """Generate explainable options without an LLM or hidden side effects."""

    def generate(self, investigation: Investigation, *, exploration_id: str | None = None, overlarge: bool = False) -> dict[str, Any]:
        riff = investigation.riff
        exploration_id = exploration_id or str(uuid.uuid4())
        capability = str(riff.get("underlying_capability") or "applied technical judgment")
        technologies = tuple(str(item) for item in (riff.get("associated_technologies") or []) if str(item).strip()) or ("Python",)
        thesis = str(riff.get("hypothesis") or riff.get("observation") or "Investigate the Riff thesis")
        why = str(riff.get("why_it_matters") or "Build evidence that informs a useful technical decision.")
        question = f"What evidence would show whether {thesis.rstrip('.')} is useful for {capability}?"
        signaling_gap = "signal" in str(riff.get("user_relevance", "")).lower() or "public" in str(riff.get("user_relevance", "")).lower()
        first_title = "Public capability artifact" if signaling_gap else "Working capability vertical slice"
        first_artifact = "A public, reproducible demo repository with a short architecture note and measured result." if signaling_gap else "A runnable vertical slice with a README, test, and measured result."
        options = [
            (first_title, f"Build a small end-to-end slice that makes {capability} visible and testable.", first_artifact, 10.0),
            ("Comparative measurement", f"Implement two materially different approaches and compare their trade-offs on a fixed fixture.", "A comparison table, benchmark output, and recommendation backed by the fixture.", 12.0),
            ("Failure-mode probe", f"Intentionally exercise a boundary case to inspect where the approach fails and what guardrail is needed.", "A failure fixture, diagnostic output, and a concise design decision describing the guardrail.", 8.0),
        ]
        experiments = []
        for index, (title, description, artifact, hours) in enumerate(options, start=1):
            rules: dict[str, Any] = {rule: True for rule in SELECTION_RULES}
            if overlarge and index == 1:
                rules["reduced_from_hours"] = 40
                description = description + " The original broad project is reduced to this valuable vertical slice."
            experiment = Experiment(
                experiment_id=f"{exploration_id}-exp-{index}",
                exploration_id=exploration_id,
                title=title,
                description=description,
                target_capability_id=capability,
                technology_ids=technologies,
                learning_steps=REQUIRED_LEARNING_STEPS,
                effort_hours=hours,
                effort_assumptions=("One focused session with a prepared fixture", "No production deployment or private data required"),
                artifact_or_measurement=artifact,
                competence_evidence=(f"Explain and defend a {capability} design", "Show reproducible implementation evidence"),
                selection_rules=rules,
            )
            validate_experiment(experiment)
            experiments.append(experiment)
        return {
            "exploration_id": exploration_id,
            "thesis": thesis,
            "why_it_matters": why,
            "what_i_want_to_understand": question,
            "capability_targets": (capability,),
            "technology_targets": technologies,
            "open_questions": ("Which trade-off matters most in practice?", "What evidence would change the recommendation?"),
            "possible_experiments": tuple(experiments),
            "estimated_effort": {"min_hours": 8, "max_hours": 12, "focused_hours": True},
            "evidence_of_competence": (f"Explain and defend a design for {capability}", "Show a reproducible artifact and measured trade-off"),
        }


class ExplorationRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _approval(self, conn, riff_id: str) -> tuple[str, ...]:
        rows = conn.execute("SELECT decision_id FROM riff_decisions WHERE riff_id = %s AND decision = 'APPROVE_EXPLORATION' AND actor_kind = 'USER' ORDER BY created_at", (riff_id,)).fetchall()
        if not rows:
            raise ExplorationError("an explicit user APPROVE_EXPLORATION decision is required")
        return tuple(str(row[0]) for row in rows)

    def create(self, riff_id: str, *, actor: str = "user", overlarge: bool = False) -> Exploration:
        with connection(self.database_url) as conn:
            approvals = self._approval(conn, riff_id)
            existing = conn.execute("SELECT exploration_id FROM explorations WHERE riff_id = %s", (riff_id,)).fetchone()
            if existing:
                return self.get(str(existing[0]))
        exploration_id = str(uuid.uuid4())
        generated = DeterministicExplorationGenerator().generate(DecisionRepository(self.database_url).investigation(riff_id), exploration_id=exploration_id, overlarge=overlarge)
        experiments: tuple[Experiment, ...] = generated["possible_experiments"]
        with connection(self.database_url) as conn:
            # Recheck under the write transaction for idempotence under concurrent requests.
            existing = conn.execute("SELECT exploration_id FROM explorations WHERE riff_id = %s", (riff_id,)).fetchone()
            if existing:
                return self.get(str(existing[0]))
            conn.execute("INSERT INTO explorations (exploration_id, riff_id, approval_decision_id, status, thesis, why_it_matters, what_i_want_to_understand, capability_targets, technology_targets, open_questions, estimated_effort, evidence_of_competence, version) VALUES (%s, %s, %s, 'DRAFT', %s, %s, %s, %s, %s, %s, %s, %s, 1)", (exploration_id, riff_id, approvals[-1], generated["thesis"], generated["why_it_matters"], generated["what_i_want_to_understand"], Jsonb(list(generated["capability_targets"])), Jsonb(list(generated["technology_targets"])), Jsonb(list(generated["open_questions"])), Jsonb(generated["estimated_effort"]), Jsonb(list(generated["evidence_of_competence"]))))
            for item in experiments:
                conn.execute("INSERT INTO exploration_experiments (experiment_id, exploration_id, title, description, target_capability_id, technology_ids, learning_steps, effort_hours, effort_assumptions, artifact_or_measurement, competence_evidence, selection_rules, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PROPOSED')", (item.experiment_id, exploration_id, item.title, item.description, item.target_capability_id, Jsonb(list(item.technology_ids)), Jsonb(list(item.learning_steps)), item.effort_hours, Jsonb(list(item.effort_assumptions)), item.artifact_or_measurement, Jsonb(list(item.competence_evidence)), Jsonb(item.selection_rules)))
            payload = self._payload(generated, experiments)
            conn.execute("INSERT INTO exploration_versions (version_id, exploration_id, version, actor, reason, payload) VALUES (%s, %s, 1, %s, %s, %s)", (str(uuid.uuid4()), exploration_id, actor, "created from approved Riff", Jsonb(payload)))
            conn.execute("INSERT INTO exploration_events (event_id, exploration_id, event_type, actor, reason, payload) VALUES (%s, %s, 'CREATED', %s, %s, %s)", (str(uuid.uuid4()), exploration_id, actor, "created from approved Riff", Jsonb(payload)))
        return self.get(exploration_id)

    def get(self, exploration_id: str) -> Exploration:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT exploration_id, riff_id, approval_decision_id, status, thesis, why_it_matters, what_i_want_to_understand, capability_targets, technology_targets, open_questions, estimated_effort, evidence_of_competence, version, selected_experiment_id FROM explorations WHERE exploration_id = %s", (exploration_id,)).fetchone()
            if row is None:
                raise ExplorationError("Exploration not found")
            exp_rows = conn.execute("SELECT experiment_id, exploration_id, title, description, target_capability_id, technology_ids, learning_steps, effort_hours, effort_assumptions, artifact_or_measurement, competence_evidence, selection_rules, status FROM exploration_experiments WHERE exploration_id = %s ORDER BY created_at, experiment_id", (exploration_id,)).fetchall()
            events = conn.execute("SELECT event_type, actor, reason, payload, created_at FROM exploration_events WHERE exploration_id = %s ORDER BY created_at", (exploration_id,)).fetchall()
        experiments = tuple(Experiment(str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]), tuple(_json(r[5])), tuple(_json(r[6])), float(r[7]), tuple(_json(r[8])), str(r[9]), tuple(_json(r[10])), dict(_json(r[11])), str(r[12])) for r in exp_rows)
        history = tuple({"event_type": str(r[0]), "actor": str(r[1]), "reason": str(r[2]), "payload": _json(r[3]), "created_at": r[4].isoformat()} for r in events)
        return Exploration(str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]), str(row[5]), str(row[6]), tuple(_json(row[7])), tuple(_json(row[8])), tuple(_json(row[9])), experiments, dict(_json(row[10])), tuple(_json(row[11])), int(row[12]), str(row[13]) if row[13] else None, history)

    def refine(self, exploration_id: str, experiment_id: str, reason: str, *, actor: str = "user", actor_kind: str = "USER") -> Exploration:
        if actor_kind != "USER" or not reason.strip():
            raise ExplorationError("refinement requires a user and a semantic reason")
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT version FROM explorations WHERE exploration_id = %s FOR UPDATE", (exploration_id,)).fetchone()
            original = conn.execute("SELECT experiment_id, title, description, target_capability_id, technology_ids, learning_steps, effort_hours, effort_assumptions, artifact_or_measurement, competence_evidence, selection_rules, status FROM exploration_experiments WHERE experiment_id = %s AND exploration_id = %s FOR UPDATE", (experiment_id, exploration_id)).fetchone()
            if row is None or original is None:
                raise ExplorationError("Exploration or experiment not found")
            if str(original[11]) == "REJECTED":
                raise ExplorationError("an already rejected experiment cannot be refined")
            new_id = f"{experiment_id}-refined-{uuid.uuid4().hex[:8]}"
            new_item = Experiment(new_id, exploration_id, f"Refined: {original[1]}", f"{original[2]} Revised after user feedback: {reason.strip()}", str(original[3]), tuple(_json(original[4])), tuple(_json(original[5])), float(original[6]), tuple(_json(original[7])), str(original[8]), tuple(_json(original[9])), dict(_json(original[10])))
            validate_experiment(new_item)
            conn.execute("UPDATE exploration_experiments SET status = 'REJECTED' WHERE experiment_id = %s", (experiment_id,))
            conn.execute("INSERT INTO exploration_experiments (experiment_id, exploration_id, title, description, target_capability_id, technology_ids, learning_steps, effort_hours, effort_assumptions, artifact_or_measurement, competence_evidence, selection_rules, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PROPOSED')", (new_id, exploration_id, new_item.title, new_item.description, new_item.target_capability_id, Jsonb(list(new_item.technology_ids)), Jsonb(list(new_item.learning_steps)), new_item.effort_hours, Jsonb(list(new_item.effort_assumptions)), new_item.artifact_or_measurement, Jsonb(list(new_item.competence_evidence)), Jsonb(new_item.selection_rules)))
            version = int(row[0]) + 1
            payload = {"rejected_experiment_id": experiment_id, "new_experiment_id": new_id, "reason": reason.strip()}
            conn.execute("UPDATE explorations SET status = 'REFINING', version = %s, updated_at = now() WHERE exploration_id = %s", (version, exploration_id))
            conn.execute("INSERT INTO exploration_versions (version_id, exploration_id, version, actor, reason, payload) VALUES (%s, %s, %s, %s, %s, %s)", (str(uuid.uuid4()), exploration_id, version, actor, reason.strip(), Jsonb(payload)))
            conn.execute("INSERT INTO exploration_events (event_id, exploration_id, event_type, actor, reason, payload) VALUES (%s, %s, 'EXPERIMENT_REJECTED', %s, %s, %s), (%s, %s, 'REFINED', %s, %s, %s)", (str(uuid.uuid4()), exploration_id, actor, reason.strip(), Jsonb(payload), str(uuid.uuid4()), exploration_id, actor, reason.strip(), Jsonb(payload)))
        return self.get(exploration_id)

    def select_experiment(self, exploration_id: str, experiment_id: str, *, actor: str = "user", actor_kind: str = "USER") -> Exploration:
        if actor_kind != "USER":
            raise ExplorationError("only the user can select an experiment")
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT version FROM explorations WHERE exploration_id = %s FOR UPDATE", (exploration_id,)).fetchone()
            item = conn.execute("SELECT status FROM exploration_experiments WHERE experiment_id = %s AND exploration_id = %s FOR UPDATE", (experiment_id, exploration_id)).fetchone()
            if row is None or item is None:
                raise ExplorationError("Exploration or experiment not found")
            if str(item[0]) == "REJECTED":
                raise ExplorationError("a rejected experiment cannot be selected")
            conn.execute("UPDATE exploration_experiments SET status = CASE WHEN experiment_id = %s THEN 'SELECTED' ELSE status END WHERE exploration_id = %s", (experiment_id, exploration_id))
            version = int(row[0]) + 1
            payload = {"experiment_id": experiment_id}
            conn.execute("UPDATE explorations SET status = 'SELECTED', selected_experiment_id = %s, version = %s, updated_at = now() WHERE exploration_id = %s", (experiment_id, version, exploration_id))
            conn.execute("INSERT INTO exploration_versions (version_id, exploration_id, version, actor, reason, payload) VALUES (%s, %s, %s, %s, 'selected experiment', %s)", (str(uuid.uuid4()), exploration_id, version, actor, Jsonb(payload)))
            conn.execute("INSERT INTO exploration_events (event_id, exploration_id, event_type, actor, reason, payload) VALUES (%s, %s, 'EXPERIMENT_SELECTED', %s, 'selected experiment', %s)", (str(uuid.uuid4()), exploration_id, actor, Jsonb(payload)))
        return self.get(exploration_id)

    @staticmethod
    def _payload(generated: Mapping[str, Any], experiments: tuple[Experiment, ...]) -> dict[str, Any]:
        payload = dict(generated)
        payload["possible_experiments"] = [asdict(item) for item in experiments]
        return _jsonable(payload)


def _json(value: Any) -> Any:
    if isinstance(value, (bytes, str)):
        return json.loads(value.decode() if isinstance(value, bytes) else value)
    return value if value is not None else []


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
