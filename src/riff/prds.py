"""Learning PRD and agent-ready goal generation (G12)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from .db import connection
from .explorations import Exploration, ExplorationError, ExplorationRepository, Experiment


class PrdError(ValueError):
    """An invalid PRD approval, project, goal, or dependency graph."""


PRD_SECTIONS = (
    "thesis", "capability_target", "technology_targets", "problem_user",
    "learning_objectives", "scope", "non_goals", "time_budget", "architecture",
    "technical_decisions", "failure_modes", "acceptance_criteria", "evaluation_plan",
    "milestones", "evidence_produced", "talk_track", "kill_criteria",
)
GOAL_FIELDS = ("outcome", "inputs", "deliverable", "dependencies", "non_goals", "acceptance_criteria", "verification_evidence")


@dataclass(frozen=True, slots=True)
class ProjectGoal:
    goal_id: str
    project_id: str
    ordinal: int
    title: str
    outcome: str
    inputs: tuple[str, ...]
    deliverable: str
    dependencies: tuple[str, ...]
    non_goals: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    verification_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    exploration_id: str
    approval_id: str
    status: str
    version: int
    useful_hours: float
    prd: dict[str, Any]
    goals: tuple[ProjectGoal, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


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


class DeterministicPrdGenerator:
    """Turn one selected experiment into a complete, inspectable project packet."""

    def generate(self, exploration: Exploration, experiment: Experiment | None = None, *, project_id: str | None = None) -> dict[str, Any]:
        experiment = experiment or next((item for item in exploration.possible_experiments if item.experiment_id == exploration.selected_experiment_id), None)
        if experiment is None:
            raise PrdError("a selected experiment is required before PRD generation")
        if experiment.status == "REJECTED":
            raise PrdError("a rejected experiment cannot become a PRD")
        project_id = project_id or str(uuid.uuid4())
        capability = ", ".join(exploration.capability_targets)
        technologies = list(experiment.technology_ids or exploration.technology_targets)
        artifact = experiment.artifact_or_measurement
        prd = {
            "thesis": exploration.thesis,
            "capability_target": capability,
            "technology_targets": technologies,
            "problem_user": f"A technically curious builder needs evidence about {capability}, using a bounded public or reproducible artifact rather than passive study.",
            "learning_objectives": [exploration.what_i_want_to_understand, *exploration.evidence_of_competence],
            "scope": [experiment.description, f"Use {', '.join(technologies)} in one focused vertical slice.", f"Produce: {artifact}"],
            "non_goals": ["Production deployment", "A generalized framework or polished product", "Private-data ingestion beyond the prepared fixture"],
            "time_budget": {"focused_hours": float(experiment.effort_hours), "assumptions": list(experiment.effort_assumptions), "bounded": True},
            "architecture": ["A small input/fixture boundary", "One implementation under test", "A measurement or inspection boundary", "A documented artifact and conclusion"],
            "technical_decisions": [f"Choose how {technologies[0]} supports {capability} without hiding the underlying capability.", "Choose a fixture and measurement that make trade-offs reproducible.", "Choose what to omit to preserve the time budget."],
            "failure_modes": ["Interrupted or malformed input", "A misleadingly good result on a narrow fixture", "A trade-off that makes the approach less useful than the baseline"],
            "acceptance_criteria": [f"The slice produces the named artifact or measurement: {artifact}", f"The implementation explains one capability trade-off for {capability} using {technologies[0]}", "A repeatable test or fixture demonstrates the result", "The final notes identify one failure mode and one next decision"],
            "evaluation_plan": ["Run the prepared fixture twice and compare stable outputs", "Inspect the implementation and record the key trade-off", "Use the artifact, measurement, and notes in a human review rubric"],
            "milestones": ["Fixture and smallest runnable slice", "Inspection and comparison", "Demonstration, evidence capture, and talk track"],
            "evidence_produced": list(experiment.competence_evidence) + [artifact],
            "talk_track": [f"Why is {capability} the capability rather than merely a {technologies[0]} feature?", "What did the measurement prove and fail to prove?", "What would you change with another focused session?"],
            "kill_criteria": ["The smallest useful slice cannot fit within the remaining focused hours", "The fixture cannot distinguish the approaches or produce defensible evidence", "The work has become wrapper familiarity with no capability-level learning"],
        }
        if exploration.target_project_id:
            prd["target_project_id"] = exploration.target_project_id
            prd["target_project_disposition"] = "EXTEND_EXISTING"
            prd["scope"].append(f"Extend the approved existing project {exploration.target_project_id} at a named seam; preserve a greenfield fallback if the seam fails.")
            prd["technical_decisions"].append("Measure whether extending the existing project produces more learning value than starting a separate project.")
        goals = (
            ProjectGoal(f"{project_id}-g1", project_id, 1, "Build the bounded capability slice", "A runnable smallest useful slice produces the planned artifact or measurement.", tuple(prd["scope"]), f"Runnable slice and focused fixture for {artifact}", (), ("Production deployment", "Unbounded feature expansion"), ("The fixture runs successfully and produces the named artifact.", "The implementation identifies the target capability separately from framework mechanics."), ("Automated fixture/test output", "A short implementation note")),
            ProjectGoal(f"{project_id}-g2", project_id, 2, "Inspect and compare the result", "The builder can explain a measured trade-off and a relevant failure mode.", (f"Goal {project_id}-g1 output",), "Comparison record with implementation inspection and failure probe", (f"{project_id}-g1",), ("New product features",), ("Two repeat runs produce comparable measurements.", "One failure mode is reproduced or bounded and its implication is recorded."), ("Comparison table or benchmark", "Failure fixture/output", "Architecture decision note")),
            ProjectGoal(f"{project_id}-g3", project_id, 3, "Demonstrate competence and decide next", "A clean-context reviewer can judge the artifact's usefulness and the capability gained.", (f"Goal {project_id}-g2 output",), "Stable evidence packet, talk track, and next-step or kill decision", (f"{project_id}-g2",), ("Automatic PR or publication", "Additional scope outside the selected experiment"), ("The artifact and measurement are linked to {capability}.", "The talk track answers what was learned, what remains uncertain, and whether to continue."), ("Exported PRD/goal packet", "Human review rubric", "Evidence-of-competence record")),
        )
        return {"project_id": project_id, "useful_hours": float(experiment.effort_hours), "prd": prd, "goals": goals, "source_experiment_id": experiment.experiment_id}


def validate_project(project: Project) -> None:
    if not 4 <= project.useful_hours <= 20:
        raise PrdError("useful project version must fit 4–20 focused hours")
    missing = [section for section in PRD_SECTIONS if not project.prd.get(section)]
    if missing:
        raise PrdError(f"PRD is missing required sections: {', '.join(missing)}")
    if not project.goals:
        raise PrdError("PRD must have at least one implementation goal")
    ids = {goal.goal_id for goal in project.goals}
    for goal in project.goals:
        if not all(_text(getattr(goal, field)) for field in ("outcome", "deliverable")):
            raise PrdError(f"goal {goal.goal_id} has empty required content")
        if not goal.inputs or not goal.acceptance_criteria or not goal.verification_evidence:
            raise PrdError(f"goal {goal.goal_id} is missing required contract fields")
        for dependency in goal.dependencies:
            if dependency not in ids or dependency == goal.goal_id:
                raise PrdError(f"goal {goal.goal_id} has an invalid dependency")
        for criterion in goal.acceptance_criteria:
            if "works well" in criterion.lower() and not any(word in criterion.lower() for word in ("rubric", "evaluator", "measure")):
                raise PrdError(f"vague acceptance criterion in {goal.goal_id}")
    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {goal.goal_id: goal for goal in project.goals}

    def visit(goal_id: str) -> None:
        if goal_id in visiting:
            raise PrdError("goal dependency graph contains a cycle")
        if goal_id in visited:
            return
        visiting.add(goal_id)
        for dependency in by_id[goal_id].dependencies:
            visit(dependency)
        visiting.remove(goal_id)
        visited.add(goal_id)

    for goal_id in ids:
        visit(goal_id)


class ProjectRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def approve_prd(self, exploration_id: str, reason: str, *, actor: str = "user", actor_kind: str = "USER") -> str:
        if actor_kind != "USER" or not _text(reason):
            raise PrdError("PRD approval requires an explicit user and reason")
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT selected_experiment_id FROM explorations WHERE exploration_id = %s", (exploration_id,)).fetchone()
            if row is None:
                raise PrdError("Exploration not found")
            if not row[0]:
                raise PrdError("an experiment must be selected before PRD approval")
            approval_id = str(uuid.uuid4())
            conn.execute("INSERT INTO prd_approvals (approval_id, exploration_id, actor, actor_kind, reason) VALUES (%s, %s, %s, %s, %s)", (approval_id, exploration_id, actor, actor_kind, reason.strip()))
        return approval_id

    def generate(self, exploration_id: str, *, actor: str = "generator") -> Project:
        with connection(self.database_url) as conn:
            approval = conn.execute("SELECT approval_id FROM prd_approvals WHERE exploration_id = %s AND actor_kind = 'USER' ORDER BY created_at DESC LIMIT 1", (exploration_id,)).fetchone()
            if approval is None:
                raise PrdError("a distinct explicit user PRD approval is required")
            existing = conn.execute("SELECT project_id FROM projects WHERE exploration_id = %s", (exploration_id,)).fetchone()
            if existing:
                return self.get(str(existing[0]))
        exploration = ExplorationRepository(self.database_url).get(exploration_id)
        generated = DeterministicPrdGenerator().generate(exploration)
        project_id = str(generated["project_id"])
        goals: tuple[ProjectGoal, ...] = generated["goals"]
        project = Project(project_id, exploration_id, str(approval[0]), "READY", 1, generated["useful_hours"], generated["prd"], goals)
        validate_project(project)
        with connection(self.database_url) as conn:
            existing = conn.execute("SELECT project_id FROM projects WHERE exploration_id = %s", (exploration_id,)).fetchone()
            if existing:
                return self.get(str(existing[0]))
            conn.execute("INSERT INTO projects (project_id, exploration_id, approval_id, status, version, useful_hours, prd) VALUES (%s, %s, %s, 'READY', 1, %s, %s)", (project_id, exploration_id, str(approval[0]), project.useful_hours, Jsonb(_jsonable(project.prd))))
            for goal in goals:
                conn.execute("INSERT INTO project_goals (goal_id, project_id, ordinal, title, outcome, inputs, deliverable, dependencies, non_goals, acceptance_criteria, verification_evidence) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (goal.goal_id, project_id, goal.ordinal, goal.title, goal.outcome, Jsonb(list(goal.inputs)), goal.deliverable, Jsonb(list(goal.dependencies)), Jsonb(list(goal.non_goals)), Jsonb(list(goal.acceptance_criteria)), Jsonb(list(goal.verification_evidence))))
            payload = _jsonable({"prd": project.prd, "goals": [asdict(goal) for goal in goals]})
            conn.execute("INSERT INTO project_versions (version_id, project_id, version, actor, reason, payload) VALUES (%s, %s, 1, %s, 'generated from approved Exploration', %s)", (str(uuid.uuid4()), project_id, actor, Jsonb(payload)))
        return self.get(project_id)

    def get(self, project_id: str) -> Project:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT project_id, exploration_id, approval_id, status, version, useful_hours, prd FROM projects WHERE project_id = %s", (project_id,)).fetchone()
            if row is None:
                raise PrdError("project not found")
            goals = conn.execute("SELECT goal_id, project_id, ordinal, title, outcome, inputs, deliverable, dependencies, non_goals, acceptance_criteria, verification_evidence FROM project_goals WHERE project_id = %s ORDER BY ordinal", (project_id,)).fetchall()
        parsed_goals = tuple(ProjectGoal(str(g[0]), str(g[1]), int(g[2]), str(g[3]), str(g[4]), tuple(_json(g[5])), str(g[6]), tuple(_json(g[7])), tuple(_json(g[8])), tuple(_json(g[9])), tuple(_json(g[10]))) for g in goals)
        return Project(str(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]), float(row[5]), dict(_json(row[6])), parsed_goals)

    def export_markdown(self, project_id: str) -> str:
        project = self.get(project_id)
        lines = [f"# Riff Project {project.project_id}", "", f"- Source Exploration: `{project.exploration_id}`", f"- PRD approval: `{project.approval_id}`", f"- Useful focused hours: {project.useful_hours:g}"]
        if project.prd.get("target_project_id"):
            lines.append(f"- Target existing project: `{project.prd['target_project_id']}`")
        lines.append("")
        labels = {key: key.replace("_", " ").title() for key in PRD_SECTIONS}
        for section in PRD_SECTIONS:
            lines.extend([f"## {labels[section]}", ""])
            value = project.prd[section]
            if isinstance(value, list):
                lines.extend(f"- {item}" for item in value)
            elif isinstance(value, dict):
                lines.extend(f"- {key.replace('_', ' ').title()}: {item}" for key, item in value.items())
            else:
                lines.append(str(value))
            lines.append("")
        lines.append("## Implementation Goals\n")
        for goal in project.goals:
            lines.extend([f"### Goal {goal.ordinal}: {goal.title}", "", f"**Outcome:** {goal.outcome}", "", f"**Inputs:** {', '.join(goal.inputs)}", "", f"**Deliverable:** {goal.deliverable}", "", f"**Dependencies:** {', '.join(goal.dependencies) or 'None'}", "", "**Non-goals:**", *[f"- {item}" for item in goal.non_goals], "", "**Acceptance criteria:**", *[f"- {item}" for item in goal.acceptance_criteria], "", "**Verification evidence:**", *[f"- {item}" for item in goal.verification_evidence], ""])
        return "\n".join(lines).rstrip() + "\n"

    def regenerate(self, project_id: str, *, actor: str = "user", reason: str = "regenerated") -> Project:
        project = self.get(project_id)
        exploration = ExplorationRepository(self.database_url).get(project.exploration_id)
        generated = DeterministicPrdGenerator().generate(exploration, project_id=project.project_id)
        goals: tuple[ProjectGoal, ...] = generated["goals"]
        updated = Project(project.project_id, project.exploration_id, project.approval_id, "READY", project.version + 1, generated["useful_hours"], generated["prd"], goals)
        validate_project(updated)
        with connection(self.database_url) as conn:
            conn.execute("UPDATE projects SET version = %s, useful_hours = %s, prd = %s, updated_at = now() WHERE project_id = %s", (updated.version, updated.useful_hours, Jsonb(_jsonable(updated.prd)), project_id))
            conn.execute("DELETE FROM project_goals WHERE project_id = %s", (project_id,))
            for goal in goals:
                conn.execute("INSERT INTO project_goals (goal_id, project_id, ordinal, title, outcome, inputs, deliverable, dependencies, non_goals, acceptance_criteria, verification_evidence) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (goal.goal_id, project_id, goal.ordinal, goal.title, goal.outcome, Jsonb(list(goal.inputs)), goal.deliverable, Jsonb(list(goal.dependencies)), Jsonb(list(goal.non_goals)), Jsonb(list(goal.acceptance_criteria)), Jsonb(list(goal.verification_evidence))))
            conn.execute("INSERT INTO project_versions (version_id, project_id, version, actor, reason, payload) VALUES (%s, %s, %s, %s, %s, %s)", (str(uuid.uuid4()), project_id, updated.version, actor, reason, Jsonb(_jsonable({"prd": updated.prd, "goals": [asdict(goal) for goal in goals]}))))
        return self.get(project_id)
