# Independent Architecture Review — Panda entity-resolution gate

Reviewer: fresh context, adversarial. Artifacts as of 2026-10-01.
Scope: design + data-artifact review only. No production code written.

---

## 1. Verdict table

| # | Item | Verdict | One-line rationale |
|---|---|---|---|
| R1 | Compositional name resolution | **REVISE** | The idea is right, the grammar sketched is not implementable — a positional trailing numeral is undecidable without a declared leaf namespace per parent, and no such declaration exists. |
| R2 | Society-specific hierarchies | **REVISE** | `place_type` is correct; "single parent_id" is not. LDA City is unmodellable on current evidence and should be declared unmodellable rather than half-modelled. |
| R3 | Explicit `sub_sector` level | **REJECT (as proposed)** | A tree *level* is the wrong abstraction — it will need sub-sub-sectors within one release. Replace with a scoped, per-parent `place_type` label. The Rahbar bug is real and is **still live in the shipped CSV**. |
| R4 | Permanent observation records | **REVISE** | The table is the right idea implemented at the wrong grain — keyed on the string, when the disambiguating evidence lives on the page. Cannot ever resolve bare `Phase 9`. |
| R5 | Inaccessible/unverified sources | **REJECT the framing / the premise is false** | Both "unverified" claims are falsified by live check: asas is up, maanestate has a 118-line crawl policy and a published `llm.txt` AI hub. And a boolean flag is insufficient. |
| R6 | Coverage stays diagnostic | **REVISE** | The stated proof for R6 is circular — the 8 occurrences cited are labelled `harness_artifact` in the same artifact set, and the ~30% baseline is not reproducible from any file. The principle is right; the enforcement is prose. |

---

## 2. Per-item analysis

### R1 — Compositional name resolution → **REVISE**

**What is right.** Replacing alias enumeration with slot parsing is correct and the diagnosis ("the alias table is the wrong shape") is the single best finding in the whole dry-run. The cross-product `{ "", "DHA ", "DHA Lahore ", "Defence " } × { "Phase N", "Ph N", "Phase-N", "PhaseN" }` is genuinely unbounded and must not be hand-written.

**Where it breaks.** The proposal's own grammar is wrong in a specific way: it parses *society* and *phase* only, then asserts the "resulting entity actually exists under that society". But the failure cases you named are all *below* the phase, and the proposal has no slot for them. Concretely:

1. **`DHA Phase 9 Prism 10` vs `DHA Phase 9 Town 5`.** These are not the same dimension and the difference is not recoverable from the token. The disambiguating fact is: *which namespace does the trailing numeral index into?* For `ph_dha_9_prism` the trailing token is a sector id; for `ph_dha_9_town` it is a size. That information does not live in the string, in the society, or in the parser — it lives in the **leaf namespace declared by the parent**. Without `place.parent` carrying `children_are: {sector_id | size}`, the parser must guess, and "never accept a match because the text resembles a known name" is violated at exactly this point.
2. **`Sector A` bare.** Compositional parsing cannot help — there is no society slot. Not a parser bug; a genuinely absent referent. Correct outcome.
3. **`Block B` bare.** Same. 13 DHA phases × letters means `Block B` has ≥13 referents. Correct outcome.
4. **`Phase 9` bare, 22 occurrences across 5 sources.** Parsing yields `{phase: 9}` with `society: null`, and the society slot is *required*. So it fails. Correct outcome — but only because the slot is mandatory. Make the society slot optional and this becomes a silent wrong merge.
5. **`Phase 1–4` (and Phase 2, 76 occurrences).** Compositional parsing *will* resolve `DHA Phase 2` to a phase entity if one is ever created, and it validates only against "does this phase exist". It cannot validate that the phase is *one we have sources for*. `map.md` correctly refuses to split `Ph 1-4` into per-phase rates; the parser must equally refuse to invent `ph_dha_2`. Existence-in-Lahore and existence-in-corpus are different predicates and the design conflates them.

**The grammar I would actually implement** — tokenise into typed slots with a *required* society slot and a *typed* numeric tail resolved against the parent's declared namespace:

```
TOKENS := (SOCIETY)? (PHASE_DESIGNATOR) (PARENTHETICAL)? (SCOPE_TOKEN)* (TRAILING_NUMERAL)?
SOCIETY         := one of society_qualifier table, resolved to exactly one society_id
PHASE_DESIGNATOR:= ("phase"|"ph") ("-")? (roman|arabic)      -- normalise roman→arabic
                    | "phase" ("-")? ("x"|roman|arabic)
SCOPE_TOKEN     := prism | town | extension | rahbar | m-extension | ex-dha city | ...
TRAILING_NUMERAL:= arabic, typed by parent's declared `child_namespace`
```

Hard rules:
- `SOCIETY` is **mandatory** for any resolution below society level. A missing society is a drop, not a default. No default-society inference, ever — this is the single line that prevents the Bahria/Askari corruption.
- A `TRAILING_NUMERAL` is **only** resolved if the parent entity declares `child_namespace` and the token is in that namespace's vocabulary. If the parent declares `size` namespace, `DHA Phase 9 Town 5` → size=5. If `sector`, → sector 10. If neither, unresolved. Never both. Never "whichever matches something".
- Parenthesised scope tokens are **stripped before phase matching, then re-attached as the parent discriminator**. `Phase 11 (Rahbar Sec-4)` must not resolve to `ph_dha_11_rahbar` by base-form match — that is Class B, currently a map failure, and a base-form strip would turn it into a *silent* wrong merge instead of a visible miss. Parenthetical content is a discriminator, never decoration.
- Normalisation (roman, hyphen, no-space) happens **before** slot parsing, and the normalised form is stored on the observation alongside the raw form. Never overwrite the raw string.

**Failure modes this does not fix** (and should not claim to): bare phase without society (needs page context, see R4); `DHA City` (three referents including Karachi — a cross-city leak, not an ambiguity); `Phase 9 Extension → Phase 10` (needs a date boundary, i.e. temporal identity, which the schema lacks entirely).

**Required change:** add `place.child_namespace` and `namespace_token` tables; make the society slot mandatory in the resolver signature, not in a docstring.

---

### R2 — Society-specific hierarchies → **REVISE**

**What is right.** Replacing the global `level` enum with a per-society `place_type` declaration is correct and is the actual fix for "sector vs block is not a uniform level".

**What is wrong.** Two things.

**(a) Single `parent_id` is not enough — but not for the reason you'd expect.** You do not need a closure table or nested set for the *current* corpus, because every current hierarchy is depth ≤ 2 and every node has exactly one taxonomic parent. A closure table would be over-engineering *today* and would become necessary the moment you get Bahria's sector-within-block structure (Sector C Block B) or LDA's actual nesting. The correct call: **single parent for now, plus a second edge table from day one** so the migration is additive rather than a rewrite. Do not build the closure table; do not pretend the single-parent invariant is permanent.

```
place_edge(child_id, parent_id, edge_kind, ordinal)
edge_kind ∈ {taxonomic, partition_of, renamed_to, overlaps}
```
Unique index on `(child_id, edge_kind)`. `place.parent_id` stays as a denormalised convenience for the `taxonomic` edge only.

**(b) LDA City is unmodellable on current evidence, and should be declared so.** You have blocks A1, B1, E1, H, L, M, N, P and sectors Jinnah, Iqbal, Pine, and **no source anywhere states how a block relates to a sector**. Not "ambiguous" — *unobserved*. The honest modelling is:

- Do **not** nest sectors under blocks or vice versa. You have zero evidence.
- Do **not** model them as siblings under `soc_lda_city` either, because that asserts they are *independent partitions*, which is also unevidenced and is a stronger claim than "we don't know".
- Required state: `edge_kind='unknown'`, an explicit `LDA City: block↔sector relationship UNOBSERVED` coverage-gap row, and a resolver rule that **refuses to resolve any LDA City place to a canonical_id at all** — it may only be stored as an unresolved observation with a `place_candidate` link. Every LDA City block entity in `entity.csv` is currently a guess wearing a canonical_id.

This is the honest answer and it costs you the LDA City portion of the corpus in v1. Accept that cost.

**(c) The `level` enum is already broken in the shipped fixture.** `map.md` declares `level (society|phase|block)`. `entity.csv` contains five values: `society, phase, block, sector, scheme`. The prose schema and the data already disagree. That is not a nit — it means the declared contract was never enforced and the fixture drifted.

**Required change:** `society.place_types` declaration table; `place_edge` for non-taxonomic relations; `lra_relation_state ∈ {observed, unknown}` on society, with `unknown` blocking resolution.

---

### R3 — Explicit `sub_sector` level → **REJECT as proposed**

**The bug is real.** `Rahbar Sec-4` → `ph_dha_11_rahbar` is a confirmed wrong mapping — a sector flattened onto a phase. Your own framing of the consequence ("sourced, dated, and wrong") is correct.

**But adding a tree level is the wrong fix, for a structural reason:** a global `level` enum is a *taxonomic depth* axis, and `sub_sector` is not a depth axis — it is a **scope label relative to a specific parent**. DHA has sectors directly under the society (Bahria-style naming collides), sectors under a phase (Rahbar Sec-4), and lettered sectors under a sub-phase (Prism L/R/B/F). None of those are "level 4". You will discover `sub_sub_sector` inside a quarter, which is exactly the trap R2's `place_type` was supposed to avoid — and you would be reintroducing it in the same schema.

**Correct fix:** `sub_sector` is a `place_type`, not a level. Depth comes from `parent_id`; naming convention comes from `place_type`. `place_type` is declared per parent, so "sector within Phase 11" and "sector within Phase 9 Prism" are the same `place_type` with different parents and no new level required.

**Deeper problem you did not ask about, and it is the real one:** the flattening bug is not a *schema* bug. It is a *review-process* bug that the schema did not catch. `alias.csv` has carried `Rahbar Sec-4 → ph_dha_11_rahbar, confirmed=true` since it was authored, with `evidence_url` pointing at a page whose heading is literally `DHA Rahbar (Phase-11 Sec-4)` — **the cited evidence contradicts the asserted mapping**. The dry-run only caught it because `DHA Rahbar Sector-4` (a slightly different string) happened to be observed. A confirmed alias can therefore pass the entire authoring process on evidence that refutes it. Fixing the schema without fixing the evidence-check does not close this hole.

**Required invariant (this is the important deliverable of R3):**
> An alias may not be `confirmed` unless its target's `place_type` is compatible with the alias's grammatical form, **and** the `evidence_quote` field contains the matched span verbatim. Enforced by a test, not a review.

Add `alias.evidence_quote` (exact substring from the page, mandatory) and `alias.target_place_type_asserted`. If you cannot paste the quote, the alias is not confirmed.

**DHA's inconsistent numbering.** Do not try to normalise it — it is not noise, it is the actual administrative history and the sources reflect it. Model it as data, not as grammar:

- Add `place.official_number` (nullable) distinct from `canonical_name`.
- Add `place_variant` (Prism/Town/Extension, M-Extension, Ex-DHA City) as a **discriminator attribute on the phase**, not as separate top-level phase entities. `ph_dha_9_prism` / `_town` / `_ext` as siblings is defensible; but `ph_dha_5` vs `ph_dha_5_mext` as siblings is *wrong* — M-Extension is a variant of Phase 5, not a phase. Two different relations expressed with one mechanism.
- Add `place_relation(child_id, parent_id, relation_kind ∈ {variant_of, renamed_to, successor_of})` with **temporal columns** `valid_from` / `valid_to`. `Phase 9 Extension → Phase 10` cannot be adjudicated without a date boundary, which is why it is dropped — and it stays dropped until `renamed_to` carries `valid_to`. That is the correct, honest resolution and it should be stated as such rather than left as an open problem.

**No sub-sub-sectors** will be needed if `place_type` is scoped to a parent. State that as the design goal.

---

### R4 — Permanent observation records → **REVISE**

**What is right.** Retaining drops permanently, with adjudication and reason, is correct and is the best structural instinct after R1. Drops are signal.

**What is missing.** The table is keyed on `(observed_string)` — but **the disambiguating evidence does not live on the string**. `Phase 9` occurs 22 times across 5 sources; in some documents it means Prism, in others Town. No amount of adjudication on the *string* can resolve that, because the disambiguating token was thrown away by the harness. This is the single most important field missing:

```
occurrence.fact_document_id   -- FK to the fetched page/table row
occurrence.char_start, char_end
occurrence.context_window     -- ±N chars verbatim
occurrence.co_located_strings -- JSON array of other place strings in the same scope
```

With document scope, `Phase 9` on a page whose heading is `DHA Phase 9 Town` resolves *compositionally against the document*, which is the mechanism R1 cannot supply and R6 forbids faking. Without it you have a dead-end table.

**Other missing fields:** `raw_string` and `normalised_string` separately (today only raw survives, so you cannot tell whether normalisation or parsing failed); `resolver_version` (which map generation produced this outcome); `adjudicated_by` / `adjudicated_at`; `adjudication_rationale` (free text — the *reason* is the asset); `evidence_url` + `evidence_quote`; `first_seen_run_id` / `last_seen_run_id`; `occurrence_count` as an **append-only** counter plus per-run deltas, not a mutable int (a mutable count cannot answer "did this get worse?").

**Adjudication over time.** Never mutate a row. Two tables:

```
observation(run_id, document_id, raw_string, normalised_string, ctx, char_start, char_end)
adjudication(id, observation_id_FK_to_canonical_run, disposition, canonical_id, reason, decided_by, decided_at, superseded_at)
```

`disposition ∈ {resolved, ambiguous, drop, not_a_place, harness_artifact, coverage_gap}`. History = rows where `superseded_at IS NULL`. Re-adjudication inserts a new row and stamps the old one. Note `not_a_place` and `coverage_gap` are **not currently in your adjudication vocabulary** — `observation.csv` only has `open` and `harness_artifact`. You cannot currently distinguish "we don't know" from "we decided this is garbage", which is the entire point of keeping drops.

**Re-evaluation on map change.** This is the mechanism R6 needs and it does not currently exist. Add:

```
resolver_run(id, map_version, started_at, completed_at, corpus_checksum)
resolution_decision(run_id, observation_id, outcome, matched_via, matched_span)
```

When the map changes: re-run *every historical observation* through the new resolver, store the decision in a **new run row**, never overwrite. Then diff `outcome` between runs. A string that flips `drop → resolved` is either a real fix or a forced match, and the diff tells you which map line changed. This is the anti-regression tripwire and it is a hard requirement, not a nice-to-have.

**Retention.** Never GC observations. Observations are the only record of what the corpus said that the map could not represent — they are the substrate for discovering that the map is wrong. Practical anti-dumping-ground measures: partition by run, index on `(normalised_string, run_id)`, and a standing dashboard of *unadjudicated volume by age* rather than a row count. An observation table becomes a dumping ground when nobody triages it; the fix is a work queue, not a deletion policy. Do not add a TTL — deletion here is strictly loss.

**Is it sufficient?** No. It preserves the string; it does not preserve the context that would let you resolve it.

---

### R5 — Inaccessible/unverified sources → **REJECT the framing; the premise is false**

**I checked both claims live. Both are wrong.**

| Source | Claim in `sources.md` | What I observed just now |
|---|---|---|
| `asaspropertiespk.com` | "No robots.txt (site not reachable at check time)"; dry-run fetch `000` | **HTTP 200.** Real, populated `robots.txt` (WordPress, disallows `/wp-admin/`, `?add-to-cart`, woo log dirs — content explicitly crawlable). Live homepage, real title, `sitemap.xml` returns 200. |
| `maanestate.com` | "No robots.txt found"; "privacy page returns 403"; "Unstated = silence, not permission" | **A 118-line `robots.txt` exists and is titled `# MAAN ESTATE - Crawl Policy`.** `User-agent: *` allows content with `Crawl-delay: 10`. The site also publishes `/llm.txt`, `/llms.txt`, `/ai.txt`, `/ai.json`, `/sitemap-ai.xml` and an `/ai/` hub. Homepage returns **HTTP 200 with a normal browser UA**; the earlier 403/000 was user-agent filtering, not a block. |

Two consequences you should act on immediately:

1. **The ToS-gate table is wrong for the one source it flagged as unknown.** MAAN ESTATE is not "unstated"; it is the most explicitly AI-permissive source in the set — it has published a machine-readable AI surface *by name*. That removes R5's biggest risk. **But it also adds an obligation the design doc missed: `Crawl-delay: 10`.** That is a hard per-request delay and it is not in your standing obligations list (which says only "rate-limit"). Add it.
2. **The dry-run's fetch layer is unreliable and produced false negatives.** A source reported unreachable is in fact reachable. That means "8 of 10 sources fetched" is an underestimate and, more dangerously, that the `observation.csv` volumes are computed over an unknown corpus. Any conclusion resting on occurrence counts inherits this.

So R5 is not "settle the flag". R5 is: **re-fetch both, with a real browser-like UA, record the actual crawl policy, and treat the reported 8/10 as unreliable.**

**Now the design question, which stands regardless.** A boolean on the fact is **not sufficient**. Reasons:

- A boolean cannot express "fetched, robots verified, but the content is a marketing page with a date on the page footer rather than on the table". That is the *common* case in this corpus, and it is the case that matters — a `rate` table dated by blog-post date is not the same epistemic object as one dated inline.
- A boolean cannot be reasoned about downstream. Your retrieval layer needs to *order* and *withhold*, which requires a **ranked** dimension, not a flag.

Required:

```
source(id, domain, crawl_policy_text, policy_checked_at, policy_http_status,
       ua_required, crawl_delay_seconds, content_verified_at, verification_state)
verification_state ∈ {verified_readable, verified_blocked, unreachable, unverified_assumed}

fact_source_verification(fact_id, source_id, content_read, quote_verified,
                         date_explicit, date_inferred_from, official_vs_rumour)
```

Three separate axes, all mandatory, none boolean-collapseable:
- `content_read` — did we actually see the text? (false ⇒ the fact does not exist in the corpus, full stop)
- `date_explicit` / `date_inferred_from` — a fact whose date comes from a post timestamp rather than the table is a **different fact_type** for your purposes; it must not be presented identically.
- `official_vs_rumour` — CDB is the only source separating these. Do not let an inferred-date rumour and an explicit-date official status land in the same column with the same rendering.

**Your framing is right and I am reinforcing it:** given a product whose entire value proposition is sourced, dated honesty, **a fact you cannot verify against a readable source must not enter the corpus at all.** Not "flagged and shown". Excluded from extraction output, retained only as an observation. Showing a user a number attributed to a page no one has read is strictly worse than saying "I don't have data on that area" — which is a claim your product is supposed to make honestly. Verified-exclusion, not user-visible-flagging.

---

### R6 — Coverage stays diagnostic → **REVISE**

**The principle is correct and should be kept.** The failure it names — a forced match raising coverage while corrupting the corpus — is real and it is the dominant long-term risk in this project.

**But the proof offered for it does not hold up, and that matters more than the principle.**

R6's stated evidence: *"8 occurrences of bare `Sector A`/`Sector B` were correctly left unresolved."* In `observation.csv`:

- `Sector A` — 8 occurrences, sources `burst;lre_lda;mohsin`, **`adjudication = harness_artifact`**
- `Sector B` — 7 occurrences, sources `burst;lre_lda`, **`adjudication = harness_artifact`**

Both are classified as **regex artifacts — "trailing prose token; NOT a map failure"** — and therefore *excluded from the genuine-miss count*. They are not recorded as correctly-unresolved ambiguities. The dry-run report then cites them as evidence that the drop rules "behaved exactly as designed". You cannot cite a bucket as evidence of correct behaviour when the same file classifies it as noise. **The proof is circular.**

Worse, `Sector B` **does not exist in `drop.csv` at all**. drop.csv has `Sector A (bare)` and `Sector F (bare)` — no `Sector B`. So `Sector B` (7 occurrences) is unadjudicated by any rule and simultaneously dismissed as an artifact. Its stated reason — *"trailing prose token"* — is also false on its face: `Sector B` has no trailing token.

The same pattern covers seven bare-sector strings, **29 occurrences**, all relabelled `harness_artifact` with the same boilerplate note, none in `drop.csv`:

`Sector A`(8), `Sector B`(7), `Sector S`(5), `Sector Z`(4), `Sector D`(3), `Sector T`(1), `Sector L`(1)

Several of these are unambiguously genuine ambiguities, not regex artifacts. `Sector S`/`Sector T`/`Sector Z`/`Sector D` are bare and are not in the drop list under any spelling. The claim *"122 observations logged, none discarded"* is technically true and materially misleading: ~29 occurrences of genuinely ambiguous input were reclassified out of the failure count with a copy-pasted justification.

**Two more arithmetic problems.**

- The **`~30% baseline` is not reproducible from any artifact.** No file records a successful resolution. `alias.csv` has no occurrence counts, `entity.csv` has no counts, and `observation.csv` records misses only. The figure appears to be `155/512` — where **155 is exactly the `harness_artifact` occurrence total**. The "resolution rate" numerator is the artifact bucket. This is not a measurement of the map; it is an artifact of the harness. Do not carry it forward as a baseline.
- The claim that `Sector A/F (bare)` drops "fired during the dry-run": **bare `Sector F` never appears in `observation.csv` at all.** `DHA Phase 9 Prism F` (6 occ) is a different string. Unsupported.

**Verdict: principle APPROVED, current enforcement and evidence REJECTED.**

**The actual mechanism that makes leakage impossible.** Prose does not work — engineers optimise the number they can see, and "coverage rate" on a dashboard is exactly that. Required:

1. **The resolver must not return a score, a rank, or a candidate list.** Its signature returns a *decision*, not a ranking: `resolve(span, document_scope) -> Resolution | Unresolved(reason)`. There is no "best match" for anyone to optimise toward. No top-N, no confidence float on a resolution.
2. **`Unresolved` is a first-class, fully-instrumented success path.** It writes an observation row with a reason code. It is not a null return and it is not logged at a level that reads as failure. If unresolved strings generate a dashboard row, the metric that gets watched becomes *rate of unadjudicated observations*, which is a queue to work, not a score to improve.
3. **Coverage lives in a separate store with separate credentials.** `coverage_rollup` in a read-only reporting schema, populated by a nightly job, never queried by the resolver path. Structurally impossible to feed back. No runtime coupling at all — this is the only bullet that truly holds.
4. **The anti-regression tripwire (from R4):** `resolver_run` + `resolution_decision` diffing. Any string that transitions `drop/ambiguous → resolved` between map versions **must** name the map change that caused it. CI fails the build on such a transition unless the commit message contains the canonical_ids added and an `alias.evidence_quote` for each. This is the only mechanism that survives a deadline.

**Detecting the regression:** CI rule on `outcome` diff between runs — any `unresolved → resolved` transition without an accompanying `place` row addition or a quoted `alias` row is a forced match and fails the build. Additionally: a hard rule that no change may reduce `unresolved` by more than N% without a linked `place`/`alias` row. And a standing review of `unresolved` volume per source: a source whose unresolved rate suddenly drops is the tell.

---

## 3. Additional findings

### 3.1 The ground-truth entities have no provenance at all — **most serious unasked finding**

`alias.csv` has `evidence` and `evidence_url`. `entity.csv` has **no evidence column whatsoever** — only a free-text `notes` field, populated on 28 of 43 rows and empty on 15.

Every fact in the system resolves to a `canonical_id`. Those canonical ids have **zero recorded evidence for their existence, parentage, or place_type**. The artifact whose entire stated purpose is preventing "internally consistent and still wrong" has assigned the identity of every place in Lahore on the strength of unevidenced prose in a `notes` column. The audit trail runs from a fact to an alias to a URL — and then stops, at a node with no provenance at all.

Required: `place.evidence_quote`, `place.evidence_url`, `place.evidence_source_id`, `place.confidence`, non-null for every place that any fact may attach to. A place with no evidence quote is an observation, not a place.

### 3.2 Two confirmed aliases cite a source that does not exist in the registry

```
Defence Phase 6  → ph_dha_6  evidence_url = https://techx.pk/
DHA P6           → ph_dha_6  evidence_url = https://techx.pk/
```

`techx.pk` is **not one of the ten registered sources** and has no recorded crawl policy. Both aliases are `confirmed = true`. This violates the project's own rule — *"per-source policy must be recorded before that source is fetched"* — and the ToS gate's scope limitation (*"cleared for known sources only"*). `techx.pk` is live (HTTP 200) and must either be registered with its policy recorded, or these two aliases must be downgraded to observations.

### 3.3 Three confirmed aliases rest entirely on a source that was never fetched

`Sector C (Main Boulevard)`, `Sector F (Talha; Safari)`, `Sector E (Johar; Iqbal)` — all `confirmed = true`, all `evidence_url` pointing at deep paths on `asaspropertiespk.com`, the source reported unreachable. **You cannot have evidence quotes from a page you never retrieved.** Either the page was reached at some point (in which case the dry-run's `000` is a false negative and the fetch layer is unreliable — see R5), or these three aliases were asserted without reading the source. Both possibilities are serious; the artifacts do not distinguish them. And per §3.2's `evidence_quote` requirement, these are exactly the rows that would have been caught.

### 3.4 Four drops cite a source that was never fetched

`Block B (bare)`, `Block D (bare)`, `Block S (bare)`, `Block X (bare)` all record `source_id = maanestate.com` — the source that returned 403 and was **never fetched**. These are observations attributed to a document nobody read. Same problem as 3.3, in the drop table.

### 3.5 The confirmed-wrong mapping is still live in the shipped data

`alias.csv` line 14: `Rahbar Sec-4 → ph_dha_11_rahbar, confirmed = true`, with `evidence_url` = the dharealestate page whose heading is `DHA Rahbar (Phase-11 Sec-4)` — **the evidence string contains the sector that the mapping discards.** The dry-run identified this as a defect and it has not been corrected in the data. Extraction is blocked, so nothing is consuming it yet — but the review's exit criterion says "R1-R3 resolved **in the schema**", and this row is the opposite of resolved.

### 3.6 The taxonomy is DHA-shaped in a way that is flagged but not understood

The flagged distortion is "five of ten sources are DHA-only". The unflagged one is worse:

- **DHA: 19 entities, of which 12 are phases and only 6 are blocks** — and all 6 sit in Phase 6 and Phase 8.
- **Zero block-level entities for Phases 7, 9, 10, 11, 12, 13** — precisely the phases where the corpus is densest (`cdb_ph10` alone contributes 176 observed occurrences).
- Meanwhile the highest-value fact types in the design doc — `balloting_status`, `litigation_status`, `possession_estimate` — are **inherently block-level** ("Ph 10 Prism, H Block litigation cleared Jul 2025"). The design has maximum phase-level depth and near-zero block-level depth, which is a mismatch between the taxonomy and the product.
- The demo question in the design doc is *"is DHA Phase 6 Block D a safe buy in 2026"* — and `blk_dha_6_d` exists only because of a hand-authored note, with no evidence, from a scheme where no source publishes block-level rates (`map.md`: *"Almost all sources publish phase-level"*, called "the single biggest gap").

**The real risk is not DHA-weight — it is that the DHA weight is phase-shaped and the product is block-shaped.** No `place_type` in R2/R3 fixes that. It requires either block-level sources or an explicit decision that v1 answers at phase granularity only. Make that decision in writing.

### 3.7 A registered source has no taxonomy at all

`burstforum.com` is a Tier-2 registered source dedicated to Askari 10 sector-level data. The map contains **exactly one Askari entity — the society itself — and zero sectors.** Five distinct sector strings / 24 occurrences observed from burst. Any Askari fact is unplaceable.

The drop reason given is also wrong: `Sector A (bare)` is dropped because *"Bahria and Askari 10 both use sector letters"* — implying a qualified `Askari 10 Sector A` would be ambiguous. It would not; the qualifier resolves it completely. The actual blocker is that **Askari has no place entities at all.** The stated reason is not the true reason, and fixing the stated reason would not fix the problem.

### 3.8 A range is modelled as a node

`sec_bahria_ab`, `canonical_name = "Sectors A-F"`, `place_type = sector`. A set of six sectors is stored as one sector. Any fact about "Sectors A–F" is a **range aggregate** and cannot be stored on a node that also serves as a leaf for a single-sector fact. It will silently merge A–F facts with F facts. Either model it as an explicit `place_group` with members, or reject range strings as `not_a_place`. A range masquerading as a leaf is the same class of error as Rahbar.

### 3.9 An entity exists for a string that is declared unresolvable

`ph_dha_9_ext` (DHA Phase 9 Extension) exists as a phase entity. `Phase 9 Extension` is in `drop.csv` as unresolvable. Both can be true only if the entity is unreachable — but nothing enforces that, and `map.md`'s note ("see drop list for the raw string") documents the contradiction instead of resolving it. An entity that exists but can never be matched is a ghost node; a fact that ever lands on it is wrong with no error. Per my R3 fix: this becomes a `renamed_to` relation to `ph_dha_10` with `valid_to = NULL` until a date boundary is sourced, and the entity is retired.

### 3.10 Missing temporal identity — a category error in the framing

The product's thesis is **dated** honesty. Facts carry `as_of`. **Places do not.** There is no `valid_from`/`valid_to`/superseded marker anywhere in `entity.csv`. Yet the corpus is full of unstable identity: Phase 9 Extension → Phase 10, Bahria G/H *"future merger pending — status unsettled"*, Pine Sector *"announced, not launched"*, balloting status changing month to month.

You cannot honestly date a *fact* about a place whose own name and boundaries changed. This is the most consequential thing missing from the schema and it is not on the R1–R6 agenda.

### 3.11 The declared `coverage` table does not exist

`map.md` line 22 declares four tables; only three CSVs exist. `coverage(canonical_id, covered_by_sources, gap_status)` has **no file**. Coverage is what R6 is entirely about, and the table that would hold it was never built. The 8 gap rows in `map.md` are prose. Make it a table — it is the substrate for R6's metric.

### 3.12 Schema drift between prose and data

- `map.md` declares `level (society|phase|block)`; `entity.csv` uses five values including `sector` and `scheme`.
- `map.md` declares `drop(alias_text, reason, source_id, seen_on)`; `drop.csv` has **no `seen_on` column**.
- `map.md` names entities `soc_bahria_orchard` / `soc_bahria_overseas`; `entity.csv` uses `sch_bahria_orchard` / `sch_bahria_overseas`. **Canonical ids are supposed to be stable and never reused — they already disagree between the prose and the fixture that will become the migration.**
- `map.md` names blocks "DHA Phase 6 Block B"; `entity.csv` names them "Block B". Since `canonical_name` is what renders into user-facing answers with a source citation, this is a display-correctness issue, not cosmetic.

The prose schema was never the source of truth and nothing kept them in sync. Pick one — the CSV — and generate the prose from it.

### 3.13 Inconsistent adjudication policy for identically-shaped inputs

Bare block letters are handled two different ways:
- `Block B`, `Block D`, `Block S`, `Block X` (bare) → **permanent drops**, reason "letters meaningless without phase".
- `Block 1`(3 occ), `Block 4`(4 occ), `Block 5`(2 occ) from mohsin — a **DHA-only source** where blocks are lettered — → **open map failures**, i.e. treated as fixable.

Same shape, opposite disposition. The numeric ones are at least as ambiguous (LDA City uses A1/B1/E1; nothing licenses `Block 4` anywhere). There is no written adjudication policy, so the same class of input gets opposite rulings depending on who was looking. Write the policy down: *shape alone determines default disposition; source identity never does.*

### 3.14 `measurement.csv` — one real error, one structural problem

- **`PKR 43.75L` is mapped with `canonical_value = lakh`.** A *currency form* has been given a *currency unit* as its canonical value. `43.75L` is a quantity; its canonical is `43.75` with unit `lakh`. As written, the row asserts that the token "PKR 43.75L" means "lakh" — losing the number entirely. Same for `Rs → lakh`. These belong in a numeric-parse table (`currency_form, prefix_multiplier`), separate from `currency(unit)`.
- **`size 4 Marla` carries the note "also commercial category"** — that is a category fact leaking into the size dimension, exactly the entanglement `map.md` open problem 4 warns about. `CCA` is a commercial *category*; `4 Marla` is a size. If they co-occur they co-occur as two facts, not one.
- The dimension conflation is fine in principle (`dimension, source_form, canonical_value, unit`) but there is **no `evidence_url` column**, so unlike `alias.csv` none of the 30 measurement mappings are evidenced either.

### 3.15 `block` vs `Sector` is decided by the *word*, not the world

The entity table uses `level=sector` for Bahria and `level=block` for DHA, driven by the words sources use. But observation shows `DHA Lahore Phase 9 Prism Sector N` and `Sector L/R/B/F/Q` appearing under **DHA** (12 occurrences) — the exact strings that made §R1's namespace problem. DHA uses "Sector" too, at a sub-phase level. So "Bahria uses sectors, DHA uses blocks" is **false as written in `map.md` and `entity.csv` notes**. The correct statement is per-parent: DHA phases have `block` children; DHA Phase 9 Prism has `sector` children; Bahria has `sector` children. Any `place_type` design must be keyed on the parent, not the society — which is exactly R2's proposal, so R2 is right and the current notes contradict it.

### 3.16 Roman numeral handling has a hole

`DHA Phase VI → ph_dha_6` and `DHA Phase IX Prism L` appear in observations. The alias evidence for `Phase VI` cites `lahorerealestate.com`. Nothing in the design normalises Roman numerals. I, however, would **reject Roman-numeral normalisation as a silent transform** — `Phase VI` → 6 is only valid if the numeral is unambiguous in that source's convention, and DHA's own numbering (Phase 9 Prism / Town / Extension, Phase 11 Rahbar, Phase 13 Ex-DHA City) shows the numeral is not a reliable index. Normalise, but record `numeral_system ∈ {arabic, roman}` on the observation and never let a roman form resolve where the arabic form would not.

---

## 4. Data integrity check

**Referential integrity: clean.**

```
entity.csv          43 rows, 43 unique canonical_id, 0 duplicates        OK
dangling parent_id  0                                                  OK
alias.csv           23 rows, 0 pointing at nonexistent canonical_id     OK
duplicate alias_text 0                                                  OK
canonical_name collisions  0                                           OK
drop.csv            19 rows, 0 duplicate alias_text                     OK
observation.csv     122 rows, 122 distinct, 0 duplicates                OK
```

**Count reconciliation: consistent.**

```
observation occurrences total            512   matches dryrun baseline
  adjudication=open             50 rows / 357 occ   matches "50 genuine failures"
  adjudication=harness_artifact 72 rows / 155 occ   matches "72 artifacts / 155 occ"
```

**But five substantive violations exist, all of which the integrity check cannot see:**

| # | Violation | Severity |
|---|---|---|
| V1 | `alias.csv:5,6` — `Defence Phase 6`, `DHA P6` — `confirmed=true`, `evidence_url=https://techx.pk/`, **a domain absent from the 10-source registry and with no recorded crawl policy** | High — violates the project's own per-source-policy rule |
| V2 | `alias.csv:18,19,20` — three Bahria sector aliases `confirmed=true` on `evidence_url` at `asaspropertiespk.com`, **the source the dry-run reported as never fetched** | High — evidence cited from an unread page |
| V3 | `drop.csv:11,12,13,14` — `Block B/D/S/X (bare)` cite `source_id=maanestate.com`, **never fetched (403)** | High — observations attributed to an unread document |
| V4 | `alias.csv:14` — `Rahbar Sec-4 → ph_dha_11_rahbar, confirmed=true`; the cited evidence heading is `DHA Rahbar (Phase-11 Sec-4)`, **i.e. the evidence refutes the mapping. Identified as a defect in the dry-run and never corrected.** | High — the exact "internally consistent and still wrong" failure, live in the data |
| V5 | `map.md` declares `coverage` table + `drop.seen_on`; neither exists. `map.md` declares `level(society\|phase\|block)`; `entity.csv` uses 5 values. `map.md` ids `soc_bahria_*` vs `entity.csv` `sch_bahria_*`. | Medium — prose schema is not the source of truth and has already drifted |

**Drop-logic violations:**

| # | Violation | Severity |
|---|---|---|
| V6 | `Sector B`(7 occ), `Sector S`(5), `Sector Z`(4), `Sector D`(3), `Sector T`(1), `Sector L`(1) — **29 occurrences** of bare sector letters, all labelled `harness_artifact` with the boilerplate reason *"trailing prose token"* (these strings have no trailing token), and **none present in `drop.csv`**. Genuine ambiguities relabelled as regex noise and excluded from the failure count. | High — understates the map's failure surface by ~29 occurrences and contradicts "none silently discarded" |
| V7 | `Sector A`(8 occ) and `Sector B`(7 occ) — cited by R6 as proof that correct drops "behaved as designed" — are classified `harness_artifact` in the same artifact set. **R6's only empirical proof is circular.** | High — invalidates R6's evidence |
| V8 | Bare `Sector F` **never appears in `observation.csv`**, yet dryrun-report states the `Sector A/F (bare)` drops "fired during the dry-run". `DHA Phase 9 Prism F` is a different string. | Medium — unsupported claim |
| V9 | `ph_dha_9_ext` (entity) and `Phase 9 Extension` (drop) coexist — a resolvable entity and an unresolvable string for the same referent, with no invariant preventing the entity being populated. | Medium — guaranteed-wrong node |
| V10 | Bare `Block B/D/S/X` → permanent drop; bare `Block 1/4/5` from a DHA source → "open, fixable". Same shape, opposite disposition, no written policy. | Medium — adjudication is not reproducible |

**Metric violations:**

| # | Violation | Severity |
|---|---|---|
| V11 | The **`~30% resolution rate` is not reproducible from any artifact** — no file records a single successful resolution. The figure appears to be `155/512`, and **155 is exactly the `harness_artifact` occurrence total**. The numerator of the "resolution rate" is the noise bucket. | High — the headline baseline is an artifact of the harness, not a measurement |
| V12 | `entity.csv` has **no `evidence`/`evidence_url` column** — 43 of 43 canonical entities are unevidenced; the audit trail terminates at an unevidenced node. 15 of 43 have empty `notes`. | High — see §3.1 |
| V13 | `measurement.csv:22,23` — `PKR 43.75L → canonical_value=lakh`, `Rs → canonical_value=lakh`. A quantity mapped to a unit; the number is destroyed. No `evidence_url` column on any of the 30 rows. | Medium |

**Live verification of R5 — both premise claims falsified:**

```
asaspropertiespk.com   → HTTP 200, real robots.txt, live homepage, sitemap 200
                        sources.md says "No robots.txt (site not reachable at check time)"  ← FALSE
maanestate.com/robots.txt → HTTP 200, 118 lines, titled "# MAAN ESTATE - Crawl Policy"
                        User-agent: * → content allowed, Crawl-delay: 10
                        sources.md says "No robots.txt found"                            ← FALSE
maanestate.com/       → HTTP 200 with browser UA (403/000 was UA filtering)
                        publishes /llm.txt, /ai.json, /sitemap-ai.xml, /ai/ hub
```

I verified these directly. The claimed unverifiable state of both sources is wrong, and the ToS-gate row for MAAN ESTATE ("unstated = silence") is wrong in the direction that *reduces* risk — but the gate table is not evidence-grade, and the fetch layer produced two false negatives.

---

## 5. Revised schema

Django. Postgres (needs `JSONB`, `ltree` not required, but partial indexes and `CHECK` constraints are essential — most of the invariants below are `CHECK`s, and they are the point).

### 5.1 Core place model

```python
# app: places

class Society(models.Model):
    id = models.TextField(primary_key=True)              # stable, never reused
    name = models.TextField()
    city = models.TextField(default="Lahore")
    # R2: relation state between different place_type namespaces
    lra_relation_state = models.CharField(
        choices=[("observed", "observed"), ("unknown", "unknown")],
        default="unknown",
    )
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            # A society with UNKNOWN multi-namespace relations must not be resolvable
            models.CheckConstraint(
                check=Q(lra_relation_state="observed")
                      | ~Q(place_types__count__=2),
                name="single_namespace_needs_no_relation_state",
            ),
        ]
```

```python
class PlaceType(models.Model):
    """Declared vocabulary of partition types. Referenced by Place.child_namespace."""
    code = models.TextField(primary_key=True)   # 'block' | 'sector' | 'sub_sector' | 'phase' | 'scheme'
    label = models.TextField()

class Namespace(models.Model):
    """A namespace a trailing bare token can be typed INTO.
    This is what disambiguates 'Prism 10' (sector) from 'Town 5' (size)."""
    id = models.TextField(primary_key=True)     # 'ph_dha_9_prism:sector' | 'ph_dha_9_town:size'
    place_type = models.ForeignKey(PlaceType, on_delete=models.PROTECT)
    token_pattern = models.TextField()          # r'^[A-Z]$' | r'^\d+$' | r'^(?:[A-Z]|\d+)$'
    description = models.TextField()

class Place(models.Model):
    id = models.TextField(primary_key=True)
    name = models.TextField()                   # OUR canonical display name
    official_number = models.IntegerField(null=True)   # DHA's own number, nullable & often absent
    parent = models.ForeignKey("self", null=True, on_delete=models.PROTECT,
                               related_name="children")
    place_type = models.ForeignKey(PlaceType, on_delete=models.PROTECT)
    city = models.TextField(default="Lahore")

    # §3.1 — the ground truth must be evidenced. Non-null below the society level.
    evidence_quote = models.TextField(null=True)
    evidence_url = models.TextField(null=True)
    evidence_source = models.ForeignKey("corpus.Source", null=True, on_delete=models.PROTECT)

    status = models.CharField(
        choices=[("active", "active"), ("announced", "announced"),
                 ("merger_pending", "merger_pending"), ("retired", "retired")],
        default="active",
    )
    resolvable = models.BooleanField(default=True)   # False for candidate/ghost nodes

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_name_under_parent"),
            # §3.1 every non-society place must carry evidence
            models.CheckConstraint(
                check=Q(place_type__code="society")
                      | (Q(evidence_quote__isnull=False) & Q(evidence_url__isnull=False)),
                name="non_society_place_requires_evidence",
            ),
            # a place may not be its own ancestor
            models.CheckConstraint(check=~Q(parent_id=models.F("id")), name="no_self_parent"),
        ]
```

```python
class PlaceEdge(models.Model):
    """R2: second edge dimension from day one. Single parent stays the taxonomic
    fast path; this is what makes the LDA/Bahria migration additive, not a rewrite."""
    RELATIONS = [("taxonomic", "taxonomic"), ("partition_of", "partition_of"),
                 ("renamed_to", "renamed_to"), ("variant_of", "variant_of"),
                 ("successor_of", "successor_of"), ("overlaps", "overlaps"),
                 ("unknown", "unknown")]
    child = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="edges_out")
    parent = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="edges_in")
    relation_kind = models.CharField(choices=RELATIONS)
    # §3.10 temporal identity — facts are dated, places must be too
    valid_from = models.DateField(null=True)
    valid_to = models.DateField(null=True)
    evidence_quote = models.TextField(null=True)
    evidence_url = models.TextField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["child", "relation_kind"],
                                    name="uniq_child_per_relation_kind"),
            models.CheckConstraint(check=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                                   name="valid_range_ordered"),
        ]
```

**LDA City rule (R2b):** for `soc_lda_city`, `lra_relation_state = 'unknown'`. `Place.resolvable = False` on every LDA City child, enforced in the resolver: an LDA City place may only be written as `PlaceCandidate` + observation. Do not guess the nesting. V1 ships without resolved LDA City places; that is the correct trade.

### 5.2 Naming, aliases, and the evidence gate

```python
class SocietyQualifier(models.Model):
    """R1: the society slot. Mandatory for resolution below society level."""
    token = models.TextField(primary_key=True)   # 'dha', 'dha lahore', 'defence', 'bahria', ...
    society = models.ForeignKey(Society, on_delete=models.CASCADE)
    # false for 'gulberg' (a zone, not a society) -> resolves to no society
    is_society_name = models.BooleanField(default=True)

class ScopeToken(models.Model):
    """Disambiguates phases with the same number: prism / town / extension /
    rahbar / m-extension / ex-dha city."""
    token = models.TextField(primary_key=True)
    phase_number = models.IntegerField()
    variant_code = models.CharField(max_length=32)
    evidence_quote = models.TextField()
    evidence_url = models.TextField()

class Alias(models.Model):
    id = models.BigAutoField(primary_key=True)
    alias_text = models.TextField()
    canonical = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="aliases")
    # R3 — the anti-Rahbar gate
    evidence_quote = models.TextField()                 # exact substring, MANDATORY
    evidence_url = models.TextField()
    evidence_source = models.ForeignKey("corpus.Source", on_delete=models.PROTECT)
    asserted_place_type = models.ForeignKey(PlaceType, on_delete=models.PROTECT)
    confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True)
    confirmed_by = models.TextField(null=True)
    # §3.2/§3.3 — registry membership is enforced, not documented
    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(confirmed) == Q(evidence_quote__regex=r"\S"),
                                   name="confirmed_requires_quote"),
            models.UniqueConstraint(fields=["alias_text", "canonical"], name="uniq_alias_per_target"),
        ]
```

**Required migration, before anything else:** `Rahbar Sec-4 → ph_dha_11_rahbar` must be **retracted** (`confirmed=false`, disposition `drop`, reason `flattened level`). Then create `sec_dha_11_rahbar_4` under `ph_dha_11_rahbar` with the quoted evidence, and `variant_of` edge `ph_dha_5_mext → ph_dha_5` with `relation_kind='variant_of'` (M-Extension is a variant of Phase 5, not a sibling phase). Retire `ph_dha_9_ext` into a `renamed_to` edge to `ph_dha_10` with `valid_to=NULL` until a date boundary is sourced.

### 5.3 Observations and adjudication (R4)

```python
class ResolverRun(models.Model):
    id = models.BigAutoField(primary_key=True)
    map_version = models.TextField()             # bumped on every map change
    corpus_checksum = models.TextField()
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

class Document(models.Model):
    """R4 — the missing grain. Scope is what disambiguates bare 'Phase 9'."""
    id = models.BigAutoField(primary_key=True)
    source = models.ForeignKey("corpus.Source", on_delete=models.CASCADE)
    url = models.TextField()
    fetched_at = models.DateTimeField()
    content_sha256 = models.CharField(max_length=64)
    heading = models.TextField(blank=True)        # often the disambiguator itself

class Observation(models.Model):
    """Append-only. One row per (run, document, span). Never updated, never deleted."""
    run = models.ForeignKey(ResolverRun, on_delete=models.CASCADE)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    raw_string = models.TextField()              # never normalised away
    normalised_string = models.TextField()
    char_start = models.IntegerField()
    char_end = models.IntegerField()
    context_window = models.TextField()          # +/- 200 chars verbatim
    co_located_strings = models.JSONField(default=list)   # other place strings in scope
    numeral_system = models.CharField(
        choices=[("arabic", "arabic"), ("roman", "roman")], default="arabic")
    outcome = models.CharField(
        choices=[("resolved", "resolved"), ("unresolved", "unresolved"),
                 ("drop", "drop"), ("harness_artifact", "harness_artifact")],
        default="unresolved",
    )
    reason_code = models.TextField(blank=True)   # machine-readable, see below
    canonical = models.ForeignKey(Place, null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "document", "char_start", "char_end"], name="uniq_span_per_run"),
        ]
        indexes = [models.Index(fields=["normalised_string", "run"])]
```

`reason_code` vocabulary (required — the current `open`/`harness_artifact` pair cannot distinguish "we don't know" from "this is garbage"):
`ambiguous_bare_society` · `ambiguous_bare_phase` · `ambiguous_bare_letter` ·
`namespace_undeclared` · `society_slot_missing` · `city_mismatch` ·
`not_a_place` · `coverage_gap` · `below_resolution_floor` · `harness_artifact`

```python
class Adjudication(models.Model):
    """Append-only history. Re-adjudication inserts; never mutates."""
    id = models.BigAutoField(primary_key=True)
    observation = models.ForeignKey(Observation, on_delete=models.CASCADE)
    disposition = models.CharField(choices=[
        ("resolved", "resolved"), ("ambiguous", "ambiguous"), ("drop", "drop"),
        ("not_a_place", "not_a_place"), ("coverage_gap", "coverage_gap"),
        ("harness_artifact", "harness_artifact")])
    canonical = models.ForeignKey(Place, null=True, on_delete=models.SET_NULL)
    reason = models.TextField()
    decided_by = models.TextField()
    decided_at = models.DateTimeField(auto_now_add=True)
    superseded_at = models.DateTimeField(null=True)   # current row: NULL

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(superseded_at__isnull=True) == Q(disposition="harness_artifact") | Q(True),
                name="placeholder"),
        ]
```

Simplify: drop that placeholder; enforce "exactly one non-superseded adjudication per observation" in application code plus a partial unique index:

```python
    class Meta:
        indexes = [models.Index(fields=["observation"], condition=Q(superseded_at__isnull=True),
                                name="uniq_current_adjudication")]
```

```python
class PlaceCandidate(models.Model):
    """§3.6 — unresolvable places are recorded as candidates, not as Places."""
    observation = models.ForeignKey(Observation, on_delete=models.CASCADE)
    proposed_name = models.TextField()
    proposed_parent = models.ForeignKey(Place, null=True, on_delete=models.SET_NULL)
    blocked_reason = models.TextField()
```

**Retention: no TTL, no GC, ever.** Partition `Observation` by `run_id` monthly for query performance only. Operational anti-dumping-ground measure is a work queue: `unadjudicated volume by age`, surfaced as a count of items to triage — never as a percentage to improve.

### 5.4 Sources and provenance (R5)

```python
class Source(models.Model):
    id = models.TextField(primary_key=True)
    domain = models.TextField(unique=True)
    name = models.TextField()
    crawl_policy_text = models.TextField(blank=True)
    policy_checked_at = models.DateTimeField(null=True)
    policy_http_status = models.IntegerField(null=True)
    ua_required = models.BooleanField(default=False)
    crawl_delay_seconds = models.IntegerField(default=0)   # maanestate = 10
    verification_state = models.CharField(
        choices=[("verified_readable", "verified_readable"),
                 ("verified_blocked", "verified_blocked"),
                 ("unreachable", "unreachable"),
                 ("unverified_assumed", "unverified_assumed")])
    content_verified_at = models.DateTimeField(null=True)

class SourceObservation(models.Model):
    """§3.2/§3.3/§3.4 — registry membership enforced in the DB, not in a doc."""
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    observed_on = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "observed_on"], name="uniq_source_day"),
        ]
```

**Enforce that every `evidence_url` host resolves to a registered `Source`.** This one constraint kills V1, V2 and V3 permanently and makes the whole class of "evidence from a page nobody read" impossible. Implement as a `CheckConstraint` over a denormalised `evidence_host` column, or as a `NOT NULL` FK `evidence_source` — prefer the FK.

**Verification axes for facts (R5) — three booleans, not one flag:**

```python
class ClaimVerification(models.Model):
    claim = models.OneToOneField("facts.Claim", on_delete=models.CASCADE)
    content_read = models.BooleanField()        # did we actually see this text?
    quote_verified = models.BooleanField()     # does raw_quote appear verbatim in the cached page?
    date_explicit = models.BooleanField()      # is the date on the datum, not the post?
    date_inferred_from = models.ForeignKey(Document, null=True, on_delete=models.SET_NULL)
    official_vs_rumour = models.CharField(
        choices=[("official", "official"), ("reported", "reported"),
                 ("rumour", "rumour"), ("unknown", "unknown")], default="unknown")

    class Meta:
        constraints = [
            # R5's core rule, in the database:
            # a fact from a source whose content was never read does not exist
            models.CheckConstraint(
                check=Q(content_read=True),
                name="unread_source_cannot_produce_a_fact",
            ),
        ]
```

**Also register `techx.pk`** (V1) with its robots policy recorded, or retract the two aliases citing it. `techx.pk` is live.

### 5.5 Measurements (fixes §3.14)

```python
class Currency(models.Model):
    code = models.TextField(primary_key=True)   # 'PKR'

class CurrencyForm(models.Model):
    """'43.75L' is a QUANTITY. It is not the unit 'lakh'."""
    surface_form = models.TextField(primary_key=True)   # 'L', 'Lac', 'Lakh', 'Lacs', 'Cr', 'Crore'
    multiplier = models.DecimalField(max_digits=18, decimal_places=4)  # 100000, 10000000
    evidence_url = models.TextField()

class Size(models.Model):
    id = models.TextField(primary_key=True)     # 'marla_20'
    marla = models.DecimalField(max_digits=8, decimal_places=2)   # single canonical: 20 marla
    evidence_url = models.TextField(null=True)
    # '1 Kanal' -> Size(marla=20). Never a second size. Sources assert the equivalence.

class SizeForm(models.Model):
    surface_form = models.TextField(primary_key=True)
    size = models.ForeignKey(Size, on_delete=models.PROTECT)
    evidence_url = models.TextField()

class CategoryDimension(models.Model):
    """'CCA-3' is a commercial CATEGORY. It is never a size and never a place.
    '4 Marla' carries note 'also commercial category' — that note is the bug;
    category and size are orthogonal and co-occur as two facts."""
    surface_form = models.TextField(primary_key=True)
    canonical = models.TextField()             # 'cca3' | 'allocation' | 'affidavit' | ...
    kind = models.CharField(choices=[("file_type", "file_type"),
                                     ("file_status", "file_status"),
                                     ("commercial_category", "commercial_category")])
    evidence_url = models.TextField(null=True)
```

### 5.6 Resolution algorithm

```python
# place/resolver.py  -- pure function. Returns a DECISION, never a ranking.

class Resolution(NamedTuple):
    canonical_id: str | None
    matched_via: str | None      # 'alias' | 'composition' | 'document_scope'
    matched_span: str | None     # verbatim text that justified it
    reason_code: str | None

def resolve(raw: str, doc: DocumentScope) -> Resolution:
    n = normalise(raw)                       # hyphen/space/roman -> arabic; raw is kept separately

    # 0. IRREGULAR FORMS FIRST -- the only path that may accept a whole-string match.
    a = Alias.objects.filter(alias_text=n, confirmed=True).first()
    if a:
        assert a.evidence_quote in fetch(a.evidence_url)   # R3 gate, runtime
        return Resolution(a.canonical_id, "alias", a.evidence_quote, None)

    slots = tokenize(n)                      # -> (society, phase_no, scopes[], tail)

    # 1. SOCIETY SLOT IS MANDATORY below society level. No default, ever.
    if slots.society is None:
        if slots.is_society_level_only:
            return Resolution(None, None, None, "society_slot_missing")
        return Resolution(None, None, None, "ambiguous_bare_society")

    society = slots.society
    if society.lra_relation_state == "unknown" and needs_cross_namespace(slots):
        # R2b -- LDA City. We do not know how blocks relate to sectors. Refuse.
        PlaceCandidate.record(doc, raw, slots, blocked_reason="lra_relation_unknown")
        return Resolution(None, None, None, "below_resolution_floor")

    # 2. PHASE -- number alone is not enough; scope tokens select the variant.
    if slots.phase_no is not None:
        phases = Place.objects.filter(
            parent=society, place_type__code="phase", resolvable=True)
        if slots.scopes:
            phases = phases.filter(
                official_number=slots.phase_no,
                edges_out__relation_kind="variant_of",
                edges_out__parent__place_type__code="scope_token",
                edges_out__parent__name__in=slots.scopes)
        else:
            # R1: 'DHA Phase 9' with no scope token -> MULTIPLE real candidates.
            # Refusing here is the entire defence of R6.
            cands = list(phases.filter(official_number=slots.phase_no))
            if len(cands) != 1:
                return Resolution(None, None, None, "ambiguous_bare_phase")
            phases = [cands[0]]
        if not phases.exists():
            return Resolution(None, None, None, "coverage_gap")
        node = phases.get()

        # 3. PARENTHETICALS ARE DISCRIMINATORS, NOT DECORATION.
        #    Never strip-and-base-match: that turns a visible miss into a silent merge.
        #    Strip them for the phase lookup, then re-attach to select the child.
        for paren in slots.parentheticals:
            child = node.children.filter(
                name__iexact=paren, resolvable=True).first()
            if child is None:
                return Resolution(None, None, None, "ambiguous_bare_letter")
            node = child

        # 4. TRAILING NUMERAL -- typed by the parent's DECLARED namespace.
        #    'Prism 10' -> sector 10. 'Town 5' -> size 5. Never both. Never guessed.
        if slots.tail is not None:
            ns = node.child_namespace          # may be NULL -- that is the answer
            if ns is None:
                return Resolution(None, None, None, "namespace_undeclared")
            if not re.fullmatch(ns.token_pattern, slots.tail):
                return Resolution(None, None, None, "ambiguous_bare_letter")
            child = node.children.filter(name__iexact=slots.tail,
                                         place_type=ns.place_type).first()
            if child is None:
                return Resolution(None, None, None, "coverage_gap")
            node = child
        return Resolution(node.id, "composition", n, None)

    # 5. NO PHASE: society-level place, or an unresolvable leaf.
    #    'Sector A' / 'Block B' / 'Gulberg' land here and MUST land here.
    cand = society.children.filter(name__iexact=n, resolvable=True).first()
    if cand is None:
        return Resolution(None, None, None, "ambiguous_bare_letter")
    return Resolution(cand.id, "composition", n, None)
```

**Composition loop rules, stated as invariants:**
1. Society slot mandatory below society level. No default society. Ever.
2. A trailing numeral resolves only against the parent's declared `child_namespace`. If undeclared → `namespace_undeclared`, never a guess.
3. Parenthesised content is a discriminator; it is never stripped for the final decision.
4. If a phase number matches >1 place under the society with no scope token → `ambiguous_bare_phase`. **Do not break the tie with document context inside the resolver.** Document scope is a separate, explicitly-labelled path (`matched_via='document_scope'`) that must record which document token was used. Mixing them silently is how `Phase 9` becomes a coin flip.
5. A place with `resolvable=False` is never returned.
6. No path returns a candidate list, a score, or a rank.

### 5.7 Anti-regression enforcement (R6's actual mechanism)

```python
# tests/test_no_forced_matches.py  -- CI gate, runs on every map change

def test_no_new_resolutions_without_evidence():
    """V11/V7: any unresolved -> resolved transition must be justified by a
    NEW Place row or a NEW confirmed Alias carrying an evidence quote."""
    for change in diff_outcomes(previous_run(), current_run()):
        if change.old == "unresolved" and change.new == "resolved":
            assert change.matched_via == "alias" and change.evidence_quote
            # or
            assert change.matched_via == "composition" and change.place_row_added

def test_no_metric_on_the_resolution_path():
    """The resolver module must not import the reporting schema."""
    src = Path("place/resolver.py").read_text()
    for forbidden in ("coverage_rollup", "coverage_rate", "resolution_rate"):
        assert forbidden not in src
```

Structural guarantees, in order of how much they actually hold:
1. **Resolver returns a decision, not a ranking.** No top-N, no confidence float. Nothing to optimise toward.
2. **Coverage lives in a separate Postgres schema with a read-only role**, populated by a nightly job. The resolver's DB user has no `SELECT` on it. This is the only bullet that is genuinely impossible to bypass.
3. **`resolver_run` + `observation.outcome` diffing**, enforced by the test above.
4. **The watched metric is `unadjudicated observations by age`** — a work queue, not a percentage. A rate to improve is a rate that will be improved.

---

## 6. What I would build first, and what I would refuse to build

### Build first, in this order

1. **Fix the data, not the schema.** Five violations (V1–V5) are wrong rows in shipped CSVs, not design problems. Retract `Rahbar Sec-4`, retract or evidence the `techx.pk` and `asaspropertiespk` aliases, re-source or void the four `maanestate` drops, register `techx.pk`, reconcile `map.md` ids against `entity.csv`. **Do this before writing a line of Django.** A correct schema over wrong rows produces a wrong corpus more confidently than the current one.
2. **Re-fetch both "unverified" sources with a browser UA** and record real crawl policies. Includes honouring MAAN ESTATE's `Crawl-delay: 10`. This closes R5 empirically and corrects the ToS-gate table.
3. **Evidence every existing `Place`** (§3.1) — `evidence_quote` + `evidence_url` + registered source. 43 rows. Non-negotiable; the audit trail currently dead-ends.
4. **`evidence_source` FK constraint on `Alias.evidence_url` host.** One constraint, permanently kills the entire V1/V2/V3 class.
5. **The normaliser + tokenizer + resolver as a pure function**, with `Observation` written on **both** paths — resolved and unresolved. Uninstrumented successes are how the ~30% baseline became unreproducible in the first place.
6. **`ResolverRun` / `Observation` / `Adjudication` / the CI no-forced-matches test.** The tripwire must exist *before* the metric improves for any reason, or it is decoration.
7. **Adjudicate the 29 orphaned bare-sector occurrences** (§V6). They are currently mislabelled and are suppressing a real ~29-occurrence failure surface.
8. **Then, and only then, re-run the dry-run** on the fixed resolver.

### Refuse to build until something else is true

- **Any extraction, at all**, until 1–7 are done. The block is correct, but for a stronger reason than the doc gives: the current map would attach facts to unevidenced places, and the map's own known-wrong row is `confirmed=true`. Extraction would make that silent within one ingest run.
- **Any resolved LDA City place** until a source states how blocks relate to sectors. Two fake hierarchies is worse than none. Ship LDA City as `PlaceCandidate` + `coverage_gap`.
- **Any fact from a source whose content has not been read.** Not flagged-and-shown — excluded. For a product whose whole claim is sourced honesty, an unverifiable number is a defect, and "I don't have data on that area" is the correct answer.
- **The 30% baseline as a target.** It is not reproducible from any artifact (V11), and its numerator appears to be the regex-noise bucket. Discard it. Re-establish the baseline from run 1 of the fixed resolver, recording successes.
- **Any `sub_sector` tree level.** Rejected — it is a scope label, not a depth, and it will need sub-sub-sectors within a quarter.
- **Roman-numeral normalisation as a silent transform** — record `numeral_system` and require roman forms to satisfy the same gates as arabic.
- **Block-level granularity as a product claim.** 6 block entities exist, all in Phases 6 and 8, none evidenced, from sources that mostly publish phase-level rates. Either source block-level data or commit in writing that v1 answers at phase granularity. Do not let the demo question imply otherwise.
- **Public launch**, per the doc's own note — but note that the social-risk argument in the design doc now applies most sharply to MAAN ESTATE and ASAS, the two most machine-readable and most AI-explicit sources in the set.

### The one thing I would change about how this project is being run

The process found the Rahbar flattening bug *by accident* — a slightly different string happened to be observed. The same process shipped that wrong mapping as `confirmed=true`, with an `evidence_url` whose own heading contradicts it, and shipped two more confirmed aliases citing a domain not in the registry. **The dry-run is a good bug detector and a bad verifier.** Every one of V1–V5 would have been caught in seconds by the two constraints in §5.4 (`evidence_source` FK, `confirmed_requires_quote`) and §5.2 (`asserted_place_type` check). Build the verifier. The detectors are already earning their keep.