import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# LiteLLM lives in .venv (PEP 668 blocks system-wide installs). Prepend it so the
# LLM backend resolves without requiring `source .venv/bin/activate` every time.
_VENV_SITE = BASE_DIR / ".venv" / "lib"
if _VENV_SITE.is_dir():
    for _py in sorted(_VENV_SITE.glob("python*")):
        _sp = _py / "site-packages"
        if _sp.is_dir() and str(_sp) not in sys.path:
            sys.path.insert(0, str(_sp))

# --- LLM configuration -----------------------------------------------------
# Secrets live in .env at the project root, never in code, fixtures, or git.
# .env is gitignored; .env.example documents the variables.
_ENV = BASE_DIR / ".env"
if _ENV.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV, override=False)
    except ImportError:
        pass  # fall back to a minimal parser below

    def _load_env_fallback(path):
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))

    _load_env_fallback(_ENV)

# LiteLLM's documented pattern is "provider/model", e.g. "anthropic/claude-sonnet-4-5"
# or "openai/gpt-5". Override in .env; do not hardcode a key anywhere.
LLM_BACKEND = os.environ.get("LLM_BACKEND", "litellm")     # litellm | anthropic
LLM_MODEL = os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4-5")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4096"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))

# The hosted gateway IS in use. Note the prefix caveat documented in .env.example:
# litellm strips a leading provider prefix, and this gateway only knows fully
# prefixed names, so LLM_MODEL carries a doubled prefix.
LLM_API_BASE = os.environ.get("LITELLM_API_BASE") or None

# Local development. ALLOWED_HOSTS is localhost-only; this service is not built
# to face the public internet and the corpus is pre-launch.
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
STATIC_URL = "/static/"
SECRET_KEY = os.environ.get("PANDA_SECRET_KEY", "milestone1-local-only-not-for-deployment")
# No admin app: there is no web surface to administer. auth/contenttypes remain
# because Django's ORM and test client expect them.
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corpus.apps.CorpusConfig",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "panda.sqlite3"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
    ]},
}]

ROOT_URLCONF = "panda.urls"
USE_TZ = True
