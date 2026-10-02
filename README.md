# Panda

An AI property search engine for Lahore. Conversational interface over a
risk-and-possession knowledge layer for Lahore housing schemes.

Status: **Milestones 1-7 complete.** Django models, deterministic resolver
(society slot + flat block-identity layer), and the extraction-boundary validators.

**Design exploration is deferred** until controlled live extraction passes. An interface
drawn before the corpus can answer anything encodes assumptions we have not validated.

**The answer surface must distinguish "the corpus has no evidence" from "no such
property exists".** Those are different claims and only the first is ever supportable
here. See the design doc section of that name.

**This project has no web interface and is not meant to have one yet.** It is a
library plus a CLI. Django's admin was built once while trying to answer "run it
locally", and removed again the moment it started to look like a product surface.
There is no conversational search interface yet — that is the actual product, and it
has not been built.
**162 tests passing.** Baseline **1351/2725 = 49.6%**, zero cross-city false matches.
Two real-page extraction runs on 5 pages have surfaced **three** contract holes the
tests alone missed: V9 place corroboration, V10 fact-type cue, and a V6 gap where a
CCA-3 _commercial_ rate was accepted as residential. 5 facts accepted, 22 rejected,
V3 refusals cut 11 → 2 by ingesting publication dates. **No live LLM calls** (no
credentials); the proposer was the engineer reading each page.

`Fact` stores `(place, size, file_type, amount)` with an explicit `qualifier_status` of
complete/partial/unknown.

Gateway chain verified hop by hop (`manage.py check_gateway`): all three hops pass. The
first live page then exposed a fourth defect — **the gateway drops litellm's `system=`
parameter**, so the extraction contract never reached the model and it returned prose
instead of candidates, with no error. Fixed: gateway mode sends the contract as a
`role="system"` message; SDK mode keeps `system=`.

**Live extraction is now blocked only on OpenRouter credits** (402, ~505 tokens
affordable). One call succeeded and returned a faithful verbatim rate table — the model
works, it just had no instructions.

**What the numbers do and don't mean.** 49.6% resolution and the validator
rejection counts are **test-corpus measurements**, not Lahore-wide coverage and not a
reliability claim about live extraction. The corpus over-represents DHA because that is
what the sources publish. All nine validators firing shows the boundary is exercised,
not that it is proven. Only the controlled live run proves that.

## Read this first

**Blocked right now on OpenRouter credits.** When they exist, the next action is
`docs/CONTROLLED-LIVE-EXTRACTION.md` — a runbook, not a suggestion. One page, then
one section, then the full page, with a manual inspection gate at each step.

`docs/MILESTONE-1-HANDOFF.md` states what was built and in what order.

Supporting material:

- `docs/designs/lahore-aarea-gyan-engine.md` — design + Milestone 1 contract
- `docs/CONTROLLED-LIVE-EXTRACTION.md` — **the next run, step by step**
- `data/sources.md` — 10 registered sources; no crawling needed
- `data/normalization/` — entity map, drops, observations, review history
- `data/live/` — raw model responses, kept deliberately. See its README for why.

The one-line version: chat is the interface, not the product. Conversational property
search already exists in Pakistan (PropertyAI.pk, PropertyWalay) and Lahore block-level
price intelligence already exists (GharPulse). The unbuilt layer is the dated
risk/possession knowledge — balloting status, litigation, possession timelines, file
terms, fee schedules — which exists as prose across competing agency blogs.

## Current order of work

1. ~~Resolve the terms-of-service gate~~ — **cleared, then RE-VERIFIED**. All 10 sources permitted;
   Terms evidence. Harvesting permitted under stated policy, with rate limiting,
   local caching, and per-source attribution. Still required: record per-source
   policy before fetching any _new_ source.
2. ~~Enumerate 8-10 Lahore sources~~ — **done**. See `data/sources.md` for the 10
   registered sources, coverage matrix, and the naming variants that must seed the map
3. ~~Hand-author the normalization map~~ — **done**. `data/normalization/map.md` plus
   CSV fixtures: 42 entities (39 evidenced), 23 aliases, 20 drops
4. ~~Dry-run the map~~ — **done**. `data/normalization/dryrun-report.md`: 122
   observations logged, none discarded. **The ~30% baseline is retracted — it counted
   the noise bucket. No valid baseline exists.**
5. ~~Independent architecture review on R1-R6~~ — **done**.
   `data/normalization/review-R1-R6.md`. Verified defects fixed; R1-R6 held as
   proposals, not applied.
6. ~~Fix Rahbar level bug; add entity evidence column~~ — **done**. 42 entities,
   39 evidenced, 1 contested, 2 invented ones deleted.
7. ~~Redo ToS verification with real policies~~ — **done**.
   `data/normalization/tos-verification.md`. All 10 sources permitted; maanestate has
   a full crawl policy with Crawl-delay 10 and a published AI hub.
8. ~~Reconcile drops against observations~~ — **done**.
   `data/normalization/drops-reconciliation.md`. 3 drops vacuous, 1 was missing,
   2 resolvable via document scope.
9. ~~Validate R1-R6 against multiple pages per source~~ — **done**, 84 pages.
   `data/normalization/validation-R1-R6.md`. **R1 and R6 adopted; R2 and R3 rejected
   on evidence; R4 partial; R5 moot.** Reproducible baseline: 680/2725 = 25.0%
10. ~~Decide Phase 1-4 scope; update map; re-run~~ — **done**. Entities added for
    Lahore; **bare `DHA Phase N` dropped as cross-city** (Islamabad has the same phase
    numbers). `data/normalization/rerun-results.md`: 1033/2725 = **37.9%**
11. Implement the society slot in the resolver (recovers ~9%: `Bahria Town`, `LDA City`);
    route `CCA-*` through measurement.csv; enforce drops before canonical matching
12. ~~Milestone 1 — deterministic foundation~~ — **done**. `corpus/` (models, resolver,
    load_corpus, run_resolver). `python3 manage.py test corpus` -> 25 passing
13. ~~Society slot~~ — **done**. +148 net to 41.8%. Three false-match classes opened
    and closed (abbreviated cross-city forms, DHA Valley, bare Gulberg)
14. Review the 3 loader defects found while implementing (documented in
    docs/MILESTONE-1-HANDOFF.md)
15. ~~Block identity investigation~~ — **done**, then implemented. Flat BlockIdentity
    model (not a Place), promotion rule requires 2+ independent sources. 56 of 57
    identities are single-source and blocked from promotion
16. ~~Extraction boundary contract~~ — **decided**. Tier 1 only, 7 deterministic
    validators, LLM never names a place. See design doc "Extraction Boundary"
17. ~~Implement the boundary contract + negative tests~~ — **done**. `corpus/validators.py`
    V1-V8, 31 tests. Both non-negotiables pass; a control test proves they aren't
    rejecting everything
18. ~~Wire extractor, run on real pages, review rejection volume~~ — **done**
19. ~~Cue-word contract~~ and ~~metadata-date ingestion~~ — **done**. V10 + V6 fix + `published_dates`
20. ~~`Fact` needs `size` and `file_type`~~ — **done**, plus V11 qualifier contract
21. ~~Set credentials, one live page~~ — auth chain done, contract-delivery bug fixed.
    **Blocked on OpenRouter credits.** Add credits, then:
    `run_live_page --source dha_rates --file data/pages/dha_rates_section.html`
22. Then: chat interface

**Milestone 1 does not include extraction.** Extraction sits on top of a validated
deterministic resolver.

**Extraction is blocked** until Milestone 1 reproduces 37.9% with zero cross-city
false matches. Validated baseline is **37.9%** (1033/2725, 84 pages) —
the numerator is recorded matches, not noise. A higher number bought by forcing
matches is a regression, not progress.

**Revisit the ToS decision before any public launch.** The live risk is social, not
legal: these are small businesses whose traffic advantage a public corpus would erode.

## Stack

**Run with the venv interpreter** — it holds both Django and LiteLLM:

```bash
.venv/bin/python manage.py test corpus          # 162 tests
.venv/bin/python manage.py load_corpus          # load the entity map
.venv/bin/python manage.py run_resolver         # offline resolution diagnostic
.venv/bin/python manage.py run_extraction       # replay proposals through the boundary
.venv/bin/python manage.py check_gateway        # probe the LiteLLM gateway hop by hop
.venv/bin/python manage.py run_live_page        # one page, live LLM + boundary
```

There is no `runserver` step and no URL routes. Django is used for its ORM, models,
migrations and test runner; everything runs from management commands. Web framework, ORM, admin, and the
ingestion/cron surface. No separate frontend framework, no second service.

## Hard rules

- Never guess an entity mapping. Drop it and log the drop.
- An alias is usable only with recorded evidence. Unconfirmed aliases are observations,
  not mappings.
- Coverage gaps stay visible. Do not create entities for schemes no source publishes.
- Never force a match to improve coverage statistics. Unresolved is a valid outcome;
  a wrong resolution is not.
- Never spoof a browser user-agent. Never evade a 403.
- Every entity and alias needs evidence from a registered source. An invented entity
  is worse than a missing one.
- Preserve the original source string alongside every canonical entity.
- Every fact carries a source URL and an `as_of` date.
- An inaccurate data point is worse than a missing one.
