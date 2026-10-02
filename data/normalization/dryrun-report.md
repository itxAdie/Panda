# Dry-Run Report — Normalization Map vs Live Sources

Step 4, 2026-10-01. Ten sources attempted, **eight fetched successfully**. No
extraction code was written; this is observation only.

## Method

Fetched one representative page per source, stripped markup, and swept for
entity-bearing place patterns. Matched every observed string against `entity.csv`,
`alias.csv` and `drop.csv`. Every unmatched string was kept and adjudicated — none
silently discarded.

**Harness limitation, stated up front:** the first two sweeps were badly calibrated
and produced 122 apparent misses. Two classifier bugs inflated the artifact side in
turn — a filter that matched any string *beginning* with "DHA"/"Phase", then a
`len(token)==1` test that wrongly treated the `2` in `Phase 2` as a stray token.
Corrected: **72 of 122 distinct misses are regex artifacts (155 of 512
occurrences)** — a trailing prose token glued onto a real place name, as in
`DHA Phase 9 Prism L` or `DHA Phase 10 Balloting U`. These are not map failures.

The genuine figure is **50 distinct strings / 357 occurrences (70% of everything
missed)**. Do not read the raw 122 as the map's failure count, and do not read the
50 as acceptable.

## Source fetch results

| Source | Fetch | Note |
|---|---|---|
| dharealestate.pk | 200 | Richest entity vocabulary — 59 distinct strings |
| mohsinestate.com | 200 | 43 strings; most block-level naming found anywhere |
| lahoreerealestate.com (x2) | 200 | Rate page + LDA City page |
| cdbrealestate.com | 200 | |
| milkiyat.com | 200 | |
| burstforum.com | 200 | |
| elegantdha.com | 200 | |
| lex-form.com | 200 | Only 2 distinct strings — qualitative source |
| **maanestate.com** | **403** | **Blocked. Policy unverified, content untested.** |
| **asaspropertiespk.com** | **000** | **Unreachable from this host.** |

Two sources untested. `maanestate.com` already had no robots.txt and a 403 privacy
page at gate time; it is now the least accessible source in the set and its
coverage is entirely assumed.

---

## Genuine misses — 50 strings, 357 occurrences

### Class A — Qualified-form gaps (highest volume, mechanical fix)

| Observed | Occ | Canonical it should match | Root cause |
|---|---|---|---|
| `LDA City` | 44 | soc_lda_city (*LDA City Lahore*) | Short form absent |
| `Bahria Town` | 37 | soc_bahria_lahore (*Bahria Town Lahore*) | Short form absent |
| `Bahria` | 29 | soc_bahria_lahore | Bare form absent |
| `DHA Lahore Phase 10` | 5 | ph_dha_10 | City-qualified form absent |
| `DHA Lahore Phase 13` | 3 | ph_dha_13 | as above |
| `DHA Phase 2` | 76 | *(no entity)* | **Phase 2 not in map — Elegant DHA's entire subject** |
| `DHA Phase 9`, `DHA Phase 7`, `DHA Phase 1` | 22 | ph_dha_9_*, ph_dha_7, ph_dha_1 | `DHA Phase 1` has no entity; 9 and 7 exist |

Root cause: the map stores one canonical name per entity and treats every other
form as a hand-written alias. Real sources emit *systematic* qualifier variants
(`DHA` / `DHA Lahore` / `Defence` × `Phase N` / `Ph N` / `Phase N`). Hand-writing
that cross-product is unbounded. **The alias table is the wrong shape.**

### Class B — Matching-strategy failures (aliases exist but did not fire)

| Observed | Alias present in map | Occ |
|---|---|---|
| `Phase 13 (Ex-DHA City)` | yes — `Ph 13 (Ex-DHA City)` | 1 |
| `Phase 11 (Rahbar Sec-4)` | yes — `Phase 11 (Rahbar Sec-4)` | 1 |
| `Phase 5 (M-Extension)` | yes — `Phase 5 (M-Extension)` | 1 |

These matched on neither alias nor canonical. **Exact-string matching cannot resolve
parenthesised forms or a `Ph`/`Phase` prefix difference.** Resolution must be
pattern-based: strip parentheticals, then match the base form.

### Class C — Parenthetical / abbreviation normalization

| Observed | Occ | Note |
|---|---|---|
| `PhaseX`, `Phase10`, `Phase13`, `Phase7`, `Phase2`, `Phase3` | 7 | No space between word and numeral |
| `Phase-9`, `Phase-2` | 2 | Hyphenated |
| `Phase9` | 2 | No space |

Same normalization problem as Class B, different surface form. All resolve to
entities that **already exist**. Currently lost.

### Class D — Genuinely ambiguous, correctly unresolved

| Observed | Occ | Why unresolved |
|---|---|---|
| `Phase 9` | 22 | Prism / Town / Extension — three meanings, 5 sources |
| `Phase 7`, `Phase 13`, `Phase 6`, `Phase 8`, `Phase 4`, `Phase 3`, `Phase 1`, `Phase 5` | 43 | Bare phase, no society qualifier |
| `DHA Phase 9 Prism 5`, `DHA Phase 9 Town 5`, `DHA Phase 9 Prism 10` | 5 | Trailing numeral — but `10` in Prism is a **sector**, while `5` is a size. Same surface form, different dimensions. |
| `Block 1`, `Block 4`, `Block 5` (bare) | 9 | Correctly unresolved — block letters repeat across schemes |
| `Gulberg` | 32 | Only Gulberg III is an entity. Gulberg generally is a zone, not a society in this map |
| `DHA Phase 8 CCA3`, `DHA Phase 7 CCA1`, `DHA Phase 6 CCA-3` | 5 | **Not places.** CCA is a DHA commercial category |

---

## The two findings that change the schema

### 1. The alias table is the wrong shape — qualifier cross-product is unbounded

Classes A and C together account for roughly **190 of 357 genuine occurrences** —
well over half of everything missed. The pattern is systematic, not exceptional:

```
{ "", "DHA ", "DHA Lahore ", "Defence " } × { "Phase N", "Ph N", "Phase-N", "PhaseN" } × optional parenthetical
```

Hand-authoring this cross-product is exactly the failure mode this step exists to
catch. **Resolution must be compositional**, not lookup: match the society
qualifier and the phase designator as independent slots, then confirm the phase
exists under that society. Aliases stay for genuinely irregular forms
(`Phase X`, `Ex-DHA City`, `M-Extension`) — cases where the string does not
decompose.

### 2. I got one entity wrong, and the dry-run caught it

`DHA Rahbar Sector-4` — I modelled `Rahbar Sec-4` as an **alias of Phase 11**, i.e.
a phase-level name. The source string is `DHA Rahbar Sector-4`: **Sec-4 is a sector
*inside* Phase 11**, not a synonym for the phase. The map flattens a level.

This is exactly the "internally consistent and still wrong" failure. Facts about
Rahbar Sector-4 and Phase 11 overall would have merged into one entity, both
sourced, both dated, no error anywhere.

Also missing entirely: **DHA Phase 9 Prism sub-sectors.** mohsinestate and
dharealestate both publish lettered Prism sectors (L, R, B, F, G, H, N, Q, 10).
Prism is where most 2026 activity is, and the map has *zero* granularity for it.
`DHA Phase 9 Prism 10` in the miss list is a sector, not a size — a fact the map
cannot currently represent.

---

## What I did NOT do, deliberately

- **Did not create entities for Gulberg, Model Town, Johar Town, Faisal Town.**
  They appear as bare strings in milkiyat.com. Adding them because the dry-run
  surfaced them would be filling a coverage gap with assumptions — rule 4.
- **Did not resolve bare `Phase N` to a society.** Genuinely ambiguous.
- **Did not promote any Class D string.** Logged as observations only.
- **Did not write matching code.** That is extraction-phase work.

---

## Remaining drops, still live

All 19 entries in `drop.csv` remain in force. None was encountered-and-resolved
during this run, and none should be revisited without new evidence:

`DHA City` · `Phase 9 Extension` · `Phase 9 (bare)` · `DHA Lahore (bare as phase)` ·
`N/M/L Block (unqualified)` · `Sector A/F (bare)` · `Block B/D/S/X (bare)` ·
`Model Town` · `Johar Town` · `Faisal Town` · `Ring Road periphery` ·
`On Call` · `Call us for Rates`

Two of these — `Sector A/F (bare)` and `Block B/D/S/X (bare)` — fired during the
dry-run and behaved exactly as designed. Eight occurrences of `Sector A`/`Sector B`
in burst and lre_lda were **not** resolved, and that is the correct outcome.

---

## Recommended schema changes before extraction

> **These six are now the explicit agenda for `/plan-eng-review`** — see the design
> doc section "Schema Changes For /plan-eng-review": R1 compositional resolution,
> R2 per-society hierarchies, R3 sub-sector level, R4 permanent observation table,
> R5 two untested sources, R6 never force a match for coverage.
>
> **The ~30% resolution rate in this report is a baseline, not a success metric.**
> A higher figure achieved by forcing matches is a regression, not progress.

Detail follows.

**R1 — Compositional resolution** replaces alias lookup for systematic forms.
Never accept a match on resemblance alone. Aliases retained for irregular forms only
(`Phase X`, `Ex-DHA City`, `M-Extension`).

**R2 — Per-society `place_type`** instead of a global `level` enum. Society declares
whether it partitions by `block`, `sector`, `sub_sector`, or more than one. Fixes
LDA City (blocks + sectors) and Rahbar (phase → sector nesting).

**R3 — `sub_sector` level** so Prism lettered sectors and Rahbar Sec-4 have a home.
Also resolves the `Prism 10` (sector) vs `Town 5` (size) surface collision.

**R4 — `observation` table becomes permanent.** Every unmatched, ambiguous and
rejected string lands there with source, occurrence count, adjudication and reason.

**R5 — Two sources still untested.** maanestate.com (403), asaspropertiespk.com
(unreachable). Coverage is assumed, not verified. Carry the flag into any fact
attributed to them, or drop them.

**R6 — Never force a match to improve coverage.** The eight unresolved bare
`Sector A`/`Sector B` occurrences were correct. Forcing them would have raised the
rate and corrupted the corpus.

Also settled at this step, not a schema question: **size and currency normalization
is separated from place identity** in `measurement.csv` — 15 size forms to 8
canonical values, 7 currency forms, 8 categories. `1 Kanal` = 20 marla as one
canonical with two aliases. `CCA-1`/`CCA-3` are categories, not sizes and not places.