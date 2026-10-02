# Controlled Live Extraction — Runbook

**Status: BLOCKED on OpenRouter credits (402). Run nothing until they exist.**

This is the next run, and it is deliberately narrow. Do not expand past step 2 until
step 1 is manually inspected.

---

## Preconditions

```bash
python3 manage.py check_gateway
```

All three hops must PASS. A failure here is a gateway problem; stop and fix that, do
not run extraction.

---

## Step 1 — Section file (2.6k chars, ~650 input tokens)

```bash
python3 manage.py run_live_page \
  --url "https://dharealestate.pk/dha-lahore-files-prices-allocation-affidavit-rates-phase-13-phase-10-phase-9-prism-phase-7-phase-9-town/" \
  --source dha_rates \
  --file data/pages/dha_rates_section.html \
  --limit 5
```

### The first thing to check, before anything else

**Does `data/live/dha_rates_raw_response.txt` contain candidate JSON?**

If it contains prose, markdown, or a summary: **stop. The contract was not delivered.**
That is the defect class that produced the earlier false zero-candidate result. Do not
interpret anything downstream as corpus evidence.

- Contract delivered looks like a JSON array of
  `{fact_type, value, place_ref, raw_quote, as_of, size_marla?, file_type?}`
- Contract absent looks like `# ...` headings or a markdown table

### Then inspect EVERY candidate by hand

Do not trust the validator's accept/reject verdict as its own review. For each one:

| Check | Question |
|---|---|
| Quote exact | Is `raw_quote` a contiguous substring of the page text? Word for word. |
| Place valid | Does `place_ref` appear in the quote or its section heading? |
| Size supported | If `size_marla` is set, does the quote state that size? |
| File type supported | If `file_type` is set, does the quote state that file type? |
| No invention | Does any number in `value` appear in the quote? |

### Validator behaviour expected on a well-formed run

| Validator | Should reject | Why |
|---|---|---|
| V1 | fabricated or paraphrased quotes | not a substring |
| V2 | numbers absent from the quote | arithmetic or inference |
| V10 | a fact_type the quote does not speak | e.g. balloting filed as possession |
| V11 | missing or unsupported size/file_type | ambiguity |

**A run where every validator fires zero times is suspicious, not reassuring.** It may
mean the boundary is not actually being exercised. Check that the candidates file
contains a mix rather than uniformly perfect input.

---

## Step 2 — Provenance and mutation checks

After step 1 is clean:

```bash
python3 manage.py shell -c "
from corpus.models import Fact, BlockIdentity, Observation
print('facts      :', Fact.objects.count())
print('  raw_quote mandatory:', not Fact.objects.filter(raw_quote='').exists())
print('  qualified rates    :', not Fact.objects.filter(fact_type='rate', qualifier_status='').exists())
print('observations:', Observation.objects.count())
print('forced     :', Observation.objects.filter(adjudication='forced').count())
print('verified   :', BlockIdentity.objects.filter(verified=True).count(), '(must stay 1)')
"
```

Hard requirements:

- **Zero forced adjudications.** A forced row is a tripwire, not a metric.
- **`BlockIdentity.verified` must not change.** The 1 corroborated identity
  (`DHA Phase 5 [M]`) stays verified; the other 56 stay blocked. If this count moves,
  something reached the promotion flag and that is a defect, not progress.
- **Every stored fact has a non-empty `raw_quote`.** It is the audit path.
- Every stored rate has a `qualifier_status` of complete/partial/unknown.

---

## Step 3 — Full page (22k chars, ~6k input tokens)

Only after steps 1 and 2 pass, and only with enough credits:

```bash
python3 manage.py run_live_page \
  --url "https://dharealestate.pk/dha-lahore-files-prices-allocation-affidavit-rates-phase-13-phase-10-phase-9-prism-phase-7-phase-9-town/" \
  --source dha_rates \
  --file data/pages/dha_rates.html \
  --limit 8
```

Still **one page**. No bulk. A larger page mostly raises input tokens and adds more
chances for the model to drift on quote fidelity.

---

## Do not do these

- **Do not read the earlier zero-candidate run as corpus evidence.** It was an
  infrastructure failure. See `data/live/README.md`.
- **Do not lower `max_tokens` to fix a 402.** The input is ~6k tokens; the budget error
  is about input size. Shrinking output cannot help.
- **Do not expand to multiple pages** until the single full page is manually inspected.
- **Do not delete a raw response on failure.** It is the only evidence of what the model
  returned, and it is what caught the contract-delivery defect.
- **Do not raise acceptance volume by weakening a validator.** Rejection volume is a
  diagnostic. A validator that suddenly stops firing is the thing to investigate.

---

## If a validator rejects almost everything

That is information, not a bug to tune away. It means either the validator is
mis-specified or the model is being asked for something the sources cannot support.
Both are worth seeing before changing anything.

The precedent: the first real extraction surfaced three holes no unit test had found —
V9 place corroboration, V10 fact-type cue, and V6 missing the quote.