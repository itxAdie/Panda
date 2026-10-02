"""Diagnose the hosted LiteLLM gateway hop by hop.

Answers one question: WHERE does the request die?

  hop 1  Django -> gateway   virtual key accepted by the gateway
  hop 2  gateway -> /v1/models   gateway can list its models
  hop 3  gateway -> provider   gateway holds a working credential for the provider
                               behind the selected model string

Hop 3 failing while hops 1-2 pass means the GATEWAY lacks the provider credential.
That is fixed on the gateway, not here — Django cannot supply it, and should not.

Touches nothing in corpus.extract, corpus.validators, or the test suite.
"""

import json
import os
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand

# Prefixes LiteLLM consumes locally rather than forwarding to an OpenAI-compatible
# gateway. The gateway never sees them.
LITELLM_PASSTHROUGH_PREFIXES = ("openai/", "openrouter/", "gemini/", "groq/")


def gateway_facing_model(model: str) -> str:
    """Strip the passthrough prefix LiteLLM would strip, leaving the gateway's name.

    With model='openai/openrouter/anthropic/claude-sonnet-4.5', litellm removes
    'openai/' and the gateway receives 'openrouter/anthropic/claude-sonnet-4.5'.
    Only one prefix is removed, because a second prefix may be genuine.
    """
    for p in LITELLM_PASSTHROUGH_PREFIXES:
        if model.startswith(p):
            return model[len(p):]
    return model


class Command(BaseCommand):
    help = "Probe the LiteLLM gateway hop by hop and report where auth fails."

    def add_arguments(self, parser):
        parser.add_argument("--model", default=None)

    def handle(self, *args, **opts):
        base = (opts.get("model") and None) or getattr(settings, "LLM_API_BASE", None)
        key = os.environ.get("LITELLM_API_KEY")
        model = opts.get("model") or settings.LLM_MODEL
        # LLM_MODEL is the LITELLM-facing name, which may carry a prefix litellm strips
        # (e.g. "openai/openrouter/anthropic/..." -> gateway sees "openrouter/anthropic/...").
        # Probing the gateway with the litellm-facing name tests the wrong thing and
        # reports a false failure. Strip the passthrough prefix before probing.
        gw_model = gateway_facing_model(model)
        self.stdout.write("")
        if not base:
            self.stdout.write(self.style.WARNING(
                "  LITELLM_API_BASE is unset -> SDK mode, no gateway. "
                "Nothing to probe."))
            return
        self.stdout.write(f"  gateway : {base.rstrip('/')}")
        self.stdout.write(f"  virtual key present: {bool(key)}")
        self.stdout.write(f"  model   : {model}")
        if gw_model != model:
            self.stdout.write(f"            (gateway-facing: {gw_model})")
        self.stdout.write("")

        # hop 1 + 2: gateway auth and model listing
        ok, ids, detail = self._get_models(base, key)
        self._hop("1  gateway accepts the virtual key", ok, detail)
        listed = []
        if ok:
            ok2, listed, detail2 = self._check_listed(base, key, gw_model)
            self._hop("2  gateway lists the selected model", ok2, detail2)
        self.stdout.write("")

        # hop 3: gateway -> provider
        ok3, detail3 = self._completion(base, key, gw_model)
        if ok3:
            self._hop("3  gateway authenticates to the provider", True, detail3)
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(
                "  ALL HOPS PASS. Re-run: run_live_page"))
        else:
            self._hop("3  gateway authenticates to the provider", False, detail3)
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(
                "  Hops 1-2 pass, hop 3 fails: the GATEWAY is missing the provider\n"
                "  credential for this model. Fix it on the LiteLLM server — Django\n"
                "  cannot supply it, and adding a provider key here would defeat the\n"
                "  point of the virtual key.\n\n"
                "  On the gateway: add the provider key (e.g. OPENROUTER_API_KEY for\n"
                "  openrouter/* models), restart, then re-run check_gateway."))
        self.stdout.write("")

    # -- helpers ---------------------------------------------------------

    def _hop(self, label, ok, detail=""):
        style = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(style(f"  [{'PASS' if ok else 'FAIL'}] {label}"))
        if detail:
            self.stdout.write(f"         {detail[:150]}")

    def _get_models(self, base, key):
        req = urllib.request.Request(
            base.rstrip("/") + "/v1/models",
            headers={"Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read())
            return True, [m.get("id", "") for m in data.get("data", [])], f"{len(data.get('data', []))} models"
        except urllib.error.HTTPError as e:
            return False, [], f"HTTP {e.code}: {e.read()[:100].decode('utf-8','ignore')}"
        except Exception as e:
            return False, [], f"{type(e).__name__}: {e}"

    def _check_listed(self, base, key, model):
        ok, ids, detail = self._get_models(base, key)
        if not ok:
            return False, [], detail
        if model in ids:
            return True, ids, f"'{model}' present"
        prefixes = sorted({i.split("/")[0] for i in ids if "/" in i})
        return False, ids, f"'{model}' ABSENT. prefixes offered: {prefixes}"

    def _completion(self, base, key, model):
        payload = json.dumps({
            "model": model, "max_tokens": 8,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        }).encode()
        req = urllib.request.Request(
            base.rstrip("/") + "/v1/chat/completions", data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            msg = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return True, f"provider responded: {str(msg)[:60]!r}"
        except urllib.error.HTTPError as e:
            body = e.read()[:220].decode("utf-8", "ignore")
            hint = ""
            if e.code in (401, 403) or "api key" in body.lower():
                hint = "  <- provider credential missing ON THE GATEWAY"
            return False, f"HTTP {e.code}: {body}{hint}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
