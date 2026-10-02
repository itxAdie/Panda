# Source Registry — Lahore Risk/Possession Knowledge Layer

Created by /office-hours Step 2, 2026-10-01. Source discovery only — no extraction.
Crawl policy verified against live `robots.txt` on 2026-10-01.

Fields per source: name, URL, what it publishes, date visibility, crawl policy,
Lahore coverage, gaps.

---

## Tier 1 — Primary corpus (file-level rates, dated, high update frequency)

### 1. DHA Real Estate.pk (Islam Estate / Faraz Ali)
- **URL:** https://dharealestate.pk/
- **Publishes:** DHA file rates by phase/size/file-type, affidavit vs allocation,
  commercial file rates, LDA City possession blocks, transfer process (NDC, FRC),
  fee schedules, tax regime
- **Dates visible:** **Yes, explicit** — "DHA Lahore Files Daily Update – 30-08-2026"
  in the body text. Multiple dated posts per month (17 Aug, 25 Aug, 30 Aug 2026 observed)
- **Crawl policy:** robots.txt allows all, disallows `/wp-admin/` only
- **Coverage:** DHA Phases 7, 9 Prism, 9 Town, 10 (also as "Phase X"), 13; LDA City;
  DHA Quetta; commercial CCA series
- **Gaps:** DHA only — no Bahria, no Gulberg, no Askari. Rates are market quotes, not
  transaction prices. No block-level granularity in most posts (phase-level only)

### 2. Lahore Real Estate (LRE)
- **URL:** https://lahorerealestate.com/
- **Publishes:** Multi-city file rates, LDA City + Lake City file rates, phase-level
  development and possession updates, balloting news, commercial rates
- **Dates visible:** **Yes** — dated posts plus an inline "as of 26th September 2026"
  disclaimer on rate tables
- **Crawl policy:** robots.txt `Disallow:` (empty) — allows all crawlers
- **Coverage:** DHA (all phases incl. Rahbar Sec-4, Ph 12, Ph 13), LDA City, Lake City,
  RUDA projects; some non-Lahore cities mixed in
- **Gaps:** Non-Lahore cities dilute Lahore signal — extraction must filter by city.
  Many rates are "Call us for Rates" rather than published numbers

### 3. MAAN ESTATE
- **URL:** https://maanestate.com/
- **Publishes:** Monthly DHA market briefings, FBR tax changes, fee schedules,
  possession and balloting expectations, risk commentary on file investment
- **Dates visible:** **Yes** — monthly cadence, e.g. "DHA Lahore Monthly Market Update –
  August 2026"; explicitly flags unconfirmed vs confirmed information
- **Crawl policy:** No robots.txt found; privacy page returns 403. **Unstated = silence,
  not permission** — record as permissive-by-default with attribution
- **Coverage:** DHA Lahore primarily (Phases 5, 6, 7, 8, 9, 10); some Bahria, Askari
- **Gaps:** Low volume (monthly). Unique value is the *risk and tax* commentary, not
  raw rate tables

---

## Tier 2 — Secondary corpus (area knowledge, risk and process focus)

### 4. ASAS Properties
- **URL:** https://asaspropertiespk.com/
- **Publishes:** DHA vs Bahria Town comparison, phase-level and sector-level price
  tables, rental yields, capital appreciation, resale liquidity, legal and verification
  guidance
- **Dates visible:** **Yes** — "reviewed on a rolling basis"; mid-2026 figures stated
- **Crawl policy:** No robots.txt (site not reachable at check time). Record before fetch
- **Coverage:** DHA Phases 1-13, Bahria Town Sectors A-F, G/H, Overseas Enclave,
  Bahria Orchard
- **Gaps:** Broader than deep. Notes its own figures come from site visits, not
  portals — high value, harder to verify. **States asking prices run 8-10% above
  accepted on-the-ground values** — directly relevant to the confidence model

### 5. CDB Properties
- **URL:** https://cdbrealestate.com/
- **Publishes:** DHA Phase 10 balloting status, official-vs-expected distinction,
  file rates, installment plan terms, affidavit vs allocation transfer requirements
- **Dates visible:** **Yes** — dated posts, tracks DHA official announcements
  (Dec 2025 plan, Jan 2026 stall, Aug 2026 confirmation)
- **Crawl policy:** robots.txt allows all, disallows `/wp-admin/` only
- **Coverage:** DHA Phase 10 focused, with Bahria comparison
- **Gaps:** Narrow. But the *best single source for the official-vs-rumour distinction*
  — a fact type nobody else in this set separates cleanly

### 6. milkiyat.com
- **URL:** https://milkiyat.com/
- **Publishes:** Lahore market guide, Gulberg guide, zone-level price-per-marla bands,
  rental yields, days-to-sell, tax/PLRA transfer mechanics, per-zone risk column
- **Dates visible:** **Yes** — "current to June–July 2026", published dates on guides
- **Crawl policy:** robots.txt allows content, disallows `/api/`, `/dashboard`,
  `/properties/*/inquiry`, and query-string variants. Article and city-guide pages
  are **explicitly crawlable**
- **Coverage:** City-wide Lahore zones — Gulberg, Model Town, Johar Town, DHA 5-6,
  DHA 9-11, LDA City, Ring Road periphery
- **Gaps:** Islamabad-weighted (most of its article corpus is Islamabad). Lahore
  content is strong but is a minority of the site. Has a per-zone "typical days to
  sell" and "primary risk" field that no other source carries

### 7. LexForm (legal practice)
- **URL:** https://lex-form.com/
- **Publishes:** Legal risk analysis, DHA vs Bahria legal structure differences,
  approval/NOC status, possession dispute patterns, transfer and verification procedure
- **Dates visible:** Partial — dated posts
- **Crawl policy:** robots.txt `Allow: /` — explicitly allows all
- **Coverage:** DHA and Bahria Town schemes, structurally
- **Gaps:** Qualitative, not numeric. Highest-authority source on risk fact types
  (`litigation_status`, `transfer_process`, legal risk) and no substitute for it

### 8. mohsinestate.com
- **URL:** https://mohsinestate.com/
- **Publishes:** DHA buyer mistakes, red flags, transfer and verification checklists
- **Dates visible:** Partial
- **Crawl policy:** **Notable** — explicitly allows GPTBot, ChatGPT-User,
  OAI-SearchBot, PerplexityBot, ClaudeBot and Google bots; blocks Bytespider,
  CCBot, Amazonbot and meta-externalagent. `User-Agent: *` disallows only `/wp-admin/`
- **Coverage:** DHA Phases 6-10
- **Gaps:** Content-light. But its robots.txt is the clearest signal in the whole set
  that AI access is anticipated

### 9. Askari 10 / Burstforum
- **URL:** https://burstforum.com/
- **Publishes:** Sector-level house and flat prices, rental yields, sector movement
  over time, the "no plot file market" structural fact for built-out societies
- **Dates visible:** **Yes, explicit** — "as of the June and July 2026 update",
  with per-sector month-over-month figures
- **Crawl policy:** No robots.txt (site not reachable at check time). Record before fetch
- **Coverage:** Askari 10 only
- **Gaps:** Single society. Notable for the **structural insight**: built-out societies
  have no file market, so the entire file-risk fact model does not apply to them.
  This is a fact-type the other sources miss

### 10. Elegant DHA
- **URL:** https://elegantdha.com/
- **Publishes:** Phase change and market movement commentary, DHA-specific
- **Dates visible:** Partial
- **Crawl policy:** robots.txt allows all. **Terms page is Lorem ipsum placeholder** —
  no crawl policy exists because the site has no policy
- **Coverage:** DHA Phase 2 focus
- **Gaps:** Weakest of the ten. Include only to round out phase coverage; verify it
  earns its place during the dry-run

---

## Coverage matrix

| Source | DHA | Bahria | LDA City | Gulberg | Askari | Rate tables | Process/risk | Dates |
|---|---|---|---|---|---|---|---|---|
| DHA Real Estate.pk | Ph 7-13 | — | yes | — | — | dense | yes | daily |
| Lahore Real Estate | Ph 1-13 | — | yes | — | — | dense | partial | dated |
| MAAN ESTATE | Ph 5-10 | some | — | — | some | sparse | strong | monthly |
| ASAS Properties | Ph 1-13 | Sectors A-H | — | — | — | phase/sector | yes | rolling |
| CDB Properties | Ph 10 | some | — | — | — | narrow | strong (official-vs-rumour) | dated |
| milkiyat.com | Ph 5-11 | yes | yes | yes | — | zone-level | yes | dated |
| LexForm | structural | structural | — | — | — | none | strongest | partial |
| mohsinestate | Ph 6-10 | — | — | — | — | none | yes | partial |
| Burstforum | — | — | — | — | 10 | sector-level | — | dated |
| Elegant DHA | Ph 2 | — | — | — | — | sparse | — | partial |

---

## Structural gaps across the whole set

1. **Askari, Johar Town, Faisal Town, Model Town, Ring Road schemes are almost
   entirely absent** except via milkiyat. Five of ten sources are DHA-only.
2. **Bahria Town is covered by two sources** (ASAS, LexForm) and neither is a
   dedicated Bahria rate publisher. A dedicated Bahria source is the highest-value
   addition to this set.
3. **Gulberg and Model Town** appear only as price zones in milkiyat. These are
   established LDA-regulated areas with no file/possession risk, so they may need a
   different fact model entirely.
4. **No Roman Urdu source.** Every source here is English. Open Question 3 is
   unresolved and this registry does not fix it.
5. **Every rate is an asking price**, not a transaction price. Pakistan has no
   mandatory transaction price disclosure. ASAS is the only source that explicitly
   models the asking-vs-accepted gap (8-10%).
7. **No official source.** DHA and LDA publish their own notices. Nothing in this
   set is authoritative — the corpus is entirely secondary reporting.

---

## Notes for the normalization map (Step 3)

Naming variants already observed in these sources, to seed the alias table:

- DHA: `DHA Ph 6`, `DHA Phase 6`, `DHA Phase VI`, `Defence Phase 6`,
  `DHA Lahore Phase 6`, `DHA P6`
- DHA Phase 10 appears as both `Phase 10` and **`Phase X`**
- Phase 9 splits into **`DHA Ph 9 Prism`**, **`DHA Ph 9 Town`**, **`Ph 9 Extension`**
  (per CDB: Phase 10 was earlier known as Phase 9 Extension)
- `Ph 11 (Rahbar)`, `Rahbar Sec-4`, `DHA Rahbar`
- `Ph 12`, `Ph 13`, `Ph 13 (Ex-DHA City)`, `DHA City` — several different schemes
  referred to as "DHA City"; treat as distinct and disambiguate by source
- Bahria uses **sectors**, not blocks: `Sector A-F`, `Sector C (Main Boulevard)`,
  `Bahria Orchard`, `Overseas Enclave`, `Bahria Nasheman`
- LDA City uses **blocks** (A1, B1, E1, H, L, M, N, P) and also **sectors**
  (Jinnah Sector, Iqbal Sector) — two competing hierarchies in one scheme
- File types: `Allocation`, `Affidavit`, `Barcode`, `Balloted`, `Unballoted`
- Sizes: `5 Marla`, `5-Marla`, `5M`, `20 Marla`, `1 Kanal`, `2 Kanal`,
  `CCA-3`, `4 Marla Commercial`
- Currency/unit variants: `Lac`, `Lakh`, `Lacs`, `Crore`, `Cr`, `PKR 43.75L`

**The Phase 9 / Phase 10 / "DHA City" clusters are the hard cases.** Each involves
genuinely ambiguous naming that will require source-level disambiguation, and the
design rule is to drop rather than guess.