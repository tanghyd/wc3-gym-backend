# Codebase guide

A walk through the backend as it is now: where things live, how a request moves through it, and where each kind of rule is kept. Read this with the repository open.

## 1. The stack

| Concern | Library | Where |
|---|---|---|
| HTTP | FastAPI on uvicorn | `app/main.py`, `app/api/` |
| Validation and serialisation | Pydantic v2 through SQLModel | `app/models/` |
| Database | SQLAlchemy 2 through SQLModel, MySQL 5.7 via PyMySQL | `app/core/db.py`, `app/models/` |
| Schema | Alembic | `migrations/` |
| Auth | PyJWT, HS256 | `app/core/security.py`, `app/api/deps.py` |
| Packaging | uv, `pyproject.toml`, `uv.lock` | repo root |
| Lint and format | ruff | `pyproject.toml` |
| Tests | pytest, SQLite | `tests/` |

SQLModel is the one library that is both the ORM model and the API schema. One class per table declares the columns; small subclasses declare the request and response shapes. That is why there is no separate `schemas/` directory.

## 2. Layout

```
app/
├── main.py            create_app(): dotenv, logging, engine, CORS, error handlers, router
├── api/
│   ├── main.py        collects the 15 route modules into one router
│   ├── deps.py        auth guards, the service singletons, Depends aliases
│   └── routes/        one module per API area (users, teams, matches, seasons, series,
│                      draft_series, maps, fantasy, koth, config, stats, import_export,
│                      public, login, health)
├── core/
│   ├── db.py          the one engine and session factory
│   ├── security.py    mint and decode JWTs
│   ├── exceptions.py  NotFoundError, BadRequestError
│   ├── query.py       the search language ("season_id == 3 and name ilike smith")
│   ├── ordering.py    sort/order on list statements
│   ├── scoring.py     the series points rule
│   ├── career.py      the career rating rule
│   └── fantasy.py     the fantasy scoring rule
├── models/            one module per table: the table class plus its Create/Update/Public shapes
└── services/          one module per entity; derived.py, season_import.py, player_series.py, w3c.py
migrations/            Alembic env.py and 8 revisions
tests/                 conftest.py plus 37 test modules
```

`app/core/` holds rules that touch no database. `app/services/` holds everything that does. `app/api/` holds nothing but HTTP.

## 3. A request, end to end

Take `GET /users?limit=50`.

1. **Route** — `app/api/routes/users.py`: `get_all_users(service: UserServiceDep, response: Response, limit=500, offset=0)`. `limit` is `Query(ge=1, le=500)`, so `limit=0` answers 422 before any code runs.
2. **Dependency** — `UserServiceDep` in `app/api/deps.py` resolves to a module-level `UserService` instance. The 13 services are singletons built once at import; they hold no request state.
3. **Service** — `UserService.getAll(limit, offset)` opens `with self.get_session() as session:`. That is `Session.begin()`: one transaction per call, commit on success, rollback on exception, always closed. Services never call `commit()` themselves.
4. **Model** — the service calls `User.getAll(session, limit, offset)` from `DBModel` in `app/models/base.py`, which adds `ORDER BY id` whenever a limit or offset is present so pages are stable.
5. **Response** — the route sets `X-Total-Count` and returns a list of `UserListPublic`. FastAPI serialises from the return annotation.

Writes follow the same shape with a `Create` or `Update` model as the body. `Update` models have every field optional, which is what makes a partial `PUT` safe: only the fields sent are written.

All handlers are plain `def`, so FastAPI runs them in a thread pool. One handler is `async` (`PUT /player-series/{id}`) and hands its blocking work to `run_in_threadpool`.

## 4. Models

Each entity module in `app/models/` declares a family:

```
XBase(SQLModel)                 shared fields
X(XBase, DBModel, table=True)   the table, relationships
XCreate(XBase)                  POST body
XUpdate(SQLModel)               PUT body, every field optional
XPublic(XBase)                  response; from_x() and to_dict()
```

Extra shapes where a list needs less than a single row: `UserReduced`, `UserListPublic`, `TeamReduced`, `SeasonInfoPublic`, `UserTeamSeasonStatsPublic`. List routes answer reduced shapes; single-row routes answer the full graph.

`app/models/__init__.py` sets the constraint naming convention on the metadata and then imports every model module, so relationships always resolve and every index has a stable name.

`app/models/types.py` holds the field converters that keep the wire format the old API had: ISO datetimes, enum values, `[]` for a missing list, numbers as strings where clients expect strings.

21 tables. Unique keys: `player_career_stats.player_name`, `settings.key`, `w3cstats(user_id, race, wc3_season)`, `koth_signups(event_id, active_twitch_username, race)`.

## 5. Derived values

No score, standing, career total or fantasy total is stored. `app/services/derived.py` computes them when a response is built, from three pure rule modules:

| Rule | Module | Notes |
|---|---|---|
| Series points per season score system | `app/core/scoring.py` | written twice, `points()` in Python and `points_case()` as SQL, and a test pins the two to each other over all 32 inputs |
| Team standings | `derived.py` over `scoring.py` | two statements per response: one resolves the score system, one grouped SUM |
| Career rating and totals | `app/core/career.py` | fold over every league season with 15 % decay per season, from the six `historical_*` baseline columns plus played series |
| Fantasy team points and bet results | `app/core/fantasy.py` | drafted players, bench, team standing, weekly race table, captain bets |

Each season carries its own scale in `seasons.score_system` (`standard`, max 3; `helpstone`, max 4).

What this buys: no recalculate buttons, no stale numbers after an import, no write races on totals, and imports of any shape are safe by construction. Never add a stored total; put the rule in `app/core/` and the fill in `derived.py`, and add a statement-count test.

## 6. Lists: paging, sorting, search, totals

Every list route takes `limit` (1 to 500, default 500) and `offset` (0 or more) as query parameters, on POST search routes too. The body is a bare JSON array. The total travels in the `X-Total-Count` header on seven routes: `GET /users`, `GET /stats/career`, `GET /player-series`, `GET /fantasy/teams`, `POST /fantasy/teams/search`, `GET /fantasy/bets`, `POST /fantasy/bets/search`. CORS exposes the header to browsers.

Three routes take `sort` and `order` (`app/core/ordering.py`); the allowed names are a `Literal` per route, so an unknown name answers 422 and no raw column name reaches SQL. The id tie-break stays ascending so two requests with the same parameters answer the same pages.

Search routes take a `query` string in the language of `app/core/query.py`: `==`, `!=`, `<`, `<=`, `>`, `>=`, `ilike`, joined by ` and ` / ` or `. Internal lookups do not go through this parser; they use named finders (`find_by_name`, `find_by_discord_id`, ...) so a value containing ` and ` cannot change the filter.

`README.md` has the route-by-route tables.

## 7. Auth

| Mechanism | How |
|---|---|
| Admin | `POST /login {"token": ADMIN_TOKEN}` answers an access and a refresh JWT. Routes marked `Depends(require_admin)` need `Authorization: Bearer <access>`. 63 of the 131 routes are admin. |
| Bot | `POST /public-access-helper` with `client_token` = `BOT_CLIENT_TOKEN` (body or query) mints a one-time public token and a URL for a Discord user. |
| Public one-time tokens | an in-process dict in `app/api/routes/public.py`; 30-minute TTL; signup, player dashboard and fantasy registration read it. `POST /signup` consumes the token. |
| KOTH Nightbot | `POST /koth/signups` and `GET /koth/signup` compare a token against the `KOTH_NIGHTBOT_TOKEN` settings row. |

Because the token store is a process dict, the backend is one process by design. Two uvicorn workers would not share tokens.

## 8. Errors

Every error answers `{"error": "<message>"}`. FastAPI's `{"detail": ...}` is never emitted; `tests/test_error_envelope.py` locks that.

| Raised | Status |
|---|---|
| `NotFoundError` (`app/core/exceptions.py`) | 404 |
| `BadRequestError` | 400 |
| `AuthError` (`app/api/deps.py`) | 401 or 422 |
| validation failure | 422, fields joined into one string |
| `SQLAlchemyError` | 500 `Database error`; the statement goes to the log only |
| anything else | 500 `Internal Server Error`; traceback to the log |

## 9. Configuration

There is no settings class. Each variable is read with `os.getenv` where it is used; `create_app` calls `load_dotenv()` first, which never overrides a variable already set. The committed `.env` holds only `TOKEN_TIME`, `REFRESH_TOKEN_TIME` and `W3C_URL`. Secrets (`DB_URL`, `ADMIN_TOKEN`, `JWT_SECRET_KEY`, `BOT_CLIENT_TOKEN`) are passed to the container. `README.md` has the table.

Three values live in the `settings` table, not the environment: `w3c_url`, `current_wc3_season`, `KOTH_NIGHTBOT_TOKEN` (plus `signups_enabled` and `current_gnl_season`). `GET /config/w3c` shows what the backend resolved.

## 10. W3Champions

`app/services/w3c.py`. One `GET {base}/players/{battletag}/game-mode-stats?gateWay=20&season=N` per player per season, 10-second timeout, keeping the 1v1 rows (one per race). Two triggers, both admin, both manual:

- `POST /users/w3c_sync/{user_id}` — one player, always runs.
- `POST /teams/w3c_sync/{team_id}/seasons/{season_id}` — one team, one run per team and season per day (a process-local stamp; 429 on a second click).

No scheduler, cron or queue. The next piece of work changes this route family; see [HANDOVER.md](HANDOVER.md).

## 11. Import and export

`POST /import` takes the season workbook (`file`, multipart) and creates or updates the season, teams, players, matches, series, and fantasy data in one synchronous request. `POST /export` writes the workbook for one `season_id`. `POST /fantasy/import/teams` and `/bets` take the fantasy sheets. `POST /stats/career/import-csv` takes the career baseline. The pipeline lives in `app/services/season_import.py`.

## 12. Tests

`tests/conftest.py` is the only file that knows FastAPI. It builds a temporary SQLite file with `alembic upgrade head`, creates the app with `create_app(db_url=...)`, and gives every test a `TestClient`. An autouse fixture empties every table after each test. Everything else asserts on status codes and JSON.

Worth knowing by name:

| File | Pins |
|---|---|
| `test_migrations.py` | migrated schema equals the models |
| `test_contract.py`, `test_public_contract.py` | the response shapes the admin app and the WordPress shortcodes read |
| `test_paging.py`, `test_total_count.py` | every paged route and its default order |
| `test_query_budget.py`, `test_memory_budget.py` | statement counts and peak memory of the list routes |
| `test_error_envelope.py` | `{"error": ...}` on every error path |
| `test_scoring.py`, `test_career_derived.py`, `test_fantasy_derived.py` | the three rule modules against known results |
| `test_admin_flows.py` | a season built through the write endpoints, end to end |

`uv run pytest`: 553 passed, 1 xfailed.

## 13. Where to change what

| I want to | Go to |
|---|---|
| add a field to a table | `app/models/<entity>.py`, then `uv run alembic revision --autogenerate`, read the file, run the tests |
| add a route | `app/api/routes/<area>.py`; a service method under `app/services/`; a test |
| change how points are scored | `app/core/scoring.py` and its 32-case test |
| change a list's default order or sort names | the route's sort map and `tests/test_paging.py` |
| change an error message | the raise site; the envelope is fixed |
| change what a list returns | the `Public` or `Reduced` model, and `test_contract.py` / `test_public_contract.py` if a client reads it |
