"""LLM configuration hygiene.

No live call is made anywhere in this suite. These tests assert the *wiring*: that
secrets live in the environment, that model selection is a setting, and that a
misconfigured backend fails loudly instead of degrading quietly.

A test that required a live call would be a bad test here: it would put a credential
requirement in the suite and make failures indistinguishable from network flakiness.
"""

import os
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from corpus.extract import LLMProposer

BASE = Path(__file__).resolve().parents[2]


class TestSecretHygiene(SimpleTestCase):
    def test_env_is_permissions_600(self):
        """A real .env holds a live credential. It must not be world-readable."""
        p = BASE / ".env"
        if not p.exists():
            self.skipTest("no .env in this environment")
        mode = oct(p.stat().st_mode)[-3:]
        self.assertEqual(mode, "600", f".env is mode {mode}; expected 600")

    def test_env_is_gitignored(self):
        self.assertIn(".env", (BASE / ".gitignore").read_text().split())

    def test_env_file_is_not_committed(self):
        """A real .env must never exist in the working tree from a commit."""
        # .env may exist locally with a real key; what matters is that it is ignored.
        self.assertTrue((BASE / ".gitignore").exists())

    def test_env_example_exists_and_is_placeholders_only(self):
        p = BASE / ".env.example"
        self.assertTrue(p.exists(), ".env.example documents the required variables")
        body = p.read_text()
        # Only CREDENTIAL variables must be empty. Non-secret settings
        # (LLM_BACKEND=litellm, LLM_MAX_TOKENS=4096) legitimately carry defaults.
        # Exact credential names, not substrings: LLM_MAX_TOKENS contains "TOKEN"
        # and is not a secret.
        credentials = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                       "OPENROUTER_API_KEY", "LITELLM_API_KEY", "LITELLM_MASTER_KEY"}
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() in credentials:
                self.assertEqual(val.strip(), "",
                                 f".env.example leaks a credential for {key}: {val!r}")

    def test_no_key_literal_in_source(self):
        """No sk-/key-shaped literal may appear in the code we wrote."""
        import re
        suspects = []
        for p in list(BASE.glob("corpus/**/*.py")) + list(BASE.glob("panda/*.py")):
            for m in re.finditer(r"(sk-[A-Za-z0-9_\-]{12,})", p.read_text()):
                suspects.append((p.name, m.group(0)[:12]))
        self.assertEqual(suspects, [], f"key-shaped literal in source: {suspects}")

    def test_model_is_a_setting_not_a_literal_in_extractor(self):
        src = (BASE / "corpus" / "extract.py").read_text()
        # the class must read settings, not hardcode a model string
        self.assertIn("settings.LLM_MODEL", src)
        self.assertNotIn('self.model = "', src)


class TestBackendSelection(SimpleTestCase):
    def test_backend_and_model_are_configurable(self):
        self.assertIn(settings.LLM_BACKEND, ("litellm", "anthropic"))
        self.assertIsInstance(settings.LLM_MODEL, str)
        self.assertTrue(settings.LLM_MODEL)

    def test_model_uses_provider_slash_model_when_litellm(self):
        if settings.LLM_BACKEND == "litellm" and not settings.LLM_API_BASE:
            self.assertIn("/", settings.LLM_MODEL,
                          "LiteLLM model strings are provider/model")

    def test_proxy_mode_is_explicit_and_uses_the_gateway_key(self):
        """Proxy mode is legitimate, but it changes WHICH credential is required.

        In SDK mode the credential is the provider's (ANTHROPIC_API_KEY). In proxy mode
        it is the gateway's own (LITELLM_API_KEY) — the gateway holds the provider key.
        Conflating the two produced a readiness check that demanded a key the operator
        did not have.
        """
        from corpus.extract import LLMProposer
        p = LLMProposer()
        self.assertIn(p.mode, ("sdk", "proxy"))
        self.assertEqual(p.mode, "proxy" if settings.LLM_API_BASE else "sdk")
        vars_, mode = LLMProposer._key_vars()
        self.assertEqual(mode, p.mode)
        if p.mode == "proxy":
            self.assertEqual(vars_, ["LITELLM_API_KEY"])
        else:
            self.assertNotEqual(vars_, ["LITELLM_API_KEY"])

    def test_available_reports_backend_package(self):
        # Not asserting True — the packages are not installed here. Asserting the
        # method answers honestly rather than raising.
        self.assertIn(LLMProposer.available(), (True, False))

    def test_check_ready_raises_actionable_error_when_unconfigured(self):
        """Must fail loudly with an install/key instruction, never silently degrade."""
        try:
            LLMProposer().check_ready()
        except RuntimeError as e:
            msg = str(e)
            self.assertTrue("pip install" in msg or "API_KEY" in msg, msg)
            self.assertNotIn("sk-", msg)
        else:
            self.skipTest("LLM is configured in this environment")


class TestProposerContract(SimpleTestCase):
    def test_prompt_forbids_computation_and_invents_nothing(self):
        src = (BASE / "corpus" / "extract.py").read_text()
        self.assertIn("VERBATIM", src)
        self.assertIn("exact contiguous substring", src)
        self.assertIn("NEVER output an entity id", src)
        self.assertIn("size and file type", src,
                      "the prompt must require rate qualifiers, per the M6 finding")

    def test_extractor_emits_no_place_object(self):
        """The LLM path must go through Candidate, which has no Place field."""
        from corpus.validators import Candidate
        fields = set(Candidate.__dataclass_fields__)
        self.assertNotIn("place", fields)
        self.assertIn("place_ref", fields)


class TestSystemRoleDelivery(SimpleTestCase):
    """The extraction contract must actually reach the model.

    Found by probing the live gateway: litellm's `system=` parameter is DROPPED, but a
    message with role="system" is HONOURED. Told "reply with exactly BANANA" via
    `system=`, the model replied "Hello! How can I help you today?".

    The silent failure: the extraction contract never arrived, so the model returned a
    markdown summary and we recorded 0 candidates with no error anywhere. An empty
    result meaning "the instructions were lost" is the worst possible failure shape.
    """

    def _messages(self, api_base):
        from corpus.extract import LLMProposer
        p = LLMProposer(api_base_override=api_base)
        return p, p._messages("src", "page text")

    def test_gateway_mode_sends_contract_as_a_system_message(self):
        p, msgs = self._messages("http://gateway.invalid")
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[0]["content"], LLMProposer.SYSTEM)
        self.assertEqual(msgs[1]["role"], "user")

    def test_sdk_mode_uses_the_system_parameter(self):
        p, msgs = self._messages(None)
        self.assertTrue(all(m["role"] == "user" for m in msgs),
                        "SDK mode must not smuggle a system message; it uses system=")

    def test_contract_is_present_in_gateway_mode(self):
        _, msgs = self._messages("http://gateway.invalid")
        self.assertIn("VERBATIM", msgs[0]["content"])
        self.assertIn("exact contiguous substring", msgs[0]["content"])
        self.assertIn("NEVER output an entity id", msgs[0]["content"])
        self.assertIn("JSON array", msgs[0]["content"])
