# Milestone 6 — Cue contract + metadata dates: DONE ✅

**125 tests. V3 refusals 11 → 2. Facts accepted 2 → 5.**

**V10 fact-type cue** — vocabulary in `data/normalization/fact_type_cues.csv`,
47 cues, corpus-derived with per-cue counts. 9 cues have zero corpus occurrences and
are marked `proven_in_corpus=False` rather than dropped, with a test asserting they
survive so the vocabulary can't be quietly narrowed. Rejections name what the quote
*does* speak: `quote does speak: balloting_status`.

**V6 tightened** — it missed the quote, so `DHA Phase 6 CCA-3 ... 600 Lacs` was
accepted as a *residential* rate when it is commercial. Now checks quote + value +
place_ref and names which.

**Metadata dates** — `Document.published_dates` from `<meta>`/`<time>`. Test asserts
absence still refuses rather than inventing.

### Open gap, deliberately not fixed

**A `rate` fact carries only the number.** `133.00 Lacs` and `218 Lacs` are correct but
don't record which size or file type they belong to. A rate is only meaningful as
`(place, size, file_type, amount)`. Also: `file_type` as a standalone `fact_type` is
near-useless — file type is *qualifier* information for a rate.

Both are data-model gaps, not validator gaps. Fix before the chat interface, or every
answer about price will be ambiguous.

---

# Milestone 5 — Real-page extraction: DONE ✅

**5 real pages, 27 candidates, 2 accepted, 25 rejected. 107 tests OK.**

It earned its place by finding **V9 place corroboration**, which was not in the
contract: a `Rahbar Sector-4` fact quoted from a **DHA Phase 9 Town** sentence
passed V1-V8 and would have entered the knowledge base fully sourced and dated.
V9 now requires the resolved place to be corroborated by a mention *before* the
quote.

Three bugs in V9 itself, all found by real data: a symmetric window that covered
whole short documents; `Rahbar Sector-4` generating a bogus `phase 4` marker; and
`dha lahore` acting as a marker that matches every DHA page. V9 then caught a
wrong-entity case I had written into our own test suite.

**Two open findings, deliberately not papered over:**
1. **V8 checks fact_type is in the allowed set, not that it matches the quote.**
   A balloting fact filed as `possession_status` passes every validator. Needs a
   fact-type ↔ cue-word contract. Until then `fact_type` is the least trustworthy
   field in the corpus.
2. **V3's 11 rejections are an ingestion gap**: `html_to_text` drops `<head>`, so
   the published date is absent from the body. Documents need a metadata date.

**No live LLM call was made** — no credentials in the environment. The proposer was
the engineer reading the page. `LLMProposer` ships and needs `ANTHROPIC_API_KEY`.

---

# Milestone 4 — Extraction Boundary: IMPLEMENTED ✅

**Validators live in `corpus/validators.py`. 31 boundary tests, all passing.**
Full suite: 102 tests.

Both non-negotiable negatives pass:
| Test | Rejected by |
|---|---|
| invented value + genuine quote | **V2** |
| genuine candidate + fabricated quote | **V1** |

A control test asserts a genuine candidate passes. It caught a real V3 bug: the
validator compared the model's ISO date against the page's "25 August 2026". Fixed
with date normalisation, not by relaxing the check.

Validator order: V1 → V2 → V3 → V8(tier) → V7 → V5 → V6 → V4. **V5 deliberately
precedes V4** so a cross-city rejection records *why*, not just that resolution failed.
No live LLM calls yet.

---

# Milestone 4 — Extraction Boundary: DECIDED (original brief)

**Contract written to `docs/designs/lahore-aarea-gyan-engine.md` -> "Extraction
Boundary — LLM Contract". No extraction code written.**

- **Rule:** every LLM output must be reconstructible from its quote by a deterministic
  function. If nothing can verify it, it does not enter the knowledge base.
- **The LLM never names a place.** It is handed a `Place` id.
- **Tier 1 only** (extractable values). Tier 2 (derived) refused in v1 — a derived
  value that cannot be recomputed when inputs are corrected is the exact failure this
  project prevents. Tier 3 never.
- **Seven deterministic validators**, V1-V7. V4 (entity binding) and V7 (no
  self-promotion) are structural — the bad states cannot be constructed.
- **Rejections persist** as `Observation` with `adjudication='dropped'` and the
  validator id. Never retried into acceptance, never discarded.
- **First tests to write are negative:** invented rate rejected by V2; fabricated
  quote rejected by V1.

LLM extraction remains blocked until the contract is implemented and tested.

---

# Milestone 3 — Block Identity: IMPLEMENTED ✅

**Status: built and passing.** 71 tests OK.

| Criterion | Result |
|---|---|
| Reproduce baseline | **1351 / 2,725 = 49.6%** (the measured ceiling) |
| Cross-city false matches | **0** |
| Forced adjudications | **0** |
| Block identities | 57 (56 single-source, **1 corroborated**) |
| Label conflicts recorded | 2 |
| Bare letters refused | pass |

## Why this is NOT R3 resurrected

`BlockIdentity` is a separate model, **not** a `Place` with `level=block`. It asserts
no hierarchy:
- `letter` is the source's identifier, not a surveyed block name
- `labels_observed` stores the words the source used (`Block` / `Sector` / both)
  and is never interpreted
- the phase is a **reference**, not a parent assertion about geography

A test asserts no `Place` row exists for any letter — if one appears, R3 is back.

## The promotion rule (structural)

`verified=True` requires `source_count >= 2`. Enforced three ways:
1. `BlockIdentity.clean()` raises `ValueError` on single-source promotion
2. `promote_block_identities --apply` is the only write path, and it re-runs `full_clean()`
3. A test asserts the sole corroborated identity is `DHA Phase 5 [M]`
   (lahorerealestate + mohsinestate) and that 56 remain blocked

Single-source identities resolve, cite their source, and carry the limitation. They
cannot silently harden into fact.

## Investigation that preceded it

Q1 phase evidence: YES. Q2 cross-source identity: **NO** (58 of 59 single-source).
Q3 repeated letters: 23 of 27 identifiers repeat across phases within one source, and
2 pairs carry contradictory labels. Q4 terminology without hierarchy: YES, trivially,
by not making it a level at all.

Gain: 1140 -> 1351 (+211), exactly the measured ceiling.

---

# Milestone 2 — Society Slot: IMPLEMENTED ✅

**Status: built and passing.** 46 tests OK (25 from M1 + 21 new).

| Criterion | Result |
|---|---|
| Reproduce baseline | **1140 / 2,725 = 41.8%** |
| Cross-city false matches | **0** |
| Cross-city held as drops | 204 |
| Forced adjudications | **0** |
| Drop-policy violations | **0** |
| Society bindings | Bahria Town, LDA City, Lake City, Askari 10, Gulberg III |

Gain: 992 -> 1140 (+148 net). Ceiling audited at 42%; a rate above that is a leak.

## Three false-match classes the society slot opened — all closed

1. **Abbreviated cross-city forms.** M1's guard matched only `DHA Phase 1-4`. The
   slot let `DHA Ph-1`, `DHA 1`, `DHA P2` bind to Lahore. Same bug class, different
   spelling. Guard now normalises the designator before range-checking.
2. **`DHA Valley` is an Islamabad society.** `DHA V` parsed as `DHA Phase 5` (23x)
   and `DHA Valley Phase 7` bound to Lahore Phase 7. Root cause: the phase designator
   was **optional** after a society token, so "DHA Valley Phase 7" parsed as
   DHA+Phase 7. It is now **required** — and `DHA Valley` is dropped outright.
3. **Bare `Gulberg`** bound to Gulberg III. Observed context was "Gulberg Greens" and
   "Gulberg Residencia" — not Gulberg III. Now unresolved.

## Two of my own bugs during this milestone

- The cross-city guard briefly had `Lahore` **optional**, which swallowed the
  *qualified* `DHA Lahore Phase 1-4` — the forms that must resolve. Caught by
  `test_lahore_qualified_phases_still_resolve`.
- Two test regexes repeated the same over-broad pattern. Tests caught them.

**Pattern worth noticing:** every one of these was a guard that was too narrow, then
briefly too wide. Both directions produce wrong data. Tests for the *good* cases are
as load-bearing as tests for the refused ones.

## M1 baseline is now a FLOOR

`test_resolution_rate_at_least_milestone1_floor` pins 992 as a minimum, not an
exact count. Exact per-milestone counts live in that milestone's own tests. A rate
*below* the floor means a milestone regressed or a guard stopped firing.

---

# Milestone 1 — IMPLEMENTED

**Status: built and passing.** `python3 manage.py test corpus` -> 25 tests OK.

| Acceptance criterion | Result |
|---|---|
| Reproduce baseline | **992 / 2,725 = 36.4%** |
| Cross-city false matches | **0** (204 bare `DHA Phase N` held as drops) |
| Bare `DHA Phase N` does not resolve | pass, phases 1-4 |
| `CCA-3` / `CCA3` never a place | pass (66 measurement outcomes) |
| Known aliases resolve | 27/27 |
| Ambiguous sector letters unresolved | pass |

## Baseline moved DOWN — read this

`rerun-results.md` reported **37.9%**. That was wrong: the measuring script bound **41
bare sector/block letters** to real canonical names (`Sector F` -> Bahria Sector F,
`Block B` -> DHA Phase 6 Block B). Sector and block letters repeat across schemes, so
all 41 were false matches.

The implemented resolver refuses them. True baseline is **36.4%**.

**A baseline that moves down when the code gets stricter is the system working.** Do not
"fix" the resolver to hit 37.9%.

## Code map

- `corpus/models.py` — Django models. Invariants documented at module top
- `corpus/resolver.py` — the resolver. Stage order is the safety argument
- `corpus/management/commands/load_corpus.py` — CSV -> DB, idempotent
- `corpus/management/commands/run_resolver.py` — offline diagnostic; reports rate
  AND false-match counts together, never rate alone
- `corpus/tests/test_acceptance.py` — the six criteria plus integrity invariants
- `corpus/tests/fixtures/corpus_84pages.json` — 84-page corpus, so tests do not
  depend on /tmp

Run: `python3 manage.py load_corpus && python3 manage.py run_resolver`

---

# Original handoff brief (kept for context)

Next session starts here. No further design debate required; this is decided.

## Governing principle

**A higher resolution percentage is not an improvement if it increases false matches.**

This is not advice — it is the criterion the work is judged by. It was learned the
expensive way: a naive resolver reported 45.5% resolution when the honest figure was
37.9%. The missing 7.6 points were 206 bare `DHA Phase N` references silently
resolved to Lahore when they referred to Islamabad.

## Start here, not at the models

The resolver's safety guarantees are the load-bearing part of Milestone 1. Models are
mechanical. **Implement the precondition order first.**

```
1. Drops              cross-city, sector-letter, not-a-place
2. Measurement        CCA-* as category via measurement.csv — NEVER a place
3. Compositional parse society slot AND phase slot
4. Existence validate against entity.csv
5. Alias lookup
```

**Step 1 must precede canonical matching.** If it does not, bare `DHA Phase N`
resolves by canonical name and the corpus absorbs Islamabad data. Assert this in a
test, not a comment.

## Acceptance tests

Write these first or alongside. All must pass before any extraction work.

| Test | Expected |
|---|---|
| Reproduce baseline | **37.9%** resolution (1033/2725) on the 84-page corpus |
| Cross-city regression | bare `DHA Phase 2` does NOT resolve; `DHA Lahore Phase 2` does |
| False-match count | **zero** cross-city false matches |
| Category routing | `CCA-3` and `CCA3` never become a place |
| Alias correctness | known aliases resolve to their recorded entity |
| Sector-letter ceiling | `Sector A` stays unresolved **even with document scope** |

Report resolution rate **and** false-match count together. Never the rate alone.

## Data the resolver reads

All in `data/normalization/`, hand-authored, evidence-backed:

- `entity.csv` — 46 entities, 45 evidenced, 1 contested (`ph_dha_9_ext`)
- `alias.csv` — 27 aliases, each with evidence URL
- `drop.csv` — 21 drops: 16 confirmed, 3 untested, 2 not-a-place
- `measurement.csv` — 15 size forms → 8 canonical, 7 currency, 8 category

## Cross-city rule

DHA Phases 1-4 exist in **both** Lahore and Islamabad.

- `ph_dha_1` … `ph_dha_4` are **Lahore** entities
- Only `DHA Lahore Phase N` is an alias
- Bare `DHA Phase N` is a **drop** — never resolves to Lahore

## Known ceiling — do not try to solve it

Sector-letter ambiguity. 12 letters map to more than one society *even within a single
document* (`Sector A` → Askari 6, Bahria 3, DHA 6). ~75 occurrences across four
forms. This is a product limitation, not a bug.

Do not close it with cleverer guessing. A wrong resolution is worse than a miss —
that is the whole thesis of this project.

## Not in Milestone 1

LLM extraction, chat interface, contradiction detection (Approach B), voice input,
Karachi/Islamabad. Sourced data exists at `data/sources.md` — no crawling needed.

## Later, when ready

1. Society slot recovers ~9% (`Bahria Town` 208, `LDA City` 28) — no structural change
2. Approach B — contradiction detection. The schema absorbs it without re-ingestion
3. Decide whether the sector-letter ceiling blocks block-level intelligence. That is
   GharPulse's territory and worth a deliberate decision, not a default

## Unresolved, carry forward

- 3 drops are `untested` — never occurred in the corpus, not disproven
- No source publishes rates for DHA Phases 1-4 even though the entities now exist
- Whether the sector-letter ceiling is acceptable as a product limit

## Reading order

1. `docs/designs/lahore-aarea-gyan-engine.md` — Milestone 1 contract
2. `data/normalization/rerun-results.md` — the 37.9% baseline and the retracted 45.5%
3. `data/normalization/validation-R1-R6.md` — why R2 and R3 were rejected
4. `data/normalization/map.md` — cross-city ambiguity section
## Loader defects found while implementing

Three bugs in my own loader, all fixed. Recorded because they are the kind that
silently corrupt data rather than crash:

1. **`DATA` path resolved one directory short** (`corpus/data` instead of
   project `data/`). Loaded 0 rows and reported success. Fixed with
   `Path(__file__).resolve().parents[3]`.
2. **Society hardcoded to DHA** for all non-society levels, so Bahria and LDA City
   places were created under the DHA society. Caught by an alias-target mismatch
   (46→65 duplicate places). Fixed by resolving society from the topmost ancestor.
3. **Alias targets hardcoded to `soc_dha_lahore`**, dropping the three society-level
   aliases (Lake City, Askari 10, Gulberg III).

Also: two CSV rewrites during this session omitted `writeheader()` and destroyed
header rows in `entity.csv` and `alias.csv`. Both were caught by referential checks
and restored, but these files were briefly malformed — commit only after
`python3 manage.py load_corpus` reports the expected counts.

**Expected load counts:** sources=10 societies=6 places=46 aliases=27 drops=21
measurements=30. Anything else means the CSVs and the loader have diverged.
