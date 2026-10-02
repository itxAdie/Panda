"""The answer surface, and the absence invariant enforced at the UI layer.

The invariant was documented and recorded in corpus.validators, but nothing enforced
it, because no answer layer existed. These tests are that enforcement.

The gate: a query with no supporting evidence must never yield a claim that a property
or market condition does not exist. It must disclose what the corpus searched.
"""

import json

from django.test import TestCase
from django.urls import reverse

from corpus import query as Q
from corpus.models import Document, Fact, Source
from corpus.resolver import Resolver

# Phrases that would convert "my corpus is empty" into "reality is empty".
NEGATIVE_CLAIMS = [
    "does not exist", "doesn't exist", "no such property", "no such property exists",
    "not available", "unavailable", "does not have", "doesn't have", "none exist",
    "no properties", "no property exists", "doesn't exist anywhere", "cannot exist",
    "will never exist", "there is no", "there are no",
]


class SurfaceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.src, _ = Source.objects.get_or_create(
            slug="testsrc", defaults={"name": "t", "base_url": "https://x.invalid", "verified": True})
        cls.doc, _ = Document.objects.get_or_create(
            source=cls.src, url="https://x.invalid/rates", defaults={"raw_text": "x"})
        cls.quote = "DHA Phase 10 Files 10 Marla Allocation: 54.00 Lac 10 Marla Affidavit: 56.25 Lac"

    @staticmethod
    def dha_society():
        from corpus.models import Society
        soc, _ = Society.objects.get_or_create(
            slug="soc_dha_lahore", defaults={"canonical_name": "DHA Lahore", "city": "Lahore"})
        return soc

    def make_phase(self, name):
        from corpus.models import Place
        # get_or_create: several of these names exist in the loaded map, and create()
        # collides on the (society, canonical_name) unique constraint.
        p, _ = Place.objects.get_or_create(
            society=self.dha_society(), canonical_name=name,
            defaults={"level": "phase"})
        return p

    def make_fact(self, place, value="54.00 Lac", size=10.0, ftype="allocation", amount=5400000.0):
        from corpus.models import QualifierStatus
        return Fact.objects.create(
            place=place, fact_type="rate", value=value,
            size_marla=size, file_type=ftype, amount_pkr=amount,
            qualifier_status=(QualifierStatus.COMPLETE if size and ftype
                              else QualifierStatus.UNKNOWN),
            document=self.__class__.doc, raw_quote=self.quote, source=self.__class__.src,
        )


class TestZeroResultNeverClaimsAbsence(SurfaceTestCase):
    """THE GATE. A zero-result path must not make a negative market claim."""

    def test_api_zero_result_says_no_evidence_not_no_property(self):
        from corpus.models import Place
        p = self.make_phase("DHA Phase 7")
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "10 marla allocation in DHA Phase 7"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["kind"], "no_evidence")

        blob = json.dumps(body).lower()
        for phrase in NEGATIVE_CLAIMS:
            self.assertNotIn(phrase, blob,
                             f"zero-result answer contains the negative claim {phrase!r}")

    def test_zero_result_discloses_what_it_searched(self):
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "anything at all"}),
                             content_type="application/json")
        body = r.json()
        self.assertIn("searched", body)
        self.assertIn("coverage", body)
        self.assertIn("fact_count", body["coverage"])
        self.assertIn("total_places", body["coverage"])
        self.assertTrue(body["not_a_claim"])

    def test_unknown_place_is_coverage_disclosure_not_a_verdict(self):
        """A place the corpus cannot resolve is not a place that does not exist."""
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "rates in Bahawalpur XYZ township"}),
                             content_type="application/json")
        blob = json.dumps(r.json()).lower()
        for phrase in NEGATIVE_CLAIMS:
            self.assertNotIn(phrase, blob)

    def test_no_evidence_answer_helper_is_safe_on_its_own(self):
        from corpus.models import Place
        cov = Q.coverage_of(Place.objects.filter(level="phase").first())
        ans = Q.no_evidence_answer(None, cov)
        blob = json.dumps(ans).lower()
        for phrase in NEGATIVE_CLAIMS:
            self.assertNotIn(phrase, blob)

    def test_unmatched_filters_do_not_become_a_negative_claim(self):
        """Filter too narrow for the corpus is still absence of evidence."""
        p = self.make_phase("DHA Phase 7")
        self.make_fact(p)
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "20 marla affidavit under 10 lac in DHA Phase 7"}),
                             content_type="application/json")
        self.assertEqual(r.json()["kind"], "no_evidence")
        blob = json.dumps(r.json()).lower()
        for phrase in NEGATIVE_CLAIMS:
            self.assertNotIn(phrase, blob)


class TestUnresolvedPlaceNeverWidens(SurfaceTestCase):
    """An unrecognised place must yield nothing, never the whole corpus.

    Found by running the surface: asking about a phase that does not resolve returned
    rates from a DIFFERENT phase, because the place filter was skipped rather than
    applied. Nothing errored. That is the most misleading thing this service can do,
    and it is the exact failure the absence invariant exists to prevent.
    """

    def test_unrecognised_place_does_not_return_other_places(self):
        p = self.make_phase("DHA Phase 7")
        self.make_fact(p)
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "rates in Bahawalpur XYZ township"}),
                             content_type="application/json")
        body = r.json()
        self.assertEqual(body["kind"], "no_evidence")
        self.assertNotIn("facts", body)
        for phrase in NEGATIVE_CLAIMS:
            self.assertNotIn(phrase, json.dumps(body).lower())

    def test_coverage_does_not_claim_the_corpus_was_searched(self):
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "rates in Bahawalpur XYZ township"}),
                             content_type="application/json")
        cov = r.json()["coverage"]
        self.assertEqual(cov["fact_count"], 0)
        self.assertEqual(cov["source_slugs"], [])

    def test_fact_type_vocabulary_does_not_break_the_place(self):
        """"balloting in DHA Phase 10" must find the balloting facts.

        Leaving "balloting" in the residue produced the string
        "balloting DHA Phase 10", which is not a place, so a real question about a
        real phase returned nothing.
        """
        from corpus.models import QualifierStatus
        p = self.make_phase("DHA Phase 10")
        Fact.objects.create(place=p, fact_type="balloting_status",
                            value="no published ballot date", as_of=None,
                            document=self.doc, raw_quote=self.quote, source=self.src,
                            qualifier_status=QualifierStatus.COMPLETE)
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "balloting in DHA Phase 10"}),
                             content_type="application/json")
        body = r.json()
        self.assertEqual(body["kind"], "evidence", body)
        self.assertEqual(body["parsed"]["place"], "DHA Phase 10")

    def test_duplicate_facts_are_collapsed(self):
        p = self.make_phase("DHA Phase 7")
        # simulated re-runs accumulate identical facts; size must match the query
        self.make_fact(p, size=4.0)
        self.make_fact(p, size=4.0)
        _q, facts, _ = Q.search("4 marla allocation in DHA Phase 7", Resolver())
        self.assertEqual(len(facts), 1)

    def test_size_filter_is_not_a_wildcard(self):
        p = self.make_phase("DHA Phase 7")
        self.make_fact(p, size=10.0)
        _q, facts, _ = Q.search("4 marla allocation in DHA Phase 7", Resolver())
        self.assertEqual(facts, [], "a 10-marla fact answered a 4-marla question")


class TestAnswersAreSourced(SurfaceTestCase):
    """Every fact returned carries quote, source URL and as_of."""

    def setUp(self):
        from corpus.models import Place
        self.place = self.make_phase("DHA Phase 10")
        self.fact = self.make_fact(self.place)

    def test_hit_carries_quote_source_and_provenance(self):
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "10 marla allocation under 55 lac in DHA Phase 10"}),
                             content_type="application/json")
        body = r.json()
        self.assertEqual(body["kind"], "evidence")
        self.assertGreaterEqual(body["count"], 1)
        f = body["facts"][0]
        self.assertTrue(f["quote"], "a returned fact must carry its quote")
        self.assertTrue(f["source_url"], "a returned fact must carry its source URL")
        self.assertIn("source", f)
        self.assertIn("as_of", f)
        self.assertIn("qualifier_status", f)

    def test_every_fact_in_the_payload_is_sourced(self):
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "allocation in DHA Phase 10"}),
                             content_type="application/json")
        for f in r.json().get("facts", []):
            self.assertTrue(f["quote"])
            self.assertTrue(f["source_url"])


class TestQueryParsing(SurfaceTestCase):
    def setUp(self):
        from corpus.models import Place
        self.place = self.make_phase("DHA Phase 10")

    def test_parses_size_file_type_and_budget(self):
        q = Q.parse_query("10 marla allocation under 55 lac in DHA Phase 10", Resolver())
        self.assertEqual(q.size_marla, 10.0)
        self.assertEqual(q.file_type, "allocation")
        self.assertEqual(q.budget_pkr, 5500000.0)
        self.assertIsNotNone(q.place)
        self.assertEqual(q.place.canonical_name, "DHA Phase 10")

    def test_kanal_is_normalised_to_marla(self):
        q = Q.parse_query("1 kanal in DHA Phase 10", Resolver())
        self.assertEqual(q.size_marla, 20.0)

    def test_budget_filter_excludes_above_budget(self):
        self.make_fact(self.place, value="60.00 Lac", amount=6000000.0)
        q, facts, _ = Q.search("under 55 lac in DHA Phase 10", Resolver())
        self.assertEqual(facts, [])

    def test_unresolved_size_does_not_match_a_size_filter(self):
        """An unknown size is not a match. It must not slip through as a wildcard."""
        from corpus.models import QualifierStatus
        Fact.objects.create(place=self.place, fact_type="rate", value="? Lac",
                            size_marla=None, file_type=None, amount_pkr=None,
                            qualifier_status=QualifierStatus.UNKNOWN,
                            document=self.doc, raw_quote=self.quote, source=self.src)
        _q, facts, _ = Q.search("10 marla in DHA Phase 10", Resolver())
        for f in facts:
            self.assertEqual(float(f.size_marla), 10.0,
                             "a fact with unknown size matched a size filter")


class TestSurfacePage(TestCase):
    def test_page_loads_and_shows_coverage(self):
        r = self.client.get(reverse("corpus:search"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Panda")
        self.assertContains(r, "Corpus now holds")
        self.assertContains(r, "not the market")

    def test_empty_query_is_a_400_not_a_claim(self):
        r = self.client.post(reverse("corpus:search_api"),
                             data=json.dumps({"q": "   "}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)

class TestTypeTabsAreDerivedNotTyped(SurfaceTestCase):
    """Tab counts come from the corpus.

    The first version of this UI hardcoded "Rate 3 / Balloting 2" in the markup. The
    database actually held rate 4 and balloting_status 4, so the tab row was lying
    before anyone clicked it. These tests fail if a count is ever typed in again.
    """

    def test_counts_match_the_rows_actually_stored(self):
        p = self.make_phase("DHA Phase 11")
        self.make_fact(p, value="60.00 Lac")                       # rate
        self.make_fact(p, ftype="balloted")                        # still fact_type=rate
        Fact.objects.create(place=p, fact_type="balloting_status", value="balloting open",
                            document=self.doc, raw_quote="q2", source=self.src)
        rows = {r["key"]: r["count"] for r in Q.type_counts()}
        self.assertEqual(rows["rate"], 2)
        self.assertEqual(rows["balloting"], 1)
        self.assertEqual(rows["possession"], 0)
        self.assertEqual(rows["fees"], 0)

    def test_zero_count_types_stay_visible(self):
        """A type with nothing stored reports 0 rather than vanishing. A missing tab
        is indistinguishable from a forgotten one."""
        labels = [r["label"] for r in Q.type_counts()]
        for label in ("Rate", "Balloting", "Possession", "Fees"):
            self.assertIn(label, labels)

    def test_all_reconciles_with_the_visible_tabs(self):
        """The tab total must match what a search can actually return, or the All tab
        promises rows the results view cannot produce."""
        distinct = len(Q._dedupe(Fact.objects.all()))
        self.assertEqual(sum(r["count"] for r in Q.type_counts()), distinct)

    def test_duplicates_do_not_inflate_a_tab(self):
        p = self.make_phase("DHA Phase 11")
        self.make_fact(p, value="60.00 Lac")
        self.make_fact(p, value="60.00 Lac")   # same claim stored twice
        rows = {r["key"]: r["count"] for r in Q.type_counts()}
        self.assertEqual(rows["rate"], 1)


class TestTypeFilterNarrowsResults(SurfaceTestCase):
    def setUp(self):
        self.p = self.make_phase("DHA Phase 11")
        self.make_fact(self.p, value="60.00 Lac")
        Fact.objects.create(place=self.p, fact_type="balloting_status",
                            value="balloting open", document=self.doc,
                            raw_quote="q2", source=self.src)

    def ask(self, text, ftype=None):
        return self.client.post(reverse("corpus:search_api"),
                                data=json.dumps({"q": text, "type": ftype}),
                                content_type="application/json").json()

    def test_type_filter_restricts_the_result_set(self):
        both = self.ask("DHA Phase 11")
        only_balloting = self.ask("DHA Phase 11", "balloting")
        self.assertGreater(both["count"], only_balloting["count"])
        for f in only_balloting["facts"]:
            self.assertEqual(f["fact_type"], "balloting_status")

    def test_filtered_out_type_with_no_rows_is_a_disclosure_not_everything(self):
        """Selecting Possession must not silently return the unfiltered corpus."""
        r = self.ask("DHA Phase 11", "possession")
        self.assertEqual(r["kind"], "no_evidence")
        self.assertEqual(r["count"] if "count" in r else 0, 0)
        for phrase in NEGATIVE_CLAIMS:
            self.assertNotIn(phrase, json.dumps(r).lower())

    def test_unknown_type_key_matches_nothing(self):
        r = self.ask("DHA Phase 11", "not_a_real_type")
        self.assertEqual(r["kind"], "no_evidence")

    def test_all_type_is_not_a_filter(self):
        self.assertEqual(self.ask("DHA Phase 11", "__all")["kind"], "evidence")


class TestLandingPageIsTheHero(TestCase):
    """The landing page is the hero alone; results exist only after a question."""

    def test_page_renders_tabs_with_server_side_counts(self):
        r = self.client.get(reverse("corpus:search"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'role="tablist"')
        self.assertContains(r, 'data-type="rate"')
        self.assertContains(r, 'data-type="balloting"')

    def test_page_carries_the_corpus_disclosure_and_credit(self):
        r = self.client.get(reverse("corpus:search"))
        self.assertContains(r, "Corpus now holds")
        self.assertContains(r, "not the market")
        # CC BY 4.0 requires visible credit wherever the image appears
        self.assertContains(r, "CC BY 4.0")
        self.assertContains(r, "AlidPedian")
