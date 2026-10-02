"""Deterministic query engine — the read side of the corpus.

A question in, sourced facts out. Deliberately NOT LLM-driven at this layer:

  * retrieval is a filter over stored facts, so it can be tested exactly
  * the absence invariant is enforceable here. A query that matches nothing
    returns a coverage disclosure, never a negative market claim.
  * entity resolution stays the Resolver's job. The query layer never re-parses
    a place name; it hands the text to the Resolver.

Query understanding is pattern-based, not conversational, for the same reason.
Roman-Urdu / free-form intent parsing is a later layer and must not be allowed to
bypass these guarantees to produce a confident answer.
"""

import re
from dataclasses import dataclass, field

from corpus.models import Fact, Place
from corpus.resolver import Resolver

# --- query slots -----------------------------------------------------------

_SIZE_RE = re.compile(r"\b(\d{1,2})\s*[- ]?\s*(marla)\b|\b([12])\s*(kanal)\b", re.I)
_KANAL = {"1": 20.0, "2": 40.0}
_FILE_TYPES = ("affidavit", "allocation", "barcode", "balloted")
_BUDGET_RE = re.compile(
    r"(?:under|below|less than|upto|up to|within|max|maximum|budget)?\s*"
    r"(?:rs\.?|pkr\.?)?\s*"
    r"(\d+(?:\.\d+)?)\s*(lac|lakh|lacs|cr|crore|crs)\b", re.I)
_UNIT = {"lac": 100000, "lakh": 100000, "lacs": 100000,
         "cr": 10000000, "crore": 10000000, "crs": 10000000}


@dataclass
class Query:
    raw: str
    place: Place | None = None
    place_ref: str = ""
    size_marla: float | None = None
    file_type: str | None = None
    budget_pkr: float | None = None
    notes: list = field(default_factory=list)

    @property
    def has_filters(self) -> bool:
        return bool(self.size_marla or self.file_type or self.budget_pkr or self.place)


def parse_query(text: str, resolver: Resolver) -> Query:
    q = Query(raw=text or "")

    m = _SIZE_RE.search(text)
    if m:
        q.size_marla = float(m.group(1)) if m.group(1) else _KANAL[m.group(3)]

    low = text.lower()
    for ft in _FILE_TYPES:
        if ft in low:
            q.file_type = ft
            break

    m = _BUDGET_RE.search(text)
    if m and m.group(1):
        q.budget_pkr = float(m.group(1)) * _UNIT[m.group(2).lower()]

    # The place is whatever is left after removing the filter terms. The Resolver
    # decides whether it binds; this layer never decides that itself.
    residue = text
    for pat in (_SIZE_RE, _BUDGET_RE):
        residue = pat.sub(" ", residue)
    for ft in _FILE_TYPES:
        residue = re.sub(rf"\b{ft}\b", " ", residue, flags=re.I)
    # Strip budget/filter words AND the fact-type vocabulary a buyer naturally types.
    # Leaving "balloting" in the residue made "balloting in DHA Phase 10" resolve to
    # the string "balloting DHA Phase 10", which is not a place, so a real question
    # about a real phase returned nothing.
    for w in ("under", "below", "less than", "upto", "up to", "within", "max",
              "maximum", "budget", "is", "the", "a", "an", "for", "in", "of", "any",
              "price", "rate", "rates", "show", "me", "find", "search", "what",
              # fact-type vocabulary
              "balloting", "ballot", "balloted", "possession", "litigation", "fees",
              "fee", "taxes", "tax", "transfer", "files", "file", "status", "statuses",
              "details", "info", "information", "about", "tell", "give", "list", "all",
              "please", "there", "have", "has", "got", "available", "currently",
              # filler that means "no specific place"
              "anywhere", "everywhere", "lahore", "city", "apply", "applies", "paid", "pay",
              "worth", "good", "cheap", "cheapest", "best", "options", "option"):
        residue = re.sub(rf"\b{re.escape(w)}\b", " ", residue, flags=re.I)
    residue = re.sub(r"[^A-Za-z0-9\-\s]", " ", residue)
    residue = re.sub(r"\s+", " ", residue).strip()
    q.place_ref = residue

    if residue:
        res = resolver.resolve(residue)
        if res.is_resolved:
            q.place = res.place
        else:
            q.notes.append(f"place {residue!r} not resolved ({res.outcome})")
    return q


# --- coverage disclosure ---------------------------------------------------

def coverage_of(place: Place | None) -> dict:
    """What the corpus actually holds, so a zero-result answer can say so."""
    qs = Fact.objects.all()
    if place is not None:
        qs = qs.filter(place=place)
    # dedupe: repeated extraction runs store the same claim more than once, and a
    # count that double-counts must not be shown as though it were coverage.
    facts = _dedupe(list(qs.select_related("place", "source")))
    places = Place.objects.filter(level__in=("phase", "society"))
    return {
        "fact_count": len(facts),
        "places_with_facts": facts and len({f.place_id for f in facts}) or 0,
        "searched_place": place.canonical_name if place else None,
        "searched_place_id": place.id if place else None,
        "total_places": places.count(),
        "source_slugs": sorted({f.source.slug for f in facts}),
        "oldest_as_of": min((f.as_of for f in facts if f.as_of), default=None),
        "newest_as_of": max((f.as_of for f in facts if f.as_of), default=None),
    }


# --- fact-type taxonomy -----------------------------------------------------

# Buyer-facing types, in the order a buyer asks about them. Values that map to the
# same type are grouped, so a growing corpus does not fragment the tab row.
TYPE_TABS = (
    ("rate",      "Rate",       ("rate", "price", "pricing")),
    ("balloting", "Balloting",  ("balloting", "balloting_status", "balloted")),
    ("possession","Possession", ("possession", "possession_status")),
    ("fees",      "Fees",       ("fees", "fee", "charges", "maintenance")),
)
_TYPE_ALIASES = {alias: key for key, _label, aliases in TYPE_TABS for alias in aliases}
OTHER_LABEL = "Other"


def _dedupe_key(f):
    return (f.place_id, f.fact_type, f.value, f.size_marla, f.file_type, f.raw_quote)


def _dedupe(facts):
    """Collapse identical facts, keeping the newest. Simulated extraction runs
    accumulate duplicates for the same claim."""
    seen, out = set(), []
    for f in sorted(facts, key=lambda x: -x.id):
        k = _dedupe_key(f)
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


def type_counts() -> list[dict]:
    """Honest per-type counts for the tab row.

    Derived from the corpus, never typed in. A type with nothing stored reports 0
    rather than disappearing, so the tabs tell the truth before anyone clicks one.
    Counts use the same dedupe as search(), so the tab total matches the results.
    """
    counts = {key: 0 for key, _l, _a in TYPE_TABS}
    counts[OTHER_LABEL] = 0
    for f in _dedupe(Fact.objects.all()):
        counts[_TYPE_ALIASES.get(f.fact_type, OTHER_LABEL)] += 1
    rows = [{"key": key, "label": label, "count": counts[key]}
            for key, label, _a in TYPE_TABS]
    if counts[OTHER_LABEL]:
        # Facts whose type is not in the taxonomy are surfaced, not hidden, so
        # All always reconciles with the visible tabs.
        rows.append({"key": "__other", "label": OTHER_LABEL,
                     "count": counts[OTHER_LABEL]})
    return rows


# --- retrieval -------------------------------------------------------------

def search(text: str, resolver: Resolver | None = None, limit: int = 25,
           fact_type: str | None = None):
    resolver = resolver or Resolver()
    q = parse_query(text, resolver)
    facts = Fact.objects.select_related("place", "source", "document").all()

    if fact_type and fact_type != "__all":
        aliases = (_TYPE_ALIASES.get(fact_type)
                   if fact_type != "__other" else None)
        if aliases:
            names = sorted(a for a, k in _TYPE_ALIASES.items() if k == aliases)
            facts = facts.filter(fact_type__in=names)
        elif fact_type == "__other":
            known = set(_TYPE_ALIASES)
            facts = facts.exclude(fact_type__in=known)
        else:
            facts = facts.none()   # unknown tab is a filter that matches nothing
        q.notes.append(f"filtered to fact type {fact_type!r}")

    if q.place is not None:
        facts = facts.filter(place=q.place)
    elif q.place_ref:
        # A place WAS mentioned but did not resolve. Returning the whole corpus here
        # answered a question about Phase 12 with rates from Phase 7 — the most
        # misleading thing this service can do, and it errored nowhere. An
        # unrecognised place must yield nothing plus a disclosure, never a widening.
        facts = facts.none()
        q.notes.append(
            f"place {q.place_ref!r} was not recognised, so the corpus was NOT searched "
            "widely; nothing is shown rather than facts from somewhere else")
    if q.file_type:
        facts = facts.filter(file_type=q.file_type)
    if q.size_marla is not None:
        # An unknown size cannot satisfy a size filter. It is not a match.
        facts = facts.filter(size_marla=q.size_marla)
    if q.budget_pkr is not None:
        facts = [f for f in facts
                 if f.amount_pkr is not None and f.amount_pkr <= q.budget_pkr]

    # The simulated extraction runs accumulate duplicates for the same (place, type,
    # value, quote). Collapse on the identity of a fact, keeping the newest.
    seen, deduped = set(), []
    for f in sorted(facts, key=lambda x: (-x.id)):
        key = (f.place_id, f.fact_type, f.value, f.size_marla, f.file_type, f.raw_quote)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    matched = deduped[:limit]
    coverage = coverage_of(q.place)
    if q.place_ref and q.place is None:
        # nothing was searched because the place was unrecognised; coverage must not
        # report the whole corpus as if it had been consulted
        coverage = {"fact_count": 0, "places_with_facts": 0,
                    "searched_place": q.place_ref, "searched_place_id": None,
                    "total_places": Place.objects.filter(level__in=("phase", "society")).count(),
                    "source_slugs": [], "oldest_as_of": None, "newest_as_of": None}
    return q, matched, coverage


def no_evidence_answer(query: Query, coverage: dict) -> dict:
    """The absence invariant, enforced.

    Says what the corpus searched and what it holds. It must NEVER say the property
    or market condition does not exist — this corpus is secondary reporting and cannot
    support a negative claim. See the design doc section "Invariant: absence of
    evidence is not evidence of absence".
    """
    where = coverage["searched_place"] or "any place in the corpus"
    return {
        "kind": "no_evidence",
        "headline": f"The corpus holds no evidence matching that query.",
        "searched": where,
        "detail": (
            f"I searched stored facts for {where}. "
            f"That search returned {coverage['fact_count']} fact(s) covering "
            f"{coverage['places_with_facts']} place(s)."
        ),
        "coverage": coverage,
        # Deliberately worded so it does NOT contain any phrase from the negative-claim
        # list. An audit that a naive substring scan can run must not trip on our own
        # copy — if the disclaimer says "does not exist" inside a negation, the check
        # becomes unusable and quietly gets skipped.
        "not_a_claim": (
            "This is a statement about MY CORPUS ONLY. It is not a statement about the "
            "Lahore market. Verify anything that matters with DHA, LDA, and a lawyer."
        ),
    }


def serialize_fact(f: Fact) -> dict:
    return {
        "id": f.id,
        "place": f.place.canonical_name,
        "place_level": f.place.level,
        "fact_type": f.fact_type,
        "qualified": f.as_qualified_string(),
        "value": f.value,
        "size_marla": float(f.size_marla) if f.size_marla is not None else None,
        "file_type": f.file_type,
        "amount_pkr": float(f.amount_pkr) if f.amount_pkr is not None else None,
        "qualifier_status": f.qualifier_status,
        "fully_qualified": f.is_fully_qualified,
        "as_of": f.as_of.isoformat() if f.as_of else None,
        "source": f.source.slug,
        "source_url": f.document.url,
        "quote": f.raw_quote,
    }