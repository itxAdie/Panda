# Re-run Results — Resolution After Phase 1-4 Decision

> **CORRECTION (2026-10-02).** The 37.9% figure below is **superseded by 36.4%**.
> Implementing the resolver revealed that this script's canonical-name matching bound
> **41 bare sector/block letters** to real entities — `Sector F` → Bahria Sector F,
> `Block B` → DHA Phase 6 Block B. Sector and block letters repeat across schemes, so
> all 41 were false matches. The Django resolver refuses them.
>
> The true figure is **992 / 2,725 = 36.4%**. The baseline moved **down** because the
> implemented code is stricter than the script that measured it.
>
> The 45.5% retraction below remains valid, and the 206 cross-city drops remain correct.
> See `corpus/tests/test_acceptance.py` (`test_sector_letters_never_bind_despite_canonical_name`).

2026-10-01. Same 84-page corpus as `validation-R1-R6.md` (2,725 entity-string
occurrences), so the comparison is like-for-like.

## Headline

| Run | Resolved | Rate |
|---|---|---|
| Before Phase 1-4 | 680 / 2,725 | 25.0% |
| Naive after adding Phases 1-4 | 1,239 / 2,725 | **45.5% — wrong** |
| **Honest, cross-city enforced** | **1,033 / 2,725** | **37.9%** |

**The 45.5% figure is retracted.** Because `ph_dha_1`'s canonical name is literally
`DHA Phase 1`, canonical-name matching resolved **206 occurrences of the bare
cross-city form to Lahore** — merging Islamabad phases into the Lahore corpus. That
is precisely the failure mode the entire pipeline exists to prevent, and it presented
as a large improvement.

The resolver now applies the cross-city drop **before** canonical matching. The honest
gain from Phase 1-4 is **+12.9 points**, all of it from Lahore-qualified strings and
from phases whose bare form is unambiguous (5-13).

## Resolution by method

| Method | Distinct forms |
|---|---|
| canonical | 14 |
| compositional | 16 |
| alias | 9 |

Compositional resolution (R1) is doing the largest share of the *new* work and is
load-bearing as predicted.

## Phase 1-4 outcome

| Form | Occ | Resolved to |
|---|---|---|
| `DHA Lahore Phase 1-4` | 9 | ph_dha_1..4 (alias) |
| `DHA Phase 1` / `2` / `3` / `4` (bare) | 206 | **DROPPED — cross-city** |
| `DHA Phase 13`, `Phase 13` | 42 | ph_dha_13 |

## Remaining misses — 1,692 occurrences (62.1%)

159 distinct strings. By reason: 154 unparsed, 5 correctly dropped as cross-city.

| Occ | String | Why |
|---|---|---|
| 208 | `Bahria Town` | Society-slot parse not implemented. Canonical is `Bahria Town Lahore` |
| 135/131/82/65/50/45/42/28/31 | `Phase N` bare | Society unknown. Some are Islamabad |
| 42+22 | `CCA-3`, `CCA3` | Commercial category, in `measurement.csv` — not yet routed |
| 32 | `Sector-Z` | Hyphenated form; sector-letter ceiling |
| 24/22/15/14 | `Block 4`, `Block Q`, `Block D`, `Sector A` | **Known resolution ceiling** — multi-society even in-document |
| 17 | `DHA Phase 9 Prism Block Q` | Sub-partition naming; R3 rejected on evidence |
| 28 | `LDA City` | Canonical is `LDA City Lahore` |

## Assessment

The rerun is **satisfactory for deciding the schema, not for extraction**. What it
establishes:

1. **The cross-city rule is necessary and working.** 206 occurrences correctly held
   back. Without it the corpus would have silently absorbed Islamabad data.
2. **R1 is justified.** Compositional resolution carries the largest share of new
   matches.
3. **The sector-letter ceiling is real** — ~75 occurrences across four forms, all
   multi-society even with document scope. This is a limit, not a bug.
4. **The largest remaining miss is trivial to fix**: a society-slot parse would
   recover `Bahria Town` (208) and `LDA City` (28) — ~9% — with no structural change.

## Recommended before extraction

- Implement the society slot alongside the phase slot (R1 completed, not partial)
- Route `CCA-*` through `measurement.csv` as a category, never as a place
- Enforce drops **before** canonical matching, as an explicit precondition
- Treat sector letters as a permanent ceiling and document it as a product limit
