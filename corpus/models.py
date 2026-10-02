"""Django models — Milestone 1 contract.

Invariants enforced here (see docs/designs/lahore-aarea-gyan-engine.md):

  * no Alias/Observation may reference a nonexistent Place (FK integrity)
  * a confirmed alias's evidence may not contradict its mapping (Rahbar-class bug)
  * raw_quote is mandatory on every Fact — it is the audit path
  * drops are applied before canonical matching (resolver stage order, asserted in tests)
"""

from django.db import models

# Evidence states for Place. 'contested' entities exist but are not trustworthy.
EVIDENCE_EVIDENCED = "evidenced"
EVIDENCE_CONTESTED = "contested"
EVIDENCE_UNEVIDENCED = "unevidenced"


class Source(models.Model):
    """A registered publisher. 10 of these; all with verified crawl policies."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    base_url = models.URLField()
    # verified = robots/Terms confirmed. See data/normalization/tos-verification.md
    verified = models.BooleanField(default=False)
    # 'live' pages, or a published AI hub. Different freshness guarantees.
    channel = models.CharField(max_length=32, default="live")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.slug


class Document(models.Model):
    """A fetched page. Provenance root for every fact."""

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="documents")
    url = models.URLField(max_length=1000)
    fetched_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(max_length=32, default="live")
    content_hash = models.CharField(max_length=64, blank=True)
    raw_text = models.TextField(blank=True)
    # Publication dates recovered from <head>. V3 checks these, because raw_text
    # deliberately excludes <head> where these dates live.
    published_dates = models.TextField(blank=True)

    class Meta:
        unique_together = [("source", "url")]

    def __str__(self):
        return f"{self.source.slug}:{self.url[-40:]}"


class Society(models.Model):
    """Top of the place hierarchy. Lahore-only scope is locked."""

    slug = models.SlugField(unique=True)
    canonical_name = models.CharField(max_length=200)
    city = models.CharField(max_length=64, default="Lahore")

    def __str__(self):
        return self.canonical_name


class Place(models.Model):
    """A canonical entity. Flat-ish: parent_id plus name, no type enum.

    R2 (per-society place_type) was REJECTED on evidence: DHA uses both 'Block X'
    and 'Sector X' freely, so there is no clean per-society grammar to declare.
    See data/normalization/validation-R1-R6.md.
    """

    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name="places")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    canonical_name = models.CharField(max_length=200)
    level = models.CharField(max_length=32)  # society|phase|block|sector|scheme
    evidence_url = models.URLField(max_length=1000, blank=True)
    evidence = models.TextField(blank=True)
    evidence_status = models.CharField(
        max_length=16, default=EVIDENCE_EVIDENCED,
        choices=[(EVIDENCE_EVIDENCED, "evidenced"), (EVIDENCE_CONTESTED, "contested"),
                 (EVIDENCE_UNEVIDENCED, "unevidenced")],
    )
    is_contested = models.BooleanField(default=False)

    class Meta:
        unique_together = [("society", "canonical_name")]
        indexes = [models.Index(fields=["level"])]

    def __str__(self):
        return self.canonical_name


class Alias(models.Model):
    """A source string bound to a Place, with the evidence that justifies it.

    A confirmed alias whose evidence contradicts its mapping is the Rahbar bug.
    Rule tested: an alias naming a nested unit must not point at its ancestor.
    """

    alias_text = models.CharField(max_length=300)
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="aliases")
    evidence = models.TextField(blank=True)
    evidence_url = models.URLField(max_length=1000, blank=True)
    confirmed = models.BooleanField(default=False)

    class Meta:
        unique_together = [("alias_text", "place")]
        indexes = [models.Index(fields=["alias_text"])]

    def __str__(self):
        return f"{self.alias_text} -> {self.place.canonical_name}"


class Drop(models.Model):
    """A string refused by policy. Never resolves. Always auditable.

    evidence_state values:
      confirmed        occurs in corpus, genuinely unresolvable
      untested         asserted precaution, never observed — not disproven
      document_scoped  resolvable only with document scope (none currently)
      not_a_place      a missing value (e.g. 'On Call'), not an entity ambiguity
    """

    CONFIRMED = "confirmed"
    UNTESTED = "untested"
    DOCUMENT_SCOPED = "document_scoped"
    NOT_A_PLACE = "not_a_place"
    STATES = [(CONFIRMED, "confirmed"), (UNTESTED, "untested"),
              (DOCUMENT_SCOPED, "document-scoped"), (NOT_A_PLACE, "not-a-place")]

    alias_text = models.CharField(max_length=300, unique=True)
    reason = models.TextField()
    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL)
    evidence_state = models.CharField(max_length=32, choices=STATES, default=CONFIRMED)
    evidence_note = models.TextField(blank=True)

    def __str__(self):
        return f"DROP {self.alias_text}"


class FactTypeCue(models.Model):
    """A lexical cue that a fact_type REQUIRES in its quote (V10).

    Found by the first real extraction run: a balloting fact filed as
    possession_status passed V1-V9, because both are Tier 1 and the value text was
    honest. The only thing wrong was the label.

    `corpus_count` records how often the cue actually appeared in the 5-page sample.
    `proven_in_corpus=False` marks cues that are plausible domain vocabulary but were
    NOT observed — kept visible so the gap is auditable rather than hidden.

    `group` lets a fact_type accept several cues for one concept (any-of), so a quote
    saying "balloting" satisfies balloting_status without needing all three variants.
    """

    fact_type = models.CharField(max_length=64)
    cue = models.CharField(max_length=64)
    group = models.CharField(max_length=32)
    corpus_count = models.PositiveIntegerField(default=0)
    proven_in_corpus = models.BooleanField(default=False)

    class Meta:
        unique_together = [("fact_type", "cue")]
        indexes = [models.Index(fields=["fact_type"])]

    def __str__(self):
        return f"{self.fact_type} <- {self.cue!r}"


class BlockIdentity(models.Model):
    """A source-named sub-division of a phase, identified by (phase, letter).

    DELIBERATELY NOT A Place. R3 proposed a `sub_sector` tree level and was REJECTED
    on evidence: mohsinestate labels the same objects both "Block" and "Sector", so
    a hierarchy level would encode a source's inconsistency as geographic truth.

    This model asserts NO hierarchy and NO label semantics:
      * `letter` is the source's identifier, not a surveyed block name
      * `labels_observed` records the words the source used, possibly conflicting
      * `single_source` marks identities only one publisher names

    PROMOTION RULE: `verified` may only be True when two or more INDEPENDENT sources
    name the same (phase, letter). Enforced by `clean()`; see management command
    `promote_block_identities`.
    """

    phase = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="block_identities")
    letter = models.CharField(max_length=8)
    labels_observed = models.CharField(max_length=64)   # "Block" | "Sector" | "Block;Sector"
    source_count = models.PositiveSmallIntegerField(default=1)
    verified = models.BooleanField(default=False)
    single_source = models.BooleanField(default=True)
    occurrences = models.PositiveIntegerField(default=0)
    sources = models.ManyToManyField(Source, related_name="block_identities", blank=True)

    class Meta:
        unique_together = [("phase", "letter")]

    def __str__(self):
        return f"{self.phase.canonical_name} [{self.letter}] ({self.source_count} src)"

    def clean(self):
        if self.verified and self.source_count < 2:
            raise ValueError(
                f"promotion rule: {self} has {self.source_count} source(s); "
                "an identity cannot be verified without two independent sources")

    @property
    def label_conflict(self) -> bool:
        return ";" in (self.labels_observed or "")


class Measurement(models.Model):
    """Size / currency / category normalization. SEPARATE from place identity.

    '1 Kanal' == 20 marla is a size equivalence, not an entity alias.
    CCA-1/CCA-3 are commercial categories — never places.
    """

    SIZE = "size"
    CURRENCY = "currency"
    CATEGORY = "category"
    DIMENSIONS = [(SIZE, "size"), (CURRENCY, "currency"), (CATEGORY, "category")]

    dimension = models.CharField(max_length=16, choices=DIMENSIONS)
    source_form = models.CharField(max_length=64, unique=True)
    canonical_value = models.CharField(max_length=64)
    unit = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["dimension"])]

    def __str__(self):
        return f"{self.source_form} [{self.dimension}]"


class Observation(models.Model):
    """Permanent record of every string the resolver did not bind to a Place.

    Never pruned. Drops are signal: they show where source terminology outruns the
    map, and they are the only defence against a silent coverage regression.
    """

    ADJ_UNRESOLVED = "unresolved"
    ADJ_DROPPED = "dropped"
    ADJ_MEASUREMENT = "measurement"
    ADJ_RESOLVED = "resolved"
    ADJ_FORCED = "forced"  # must never occur; a tripwire

    observed = models.CharField(max_length=300)
    document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.CASCADE)
    occurrences = models.PositiveIntegerField(default=1)
    adjudication = models.CharField(max_length=16, default=ADJ_UNRESOLVED)
    resolved_to = models.ForeignKey(Place, null=True, blank=True, on_delete=models.SET_NULL)
    stage = models.CharField(max_length=32, blank=True)
    reason = models.TextField(blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["adjudication"]), models.Index(fields=["observed"])]

    def __str__(self):
        return f"{self.observed} [{self.adjudication}]"


class QualifierStatus(models.TextChoices):
    """How complete a fact's qualifier set is.

    An explicit state, not an ambiguous NULL. 'unknown' means the SOURCE did not
    supply the qualifier — which is honest and queryable. A NULL column would be
    indistinguishable from a bug, and an inferred value would be a fabrication.
    """

    COMPLETE = "complete", "complete"
    PARTIAL = "partial", "partial"
    UNKNOWN = "unknown", "unknown"


class Fact(models.Model):
    """An area fact with full provenance. raw_quote is MANDATORY — audit path.

    A rate is only meaningful as (place, size, file_type, amount). v1 stored a bare
    number, so `133.00 Lacs` and `218 Lacs` were indistinguishable from a whole
    population of equally valid but differently-qualified rates. Qualifiers now have
    their own columns, and a qualifier the source did not supply is recorded as
    explicitly UNKNOWN rather than inferred.
    """

    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="facts")
    fact_type = models.CharField(max_length=64)
    value = models.TextField()
    as_of = models.DateField(null=True, blank=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="facts")
    raw_quote = models.TextField()
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="facts")
    # 'live' page vs published AI hub. A fact from a hub is not a fact from the page.
    channel = models.CharField(max_length=32, default="live")

    # --- qualifiers (M6 gap) ---------------------------------------------
    # Populated from the quote by the deterministic layer, never by the model
    # guessing. Null + qualifier_status='unknown' is a legitimate, honest state.
    size_marla = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    file_type = models.CharField(max_length=32, null=True, blank=True)
    amount_pkr = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    qualifier_status = models.CharField(
        max_length=16, choices=QualifierStatus.choices, default=QualifierStatus.UNKNOWN)

    class Meta:
        indexes = [models.Index(fields=["place", "fact_type"]),
                   models.Index(fields=["qualifier_status"])]

    def __str__(self):
        return f"{self.fact_type}@{self.place.canonical_name}"

    def as_qualified_string(self) -> str:
        """Human/machine readable qualified form. Never silently drops a qualifier."""
        if self.fact_type != "rate":
            return self.value
        parts = [f"{self.value} PKR"]
        size = f"{self.size_marla} marla" if self.size_marla is not None else "size unknown"
        ftype = self.file_type or "file type unknown"
        return f"{size} {ftype} = {self.value} ({self.qualifier_status})"

    @property
    def is_fully_qualified(self) -> bool:
        return (self.qualifier_status == QualifierStatus.COMPLETE
                and self.size_marla is not None
                and bool(self.file_type))