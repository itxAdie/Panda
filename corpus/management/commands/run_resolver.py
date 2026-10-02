"""Run the resolver over the corpus fixture and persist Observations.

Offline diagnostic only. The resolver never reads this command's output.
Rate and false-match count are reported TOGETHER, never alone.
"""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from corpus import DROPPED, MEASUREMENT, RESOLVED, UNRESOLVED
from corpus.models import Observation, Source, Document
from corpus.resolver import Resolver

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "corpus_84pages.json"


class Command(BaseCommand):
    help = "Resolve the corpus fixture offline; persist every observation."

    def handle(self, *args, **opts):
        data = json.loads(FIXTURE.read_text())
        r = Resolver()
        total = data["total_occurrences"]
        tally = {RESOLVED: 0, DROPPED: 0, MEASUREMENT: 0, UNRESOLVED: 0}
        Observation.objects.all().delete()
        src, _ = Source.objects.get_or_create(slug="fixture", defaults={"name": "corpus fixture",
            "base_url": "https://example.invalid/fixture", "verified": True})
        doc, _ = Document.objects.get_or_create(source=src, url="https://example.invalid/fixture/84pages")
        forced = 0
        for s, n in data["occurrences"].items():
            res = r.resolve(s, document=doc)
            tally[res.outcome] = tally.get(res.outcome, 0) + n
            adj = {RESOLVED: Observation.ADJ_RESOLVED, DROPPED: Observation.ADJ_DROPPED,
                   MEASUREMENT: Observation.ADJ_MEASUREMENT, UNRESOLVED: Observation.ADJ_UNRESOLVED}[res.outcome]
            Observation.objects.create(observed=s, document=doc, occurrences=n,
                                       adjudication=adj, resolved_to=res.place, stage=res.stage,
                                       reason=res.reason)
            if adj == Observation.ADJ_FORCED:
                forced += n
        rate = 100.0 * tally[RESOLVED] / total
        # false matches: any resolution that contradicts an active drop
        false = Observation.objects.filter(
            adjudication=Observation.ADJ_RESOLVED,
            observed__in=list(r._drops.keys())).count()
        # A cross-city FALSE MATCH is a bare 'DHA Phase N' that got RESOLVED.
        # Correctly-dropped ones are not false matches; they are the policy working.
        crosscity = sum(d.occurrences for d in Observation.objects.filter(
            adjudication=Observation.ADJ_RESOLVED)
            if d.observed.lower() in (f"dha phase {i}" for i in (1, 2, 3, 4)))
        crosscity_held = sum(d.occurrences for d in Observation.objects.filter(
            adjudication=Observation.ADJ_DROPPED)
            if d.observed.lower() in (f"dha phase {i}" for i in (1, 2, 3, 4)))
        self.stdout.write("")
        self.stdout.write(f"  occurrences            {total}")
        self.stdout.write(f"  resolved               {tally[RESOLVED]}  ({rate:.1f}%)")
        self.stdout.write(f"  dropped (by policy)    {tally[DROPPED]}")
        self.stdout.write(f"  measurement/category   {tally[MEASUREMENT]}")
        self.stdout.write(f"  unresolved             {tally[UNRESOLVED]}")
        self.stdout.write(f"  forced adjudications   {forced}")
        self.stdout.write(f"  cross-city false match {crosscity}   (must be 0)")
        self.stdout.write(f"  cross-city held as drop {crosscity_held}")
        self.stdout.write(f"  drop-policy violations {false}")
        self.stdout.write("")
        self.stdout.write("  Rate is only meaningful alongside the two counts above.")
        Observation.objects.create(observed="__summary__", adjudication=Observation.ADJ_UNRESOLVED,
                                   reason=f"rate={rate:.1f}% resolved={tally[RESOLVED]}/{total} "
                                          f"false={false} crosscity={crosscity} forced={forced}")
