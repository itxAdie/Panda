# ToS Verification — REDONE

Re-verified 2026-10-01 with an honest user-agent (`PandaResearch/0.1`). This
**supersedes** the original gate, which was built on a defective probe.

## Why the original was wrong

The first pass sent `Mozilla/5.0 (compatible; research)`. Two sources refused it and
returned `403` / `000`. I recorded them as "no policy" and "unreachable". Both
conclusions were **artifacts of my own user-agent string**, not properties of the
sites. One reviewer's independent check, re-verified here:

- `maanestate.com` — **has a 119-line `# MAAN ESTATE - Crawl Policy`**, a published
  `/llm.txt`, `/llms.txt`, `/ai.txt`, `/ai.json`, and `/sitemap-ai.xml` built
  explicitly for AI consumers, and imposes **`Crawl-delay: 10`**
- `asaspropertiespk.com` — **HTTP 200**, ordinary WordPress policy

`Crawl-delay: 10` is an obligation the original standing-obligations list missed
entirely.

## Verified policies — all 10 sources, honest UA

| Source | HTTP | robots.txt | Wildcard | Crawl-delay | Verdict |
|---|---|---|---|---|---|
| maanestate.com | **403** | **119 lines** | content allowed, `/wp-admin` + query params blocked | **10s** | **Permitted, rate-limited.** See below |
| asaspropertiespk.com | 200 | 11 lines | content allowed | — | Permitted |
| lahorerealestate.com | 200 | 8 lines | `Disallow:` empty | — | Permitted |
| elegantdha.com | 200 | 8 lines | `Disallow:` empty | — | Permitted |
| lex-form.com | 200 | 18 lines | `Allow: /` | — | Permitted |
| dharealestate.pk | 200 | 5 lines | `/wp-admin/` only | — | Permitted |
| mohsinestate.com | 200 | 33 lines | `/wp-admin/` only | — | Permitted |
| cdbrealestate.com | 200 | 4 lines | `/wp-admin/` only | — | Permitted |
| milkiyat.com | 200 | 192 lines | blocks `/api/`, `/dashboard`, `/properties/*/inquiry`, query-string variants | — | Permitted for articles/guides |
| burstforum.com | 200 | 19 lines | content allowed | — | Permitted |

**No source prohibits general crawling. One (maanestate) prohibits specific AI
training crawlers** — `CCBot`, `Bytespider`, and others — while explicitly allowing
research retrieval via its published AI hub.

## The maanestate complication

`robots.txt` permits content for wildcard UAs, but the **site returns 403 to all
page requests** from this host, regardless of UA, including a plain honest string.
Its machine-readable endpoints are served fine: `/llm.txt`, `/ai.txt`, `/ai.json`,
`/sitemap-ai.xml` all return 200.

Three distinct facts, previously conflated into one wrong conclusion:

1. **Policy exists and permits research retrieval** — with `Crawl-delay: 10`
2. **Server-side bot security blocks page fetches** — its own robots.txt notes
   "Server-side bot/security rules may also be enforced in .htaccess"
3. **The content is not lost** — it is served through a first-class AI hub designed
   for exactly this access pattern

## Decision

**Harvesting permitted for 9 of 10 sources.** For maanestate, the correct path is
its published AI channel rather than working around the server-side block:
`sitemap-ai.xml` → `ai.txt` / `ai.json` / `/ai/` hub. **Do not attempt to evade the
403.** The site has deliberately chosen a machine-readable channel; using it is
compliance, working around the block is not.

If the AI channel proves insufficient, maanestate is dropped from the corpus. Its
absence is acceptable: it overlaps DHA Real Estate.pk and Lahore Real Estate, both
fully accessible.

## Corrected standing obligations

1. Identify honestly as `PandaResearch/0.1`. Never spoof a browser UA — that is what
   produced the original defective gate, and it is also disrespectful to operators who
   publish crawl policies precisely so they are read.
2. **Honour `Crawl-delay: 10` on maanestate.**
3. Respect each source's wildcard exclusions. milkiyat's `/api/` and inquiry paths
   are blocked and stay blocked.
4. Local cache, re-run periodically rather than hammering live pages.
5. Attribute every fact to its source with an `as_of` date.
6. Record per-source policy before fetching any **new** source.
7. **Never evade a 403.** Use the published channel or drop the source.
8. Revisit before any public launch. The live risk is social, not legal.

## Correction to the record

The original ToS section in the design doc claimed maanestate had *"No robots.txt
found"* and was *"Unstated = silence, not permission"*. That was wrong, and it was
wrong in the direction of understating an operator's stated wishes — a site with a
119-line policy and a published AI hub was recorded as having no policy at all.