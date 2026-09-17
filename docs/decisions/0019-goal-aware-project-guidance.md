# Decision 0019 — Make project goals first-class

G37 stores explicit project-goal projections separately from GitHub repositories,
files, immutable evidence, and project snapshots. Extraction is deterministic
and bounded to explicit roadmap language. Goal wording/status changes create
linked versions; user prioritization, completion, archival, and correction are
append-only events requiring explicit confirmation.

Goal-aware guidance composes the selected goal with G36 deltas and narrow
profile/decision/opportunity context. It compares extension, greenfield,
investigation, and wait-for-evidence paths while retaining uncertainty for
synthetic or insufficient evidence. Natural repository references use
`owner/name`, canonical URL, or unique display name, so a filename cannot be a
repository selector.
