"""Milestone 4 acceptance tests — extraction boundary.

THE FIRST TWO TESTS ARE THE NON-NEGOTIABLES from the contract:
  1. invented value + genuine quote  -> V2 rejects
  2. genuine-looking candidate + fabricated quote -> V1 rejects

If these two do not fail correctly, nothing else about the boundary is trustworthy.
Validators are never weakened to raise acceptance volume.
"""

from django.core.management import call_command

from corpus.models import Fact, Observation, Source, Document, BlockIdentity
from corpus.resolver import Resolver
from corpus.tests.test_acceptance import ResolverTestCase
from corpus.validators import (
    ACCEPTED, CORROBORATION_WINDOW, TIER2_FACT_TYPES, Candidate, V1_QUOTE_FIDELITY,
    V2_VALUE_PRESENCE, V3_DATE_PRESENCE, V4_ENTITY_BINDING, V5_CROSS_CITY,
    V6_CATEGORY_ROUTING, V7_NO_SELF_PROMOTION, V8_TIER, V9_PLACE_CORROBORATION,
    V10_FACT_TYPE_CUE,
    _norm_aggressive, _place_markers, persist_accepted, persist_rejection, validate,
)

# A real sentence lifted from dharealestate.pk's daily rate posts.
GENUINE_QUOTE = ("DHA Phase 10 - 10 Marla Affidavit: 56.25 Lac | "
                 "10 Marla Allocation: 54.00 Lac | as of 25 August 2026")


class BoundaryTestCase(ResolverTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.src, _ = Source.objects.get_or_create(
            slug="testsrc", defaults={"name": "Test", "base_url": "https://example.invalid", "verified": True})
        cls.doc, _ = Document.objects.get_or_create(
            source=cls.src, url="https://example.invalid/rates",
            defaults={"raw_text": GENUINE_QUOTE + " Phase 9 Town 5 Marla Allocation: 56 Lac"})

    def cand(self, **kw):
        # V11: a rate must carry the size and file type its quote states.
        # GENUINE_QUOTE says "10 Marla Affidavit: 56.25 Lac | 10 Marla Allocation: 54.00 Lac"
        base = dict(fact_type="rate", value="56.25 Lac", place_ref="DHA Phase 10",
                    raw_quote=GENUINE_QUOTE, document=self.doc, as_of="2026-08-25",
                    size_marla="10", file_type="affidavit")
        base.update(kw)
        return Candidate(**base)


# ---------------------------------------------------------------------------
# THE TWO NON-NEGOTIABLE NEGATIVE TESTS
# ---------------------------------------------------------------------------

class TestNonNegotiableNegatives(BoundaryTestCase):

    def test_invented_value_with_genuine_quote_rejected_by_v2(self):
        """The quote is real. The number 99.5 is not in it. V2 must reject."""
        cand = self.cand(value="99.5 Lac")
        res = validate(cand, self.r)
        self.assertFalse(res.accepted, "an invented value was accepted")
        self.assertEqual(res.validator, V2_VALUE_PRESENCE)
        self.assertIn("99.5", res.reason)

    def test_fabricated_quote_rejected_by_v1(self):
        """The candidate looks entirely reasonable. The quote does not exist. V1 must reject."""
        cand = self.cand(
            value="43.75 Lac",
            raw_quote="DHA Phase 10 10 Marla Allocation is 43.75 Lac per official DHA notification")
        res = validate(cand, self.r)
        self.assertFalse(res.accepted, "a fabricated quote was accepted")
        self.assertEqual(res.validator, V1_QUOTE_FIDELITY)

    def test_v2_rejects_a_value_whose_number_is_only_derived(self):
        """Arithmetic on a real number is still not in the quote."""
        cand = self.cand(value="112.5 Lac")   # 56.25 * 2, a real double
        res = validate(cand, self.r)
        self.assertEqual(res.validator, V2_VALUE_PRESENCE)

    def test_v1_rejects_a_paraphrase_even_when_facts_are_right(self):
        cand = self.cand(raw_quote="The 10 marla affidavit file in DHA Phase 10 costs 56.25 lac.")
        res = validate(cand, self.r)
        self.assertEqual(res.validator, V1_QUOTE_FIDELITY)

    def test_a_genuine_candidate_passes(self):
        """The control: the same shape with a real quote and real number must pass.
        Without this, V1/V2 could be rejecting everything and the tests would still be green."""
        res = validate(self.cand(), self.r)
        self.assertTrue(res.accepted, f"genuine candidate rejected: {res.validator} {res.reason}")


# ---------------------------------------------------------------------------
# V3 date
# ---------------------------------------------------------------------------

class TestDatePresence(BoundaryTestCase):
    def test_invented_date_rejected(self):
        res = validate(self.cand(as_of="2019-01-01"), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V3_DATE_PRESENCE)

    def test_date_in_document_accepted(self):
        res = validate(self.cand(as_of="2026-08-25"), self.r)
        self.assertTrue(res.accepted)

    def test_missing_date_is_allowed_not_fabricated(self):
        """as_of is nullable. Absence is honest; invention is not."""
        res = validate(self.cand(as_of=None), self.r)
        self.assertTrue(res.accepted)


# ---------------------------------------------------------------------------
# V4 entity binding
# ---------------------------------------------------------------------------

class TestEntityBinding(BoundaryTestCase):
    def test_unresolvable_place_ref_rejected(self):
        res = validate(self.cand(place_ref="Sector F"), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V4_ENTITY_BINDING)

    def test_sector_letter_place_ref_never_binds(self):
        for s in ("Sector F", "Block Q", "Sector A"):
            self.assertIsNone(validate(self.cand(place_ref=s), self.r).place)

    def test_cross_city_place_ref_rejected(self):
        """V5 fires before V4 for cross-city text — a more specific diagnosis.

        The resolver would also refuse 'DHA Phase 2', but V5 names WHY, which is the
        useful thing to persist on the rejection.
        """
        res = validate(self.cand(place_ref="DHA Phase 2"), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V5_CROSS_CITY)
        self.assertIn("cross-city", res.reason)

    def test_model_supplied_place_id_rejected(self):
        """The LLM must never name a place. A supplied id is refused outright."""
        res = validate(self.cand(claims_place_id=1), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V7_NO_SELF_PROMOTION)

    def test_block_identity_place_ref_accepted(self):
        res = validate(self.cand(place_ref="DHA Phase 10 Block M"), self.r)
        self.assertFalse(res.accepted, "phase 10 block M is not in the identity map")

    def test_block_identity_that_exists_accepted(self):
        self.doc.raw_text = ("DHA Phase 5 Block M files 10 Marla Allocation: 59.00 Lac "
                             "10 Marla Affidavit: 61.00 Lac")
        self.doc.save()
        res = validate(self.cand(value="61.00 Lac", place_ref="DHA Phase 5 Block M",
                                 as_of=None, size_marla="10", file_type="affidavit",
                                 raw_quote="10 Marla Allocation: 59.00 Lac 10 Marla Affidavit: 61.00 Lac"),
                       self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")


# ---------------------------------------------------------------------------
# V5 cross-city
# ---------------------------------------------------------------------------

class TestCrossCity(BoundaryTestCase):
    def test_islamabad_society_in_fact_rejected(self):
        cand = self.cand(
            value="56.25 Lac", as_of=None,
            raw_quote="DHA Valley Phase 7 5 Marla Allocation: 56.25 Lac")
        self.doc.raw_text = cand.raw_quote
        self.doc.save()
        res = validate(cand, self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V5_CROSS_CITY)

    def test_bare_dha_phase_1_4_in_fact_rejected(self):
        cand = self.cand(
            value="30 Lac", as_of=None,
            raw_quote="DHA Phase 2 10 Marla Allocation: 30 Lac")
        self.doc.raw_text = cand.raw_quote
        self.doc.save()
        res = validate(cand, self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V5_CROSS_CITY)

    def test_lahore_qualified_fact_accepted(self):
        # place_ref MUST match the quote's phase. This test originally inherited
        # place_ref="DHA Phase 10" from the default candidate while quoting a Phase 2
        # sentence — i.e. it asserted the exact wrong-entity behaviour V9 forbids.
        # V9 caught the mistake in our own suite.
        cand = self.cand(
            value="30 Lac", as_of=None, place_ref="DHA Lahore Phase 2",
            size_marla="10", file_type="allocation",
            raw_quote="DHA Lahore Phase 2 10 Marla Allocation: 30 Lac")
        self.doc.raw_text = cand.raw_quote
        self.doc.save()
        res = validate(cand, self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")


# ---------------------------------------------------------------------------
# V6 category routing
# ---------------------------------------------------------------------------

class TestCategoryRouting(BoundaryTestCase):
    def test_cca_as_value_rejected(self):
        cand = self.cand(value="CCA-3 4 Marla 145 Lac", as_of=None,
                         raw_quote="CCA-3 4 Marla: 145 Lac")
        self.doc.raw_text = cand.raw_quote
        self.doc.save()
        res = validate(cand, self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V6_CATEGORY_ROUTING)

    def test_cca_as_place_ref_rejected(self):
        cand = self.cand(place_ref="DHA Phase 8 CCA3")
        res = validate(cand, self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V6_CATEGORY_ROUTING)


# ---------------------------------------------------------------------------
# V7 no self-promotion
# ---------------------------------------------------------------------------

class TestNoSelfPromotion(BoundaryTestCase):
    def test_candidate_claiming_verified_block_rejected(self):
        bi = BlockIdentity.objects.first()
        res = validate(self.cand(claims_verified_block=f"{bi.phase_id}:{bi.letter}"), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V7_NO_SELF_PROMOTION)
        bi.refresh_from_db()
        self.assertFalse(bi.verified, "a rejected candidate still mutated the identity")

    def test_extraction_cannot_reach_verified(self):
        """No code path from validation writes BlockIdentity.verified."""
        bi = BlockIdentity.objects.filter(single_source=True).first()
        res = validate(self.cand(), self.r)
        self.assertTrue(res.accepted)
        bi.refresh_from_db()
        self.assertFalse(bi.verified)


# ---------------------------------------------------------------------------
# V8 tier refusal
# ---------------------------------------------------------------------------

class TestTierRefusal(BoundaryTestCase):
    def test_tier2_fact_types_all_refused(self):
        for ft in sorted(TIER2_FACT_TYPES):
            with self.subTest(fact_type=ft):
                res = validate(self.cand(fact_type=ft), self.r)
                self.assertFalse(res.accepted)
                self.assertEqual(res.validator, V8_TIER)

    def test_unknown_fact_type_refused_not_silently_dropped(self):
        res = validate(self.cand(fact_type="sentiment_score"), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V8_TIER)
        self.assertIn("sentiment_score", res.reason)


# ---------------------------------------------------------------------------
# Rejection handling
# ---------------------------------------------------------------------------

class TestRejectionHandling(BoundaryTestCase):
    def test_rejection_is_persisted_with_validator_id(self):
        cand = self.cand(value="99.5 Lac")
        res = validate(cand, self.r)
        obs = persist_rejection(cand, res)
        self.assertEqual(obs.adjudication, Observation.ADJ_DROPPED)
        self.assertEqual(obs.stage, V2_VALUE_PRESENCE)
        self.assertIn(V2_VALUE_PRESENCE, obs.reason)

    def test_rejected_candidate_creates_no_fact(self):
        before = Fact.objects.count()
        cand = self.cand(value="99.5 Lac")
        res = validate(cand, self.r)
        if res.accepted:
            persist_accepted(cand, res)
        self.assertEqual(Fact.objects.count(), before)

    def test_accepted_candidate_persists_with_provenance(self):
        cand = self.cand()
        res = validate(cand, self.r)
        self.assertTrue(res.accepted)
        f = persist_accepted(cand, res)
        self.assertEqual(f.place.canonical_name, "DHA Phase 10")
        self.assertEqual(f.fact_type, "rate")
        self.assertTrue(f.raw_quote)
        self.assertEqual(f.source_id, self.doc.source_id)
        self.assertEqual(f.as_of.isoformat(), "2026-08-25")

    def test_fact_requires_raw_quote(self):
        cand = self.cand()
        res = validate(cand, self.r)
        f = persist_accepted(cand, res)
        self.assertFalse(Fact.objects.filter(pk=f.pk, raw_quote="").exists())

    def test_empty_document_rejects_everything(self):
        empty, _ = Document.objects.get_or_create(
            source=self.src, url="https://example.invalid/empty", defaults={"raw_text": ""})
        res = validate(self.cand(document=empty), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V1_QUOTE_FIDELITY)

    def test_empty_quote_rejects(self):
        res = validate(self.cand(raw_quote=""), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V1_QUOTE_FIDELITY)


class TestValidatorOrder(BoundaryTestCase):
    def test_v1_runs_before_v2(self):
        """A fabricated quote must be reported as V1, not evaluated against V2."""
        cand = self.cand(value="99.5 Lac",
                         raw_quote="DHA Phase 10 official allocation is 43.75 Lac per DHA")
        res = validate(cand, self.r)
        self.assertEqual(res.validator, V1_QUOTE_FIDELITY)

    def test_tier_refused_before_entity_binding(self):
        """An out-of-contract fact_type is refused on type, before we look at places."""
        res = validate(self.cand(fact_type="rate_band", place_ref="Sector F"), self.r)
        self.assertEqual(res.validator, V8_TIER)

# ---------------------------------------------------------------------------
# V9 place corroboration — added after the first real extraction run
# ---------------------------------------------------------------------------

class TestPlaceCorroboration(BoundaryTestCase):
    """The quote must SUPPORT the place it is attached to.

    Found in the first real-page run: a candidate naming 'Rahbar Sector-4' with a
    quote reading 'DHA Phase 9 Town' passed V1-V8 and would have entered the knowledge
    base fully sourced and dated. Wrong entity, correct provenance — the project's
    core failure mode, arriving through the proposer's place_ref.
    """

    def setUp(self):
        super().setUp()
        self.doc.raw_text = (
            "DHA Phase 9 Town Files 4 Marla Affidavit: 230 Lacs "
            "4 Marla Allocation: 215 Lacs "
            "DHA Rahbar Sector-4 Files 4 Marla Affidavit: 175 Lacs"
        )
        self.doc.save()

    def test_wrong_phase_quote_rejected(self):
        cand = self.cand(
            value="215 Lacs", place_ref="Rahbar Sector-4",
            size_marla="4", file_type="allocation",
            raw_quote="DHA Phase 9 Town Files 4 Marla Affidavit: 230 Lacs 4 Marla Allocation: 215 Lacs",
            as_of=None)
        res = validate(cand, self.r)
        self.assertFalse(res.accepted, "a fact bound to a place its quote does not support")
        self.assertEqual(res.validator, V9_PLACE_CORROBORATION)

    def test_correct_place_accepted(self):
        cand = self.cand(
            value="215 Lacs", place_ref="DHA Phase 9 Town",
            size_marla="4", file_type="allocation",
            raw_quote="DHA Phase 9 Town Files 4 Marla Affidavit: 230 Lacs 4 Marla Allocation: 215 Lacs",
            as_of=None)
        res = validate(cand, self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")

    def test_v9_runs_after_v4(self):
        """An unresolvable place_ref is a V4 failure, not a V9 one."""
        cand = self.cand(
            value="215 Lacs", place_ref="Sector B", as_of=None,
            size_marla="4", file_type="allocation",
            raw_quote="DHA Phase 9 Town Files 4 Marla Affidavit: 230 Lacs 4 Marla Allocation: 215 Lacs")
        res = validate(cand, self.r)
        self.assertEqual(res.validator, V4_ENTITY_BINDING)

    def test_v9_accepts_a_section_heading_above_the_quote(self):
        """Real pages label a table then list rows. The heading counts."""
        self.doc.raw_text = (
            "DHA Phase 10 Files 4 Marla Affidavit: 120 Lacs "
            "10 Marla Allocation: 54.00 Lac 10 Marla Affidavit: 56.25 Lac")
        self.doc.save()
        cand = self.cand(
            value="56.25 Lac", place_ref="DHA Phase 10",
            size_marla="10", file_type="affidavit",
            raw_quote="10 Marla Allocation: 54.00 Lac 10 Marla Affidavit: 56.25 Lac",
            as_of=None)
        res = validate(cand, self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")

    def test_every_accepted_fact_in_the_real_run_is_corroborated(self):
        """Regression guard on the actual extraction output."""
        for f in Fact.objects.select_related("place", "document"):
            marks = _place_markers(f.place)
            hay = _norm_aggressive(f.document.raw_text)
            idx = hay.find(_norm_aggressive(f.raw_quote))
            with self.subTest(place=f.place.canonical_name, quote=f.raw_quote[:40]):
                self.assertGreaterEqual(idx, 0, "quote vanished from its document")
                window = hay[max(0, idx - CORROBORATION_WINDOW): idx + len(f.raw_quote)]
                self.assertTrue(any(m in window for m in marks),
                                f"fact at {f.place.canonical_name} is not corroborated by its quote")


# ---------------------------------------------------------------------------
# V10 fact-type cue — added after the real run exposed a semantic hole
# ---------------------------------------------------------------------------

class TestFactTypeCue(BoundaryTestCase):
    """The quote must speak the proposed fact_type's language.

    The specific failure this exists for: a quote about BALLOTING was filed as
    possession_status. Both are Tier 1. The value text was honest. The label was
    simply wrong, and V1-V9 all passed it.
    """

    def setUp(self):
        super().setUp()
        # V9 corroboration looks BACKWARD only: on real pages a heading precedes the
        # rows it labels. The fixture must mirror that or V9 (correctly) refuses.
        self.doc.raw_text = ("DHA Phase 10 Balloting Update. "
                             "Balloting was scheduled for 5 February 2026 through five "
                             "designated banks: MCB, Bank Alfalah, Askari Bank, HBL and Meezan Bank.")
        self.doc.save()

    def test_the_discovered_failure_is_now_rejected(self):
        cand = self.cand(
            fact_type="possession_status",
            value="balloting was scheduled for 5 February 2026",
            place_ref="DHA Phase 10", as_of=None,
            raw_quote="Balloting was scheduled for 5 February 2026 through five designated banks: "
                      "MCB, Bank Alfalah, Askari Bank, HBL and Meezan Bank.")
        res = validate(cand, self.r)
        self.assertFalse(res.accepted, "the balloting->possession mislabel passed")
        self.assertEqual(res.validator, V10_FACT_TYPE_CUE)

    def test_rejection_names_the_cue_the_quote_actually_speaks(self):
        cand = self.cand(
            fact_type="possession_status",
            value="balloting was scheduled", place_ref="DHA Phase 10", as_of=None,
            raw_quote="Balloting was scheduled for 5 February 2026 through five designated banks: "
                      "MCB, Bank Alfalah, Askari Bank, HBL and Meezan Bank.")
        res = validate(cand, self.r)
        self.assertIn("balloting_status", res.reason,
                      "the rejection should say what the quote actually speaks")

    def test_same_quote_with_the_right_label_is_accepted(self):
        cand = self.cand(
            fact_type="balloting_status",
            value="balloting was scheduled for 5 February 2026",
            place_ref="DHA Phase 10", as_of=None,
            size_marla=None, file_type=None,
            raw_quote="Balloting was scheduled for 5 February 2026 through five designated banks: "
                      "MCB, Bank Alfalah, Askari Bank, HBL and Meezan Bank.")
        res = validate(cand, self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")

    def test_genuine_possession_quote_accepted(self):
        self.doc.raw_text = ("DHA Phase 10 Possession Update. Possession has been granted in "
                             "multiple blocks, including A1 Block, B1 Block and E1 Block in LDA City.")
        self.doc.save()
        cand = self.cand(
            fact_type="possession_status", value="possession granted in multiple blocks",
            place_ref="DHA Phase 10", as_of=None, size_marla=None, file_type=None,
            raw_quote="Possession has been granted in multiple blocks, including A1 Block, "
                      "B1 Block and E1 Block in LDA City.")
        res = validate(cand, self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")

    def test_rate_needs_a_money_cue(self):
        self.doc.raw_text = ("DHA Phase 10 Balloting scheduled for 2026.")
        self.doc.save()
        # Value passes V2 (its number is in the quote) but the quote has no money cue,
        # so V10 is the validator that must refuse it.
        cand = self.cand(fact_type="rate", value="2026", place_ref="DHA Phase 10",
                         as_of=None, size_marla=None, file_type=None,
                         raw_quote="DHA Phase 10 Balloting scheduled for 2026.")
        res = validate(cand, self.r)
        self.assertEqual(res.validator, V10_FACT_TYPE_CUE)

    def test_unvalidated_fact_type_is_rejected_not_assumed(self):
        """A fact_type with no cue rows must NOT get an implicit pass."""
        cand = self.cand(fact_type="transfer_process",
                         value="balloting was scheduled", place_ref="DHA Phase 10", as_of=None,
                         raw_quote="Balloting was scheduled for 5 February 2026 through five "
                                   "designated banks: MCB, Bank Alfalah, Askari Bank, HBL and Meezan Bank.")
        res = validate(cand, self.r)
        self.assertEqual(res.validator, V10_FACT_TYPE_CUE)

    def test_every_tier1_fact_type_has_a_cue_vocabulary(self):
        """No Tier 1 type may exist without cues — that would be an implicit pass."""
        from corpus.models import FactTypeCue
        from corpus.validators import TIER1_FACT_TYPES
        for ft in sorted(TIER1_FACT_TYPES):
            with self.subTest(fact_type=ft):
                self.assertTrue(FactTypeCue.objects.filter(fact_type=ft).exists(),
                                f"{ft} has no cue vocabulary")

    def test_cue_vocabulary_is_corpus_derived_and_inspectable(self):
        """Cues live in a CSV with counts, so the vocabulary is auditable."""
        from corpus.models import FactTypeCue
        cues = FactTypeCue.objects.all()
        self.assertGreater(cues.count(), 0)
        for c in cues:
            self.assertTrue(c.group, f"cue {c.cue} has no group")
            self.assertGreaterEqual(c.corpus_count, 0)
        proven = cues.filter(proven_in_corpus=True)
        self.assertGreater(proven.count(), 0)
        # unproven cues are kept visible, not silently dropped
        unproven = cues.filter(proven_in_corpus=False)
        for c in unproven:
            self.assertEqual(c.corpus_count, 0,
                             f"{c.cue} is marked unproven but has a nonzero count")

    def test_v10_runs_after_v1(self):
        """A fabricated quote is V1, not V10 — order must stay honest."""
        cand = self.cand(fact_type="possession_status", value="x",
                         raw_quote="DHA officially confirms possession handed over to all buyers")
        res = validate(cand, self.r)
        self.assertEqual(res.validator, V1_QUOTE_FIDELITY)

    def test_real_run_output_is_cue_valid(self):
        """Regression guard on the actual extraction output."""
        from corpus.models import FactTypeCue
        from corpus.validators import _norm_aggressive
        for f in Fact.objects.select_related("place"):
            q = _norm_aggressive(f.raw_quote)
            cues = FactTypeCue.objects.filter(fact_type=f.fact_type)
            self.assertTrue(any(c.cue.lower() in q for c in cues),
                            f"stored {f.fact_type} fact has no matching cue: {f.raw_quote[:60]}")


# ---------------------------------------------------------------------------
# V10 cue vocabulary + metadata-date ingestion (second real run)
# ---------------------------------------------------------------------------

class TestCueVocabularyHygiene(BoundaryTestCase):
    def test_unproven_cues_are_visible_not_hidden(self):
        """Cues absent from the corpus are kept, but marked, so the gap is auditable."""
        from corpus.models import FactTypeCue
        unproven = FactTypeCue.objects.filter(proven_in_corpus=False)
        self.assertGreater(unproven.count(), 0,
                           "expected some unproven cues; if this is 0 the vocabulary "
                           "was silently narrowed")
        for c in unproven:
            self.assertEqual(c.corpus_count, 0)

    def test_cue_csv_is_the_source_of_truth(self):
        import csv
        from pathlib import Path
        p = Path(__file__).resolve().parents[2] / "data" / "normalization" / "fact_type_cues.csv"
        self.assertTrue(p.exists(), "cue vocabulary must be an inspectable artifact")
        rows = list(csv.DictReader(p.open()))
        self.assertGreater(len(rows), 20)
        for r in rows:
            self.assertIn("corpus_count", r)
            self.assertIn("proven_in_corpus", r)


class TestMetadataDateIngestion(ResolverTestCase):
    """V3 refused 11 valid candidates because html_to_text drops <head>."""

    def test_iso_dates_recovered_from_head(self):
        from corpus.extract import extract_published_dates
        html = ('<html><head>'
                '<meta property="article:published_time" content="2026-08-22T18:27:00+00:00">'
                '<meta name="article:modified_time" content="2026-09-10T14:21:13+00:00">'
                '</head><body>text</body></html>')
        found = extract_published_dates(html)
        self.assertIn("2026-08-22T18:27:00+00:00", found)
        self.assertIn("2026-09-10T14:21:13+00:00", found)

    def test_content_before_property_name_is_also_found(self):
        from corpus.extract import extract_published_dates
        html = '<meta content="2026-05-01" property="article:published_time">'
        self.assertIn("2026-05-01", extract_published_dates(html))

    def test_time_tag_datetime_is_found(self):
        from corpus.extract import extract_published_dates
        self.assertIn("2026-03-04",
                      extract_published_dates('<time datetime="2026-03-04">March</time>'))

    def test_iso_date_parses_in_v3(self):
        from corpus.validators import _dates_in, _to_date
        self.assertIn("2026-08-22", {d.isoformat() for d in _dates_in("2026-08-22T18:27:00+00:00")})
        self.assertEqual(_to_date("2026-08-22").isoformat(), "2026-08-22")

    def test_body_absence_does_not_become_an_invented_date(self):
        """Metadata supplies the date. It must never be guessed when absent."""
        from corpus.models import Document, Source
        src, _ = Source.objects.get_or_create(
            slug="metatest", defaults={"name": "m", "base_url": "https://x.invalid", "verified": True})
        quote = "DHA Phase 10 10 Marla Allocation: 54.00 Lac 10 Marla Affidavit: 56.25 Lac"
        d_no, _ = Document.objects.get_or_create(
            source=src, url="https://x.invalid/nometa", defaults={"raw_text": quote})
        res = validate(self.cand_kind(d_no, quote, "2019-05-05"), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V3_DATE_PRESENCE)

        d_yes, _ = Document.objects.get_or_create(
            source=src, url="https://x.invalid/meta",
            defaults={"raw_text": quote,
                      "published_dates": "2026-08-25T10:00:00+00:00"})
        res = validate(self.cand_kind(d_yes, quote, "2026-08-25"), self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")

    def cand_kind(self, doc, quote, as_of):
        return Candidate(fact_type="rate", value="56.25 Lac", place_ref="DHA Phase 10",
                         raw_quote=quote, document=doc, as_of=as_of,
                         size_marla="10", file_type="affidavit")


class TestCCAInQuote(ResolverTestCase):
    """A CCA-3 commercial rate was accepted as a residential one.

    V6 checked `value` and `place_ref` but not the quote, and CCA appeared in
    neither of the candidate's own fields — only in the source sentence.
    """

    def setUp(self):
        super().setUp()
        from corpus.models import Document, Source
        src, _ = Source.objects.get_or_create(
            slug="ccatest", defaults={"name": "c", "base_url": "https://x.invalid", "verified": True})
        self.doc, _ = Document.objects.get_or_create(
            source=src, url="https://x.invalid/cca",
            defaults={"raw_text": "DHA Phase 6 CCA-3 Files 4 Marla Affidavit: 600 Lacs"})

    def test_commercial_cca_rate_cannot_pose_as_residential(self):
        c = Candidate(fact_type="rate", value="600 Lacs", place_ref="DHA Phase 6",
                      raw_quote="DHA Phase 6 CCA-3 Files 4 Marla Affidavit: 600 Lacs",
                      document=self.doc, as_of=None)
        res = validate(c, self.r)
        self.assertFalse(res.accepted, "a CCA-3 commercial rate was accepted as residential")
        self.assertEqual(res.validator, V6_CATEGORY_ROUTING)
        self.assertIn("quote", res.reason)
