# Engineer-authored source map

This is the G17 research artifact. It is a qualification roster, not an
enablement list: entries remain disabled and `PENDING_REVIEW` until the
operator confirms the endpoint, attribution, and retention terms. The separate
RSS selection manifest now contains 16 reviewed and enabled feed-backed
selections; the roster remains the source of identity and correlation metadata.
The three URL-only candidates remain outside the RSS pipeline pending a bounded
HTML or official-API adapter.

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
| Eugene Yan | applied ML, LLM systems, evals | [RSS](https://eugeneyan.com/rss/) | Personal | Native RSS; review terms | `person:eugene-yan` |
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
| Ethan Mollick | AI in work, human-AI interaction | [One Useful Thing](https://www.oneusefulthing.org/feed) | Personal | Native RSS; pending terms review | `person:ethan-mollick` |
| Nathan Lambert | post-training, open models, evals | [Interconnects](https://www.interconnects.ai/feed) | Personal publication | Native RSS; bounded public-feed retention review | `person:nathan-lambert` |
| Chris Olah | mechanistic interpretability, model internals | [colah's blog](https://colah.github.io/rss.xml) | Personal | Native RSS; pending terms review | `person:chris-olah` |
| Evan Anders | interpretability, transformer circuits | [Research blog](https://evanhanders.blog/feed/) | Personal | Native RSS; pending terms review | `person:evan-anders` |
| Kevin Chen | reasoning, ML systems, simulation | [Personal blog](https://kevinchen.co/feed.xml) | Personal | Native RSS; OpenAI affiliation correlated | `person:kevin-chen` |
| Nishanth J. Kumar | robotics, planning, long-horizon agents | [Personal blog](https://nishanthjkumar.com/feed.xml) | Personal | Native RSS; Meta affiliation correlated | `person:nishanth-kumar` |
| Praj Bhargava | pretraining infrastructure, long context | [Personal blog](https://prajjwal1.github.io/atom.xml) | Personal | Native RSS; Meta affiliation correlated | `person:praj-bhargava` |
| Jeremy Howard | practical ML, end-user AI, education | [fast.ai posts](https://www.fast.ai/index.xml) | Community | Native RSS; fast.ai/Answer.AI correlation required | `person:jeremy-howard` |
| Julia Evans | systems, networking, debugging | [jvns.ca](https://jvns.ca/atom.xml) | Personal | Native RSS; pending terms review | `person:julia-evans` |
| Armin Ronacher | agentic coding, runtimes, open source | [Technology blog](https://lucumr.pocoo.org/feed.atom) | Personal | Native Atom; pending terms review | `person:armin-ronacher` |
| Mario Zechner | coding-agent harnesses, developer tools | [Personal blog](https://mariozechner.at/rss.xml) | Personal | Native RSS; pending terms review | `person:mario-zechner` |
| Mitchell Hashimoto | developer tools, systems performance | [Writing](https://mitchellh.com/feed.xml) | Personal | Native RSS; pending terms review | `person:mitchell-hashimoto` |
| Geoffrey Litt | malleable software, HCI, AI-assisted programming | [Personal site](https://www.geoffreylitt.com/feed.xml) | Personal | Native RSS; employer correlation required | `person:geoffrey-litt` |
| Matt Lim | agent research, tool use, product engineering | [Personal site](https://www.mattlim.me/) | Personal | URL-only; bounded adapter required | `person:matt-lim` |
| Saffron Huang | AI societal impacts, human-AI interaction, safety | [Personal site](https://saffronhuang.com/) | Personal | URL-only; bounded adapter required | `person:saffron-huang` |
| François Chollet | AI foundations, program synthesis, evaluation | [Personal site](https://fchollet.com/) | Personal | URL-only; bounded adapter required | `person:francois-chollet` |

The feed URLs for Sebastian Raschka, Andrej Karpathy, Jay Alammar, and Hamel
Husain are candidate endpoints gathered from their public sites or public feed
indexes; G17 keeps them pending until a live endpoint/terms check is explicitly
performed. G31 completed the initial check for three approved selections, and
the 2026-09-15 expansion pass validated 13 additional native feeds. Hamel's
writing is directly about practical AI engineering and evals, and Eugene Yan's
published themes include production LLM systems and evaluation.

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
keeps unreviewed selections `PENDING` and disabled until their own endpoint,
terms, retention, reviewer, and date are recorded. The 16 feed-backed
selections are reviewed and enabled; `NONE_FOUND` URL-only entries remain
outside the RSS pipeline.

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
