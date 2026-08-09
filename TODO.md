# TODO — Windows psycopg3/Uvicorn event-loop fix

- [x] Investigate Uvicorn 0.52.0 loop creation (root cause confirmed)
- [x] Create `apps/api/sitecustomize.py` (real fix: patch uvicorn loop factory + selector policy)
- [x] Verify fix with standard `python -m uvicorn` command (probe → `_WindowsSelectorEventLoop`)
- [ ] Remove ineffective `asyncio.set_event_loop_policy()` block from `app/main.py`
- [ ] Update regression test `tests/test_event_loop_policy.py`
- [ ] Remove temporary probe files (`_probe_loop.py`, `_probe_launcher.py`)
- [ ] Run `python -m ruff check .`
- [ ] Run `python -m pytest -q`
- [ ] Start real server (postgres + Neon) and verify startup + `/health`
- [ ] Verify `--reload` works
- [ ] Report exact results
