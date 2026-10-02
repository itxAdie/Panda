"""Entity resolver — the load-bearing component of Milestone 1.

MANDATORY STAGE ORDER
=====================
    1. DROPS              refuse by policy BEFORE anything can bind
    2. MEASUREMENT        size/currency/category — never a place
    3. COMPOSITIONAL      parse society slot AND phase slot
    4. EXISTENCE          validate the parsed entity actually exists
    5. ALIAS              irregular forms only
    6. CANONICAL          last resort, still after drops

Why the order is not negotiable
-------------------------------
`Place.canonical_name` for the Lahore entity ph_dha_2 is literally "DHA Phase 2".
An entity with the same name also exists in Islamabad. If canonical matching runs
before drops, the bare form binds to Lahore and silently absorbs Islamabad data.

Observed cost: 206 occurrences, 7.6 points of false resolution, presenting as a
large improvement. See data/normalization/rerun-results.md.

Coverage metrics are NOT readable from this module. By design, the resolver has no
path by which a rate could influence a decision (R6, structural enforcement).
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from corpus import DROPPED, MEASUREMENT, RESOLVED, UNRESOLVED
from corpus.models import Alias, BlockIdentity, Drop, Measurement, Place

# --- stage names, recorded on every Observation ---------------------------

S_DROP = "1-drop"
S_MEASURE = "2-measurement"
S_COMPOSE = "3-compositional"
S_EXIST = "4-existence"
S_ALIAS = "5-alias"
S_CANON = "6-canonical"
S_BLOCKID = "3b-block-identity"

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
         "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13}

# Society slot. DHA and Defence are the same authority.
_SOCIETY = r"(?:DHA|Defence)(?:\s+Lahore)?|Bahria(?:\s+Town)?|LDA\s*City|Lake\s*City|Askari\s*10|Gulberg(?:\s*III)?"

# Society -> Society slug. DHA/Defence map to the DHA society.
_SOCIETY_SLUG = {
    "dha": "soc_dha_lahore", "defence": "soc_dha_lahore", "dha lahore": "soc_dha_lahore",
    "bahria": "soc_bahria_lahore", "bahria town": "soc_bahria_lahore",
    "lda city": "soc_lda_city", "lake city": "soc_lake_city",
    "askari 10": "soc_askari_10", "gulberg": "soc_gulberg_iii", "gulberg iii": "soc_gulberg_iii",
}

# Society alone, optionally with a named sub-part: 'Bahria Town', 'LDA City',
# 'Bahria Town Sector C', 'LDA City N Block'.
_SOCIETY_SOLO = re.compile(
    rf"^({_SOCIETY})(?:\s+(?:(?:Sector|Sec|Block)\.?\s*-?\s*[A-Z0-9]{{1,3}}|[A-Z]{{1,2}}\s+Block))?$", re.I)
# Phase slot. Handles: 7 / 07 / 6 / VI / 10 / Ph-9 / Phase-9 / Phase9 / Phase 9
_PHASE_NUM = r"(\d{1,2}|VI{0,3}|IX|XI{0,3})"
_PHASE_TAIL = r"(?:\s+(Prism|Town|Extension|Rahbar(?:\s*Sec-?4)?))?"

_PHASE_COMPOUND = re.compile(
    rf"^(?:(?:Ph(?:ase)?\.?\s*-?\s*)?{_PHASE_NUM}){_PHASE_TAIL}$", re.I)
# The phase designator (Phase/Ph) is REQUIRED after a society token.
# It was optional, which let 'DHA V' (truncated 'DHA Valley', Islamabad) parse as
# 'DHA Phase 5' and 'DHA Valley Phase 7' bind to Lahore Phase 7. Both false.
_SOCIETY_PHASE = re.compile(
    rf"^({_SOCIETY})(?:\s+(?:Lahore\s+)?Ph(?:ase)?\.?\s*-?\s*"
    rf"{_PHASE_NUM}{_PHASE_TAIL})$", re.I)
_PHASE_LEADING = re.compile(
    rf"^(?:Ph(?:ase)?\.?\s*-?\s*){_PHASE_NUM}{_PHASE_TAIL}$", re.I)

# Phase-qualified sub-division: 'DHA Phase 9 Prism Block Q', 'DHA Phase 7 Sector U'.
# This is the ONLY form that binds to a BlockIdentity. A bare 'Block Q' never does —
# 23 of 27 identifiers repeat across phases within one source, so the phase qualifier
# is what makes the reference meaningful.
_BLOCK_QUALIFIED = re.compile(
    rf"^(?:{_SOCIETY})\s+(?:Lahore\s+)?Ph(?:ase)?\.?\s*-?\s*{_PHASE_NUM}{_PHASE_TAIL}"
    rf"\s+(?:Block|Sector)\.?\s*-?\s*([A-Z0-9]{{1,3}})$", re.I)

# Bare sector/block letters: a known resolution CEILING, not a bug.
# Sector A maps to Askari/Bahria/DHA even within one document. Never resolved.
_SECTOR_OR_BLOCK = re.compile(r"^\s*(?:Sector|Sec|Block)\.?\s*-?\s*[A-Z0-9]{1,3}\s*$", re.I)

# Cross-city: DHA Phases 1-4 exist in BOTH Lahore and Islamabad.
# The bare form must never bind to Lahore — in ANY spelling.
#   DHA Phase 2 | DHA Ph-2 | DHA Phase-2 | DHA 2 | DHA P2 | Defence Phase 2
# An earlier guard matched only the spelled-out form, so 'DHA Ph-1' and 'DHA 1'
# resolved to Lahore. Normalise the designator first, then range-check.
_DESIG = r"(?:Ph(?:ase)?\.?|P)\s*-?\s*"
# NOTE: 'Lahore' is deliberately NOT optional here. The qualified form
# 'DHA Lahore Phase 2' IS resolvable and must resolve; only the BARE form is
# cross-city ambiguous. Allowing 'Lahore' here swallowed the good cases.
CROSS_CITY = re.compile(rf"^(?:DHA|Defence)\s+(?:{_DESIG}|){_PHASE_NUM}$", re.I)

# 'DHA Valley' is an Islamabad society. Its 'Phase 7' is not Lahore's Phase 7.
DHA_VALLEY = re.compile(r"^DHA\s+Valley\b", re.I)

# Bare 'Gulberg' names a district containing Gulberg I/II/III/IV. Only III is an
# entity. Observed context: 'Gulberg Greens', 'Gulberg Residencia' — not III.
BARE_GULBERG = re.compile(r"^Gulberg$", re.I)

# Commercial categories. Measured, never places.
_CCA = re.compile(r"^\s*CCA-?\s*([13])\b", re.I)


def _norm(s: str) -> str:
    """Aggressive normalisation used for drop/alias lookup only."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _norm_compact(s: str) -> str:
    """Loose normalisation used for compositional parsing (keeps separators)."""
    return re.sub(r"\s+", " ", (s or "").replace("–", "-").replace("—", "-")).strip()


def _num(tok: str) -> Optional[int]:
    tok = tok.strip()
    if tok.isdigit():
        n = int(tok)
        return n if 1 <= n <= 13 else None
    return ROMAN.get(tok.upper())


@dataclass
class Resolution:
    outcome: str
    stage: str = ""
    place: Optional[Place] = None
    reason: str = ""
    parsed: dict = field(default_factory=dict)

    @property
    def is_resolved(self) -> bool:
        return self.outcome == RESOLVED


class Resolver:
    """Stateless resolver over the loaded corpus map.

    No coverage metric is accepted, returned, or consulted. The resolver sees only:
    the observed string, its document context, and the entity map.
    """

    def __init__(self):
        self._drops = {}
        for d in Drop.objects.all():
            self._drops[_norm(d.alias_text)] = d
        self._measure = {}
        for m in Measurement.objects.all():
            self._measure[_norm(m.source_form)] = m
        self._aliases = {}
        for a in Alias.objects.filter(confirmed=True).select_related("place"):
            self._aliases.setdefault(_norm(a.alias_text), a.place)
        self._canonical = {}
        for p in Place.objects.all():
            self._canonical.setdefault(_norm(p.canonical_name), p)

    # -- 1. DROPS ---------------------------------------------------------

    def _stage_drops(self, text: str, nkey: str) -> Optional[Resolution]:
        # Cross-city guard runs FIRST, before any binding path. DHA Phase 1-4
        # exist in both Lahore and Islamabad; the bare form binds to neither.
        if DHA_VALLEY.match(text):
            return Resolution(DROPPED, S_DROP,
                              reason="DHA Valley is an Islamabad society, not DHA Lahore")
        if CROSS_CITY.match(text):
            n = _num(CROSS_CITY.match(text).group(1))
            if n is not None and 1 <= n <= 4:
                return Resolution(DROPPED, S_DROP,
                                  reason="cross-city: DHA Phase 1-4 exist in both Lahore and Islamabad")
        if BARE_GULBERG.match(text):
            return Resolution(UNRESOLVED, S_EXIST,
                              reason="bare 'Gulberg' is a district; only Gulberg III is an entity")
        hit = self._drops.get(nkey)
        if hit is None:
            # also try a hyphen/space-insensitive form
            hit = self._drops.get(re.sub(r"\s+", "", nkey))
        if hit is not None:
            return Resolution(DROPPED, S_DROP, reason=f"{hit.evidence_state}: {hit.reason}")
        return None

    # -- 2. MEASUREMENT ---------------------------------------------------

    def _stage_measurement(self, text: str, nkey: str) -> Optional[Resolution]:
        m = self._measure.get(nkey)
        if m is None:
            m = self._measure.get(re.sub(r"\s+", "", nkey))
        if m is not None:
            return Resolution(MEASUREMENT, S_MEASURE,
                              reason=f"{m.dimension}:{m.canonical_value}")
        cca = _CCA.match(text)
        if cca:
            return Resolution(MEASUREMENT, S_MEASURE,
                              reason=f"category:cca{cca.group(1)}",
                              parsed={"dimension": "category", "value": f"cca{cca.group(1)}"})
        return None

    # -- 3. COMPOSITIONAL -------------------------------------------------

    def _parse(self, text: str):
        """Return (society, phase_number, tail) or None.

        A phase WITHOUT a society slot is deliberately NOT bindable. 'Phase 7' alone
        is society-ambiguous — DHA Phases exist in Lahore and Islamabad — so it must
        stay a miss rather than be attributed to DHA by default. Irregular society-less
        forms that ARE unambiguous ('Phase X', 'Phase 11 (Rahbar)') are handled by the
        alias stage, which runs after drops.
        """
        m = _SOCIETY_PHASE.match(text)
        if m:
            soc_raw, phase_raw, tail = m.group(1), m.group(2), m.group(3)
            sm = re.match(_SOCIETY, soc_raw, re.I)
            soc = _norm(sm.group(0)) if sm else None
            n = _num(phase_raw)
            if n is None:
                return None
            return soc, n, (tail or "").title()

        # Society slot alone: 'Bahria Town', 'LDA City', optionally with a sub-part.
        # Returns phase=None to signal "society known, no phase".
        m = _SOCIETY_SOLO.match(text)
        if m:
            sm = re.match(_SOCIETY, m.group(1), re.I)
            soc = _norm(sm.group(0)) if sm else None
            return soc, None, ""
        return None

    def _block_identity(self, text: str) -> Optional[Resolution]:
        """Resolve a phase-qualified sub-division to a flat BlockIdentity.

        Asserts no hierarchy. The phase is a reference, not a parent assertion about
        geography; the label ('Block' vs 'Sector') is recorded but never interpreted.
        """
        m = _BLOCK_QUALIFIED.match(text)
        if not m:
            return None
        num = _num(m.group(1))
        if num is None:
            return None
        tail = (m.group(2) or "").title()
        letter = m.group(3).upper()
        phase = Place.objects.filter(
            level="phase", canonical_name__iexact=f"DHA Phase {num}" + (f" {tail}" if tail else "")
        ).first()
        if phase is None:
            return None
        bi = BlockIdentity.objects.filter(phase=phase, letter=letter).first()
        if bi is None:
            return None
        note = "single-source" if bi.single_source else f"{bi.source_count} sources"
        if bi.label_conflict:
            note += f"; label conflict ({bi.labels_observed})"
        return Resolution(RESOLVED, S_BLOCKID, place=phase,
                          reason=f"block identity {phase.canonical_name} [{letter}] ({note})",
                          parsed={"phase": num, "tail": tail, "letter": letter,
                                  "single_source": bi.single_source, "verified": bi.verified})

    def _place_for(self, society_hint: Optional[str], n: int, tail: str) -> Optional[Place]:
        candidates = []
        base = f"ph_dha_{n}"
        if tail == "Prism":
            candidates = [f"ph_dha_{n}_prism", base]
        elif tail == "Town":
            candidates = [f"ph_dha_{n}_town", base]
        elif tail == "Extension":
            candidates = [f"ph_dha_{n}_ext", base]
        else:
            candidates = [base]
        for cid in candidates:
            p = Place.objects.filter(level__in=("phase", "society")).filter(
                canonical_name__iexact=f"DHA Phase {n}" + (f" {tail}" if tail else "")
            ).first() if cid.startswith("ph_dha") else None
            if p is not None:
                return p
        # fall back to canonical-name lookup restricted to phase-level places
        name = f"DHA Phase {n}" + (f" {tail}" if tail else "")
        return Place.objects.filter(level="phase", canonical_name__iexact=name).first()

    # -- public API -------------------------------------------------------

    def resolve(self, observed: str, document=None) -> Resolution:
        text = _norm_compact(observed)
        nkey = _norm(text)
        if not text:
            return Resolution(UNRESOLVED, S_COMPOSE, reason="empty")

        # 1. drops
        r = self._stage_drops(text, nkey)
        if r:
            return r

        # sector/block letters: documented ceiling, never resolved
        if _SECTOR_OR_BLOCK.match(text):
            return Resolution(UNRESOLVED, S_EXIST,
                              reason="sector-letter ceiling: multi-society even within one document")

        # 2. measurement / category
        r = self._stage_measurement(text, nkey)
        if r:
            return r

        # 2b. phase-qualified sub-division -> flat BlockIdentity.
        # Ahead of the compositional parse: 'DHA Phase 9 Prism Block Q' would otherwise
        # match the phase parse and lose the letter.
        r = self._block_identity(text)
        if r is not None:
            return r

        # 3. compositional
        parsed = self._parse(text)
        if parsed:
            soc, n, tail = parsed
            # 4. existence
            if n is None:
                # Society slot only — bind the society-level Place.
                slug = _SOCIETY_SLUG.get(soc or "")
                place = Place.objects.filter(
                    society__slug=slug, level="society").first() if slug else None
                if place is None:
                    return Resolution(UNRESOLVED, S_EXIST,
                                      reason=f"society '{soc}' has no society-level entity",
                                      parsed={"society": soc})
                return Resolution(RESOLVED, S_EXIST, place=place,
                                  reason=f"society slot -> {place.canonical_name}",
                                  parsed={"society": soc})
            place = self._place_for(soc, n, tail)
            if place is not None:
                return Resolution(RESOLVED, S_EXIST, place=place,
                                  reason=f"compositional {soc or 'DHA'} phase {n} {tail}".strip(),
                                  parsed={"society": soc, "phase": n, "tail": tail})
            return Resolution(UNRESOLVED, S_EXIST,
                              reason=f"compositional parse OK but no entity for phase {n} {tail}".strip(),
                              parsed={"society": soc, "phase": n, "tail": tail})

        # 5. alias
        p = self._aliases.get(nkey)
        if p is not None:
            return Resolution(RESOLVED, S_ALIAS, place=p, reason="alias")

        # 6. canonical (still after drops)
        p = self._canonical.get(nkey)
        if p is not None:
            return Resolution(RESOLVED, S_CANON, place=p, reason="canonical name")

        return Resolution(UNRESOLVED, S_ALIAS, reason="no parse, no alias, no canonical")

    def resolve_many(self, strings, document=None):
        return [(s, self.resolve(s, document=document)) for s in strings]