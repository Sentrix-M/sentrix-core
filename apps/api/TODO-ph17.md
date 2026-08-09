# Phase 17 — Persistent Authentication (PostgreSQL)

## Objective
Persist users + refresh tokens via PostgreSQL (Neon) while preserving the
in-memory default and all existing auth contracts.

## Steps
- [x] 0. Plan confirmed with user (psycopg[binary], AUTH_BACKEND=memory default)
- [ ] 1. Add `psycopg[binary]` dependency (pyproject.toml + requirements.txt)
- [ ] 2. Add config: `auth_backend` (memory/postgres), `database_url` in `settings.py`
- [ ] 3. Add DB connection helper (`app/db/postgres.py`): async pool + idempotent DDL
- [ ] 4. Implement `PostgreSQLUserRepository` in `app/repositories/user_repository.py`
- [ ] 5. Implement `PostgreSQLRefreshTokenRepository` in `app/repositories/refresh_token_repository.py`
- [ ] 6. Wire backend selection in `app/main.py` (AUTH_BACKEND + DATABASE_URL)
- [ ] 7. Add offline tests for both PG repositories (fakes/mocks)
- [ ] 8. Run `python -m ruff check .`
- [ ] 9. Run `python -m pytest -q`
- [ ] 10. Revert TODO · report results

