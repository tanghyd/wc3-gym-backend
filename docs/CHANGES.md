# What changed since the Flask app

A reviewer's summary of the fork against `Warcraft-Gym/backend` main (`fa2439d`, PR #61). 111 pull requests, one squash commit each, on `tanghyd/wc3-gym-backend`. The admin frontend fork is 23 squash commits (pull requests numbered to #25) against `Warcraft-Gym/admin_frontend` (`1b70102`). Client repositories at the end.

The one-line version: same routes, same JSON, same database, but the app is FastAPI instead of Flask, the schema is managed by Alembic, every total is computed on read instead of stored, every list is paged, and the tables sort on the server.

## Backend, by theme

### Framework: Flask to FastAPI (#14, #21, #22, #23, #26, #31, #34)

`src/` became `app/`, laid out as the FastAPI template does it: `api/routes/`, `api/deps.py`, `core/`, `models/`, `services/`. The app is built by `create_app()` so importing a module opens no database connection. The 13 hand-written Swagger `schema()` methods were deleted; OpenAPI comes from the models now. Every function is type-hinted and ruff enforces it; Python 3.13 is the floor.

Visible to clients: `/apidocs/` moved to `/docs` and `/apispec.json` to `/openapi.json`. A non-integer id in a path answers 422 instead of 404. 204 responses carry no body. JSON keys are no longer sorted.

### Data layer: SQLAlchemy 2 and SQLModel (#5, #12, #27, #32, #33, #35, #36, #55)

Pydantic v2 schemas replaced dict DTOs, then the models moved to SQLAlchemy 2 style, then to SQLModel so one class serves as table and schema. Each entity now has Base / table / Create / Update / Public classes. A partial `PUT` used to null every field it did not carry and answered 500 on some entities; it now writes only what is sent. A POST missing a required column answers 422 naming the field instead of 500.

### Derived values (#54, #101, #103, #105–#112)

The biggest behaviour change. Series points, match scores, team standings, career totals, fantasy team totals and bet results were stored columns that an admin refreshed with a "calculate" button. They are now computed when read, from rules in `app/core/scoring.py`, `career.py` and `fantasy.py`. The 24 stored columns were dropped in four migrations. Each season carries its own score system (`standard` or `helpstone`).

Removed routes: `POST /season/{id}/calculate/`, `GET /season/{id}/calculate/status`, `POST /stats/career/recalculate`, `POST /fantasy/season/{id}/calculate/`. The admin app lost the matching buttons.

Numbers a client sees: rows nobody had calculated read a number instead of `null`; a team with no played series reads `(0, 0, full points available)`; the career list also shows players who played but have no stored row (with `id: null`). The old calculate stamped one season's numbers onto every fantasy team; each team now scores against its own season.

### Paging, totals, sorting (#86–#91, #100, #102, #104, #114, #116, #117, #128, #130)

22 list routes take `limit` (1–500, default 500) and `offset`. Seven carry `X-Total-Count`. Three take `sort` and `order`. `GET /stats/career` takes `search`. Lists answer reduced payloads: every key stays, but collections inside embedded objects answer `[]`. Details in README.md.

This is why the WordPress player-stats and fantasy shortcodes had to change: unpaged, they now show the first 500 rows.

### Memory and speed (#3, #11, #68, #69, #72, #73, #86, #92, #95–#98, #126, #133, #136)

The backend on production held ~400 MB and grew with data. Causes found and fixed: 13 services each with their own connection pool; joined eager loads that multiplied rows (one team-season read produced 104,976 joined rows for 324 real ones); `joinedload(...).noload("*")` still joining the link tables; a request limiter that ran one request at a time; per-row queries in the import. Results measured on the same data: `POST /series/search` 201 MB / 7.3 s → 15 MB / 0.8 s; `GET /seasons` 244 MB / 9.8 s → 1.3 MB / 0.1 s; `GET /teams/season/{id}` and `GET /fantasy/teams` from out-of-memory at 20 seasons to 11 MB and 8 MB; `/users` 805 KB → 48 KB. On staging every route answers under 0.2 s at the box.

### Concurrency (#93, #118, #120, #121, #122, #125, #127)

Duplicate link rows are refused by the database, not by a read-then-write check. The w3c stats table is unique per user, race and season. KOTH signups cannot be double-active. The public token store is safe under parallel requests; two parallel signups with one token cannot both create a user. Token validation tolerates 5 seconds of clock drift.

### W3Champions (#118, #120, #123, #127, #135)

The team sync no longer reads w3champions twice per player. Requests time out at 10 s. `W3C_URL` means the API base, and the `CURRENT_WC3_SEASON` variable is gone: the season is the `current_wc3_season` settings row, or the newest season from w3champions when the row is absent. New route `GET /config/w3c` shows what the backend resolved.

### Errors and status codes (#29, #48, #51, #57, #134)

Every error answers `{"error": "..."}`, including the router's own 404/405 and auth failures (which answered `{"msg": ...}`). 29 raise sites that answered 500 for a missing row answer 404. Rule violations (season not active, setting missing, bad race) answer 400 or 404 with the message that names them instead of 500. The database driver's message no longer leaks into responses.

### Auth (#46, #75, #78)

Four routes that were open in production are admin-only now: `POST /teams/w3c_sync/...` and `POST /teams/{id}/image` (a decorator-order bug in Flask had left them open), `POST /fantasy/import/teams` and `/bets` (their guards were commented out). `GET /health` is new and open.

### Schema and migrations (#28, #38, #70, #103, #107, #110, #112, #119, #120, #125)

Alembic owns the schema. `create_all` is gone. Eight revisions; the first recognises an existing Flask-made database. [DATABASE-MIGRATION.md](DATABASE-MIGRATION.md) has the full list.

### Tooling (#17, #18, #19, #25, #39, #40, #76, #99, #129)

uv replaces `requirements.txt`. ruff formats and lints. GitHub Actions runs lint and 553 tests on every PR and publishes `ghcr.io/tanghyd/gnl-backend:staging` and `:sha-<commit>` on every push to main. A `justfile` holds the everyday commands.

### Dead code (#13, #30, #61, #64–#66, #81, #82, #85)

A never-registered blueprint with four routes, 25 unreachable exception branches, `db_scripts/`, `.vscode/`, the `background=true` form of the import, and 43 internal query strings that were built in Python only to be parsed back (a crafted `discord_id` could match every user; named finders replaced them).

### Standalone bug fixes

| PR | Fixed |
|---|---|
| #9 | 500 on the fantasy score breakdown |
| #10 | 500 creating or updating a season with string dates |
| #49 | fantasy calculate stored nothing; breakdown answered `"Race.HU"`; add/remove players 500 |
| #63 | fantasy import 500 on every row that named a race |
| #83 | a failed import answered 200 "imported successfully" |
| #124 | every player-series edit answered 500 and clobbered concurrent edits |
| #131 | export without `season_id` answered 500 |
| #136 | one team-season read joined 104,976 rows |

## Admin frontend (23 commits)

- **Tables page and sort on the server**: bets, career stats and the player dashboard series table are server-paged at 25 rows; column headers sort across the whole table; the sorted column is highlighted; the career search box asks the server. "All" walks every page.
- **Recalculate buttons removed** (season, career, fantasy) with a short note in their place.
- **Row actions are inline icon buttons** instead of a menu; edit, sync and delete take one click; "Remove from Team" asks for confirmation.
- **Error messages** from the backend are shown instead of fixed strings; a failed series save shows its error.
- **Match page** loads with 7 requests instead of 14 and one season-wide search instead of five weekly ones; MMR headers name the w3champions season.
- **Config page** shows the effective w3champions URL and season as placeholders.
- **Fantasy pages** no longer fail when the `current_gnl_season` key is absent.
- **CI** publishes `ghcr.io/tanghyd/gnl-admin-frontend:staging` and `:sha-<commit>`.
- Dead store actions removed (`fetchSeries`, `toggleDraft`, `fetchBets`).

Nothing changed in the Dockerfile, the build, or the `/api` base path.

## Other repositories

| Repo | Branch | Change |
|---|---|---|
| `gym_website_scripts` | `tanghyd/dev` | six shortcodes cache their backend calls in WordPress transients with a 2 s timeout; player stats and the two fantasy shortcodes walk the 500-row pages. **Must be installed before the backend goes live.** |
| `discord_bot_js` | `tanghyd/dev` (`b2d46b9`) | `api_framework_js` pinned to a commit; `w3c_url` read as the API base; season from w3champions instead of a hardcoded 21; two missing `await`s fixed in `/mmr` and `/stats`. |
| `api_framework` (Python SDK) | fork `master` | two 404 paths fixed; optional `limit`/`offset`. Still calls the removed fantasy calculate route in one unused file. No consumer. |
| `api_framework_js` | fork `main` | same two fixes; `calculateSeason` removed. The bot pins the upstream commit, which works for every call it makes. |

## Compatibility of old clients with the new backend

| Old client | Result |
|---|---|
| WordPress shortcodes | work, but the player-stats page and fantasy pages silently show the first 500 rows |
| Discord bot | works; `/mmr` and `/stats` were already broken by the missing `await`s |
| Old admin frontend | breaks: four buttons hit removed routes, match page stat columns empty, players page details empty. Deploy the new frontend with the new backend. |
