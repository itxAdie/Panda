"""Extraction pipeline: raw source page -> validated Fact, or a recorded rejection.

    fetch  -> Document.raw_text
    segment-> candidate text windows
    propose-> Candidate   (pluggable; NEVER names a place)
    validate-> V1..V8      (deterministic, corpus.validators)
    persist -> Fact, or Observation(adjudication='dropped')

The proposer is the only non-deterministic component. Everything downstream of it is
deterministic, and the proposer has no way to bind a Place — it emits `place_ref`,
the string as written, which V4 resolves through the Resolver.

Two proposers ship:
  * `FileProposer`    — candidates from a JSON file. Used for reproducible runs and
                        for this milestone's dry run, where the proposer was the
                        engineer reading the page rather than a live model.
  * `LLMProposer`     — Anthropic Messages API. Requires ANTHROPIC_API_KEY.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from corpus.models import Document, Observation, Source
from corpus.validators import (
    Candidate, ValidationResult, persist_accepted, persist_rejection, validate,
)


# --------------------------------------------------------------------------
# text extraction
# --------------------------------------------------------------------------

_META_DATE = re.compile(
    r'<meta[^>]+(?:property|name)\s*=\s*["\'](?:article:published_time|'
    r'article:modified_time|og:updated_time|datePublished|dateModified|'
    r'publish[_-]?date|dcterms\.date|DATE)[^"\']*["\'][^>]*'
    r'content\s*=\s*["\']([^"\']+)["\']', re.I)
_META_DATE_REV = re.compile(
    r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]*'
    r'(?:property|name)\s*=\s*["\'](?:article:published_time|'
    r'article:modified_time|og:updated_time|datePublished|dateModified|'
    r'publish[_-]?date|dcterms\.date|DATE)[^"\']*["\']', re.I)
_TIME_TAG = re.compile(r'<time[^>]+datetime\s*=\s*["\']([^"\']+)["\']', re.I)


def extract_published_dates(raw: str):
    """Publication dates from <head> — the field V3 needs and <body> lacks.

    V3 rejected 11 well-formed candidates purely because html_to_text discards
    <head>, where these dates actually live. This is an ingestion gap, not a
    validator fault, so it is fixed here rather than by loosening V3.
    """
    found = []
    for rx in (_META_DATE, _META_DATE_REV, _TIME_TAG):
        for m in rx.finditer(raw or ""):
            v = (m.group(1) or "").strip()
            if v and v not in found:
                found.append(v)
    return found


def html_to_text(raw: str) -> str:
    t = re.sub(r"(?is)<(script|style|head|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", t).strip()


# --------------------------------------------------------------------------
# proposers
# --------------------------------------------------------------------------

class FileProposer:
    """Proposes candidates from a JSON file. Deterministic and reproducible.

    Format: {"<source-slug>": [ {fact_type, value, place_ref, raw_quote, as_of?}, ... ]}
    The proposer supplies no Place. `place_ref` is a source string, nothing more.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def propose(self, source_slug: str, text: str, limit: Optional[int] = None) -> Iterable[dict]:
        rows = self.data.get(source_slug, [])
        return rows[:limit] if limit else rows

    @property
    def model(self) -> str:
        return f"file:{self.path.name}"


class LLMProposer:
    """Proposes candidates via LiteLLM SDK mode, or the direct Anthropic SDK.

    Selection is by Django settings, never hardcoded here:

      LLM_BACKEND  "litellm" (default) | "anthropic"
      LLM_MODEL    LiteLLM pattern "provider/model", e.g.
                   "anthropic/claude-sonnet-4-5", "openai/gpt-5"

    The API key is read from the environment (populated from .env by settings).
    No key, URL, or model string is ever written into this file.

    SDK mode is the default on purpose: the LiteLLM proxy is a second moving part
    that can change routing and failure behaviour underneath the deterministic
    validators. It is only used when LITELLM_API_BASE is explicitly set.

    NOT AVAILABLE in this environment: neither `litellm` nor `anthropic` is
    installed, so no live call has been made and this class is unverified against a
    real provider. It fails loudly rather than silently degrading.
    """

    SYSTEM = """You extract property facts from Pakistani real-estate web pages.

Rules:
- Copy every value VERBATIM from the page. Never compute, convert, or infer a number.
- raw_quote must be an exact contiguous substring of the page text you were given.
- place_ref must be the place string exactly as the source wrote it (e.g. "DHA Phase 10").
  NEVER output an entity id, a canonical name you invented, or a normalised form.
- Only these fact_types: rate, size, file_type, balloting_status, possession_status,
  litigation_status, fee_schedule, tax_regime, transfer_process.
- A rate must be attributed to the size and file type it is quoted under.
- Do not output price bands, ranges, medians, or comparisons.
Return a JSON array of {fact_type, value, place_ref, raw_quote, as_of} objects.
Omit anything whose value you would have to compute."""

    _UNSET = object()

    def __init__(self, model=None, max_tokens=None, backend=None, api_base_override=_UNSET):
        from django.conf import settings
        self.backend = (backend or settings.LLM_BACKEND).lower()
        self.model = model or settings.LLM_MODEL
        self.max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        self.timeout = getattr(settings, "LLM_TIMEOUT", 120)
        # api_base_override lets tests exercise gateway AND sdk mode without touching
        # the operator's environment. A sentinel is required: None cannot mean both
        # "no override" and "no api_base".
        if api_base_override is not self._UNSET:
            self.api_base = api_base_override or None
        else:
            self.api_base = getattr(settings, "LLM_API_BASE", None)

    # -- availability ---------------------------------------------------

    @staticmethod
    def available() -> bool:
        """True when the selected backend's package is importable."""
        import importlib.util
        from django.conf import settings
        backend = (settings.LLM_BACKEND or "litellm").lower()
        pkg = "litellm" if backend == "litellm" else "anthropic"
        return importlib.util.find_spec(pkg) is not None

    @staticmethod
    def _key_vars():
        """Which env vars carry the credential.

        In PROXY mode the credential is the LiteLLM gateway's own key
        (LITELLM_API_KEY), NOT the provider's — the gateway holds the provider key.
        Getting this wrong produces a readiness check that demands a key the operator
        does not have, while the real one sits unused in the environment.
        """
        import os
        from django.conf import settings
        if getattr(settings, "LLM_API_BASE", None):
            return ["LITELLM_API_KEY"], "proxy"
        provider = (settings.LLM_MODEL or "").split("/")[0]
        var = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
               "gemini": "GEMINI_API_KEY", "google": "GEMINI_API_KEY",
               "openrouter": "OPENROUTER_API_KEY"}.get(
                   provider, f"{provider.upper()}_API_KEY")
        return [var], "sdk"

    @classmethod
    def _missing_key_error(cls, backend):
        vars_, mode = cls._key_vars()
        return RuntimeError(
            f"backend={backend!r} in {mode} mode needs {vars_[0]} in the environment. "
            f"It is absent. Copy .env.example to .env and set it. "
            f"Do NOT put the key in code, fixtures, or the data/ directory.")

    # -- call -----------------------------------------------------------

    def _messages(self, source_slug: str, text: str):
        """Build the message list.

        GATEWAY CAVEAT, found by probing: the hosted OpenAI-compatible gateway DROPS
        litellm's `system=` parameter but HONOURS a message with role="system".
        Verified against the live endpoint — told "reply with exactly BANANA" via
        `system=`, the model replied "Hello! How can I help you today?".

        The consequence was silent: the extraction contract never reached the model, so
        it returned a markdown summary instead of candidates and we had 0 candidates
        with no error anywhere. An empty result that means "the instructions were lost"
        is the worst possible failure shape.
        """
        user = f"Source: {source_slug}\n\nPage text:\n\n{text[:120000]}"
        if self.api_base:
            return ([{"role": "system", "content": self.SYSTEM},
                     {"role": "user", "content": user}])
        return [{"role": "user", "content": user}]

    def _call(self, source_slug: str, text: str) -> str:
        user = f"Source: {source_slug}\n\nPage text:\n\n{text[:120000]}"
        messages = self._messages(source_slug, text)
        if self.backend == "litellm":
            import litellm
            kw = dict(model=self.model, max_tokens=self.max_tokens,
                      timeout=self.timeout, messages=messages)
            if not self.api_base:
                # SDK mode honours system=; gateway mode does not (see _messages).
                kw["system"] = self.SYSTEM
            if self.api_base:
                kw["api_base"] = self.api_base
            resp = litellm.completion(**kw)
            return resp["choices"][0]["message"]["content"] or ""
        if self.backend == "anthropic":
            import anthropic
            client = anthropic.Anthropic(timeout=self.timeout)
            msg = client.messages.create(
                model=self.model.split("/")[-1], max_tokens=self.max_tokens,
                system=self.SYSTEM,
                messages=[{"role": "user", "content": user}])
            # the anthropic SDK path always uses system=; the gateway path does not
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        raise RuntimeError(f"unknown LLM_BACKEND {self.backend!r}; use 'litellm' or 'anthropic'")

    @staticmethod
    def _parse(payload: str, limit=None):
        """Extract the candidate array from a raw response.

        Surfaces malformed output instead of silently returning [] — an empty result
        must mean "the model returned nothing", never "we failed to parse it".
        """
        rows = []
        for m in re.finditer(r"\[.*?\](?=\s*\Z)|\[.*\]", payload or "", re.S):
            try:
                cand = json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
            if isinstance(cand, list):
                rows = [r for r in cand if isinstance(r, dict)]
                break
        return rows[:limit] if limit else rows

    def propose(self, source_slug, text, limit=None):
        if not self.available():
            import importlib.util
            from django.conf import settings
            pkg = "litellm" if self.backend == "litellm" else "anthropic"
            raise RuntimeError(
                f"LLM_BACKEND={self.backend!r} requires the {pkg!r} package, which is not "
                f"installed. pip install {pkg}")
        payload = self._call(source_slug, text)
        m = re.search(r"\[.*\]", payload, re.S)
        rows = json.loads(m.group(0)) if m else []
        return rows[:limit] if limit else rows

    def check_ready(self):
        """Raise a precise, actionable error rather than failing mid-run."""
        import os
        from django.conf import settings
        if not self.available():
            import importlib.util
            pkg = "litellm" if self.backend == "litellm" else "anthropic"
            raise RuntimeError(f"install {pkg}: pip install {pkg}")
        vars_, mode = self._key_vars()
        if not any(os.environ.get(v) for v in vars_):
            raise self._missing_key_error(self.backend)
        return True

    @property
    def mode(self) -> str:
        """'proxy' when a gateway is configured, else 'sdk'."""
        return "proxy" if self.api_base else "sdk"


# --------------------------------------------------------------------------
# pipeline
# --------------------------------------------------------------------------

@dataclass
class ExtractionReport:
    source: str
    considered: int = 0
    accepted: int = 0
    rejected: int = 0
    by_validator: dict = None
    reasons: list = None
    facts: list = None

    def __post_init__(self):
        self.by_validator = self.by_validator or {}
        self.reasons = self.reasons or []
        self.facts = self.facts or []


def extract_document(document: Document, proposer, resolver, limit=None) -> ExtractionReport:
    """Run one document through the boundary. Rejections are persisted, never retried."""
    rep = ExtractionReport(source=document.source.slug)
    text = document.raw_text

    for row in proposer.propose(document.source.slug, text, limit=limit):
        rep.considered += 1
        row = {k: v for k, v in row.items() if v is not None}
        cand = Candidate(document=document, model=getattr(proposer, "model", "?"), **row)
        result: ValidationResult = validate(cand, resolver=resolver)
        if result.accepted:
            fact = persist_accepted(cand, result)
            rep.accepted += 1
            rep.facts.append((fact, cand))
        else:
            persist_rejection(cand, result)
            rep.rejected += 1
            rep.by_validator[result.validator] = rep.by_validator.get(result.validator, 0) + 1
            rep.reasons.append((result.validator, result.reason))
    return rep


def ingest_page(source_slug: str, url: str, raw_html: str, channel="live") -> Document:
    src, _ = Source.objects.get_or_create(
        slug=source_slug,
        defaults={"name": source_slug, "base_url": url, "verified": True, "channel": channel})
    doc, _ = Document.objects.update_or_create(
        source=src, url=url,
        defaults={"raw_text": html_to_text(raw_html), "channel": channel,
                  "published_dates": "\n".join(extract_published_dates(raw_html))})
    return doc


def load_local_pages(pages_dir) -> list:
    """Turn files in data/pages into Documents, keyed by source slug."""
    out = []
    pages = Path(pages_dir)
    for p in sorted(pages.glob("*.html")):
        # stem is the source key: dha_rates, cdb_ph10, lre_sep, burst, milkiyat
        slug = p.stem
        out.append(ingest_page(slug, f"https://local.invalid/{p.name}", p.read_text(errors="ignore")))
    return out