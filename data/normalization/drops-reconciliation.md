# Drops ↔ Observations Reconciliation

Step 4 follow-up, 2026-10-01. The 19 drops in `drop.csv` were asserted at Step 3 and
never tested against real source text. This reconciles them.

**Result: of 19 drops, 2 were vacuous (never occur in any fetched page), 1 was
missing, and 2 are resolvable if document scope is modelled.** The dry-run did not
validate the drop rules, because the drop rules were never applied to it.

## Method

Two passes:

1. **Structural** — matched each `drop.csv` alias against `observation.csv`.
2. **Direct probe** — searched the raw text of all 11 fetched pages (including
   `asas.html`, now retrieved) for each drop string literally. This was necessary
   because the Step 4 observation regex only captured *place-shaped* strings and
   would never surface `On Call` or `Call us for Rates`.

## Reconciliation table

| Drop | Occurrences | Sources | Finding |
|---|---|---|---|
| `DHA City` | 6 | dha_rates, lre_sep | **Justified.** 3+ referents, unresolvable |
| `Phase 9 Extension` | 1 | cdb_ph10 | **Justified.** Single occurrence, single source |
| `Phase 9 (bare)` | 22 | 5 sources | **Justified.** Prism / Town / Extension |
| `Sector A (bare)` | 8 | burst, lre_lda | **CONFIRMED drop** — multi-society even in-document |
| `Sector F (bare)` | 21 | asas, burst | **CONFIRMED drop** — multi-society even in-document |
| `N Block (unqualified)` | 19 | asas, elegant, lre_lda, milkiyat, mohsin | Justified. Means LDA City in lre_lda, something else elsewhere |
| `M Block (unqualified)` | 10 | mohsin | Justified |
| `L Block (unqualified)` | 7 | asas, elegant, milkiyat, mohsin | Justified |
| `Block B (bare)` | 1 | cdb_ph10 | Justified |
| `Block D (bare)` | 6 | mohsin | Justified |
| `Block S (bare)` | 2 | mohsin | Justified |
| `Block X (bare)` | **0** | — | **VACUOUS.** Never occurs. Drop is untested |
| `DHA Lahore (bare as phase)` | 0 | — | **VACUOUS.** Never occurs as a bare form |
| `Model Town` | 18 | milkiyat | Justified as coverage gap — no entity-level source |
| `Johar Town` | 10 | milkiyat | as above |
| `Faisal Town` | **0** | — | **VACUOUS.** Never occurs |
| `Ring Road periphery` | 30 | asas, cdb, lre_lda, milkiyat | Justified as coverage gap |
| `On Call` | 15 | lre_sep | **Not a place string.** Must be stored as `rate=null, rate_unavailable=true` |
| `Call us for Rates` | 5 | lre_sep | as above |

## Three findings

### 1. Two drops are vacuous and one is missing

`Block X (bare)`, `DHA Lahore (bare as phase)` and `Faisal Town` **never occur** in
any fetched page. They are not wrong, but they are untested — asserted as
precautions and never exercised. They should be annotated `untested` rather than
counted as validated drops.

**`Sector B` occurs 10 times across 4 sources and is not in `drop.csv` at all.**
The drop list covers `Sector A` and `Sector F` but omits `Sector B`. A gap in a
safety rule is a bug, not a redundancy.

### 2. ~~`Sector A` / `Sector F` are resolvable~~ — **RETRACTED 2026-10-01**

> **This finding was based on two sources and is wrong at corpus scale.** The
> multi-page validation pass (84 pages, `validation-R1-R6.md`) counted societies per
> sector letter *within the document containing it*: `Sector A` → Askari 6, Bahria 3,
> **DHA 6**. `Sector B` → Askari 2, Bahria 6. **Twelve letters map to more than one
> society even with full document scope.** Document scope does not disambiguate
> sector letters. The `document_scoped` evidence_state on these drops is withdrawn;
> they are genuine drops.

These are the exact strings the review's R6 used as proof, and the proof was
circular. But the underlying claim is separately true and now verified:

- `Sector F` occurs **21 times**, always with an unambiguous society in the
  **document that contains it** — 21 in `asas` (a Bahria Town sector table) and
  `burst` (an Askari 10 sector table)
- `Sector A` occurs 8 times, likewise document-scoped

The string alone is ambiguous. **The document is not.** A resolution model that
carries document scope resolves these correctly, and a model that does not will
drop 29 real observations.

**SUPERSEDED.** The claim that document scope resolves these is withdrawn. The
corpus shows 12 letters remain multi-society in-document. Document scope survives
only for bare `Phase N` (0.7% ambiguous in-document), not for sector letters.

### 3. `On Call` / `Call us for Rates` are a different category entirely

20 occurrences across one source. These are not ambiguous places — they are
**missing values**. They must be stored as `rate = null, rate_unavailable = true`,
never as a number and never as a place ambiguity. The drop list currently files
them beside genuine entity ambiguity, which conflates two unrelated failure modes.

## Actions taken

- `drop.csv` gains an `evidence_state` column: `confirmed` (occurs and is
  unresolvable), `untested` (asserted, never observed), `not_a_place` (missing value)
- `Sector B` **added** as a drop, with its 10 occurrences
- `Sector A` / `Sector F` evidence_state corrected from `document_scoped` to
  `confirmed` following the multi-page validation. They are genuine drops.
- `On Call` / `Call us for Rates` reclassified `not_a_place`

## What this does NOT establish

The dry-run tested **one page per source**. A string absent from one page of
mahsinestate may appear on another. `Block X` and `Faisal Town` are untested, not
disproven. Neither can be retired as a precaution.

Reconciliation must be re-run against all accessible sources before any drop rule
is considered validated.