"""Fact qualifier contract — (place, size, file_type, amount).

v1 stored a rate as a bare number, so `133.00 Lacs` and `218 Lacs` were
indistinguishable from a population of equally valid, differently-qualified rates.
A qualifier the source does not state must be explicitly UNKNOWN — never inferred.
"""

from decimal import Decimal

from django.core.management import call_command

from corpus.models import Document, Fact, QualifierStatus, Source
from corpus.resolver import Resolver
from corpus.tests.test_acceptance import ResolverTestCase
from corpus.validators import (
    Candidate, V11_QUALIFIER_CONTRACT, amount_in_quote, persist_accepted,
    qualifiers_in_quote, validate,
)

# A real line from lahorealestate.com's rate table.
RATE_QUOTE = "DHA Phase 9 Prism Files 4 Marla Affidavit: 218 Lacs 4 Marla Allocation: 196 Lacs"
AFF_ONLY_QUOTE = "DHA Phase 7 Files 4 Marla Affidavit: NA 4 Marla Allocation: 133.00 Lacs"


class QualifierTestCase(ResolverTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.src, _ = Source.objects.get_or_create(
            slug="qualtest", defaults={"name": "q", "base_url": "https://x.invalid", "verified": True})
        cls.doc, _ = Document.objects.get_or_create(
            source=cls.src, url="https://x.invalid/rates",
            defaults={"raw_text": f"{RATE_QUOTE} {AFF_ONLY_QUOTE} DHA Phase 10"})

    def cand(self, **kw):
        base = dict(fact_type="rate", value="218 Lacs", place_ref="DHA Phase 9 Prism",
                    raw_quote=RATE_QUOTE, document=self.doc, as_of=None,
                    size_marla="4", file_type="affidavit")
        base.update(kw)
        return Candidate(**base)


class TestQualifierExtraction(QualifierTestCase):
    def test_qualifiers_read_from_the_quote(self):
        sizes, ftypes = qualifiers_in_quote(RATE_QUOTE)
        self.assertEqual(sizes, {4.0})
        self.assertEqual(ftypes, {"affidavit", "allocation"})

    def test_amount_converts_stated_units_to_pkr(self):
        # a UNIT conversion, not a derived fact: V2 already proved the number is verbatim
        self.assertEqual(amount_in_quote("4 Marla Allocation: 218 Lacs"),
                         Decimal("21800000"))

    def test_no_amount_when_no_money_unit_stated(self):
        self.assertIsNone(amount_in_quote("Balloting expected in August 2026"))


class TestQualifierContract(QualifierTestCase):
    def test_fully_qualified_rate_accepted(self):
        res = validate(self.cand(), self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")
        f = persist_accepted(self.cand(), res)
        self.assertTrue(f.is_fully_qualified)
        self.assertEqual(f.qualifier_status, QualifierStatus.COMPLETE)
        self.assertEqual(f.size_marla, Decimal("4.00"))
        self.assertEqual(f.file_type, "affidavit")
        self.assertEqual(f.amount_pkr, Decimal("21800000"))

    def test_invented_size_rejected(self):
        """The quote says 4 marla. A candidate claiming 10 marla is refused."""
        res = validate(self.cand(size_marla="10"), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V11_QUALIFIER_CONTRACT)

    def test_invented_file_type_rejected(self):
        res = validate(self.cand(file_type="barcode"), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V11_QUALIFIER_CONTRACT)

    def test_omitting_a_quote_stated_size_rejected(self):
        """Leaving size unknown when the quote states it makes the rate ambiguous."""
        res = validate(self.cand(size_marla=None), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V11_QUALIFIER_CONTRACT)

    def test_omitting_file_type_rejected_even_when_two_are_stated(self):
        """Affidavit AND allocation in one quote: the hardest disambiguation case."""
        res = validate(self.cand(file_type=None), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V11_QUALIFIER_CONTRACT)
        self.assertIn("affidavit", res.reason)
        self.assertIn("allocation", res.reason)

    def test_unknown_is_allowed_when_the_quote_really_is_silent(self):
        """No size, no file type in the quote -> explicit UNKNOWN is honest."""
        self.doc.raw_text = "DHA Phase 10 Balloting is expected. 56.25 Lac"
        self.doc.save()
        q = "Balloting is expected. 56.25 Lac"
        res = validate(self.cand(raw_quote=q, value="56.25 Lac", size_marla=None,
                                 file_type=None, place_ref="DHA Phase 10"), self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")
        f = persist_accepted(self.cand(raw_quote=q, value="56.25 Lac", size_marla=None,
                                       file_type=None, place_ref="DHA Phase 10"), res)
        self.assertEqual(f.qualifier_status, QualifierStatus.UNKNOWN)
        self.assertIsNone(f.size_marla)
        self.assertIsNone(f.file_type)
        self.assertFalse(f.is_fully_qualified)
        self.assertIn("unknown", f.as_qualified_string())

    def test_partial_qualification_is_visible(self):
        """Quote gives a size but no file type -> PARTIAL, and says so in the string."""
        self.doc.raw_text = "DHA Phase 10 4 Marla: 54.00 Lac"
        self.doc.save()
        q = "DHA Phase 10 4 Marla: 54.00 Lac"
        c = self.cand(raw_quote=q, value="54.00 Lac", place_ref="DHA Phase 10",
                      size_marla="4", file_type=None)
        res = validate(c, self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")
        f = persist_accepted(c, res)
        self.assertEqual(f.qualifier_status, QualifierStatus.PARTIAL)
        self.assertIn("file type unknown", f.as_qualified_string())

    def test_non_rate_fact_may_not_carry_qualifiers(self):
        """A balloting fact with rate qualifiers is refused.

        The quote must speak the balloting language too, or V10 legitimately fires
        first — order is honest, so this test gives V10 what it needs.
        """
        self.doc.raw_text = ("DHA Phase 9 Prism Files. Balloting is expected in 2026. "
                             "4 Marla Affidavit: 218 Lacs")
        self.doc.save()
        res = validate(self.cand(fact_type="balloting_status", value="balloting is expected",
                                 raw_quote="DHA Phase 9 Prism Files. Balloting is expected in 2026.",
                                 size_marla="4", file_type=None), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V11_QUALIFIER_CONTRACT)

    def test_kanal_is_normalised_to_marla(self):
        self.doc.raw_text = "DHA Phase 7 Files 1 Kanal Allocation: 145.00 Lac"
        self.doc.save()
        q = "DHA Phase 7 Files 1 Kanal Allocation: 145.00 Lac"
        sizes, _ = qualifiers_in_quote(q)
        self.assertEqual(sizes, {20.0}, "1 kanal == 20 marla")


class TestQualifiedString(QualifierTestCase):
    def test_string_never_silently_drops_a_qualifier(self):
        c = self.cand()
        res = validate(c, self.r)
        f = persist_accepted(c, res)
        s = f.as_qualified_string()
        self.assertIn("marla", s)
        self.assertIn("4", s)
        self.assertIn("affidavit", s)

    def test_two_rates_same_value_different_qualifiers_are_distinguishable(self):
        """The exact confusion that motivated the schema change."""
        self.doc.raw_text = (f"{RATE_QUOTE} {AFF_ONLY_QUOTE} "
                             "DHA Phase 6 Files 4 Marla Affidavit: 218 Lacs")
        self.doc.save()
        a = self.cand()
        fa = persist_accepted(a, validate(a, self.r))
        b = self.cand(place_ref="DHA Phase 6",
                      raw_quote="DHA Phase 6 Files 4 Marla Affidavit: 218 Lacs")
        fb = persist_accepted(b, validate(b, self.r))
        self.assertEqual(fa.value, fb.value)
        self.assertNotEqual(fa.place_id, fb.place_id)


class TestStoredFactsAreQualified(QualifierTestCase):
    def test_every_stored_rate_is_explicitly_classified(self):
        """No rate may sit in the corpus with an undefined qualifier state."""
        for f in Fact.objects.filter(fact_type="rate"):
            self.assertIn(f.qualifier_status,
                          (QualifierStatus.COMPLETE, QualifierStatus.PARTIAL,
                           QualifierStatus.UNKNOWN))
            if f.qualifier_status == QualifierStatus.COMPLETE:
                self.assertIsNotNone(f.size_marla)
                self.assertTrue(f.file_type)


class TestQualifierDiscrimination(ResolverTestCase):
    """The point of the schema: rates that differ only by qualifier must stay distinct."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.src, _ = Source.objects.get_or_create(
            slug="disctest", defaults={"name": "d", "base_url": "https://x.invalid", "verified": True})
        cls.doc, _ = Document.objects.get_or_create(
            source=cls.src, url="https://x.invalid/d",
            defaults={"raw_text": (
                "DHA Phase 10 Files "
                "4 Marla Allocation: 54.00 Lac 4 Marla Affidavit: 56.25 Lac "
                "10 Marla Allocation: 97.25 Lac 10 Marla Affidavit: 105.00 Lac")})

    def rate(self, value, size, ftype, quote):
        return Candidate(fact_type="rate", value=value, place_ref="DHA Phase 10",
                         raw_quote=quote, document=self.doc, as_of=None,
                         size_marla=size, file_type=ftype)

    def test_same_place_same_amount_different_size_are_distinct(self):
        """The ambiguity that motivated the schema: one number, two sizes."""
        # quotes MUST be contiguous substrings of the document — V1 enforces that,
        # and correctly refused an earlier non-contiguous version of this test.
        q10 = "10 Marla Allocation: 97.25 Lac 10 Marla Affidavit: 105.00 Lac"
        q4 = "4 Marla Allocation: 54.00 Lac 4 Marla Affidavit: 56.25 Lac"
        a = self.rate("105.00 Lac", "10", "affidavit", q10)
        b = self.rate("56.25 Lac", "4", "affidavit", q4)
        ra, rb = validate(a, self.r), validate(b, self.r)
        self.assertTrue(ra.accepted, f"{ra.validator} {ra.reason}")
        self.assertTrue(rb.accepted, f"{rb.validator} {rb.reason}")
        fa = persist_accepted(a, ra)
        fb = persist_accepted(b, rb)
        self.assertEqual(fa.value, "105.00 Lac")
        self.assertEqual(fa.size_marla, Decimal("10.00"))
        self.assertEqual(fb.size_marla, Decimal("4.00"))
        self.assertEqual(fa.place_id, fb.place_id, "same place is the point")
        self.assertNotEqual(fa.size_marla, fb.size_marla)
        self.assertNotEqual(fa.as_qualified_string(), fb.as_qualified_string())

    def test_same_place_same_size_different_file_type_are_distinct(self):
        q = "10 Marla Allocation: 97.25 Lac 10 Marla Affidavit: 105.00 Lac"
        a = self.rate("97.25 Lac", "10", "allocation", q)
        b = self.rate("105.00 Lac", "10", "affidavit", q)
        ra, rb = validate(a, self.r), validate(b, self.r)
        self.assertTrue(ra.accepted, f"{ra.validator} {ra.reason}")
        self.assertTrue(rb.accepted, f"{rb.validator} {rb.reason}")
        fa = persist_accepted(a, ra)
        fb = persist_accepted(b, rb)
        self.assertEqual(fa.size_marla, fb.size_marla)
        self.assertNotEqual(fa.file_type, fb.file_type)

    def test_conflicting_qualifiers_rejected(self):
        """Quote states two sizes AND two file types; attributing is a guess."""
        q = "4 Marla Affidavit: 56.25 Lac 10 Marla Allocation: 97.25 Lac"
        res = validate(self.rate("56.25 Lac", None, None, q), self.r)
        self.assertFalse(res.accepted, "multi-size, multi-file-type quote left unqualified")
        self.assertEqual(res.validator, V11_QUALIFIER_CONTRACT)

    def test_multi_size_quote_accepted_when_qualifier_narrows_it(self):
        q = "4 Marla Affidavit: 56.25 Lac 10 Marla Allocation: 97.25 Lac"
        res = validate(self.rate("97.25 Lac", "10", "allocation", q), self.r)
        self.assertTrue(res.accepted, f"{res.validator} {res.reason}")

    def test_size_the_quote_never_states_rejected(self):
        q = "4 Marla Allocation: 54.00 Lac 4 Marla Affidavit: 56.25 Lac"
        res = validate(self.rate("56.25 Lac", "20", "affidavit", q), self.r)
        self.assertFalse(res.accepted)
        self.assertEqual(res.validator, V11_QUALIFIER_CONTRACT)

    def test_unsupported_file_type_value_rejected(self):
        q = "4 Marla Allocation: 54.00 Lac 4 Marla Affidavit: 56.25 Lac"
        res = validate(self.rate("56.25 Lac", "4", "inheritance", q), self.r)
        self.assertFalse(res.accepted, "a file_type the quote does not state must be refused")
        self.assertEqual(res.validator, V11_QUALIFIER_CONTRACT)
