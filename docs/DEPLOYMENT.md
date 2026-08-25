# Production deployment guide

Production is one VM with Docker, managed through Portainer: a MySQL 5.7 container, the backend container, the admin frontend container, and a reverse proxy that serves the frontend at `/` and the backend at `/api`. The database is the system of record and is never rebuilt. This page covers the first deployment of the FastAPI backend onto that box and every deployment after it.

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

Production is operated through Portainer: no shell on the VM, only the stack editor, the container list, container logs and a console into a running container. The stack is a compose file that Portainer holds. Its exact text is not in any repository yet; the first step of the first deploy is to copy it out of Portainer (Stacks → the stack → Editor) and commit it to this repository under `deploy/`, so it is versioned from then on. `infra/box/compose.yaml` in Daniel's workspace is the staging equivalent and shows the shape: mysql, backend, frontend, a proxy that serves `/api`.

Steps, all in Portainer:

1. **Dump the database first** on a release that carries a migration (section 4 of [DATABASE-MIGRATION.md](DATABASE-MIGRATION.md)). The first FastAPI deploy carries eight.
2. **Stacks → the stack → Editor.** Set the frontend image to the new tag, then the backend image to the new tag. Pin a `sha-` tag, never `latest`. Update the stack with "Re-pull image" on. MySQL and the proxy keep running if their lines did not change.
3. **Containers → backend → Logs.** On a release with a migration, expect the `Running upgrade` lines, then `INFO: Application startup complete`. On a release without one, just the startup line. A container that restarts in a loop means the migration failed: **stop**, copy the log, go to section 4.
4. **Verify.** `https://<backend host>/health` answers `{"status":"ok"}`. Console into the backend container and run `alembic current` (expect the head revision named in the release). Containers → Stats shows the backend's memory.

Then in a browser, hard-refresh the admin app (Ctrl+F5) and open the career, fantasy and standings pages. Compare against the screens saved before the dump.

Post-deploy checks that prove the new code is live:

- `POST /stats/career/recalculate` answers 405; `POST /fantasy/season/1/calculate/` answers 404. The recalculation routes are gone.
- `GET /config/w3c` answers the w3champions base URL and the season in use.
- `GET /users` carries an `X-Total-Count` header.
- The admin app shows no recalculate buttons.

Memory: the backend sits around 100 to 150 MiB at rest on staging, 250 MiB under 40 concurrent requests. If Portainer shows much more, tell Daniel.

## 4. Rollback

1. In the stack editor, set the backend **and** frontend image tags back to the previous ones. Update the stack.
2. If the release carried a migration: stop the backend container and restore the dump with the restore container (section 6 of [DATABASE-MIGRATION.md](DATABASE-MIGRATION.md)), then start the backend.
3. Verify against the saved screens.

Roll both services back together. The old frontend and the new backend do not agree on the series payload.

## 5. Every later deployment

Once production is on the Alembic chain, a deployment is:

1. Dump the database if the release carries a new file under `migrations/versions/`. Check with `git log --oneline <deployed-sha>..main -- migrations/versions`.
2. Stack editor: new tags, Update with re-pull.
3. Backend log until `Application startup complete`.
4. `/health`.

A restart with no new migration logs no `Running upgrade` line. That is normal.

### Automating it later

Portainer gives each stack a webhook URL (Stacks → the stack → Webhooks). A call to it re-pulls the images and updates the stack. A GitHub Actions job that builds the image and then calls the webhook is a full deploy with no SSH, no IP allowlist and no shell; the webhook URL is the only secret and it lives in GitHub. The manual path above stays as it is, on the same stack file, for when the automation is not there. Not built yet; needs the stack file in the repository first.

## 6. Staging, for reference

Daniel runs a staging copy on Azure from the `infra/` directory of the workspace (Terraform, `just terraform`, `just docker`, `just staging`, `just deploy <backend_tag> <frontend_tag>`). It is a 2 vCPU / 1 GiB VM with a 2 GB swap file, `mysql:5.7.41` with a 64 MB buffer pool, and the compose file above. It runs the same images production would. It has HTTP only, no HTTPS. Its data is the S18 export copied 18 times, not production data.

The `just deploy` recipe does exactly the steps in section 3 plus two guards worth copying by hand: it checks that both image tags exist in the registry before touching the box, and it checks `docker compose config` shows both pinned tags before pulling. A compose file that hardcodes `:staging` behind a `${VAR:-default}` swallows the pin without an error; the `config` check catches that.

## 7. Known gaps

- No HTTPS on staging. Production terminates TLS somewhere we have not seen.
- The production stack file (and with it the reverse-proxy config) is not in any repository. Copy it out of Portainer into `deploy/` first; confirm it serves `/api` on the dashboard origin.
- `ghcr.io/tanghyd/gnl-db-backup` is built by CI on the next push to main and has not been run against a real database yet. Test it on staging before the production window.
- The Discord bot has no deploy pipeline and its host is not recorded here.
- Nothing builds a production image on merge. The GHCR `staging` images are the closest thing; pin them by `sha-` tag.
