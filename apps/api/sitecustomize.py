"""Windows psycopg3 → SelectorEventLoop fix (auto-loaded at interpreter start).

Uvicorn 0.52 (and current 0.3x) no longer creates the event loop through
:func:`asyncio.set_event_loop_policy`. Instead ``uvicorn._compat.asyncio_run``
constructs the loop *directly* via the loop factory returned by
``Config.get_loop_factory()``:

    loop = loop_factory()   # bypasses the active event-loop policy

On Windows the default ``uvicorn.loops.asyncio.asyncio_loop_factory`` returns
:class:`asyncio.ProactorEventLoop`, which psycopg3 async connections reject
("Psycopg cannot use the 'ProactorEventLoop' to run in async mode").

Calling ``asyncio.set_event_loop_policy(...)`` from ``app.main`` is therefore
*ineffective* — the loop is built by the factory, not the policy.

This module is auto-imported by the Python ``site`` machinery at interpreter
startup (before uvicorn's CLI runs), so it can:

1. install the selector policy (harmless, covers any ``asyncio.new_event_loop``
   path), and
2. patch uvicorn's loop factory so the loop uvicorn actually creates on
   Windows is a selector-based loop.

Linux/macOS are untouched (the factory already uses ``SelectorEventLoop``).
"""

from __future__ import annotations

import asyncio
import sys


def _patch_uvicorn_factory() -> None:
    """Replace uvicorn's Windows loop factory with a selector-based one."""
    try:
        # Import happens lazily so this module stays cheap when uvicorn is
        # not in use (e.g. pytest). If uvicorn is already imported the module
        # object is the same instance uvicorn will bind at call time.
        from uvicorn.loops import asyncio as _uv_loops
    except Exception:  # pragma: no cover - uvicorn absent
        return

    def _selector_loop_factory(use_subprocess: bool = False):  # noqa: ARG001
        # psycopg3 async requires a selector loop; subprocess support is not
        # needed for the standard/reload single-process dev server.
        return asyncio.SelectorEventLoop

    # Only patch on Windows; elsewhere the default is already correct.
    if sys.platform == "win32":
        _uv_loops.asyncio_loop_factory = _selector_loop_factory


def _install() -> None:
    if sys.platform == "win32":
        # 1) Selector policy — effective for any code path that honours the
        #    policy (asyncio.run/asyncio.new_event_loop/loop="none").
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        # 2) Patch uvicorn's factory — effective for the loop uvicorn builds
        #    directly via Config.get_loop_factory() on the standard command.
        _patch_uvicorn_factory()


_install()
