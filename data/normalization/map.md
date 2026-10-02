# Normalization Map — society → phase → block

Hand-authored by /office-hours Step 3, 2026-10-01. Companion to `../sources.md`.

This is the artifact that, if wrong, makes everything downstream **internally
consistent and still wrong**. Extraction looks clean, retrieval returns results,
answers cite real URLs and real dates — and every fact is attached to the wrong
block. Nothing errors.

## Schema

Four tables. Hand-authored; will become Django fixtures or a data migration.

```
entity      canonical_id, level (society|phase|block), parent_id,
            canonical_name, city, notes

alias       alias_text, canonical_id, evidence, evidence_url, confirmed (bool)

drop        alias_text, reason, source_id, seen_on

coverage    canonical_id, covered_by_sources, gap_status
```

`confirmed` is the gate. An alias is usable by extraction only when `confirmed` is
true. Unconfirmed aliases exist as *observations* — they document what sources
actually said without asserting the mapping. That distinction is the whole point:
we record the ambiguity rather than resolving it by vibes.

## Rules carried into this map

1. **Never merge ambiguous entities.** If `DHA City` cannot be confidently resolved,
   it is dropped, not guessed.
2. **Preserve source naming.** Every alias keeps the exact string the source used.
   `canonical_name` is ours; `alias_text` is theirs.
3. **Model aliases explicitly.** `Phase X → DHA Phase 10` only where evidence
   establishes the relationship, recorded with that evidence.
4. **Gaps stay visible.** Coverage gaps are recorded as gaps. They are never filled
   with plausible-looking entities. The DHA-heavy source set must not silently
   define the taxonomy.

---

## Confirmed entities

`canonical_id` is stable and never reused.

### Society level

| canonical_id | canonical_name | city | notes |
|---|---|---|---|
| soc_dha_lahore | DHA Lahore | Lahore | Defence Housing Authority. Statutory authority. Phases 1-13. |
| soc_bahria_lahore | Bahria Town Lahore | Lahore | Private developer. Uses **sectors**, not blocks. |
| soc_lda_city | LDA City Lahore | Lahore | Government scheme, LDA is developer *and* regulator. Uses **blocks** AND **sectors** — two hierarchies, see open problem. |
| soc_lake_city | Lake City | Lahore | Appears in Lahore Real Estate rate tables. Depth unverified. |
| soc_askari_10 | Askari 10 Lahore | Lahore | Built out. **No file market** — file-risk fact model does not apply. |
| soc_gulberg_iii | Gulberg III | Lahore | Established LDA-regulated. Not a file/possession market. |

### Phase level — DHA Lahore

| canonical_id | parent | canonical_name | notes |
|---|---|---|---|
| ph_dha_1 | soc_dha_lahore | DHA Phase 1 | Added 2026-10-01. Qualified form only — see cross-city note |
| ph_dha_2 | soc_dha_lahore | DHA Phase 2 | as above |
| ph_dha_3 | soc_dha_lahore | DHA Phase 3 | as above |
| ph_dha_4 | soc_dha_lahore | DHA Phase 4 | as above |
| ph_dha_5 | soc_dha_lahore | DHA Phase 5 | Includes `M-Extension` — see alias below |
| ph_dha_5_mext | soc_dha_lahore | DHA Phase 5 (M-Extension) | Distinct from Phase 5 proper; MAAN/LRE treat as separate rate line |
| ph_dha_6 | soc_dha_lahore | DHA Phase 6 | High-liquidity; office MB-46 is here |
| ph_dha_7 | soc_dha_lahore | DHA Phase 7 | |
| ph_dha_8 | soc_dha_lahore | DHA Phase 8 | Includes `Z Block`, `IVY Green – Z Block` |
| ph_dha_9_prism | soc_dha_lahore | DHA Phase 9 Prism | Possession-open |
| ph_dha_9_town | soc_dha_lahore | DHA Phase 9 Town | Distinct from Prism — frequently conflated |
| ph_dha_9_ext | soc_dha_lahore | DHA Phase 9 Extension | Former name of Phase 10 — **see drop list for the raw string** |
| ph_dha_10 | soc_dha_lahore | DHA Phase 10 | Also published as **Phase X** |
| ph_dha_11_rahbar | soc_dha_lahore | DHA Phase 11 (Rahbar) | Sec-4 variant |
| ph_dha_12 | soc_dha_lahore | DHA Phase 12 | |
| ph_dha_13 | soc_dha_lahore | DHA Phase 13 | Also `Ex-DHA City` — **distinct from other "DHA City" uses** |

### Block/sector level — only where sources publish them

| canonical_id | parent | canonical_name | notes |
|---|---|---|---|
| blk_dha_6_b | ph_dha_6 | DHA Phase 6 Block B | MAAN ESTATE names Block B |
| blk_dha_6_d | soc_dha_lahore | DHA Phase 6 Block D | Named explicitly in normalization discussion |
| blk_dha_6_c | soc_dha_lahore | DHA Phase 6 Block C | Named explicitly |
| blk_dha_8_s | ph_dha_8 | Block S | MAAN ESTATE: "selected locations in Blocks S and X" |
| blk_dha_8_x | ph_dha_8 | Block X | as above |
| blk_dha_8_z | ph_dha_8 | Block Z | `Z Block` published as its own rate line |
| sec_bahria_c | soc_bahria_lahore | Bahria Town Sector C | Main Boulevard. Premium. |
| sec_bahria_e | soc_bahria_lahore | Bahria Town Sector E | Johar, Iqbal |
| sec_bahria_f | soc_bahria_lahore | Bahria Town Sector F | Talha, Safari |
| sec_bahria_g | soc_bahria_lahore | Bahria Town Sector G | Future merger pending — status unsettled |
| sec_bahria_h | soc_bahria_lahore | Bahria Town Sector H | as above |
| sec_bahria_ab | soc_bahria_lahore | Bahria Town Sectors A-F | Grouped range in ASAS, not a single sector |
| soc_bahria_orchard | soc_bahria_lahore | Bahria Orchard | Distinct scheme, not a sector |
| soc_bahria_overseas | soc_bahria_lahore | Overseas Enclave | NRP-focused |
| blk_lda_a1 | soc_lda_city | LDA City A1 Block | |
| blk_lda_b1 | soc_lda_city | LDA City B1 Block | |
| blk_lda_e1 | soc_lda_city | LDA City E1 Block | |
| blk_lda_h | soc_lda_city | LDA City H Block | |
| blk_lda_l | soc_lda_city | LDA City L Block | |
| blk_lda_m | soc_lda_city | LDA City M Block | |
| blk_lda_n | soc_lda_city | LDA City N Block | Under active development as of Aug 2026 |
| blk_lda_p | soc_lda_city | LDA City P Block | |
| sec_lda_jinnah | soc_lda_city | LDA City Jinnah Sector | **Overlaps block hierarchy — see open problems** |
| sec_lda_iqbal | soc_lda_city | LDA City Iqbal Sector | as above |
| sec_lda_pine | soc_lda_city | LDA City Pine Sector | **Announced, not yet launched — do not treat as active** |

---

## Confirmed aliases

Only aliases where evidence establishes the relationship. `evidence_url` is the
proof. Extraction may use these.

| alias_text | canonical_id | evidence | confirmed |
|---|---|---|---|
| `DHA Ph 6`, `DHA Phase 6`, `DHA Phase VI`, `Defence Phase 6`, `DHA Lahore Phase 6`, `DHA P6` | ph_dha_6 | Multiple sources; same phase | ✅ |
| `Phase 10`, `Phase X`, `DHA Phase 10 (Phase X)` | ph_dha_10 | dharealestate.pk publishes headings literally as "DHA Phase 10 (Phase X)" — the source itself equates them | ✅ |
| `Ph 13 (Ex-DHA City)` | ph_dha_13 | lahorerealestate.com "Phase 13 (Ex-DHA City) Files"; dharealestate.pk Phase 13 rates | ✅ |
| `Ph 11 (Rahbar)`, `Rahbar Sec-4`, `DHA Rahbar` | ph_dha_11_rahbar | lahorerealestate.com "Phase 11 (Rahbar Sec-4)"; dharealestate.pk "DHA Rahbar (Phase-11 Sec-4)" | ✅ |
| `IVY Green – Z Block`, `Z Block` | blk_dha_8_z | dharealestate.pk Phase 8 table lists both as distinct line items for the same block | ✅ |
| `Sector C (Main Boulevard)` | sec_bahria_c | ASAS Properties sector table | ✅ |
| `Sector F (Talha, Safari)` | sec_bahria_f | ASAS Properties sector table | ✅ |
| `Sector E (Johar, Iqbal)` | sec_bahria_e | ASAS Properties sector table | ✅ |
| `Phase 5 (M-Extension)`, `Phase 5 (M-Extension) Files` | ph_dha_5_mext | lahorerealestate.com rate table lists separately from Phase 5 | ✅ |
| `Lake City Lahore Files` | soc_lake_city | lahorerealestate.com LDA City & Lake City section | ✅ |
| `Askari 10` | soc_askari_10 | Burstforum throughout | ✅ |
| `Gulberg III`, `Gulberg III Block A2` | soc_gulberg_iii | milkiyat.com Gulberg guide listing blocks | ✅ |

**Critical for entity shape:** `20 Marla` and `1 Kanal` are published
interchangeably by sources (`"20 Marla / 1 Kanal Allocation File"` in dharealestate.pk).
Model as **one canonical size with two source aliases**, never as two sizes. Same
for `CCA-3`, which is a DHA commercial category, not a block.

---

## Drop list

Ambiguous or unresolvable. **Extraction must discard these and log the drop.** Never
map by inference.

| alias_text | reason | source |
|---|---|---|
| `DHA City` | Refers to at least 3 distinct things across sources: (a) `Ph 13 (Ex-DHA City)`, (b) `DHA City Karachi`, (c) a site-navigation label meaning DHA Lahore generally. Cannot resolve without source-level context. | dharealestate.pk, lahorerealestate.com |
| `Phase 9 Extension` | CDB states Phase 10 "was earlier known as Phase 9 Extension", but no other source uses it and no date boundary is established. A 2025 fact and a 2026 fact may mean different phases. | cdbrealestate.com |
| `Phase 9` (bare) | Ambiguous across Prism / Town / Extension. Three sources mean three different phases by bare "Phase 9". | multiple |
| `DHA Lahore` (bare, as a phase) | Sometimes means the whole society, sometimes means Phase 6 in casual usage (office addresses). Level is unclear. | lahorerealestate.com |
| `N Block`, `M Block`, `L Block` (LDA City, unqualified) | Block letters repeat across schemes. Needs LDA City context the string lacks. | lahorerealestate.com |
| `Sector A`, `Sector F` (bare) | Bahria and Askari 10 both use sector letters. Bare letter is ambiguous across both. | ASAS, Burstforum |
| `Block B`, `Block D`, `Block S`, `Block X` (bare) | DHA uses block letters across 13 phases. Bare letter meaningless without phase. | maanestate.com |
| `Model Town`, `Johar Town`, `Faisal Town`, `Ring Road periphery` | Real Lahore zones in milkiyat.com but **no source in the registry publishes them at entity level**. Adding them would fill a gap with assumptions — forbidden by rule 4. Coverage gap stays visible. | milkiyat.com |
| `On Call`, `Call us for Rates` | Not a fact. Must be stored as `rate = null, rate_unavailable = true`, never as a number. | lahorerealestate.com |
| `5-M`, `5M`, `5-Marla`, `5 Marla` | Unit normalization, **not entity aliases**. Handle in a size-parsing step; do not store as entity strings. | multiple |
| `Lac`, `Lakh`, `Lacs`, `Cr`, `Crore`, `PKR 43.75L` | Currency normalization, **not entity aliases**. Same. | multiple |

---

## CROSS-CITY AMBIGUITY — DHA Phase 1-4 (critical)

**DHA Phases 1-4 exist in BOTH Lahore and Islamabad.** Sources reference both.
42 bare `DHA Phase 1-4` references sit in a milkiyat.com page with explicit
Islamabad context ("DHA Islamabad vs Bahria Town Rawalpindi", GT Road, Islamabad
Expressway).

Therefore:

- **Entities `ph_dha_1` … `ph_dha_4` exist for LAHORE** — evidenced by qualified
  strings `DHA Lahore Phase N` (9 occurrences, 2 pages, lahorerealestate.com)
- **The bare form `DHA Phase N` is a DROP, not an alias.** It must never resolve to
  Lahore.
- Only the Lahore-qualified alias is registered.

Enforcement note: because the canonical name of `ph_dha_1` is itself `DHA Phase 1`,
naive canonical-name matching **will silently resolve the ambiguous bare form to
Lahore** — 206 occurrences, inflating the resolution rate by 7.6 points. The resolver
must apply the cross-city drop **before** canonical matching. This is enforced in
`rerun.json` and must be an explicit precondition in the resolution function.

## Corrections (2026-10-01)

Applied after the architecture review and independent verification:

1. **Rahbar Sec-4 re-levelled.** Was an alias of `ph_dha_11_rahbar` (phase level),
   marked `confirmed=true` — while its own cited evidence read *"Phase 11 (Rahbar
   Sec-4)"*, i.e. a sector **nested inside** the phase. Now entity
   `sec_dha_11_rahbar_4`, level `sector`, parent `ph_dha_11_rahbar`. `Ph 11 (Rahbar)`
   and `DHA Rahbar` remain phase-level aliases. The evidence contradicted the
   mapping and was not caught.
2. **`entity.csv` gained `evidence_url`, `evidence`, `evidence_status`.** All 42
   entities were previously unevidenced prose in `notes`. Now: 39 evidenced, 1
   contested, 2 removed.
3. **`blk_dha_6_c` and `blk_dha_6_d` deleted.** No source names them. They were
   created from this document's own illustrative example of naming variance
   (`DHA Lahore Phase 6 Block D`) and then cited as evidence that the variance
   exists. Circular. 43 entities -> 42.
4. **Two aliases cited `techx.pk`**, not a registry source (`DHA P6`,
   `Defence Phase 6`). Evidence must come from a registered source.

## Coverage gaps — recorded, not filled

Per rule 4. The taxonomy reflects what sources publish, and the DHA weight is a
property of the source set, not of Lahore.

| Gap | Why it is a gap | Do NOT |
|---|---|---|
| **Bahria Town dedicated rate publisher** | No source publishes Bahria block/sector-level rates on a cadence. ASAS covers it coarsely; LexForm covers legal only. | Do not synthesize Bahria rates from ASAS phase-level comparisons. |
| **Askari 10 phases/subsectors** | Only one source (Burstforum), built-out, no files. | Do not assume Askari has file/possession risk. It does not. |
| **Johar Town, Faisal Town, Model Town, Ring Road schemes** | Present only as aggregate zones in milkiyat.com. No entity-level data anywhere. | Do not create entities for them. They are not in the corpus. |
| **Gulberg beyond III** | Only Gulberg III named. Gulberg I, II, IV not published as separate entities. | Do not extrapolate. |
| **DHA Phases 1-4** | Phase-level rates referenced as a range (`Ph 1-4`) but no per-phase figures in any source. | Do not split the range into per-phase rates. |
| **DHA block-level rates** | Almost all sources publish **phase-level**, not block-level. Only the handful of blocks above are named individually. | **This is the single biggest gap.** Block-level price intelligence is GharPulse's territory and ours only where sources name blocks. |
| **Roman Urdu corpus** | Every registered source is English. | Do not generate Urdu claims from English sources and present them as sourced. |
| **Official DHA/LDA notices** | Entire corpus is secondary reporting. No authoritative source registered. | Never present a fact as official. Every answer carries "verify with DHA/LDA". |

---

## Open problems for /plan-eng-review

1. **LDA City has two competing hierarchies** — blocks (A1, B1, N…) and sectors
   (Jinnah, Iqbal, Pine). They may be nested, may overlap, or may be independent
   partitions. Sources use them interchangeably. Needs a decision before extraction.
2. **`Phase 9 Extension → Phase 10` relationship** — plausible, single-sourced, not
   confirmable. Currently dropped.
3. **Sector vs block is not a uniform level.** Bahria uses sectors, DHA uses blocks,
   LDA City uses both. The schema's `level` enum assumes a uniform tree. May need a
   looser `place_type` per society instead.
4. **Size normalization is entangled with entity identity.** `20 Marla` == `1 Kanal`
   is asserted by sources but is a *size* equivalence, not an entity alias. Needs a
   separate dimension or it will pollute the entity table.
5. **Drop logging needs a home.** Drops are the most valuable output of the dry-run,
   and they currently have no destination. They are signal, not garbage.