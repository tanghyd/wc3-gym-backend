# Handover

Everything a maintainer needs to take over the GNL backend and admin frontend as they are on the `tanghyd` forks. Five pages:

| Page | Read it when |
|---|---|
| [CHANGES.md](CHANGES.md) | you want to know what changed since the Flask app, by theme, with PR numbers |
| [CODEBASE-GUIDE.md](CODEBASE-GUIDE.md) | you are opening the code for the first time |
| [LOCAL-TESTING.md](LOCAL-TESTING.md) | you want it running on your machine |
| [DATABASE-MIGRATION.md](DATABASE-MIGRATION.md) | before the first production deploy, and before rehearsing it on a copy of production |
| [DEPLOYMENT.md](DEPLOYMENT.md) | deploying to the production VM, and rolling back |

The `README.md` at the repository root describes the current app on its own: setup, environment variables, the paging contract, migrations.

## Where the code is

| Repo | Fork | Branch of record |
|---|---|---|
| backend | `github.com/tanghyd/wc3-gym-backend` | `main` (81b2913, PR #137) |
| admin frontend | `github.com/tanghyd/wc3-gym-admin-frontend` | `main` (a8ec561, PR #25) |
| WordPress shortcodes | `github.com/Warcraft-Gym/gym_website_scripts` | `tanghyd/dev` |
| Discord bot | `github.com/Warcraft-Gym/discord_bot_js` | `tanghyd/dev` (b2d46b9) |
| Python SDK | `github.com/tanghyd/wc3-gym-api-framework` | `master` |
| JS SDK | `github.com/tanghyd/wc3-gym-api-framework-js` | `main` |

Every change is a squash-merged pull request with a description. `git log --oneline upstream/main..main` in the backend lists the 111 of them; `git show <sha>` shows one with its description.

Images: `ghcr.io/tanghyd/gnl-backend` and `ghcr.io/tanghyd/gnl-admin-frontend`, tags `staging` and `sha-<commit>`, public, built on every push to main.

Staging: `http://gnl-staging.northcentralus.cloudapp.azure.com/` runs both `staging` images on a 1 GiB Azure VM with the S18 export copied 18 times. Daniel deploys it with `just deploy` from the workspace root.

## The order to do things in

1. Read [CHANGES.md](CHANGES.md).
2. Run it locally ([LOCAL-TESTING.md](LOCAL-TESTING.md)), import the S18 export, click through.
3. Get a `mysqldump` of production and rehearse the migration on it ([DATABASE-MIGRATION.md](DATABASE-MIGRATION.md) section 5). This is the step that turns "should work" into "does work" for the real data.
4. Install the WordPress snippets from `tanghyd/dev`.
5. Deploy ([DEPLOYMENT.md](DEPLOYMENT.md)): dump, frontend, backend, verify.
6. Redeploy the bot.

## Work in flight

**W3C sync optimisation** — started 2026-08-25, in progress on the backend fork. PR A is open as `tanghyd/wc3-gym-backend#138`; PR B is being built on top of it. Four PRs in all. What they change, so a reviewer is not surprised:

| PR | Branch | Change |
|---|---|---|
| A | `fix/w3c-sync-reports-failures` | the team sync returns `{synced, skipped, failed[{id, name, battleTag, reason}]}` instead of a bare 200; one shared `requests.Session`; a w3champions 429 answers 502 `{"error": ...}` instead of a silent per-player failure |
| B | `feature/w3c-synced-at` | **one migration**: `users.w3c_synced_at DATETIME NULL`, add-only, reversible. Players sync four at a time in a thread pool; a player synced in the last 10 minutes is skipped; the process-local 24-hour stamp and its 429 go away |
| C | `feature/season-w3c-sync` | new route `POST /seasons/{season_id}/w3c_sync`, admin, syncs every signed-up player of a season |
| D | admin frontend `feature/w3c-sync-results` | the match page syncs both teams in parallel and shows synced / skipped / failed by name; a "synced 2 hours ago / never synced" label next to each MMR; the season page calls the season route once |

Why: on the match page a sync takes ~30 s today (two teams, 18 players each, two serial calls per player) and failures are hidden behind "Team synced successfully". Target under 5 s, with failures named.

What does not change: what is fetched (two w3champions seasons, every race), the `current_wc3_season` pin, and there is still no automatic sync (no cron, no queue). Deployment: PR B's migration goes in its own window, after the eight-revision chain above has landed on production, with a dump first like every migration.

Until these merge, the routes and payloads in this handover are the ones on `main`. Full plan: `W3C-SYNC-PLAN.md` in Daniel's workspace.

## Open items a maintainer should know

- **Production reverse proxy.** The built frontend calls `/api` on its own origin. Whatever serves that on the production box is not in any repository. Confirm it before deploying.
- **No production image pipeline.** CI publishes the GHCR `staging` and `sha-` images. Production pulls `eashibby/*` from Docker Hub, which nothing builds. Either pull GHCR or push by hand.
- **`CURRENT_WC3_SEASON`** must not be reintroduced by an env file on the box or in the bot's deployment.
- **The `player_name` index rename** on `player_career_stats` is optional and manual (DATABASE-MIGRATION.md section 3).
- **Two SDK files still call the removed fantasy calculate route** (`api_framework/gnl_api_framework/services/fantasy_service.py`). Nothing uses them.
- **`RandomStatsView.vue`** calls w3champions directly from the browser with a hardcoded URL and season list; it ignores the Config page.
- **The season boundary is manual.** An admin updates `current_wc3_season` in Config when a new w3champions season opens.
- **Staging deploy access.** The staging box pins SSH to one address; Daniel's changes. Replacing that with `az vm run-command`, Tailscale or a CI deploy job is decided but not done.
- **Automation.** Daniel would prefer deployments to run from CI. EAShibby's position is that a manual, well-documented path is safer when the person who built the automation is gone. This handover is written for the manual path; every step is a plain `docker compose` command.
