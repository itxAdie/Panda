"""Milestone 2 acceptance tests — society slot.

Adds a society slot to the resolver so society-qualified strings bind, and holds the
line on three new false-match classes the slot opened up:

  * abbreviated cross-city forms  ('DHA Ph-1', 'DHA 1', 'DHA P2')
  * 'DHA Valley'                  (an Islamabad society, not DHA Lahore)
  * bare 'Gulberg'                (a district; only Gulberg III is an entity)

Rate is still never asserted without a false-match count alongside it.
"""

from corpus import DROPPED, RESOLVED, UNRESOLVED
from corpus.models import Place
from corpus.tests.test_acceptance import FIXTURE, ResolverTestCase

# 992 (M1) -> 1140 with the society slot, after three false-match classes were closed
# (abbreviated cross-city forms, DHA Valley, bare Gulberg). The qualified
# 'DHA Lahore Phase 1-4' forms resolve and must keep resolving.
MILESTONE2_RESOLVED = 1140
MILESTONE2_TOTAL = 2725
MILESTONE2_RATE = 41.8


class TestSocietySlot(ResolverTestCase):
    """Society-qualified strings bind to society-level entities."""

    def test_society_names_resolve(self):
        cases = {
            "Bahria Town": "Bahria Town Lahore",
            "LDA City": "LDA City Lahore",
            "Lake City": "Lake City",
            "Askari 10": "Askari 10 Lahore",
            "Gulberg III": "Gulberg III",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                res = self.r.resolve(text)
                self.assertEqual(res.outcome, RESOLVED, f"{text} did not resolve")
                self.assertEqual(res.place.canonical_name, expected)

    def test_bahria_town_resolves_to_bahria_not_dha(self):
        res = self.r.resolve("Bahria Town")
        self.assertEqual(res.place.society.slug, "soc_bahria_lahore")

    def test_lda_city_resolves_to_lda(self):
        res = self.r.resolve("LDA City")
        self.assertEqual(res.place.society.slug, "soc_lda_city")

    def test_society_slot_is_not_a_phase_binding(self):
        """A society has no phase. It must bind to a level='society' Place."""
        res = self.r.resolve("Bahria Town")
        self.assertEqual(res.place.level, "society")


class TestSocietySlotDidNotBreakAnything(ResolverTestCase):
    def test_sector_letters_still_unresolved(self):
        for s in ("Sector A", "Sector B", "Sector F", "Sector C", "Sector G", "Sector H",
                  "Block B", "Block X", "Block Q"):
            with self.subTest(s=s):
                self.assertIsNone(self.r.resolve(s).place)

    def test_cca_still_a_measurement(self):
        for s in ("CCA-3", "CCA3", "DHA Phase 8 CCA3"):
            self.assertNotEqual(self.r.resolve(s).outcome, RESOLVED)

    def test_lahore_qualified_phases_still_resolve(self):
        for n in (1, 2, 3, 4):
            res = self.r.resolve(f"DHA Lahore Phase {n}")
            self.assertEqual(res.outcome, RESOLVED)
            self.assertEqual(res.place.society.slug, "soc_dha_lahore")

    def test_drops_still_precede_canonical(self):
        self.assertEqual(self.r.resolve("DHA Phase 2").outcome, DROPPED)
        self.assertIsNone(self.r.resolve("DHA Phase 2").place)


class TestAbbreviatedCrossCity(ResolverTestCase):
    """The guard must fire on every SPELLING of a bare cross-city phase.

    M1's guard matched only 'DHA Phase 1-4'. The society slot let 'DHA Ph-1' and
    'DHA 1' bind to Lahore — same failure class, different surface form.
    """

    FORMS = [
        "DHA Phase 1", "DHA Phase 2", "DHA Phase 3", "DHA Phase 4",
        "DHA Ph-1", "DHA Ph-2", "DHA Ph-3", "DHA Ph-4",
        "DHA Phase-1", "DHA Phase-2", "DHA Phase-3", "DHA Phase-4",
        "DHA 1", "DHA 2", "DHA 3", "DHA 4",
        "Defence Phase 2", "Defence Ph-2",
    ]

    def test_all_abbreviated_forms_dropped(self):
        for s in self.FORMS:
            with self.subTest(s=s):
                res = self.r.resolve(s)
                self.assertIsNone(res.place, f"'{s}' bound to a place — cross-city leak")
                self.assertEqual(res.outcome, DROPPED, f"'{s}' was not dropped")

    def test_no_lahore_place_for_bare_forms(self):
        for s in self.FORMS:
            res = self.r.resolve(s)
            self.assertIsNone(res.place, f"'{s}' bound {res.place}")

    def test_zero_cross_city_resolutions_in_corpus(self):
        import json
        import re
        data = json.loads(FIXTURE.read_text())
        # 'Lahore' must NOT be optional: the qualified form is legitimately resolvable.
        bare = re.compile(r"^(?:DHA|Defence)\s+(?:Ph(?:ase)?\.?|P)?\s*-?\s*[1-4]$", re.I)
        bad = [(s, n) for s, n in data["occurrences"].items()
               if bare.match(s) and self.r.resolve(s).outcome == RESOLVED]
        self.assertEqual(bad, [], f"cross-city resolutions in corpus: {bad}")


class TestDhaValley(ResolverTestCase):
    """'DHA Valley' is an Islamabad society. Its Phase 7 is not Lahore's Phase 7."""

    def test_dha_valley_dropped(self):
        for s in ("DHA Valley", "DHA Valley Phase 7", "DHA Valley (Phase 7)"):
            with self.subTest(s=s):
                self.assertEqual(self.r.resolve(s).outcome, DROPPED)
                self.assertIsNone(self.r.resolve(s).place)

    def test_dha_v_is_not_phase_five(self):
        """'DHA V' is a truncation of 'DHA Valley'.

        A roman-numeral phase slot read it as 'DHA Phase 5'. It must not bind.
        """
        res = self.r.resolve("DHA V")
        self.assertNotEqual(res.outcome, RESOLVED)
        self.assertIsNone(res.place)

    def test_roman_numerals_require_explicit_designator(self):
        """'DHA Phase VI' resolves; 'DHA VI' must not."""
        self.assertEqual(self.r.resolve("DHA Phase VI").outcome, RESOLVED)
        self.assertIsNone(self.r.resolve("DHA VI").place)


class TestBareGulberg(ResolverTestCase):
    """Bare 'Gulberg' is a district. Only Gulberg III is an entity."""

    def test_bare_gulberg_unresolved(self):
        res = self.r.resolve("Gulberg")
        self.assertEqual(res.outcome, UNRESOLVED)
        self.assertIsNone(res.place)

    def test_gulberg_iii_resolves(self):
        res = self.r.resolve("Gulberg III")
        self.assertEqual(res.outcome, RESOLVED)
        self.assertEqual(res.place.canonical_name, "Gulberg III")


class TestMilestone2Baseline(ResolverTestCase):
    def test_corpus_shape(self):
        import json
        data = json.loads(FIXTURE.read_text())
        self.assertEqual(data["total_occurrences"], MILESTONE2_TOTAL)

    def test_rate_at_least_milestone2_floor(self):
        """M2 set 1140 as a FLOOR. M3 (block identity) legitimately raised it to 1351.

        Exact counts belong to the milestone that introduced them; this file pins the
        minimum so a later regression or a guard that stopped firing is caught.
        """
        import json
        from corpus import RESOLVED as R
        data = json.loads(FIXTURE.read_text())
        resolved = sum(n for s, n in data["occurrences"].items()
                       if self.r.resolve(s).outcome == R)
        self.assertGreaterEqual(resolved, MILESTONE2_RESOLVED,
                                f"fell below the M2 floor: {resolved} < {MILESTONE2_RESOLVED}")

    def test_no_forced_adjudications(self):
        from corpus.models import Observation
        self.assertEqual(Observation.objects.filter(
            adjudication=Observation.ADJ_FORCED).count(), 0)

    def test_resolver_still_exposes_no_coverage_metric(self):
        forbidden = ("rate", "coverage", "percent", "ratio", "score", "baseline")
        for name in dir(self.r):
            if name.startswith("_"):
                continue
            self.assertFalse(any(f in name.lower() for f in forbidden),
                             f"coverage-like member: {name}")

    def test_no_society_slot_place_is_unevidenced(self):
        """New society-slot bindings must land on evidenced entities."""
        for name in ("Bahria Town Lahore", "LDA City Lahore", "Lake City", "Askari 10 Lahore"):
            p = Place.objects.filter(canonical_name__iexact=name).first()
            self.assertIsNotNone(p)
            self.assertNotEqual(p.evidence_status, "unevidenced")
            self.assertTrue(p.evidence, f"{name} has no evidence")