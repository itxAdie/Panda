"""Run extraction over real pages and report the boundary's behaviour.

Reports acceptance AND the full rejection distribution. The point is not a high
acceptance rate — it is seeing WHICH validator refuses what, and whether anything
accepted is actually trustworthy.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from corpus.extract import FileProposer, extract_document, load_local_pages
from corpus.models import Fact, Observation
from corpus.resolver import Resolver


class Command(BaseCommand):
    help = "Extract from real pages via the V1-V8 boundary and report the distribution."

    def add_arguments(self, parser):
        parser.add_argument("--proposals", default="data/pages/proposals.json")
        parser.add_argument("--pages", default="data/pages")
        parser.add_argument("--show-accepted", action="store_true")
        parser.add_argument("--show-rejected", action="store_true")

    def handle(self, *args, **opts):
        docs = load_local_pages(opts["pages"])
        if not docs:
            self.stderr.write("no pages found")
            return
        proposer = FileProposer(opts["proposals"])
        resolver = Resolver()

        before_facts = Fact.objects.count()
        before_obs = Observation.objects.count()

        reports = []
        for doc in docs:
            rep = extract_document(doc, proposer, resolver)
            reports.append(rep)

        considered = sum(r.considered for r in reports)
        accepted = sum(r.accepted for r in reports)
        rejected = sum(r.rejected for r in reports)
        byv = {}
        for r in reports:
            for k, v in r.by_validator.items():
                byv[k] = byv.get(k, 0) + v

        self.stdout.write("")
        self.stdout.write("  EXTRACTION — real pages, deterministic boundary")
        self.stdout.write(f"  proposer: {proposer.model}")
        self.stdout.write(f"  pages:    {len(docs)}")
        self.stdout.write("")
        self.stdout.write(f"  considered      {considered}")
        self.stdout.write(f"  accepted        {accepted}  ({100.0*accepted/max(considered,1):.0f}%)")
        self.stdout.write(f"  rejected        {rejected}  ({100.0*rejected/max(considered,1):.0f}%)")
        self.stdout.write("")
        self.stdout.write("  rejection by validator:")
        for k, v in sorted(byv.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"    {k:26} {v}")
        self.stdout.write("")
        self.stdout.write("  persisted:")
        self.stdout.write(f"    facts created         {Fact.objects.count() - before_facts}")
        self.stdout.write(f"    observations created  {Observation.objects.count() - before_obs}")
        self.stdout.write("")

        if opts.get("show_accepted"):
            self.stdout.write("  ACCEPTED:")
            for r in reports:
                for fact, cand in r.facts:
                    self.stdout.write(f"    [{fact.place.canonical_name}] {fact.fact_type} = "
                                      f"{fact.value[:52]}  as_of={fact.as_of}")
                    self.stdout.write(f"        quote: {fact.raw_quote[:88]}")
            self.stdout.write("")

        if opts.get("show_rejected"):
            self.stdout.write("  REJECTED:")
            for r in reports:
                for v, reason in r.reasons:
                    self.stdout.write(f"    {v:26} {reason[:96]}")
            self.stdout.write("")

        forced = Observation.objects.filter(adjudication="forced").count()
        self.stdout.write(f"  forced adjudications: {forced}  (must be 0)")