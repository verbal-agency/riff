# G28 opportunity-context and execution-riffing evaluation

## Mechanical verification

- Perplexity Computer fixture extraction preserves actors, workflow, data,
  connectors, permissions, approvals, security boundaries, success measures,
  and explicit unknowns.
- Candidate generation returns three materially different bounded candidates.
- Named riff operations produce parent-linked variants with deterministic IDs
  and comparison scores.
- MCP and connector catalogs expose bounded context/candidate operations; the
  selection operation is confirmation-gated and does not create an
  Exploration or PRD.

Automated evidence:

- `tests/test_opportunities.py`
- `tests/test_chat_loop.py`
- `tests/test_mcp_server.py`
- `tests/test_connector.py`

## Persistence verification

The additive `020_opportunity_context` migration applied successfully. The
focused Postgres test persists a context, generated candidates, a transformed
variant, and a user selection, then removes only its uniquely generated test
opportunity row.

## Human evaluation

The user selected a combined direction after comparing the initial candidates
and riffed variants: use one representative Riff workflow as the motivating
workload, while implementing and comparing three downstream memory strategies
(event-sourced ledger/replay, hierarchical memory, and content-addressed delta
checkpoints). This was judged more distinctive and personally meaningful than a
generic durable-workflow demo, without turning Riff into a literal job
application or prematurely adding a generic memory subsystem.

The comparison artifact is explicitly a separately scoped downstream project.
Account-aware evidence of where agents are actually used in the user's GitHub
projects remains routed to G33; the current local checkout only demonstrates
agent-adjacent tool-loop/MCP and durable-pipeline infrastructure.
