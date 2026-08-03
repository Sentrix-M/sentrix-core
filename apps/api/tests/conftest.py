"""Pytest configuration — keeps the entire test suite hermetic and offline.

A developer's local ``apps/api/.env`` may configure ``AI_PROVIDER=gemini``
with a real ``GEMINI_API_KEY``. Without isolation, any test that calls
``build_kernel_pipeline()`` and resolves the default provider would construct
the real :class:`~app.providers.gemini.GeminiProvider`, hit the network, burn
API quota, and produce nondeterministic failures (HTTP 429/503).

This module forces deterministic, offline-safe settings *before* any test
module is imported so the :func:`app.config.settings.get_settings` LRU cache
is warmed with mock defaults:

- ``AI_PROVIDER=mock``          → the kernel always composes MockProvider.
- ``GEMINI_API_KEY=""``         → Gemini falls back to mock; embeddings use
                                  the deterministic mock embedder.
- ``GEMINI_MODEL=gemini-2.5-flash`` → stable model identifier for tests.

Priority order in pydantic-settings is
``init args > process env > .env file``, so the process-env assignments below
override whatever a local ``.env`` file contains.  Runtime behavior of the
application is untouched — ``conftest.py`` is only ever loaded by pytest.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Force deterministic settings for the entire test session.
# ---------------------------------------------------------------------------
os.environ["AI_PROVIDER"] = "mock"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GEMINI_MODEL"] = "gemini-2.5-flash"

# Warm the cached settings object now, at import time, before any test module
# is collected, so every ``get_settings()`` call during the suite returns the
# deterministic (offline) configuration — regardless of the local ``.env``.
from app.config.settings import get_settings  # noqa: E402

get_settings.cache_clear()
get_settings()

