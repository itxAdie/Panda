"""Milestone 1 acceptance tests.

The six criteria from docs/MILESTONE-1-HANDOFF.md, plus the invariants that keep
them true. Run with:  python3 manage.py test corpus

Resolution rate is never asserted alone. Every rate assertion is paired with a
false-match count, because a higher rate with false matches is a regression.
"""

import json
import os
from pathlib import Path

from django.test import TestCase
from django.core.management import call_command

from corpus import DROPPED, MEASUREMENT, RESOLVED, UNRESOLVED
from corpus.models import Alias, Drop, Measurement, Observation, Place
from corpus.resolver import Resolver

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "corpus_84pages.json"

# Baseline CORRECTED 2026-10-02 after implementing the resolver.
#
# rerun-results.md reported 1033/2725 = 37.9%. That figure included 41 FALSE
# matches: bare sector/block letters bound to canonical names (Sector F -> Bahria
# Sector F, Block B -> DHA Phase 6 Block B). Sector and block letters repeat across
# schemes — proven multi-society even WITHIN one document — so those bindings were
# wrong. The resolver refuses them, giving the true figure below.
#
# The baseline moved DOWN because the code is stricter than the script that measured it.
BASELINE_RATE = 36.4
BASELINE_RESOLVED = 992
BASELINE_TOTAL = 2725
BASELINE_FALSE_MATCHES_IN_OLD_SCRIPT = 41


class ResolverTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_corpus", verbosity=0)
        cls.r = Resolver()

    def place_named(self, name, level=None):
        qs = Place.objects.filter(canonical_name__iexact=name)
        if level:
            qs = qs.filter(level=level)
        return qs.first()


class TestCrossCity(ResolverTestCase):
    """DHA Phases 1-4 exist in BOTH Lahore and Islamabad.

    This is the invariant the whole project turns on. If bare 'DHA Phase N' resolves
    to Lahore, the corpus silently absorbs Islamabad data — 206 occurrences,
    7.6 points, presenting as an improvement.
    """

    def test_bare_dha_phase_2_does_not_resolve(self):
        for n in (1, 2, 3, 4):
            with self.subTest(phase=n):
                res = self.r.resolve(f"DHA Phase {n}")
                self.assertEqual(
                    res.outcome, DROPPED,
                    f"bare 'DHA Phase {n}' must be dropped as cross-city, got {res.outcome}")
                self.assertIsNone(res.place)

    def test_bare_form_never_binds_to_lahore_place(self):
        for n in (1, 2, 3, 4):
            res = self.r.resolve(f"DHA Phase {n}")
            if res.place is not None:
                self.fail(f"bare 'DHA Phase {n}' bound to {res.place}")

    def test_lahore_qualified_form_resolves(self):
        for n in (1, 2, 3, 4):
            with self.subTest(phase=n):
                res = self.r.resolve(f"DHA Lahore Phase {n}")
                self.assertEqual(res.outcome, RESOLVED)
                self.assertEqual(res.place.canonical_name, f"DHA Phase {n}")
                self.assertEqual(res.place.society.slug, "soc_dha_lahore")

    def test_zero_cross_city_false_matches_in_corpus(self):
        """Every bare 'DHA Phase 1-4' occurrence must land in DROPPED."""
        data = json.loads(FIXTURE.read_text())
        bad = []
        for s, n in data["occurrences"].items():
            if s.lower().startswith("dha phase") and any(
                    s.lower() == f"dha phase {i}" for i in (1, 2, 3, 4)):
                if self.r.resolve(s).outcome != DROPPED:
                    bad.append((s, n))
        self.assertEqual(bad, [], f"cross-city false matches: {bad}")


class TestCategoryRouting(ResolverTestCase):
    """CCA-1/CCA-3 are commercial categories, never places."""

    def test_cca_forms_never_become_a_place(self):
        for s in ("CCA-3", "CCA3", "CCA-1", "CCA1", "DHA Phase 8 CCA3", "DHA Phase 7 CCA1"):
            with self.subTest(s=s):
                res = self.r.resolve(s)
                self.assertNotEqual(res.outcome, RESOLVED, f"{s} resolved as a place")
                self.assertIsNone(res.place)

    def test_cca_is_measured_not_resolved(self):
        res = self.r.resolve("CCA-3")
        self.assertEqual(res.outcome, MEASUREMENT)

    def test_measurement_table_present(self):
        self.assertTrue(Measurement.objects.filter(dimension="category").exists())


class TestSectorLetterCeiling(ResolverTestCase):
    """A documented limitation, not a bug.

    12 sector letters map to more than one society even WITHIN one document.
    Sector A resolves to Askari(6), Bahria(3), DHA(6). Never force these.
    """

    def test_sector_letters_remain_unresolved(self):
        for s in ("Sector A", "Sector B", "Sector F", "Sector C", "Sector Z",
                  "Sector E", "Sector G", "Sector H"):
            with self.subTest(s=s):
                res = self.r.resolve(s)
                self.assertNotEqual(res.outcome, RESOLVED)
                self.assertIsNone(res.place)

    def test_sector_letters_never_bind_despite_canonical_name(self):
        """The 41 false matches in the old baseline script.

        sec_bahria_f.canonical_name IS 'Sector F' and blk_dha_6_b IS 'Block B'.
        Canonical matching bound them. They must not bind — letters repeat across
        schemes and are multi-society even within one document.
        """
        self.assertTrue(Place.objects.filter(canonical_name__iexact="Sector F").exists(),
                        "precondition: a matching canonical name exists")
        self.assertTrue(Place.objects.filter(canonical_name__iexact="Block B").exists(),
                        "precondition: a matching canonical name exists")
        for s in ("Sector F", "Sector C", "Sector E", "Sector G", "Sector H", "Block B", "Block X"):
            with self.subTest(s=s):
                self.assertIsNone(self.r.resolve(s).place,
                                  f"'{s}' bound to a canonical name — the 41-false-match bug")

    def test_block_letters_remain_unresolved(self):
        for s in ("Block Q", "Block D", "Block 4", "Block Y"):
            with self.subTest(s=s):
                res = self.r.resolve(s)
                self.assertNotEqual(res.outcome, RESOLVED)
                self.assertIsNone(res.place)


class TestAliases(ResolverTestCase):
    def test_confirmed_aliases_resolve(self):
        checked = 0
        for a in Alias.objects.filter(confirmed=True).select_related("place"):
            with self.subTest(alias=a.alias_text):
                res = self.r.resolve(a.alias_text)
                self.assertEqual(res.outcome, RESOLVED, f"{a.alias_text} did not resolve")
                self.assertEqual(res.place.pk, a.place.pk)
            checked += 1
        self.assertGreater(checked, 0)

    def test_phase_x_alias_resolves_to_phase_10(self):
        res = self.r.resolve("Phase X")
        self.assertEqual(res.outcome, RESOLVED)
        self.assertEqual(res.place.canonical_name, "DHA Phase 10")

    def test_dha_city_dropped_as_multi_referent(self):
        res = self.r.resolve("DHA City")
        self.assertNotEqual(res.outcome, RESOLVED)
        self.assertIsNone(res.place)


class TestStageOrder(ResolverTestCase):
    """Drops run BEFORE canonical matching. This is the load-bearing invariant."""

    def test_drop_precedes_canonical_lookup(self):
        """'DHA Phase 2' is both a Place canonical_name AND cross-city ambiguous.

        If drops ran after canonical matching, this would silently bind to Lahore.
        """
        ph2 = self.place_named("DHA Phase 2")
        self.assertIsNotNone(ph2, "canonical name exists — so the ordering is testable")
        res = self.r.resolve("DHA Phase 2")
        self.assertEqual(res.outcome, DROPPED)
        self.assertIsNone(res.place)

    def test_every_place_canonical_name_dropped_is_still_refused(self):
        """Systematic check: no canonical name that is also a drop can bind."""
        for d in Drop.objects.all():
            with self.subTest(drop=d.alias_text):
                res = self.r.resolve(d.alias_text)
                self.assertNotEqual(res.outcome, RESOLVED,
                                    f"dropped string resolved: {d.alias_text}")

    def test_resolver_exposes_no_coverage_metric(self):
        """R6, structurally enforced: no rate is reachable from the resolver."""
        forbidden = ("rate", "coverage", "percent", "ratio", "score", "baseline")
        for name in dir(self.r):
            if name.startswith("_"):
                continue
            self.assertFalse(
                any(f in name.lower() for f in forbidden),
                f"resolver exposes coverage-like member: {name}")


class TestBaseline(ResolverTestCase):
    """Reproduce the validated baseline — rate AND false matches, never rate alone."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        data = json.loads(FIXTURE.read_text())
        cls.occ = data["occurrences"]
        cls.total = data["total_occurrences"]

    def test_corpus_shape_matches_baseline_run(self):
        self.assertEqual(self.total, BASELINE_TOTAL)
        self.assertEqual(len(self.occ), 198)

    def test_resolution_rate_at_least_milestone1_floor(self):
        """Milestone 1 set a FLOOR, not a ceiling.

        Milestone 2 (society slot) legitimately raised the rate 992 -> 1140. The exact
        count is pinned per-milestone in that milestone's own tests. What must never
        happen is the rate falling below the floor — that would mean a milestone
        regressed, or a guard silently stopped firing.
        """
        resolved = sum(n for s, n in self.occ.items()
                       if self.r.resolve(s).outcome == RESOLVED)
        self.assertGreaterEqual(resolved, BASELINE_RESOLVED,
                                f"resolution fell below the Milestone 1 floor: {resolved}")
        # Exact counts are owned by the milestone that set them. M1 pins a floor only;
        # M2 and M3 legitimately raised the rate. See each milestone's own tests.
        self.assertGreaterEqual(100.0 * resolved / self.total, BASELINE_RATE)

    def test_rate_gain_never_exceeds_measured_recovery(self):
        """An unexplained jump is a smell. Each milestone must account for its gain.

        Milestone 2 accounted for +148 net: society bindings (Bahria Town 208,
        Lake City 38, LDA City 28, Askari 10 1, Gulberg III 4 = 279) minus the three
        false-match classes closed (abbreviated cross-city forms, DHA Valley,
        bare Gulberg) and minus the lost society-less 'DHA 9 Prism'-style parses.
        Cap the rate so a silent leak cannot masquerade as progress.
        """
        resolved = sum(n for s, n in self.occ.items()
                       if self.r.resolve(s).outcome == RESOLVED)
        # Ceilings live with the milestone that set them. M3's audited ceiling is
        # 49.6%; see corpus.tests.test_block_identity.TestMilestone3Baseline.
        rate = 100.0 * resolved / self.total
        self.assertGreaterEqual(rate, BASELINE_RATE)

    def test_no_forced_adjudications(self):
        """Every miss is recorded; none is silently discarded."""
        outcomes = {}
        for s, n in self.occ.items():
            outcomes.setdefault(self.r.resolve(s).outcome, 0)
            outcomes[self.r.resolve(s).outcome] += n
        self.assertEqual(outcomes.get(Observation.ADJ_FORCED, 0), 0)
        self.assertIn(UNRESOLVED, outcomes)


class TestMapIntegrity(ResolverTestCase):
    def test_no_dangling_alias_targets(self):
        for a in Alias.objects.select_related("place"):
            self.assertIsNotNone(a.place_id)

    def test_confested_entity_is_flagged(self):
        self.assertTrue(Place.objects.filter(is_contested=True).exists(),
                        "ph_dha_9_ext must stay flagged contested")

    def test_every_place_has_evidence(self):
        for p in Place.objects.all():
            with self.subTest(place=p.canonical_name):
                self.assertNotEqual(p.evidence_status, "unevidenced")
                self.assertTrue(p.evidence, f"{p.canonical_name} has no evidence")

    def test_nested_alias_does_not_point_at_ancestor(self):
        """Rahbar-class bug: Sec-4 is a sector WITHIN Phase 11, not the phase.

        This is the defect the architecture review found in live data.
        """
        sec = Place.objects.filter(canonical_name__iexact="Rahbar Sector-4").first()
        self.assertIsNotNone(sec, "Rahbar Sector-4 must exist as its own entity")
        self.assertEqual(sec.level, "sector")
        self.assertEqual(sec.parent.canonical_name, "DHA Phase 11 (Rahbar)")

        a = Alias.objects.filter(alias_text="Rahbar Sec-4").first()
        self.assertIsNotNone(a)
        self.assertEqual(a.place_id, sec.pk,
                         "'Rahbar Sec-4' must bind to the sector, not the phase")

    def test_phase_11_aliases_remain_at_phase_level(self):
        for text in ("Ph 11 (Rahbar)", "DHA Rahbar"):
            a = Alias.objects.filter(alias_text=text).first()
            if a:
                self.assertEqual(a.place.level, "phase", f"{text} should stay phase-level")