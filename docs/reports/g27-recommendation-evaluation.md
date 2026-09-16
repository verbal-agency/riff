# G27 project-aware recommendation evaluation

## Mechanical evaluation

The recorded fixture compares a durable-agent-execution Riff with two bounded
project snapshots. The matcher selects the active runtime project because its
capability/technology evidence and observed checkpoint-replay seam align with
the Riff. It preserves a `START_NEW` alternative and returns `NOT_NOW` when
the signal has no cited receipt. Scores, citations, uncertainty, and
recommendation IDs are stable across identical runs.

Automated evidence:

- `tests/test_recommendations.py::test_matching_is_deterministic_and_preserves_greenfield_alternative`
- `tests/test_recommendations.py::test_insufficient_evidence_is_not_now_and_has_no_project_target`
- `tests/test_recommendations.py::test_scripted_chat_surface_returns_bounded_project_match`
- `tests/test_recommendations.py::test_persisted_match_and_targeted_exploration_prd`
- `tests/test_recommendations.py::test_recommendation_override_preserves_original_and_is_confirmation_gated`

## Human evaluation

Protocol correctness is automated. A human usefulness judgment remains
intentionally separate: compare one project-aware recommendation and one
new-project-only recommendation for the same Riff, then record which is more
grounded, more useful, and less likely to overfit repository metadata. The
reviewer should also assess whether the proposed seam is concrete enough to
start an Exploration and whether the greenfield fallback is credible.

Status: **PENDING USER REVIEW**. This is the only G27 acceptance item that
cannot be established from offline or Postgres tests alone.

## Local dogfood run

The read-only adapter path was exercised against the current local Postgres
database for the persisted durable-agent-execution Riff. It returned a 0.87
fit / 0.95 learning-value extension recommendation for an observed
checkpoint-replay seam, cited the Riff receipt and project evidence, and kept a
12-hour `START_NEW` alternative. An earlier explicit override was also
correctly shown as `effective_disposition=START_NEW` while preserving the
original `EXTEND_EXISTING` recommendation.

The shared development database currently contains several synthetic project
fixtures from integration tests. That makes the result useful for validating
the boundary, but not yet a clean human usefulness comparison; the cleanup
need is tracked as `BL-G27-001` in the backlog.
