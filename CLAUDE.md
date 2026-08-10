# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A Tunisian real-estate aggregator: it scrapes listings from two sites (Tayara, Mubawab), stores them in Postgres, and serves them through a FastAPI backend and a React frontend. Built as a 6-week internship project (WIMBEE); the numbered "modules" referenced in code comments (M2, M5, M6…) map to that scope — Module 5 = Gemini agent, Module 6 = ML price model / investment score, Module 7 = credit simulator. The codebase and UI are largely in French.

## Commands

Everything runs through Docker Compose. Container names are `realestate-backend`, `realestate-postgres`, `realestate-frontend`, `realestate-pgadmin`.

```bash
cp .env.example .env          # first-time setup
docker compose up -d --build  # start everything
```

- Frontend: http://localhost:3000 · API/Swagger: http://localhost:8000/docs · pgAdmin: http://localhost:5433 · Postgres direct: `127.0.0.1:5434` (5434 avoids clashing with a host Postgres on 5432)

**After changing backend (`scraper/`) code you must rebuild — the image copies the code in, it is not bind-mounted:**

```bash
docker compose up -d --build backend
```

Same for the frontend (`docker compose up -d --build frontend`). This is a hard requirement — a running container keeps stale code until rebuilt.

Retrain the ML price model (required once after install or `/estimate` returns 503; also runs automatically at the end of any scrape that inserted rows):

```bash
docker exec realestate-backend python -m scraper.ml.train_price_model
docker compose restart backend   # reload the new artifact (or call estimator.reload_artifact)
```

Apply a schema migration to an existing DB (init.sql only runs on a fresh volume):

```bash
docker exec realestate-postgres psql -U postgres -d realestate -f /migrations/migrate_ad_id.sql
```

Migration `.sql` files live in `db/`; only some are mounted into the container — check `docker-compose.yml` volumes or `docker cp` the file in.

Frontend dev (Vite, outside Docker): `cd frontend && npm run dev`. Build: `npm run build` (runs `tsc -b` then `vite build`).

Backend dev outside Docker: `pip install -r requirements.txt`, set `DB_HOST=localhost`/`DB_PORT=5434` in `.env`, then `uvicorn scraper.main:app --reload`.

There is **no test suite** and no linter configured — verify changes by exercising the running app/API.

## Architecture

### Request path

Browser → nginx (frontend container, port 80) → `/api/*` reverse-proxied to `backend:8000` (path rewritten, `/api` stripped). The frontend calls `API_BASE = "/api"` same-origin, so **CORS is not involved in normal operation**. nginx forwards `X-Forwarded-For`; the backend's `_client_ip()` trusts it for per-IP rate limiting — which is why backend/pgAdmin/Postgres ports are all bound to `127.0.0.1` only (a direct hit could otherwise spoof that header).

### Backend (`scraper/`, FastAPI, single app in `main.py`)

- **`main.py`** — all routes, the scrape orchestrator, and the weekly auto-scrape scheduler. Auth is a JWT stored in an **HttpOnly cookie** (`access_token`); the token is also accepted via `Authorization: Bearer`. `AuthMiddleware` gates `/scrape*` to admin (JWT role or `x-api-key: ADMIN_PASSWORD`). Route handlers call `get_current_user`/`get_current_user_role` for finer-grained checks. User id always comes from the signed token, never a client value.
- **`db.py`** — `db_cursor(commit=False)` context manager over a fresh psycopg2 connection per call (no pool); always use it rather than raw connections. Required env vars fail loudly if unset.
- **`scrapers/`** (`tayara.py`, `mubawab.py`) — each exposes `iter_scrape_phases(progress_callback, cancel_event, known_ad_ids)`, a generator yielding `(phase, items)` per phase. Phases are `rent`, `sale`, `land`. Ads already in the DB (`known_ad_ids`) are **not re-downloaded** unless `SCRAPER_REFRESH_ALL=1` — the biggest re-run speedup.
- **Scrape flow** (`_run_scrape_task` → `_run_site` → `_process_phase_items`): sites run concurrently (`SCRAPER_SITE_CONCURRENCY`), each site's phases run sequentially and flush to the DB per phase. Runs in a background thread; `scrape_status_state` (a module global) is polled by the dashboard. Cancellation is cooperative via `scrape_cancel_event`; rows already committed are kept, not rolled back. After a successful/partial run, ads not seen this run are **archived** (`archived = TRUE`), but only for sources that completed without error.
- **`insert.py`** — dedup + **versioning**: identity is `(source, ad_id)`. A re-scrape whose fields differ from the latest row (`is_same_property`) inserts a **new row** rather than updating; queries read the latest via `DISTINCT ON (source, ad_id) … ORDER BY id DESC`. Favorites are stored against `(source, ad_id)` so they survive re-versioning.
- **`classify.py` / `governorate.py`** — normalize each ad into one canonical `property_type` (`apartment`/`house`/`studio`/`office`/`land`) and resolve a Tunisian governorate. `backfill_*.py` scripts re-apply these rules to historical rows.
- **`agent/`** (Module 5, Gemini) — the LLM is allowed to write and run its own `SELECT` queries. Safety is enforced at the DB level: a dedicated `agent_ro` Postgres role with **`SELECT` on `properties` only** (never `users`/`agent_conversations`), created/repaired on startup by `ensure_readonly_role()`, its password generated once into gitignored `data/.agent_ro_password`, plus a 5s `statement_timeout`. `db_tool.py` also validates statement shape as defense-in-depth. Conversations persist per user in `agent_conversations`.
- **`ml/`** (Module 6) — `train_price_model.py` cleans data (`prepare_training_data.py`) and trains a gradient-boosting model on `log(price)`, saving `models/price_model.joblib` (host volume, survives rebuilds, gitignored). `estimator.py` lazy-loads and caches the artifact; it **validates the feature list matches the current code** (`ModelSchemaMismatch`) because the sklearn `ColumnTransformer` addresses columns positionally — a stale artifact would silently mispredict. The investment score (0–100): 50 = at estimate, 100 = ≥30% below (good deal), 0 = ≥30% above; `None` for rentals or placeholder prices.

### Data model

Effectively one table, **`properties`** (append-only versioned rows keyed by `source`+`ad_id`, with `archived` flag). House-only columns (`bedrooms`, `bathrooms`, `garage`, `furnished`, `terrace`, `pool`) are NULL for land; land-only columns (`buildable`, `road_access`) are NULL for houses. Plus `users`, `agent_conversations`, and `favorites`. `db/init.sql` is the fresh-install schema; incremental changes are separate `db/migrate_*.sql` files.

### Frontend (`frontend/src/`, React 18 + Vite + Tailwind + react-router 7)

- `App.tsx` — routes and `RequireAdmin`/`RequireAuth` guards. `/` welcome, `/annonces` listings, `/property/:id`, `/favorites`, `/dashboard` (admin), `/login`.
- `api/client.ts` — single API layer. **The JWT is never in JS** — it lives only in the HttpOnly cookie; `localStorage` holds only non-sensitive UI state (logged-in flag, role, name), which the server re-verifies every request.
- `lib/i18n.tsx` — custom i18n (FR/EN/AR incl. RTL). `components/AgentChatWidget.tsx` is the Gemini chat; `CreditSimulatorModal.tsx` + `lib/creditSimulator.ts` is Module 7.

## Configuration notes

All config is env vars in `.env` (see `.env.example` for the annotated full list). In Docker use `DB_HOST=db`/`DB_PORT=5432`; for local dev use `localhost`/`5434`. Key ones: `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `GEMINI_API_KEY` (+ optional `GEMINI_MODEL`), `GOOGLE_CLIENT_ID` (Google sign-in), `SMTP_*` (verification emails — if `SMTP_HOST` is empty the code is printed to backend logs instead), `COOKIE_SECURE` (set true under HTTPS), scraper tunables `SCRAPER_SITE_CONCURRENCY`/`SCRAPER_DETAIL_WORKERS`/`SCRAPER_REFRESH_ALL`.
