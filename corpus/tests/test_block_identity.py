"""Milestone 3 acceptance tests — block identity layer.

BlockIdentity is deliberately NOT a Place. R3 proposed a `sub_sector` tree level and
was REJECTED on evidence: mohsinestate labels the same objects both "Block" and
"Sector", so a hierarchy would encode a source's inconsistency as geographic truth.

These tests hold that line: the layer must resolve phase-qualified references, refuse
bare letters, never assert a hierarchy, and never let a single-source identity be
promoted without corroboration.
"""

import json

from django.core.management import call_command

from corpus import DROPPED, RESOLVED, UNRESOLVED
from corpus.models import BlockIdentity, Place
from corpus.tests.test_acceptance import FIXTURE, ResolverTestCase

MILESTONE3_RESOLVED = 1351
MILESTONE3_TOTAL = 2725
MILESTONE3_RATE = 49.6


class TestBlockIdentityResolution(ResolverTestCase):
    def test_phase_qualified_blocks_resolve(self):
        cases = {
            "DHA Phase 9 Prism Block Q": "DHA Phase 9 Prism",
            "DHA Phase 7 Block Y": "DHA Phase 7",
            "DHA Phase 6 Block D": "DHA Phase 6",
            "DHA Phase 8 Block S": "DHA Phase 8",
        }
        for text, phase_name in cases.items():
            with self.subTest(text=text):
                res = self.r.resolve(text)
                self.assertEqual(res.outcome, RESOLVED, f"{text} did not resolve")
                self.assertEqual(res.stage, "3b-block-identity")
                self.assertEqual(res.place.canonical_name, phase_name)

    def test_letter_is_reported_in_parsed_payload(self):
        res = self.r.resolve("DHA Phase 9 Prism Block Q")
        self.assertEqual(res.parsed["letter"], "Q")
        self.assertEqual(res.parsed["phase"], 9)
        self.assertEqual(res.parsed["tail"], "Prism")

    def test_non_alpha_identifiers_supported(self):
        """Z2 and KK are identifiers the sources actually publish."""
        for text in ("DHA Phase 7 Block Z2", "DHA Phase 4 Block KK"):
            with self.subTest(text=text):
                self.assertEqual(self.r.resolve(text).outcome, RESOLVED)

    def test_unknown_letter_under_known_phase_stays_unresolved(self):
        res = self.r.resolve("DHA Phase 7 Block QQ")
        self.assertNotEqual(res.outcome, RESOLVED)


class TestBareLettersStillRefused(ResolverTestCase):
    """The phase qualifier is the only thing that makes a letter meaningful.

    23 of 27 identifiers repeat across phases within one source. A bare letter is
    therefore meaningless and must never bind.
    """

    def test_bare_block_and_sector_letters_unresolved(self):
        for s in ("Block Q", "Block Y", "Block D", "Block S", "Sector U", "Sector A", "Sector F"):
            with self.subTest(s=s):
                res = self.r.resolve(s)
                self.assertNotEqual(res.outcome, RESOLVED)
                self.assertIsNone(res.place)

    def test_qualified_binds_but_bare_does_not(self):
        self.assertEqual(self.r.resolve("DHA Phase 7 Block Y").outcome, RESOLVED)
        self.assertNotEqual(self.r.resolve("Block Y").outcome, RESOLVED)


class TestNoHierarchyAsserted(ResolverTestCase):
    """BlockIdentity must not become a Place. That was R3's failure."""

    def test_block_identity_is_not_a_place(self):
        self.assertFalse(hasattr(Place, "block_identities_typed"))
        # no Place rows were created for the letters
        for letter in ("Q", "Y", "D", "S", "KK", "Z2"):
            self.assertFalse(
                Place.objects.filter(canonical_name__iexact=letter).exists(),
                f"'{letter}' was created as a Place — that is R3 resurrected")

    def test_block_identity_count(self):
        self.assertEqual(BlockIdentity.objects.count(), 57)

    def test_uses_reference_not_parent(self):
        bi = BlockIdentity.objects.get(phase__canonical_name="DHA Phase 9 Prism", letter="Q")
        self.assertEqual(bi.phase.canonical_name, "DHA Phase 9 Prism")
        # the phase is a reference; nothing asserts geographic containment
        self.assertEqual(bi.phase.level, "phase")

    def test_label_conflicts_are_recorded_not_interpreted(self):
        conflicts = [b for b in BlockIdentity.objects.all() if b.label_conflict]
        self.assertEqual(len(conflicts), 2, "expected the 2 known Block/Sector conflicts")
        for b in conflicts:
            self.assertIn(";", b.labels_observed)
            self.assertEqual(b.labels_observed.split(";")[0], "Block")
            self.assertEqual(b.labels_observed.split(";")[1], "Sector")


class TestPromotionRule(ResolverTestCase):
    """verified=True requires two independent sources. Structural, not procedural."""

    def test_single_source_identities_are_flagged(self):
        single = BlockIdentity.objects.filter(single_source=True)
        self.assertEqual(single.count(), 56)
        for b in single:
            self.assertFalse(b.verified, f"{b} is single-source but marked verified")

    def test_verified_requires_two_sources(self):
        for b in BlockIdentity.objects.filter(verified=True):
            self.assertGreaterEqual(b.source_count, 2)

    def test_clean_refuses_promotion_without_corroboration(self):
        bi = BlockIdentity.objects.get(phase__canonical_name="DHA Phase 7", letter="Y")
        self.assertEqual(bi.source_count, 1)
        bi.verified = True
        with self.assertRaises(ValueError) as ctx:
            bi.full_clean()
        self.assertIn("promotion rule", str(ctx.exception))

    def test_promote_command_reports_blocked_identities(self):
        out = call_command("promote_block_identities", "--report", verbosity=0)
        self.assertTrue(BlockIdentity.objects.filter(single_source=True).exists())
        # dry run must not promote anything
        self.assertEqual(BlockIdentity.objects.filter(verified=True).count(), 1)

    def test_promote_apply_promotes_nothing_without_sources(self):
        call_command("promote_block_identities", "--apply", verbosity=0)
        self.assertEqual(BlockIdentity.objects.filter(verified=True).count(), 1,
                         "apply must not promote single-source identities")

    def test_the_one_corroborated_identity(self):
        b = BlockIdentity.objects.get(phase__canonical_name="DHA Phase 5", letter="M")
        self.assertTrue(b.verified)
        self.assertEqual(b.source_count, 2)
        self.assertFalse(b.single_source)
        self.assertEqual({s.slug for s in b.sources.all()},
                         {"lahorerealestate", "mohsinestate"})


class TestNothingRegressed(ResolverTestCase):
    def test_cross_city_still_blocked(self):
        for s in ("DHA Phase 2", "DHA Ph-1", "DHA 1", "DHA Valley Phase 7"):
            self.assertIsNone(self.r.resolve(s).place, f"{s} bound")

    def test_sector_society_slot_still_resolves(self):
        self.assertEqual(self.r.resolve("Bahria Town").outcome, RESOLVED)
        self.assertEqual(self.r.resolve("LDA City").outcome, RESOLVED)

    def test_bare_gulberg_still_unresolved(self):
        self.assertEqual(self.r.resolve("Gulberg").outcome, UNRESOLVED)

    def test_cca_still_measurement(self):
        for s in ("CCA-3", "CCA3", "DHA Phase 8 CCA3"):
            self.assertNotEqual(self.r.resolve(s).outcome, RESOLVED)

    def test_resolver_exposes_no_coverage_metric(self):
        forbidden = ("rate", "coverage", "percent", "ratio", "score", "baseline")
        for name in dir(self.r):
            if not name.startswith("_"):
                self.assertFalse(any(f in name.lower() for f in forbidden),
                                 f"coverage-like member: {name}")

    def test_no_forced_adjudications(self):
        from corpus.models import Observation
        self.assertEqual(Observation.objects.filter(
            adjudication=Observation.ADJ_FORCED).count(), 0)


class TestMilestone3Baseline(ResolverTestCase):
    def test_rate_reproduces(self):
        data = json.loads(FIXTURE.read_text())
        self.assertEqual(data["total_occurrences"], MILESTONE3_TOTAL)
        resolved = sum(n for s, n in data["occurrences"].items()
                       if self.r.resolve(s).outcome == RESOLVED)
        self.assertEqual(resolved, MILESTONE3_RESOLVED,
                         f"resolved {resolved} != {MILESTONE3_RESOLVED}")

    def test_rate_at_or_below_audited_ceiling(self):
        """49.6% was the measured ceiling. Above it means a leak."""
        data = json.loads(FIXTURE.read_text())
        resolved = sum(n for s, n in data["occurrences"].items()
                       if self.r.resolve(s).outcome == RESOLVED)
        rate = 100.0 * resolved / data["total_occurrences"]
        self.assertLessEqual(rate, MILESTONE3_RATE + 0.5,
                             f"rate {rate:.1f}% exceeds the audited ceiling — investigate")

    def test_every_block_identity_resolves_back_to_itself(self):
        """Round-trip: each identity's own reference must resolve."""
        for b in BlockIdentity.objects.select_related("phase"):
            letter = b.letter
            label = b.labels_observed.split(";")[0]
            ref = f"{b.phase.canonical_name} {label} {letter}"
            with self.subTest(ref=ref):
                res = self.r.resolve(ref)
                self.assertEqual(res.outcome, RESOLVED, f"{ref} did not round-trip")
                self.assertEqual(res.parsed.get("letter"), letter)
                self.assertEqual(res.parsed.get("single_source"), b.single_source)