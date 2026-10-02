"""ONE live page through the real LLM, then the deterministic boundary.

Deliberately one page and no bulk. Output is written to data/live/ for manual review
of every candidate — accepted and rejected — before any expansion.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from corpus.extract import FileProposer, LLMProposer, extract_document, ingest_page
from corpus.models import Fact, Observation
from corpus.resolver import Resolver


class Command(BaseCommand):
    help = "Run ONE page through the live LLM and the V1-V11 boundary."

    def add_arguments(self, parser):
        parser.add_argument("--url", required=True)
        parser.add_argument("--source", required=True)
        parser.add_argument("--file", help="local HTML file instead of fetching")
        parser.add_argument("--limit", type=int, default=12)
        parser.add_argument("--out", default="data/live")

    def handle(self, *args, **opts):
        proposer = LLMProposer()
        if not proposer.check_ready():
            return
        raw = (Path(opts["file"]).read_text(errors="ignore") if opts.get("file")
               else _fetch(opts["url"]))
        doc = ingest_page(opts["source"], opts["url"], raw)
        self.stdout.write(f"  document: {doc.source.slug} {len(doc.raw_text)} chars")

        # Call through and capture the RAW payload before any parsing. Without this a
        # truncated or prose response is indistinguishable from "the model found
        # nothing" — which is exactly the wrong conclusion to draw.
        try:
            raw_payload = proposer._call(doc.source.slug, doc.raw_text)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"LLM call failed: {type(e).__name__}: {e}"))
            return
        out = Path(opts["out"]); out.mkdir(parents=True, exist_ok=True)
        (out / f"{doc.source.slug}_raw_response.txt").write_text(raw_payload)
        self.stdout.write(f"  raw response: {len(raw_payload)} chars -> "
                          f"{out / (doc.source.slug + '_raw_response.txt')}")
        try:
            rows = list(proposer._parse(raw_payload, limit=opts["limit"]))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"parse failed: {type(e).__name__}: {e}"))
            return
        if not rows:
            self.stdout.write(self.style.WARNING(
                "  0 candidates parsed. Inspect the saved raw response before "
                "concluding the model found nothing."))

        # FileProposer expects {source_slug: [rows]}; writing a bare list breaks it.
        (out / f"{doc.source.slug}_candidates.json").write_text(
            json.dumps({doc.source.slug: rows}, indent=2, sort_keys=True))
        self.stdout.write(f"  proposed: {len(rows)} candidates (saved for review)")

        # replay through the deterministic boundary via FileProposer, so the live
        # candidates and the reviewed run are the same artefacts
        rep = extract_document(doc, FileProposer(out / f"{doc.source.slug}_candidates.json"),
                               Resolver())
        self.stdout.write("")
        self.stdout.write(f"  considered {rep.considered}  accepted {rep.accepted}  "
                          f"rejected {rep.rejected}")
        for k, v in sorted(rep.by_validator.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"    {k:26} {v}")
        self.stdout.write("")
        for fact, cand in rep.facts:
            self.stdout.write(f"  ACCEPT [{fact.place.canonical_name}] {fact.fact_type}")
            self.stdout.write(f"      {fact.as_qualified_string()[:100]}")
            self.stdout.write(f"      quote: {fact.raw_quote[:96]}")
        for v, reason in rep.reasons:
            self.stdout.write(f"  REJECT {v:26} {reason[:92]}")


def _fetch(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "PandaResearch/0.1 (+research)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")
