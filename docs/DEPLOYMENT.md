# Production deployment guide

Production is one VM with Docker: a MySQL 5.7 container, the backend container, the admin frontend container, and a reverse proxy that serves the frontend at `/` and the backend at `/api`. The database is the system of record and is never rebuilt. This page covers the first deployment of the FastAPI backend onto that box and every deployment after it.

Read [DATABASE-MIGRATION.md](DATABASE-MIGRATION.md) before the first deployment. The backend container migrates the database when it starts.

## 1. What changes for the person deploying

### Backend

| | Before | Now |
|---|---|---|
| Base image | `python:3-slim` | `python:3.13-slim` with `uv` |
| Dependencies | `requirements.txt` | `pyproject.toml` + `uv.lock` (`requirements.txt` is gone) |
| Server | `gunicorn --bind 0.0.0.0:5002 --timeout=1250 app:app` | `alembic upgrade head && exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port 5002` |
| Schema | created by the app at import | Alembic, at container start |
| Port | 5002 | 5002 |
| API docs | `/apidocs/` | `/docs`, `/openapi.json`; `GET /` redirects to `/docs` |
| Health | none | `GET /health` answers `{"status":"ok"}` after a `SELECT 1` |

Environment variables:

| Variable | Change | Note |
|---|---|---|
| `DB_URL` | same | required; the container refuses to start without it |
| `ADMIN_TOKEN` | same | secret |
| `JWT_SECRET_KEY` | same | secret |
| `JWT_ALGORITHM` | same | default `HS256` |
| `BOT_CLIENT_TOKEN` | same | secret |
| `BOT_WEBHOOK_URL` | same | when unset, Discord notifications are skipped, not an error |
| `FRONTEND_URL` | same | |
| `LOG_LEVEL` | same | default `INFO` |
| `TOKEN_TIME`, `REFRESH_TOKEN_TIME` | same | come from the committed `.env` inside the image (60 and 300 minutes); override with `-e` if wanted |
| `W3C_URL` | meaning changed | now the API base `https://website-backend.w3champions.com/api`, not the players endpoint. Either value works: the backend strips a trailing `/players`. The `w3c_url` row in the `settings` table wins over the variable when present. |
| `CURRENT_WC3_SEASON` | **removed** | the season is the `current_wc3_season` row in the `settings` table; when the row is missing the backend asks w3champions for the newest season. Delete the variable from any env file on the box. |
| `PLAYERS_COLLECTION`, `SCORE_SYSTEM` | **removed** | unused |

Keep the `current_wc3_season` settings row pinned on purpose. The day a new w3champions season opens, an unpinned value would read every player as zero games. An admin updates the row a few times a year from the Config page.

### Admin frontend

Nothing changes for the deployer. Same base image, same `npm run build`, same `http-server dist -p 5003`, same port, same `VITE_BACKEND_URL=/api`. The bundle contents differ.

`/api` is baked in at build time and is relative, so the reverse proxy on the box must keep serving the backend under `/api` on the dashboard's origin. If production uses a different path, set `VITE_BACKEND_URL` before `npm run build`.

### Images

The two repositories publish images on every push to `main` through GitHub Actions:

| Service | Image | Tags |
|---|---|---|
| backend | `ghcr.io/tanghyd/gnl-backend` | `staging`, `sha-<first 8 of the commit>` |
| admin frontend | `ghcr.io/tanghyd/gnl-admin-frontend` | `staging`, `sha-<first 8>` |

Both packages are public; no login is needed to pull. Production today pulls `eashibby/gnl_backend` and `eashibby/gnl_admin_ui` from Docker Hub. No pipeline builds those. Either pull the GHCR images directly, or build and push to Docker Hub by hand:

```sh
docker build -t eashibby/gnl_backend:<tag> backend
docker push eashibby/gnl_backend:<tag>
docker build -t eashibby/gnl_admin_ui:<tag> admin_frontend
docker push eashibby/gnl_admin_ui:<tag>
```

Pin a `sha-` tag or a date tag, never `latest`. A pinned tag is what makes a rollback possible.

## 2. Order of deployment

1. **WordPress snippets** (`gym_website_scripts`, branch `tanghyd/dev`). `GET /stats/career` and `POST /fantasy/teams/search` now answer 500 rows at most. The old `gnl-player-stats.php`, `gnl-fantasy-teams.php` and `gnl-fantasy-leaderboard.php` show the first 500 rows with no error. The new ones walk the pages. Paste the six `gnl-*.php` files over the existing Code Snippets. No env change.
2. **Database dump.** Section 4 of [DATABASE-MIGRATION.md](DATABASE-MIGRATION.md).
3. **Admin frontend, then backend, in one go.** The new backend's series lists no longer carry player stats; the new frontend reads them from the rosters. Old frontend against new backend shows empty stat columns and four buttons that hit removed routes. New frontend against old backend has nothing to read the totals from. Deploy both, frontend first.
4. **Discord bot** (`discord_bot_js`, branch `tanghyd/dev`, commit `b2d46b9`). Not required for compatibility; every route it calls still exists. Required for two fixes: `/mmr` and `/stats` were reading a Promise, and the season was hardcoded to 21. Delete `CURRENT_WC3_SEASON` from the bot's environment as well; the code still honours it as a fallback if the deployment sets it.

The Python and JS SDKs (`api_framework`, `api_framework_js`) need no action. Nothing running uses the Python one; the bot pins the JS one to a commit that works for every call it makes.

## 3. The deployment itself

This is the staging shape; production mirrors it. `infra/box/compose.yaml` in the workspace is the reference compose file and `infra/box/nginx.conf` the reference proxy.

```sh
# 1. Pin the images
#    In the compose file, or in its .env if it reads ${BACKEND_IMAGE} / ${FRONTEND_IMAGE}
BACKEND_IMAGE=ghcr.io/tanghyd/gnl-backend:sha-81b2913d
FRONTEND_IMAGE=ghcr.io/tanghyd/gnl-admin-frontend:sha-a8ec5612

# 2. Check what compose will actually run. Do this every time.
docker compose config | grep 'image:'

# 3. Pull and restart the two app services only. MySQL and the proxy stay up.
docker compose pull backend frontend
docker compose up -d frontend
docker compose up -d backend

# 4. Watch the migration and the start
docker compose logs -f backend
#    Expect the Running upgrade lines on the first deploy, then:
#    INFO:     Application startup complete.

# 5. Verify
curl -fsS http://localhost:5002/health
docker compose exec backend alembic current
docker stats --no-stream
```

Then in a browser, hard-refresh the admin app (Ctrl+F5) and open the career, fantasy and standings pages. Compare against the screens saved before the dump.

Post-deploy checks that prove the new code is live:

- `POST /stats/career/recalculate` answers 405; `POST /fantasy/season/1/calculate/` answers 404. The recalculation routes are gone.
- `GET /config/w3c` answers the w3champions base URL and the season in use.
- `GET /users` carries an `X-Total-Count` header.
- The admin app shows no recalculate buttons.

Memory: the backend sits around 100 to 150 MiB at rest on staging, 250 MiB under 40 concurrent requests. If `docker stats` shows much more, tell Daniel.

## 4. Rollback

1. `docker compose stop backend`
2. Restore the dump (section 6 of [DATABASE-MIGRATION.md](DATABASE-MIGRATION.md)).
3. Set both image tags back to the previous ones.
4. `docker compose up -d`
5. Verify against the saved screens.

Roll both services back together. The old frontend and the new backend do not agree on the series payload.

## 5. Every later deployment

Once production is on the Alembic chain, a deployment is:

1. Dump the database if the release carries a new file under `migrations/versions/`. Check with `git log --oneline <deployed-sha>..main -- migrations/versions`.
2. Pin the new tags, `docker compose config | grep image:`, `pull`, `up -d`.
3. `docker compose logs -f backend` until `Application startup complete`.
4. `curl /health`.

A restart with no new migration logs no `Running upgrade` line. That is normal.

## 6. Staging, for reference

Daniel runs a staging copy on Azure from the `infra/` directory of the workspace (Terraform, `just terraform`, `just docker`, `just staging`, `just deploy <backend_tag> <frontend_tag>`). It is a 2 vCPU / 1 GiB VM with a 2 GB swap file, `mysql:5.7.41` with a 64 MB buffer pool, and the compose file above. It runs the same images production would. It has HTTP only, no HTTPS. Its data is the S18 export copied 18 times, not production data.

The `just deploy` recipe does exactly the steps in section 3 plus two guards worth copying by hand: it checks that both image tags exist in the registry before touching the box, and it checks `docker compose config` shows both pinned tags before pulling. A compose file that hardcodes `:staging` behind a `${VAR:-default}` swallows the pin without an error; the `config` check catches that.

## 7. Known gaps

- No HTTPS on staging. Production terminates TLS somewhere we have not seen.
- The production reverse-proxy config is not in any repository. Confirm it serves `/api` on the dashboard origin before the first deploy.
- The Discord bot has no deploy pipeline and its host is not recorded here.
- Nothing builds a production image on merge. The GHCR `staging` images are the closest thing; pin them by `sha-` tag.
