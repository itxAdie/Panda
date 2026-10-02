"""Extraction boundary — deterministic validators (V1-V7).

Contract: every LLM output must be reconstructible from its quote by a deterministic
function. If no deterministic check can verify it, it does not enter the knowledge base.

The extractor NEVER names a place. A candidate carries `place_ref` — the string as the
source wrote it — and V4 resolves it through the deterministic Resolver. An invented
Place id therefore has no referent and cannot be constructed.

Tier 1 only. Tier 2 (derived values: bands, ranges, comparisons) is refused at the
boundary, because a derived value that cannot be recomputed when its inputs are
corrected is precisely the failure this project exists to prevent.

ABSENCE INVARIANT
------------------
No validator may convert "no supporting fact" into "no such thing exists". The corpus
is entirely secondary reporting: asking prices from brokerage blogs, statuses
second-hand from DHA notices. It cannot support a negative claim about the market.

This matters most in the answer layer, which does not exist yet and is where the
invariant will be easiest to break. It is recorded here because this module is what
guarantees a returned empty result means "nothing stored", never "nothing real".
See the design doc section "Invariant: absence of evidence is not evidence of absence".
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from corpus import DROPPED, RESOLVED, UNRESOLVED
from corpus.models import BlockIdentity, Document, Fact, Observation, Place, Source

# Validator identifiers. Persisted on every Observation.rejection.
V1_QUOTE_FIDELITY = "V1-quote-fidelity"
V2_VALUE_PRESENCE = "V2-value-presence"
V3_DATE_PRESENCE = "V3-date-presence"
V4_ENTITY_BINDING = "V4-entity-binding"
V5_CROSS_CITY = "V5-cross-city"
V6_CATEGORY_ROUTING = "V6-category-routing"
V7_NO_SELF_PROMOTION = "V7-no-self-promotion"
V8_TIER = "V8-tier-refusal"
V9_PLACE_CORROBORATION = "V9-place-corroboration"
V10_FACT_TYPE_CUE = "V10-fact-type-cue"
V11_QUALIFIER_CONTRACT = "V11-qualifier-contract"

VALIDATORS = (V1_QUOTE_FIDELITY, V2_VALUE_PRESENCE, V3_DATE_PRESENCE, V4_ENTITY_BINDING,
              V5_CROSS_CITY, V6_CATEGORY_ROUTING, V7_NO_SELF_PROMOTION, V8_TIER,
              V9_PLACE_CORROBORATION, V10_FACT_TYPE_CUE, V11_QUALIFIER_CONTRACT)

# File types a source may actually state. Anything else is not a file type.
FILE_TYPES = frozenset({"affidavit", "allocation", "barcode", "balloted", "unballoted"})
_SIZE_MARLA = {"3": 3, "5": 5, "7": 7, "8": 8, "10": 10, "20": 20, "40": 40,
               "1 kanal": 20, "2 kanal": 40}

# Corroboration looks BACKWARD from the quote only. On these pages a section heading
# precedes the rows it labels, so a mention BEFORE the quote corroborates it. A mention
# AFTER the quote belongs to the NEXT section and must not count.
#
# A symmetric window was tried first and is wrong: on a short document a 500-char
# window either side covers the whole page, so a quote about Phase 9 was "corroborated"
# by a Rahbar heading that appears later. That is precisely the error V9 exists to catch.
CORROBORATION_WINDOW = 500

ACCEPTED = "accepted"

# Tier 1 fact types. Anything outside this set is out of contract.
TIER1_FACT_TYPES = frozenset({
    "rate",               # 10 marla allocation = 43.75 lac
    "size",               # 5 marla / 1 kanal
    "file_type",          # affidavit / allocation / barcode / balloted
    "balloting_status",   # expected, confirmed, cleared, stalled
    "possession_status",  # open, granted, pending, not announced
    "litigation_status",  # cleared, pending, unknown
    "fee_schedule",       # membership 150000 (was 75000)
    "tax_regime",         # 236K buyer advance 3% -> 1.5%
    "transfer_process",   # NDC mandatory; 7-15 working days
})

# Tier 2 — refused in v1. Listed explicitly so a request is REJECTED, not silently
# dropped: an unrecognised fact_type is an error we want to see.
TIER2_FACT_TYPES = frozenset({"rate_band", "price_band", "range", "comparison", "median"})

# Cross-city guard, mirroring corpus.resolver. A fact text naming DHA Valley, or a
# bare DHA Phase 1-4, must not attach to a Lahore place.
_DESIG = r"(?:Ph(?:ase)?\.?|P)\s*-?\s*"
CROSS_CITY_FACT = re.compile(
    rf"\b(?:DHA|Defence)\s+(?:{_DESIG}|)[1-4IVX]+\b", re.I)
DHA_VALLEY_FACT = re.compile(r"\bDHA\s+Valley\b", re.I)
CCA_FACT = re.compile(r"\bCCA-?\s*[13]\b", re.I)

# Number extraction for V2. Handles 43.75, 1.5%, 45,000, 10, 2-5, 30x120.
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("’", "'").replace("‘", "'")
                  .replace("“", '"').replace("”", '"')).strip().lower()


def _norm_aggressive(s: str) -> str:
    """Loose normalisation for substring checks: collapses punctuation and space."""
    return re.sub(r"[^a-z0-9]+", " ", _norm_ws(s)).strip()


def _numbers(s: str):
    return [m.group(0).replace(",", "") for m in _NUM.finditer(s or "")]


_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %B %Y",
                 "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y.", "%d %B,%Y")
_TEXT_DATE = re.compile(
    r"\b(\d{1,2})\s+([A-Za-z]{3,9}),?\s+(\d{4})\b|"
    r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b")


def _to_date(s: str):
    s = (s or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ]|$)")


def _dates_in(text: str):
    """Every date mentioned, in any format sources actually use.

    Prose ("25 August 2026", "August 25, 2026") and ISO-8601
    ("2026-08-25T17:11:57+00:00"). Metadata dates are almost always ISO; body prose
    is almost never. Both must parse or V3 refuses valid facts.
    """
    out = set()
    for m in _ISO_DATE.finditer(text or ""):
        try:
            out.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    for m in _TEXT_DATE.finditer(text or ""):
        d1, mon, y = m.group(1), m.group(2), m.group(3)
        d2, mon2, y2 = m.group(4), m.group(5), m.group(6)
        for day, month, year in ((d1, mon, y), (d2, mon2, y2)):
            if not day:
                continue
            mo = _MONTHS.get((month or "").lower())
            if not mo:
                continue
            try:
                out.add(date(int(year), mo, int(day)))
            except ValueError:
                continue
    return out


@dataclass
class Candidate:
    """An LLM's proposed fact. Deliberately carries NO Place object.

    `place_ref` is the string as written in the source. V4 resolves it. This is what
    makes 'the LLM never names a place' enforceable rather than aspirational.
    """

    fact_type: str
    value: str
    place_ref: str
    raw_quote: str
    document: Document
    as_of: Optional[str] = None
    # M6 qualifiers. Supplied by the proposer but CHECKED against the quote by V11 —
    # a supplied qualifier the quote does not support is refused, never trusted.
    size_marla: Optional[str] = None
    file_type: Optional[str] = None
    # A malicious/buggy extractor might try to set these. V7 refuses.
    claims_verified_block: Optional[str] = None
    claims_place_id: Optional[int] = None
    model: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    accepted: bool
    validator: str = ""          # which validator rejected (empty if accepted)
    reason: str = ""
    place: Optional[Place] = None
    category: str = ""           # for V6-routed measurements

    def __bool__(self):
        return self.accepted


_CUE_CACHE = {}


def _cues_for(fact_type: str):
    from corpus.models import FactTypeCue
    if not _CUE_CACHE:
        for c in FactTypeCue.objects.all():
            _CUE_CACHE.setdefault(c.fact_type, []).append(c)
    return _CUE_CACHE.get(fact_type, [])


def reset_cue_cache():
    _CUE_CACHE.clear()


_SIZE_RE = re.compile(r"\b(\d{1,2})\s*(?:\-\s*)?marla\b|\b([12])\s*kanal\b", re.I)


def qualifiers_in_quote(quote: str):
    """What size and file type the QUOTE itself states. The only admissible source."""
    q = _norm_ws(quote)
    sizes = set()
    for m in _SIZE_RE.finditer(q):
        if m.group(1):
            sizes.add(float(m.group(1)))
        elif m.group(2):
            sizes.add(20.0 if m.group(2) == "1" else 40.0)
    ftypes = {ft for ft in FILE_TYPES if re.search(r"\b" + ft + r"\b", q, re.I)}
    return sizes, {f.lower() for f in ftypes}


def _qualifier_check(cand: Candidate) -> Optional[ValidationResult]:
    """Enforce the (place, size, file_type, amount) contract on rate facts."""
    if cand.fact_type != "rate":
        # Non-rate facts must not smuggle qualifiers they do not use.
        if cand.size_marla or cand.file_type:
            return ValidationResult(
                False, V11_QUALIFIER_CONTRACT,
                f"fact_type {cand.fact_type!r} does not take size/file_type qualifiers")
        return None

    q_sizes, q_ftypes = qualifiers_in_quote(cand.raw_quote)

    # a supplied qualifier must be supported by the quote
    if cand.size_marla:
        try:
            want = float(cand.size_marla)
        except (TypeError, ValueError):
            return ValidationResult(False, V11_QUALIFIER_CONTRACT,
                                    f"size_marla {cand.size_marla!r} is not a number")
        if q_sizes and want not in q_sizes:
            return ValidationResult(
                False, V11_QUALIFIER_CONTRACT,
                f"supplied size {want} marla is not stated in the quote "
                f"(quote states: {sorted(q_sizes)})")
    if cand.file_type:
        if q_ftypes and cand.file_type.lower() not in q_ftypes:
            return ValidationResult(
                False, V11_QUALIFIER_CONTRACT,
                f"supplied file_type {cand.file_type!r} is not stated in the quote "
                f"(quote states: {sorted(q_ftypes)})")

    # a qualifier the quote DOES state must not be silently omitted
    if q_sizes and not cand.size_marla:
        return ValidationResult(
            False, V11_QUALIFIER_CONTRACT,
            f"quote states size {sorted(q_sizes)} marla; leaving it unknown would "
            "make this rate indistinguishable from other sizes")
    if q_ftypes and not cand.file_type:
        # Fires when the quote names ONE file type and when it names SEVERAL. Two file
        # types in one quote is precisely when disambiguation matters most — an affidavit
        # and an allocation at the same size are different assets with different prices.
        return ValidationResult(
            False, V11_QUALIFIER_CONTRACT,
            f"quote states file_type(s) {sorted(q_ftypes)}; leaving it unknown would make "
            "this rate indistinguishable from other file types at the same size")
    return None


def _cue_check(fact_type: str, quote: str) -> Optional[ValidationResult]:
    """The quote must contain a cue for the proposed fact_type.

    Ambiguous or unknown language REJECTS. A fact_type with no cue rows loaded also
    rejects — an unvalidated vocabulary is not an implicit pass.
    """
    cues = _cues_for(fact_type)
    if not cues:
        return ValidationResult(False, V10_FACT_TYPE_CUE,
                                f"no cue vocabulary loaded for fact_type {fact_type!r}; "
                                "refusing rather than assuming the label is right")
    q = _norm_aggressive(quote)
    groups = {}
    for c in cues:
        if c.cue.lower() in q:
            groups.setdefault(c.group, []).append(c.cue)
    if not groups:
        others = sorted({ft for ft in _CUE_CACHE if ft != fact_type
                         and any(c.cue.lower() in q for c in _CUE_CACHE[ft])})
        hint = f"; quote does speak: {', '.join(others)}" if others else "; no known cue matches"
        return ValidationResult(False, V10_FACT_TYPE_CUE,
                                f"quote contains no cue for fact_type {fact_type!r}{hint}")
    return None


def _place_markers(place) -> set:
    """Tokens that would corroborate this place if found BEFORE the quote.

    Two rules learned the hard way:

    1. Only `phase`-level places yield `phase N` / `ph N` markers. A place named
       "Rahbar Sector-4" contains the digit 4, but that is a SECTOR number, not a
       phase — deriving "phase 4" from it let a Phase 9 quote be filed as Phase 4.
    2. The society name ("DHA Lahore") is never a marker. Every page on a DHA source
       contains it, so it corroborates nothing at all.
    """
    marks = {_norm_aggressive(place.canonical_name)}
    p = place
    while p is not None:
        if p.level == "phase":
            m = re.search(r"(\d{1,2})", p.canonical_name)
            if m:
                marks.add(f"phase {m.group(1)}")
                marks.add(f"ph {m.group(1)}")
                marks.add(f"phasE {m.group(1)}".lower())
        p = p.parent if p.parent_id else None
    return {m for m in marks if m}


def _place_corroborated(cand: Candidate, place, doc_text: str) -> bool:
    """The resolved place must be mentioned BEFORE the quote in the document.

    Headings precede the rows they label. A place named only AFTER the quote belongs
    to a following section, so it does not corroborate this one — that case is exactly
    how a Phase 9 quote came to be filed under Rahbar Sector-4.
    """
    marks = _place_markers(place)
    if not marks:
        return False
    hay = _norm_aggressive(doc_text)
    needle = _norm_aggressive(cand.raw_quote)
    idx = hay.find(needle) if needle else -1
    if idx < 0:
        return False
    window = hay[max(0, idx - CORROBORATION_WINDOW): idx + len(needle)]
    return any(m in window for m in marks)


def validate(cand: Candidate, resolver=None) -> ValidationResult:
    """Run V1-V7 in order. First failure wins and is reported verbatim.

    Order matters: V1 before V2 (a fabricated quote makes V2 meaningless), V4 before
    V5/V6 (know what we're attaching to before judging the attachment).
    """
    if resolver is None:
        from corpus.resolver import Resolver
        resolver = Resolver()

    doc_text = cand.document.raw_text or ""

    # ---- V1 quote fidelity: the quote must exist in the document -------------
    if not cand.raw_quote or not doc_text:
        return ValidationResult(False, V1_QUOTE_FIDELITY, "empty quote or empty document")
    q_norm = _norm_aggressive(cand.raw_quote)
    d_norm = _norm_aggressive(doc_text)
    if not q_norm:
        return ValidationResult(False, V1_QUOTE_FIDELITY, "quote normalises to nothing")
    if q_norm not in d_norm:
        return ValidationResult(
            False, V1_QUOTE_FIDELITY,
            f"quote is not a substring of the document "
            f"(quote={q_norm[:70]!r}, doc={len(d_norm)} chars)")

    # ---- V2 value presence: every number must be in the quote ---------------
    quote_nums = set(_numbers(cand.raw_quote))
    for num in _numbers(cand.value):
        if num not in quote_nums:
            return ValidationResult(
                False, V2_VALUE_PRESENCE,
                f"value contains {num!r} which does not appear in the quote "
                f"(quote numbers: {sorted(quote_nums)[:8]})")

    # ---- V3 date presence ---------------------------------------------------
    # Format-tolerant: the model returns ISO, the page writes "25 August 2026".
    # Both are normalised to a date before comparison. This is normalisation, NOT a
    # relaxation — an as_of that parses to no real date still fails.
    if cand.as_of:
        want = _to_date(str(cand.as_of))
        if want is None:
            return ValidationResult(False, V3_DATE_PRESENCE,
                                    f"as_of {cand.as_of!r} is not a parseable date")
        # Document metadata counts: the published date is usually in <head>, which
        # raw_text excludes by design. Without this, V3 refuses valid facts.
        meta = getattr(cand.document, "published_dates", "") or ""
        found = _dates_in(f"{cand.raw_quote} {doc_text} {meta}")
        if want not in found:
            return ValidationResult(
                False, V3_DATE_PRESENCE,
                f"as_of {want.isoformat()} appears in neither quote, body, nor "
                f"document metadata (dates found: {sorted(d.isoformat() for d in found)[:6]})")

    # ---- V8 tier refusal: only Tier 1 fact types ---------------------------
    if cand.fact_type in TIER2_FACT_TYPES:
        return ValidationResult(False, V8_TIER,
                                f"Tier 2 fact_type {cand.fact_type!r} is refused in v1")
    if cand.fact_type not in TIER1_FACT_TYPES:
        return ValidationResult(False, V8_TIER,
                                f"fact_type {cand.fact_type!r} is outside the Tier 1 contract")

    # ---- V10 fact-type cue: the quote must speak the fact_type's language ----
    # Found on the first real run: a balloting quote filed as possession_status passed
    # every other validator. Both are Tier 1, the value text is honest, and the label
    # was simply wrong. Cue vocabulary is corpus-derived and inspectable in
    # data/normalization/fact_type_cues.csv — not guessed in code.
    cue_res = _cue_check(cand.fact_type, cand.raw_quote)
    if cue_res is not None:
        return cue_res

    # ---- V7 no self-promotion: extraction may never mark an identity verified
    if cand.claims_verified_block is not None:
        return ValidationResult(
            False, V7_NO_SELF_PROMOTION,
            f"candidate claims verified status for {cand.claims_verified_block!r}; "
            "only promote_block_identities may do that")
    if cand.claims_place_id is not None:
        return ValidationResult(
            False, V7_NO_SELF_PROMOTION,
            f"candidate supplied place_id={cand.claims_place_id}; "
            "the LLM must never name a place")

    # ---- V5 cross-city guard ------------------------------------------------
    haystack = f"{cand.raw_quote} {cand.value} {cand.place_ref}"
    if DHA_VALLEY_FACT.search(haystack):
        return ValidationResult(False, V5_CROSS_CITY,
                                "DHA Valley is an Islamabad society; not a Lahore fact")
    if CROSS_CITY_FACT.search(haystack) and not re.search(r"DHA\s+Lahore", haystack, re.I):
        return ValidationResult(False, V5_CROSS_CITY,
                                "bare DHA Phase 1-4 is cross-city ambiguous; "
                                "the quote must name Lahore explicitly")

    # ---- V6 category routing: CCA is a category, never a place -------------
    # Checks the QUOTE too, not just value and place_ref. Found on the real run:
    # quote "DHA Phase 6 CCA-3 Files 4 Marla Affidavit: 600 Lacs" was accepted as a
    # residential rate for DHA Phase 6, when 600 Lacs is a CCA-3 COMMERCIAL rate.
    # Checking only the candidate's own fields missed it because CCA appeared in
    # neither of them.
    for field_name, blob in (("quote", cand.raw_quote), ("value", cand.value),
                             ("place_ref", cand.place_ref)):
        if CCA_FACT.search(blob or ""):
            return ValidationResult(
                False, V6_CATEGORY_ROUTING,
                f"CCA-* appears in the {field_name}; it is a commercial category and "
                "must route to measurement, not a residential place fact")

    # ---- V11 qualifier contract: qualifiers must come from the quote --------
    # A rate is only meaningful as (place, size, file_type, amount). v1 stored a bare
    # number, so two differently-qualified rates were indistinguishable. A qualifier
    # the quote supports MUST be supplied; one the quote does not support must be
    # left explicitly UNKNOWN. Inferring either would be fabrication.
    q_res = _qualifier_check(cand)
    if q_res is not None:
        return q_res

    # ---- V4 entity binding: WE resolve, never the model ---------------------
    res = resolver.resolve(cand.place_ref, document=cand.document)
    if res.outcome != RESOLVED:
        return ValidationResult(False, V4_ENTITY_BINDING,
                                f"place_ref {cand.place_ref!r} -> {res.outcome}: {res.reason}")

    # ---- V9 place corroboration: the QUOTE must support the PLACE -----------
    # Found on the first real extraction run. A candidate named 'Rahbar Sector-4'
    # with a quote reading 'DHA Phase 9 Town' passed V1-V8 and would have entered the
    # knowledge base fully sourced and dated — the project's core failure mode,
    # arriving through the proposer's place_ref instead of the resolver.
    if not _place_corroborated(cand, res.place, doc_text):
        return ValidationResult(
            False, V9_PLACE_CORROBORATION,
            f"quote does not corroborate {res.place.canonical_name}: no corroborating "
            f"mention within {CORROBORATION_WINDOW} chars of the quote "
            f"(place_ref={cand.place_ref!r})")
    return ValidationResult(True, "", "", place=res.place)


def persist_rejection(cand: Candidate, result: ValidationResult) -> Observation:
    """Rejections are kept forever, with the validator id. Never retried, never dropped."""
    return Observation.objects.create(
        observed=cand.place_ref,
        document=cand.document,
        occurrences=1,
        adjudication=Observation.ADJ_DROPPED,
        resolved_to=None,
        stage=result.validator,
        reason=f"{result.validator}: {result.reason}",
    )


def qualifier_status(cand: Candidate) -> str:
    """complete | partial | unknown — computed from the quote, never from the model."""
    from corpus.models import QualifierStatus
    if cand.fact_type != "rate":
        return QualifierStatus.COMPLETE
    has_size = cand.size_marla is not None
    has_ft = bool(cand.file_type)
    if has_size and has_ft:
        return QualifierStatus.COMPLETE
    if has_size or has_ft:
        return QualifierStatus.PARTIAL
    return QualifierStatus.UNKNOWN


# Group 2 MUST be a capturing group: with it optional, a quote carrying no money
# unit leaves group(2) undefined and indexing it raised IndexError.
_AMOUNT = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(?:(lacs?|lakhs?|crs?|crores?|pkr|rs)\b)?", re.I)
_SCALE = {"lac": 100000, "lacs": 100000, "lakh": 100000, "lakhs": 100000,
          "cr": 10000000, "crs": 10000000, "crore": 10000000, "crores": 10000000}


def amount_in_quote(quote: str):
    """Largest money figure in the quote, normalised to PKR. Deterministic arithmetic
    on a UNIT (lakh/crore), not a derived fact — it converts a stated unit, and V2 has
    already proven the number appears verbatim."""
    best = None
    for m in _AMOUNT.finditer(quote or ""):
        raw = m.group(1).replace(",", "")
        unit = (m.group(2) or "").strip().lower()
        if unit not in _SCALE:
            continue
        try:
            v = Decimal(raw) * int(_SCALE[unit])
        except (InvalidOperation, ValueError):
            continue
        if best is None or v > best:
            best = v
    return best


def persist_accepted(cand: Candidate, result: ValidationResult) -> Fact:
    """Write the fact. raw_quote is mandatory — it is the audit path back to the page."""
    as_of = None
    if cand.as_of:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d %B %Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                as_of = datetime.strptime(str(cand.as_of), fmt).date()
                break
            except ValueError:
                continue
    return Fact.objects.create(
        place=result.place,
        fact_type=cand.fact_type,
        value=cand.value,
        as_of=as_of,
        document=cand.document,
        raw_quote=cand.raw_quote,
        source=cand.document.source,
        channel=cand.document.channel,
        size_marla=(float(cand.size_marla) if cand.size_marla else None),
        file_type=(cand.file_type.lower() if cand.file_type else None),
        amount_pkr=amount_in_quote(cand.raw_quote),
        qualifier_status=qualifier_status(cand),
    )