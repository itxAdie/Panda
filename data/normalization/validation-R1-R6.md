# R1-R6 Validation Pass — Multi-Page Evidence

2026-10-01. **84 pages** fetched across 6 sources via sitemap discovery (not one
representative page per source). 2,725 entity-string occurrences observed, 198
distinct strings. Django stack; no code written.

Principle applied throughout: **let the source evidence force each change.** Three of
the six proposals did not survive contact with the corpus.

---

## Reproducible baseline

For the first time, successful resolutions are counted explicitly rather than inferred.

| Metric | Value |
|---|---|
| Pages | 84 (6 sources) |
| Observed entity-string occurrences | 2,725 |
| **Occurrences resolved** | **680 (25.0%)** |
| Distinct strings resolved | 19 |
| Distinct strings missed | 179 |
| Entities hit | 16 of 42 |

This supersedes the retracted ~30% figure, which counted the noise bucket. The
numerator is now actual matches, reproducible by re-running this sweep.

---

## R1 — Compositional name resolution: **SURVIVES, and the data demands it**

Parse `(society, phase, tail)` then validate the entity exists.

| Parsed form | Occ | Resolves to | Result |
|---|---|---|---|
| DHA Phase 9 Prism | 333 | `ph_dha_9_prism` | EXISTS |
| DHA Phase 1 | 169 | `ph_dha_1` | **NOT IN MAP** |
| DHA Phase 7 | 143 | `ph_dha_7` | EXISTS |
| DHA Phase 6 | 131 | `ph_dha_6` | EXISTS |
| DHA Phase 8 | 110 | `ph_dha_8` | EXISTS |
| DHA Phase 5 | 83 | `ph_dha_5` | EXISTS |
| DHA Phase 9 Town | 70 | `ph_dha_9_town` | EXISTS |
| DHA Phase 3 / 2 / 4 | 106 | `ph_dha_3/2/4` | **NOT IN MAP** |

**870 of 1,145 parsed occurrences (76.0%) resolve to existing entities. The remaining
24.0% are correctly rejected** because Phases 1-4 have no entity.

That 24% is the system working, not failing. Compositional parsing plus existence
validation distinguishes "DHA Phase 1 is real and we lack it" from "Phase 9 is
ambiguous" — a distinction exact-string matching cannot make.

The parser still leaves 1,580 occurrences unparsed: `Bahria Town` (208), bare
`Phase N` (506 across sources), `CCA-3` (42), `Lake City` (38). **Society-qualified
parsing alone is insufficient** — a society-slot parse is required too.

**R1 is adopted.** Not because a reviewer proposed it, but because 870 occurrences
depend on it and the cross-product is unbounded.

## R2 — Per-society `place_type`: **DOES NOT SURVIVE**

Tested whether societies partition differently. Result across the corpus:

- **DHA documents: `Block X` 361, `Sector X` 133, `Phase N` 1,933**
- Askari: no sector/block lettering in the sampled pages

DHA — the *one* society assumed to be block-partitioned — uses **both** "Block" and
"Sector" freely, and its own sub-partitions are labelled inconsistently. Bahria and
Askari use sectors. There is no clean per-society grammar to declare.

A `place_type` enum would encode an assumption the data contradicts. **Rejected.**

What the data does support: a **flat entity + `parent_id`**, with the *name* ("Block
Y" vs "Sector U") captured as an observed alias rather than as a type declaration.

## R3 — `sub_sector` level: **REJECTED — the evidence contradicts the premise**

The proposal assumed Prism has lettered *sub-sectors*. What the corpus shows:

- `DHA Phase 9 Prism Block Q` 17x, `Block N` / `Block L` 6x each, `Block A/K/R/D` 5x,
  plus B, C, E, F, G, H, M, P — **all from a single source** (mohsinestate)
- `DHA Lahore Phase 9 Prism Sector A` — **1x, the same source**
- The same source uses `DHA Phase 7 Sector U` and `DHA Phase 7 Block U` for
  apparently the same place

So mohsinestate calls the same objects both "Block" and "Sector". That is a **source
naming inconsistency, not a hierarchy fact.** Encoding it as `sub_sector` would
bake a source's inconsistency into the schema as if it were structural truth.

Worse: `DHA Phase 7 Block CCA` (2x) and `DHA Phase 7 Block Z2` (2x) — the same
pattern captures things that are not blocks. CCA is a commercial category (42
occurrences corpus-wide); Z2 is a sector designation.

**Rejected.** The real finding is a *data-quality* problem in one source, not a
missing tree level. Address it with source-level confidence weighting, not schema.

## R4 — Document scope: **FALSIFIED for sector letters; HOLDS for phases**

This is the most consequential result, because it also invalidates a finding in
`drops-reconciliation.md`.

**Sector letters are NOT document-scoped.** Counting societies per letter *within the
document that contains it*:

| Letter | Societies in-document |
|---|---|
| A | Askari 6, Bahria 3, **DHA 6** |
| B | Askari 2, Bahria 6 |
| F | Bahria 3, Askari 1 |
| G, C, F, 4, A, B, Z, H, J, K, L, M | all map to **>1 society in-document** |

Twelve letters are society-ambiguous even with full document scope. My earlier claim
that `Sector A`/`Sector F` were "resolvable via document scope" was based on two
sources and **is wrong at corpus scale**. It must be retracted.

**Phases ARE document-scoped.** 1,495 bare `Phase N` mentions inside DHA documents;
only **11 (0.7%)** occur in a document that also names Prism/Town/Extension for that
same number.

So document scope is a real mechanism, but only for one dimension. It cannot be
generalised, and R4's blanket proposal does not hold.

## R5 — Unverified sources: **MOOT, superseded**

All 10 sources have verified policies (`tos-verification.md`). maanestate's 403
affects page fetches only; its content is served via a published AI hub. No source is
unverified.

R5 as written no longer describes the problem. The residue worth keeping: provenance
must record **which channel** a fact came from (live page vs AI hub), since those
have different freshness guarantees. That is a small field, not a review item.

## R6 — Coverage metric: **ADOPTED, reframed as diagnostic-only**

The original argument was circular and is discarded. The rule stands on its own
merits, with a concrete enforcement mechanism:

> Coverage is measured **offline only**. The resolution function does not accept, read,
> or return any coverage input. A resolution decision has access to: the observed
> string, its document context, and the entity map. Nothing else.

Enforcement is structural, not procedural — no metric exists on the resolution path
to be optimised. That is what makes "never force a match" hold rather than merely be
advised.

---

## Net effect of the validation pass

| | Proposal | Outcome |
|---|---|---|
| R1 | Compositional resolution | **ADOPTED** — 870 occ depend on it |
| R2 | Per-society `place_type` | **REJECTED** — DHA uses Block and Sector interchangeably |
| R3 | `sub_sector` level | **REJECTED** — encodes one source's inconsistency |
| R4 | Document scope | **PARTIAL** — works for phases (0.7% ambiguous), fails for sector letters |
| R5 | Unverified sources | **MOOT** — superseded by ToS re-verification |
| R6 | Coverage diagnostic-only | **ADOPTED** — reframed, structural enforcement |

Two proposals were rejected on evidence. That is the point of running the validation
before the redesign.

## Consequences for the map

**Phases 1, 2, 3, 4 are missing and are being actively referenced** — 275 occurrences.
They are not invented; they are *observed and unmodelled*. Adding them is recording
what sources publish, not filling a gap with assumption.

**9 of 12 DHA phases still have zero sub-partitions** — the coverage problem is real
and unchanged. Sources overwhelmingly publish at phase level. No schema change fixes
that; only more sources would.

## Still open

- The sector-letter ambiguity (12 letters, multi-society even in-document) has **no
  evidenced solution**. It may be genuinely unresolvable at block granularity, which
  would be a real limit on block-level intelligence — GharPulse's territory.
- Whether to add Phases 1-4 as entities.
- mohsinestate's Block/Sector inconsistency needs a source-level trust weight.