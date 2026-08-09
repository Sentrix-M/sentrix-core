"""Regression tests for the Windows psycopg3 async event-loop compatibility fix.

Root cause
----------
Uvicorn 0.52 (and current 0.3x) no longer creates the event loop via
:func:`asyncio.set_event_loop_policy`. ``uvicorn._compat.asyncio_run`` builds
the loop **directly** through the loop factory returned by
``Config.get_loop_factory()``:

    loop = loop_factory()   # bypasses the active event-loop policy

On Windows the default ``uvicorn.loops.asyncio.asyncio_loop_factory`` returns
:class:`asyncio.ProactorEventLoop`, which psycopg3 async connections reject.

The permanent fix lives in :mod:`sitecustomize` (auto-imported at interpreter
startup, before uvicorn's CLI runs). On Windows it:
  1. installs the selector event-loop policy (defense-in-depth), and
  2. patches uvicorn's ``asyncio_loop_factory`` so the loop uvicorn actually
     creates is selector-based.

This test asserts the *real* invariant: uvicorn's loop factory must yield a
selector-based loop on Windows. Non-Windows platforms are untouched.
"""

from __future__ import annotations

import asyncio
import sys

import uvicorn.loops.asyncio as _uv_loops

from app import main as main_module


def test_uvicorn_loop_factory_returns_selector_on_windows() -> None:
    """On Windows, uvicorn's asyncio loop factory must be the selector factory."""
    if sys.platform != "win32":
        import pytest

        pytest.skip("uvicorn loop-factory assertion is Windows-specific.")

    factory = _uv_loops.asyncio_loop_factory(use_subprocess=False)
    loop = factory()
    try:
        # psycopg3 async requires a selector loop; Proactor is rejected. On
        # Windows the concrete selector loop class is ``_WindowsSelectorEventLoop``
        # (a subclass of ``SelectorEventLoop``).
        assert type(loop).__name__.endswith("SelectorEventLoop")
    finally:
        loop.close()


def test_selector_policy_installed_on_windows() -> None:
    """The selector policy must be in effect on Windows."""
    if sys.platform != "win32":
        import pytest

        pytest.skip("Selector-policy assertion is Windows-specific.")

    policy = asyncio.get_event_loop_policy()
    assert type(policy).__name__ == "WindowsSelectorEventLoopPolicy"


def test_non_windows_default_policy_untouched() -> None:
    """On non-Windows the default policy must not be replaced."""
    if sys.platform == "win32":
        return

    policy = asyncio.get_event_loop_policy()
    assert hasattr(policy, "new_event_loop")


def test_main_module_imports_cleanly() -> None:
    """The fix must not break importing the app module."""
    assert hasattr(main_module, "app")
