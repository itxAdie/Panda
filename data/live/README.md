# Live run artifacts

Raw model responses are kept here **deliberately and permanently**. That
instrumentation is what distinguished "the model found no facts" from "the extraction
contract never arrived" — a failure that errored nowhere and would otherwise have
produced a false conclusion about the corpus.

Never delete a `_raw_response.txt` on failure. It is the only evidence of what the
model actually returned.

## Artifact status

| file | run | status |
|---|---|---|
| `dha_rates_raw_response.txt` | first live call | **INVALID FOR CORPUS CONCLUSIONS** |
| `dha_rates_candidates.json` | first live call | **INVALID FOR CORPUS CONCLUSIONS** |

### Why those two are invalid

That call ran BEFORE the contract-delivery defect was found. The hosted gateway drops
litellm's `system=` parameter, so the model received the page text and **no extraction
instructions**. It returned a markdown summary reproducing the rate table nearly
verbatim — correct-looking output, zero candidates, and no error anywhere.

The rate figures in that raw response are **not** extraction results and must not be
read as evidence about the corpus. It is an infrastructure failure, not an extraction
outcome.

The raw response IS retained deliberately: it is the artifact that proved the contract
had been dropped.
