# Engineer-authored source map

This is the G17 research artifact. It is a qualification roster, not an
enablement list: every entry in `config/engineer_sources.json` is disabled and
`PENDING_REVIEW` until the operator confirms the endpoint, attribution, and
retention terms.

The roster is intentionally mixed. Simon Willison documents a set of public
Atom feeds for his own site, while Sebastian Raschka, Hamel Husain, Eugene Yan,
Chip Huyen, Lilian Weng, and similar practitioners publish applied AI/ML
engineering material on personal sites or newsletters. These are useful because
they expose individual reasoning and hands-on experience, but personal and
employer sources must still be correlated rather than counted as independent
organizations. See the public source descriptions for [Simon Willison](https://feeds.simonwillison.net/about/),
[Hamel Husain](https://hamel.dev/), [Eugene Yan](https://eugeneyan.com/),
[Chip Huyen](https://huyenchip.com/blog/), and [Sebastian Raschka](https://sebastianraschka.com/blog/).

## Roster and source decisions

| Engineer/researcher | Theme | Source / endpoint | Ownership | Machine-readable decision | Correlation group |
|---|---|---|---|---|---|
| Simon Willison | applied AI, open source | [Atom entries](https://simonwillison.net/atom/entries/) | Personal | Native RSS/Atom; review terms | `person:simon-willison` |
| Chip Huyen | AI engineering, production ML | [Blog](https://huyenchip.com/blog/) / `https://huyenchip.com/feed.xml` | Personal | Pending endpoint review | `person:chip-huyen` |
| Eugene Yan | applied ML, LLM systems, evals | [RSS](https://eugeneyan.com/rss.xml) | Personal | Native RSS; review terms | `person:eugene-yan` |
| Lilian Weng | agents, research, safety | [Lil'Log](https://lilianweng.github.io/) / `https://lilianweng.github.io/index.xml` | Personal | Native RSS; review terms | `person:lilian-weng` |
| Sebastian Raschka | LLM training, evaluation | [Blog and notes](https://sebastianraschka.com/blog/) / `https://sebastianraschka.com/feed.xml` | Personal | Pending endpoint review | `person:sebastian-raschka` |
| Hamel Husain | evals, LLM infrastructure | [Hamel's Blog](https://hamel.dev/) / `https://hamel.dev/feed.xml` | Personal | Pending endpoint review | `person:hamel-husain` |
| Andrej Karpathy | models, agents, education | [Karpathy blog](https://karpathy.github.io/) / `https://karpathy.github.io/feed.xml` | Personal | Pending endpoint review | `person:andrej-karpathy` |
| Jay Alammar | transformers, ML education | [Blog](https://jalammar.github.io/) / `https://jalammar.github.io/feed.xml` | Personal | Pending endpoint review | `person:jay-alammar` |
| Gergely Orosz | software engineering, AI-assisted work | [The Pragmatic Engineer](https://newsletter.pragmaticengineer.com/) / `https://newsletter.pragmaticengineer.com/feed` | Personal publication | Pending endpoint/retention review | `person:gergely-orosz` |
| Charity Majors | observability, production engineering | [Personal site](https://charity.wtf/) | Personal | No permitted machine-readable source found | `person:charity-majors` |
| Liz Fong-Jones | observability, SRE, distributed systems | [Personal site](https://lizthegrey.com/) | Personal | No permitted machine-readable source found | `person:liz-fong-jones` |
| Bryan Cantrill | runtime and distributed systems | [DTrace blog](https://dtrace.org/blog/feed/) | Personal/employer-adjacent | Pending endpoint review | `person:bryan-cantrill` |
| Martin Kleppmann | event sourcing, distributed systems | [Blog](https://martin.kleppmann.com/) / `https://martin.kleppmann.com/atom.xml` | Personal | Pending endpoint review | `person:martin-kleppmann` |
| Maxim Fateev | durable execution, workflow runtime | [Temporal Blog](https://temporal.io/blog) | Employer | No native feed found; author filter required | `org:temporal` |
| Harrison Chase | agent frameworks, observability | [LangChain Blog](https://www.langchain.com/blog) | Employer | No native feed found; author filter required | `org:langchain` |
| Shreya Shankar | AI evaluation, data quality | [Personal site](https://shreyashankar.com/) | Personal | No permitted machine-readable source found | `person:shreya-shankar` |

The feed URLs for Simon Willison, Lilian Weng, Eugene Yan, Sebastian Raschka,
Andrej Karpathy, Jay Alammar, and Hamel Husain are candidate endpoints gathered
from their public sites or public feed indexes; G17 keeps them pending until a
live endpoint/terms check is explicitly performed. Hamel's writing is directly
about practical AI engineering and evals, and Eugene Yan's published themes
include production LLM systems and evaluation.

## Attribution and independence rules

- A personal source is attributed to the named person only when the item has a
  matching author identity or an unambiguous source-owned page.
- Employer posts are correlated to the employer root even when an engineer is
  the author. An author filter can identify the person, but it does not create a
  second independent organization.
- Co-authored items retain all authors and a co-author relation; they are not
  duplicated into one item per person.
- Reposts and newsletter/blog copies retain the original root and a
  `CONTENT_EQUIVALENT` or syndication relation.
- Missing, contradictory, or drifting attribution is quarantined for review,
  not guessed from a byline fragment or social profile.
- Follower counts, subscriber counts, stars, and publication frequency are
  context only and never evidence of capability or independence.

## Review and future adapters

Before enabling any entry, record the review date, endpoint response, terms,
retention mode, canonical-link behavior, and an archived fixture. Sources marked
`NONE_FOUND` should remain URL-only until a first-party RSS/Atom feed, official
API, or bounded HTML adapter is approved. Unofficial RSS mirrors are excluded.

The attribution fixture at
`tests/fixtures/engineer_sources/attribution_cases.json` covers personal,
employer-owned, co-authored, syndicated, and attribution-drift cases. It is
deliberately deterministic and does not contact any source.

## RSS selection and enablement

`config/engineer_rss_selections.json` is the bridge from this qualification
roster to the existing RSS registry. It references stable G17 source IDs and
keeps every selection `PENDING` and disabled until its own endpoint, terms,
retention, reviewer, and date are recorded.

Use the local review workflow:

```sh
uv run riff source engineer-rss validate
uv run riff source engineer-rss preview
uv run riff source engineer-rss project --selection-id <selection-id> --apply
uv run riff source sync --registry config/technical_sources.json
```

The projection command is fail-closed: pending, unavailable, `NONE_FOUND`,
duplicate, malformed, or credential-bearing selections cannot mutate either
registry. Projection is idempotent and preserves `engineer_source_id`, person,
owner, organization-at-publication, source root, and correlation group. The
normal RSS runner then stores these fields in retrieval metadata and applies
the attribution disposition rules above. Disable a source with the existing
`riff source disable --source-id ...` command; disabling does not erase prior
retrievals or provenance.
