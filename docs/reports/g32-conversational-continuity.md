# G32 conversational continuity verification

## Delivered

The provider-neutral conversational loop now supports disposable session
handles, multi-turn message history, natural-language result rendering, and
safe reference resolution. Labels such as “the top Riff” and “candidate 1” are
bound only to results observed in the current bounded session. Raw IDs remain
in the audit trace but are omitted from model-facing tool results.

## Behavioral evidence

- Two-turn scripted flow: read the daily result, then investigate “the top
  Riff”; the adapter receives the canonical ID while the model context contains
  only the natural label.
- Ambiguous labels return `AMBIGUOUS_REFERENCE` with bounded choices and do not
  invoke the adapter.
- Unbound natural labels return `STALE_REFERENCE`; explicit stable IDs remain
  accepted for backwards compatibility and restart recovery.
- Confirmation-gated mutations still require the outer
  `USER_CONFIRMED` boundary; model-supplied tokens are ignored.
- Rendered results omit IDs, token-like fields, and private-profile payloads,
  while retaining citations and uncertainty fields.
- Missing daily dates return a dated latest-result summary without UUIDs or
  fabricated rank claims; bounded references such as “the top Riff” resolve to
  the newest published result for follow-up inspection.
- `alternate_riffs` excludes the current/rejected Riff and returns other
  bounded recommendations; `map_riff_to_scenario` provides a read-only,
  uncertainty-aware fit assessment for a concrete workflow scenario.

## Verification

`tests/test_chat_loop.py` covers multi-turn handles, ambiguity, restart
rebinding, privacy rendering, and confirmation. `tests/test_adapter.py` covers
the missing-date/latest-context fallback and natural “top Riff” resolution
against Postgres, in addition to persisted canonical state, restart, and
lifecycle approval behavior. The user confirmed the updated conversational
flow is an improvement over the rougher relay-style experience; follow-ups
feel solid, and alternate recommendations plus scenario mapping support the
next iteration without exposing internal IDs.

The user's qualitative feedback is favorable for follow-ups: once a Riff is
available, natural references and iterative investigation feel solid. The
updated missing-current-day response now presents dated fallback context and
next actions without exposing IDs, and the user confirmed the overall flow is
an improvement.

## Routed finding

The shared Postgres integration fixture clears daily rows and seeds only its
fixed date (`2026-09-14`). Running it against the operator database can leave
no current-day result. This is separate from handle resolution and is routed
to G35: fixture tests must use an isolated database or origin/owner-scoped
cleanup so they cannot overwrite operator dogfood state.
