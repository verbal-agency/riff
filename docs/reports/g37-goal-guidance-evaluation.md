# G37 goal-aware guidance evaluation

Status: PENDING_OPERATOR_REVIEW

The scripted comparison is implemented by `tests/test_project_goals.py` and the
goal guidance MCP/CLI surfaces. It uses the same bounded delta and evidence
inputs for a goal-aware result and a G36 baseline, then checks action count,
citations, effort bounds, and uncertainty disclosure.

The human dogfood comparison is intentionally not claimed complete by the
automated suite. During the next connected session, compare one selected
project goal against the G36 profile-only baseline and record whether the
result is more relevant, actionable, distinctive, and honest. If it is not,
route the specific failure as a follow-up instead of changing policy silently.
