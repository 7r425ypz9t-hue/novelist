# Repository engineering instructions — «كاتب» (Kateb; internal package name: nis)

Read `docs/spec/*` (original requirements), `docs/SPEC_REVIEW.md` (approved deviations) and `docs/traceability.md` before changing behaviour. Arabic RTL is first-class.

## Layout
- `apps/api/nis` — FastAPI app: `models.py` (all tables), `routers/`, `services/` (manuscript, continuity, research, exports, portability, proposals, style), `agents/` (registry, context, skills, orchestrator, providers).
- `apps/api/tests` — pytest; `conftest.Writer` drives the real HTTP API.
- `apps/web/src` — React + Tiptap control panel; `lib/autosave.ts` + `lib/offline.ts` are the save engine.
- `apps/web/e2e` — Playwright against the real API (the web build is served by the API).

## Commands
- Backend: `cd apps/api && pytest -q && ruff check nis tests`
- Postgres: `NIS_DATABASE_URL=postgresql+psycopg://user:pw@host/db pytest -q`
- Frontend: `cd apps/web && npm run typecheck && npm test && npx vite build && npx playwright test`
- Schema change: edit `nis/models.py`, then `alembic revision --autogenerate`; `test_migrations_are_in_sync_with_models` enforces it.

## Non-negotiables
- Agents only create proposals; never give a skill a way to accept, modify canon, delete or publish (extend `ToolContext` with read-only tools only).
- Revisions are immutable; restores and accepted proposals create new revisions.
- Every project-scoped query goes through `deps.access_for` (404 for non-members).
- Retrieved text is data: keep `research.screen_injection` and `data_envelope` in any new model call.
- No external model call without project consent + per-run acknowledgement; no hard-coded prices or provider policies.
- Never commit credentials, manuscripts or third-party copyrighted text; demo content must be original.
- Report honestly: what was implemented, what was verified, what is pending (update PROGRESS.md / DECISIONS.md).
