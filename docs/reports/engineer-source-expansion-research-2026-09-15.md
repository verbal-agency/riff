# Engineer-source expansion research (2026-09-15)

## Finding

The current G17 roster now has 32 named people, but only Simon Willison, Eugene
Yan, and Lilian Weng have been approved and collected. The roster is strong on
personal AI/ML blogs, but it is thin on current major-lab practitioners and on
independent builders writing about agents, systems, and human-facing software.

This pass researched first-party pages and feed links. A feed returning HTTP
200/XML is only an endpoint qualification; it is not permission to ingest or
proof of authorship. Every new entry remains `PENDING_REVIEW` until its
endpoint, terms, retention, attribution, reviewer, and date are recorded.

## Newly recorded native-feed candidates

These endpoints returned a successful XML/RSS/Atom response during this review.
Affiliation is context for correlation, not an independent organization claim.
All entries below have been added to `config/engineer_sources.json` as disabled
`PENDING_REVIEW` candidates; none is enabled by this research pass.

| Candidate | First-party source | Affiliation/context | High-value themes | Ownership / decision |
|---|---|---|---|---|
| Ethan Mollick | [One Useful Thing](https://www.oneusefulthing.org/feed) | Wharton professor; writes the publication himself | AI in work, education, human use, product adoption | `PERSONAL`; add as pending |
| Nathan Lambert | [Interconnects](https://www.interconnects.ai/feed) | Ai2 post-training/open-model researcher | post-training, open models, evals, model economics | `PERSONAL_PUBLICATION`; bounded public-feed retention; add as pending |
| Chris Olah | [colah's blog](https://colah.github.io/rss.xml) | Anthropic co-founder and interpretability research lead | mechanistic interpretability, model internals | `PERSONAL`; add as pending |
| Evan Anders | [Research blog](https://evanhanders.blog/feed/) | Anthropic researcher; personal views | interpretability, transformer circuits, benchmarks | `PERSONAL`; add as pending |
| Kevin Chen | [Personal blog](https://kevinchen.co/feed.xml) | OpenAI reasoning team; personal-opinion disclaimer | reasoning, ML systems, autonomy, simulation | `PERSONAL`; add as pending |
| Nishanth J. Kumar | [Personal blog](https://nishanthjkumar.com/feed.xml) | Meta Robotics Studio research scientist | long-horizon agents, planning, robotics, foundation models | `PERSONAL`; add as pending |
| Praj Bhargava | [Personal blog](https://prajjwal1.github.io/atom.xml) | Meta Superintelligence Labs research engineer | pretraining infrastructure, long context, foundational models | `PERSONAL`; add as pending |
| Jeremy Howard | [fast.ai posts](https://www.fast.ai/index.xml) | fast.ai founding researcher; Answer.AI | practical ML, end-user AI, constrained R&D | `ORGANIZATION_AUTHORED`; correlate with fast.ai/Answer.AI |
| Julia Evans | [jvns.ca](https://jvns.ca/atom.xml) | Independent software educator and author | systems, networking, debugging, technical explanation | `PERSONAL`; add as pending |
| Armin Ronacher | [Technology blog](https://lucumr.pocoo.org/feed.atom) | Open-source creator; now building Earendil | agentic coding, runtimes, Python, OSS operations | `PERSONAL`; add as pending |
| Mario Zechner | [Personal blog](https://mariozechner.at/rss.xml) | Independent builder of the Pi coding agent | coding-agent harnesses, minimal tools, model UX | `PERSONAL`; add as pending |
| Mitchell Hashimoto | [Writing](https://mitchellh.com/feed.xml) | Ghostty/Superlogical builder; former HashiCorp founder | developer tools, systems, performance, AI-assisted coding | `PERSONAL`; add as pending |
| Geoffrey Litt | [Personal site](https://www.geoffreylitt.com/feed.xml) | Notion; former Ink & Switch researcher | malleable software, HCI, AI-assisted programming, local-first tools | `PERSONAL_EMPLOYER_ADJACENT`; correlate with Notion when applicable |

The role and source claims above are grounded in the candidates' own pages:
Mollick describes *One Useful Thing* as his blog/newsletter; Lambert describes
Interconnects as his publication and identifies his Ai2 work; Anthropic lists
Olah as its interpretability lead; Chen, Kumar, Bhargava, and Anders identify
their lab roles on their personal sites; Howard, Ronacher, and Litt describe
their projects and affiliations directly.

## Endpoint validation

On 2026-09-15, a read-only live probe of all 16 entries marked `NATIVE_RSS`
returned HTTP 200 and an XML/RSS/Atom content type (or an RSS/Atom document
root). This includes the three previously collected sources and the 13 new
native-feed candidates. The three URL-only candidates were intentionally not
treated as feed endpoints; they remain `NONE_FOUND` pending a bounded HTML or
official-API adapter decision.

## Post-research enablement and smoke

The operator subsequently enabled all 16 feed-backed selections with explicit
`USER_PROVIDED` permission and projected them into both source registries. A
targeted live run over those 16 source IDs completed `SUCCEEDED` with no new
failures on its cursor-safe retry. The first broad run stored 201 non-synthetic
items; its 159 permanent failures and 29 skips came from stale test-created
sources still present in the shared development database, not from the
targeted engineer source set. One enabled feed (Praj Bhargava) currently has
no parseable items and remains visible as `EMPTY` in the coverage report.

## Major-lab coverage gaps

| Lab / ecosystem | What Riff has now | Gap and recommended representation |
|---|---|---|
| OpenAI | General OpenAI RSS in G16; no named current engineer source | Add Chen's personal feed; keep Matt Lim as a URL-only candidate until a first-party feed is identified. Use author-filtered OpenAI evidence as employer-correlated, never as personal independence. |
| Anthropic | No native Anthropic Research RSS; employer entries are not in the engineer roster | Add Olah and Anders personal feeds. Keep Anthropic Research/Science as a future bounded HTML adapter; do not scrape around the missing feed. |
| Google DeepMind | General DeepMind RSS in G16; no newly verified named personal feed in this pass | Retain the lab feed with author attribution. Keep current/former individuals such as Sebastian Raschka or François Chollet separate until a first-party personal endpoint is confirmed. |
| Meta | No named Meta engineer in the current roster | Add Kumar and Bhargava personal feeds. Treat Meta AI/Research pages as employer-root evidence, with author filtering and no independence uplift. |
| Ai2 / open-model ecosystem | No current Ai2 individual source | Add Lambert's public feed; record that some Interconnects articles are subscriber-only and retain only permitted public content. |
| Perplexity, Mistral, NVIDIA, xAI | No verified personal feed added in this pass | Keep as a discovery queue. Prefer named first-party blogs, GitHub, papers, or official APIs over aggregators or social mirrors. |

## URL-only / future-adapter candidates

These are valuable people, but this pass did not find a stable native feed that
should be enabled immediately. They are recorded in the roster as disabled,
`PENDING_REVIEW`, URL-only candidates:

- Matt Lim — OpenAI Agents Research and former product engineer. His personal
  site is a strong identity anchor, but the technical writing is split across
  a personal TIL and Medium; keep URL-only until one bounded endpoint is
  selected.
- Saffron Huang — Anthropic researcher and former DeepMind research engineer.
  Her personal site is useful for identity and research context, but no feed
  link was advertised.
- François Chollet — former Google/Keras engineer and independent researcher.
  His public work is high-value, but no stable personal feed was confirmed.

These should not be substituted with third-party RSS mirrors. A future HTML or
official-API adapter can be proposed separately with its own retention and
attribution review.

## Recommended next implementation slice

Create a follow-up source-qualification goal that:

1. Selects a bounded first batch of 6–8 sources spanning human-centered AI,
   open models, interpretability, current lab engineering, agent harnesses,
   and systems/HCI.
2. Replays recorded fixtures for every selected source, then enables only
   sources with explicit operator review and a live smoke result.
3. Preserves employer correlation and paywall/retention boundaries; feed volume
   or public popularity must not increase confidence by itself.

The strongest initial batch is Ethan Mollick, Nathan Lambert, Chris Olah,
Kevin Chen, Nishanth J. Kumar, Mario Zechner, Armin Ronacher, and Geoffrey
Litt. This gives Riff a materially broader signal surface without turning the
roster into a popularity list or duplicating employer feeds.
