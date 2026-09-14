# Riff v0.1 — Product Requirements Document

## 1. Product Summary

**Riff** is a personal capability-intelligence system for discovering emerging ideas, skills, technologies, and engineering patterns that are becoming valuable in applied AI.

Riff continuously gathers evidence from the AI job market, GitHub, and technical writing. It looks for changes that are:

- relevant to the user's career direction,
- not already obvious to the user,
- supported by multiple independent forms of evidence,
- concrete enough to investigate,
- and potentially valuable enough to justify learning or building something.

Riff does not simply recommend skills.

It constructs **arguments** about why a capability may matter, compares that capability against the user's existing experience, exposes the evidence and counterarguments, and allows the user to reason about the idea conversationally.

If the user decides that a Riff is worth pursuing, Riff helps transform it into:

**Riff → Exploration → PRD → executable goals → completed artifact → new capability evidence**

ChatGPT is the initial conversational interface. Riff itself is the persistent system of record, research engine, evidence store, capability model, and signal-detection system.

---

# 2. Product Thesis

Career-development tools usually start with known requirements:

> You need skill X for job Y.

Riff starts earlier:

> What appears to be becoming important that you may not yet know you should care about?

The system should identify weak but meaningful signals before they become obvious résumé keywords.

Riff should be especially good at distinguishing between:

- framework adoption and underlying engineering capability,
- hype and independent adoption,
- something the user does not understand and something the user merely cannot publicly demonstrate,
- interesting developments and developments worth spending time on,
- learning a technology and developing the deeper capability the technology represents.

Riff should optimize for **useful intellectual exploration followed by action**, not content consumption.

---

# 3. Primary User

Riff v0.1 has exactly one user.

The user's primary goal is to remain competitive for high-end applied AI, AI systems, agent engineering, FDE, and adjacent technical roles by continuously developing valuable capabilities and producing evidence of those capabilities.

The system should assume the user:

- already possesses substantial professional AI experience,
- has both public and private/client experience,
- does not want generic learning recommendations,
- prefers building to passive studying,
- needs enough implementation-specific fluency to discuss real technologies,
- benefits from reasoning collaboratively rather than accepting generated recommendations uncritically,
- and should generally be biased toward applying and building rather than endless preparation.

---

# 4. Core User Outcome

When the user opens ChatGPT and asks:

> What are today's Riffs?

Riff should return up to three genuinely worthwhile developments.

A strong Riff answers:

1. **What appears to be changing?**
2. **Why might it matter?**
3. **What evidence supports that claim?**
4. **What evidence argues against it?**
5. **Why is it relevant specifically to this user?**
6. **What underlying capability does it represent?**
7. **What concrete technologies are associated with it?**
8. **Does the user already understand or demonstrate it?**
9. **What would be worth exploring?**

It is acceptable—and desirable—for Riff to return:

> No sufficiently strong new Riffs today.

Riff must never manufacture novelty to satisfy a daily quota.

---

# 5. North-Star Success Criterion

Riff succeeds when:

> **It causes the user to investigate or build something valuable that the user probably would not otherwise have discovered or pursued.**

Supporting indicators include:

- Riffs judged genuinely novel by the user,
- Riffs that change the user's prior belief,
- Riffs promoted into Explorations,
- Explorations converted into PRDs,
- resulting projects completed,
- completed projects producing meaningful new capability evidence,
- Riff identifying signaling gaps rather than incorrectly prescribing additional study.

Engagement, number of generated Riffs, token volume, and time spent inside the system are not success metrics.

---

# 6. Core Product Loop

```text
External evidence
      ↓
Evidence receipts
      ↓
Capability normalization
      ↓
Candidate signals
      ↓
Ranking + novelty filtering
      ↓
Deep argument construction
      ↓
RIFF
      ↓
Human discussion
      ↓
Reject / Watch / Explore
      ↓
EXPLORATION
      ↓
Human selection of experiment
      ↓
PRD
      ↓
Executable goals
      ↓
Completed artifact
      ↓
Updated capability evidence
```

---

# 7. Evidence Sources

## 7.1 Job Market

Job postings answer:

> What capabilities are organizations increasingly willing to pay for?

Riff should extract:

- company,
- role,
- seniority,
- compensation where available,
- responsibilities,
- explicit technologies,
- implicit capabilities,
- relevant architectural patterns,
- date observed,
- canonical posting URL.

Individual listings are evidence, not conclusions.

Repeated listings from the same company should be heavily correlated rather than treated as independent confirmation.

---

## 7.2 GitHub

GitHub answers:

> What are builders actually putting effort into?

Signals may include:

- new repositories,
- repository growth,
- releases,
- recurring abstractions,
- implementation patterns,
- dependency adoption,
- issue themes,
- discussions,
- README changes,
- release notes,
- contributor activity.

Popularity metrics such as stars should be considered weak evidence in isolation.

Particularly valuable signals occur when multiple unrelated projects independently implement similar capabilities using different technologies.

Example:

```text
Repo A → Temporal
Repo B → custom checkpointing
Repo C → LangGraph persistence
Repo D → event-driven replay
```

may strengthen the capability:

> durable agent execution

rather than four separate technology trends.

---

## 7.3 Technical Writing

Technical writing answers:

> What are practitioners arguing matters, and why?

Initial sources may include:

- engineering blogs,
- individual technical blogs,
- Substack,
- research-lab writing,
- selected newsletters,
- papers when discovered through those sources,
- original technical material surfaced through Hacker News.

Technical-writing sources should begin as a manually curated list.

Riff should later maintain source-quality statistics based on whether a source repeatedly contributes to Riffs the user finds valuable.

---

## 7.4 Discovery Sources

Hacker News may be used as a **discovery mechanism**, but should generally point Riff toward an original source.

Example:

```text
HN discussion
   ↓
interesting repository
   ↓
GitHub evidence receipt
```

Riff should prefer the underlying repository, paper, article, or primary source over discussion popularity.

---

# 8. Evidence Ingestion Strategy

Daily operation must be token-efficient.

Riff should use a funnel rather than repeatedly running deep reasoning over all available material.

## Stage 1 — Incremental Collection

Fetch only newly available evidence since the prior cursor/checkpoint.

Store raw evidence once.

Each item receives:

- ID
- canonical URL
- source
- source type
- author
- organization
- published date
- retrieval date
- content hash
- raw content or snapshot location

Duplicate material should be collapsed using canonical URLs, hashes, and semantic similarity where appropriate.

---

## Stage 2 — Evidence Compression

Each new source is processed once into an **Evidence Receipt**.

Example:

```text
EvidenceReceipt

id
source_type
author
organization
published_at

summary
relevant_spans[]

capability_candidates[]
technology_candidates[]

claims[]
signal_strength

content_hash
extractor_version
```

Typical summaries should remain compact.

Subsequent reasoning should operate primarily on Evidence Receipts rather than repeatedly providing full source material to models.

Raw evidence should remain retrievable for deeper investigation.

---

## Stage 3 — Capability Mapping

Candidate capabilities are mapped against the existing capability graph.

Example:

```text
"workflow replay"
"checkpoint recovery"
"resumable agents"
"durable workflows"
```

may map toward:

```text
durable agent execution
```

Potential matches should be probabilistic and reversible.

The system must avoid aggressively merging adjacent but meaningfully distinct capabilities.

---

## Stage 4 — Candidate Signal Ranking

Most ranking should use inexpensive code and stored metadata.

Candidate features may include:

- recency,
- frequency change,
- independent-source count,
- source-type diversity,
- company diversity,
- author diversity,
- capability novelty,
- relevance to user goals,
- current user proficiency,
- prior user decisions,
- repetition penalties,
- evidence quality.

Only the strongest candidate signals proceed to expensive reasoning.

---

## Stage 5 — Deep Reasoning

Approximately the strongest five candidates may receive deeper model analysis.

The reasoning stage constructs:

- argument for significance,
- argument against significance,
- interpretation of trajectory,
- relevance to the user,
- relationship to known technologies,
- potential learning/build implications.

The system then selects at most three Riffs.

---

# 9. The Riff Object

A Riff is an evidence-backed hypothesis worthy of discussion.

Suggested schema:

```text
Riff

id
created_at

title
claim

why_now
why_it_matters

capability_ids[]
technology_ids[]

supporting_evidence_ids[]
counterevidence_ids[]

source_diversity_score
novelty_score
relevance_score
confidence

user_gap_type
recommended_action

falsification_conditions[]

status
```

Possible `user_gap_type` values:

```text
KNOWLEDGE_GAP
IMPLEMENTATION_GAP
SIGNALING_GAP
EXPERIENCE_GAP
NO_MEANINGFUL_GAP
UNKNOWN
```

Possible statuses:

```text
NEW
WATCHING
REJECTED
EXPLORING
ARCHIVED
```

---

# 10. Riff Presentation

A normal Riff shown to the user should look approximately like:

## Durable agent recovery may be becoming a separate engineering discipline

**Claim**

Production agent systems increasingly need explicit recovery mechanisms for cases where model state, workflow state, and external-world state diverge.

**Why now**

Independent projects and employers are increasingly describing recovery, resumability, reconciliation, and checkpointing as first-class concerns.

**Evidence**

- independent hiring evidence
- GitHub implementation evidence
- practitioner writing

**Why this might be wrong**

These may simply be established distributed-systems concepts being repackaged around agents.

**Why this matters to you**

You appear to understand deterministic agent boundaries and state handling, but have weak public evidence around durable execution.

**Underlying capability**

Durable agent execution.

**Concrete technologies**

Temporal, LangGraph checkpointing, event sourcing, workflow engines.

**Recommendation**

Explore rather than study directly.

---

# 11. Capability Model

Capabilities are framework-independent abilities.

Examples:

```text
durable agent execution
agent authorization
evaluation design
tool interface design
context engineering
production inference optimization
human-in-the-loop workflow design
agent observability
```

Technologies are separately associated with capabilities.

Example:

```text
Capability:
durable agent execution

Concepts:
- idempotency
- recovery
- checkpoints
- reconciliation
- compensation

Technologies:
- Temporal
- LangGraph
- Durable Functions
- custom event-driven runtimes
```

Riff should prioritize developing capabilities while also ensuring practical fluency with representative technologies.

---

# 12. Learning Pipeline

Riff must prevent framework-independent abstraction from becoming an excuse to avoid learning concrete implementations.

Each capability may contain:

```text
Capability
    ↓
Concepts
    ↓
Patterns
    ↓
Representative technologies
    ↓
Hands-on implementation
    ↓
Demonstrable artifact
    ↓
Interview/conversation fluency
```

A learning recommendation should explicitly identify:

### Understand

What concepts the user should be able to explain.

### Implement

What mechanism the user should personally build.

### Inspect

Which real technology or framework implementation the user should understand.

### Compare

What tradeoffs the user should be able to discuss.

### Demonstrate

What artifact provides evidence of competency.

---

# 13. User Capability Profile

The user's capability profile must not be inferred solely from GitHub.

Riff should support four evidence sources.

## Public GitHub Evidence

Repos, code, READMEs, experiments, contribution history.

## Public Website Evidence

Portfolio descriptions, articles, public project documentation.

## Private Experience Ledger

The user can explicitly describe professional/client experience that cannot be exposed publicly.

Example:

```text
ExperienceEvidence

capability_id
context_type: CLIENT_WORK

description:
"Designed deterministic callback behavior around
agent execution for enterprise conversational systems."

confidence:
USER_ATTESTED

public:
false
```

## Riff-Generated Evidence

Completed Riff projects should automatically become candidate capability evidence.

---

# 14. Capability Evidence Levels

Riff should distinguish:

```text
PUBLICLY_DEMONSTRATED
PROFESSIONALLY_DEMONSTRATED_PRIVATE
HANDS_ON_PERSONAL
STUDIED
CONCEPTUALLY_FAMILIAR
UNKNOWN
```

The same capability may have multiple evidence types.

Riff should explicitly recognize **signaling gaps**.

Example:

> You likely already possess this capability professionally. The gap is that employers cannot observe it through your public work.

The recommended intervention should therefore be a demonstrative artifact rather than additional study.

---

# 15. Conversation and Human Authority

Riff should recommend actions but never independently promote a Riff into an Exploration or PRD.

The user must explicitly approve:

```text
RIFF → EXPLORATION
```

and:

```text
EXPLORATION → PRD
```

Riff may recommend both transitions.

ChatGPT acts as the initial deliberation interface.

Typical interactions include:

```text
Why do you think this matters?

Isn't this just Temporal again?

Show me the strongest evidence.

Push back on your own conclusion.

Have I already demonstrated this?

Which companies appear to care most about it?

What would make this worth learning?

What could I build?

That idea is boring. Give me stranger options.

Save option three as an exploration.

Turn this into a PRD.
```

---

# 16. Decision Memory

Riff must remember not only the user's decision, but the reasoning behind it.

Do not store:

```text
rejected = true
```

Store:

```text
Decision

riff_id
decision: REJECTED

reason:
"This appears to be vendor churn around an existing
distributed-systems problem."

implications:
- reduce importance of framework adoption
- preserve interest in underlying capability
- do not resurface unless evidence materially changes

created_at
```

Riff should use prior decisions when ranking future signals.

A rejected idea may be resurfaced only when:

- substantial new evidence appears,
- the underlying interpretation materially changes,
- or the user's capability/goals change.

When resurfacing, Riff should explain why:

> You previously rejected this because X. I am bringing it back because Y materially changed.

---

# 17. Exploration Object

Riff should not generate a PRD immediately.

An approved Riff becomes an **Exploration**.

Schema:

```text
Exploration

id
riff_id

thesis

why_it_matters
what_i_want_to_understand

capability_targets[]
technology_targets[]

open_questions[]

possible_experiments[]

estimated_effort

evidence_of_competence[]

status
```

The purpose of an Exploration is collaborative ideation.

The user and ChatGPT may riff on multiple possible experiments before selecting one.

---

# 18. Project Selection Rules

Riff-generated projects must satisfy:

### Useful

The project should solve or investigate something meaningful.

### Capability-driven

The project must clearly develop or demonstrate the capability that caused the Riff.

### Concrete

The user should build something, measure something, or prove something.

### Discussable

The resulting work should generate architectural and technical decisions worth discussing in an interview.

### Completable

A useful version must be completable within approximately:

**4–20 focused hours.**

Ideas exceeding that budget must be reduced to a valuable vertical slice.

### Portfolio-capable

When possible, the project should create public evidence.

Projects based on private professional gaps may instead create analogous public demonstrations.

---

# 19. PRD Generation Rules

An Exploration becomes a PRD only after explicit user approval.

A Riff PRD is a **learning-and-building PRD**, not merely a traditional product document.

Every PRD must contain:

## Thesis

What claim or question is being investigated?

## Capability Target

Which underlying capability should improve?

## Specific Technology Targets

Which frameworks/tools/implementations should the user understand well enough to discuss?

## Problem / User

What actual problem is being solved?

## Learning Objectives

What should the user understand by completion?

## Scope

What gets built?

## Non-Goals

What explicitly does not get built?

## Time Budget

Expected focused hours.

## Architecture

Expected high-level system structure.

## Technical Decisions

Important choices the user must personally reason about.

## Failure Modes

What should intentionally be tested or broken?

## Acceptance Criteria

What objectively constitutes completion?

## Evaluation Plan

How does the project prove what it claims?

## Milestones

Logical implementation stages.

## Evidence Produced

What becomes portfolio/profile evidence?

## Talk Track

Questions the user should be capable of answering afterward.

## Kill Criteria

Conditions under which the project should be abandoned, reduced, or reframed.

---

# 20. Goal Decomposition

Each approved PRD should terminate in agent-ready goals.

Example:

```text
Goal 1: Implement persistent execution state

Outcome:
A workflow survives process termination.

Inputs:
Defined workflow and persistence interface.

Deliverable:
Working persistence layer and test harness.

Dependencies:
None.

Acceptance criteria:
Workflow resumes from the most recent valid checkpoint
without repeating completed side effects.
```

Goals should specify **outcomes and acceptance criteria**, not prescribe detailed implementation steps unnecessarily.

A downstream coding agent may further decompose the goals.

The authority hierarchy is:

```text
User
chooses what is worth building

Riff
defines what success means

Implementation agent
determines how to implement it
```

---

# 21. Provenance Requirements

Riff should maintain unusually strong provenance.

Every evidence-backed claim must reference evidence IDs.

Example:

```text
Claim:
"Agent authorization is becoming a separate concern
from tool connectivity."

Supports:
E102
E144
E178

Counterevidence:
E151
```

Riff should explicitly distinguish:

### Observation

> Four companies mention delegated authorization.

### Hypothesis

> Agent authorization is becoming a distinct applied-AI capability.

### Recommendation

> The user should investigate delegated agent authority.

Recommendations must never be presented as direct factual implications of observations.

---

# 22. Evidence Independence

Evidence count alone is not meaningful.

Riff should estimate independence across:

- organizations,
- repositories,
- authors,
- source types,
- root information sources.

Example:

```text
20 job listings from one company
```

should not count as 20 independent confirmations.

A stronger signal might contain:

```text
3 unrelated employers
2 independent GitHub projects
2 unrelated technical writers
```

Riff should normally require evidence from at least **two different source types** before describing something as an emerging trend.

Otherwise it may surface the item as:

> Interesting observation; insufficient evidence to call this a trend.

---

# 23. Counterargument Requirement

Every published Riff must contain:

- strongest supporting argument,
- strongest counterargument,
- plausible alternative explanation,
- falsification conditions.

Example:

```text
Alternative explanation:
The apparent rise in durable-agent infrastructure reflects
existing workflow-engine vendors repositioning established
technology rather than a genuinely new engineering need.

Would weaken this Riff:
If independent agent teams stop building custom recovery
mechanisms and adoption remains confined to incumbent
workflow vendors.
```

---

# 24. Evaluation Framework

## 24.1 Extraction Evals

Create a hand-labeled fixture set containing job descriptions, repository material, and technical writing.

Evaluate extraction of:

- capabilities,
- technologies,
- companies,
- claims,
- evidence spans,
- source metadata.

---

## 24.2 Capability Normalization Evals

Test correct grouping:

```text
checkpoint/replay
workflow recovery
resumable agents
```

Potentially:

```text
durable agent execution
```

Also test over-merging.

Example:

```text
agent memory
workflow persistence
```

must not automatically become the same capability.

---

## 24.3 Signal Evals

Create adversarial fixtures.

### Correlated Hype

Forty reposts of one announcement must not create forty confirmations.

### Single-Company Hiring Burst

Twenty postings from one employer must not create a market-wide conclusion.

### Established Technology

High current volume should not automatically imply novelty.

### Buzzword Fragmentation

Multiple frameworks solving one underlying problem should strengthen the capability signal rather than create many unrelated skills.

### Personal Non-Novelty

A major industry trend should be down-ranked if the user already understands and demonstrates it well.

### Source Echo

Ten articles ultimately referencing one original paper should not be treated as ten independent sources.

---

## 24.4 Product Evals

Track:

### Novelty

Did the user already know this?

### Relevance

Did the user believe this was worth considering?

### Conviction Change

Did discussion alter the user's view?

### Exploration Conversion

Was the Riff promoted?

### Completion

Was the project actually finished?

### Capability Gain

Did completion alter the user's profile?

### Counterfactual Value

Would the user probably have encountered and pursued this without Riff?

---

# 25. Feedback Learning

User feedback should influence future ranking without permanently encoding transient opinions.

Examples:

```text
"This is too framework-specific."
```

may reduce future framework-adoption signals.

```text
"I already understand this professionally."
```

should update capability evidence.

```text
"This is interesting but irrelevant to the roles I want."
```

should affect relevance rather than capability novelty.

Riff should preserve the semantic reason behind feedback.

---

# 26. System Architecture

Riff v0.1 should optimize for simplicity and operating cost.

Recommended architecture:

```text
               SOURCES

       Jobs   GitHub   RSS
         \      |      /
          \     |     /
           ingestion
               |
               v
        scheduled worker
               |
               v
            Postgres
      _________|_________
     |         |         |
 evidence   capability  profile
 receipts     graph      state
     |_________|_________|
               |
               v
         signal pipeline
               |
               v
            Riff API
               |
        _______|________
       |                |
   ChatGPT          future clients
```

---

# 27. Technical Architecture Constraints

## Backend

One Python application.

Avoid microservices initially.

## Database

Postgres.

Use relational tables for structured entities.

Optional `pgvector` for semantic retrieval.

Do not introduce a separate vector database in v0.1.

## Worker

One scheduled process responsible for:

- incremental ingestion,
- evidence compression,
- signal generation.

## API

Expose a small application interface.

Potential operations:

```text
get_daily_riffs()

investigate_riff(riff_id)

search_evidence(query)

get_capability(capability_id)

get_my_capability(capability_id)

record_decision(...)

create_exploration(riff_id)

update_exploration(...)

generate_prd(exploration_id)

record_experience_evidence(...)
```

## ChatGPT Integration

ChatGPT is the first user interface, not the core product.

Riff's application layer must remain interface-agnostic.

A ChatGPT/MCP/plugin-style adapter can sit above the underlying API.

---

# 28. Model Strategy

Use models selectively.

### Cheap processing

Used for:

- receipt generation,
- simple extraction,
- preliminary classification.

### Deterministic code

Used where possible for:

- deduplication,
- recency calculations,
- counts,
- independence weighting,
- ranking features,
- profile lookups,
- prior-decision penalties.

### Strong reasoning model

Used only for:

- strongest candidate signals,
- argument construction,
- counterarguments,
- personalized relevance,
- exploration reasoning,
- PRD generation.

The system should avoid sending:

- the user's entire profile,
- full historical conversations,
- full raw evidence corpora,

when a small relevant slice will suffice.

---

# 29. Daily Processing Budget Principle

The daily architecture should resemble:

```text
hundreds of cheap/raw observations
          ↓
dozens of receipts
          ↓
~20 plausible candidate signals
          ↓
~5 deeply analyzed candidates
          ↓
0–3 published Riffs
```

Exact values may change based on observed quality and cost.

---

# 30. V0.1 Scope

Riff v0.1 must support:

- one user,
- job ingestion,
- GitHub evidence ingestion,
- curated technical-writing ingestion,
- Evidence Receipts,
- capability extraction,
- capability normalization,
- user capability profile,
- private Experience Ledger,
- candidate-signal generation,
- ranking,
- daily Riff generation,
- provenance,
- counterarguments,
- decision storage,
- Riff rejection reasoning,
- Explorations,
- PRD generation,
- agent-ready goals.

---

# 31. Explicitly Out of Scope for V0.1

Do not initially build:

- automated job applications,
- résumé generation,
- broad social-network crawling,
- portfolio website generation,
- coding-agent execution,
- autonomous PR creation,
- investment recommendations,
- vehicle-search workflows,
- multi-user authentication,
- organization/team functionality,
- complex frontend dashboard,
- real-time event processing,
- Kubernetes,
- Kafka,
- dedicated vector infrastructure,
- fully autonomous curriculum generation,
- automatic project promotion without user approval.

---

# 32. Initial ChatGPT Experience

The initial UX may be entirely conversational.

Example:

**User**

> What are today's Riffs?

**Riff**

> I found two worth your attention today.

Then present each with evidence and arguments.

---

**User**

> The second one sounds like normal distributed systems.

**ChatGPT / Riff**

> That's the strongest counterargument too. The potentially new part is X. Here are the pieces of evidence suggesting X rather than ordinary workflow orchestration.

---

**User**

> I'm convinced the problem is interesting, but I don't care about framework X.

Riff stores that distinction.

---

**User**

> What could I build to understand the underlying problem?

Riff creates potential experiments.

---

**User**

> Option 2 is interesting. Save that.

Riff creates an Exploration.

---

**User**

> Make it a project.

Riff produces the PRD.

---

# 33. V0.1 Acceptance Criteria

Riff v0.1 is considered usable when all of the following are true.

### Evidence

The system can ingest incremental evidence from all three primary source categories.

### Provenance

Every meaningful Riff claim can be traced back to stored evidence.

### Capability reasoning

The system can distinguish technologies from underlying capabilities with useful accuracy.

### Personalization

Riff uses GitHub, website evidence, and manually supplied private experience to determine whether something represents a real gap.

### Novelty

Riff does not repeatedly recommend capabilities the user clearly already understands.

### Independence

Correlated evidence is materially down-weighted.

### Daily output

A scheduled run produces zero to three Riffs.

### Argument quality

Each Riff includes:

- claim,
- evidence,
- counterargument,
- why it matters,
- user relevance,
- capability,
- technologies,
- recommendation.

### Conversation memory

A rejected Riff records why it was rejected and influences later recommendations.

### Human approval

No Riff becomes an Exploration without user approval.

### Exploration

An approved Riff can become an Exploration containing several possible bounded experiments.

### PRD

A chosen experiment generates a PRD whose useful first version can reasonably be completed in 4–20 focused hours.

### Goal decomposition

The PRD ends with outcome-oriented goals suitable for downstream agent decomposition.

---

# 34. First Dogfood Test

Riff should initially be tested on its own problem space.

The system should consume several weeks of:

- applied-AI job listings,
- relevant GitHub activity,
- selected engineering writing.

Riff should then answer:

> What are three emerging applied-AI capabilities the user probably does not currently realize are worth investigating?

At least one resulting Riff should cause the user to say something equivalent to:

> I hadn't framed the problem that way. I want to investigate that.

That Riff should then be converted into an Exploration and a completable PRD.

If the system cannot create that moment for its own creator, broader product development should stop until the signal pipeline improves.

---

# 35. Development Sequence

## Goal 1 — Evidence Foundation

Build normalized ingestion and persistent Evidence Receipts for all three source types.

**Acceptance criterion:** New evidence is collected incrementally, deduplicated, traceable, and searchable.

---

## Goal 2 — Capability Model

Build capability extraction and capability/technology separation.

**Acceptance criterion:** A test corpus produces useful capability clusters without excessive fragmentation or over-merging.

---

## Goal 3 — User Model

Ingest public profile evidence and support manual private Experience Ledger entries.

**Acceptance criterion:** Riff can answer what evidence exists for a selected capability and distinguish public from private evidence.

---

## Goal 4 — Signal Engine

Generate and rank candidate weak signals.

**Acceptance criterion:** Synthetic correlated-hype and single-company tests are appropriately down-ranked.

---

## Goal 5 — Daily Riff Generation

Produce zero to three evidence-backed arguments.

**Acceptance criterion:** Each Riff contains provenance, counterargument, personalization, and a useful recommendation.

---

## Goal 6 — Conversational Decision Loop

Allow Riffs to be investigated, rejected, watched, or approved.

**Acceptance criterion:** A rejection preserves semantic reasoning and affects subsequent recommendations.

---

## Goal 7 — Exploration Pipeline

Convert an approved Riff into several bounded project hypotheses.

**Acceptance criterion:** At least one proposed experiment can reasonably be completed in 4–20 focused hours and clearly maps to the target capability.

---

## Goal 8 — PRD Pipeline

Generate a learning-oriented PRD and outcome-level executable goals.

**Acceptance criterion:** Another capable coding agent could begin implementation using the resulting document without needing to rediscover the product's purpose or acceptance criteria.

---

# 36. Guiding Product Principle

Riff should behave less like a recommendation engine and more like an intelligent technical collaborator.

Its job is not:

> Tell me what's popular.

Its job is:

> **Notice something I might have missed, make the strongest case that it matters, let me challenge that case, and—if we decide it's worth my attention—help me turn curiosity into something I actually finish.**