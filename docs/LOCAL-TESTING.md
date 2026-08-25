# Local testing guide

How to run the backend and the admin frontend on one machine, load sample data, and check that everything works. Three paths, pick one:

- **A. Docker only** — no Python, no Node on the host. Closest to production.
- **B. Backend in Docker, frontend on the host** — the everyday development setup.
- **C. Everything on the host** — needs `uv` and Node.

Ports throughout: MySQL 3306, backend 5002, frontend 5003.

## Before you start

- Docker Desktop (or Docker Engine with the compose plugin).
- The two repositories side by side: `backend/` and `admin_frontend/`.
- For B and C: [uv](https://docs.astral.sh/uv/getting-started/installation/) and Node 22.

Windows note: the commands below are for a POSIX shell. In PowerShell, replace `\` line continuations with backticks or put each command on one line.

## A. Docker only

```sh
docker network create gnl-net

docker run -d --name gnl-mysql --network gnl-net -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=root_password -e MYSQL_DATABASE=GYM_BACKEND \
  -e MYSQL_USER=gym_user -e MYSQL_PASSWORD=gym_user \
  -v gnl-mysql-data:/var/lib/mysql \
  mysql:5.7.41

# wait until this answers "mysqld is alive" (about 30 s on first boot)
docker exec gnl-mysql mysqladmin ping -u gym_user -pgym_user

docker build -t gnl-backend:local backend
docker run -d --name gnl-backend --network gnl-net -p 5002:5002 \
  -e DB_URL="mysql+pymysql://gym_user:gym_user@gnl-mysql:3306/GYM_BACKEND" \
  -e ADMIN_TOKEN=devtoken -e JWT_SECRET_KEY=devsecret -e JWT_ALGORITHM=HS256 \
  -e TOKEN_TIME=60 -e REFRESH_TOKEN_TIME=1440 \
  -e BOT_CLIENT_TOKEN=dummy -e BOT_WEBHOOK_URL=http://localhost:9999 \
  -e FRONTEND_URL=http://localhost:5003 \
  gnl-backend:local

# wait until this answers {"status":"ok"}
curl -fsS http://localhost:5002/health
```

The backend container runs the migrations first, so on an empty database `docker logs gnl-backend` shows eight `Running upgrade` lines before `Application startup complete`.

Frontend as a production build:

```sh
docker build -t gnl-admin-frontend:local admin_frontend
docker run -d --name gnl-frontend --network gnl-net -p 5003:5003 gnl-admin-frontend:local
```

This serves the built bundle with `http-server`. The bundle calls `/api` on its own origin, and `http-server` does not proxy, so the app cannot reach the backend this way. Use a reverse proxy in front of both (the `infra/box/nginx.conf` in the workspace is one), or use path B for the frontend.

Teardown: `docker rm -f gnl-frontend gnl-backend gnl-mysql`. The database survives in the `gnl-mysql-data` volume; `docker volume rm gnl-mysql-data` deletes it.

## B. Backend in Docker, frontend on the host

MySQL and backend as in A (or `cd backend && uv run just up`, which does the same and waits for `/health`). Then:

```sh
cd admin_frontend
npm install
npm run dev
```

Vite serves `http://localhost:5003` and proxies `/api` to `http://localhost:5002`. Hot reload works. This is the setup `admin_frontend/README.md` recommends.

Do not run `npm run dev` inside a container with the stock `vite.config.js`: inside a container `localhost:5002` is the container itself and every `/api` call answers 500.

## C. Everything on the host

MySQL as in A. Then:

```sh
cd backend
uv sync
export DB_URL="mysql+pymysql://gym_user:gym_user@localhost:3306/GYM_BACKEND"
export ADMIN_TOKEN=devtoken JWT_SECRET_KEY=devsecret JWT_ALGORITHM=HS256
uv run alembic upgrade head
uv run uvicorn --factory app.main:create_app --host 0.0.0.0 --port 5002 --reload
```

`TOKEN_TIME` and `REFRESH_TOKEN_TIME` come from the committed `backend/.env`. `uv sync` installs Python 3.13 if the machine lacks it.

Note the host form of `DB_URL` uses `localhost`; the container form uses `gnl-mysql`. Using the wrong one is the usual reason a connection fails.

Frontend as in B.

## Load sample data

`data/GNL_S18_export.xlsx` in the workspace is one real season (107 players, 6 teams, 165 series, 380 fantasy bets). Import it through the API:

```sh
ACCESS=$(curl -fsS -X POST http://localhost:5002/login \
  -H 'Content-Type: application/json' -d '{"token":"devtoken"}' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

curl -fsS -X POST http://localhost:5002/import \
  -H "Authorization: Bearer $ACCESS" \
  -F "file=@data/GNL_S18_export.xlsx"
```

Or in the admin app: Seasons page, "Import Excel File". The season name and week count come from the workbook's `Season` sheet.

The export carries no `w3cstats` rows and no season signups. MMR columns read 0 until an admin presses a W3C sync button (needs internet; it calls w3champions) or you seed rows by hand.

For a copy of the production database instead, see section 5 of [DATABASE-MIGRATION.md](DATABASE-MIGRATION.md).

## Smoke test

| Check | Command | Expect |
|---|---|---|
| Health | `curl -fsS localhost:5002/health` | `{"status":"ok"}` |
| Docs | open `http://localhost:5002/docs` | Swagger UI; `GET /` redirects there |
| Login | `curl -X POST localhost:5002/login -H 'Content-Type: application/json' -d '{"token":"devtoken"}'` | `{"access_token":...,"refresh_token":...}` |
| Bad login | same with `"wrong"` | 401 `{"error":"Bad admin token"}` |
| Public list | `curl localhost:5002/seasons` | JSON array |
| Paged list | `curl -D - localhost:5002/stats/career?limit=5` | 5 rows and an `X-Total-Count` header |
| Admin app | `http://localhost:5003/#/login`, token `devtoken` | dashboard |

Then click through: Seasons, a match page (loads with 7 requests), the players page, Fantasy, Config. Every table pages on the server; column headers sort.

## Run the test suite

```sh
cd backend
uv run pytest          # 553 passed, 1 xfailed, about 45 s
uv run just lint       # ruff format --check + ruff check, as CI runs them
```

The suite needs no database server and no env vars. It builds a temporary SQLite file with `alembic upgrade head`, so every run checks the migrations too. `tests/test_migrations.py` fails when the models and the migrations disagree; `tests/test_query_budget.py` and `tests/test_memory_budget.py` fail when a list route starts issuing more statements or using more memory than pinned.

CI (`.github/workflows/ci.yml`) runs the same two commands on every pull request.

The admin frontend has `npm run lint` but no test suite and no CI check.

## Everyday commands (`backend/justfile`)

Run with `uv run just <name>`, or `just <name>` if just is installed.

| Recipe | Does |
|---|---|
| `up` | network, MySQL, build, run backend, wait for `/health` |
| `down` | stop the two containers (data kept) |
| `restart` | start them again |
| `logs` | follow the backend log |
| `slow-log` | MySQL queries over 0.2 s |
| `test`, `lint`, `fmt` | pytest, ruff check, ruff fix |
| `migrate`, `db-status`, `revision` | `alembic upgrade head`, `current`+`history`, `revision --autogenerate` |
| `db-reset` | `downgrade base` then `upgrade head` — deletes every row |

## Troubleshooting

- **Backend exits at start, log says `DB_URL is not set`** — pass `-e DB_URL=...`.
- **`Can't connect to MySQL server`** — wrong `DB_URL` host for where the command runs (see path C), or MySQL is still booting.
- **Every admin login answers 401** — `ADMIN_TOKEN` not set in the container.
- **`/api` answers 500 in the browser** — the frontend is running in a container with the stock vite proxy target. Run it on the host.
- **Container exits 255 after Docker Desktop restarts** — `docker start gnl-mysql gnl-backend`, MySQL first.
- **`just containers up` from the workspace root climbs one directory too far** — a `just` 1.34 module path bug. Use `just -f backend/justfile up` and start the frontend by hand.
