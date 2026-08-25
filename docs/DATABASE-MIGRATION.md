# Database migration guide

This guide is for the person who runs the new backend against the existing production MySQL database for the first time. It also covers rehearsing that on a local copy of production.

Read the whole page before you start. The short version:

1. The schema is now owned by Alembic. The backend container runs `alembic upgrade head` every time it starts, before the server. There is no separate migration command to run.
2. An existing database needs no preparation. The first revision recognises the 21 tables the Flask app created, creates nothing, and records itself.
3. Eight revisions apply. Four drop columns, one deletes rows, one changes rows. **MySQL 5.7 cannot roll DDL back.** A `mysqldump` taken before the deploy is the only undo.
4. Rehearse on a copy of production first. Section 5 shows how.

## 1. How migrations run

| Where | What runs | File |
|---|---|---|
| Container start | `alembic upgrade head && exec uvicorn ...` | `Dockerfile:34` |
| By hand | `DB_URL=... uv run alembic upgrade head` | `justfile` recipe `migrate` |
| Tests | every `pytest` run builds a SQLite file with `alembic upgrade head` | `tests/migrate.py` |

`migrations/env.py` reads the database URL from the `DB_URL` environment variable, the same one the application reads. `alembic.ini` holds no URL. The application itself never creates or alters a table (`app/core/db.py`).

**Run one backend container per database.** Alembic does not lock MySQL, so two containers starting together race on the migration. The compose files in this project run exactly one.

A container that starts against a database already at head emits no DDL. The log shows the two Alembic context lines and then `Application startup complete`. A container with work to do logs one `Running upgrade` line per revision.

## 2. What happens to an existing database

The first revision, `658616cf0c2b`, checks which of the 21 tables exist:

- **All 21 present** (production, any database the Flask app made): creates nothing, writes the `alembic_version` table with `658616cf0c2b`, and the other seven revisions then apply.
- **None present** (an empty database): creates all 21 tables, then applies the other seven.
- **Some present**: stops with `RuntimeError` listing the missing tables. Do not force it. Fix the database by hand, then `alembic stamp head`.

The 21 tables it expects:

```
draft_series  fantasy_bets  fantasy_team_player  fantasy_teams  koth_events
koth_match_participants  koth_matches  koth_signups  map_season  maps  matches
player_career_stats  seasons  series  settings  team_season  teams
user_season_signup  user_team_season  users  w3cstats
```

No `alembic stamp` is needed. The `DB_URL` user needs `ALTER`, `CREATE`, `INDEX`, `DELETE` and `UPDATE` rights on the database.

## 3. The eight revisions

In order. `alembic history` prints the same chain. The head is `c4e1a9b72d50`.

| # | Revision | What it does | Data effect | Downgrade restores |
|---|---|---|---|---|
| 1 | `658616cf0c2b` | Baseline: the 21 tables | none on an existing DB | drops every table |
| 2 | `a66160626904` | `seasons.score_system VARCHAR(20) NOT NULL DEFAULT 'standard'`, backfilled from the `settings` row `score_system` | adds a column | drops the column and every per-season value |
| 3 | `300992697182` | drops `series.player1_points`, `series.player2_points`, `matches.team1_score`, `matches.team2_score`, `team_season.final_score`, `team_season.points_available`, `team_season.points_against` | **drops 7 derived columns** | empty columns |
| 4 | `3c1064e604d3` | drops 9 columns on `player_career_stats`: `rating`, `series_won`, `series_lost`, `games_won`, `games_lost`, `seasons_played`, `series_winrate`, `games_winrate`, `avg_series_per_season` | **drops 9 derived columns** | empty columns |
| 5 | `9f4b7c1d2ae5` | drops 6 columns on `fantasy_teams` (`player_points`, `bench_points`, `team_points`, `race_points`, `bet_points`, `total_points`) and `fantasy_bets.bet_result` | **drops 7 derived columns** | empty columns |
| 6 | `b7e2d4a91c05` | drops `team_season.maps_won`, `team_season.maps_lost` | **drops 2 columns** no code wrote | empty columns |
| 7 | `b2e7c4f10d93` | `DELETE` duplicate `w3cstats` rows (keeps the highest `id` per `user_id, race, wc3_season`), then a unique index on those three columns | **deletes rows** | drops the index only |
| 8 | `c4e1a9b72d50` | sets `is_active = 0` on duplicate active KOTH signups (lowest `id` per `event_id, twitch_username, race` wins), adds a virtual generated column `active_twitch_username` and a unique index over `event_id, active_twitch_username, race` | **updates rows** | drops the index and column only |

What "derived" means: every dropped column in revisions 3 to 5 held a value the app now computes when it reads (`app/services/derived.py`). The API still answers every one of those fields. Nothing a user sees is lost. What is lost is the ability to compare the stored number against the computed one after the fact, which is why the dump matters.

Source data that stays untouched: `player_career_stats.historical_*` (six columns), `player_career_stats.player_name`, `fantasy_bets.bet_points` (the stake), every map score, every result.

Revisions 7 and 8 are the two that touch real rows:

- Revision 7 deletes `w3cstats` rows. They are w3champions data, refetchable by an admin W3C sync, but the migration keeps only the newest row per key. Count what it will delete before you run it (section 4, step 3).
- Revision 8 needs **MySQL 5.7.8 or newer** for the generated column. Check `SELECT VERSION();` first. Local development and staging use `mysql:5.7.41`.

Net schema change: 24 columns dropped, 2 columns added, 2 unique indexes added, no tables added or dropped, no renames, no type changes.

### One manual change that is not a migration

The unique key on `player_career_stats.player_name` is named `player_name` on a database the Flask app created, and `uq_player_career_stats_player_name` on a database Alembic creates. Nothing breaks at runtime either way. The only effect is that `alembic revision --autogenerate` against a Flask-made database proposes a drop and recreate of that key. To align production once:

```sql
ALTER TABLE player_career_stats DROP INDEX player_name;
ALTER TABLE player_career_stats ADD UNIQUE KEY uq_player_career_stats_player_name (player_name);
```

Optional. Do it in the same window as the migration if you want autogenerate to stay clean.

## 4. Production procedure

Production is operated through Portainer. The person deploying has no shell on the VM, only Portainer: container list, container logs, a console into a running container, and the stack editor. Every step below is done from those four places. Where a step needs a file to leave or enter the VM, a one-off container does it (Step 4 and section 6).

Names used below and where to check them in Portainer: the stack (Stacks), the MySQL service name on the stack network (Stacks → the stack → Editor; `mysql` in this guide), the database name (`GYM_BACKEND` in this guide), the root password (`MYSQL_ROOT_PASSWORD` in the stack's environment). Substitute if production differs.

Stop at any failed step. Do not retry a failed migration. Save the log and restore from the dump (section 6).

### How to run SQL

Containers → the MySQL container → Console → `/bin/sh` → Connect. Then:

```sh
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" GYM_BACKEND
```

Every SQL block below is typed into that prompt. To save a result, copy the console output into a text file on your machine.

### Step 1 — check the facts

```sql
SELECT VERSION();
SHOW TABLES;
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='GYM_BACKEND' AND table_name='alembic_version';
```

Expect: version 5.7.8 or newer, all 21 tables from section 2, and `0` for `alembic_version` (production has never run Alembic).

### Step 2 — record the numbers before

```sql
SELECT 'users',COUNT(*) FROM users UNION ALL SELECT 'seasons',COUNT(*) FROM seasons
UNION ALL SELECT 'teams',COUNT(*) FROM teams UNION ALL SELECT 'matches',COUNT(*) FROM matches
UNION ALL SELECT 'series',COUNT(*) FROM series UNION ALL SELECT 'team_season',COUNT(*) FROM team_season
UNION ALL SELECT 'player_career_stats',COUNT(*) FROM player_career_stats
UNION ALL SELECT 'fantasy_teams',COUNT(*) FROM fantasy_teams
UNION ALL SELECT 'fantasy_bets',COUNT(*) FROM fantasy_bets
UNION ALL SELECT 'w3cstats',COUNT(*) FROM w3cstats
UNION ALL SELECT 'koth_signups',COUNT(*) FROM koth_signups
UNION ALL SELECT 'koth_signups_active',COUNT(*) FROM koth_signups WHERE is_active=1;
```

Save the output as `before.txt`. Also save a few screens from the public site and the admin app: the career table, one fantasy leaderboard, one standings page. The derived numbers must match them after.

### Step 3 — count what revision 7 will delete

```sql
SELECT COUNT(*) AS total,
       COUNT(*) - COUNT(DISTINCT CONCAT_WS('|',user_id,IFNULL(race,'~'),wc3_season)) AS rows_to_delete
FROM w3cstats;
```

Write the number down. After the migration, `w3cstats` must be smaller by exactly that many rows.

### Step 4 — dump the database (mandatory)

The dump runs in a one-off container from the image `ghcr.io/tanghyd/gnl-db-backup:latest` (source: `deploy/backup/` in this repository, built by CI). It runs `mysqldump --single-transaction --routines --triggers`, checks the dump completed, gzips it and uploads it to a blob URL. Nothing is written to the VM.

Before: Daniel creates a blob in his Azure storage account and sends a SAS URL with **write** permission, valid for one day.

In Portainer: Containers → Add container.

| Field | Value |
|---|---|
| Name | `gnl-db-backup` |
| Image | `ghcr.io/tanghyd/gnl-db-backup:latest` |
| Network (Advanced → Network) | the stack's network |
| Env | `MYSQL_ROOT_PASSWORD` = the stack's root password |
| Env | `DUMP_URL` = the SAS URL |
| Env | `DB_HOST` = the MySQL service name, if it is not `mysql` |
| Env | `DB_NAME` = the database name, if it is not `GYM_BACKEND` |
| Restart policy | Never |

Deploy the container. Open its log. Expect:

```
dumping GYM_BACKEND from mysql
dump complete, <n> bytes gzipped
uploading
uploaded
```

The container exits 0. If it exits non-zero the log names the reason (`dump did not complete`, or a curl error); fix and run again. Remove the container afterwards.

Daniel confirms from his side that the blob exists, has a plausible size, and `gunzip -t` passes. Only then continue.

This is a real database dump. The app's Excel export is not a substitute: it does not carry KOTH data, settings, team icons, career baselines or w3c stats, and it cannot be restored.

### Step 5 — run the migration by starting the new backend

Follow [DEPLOYMENT.md](DEPLOYMENT.md): in the stack editor, set the admin frontend image tag, then the backend image tag, then Update the stack. The backend container runs `alembic upgrade head` as it starts.

Containers → the backend container → Logs. Expect eight `Running upgrade` lines, `658616cf0c2b` first and `c4e1a9b72d50` last, then `Application startup complete`. Note how long it took. On staging with 18 seasons of data the chain ran in seconds.

If any line reads `ERROR` or the container keeps restarting: **stop**. Copy the full log. Go to section 6.

### Step 6 — verify

Console into the backend container (`/bin/sh`):

```sh
alembic current      # expect: c4e1a9b72d50 (head)
```

In a browser: `https://<backend host>/health` answers `{"status":"ok"}`.

In the MySQL console, run the Step 2 block again and save it as `after.txt`. Compare with `before.txt`. The only allowed differences: `w3cstats` down by the Step 3 number, `koth_signups_active` down by any duplicate active signups. Every other count unchanged.

Spot checks:

```sql
SELECT id, name, score_system FROM seasons;           -- never NULL
DESCRIBE player_career_stats;                         -- historical_* present, rating etc. gone
SELECT id, bet_points FROM fantasy_bets LIMIT 5;      -- stakes intact
SHOW INDEX FROM w3cstats;                             -- uq_w3cstats_user_id_race_wc3_season
SHOW CREATE TABLE koth_signups\G                      -- active_twitch_username + unique index
```

Then compare the career table, fantasy leaderboard and standings against the screens from Step 2.

## 5. Rehearsal on a local copy of production

Do this before the production window. It answers how long the migration takes and how many rows revision 7 deletes, on the real data.

You need the dump blob from Step 4 above. Then on your machine:

```sh
curl -fsS -o gnl-prod.sql.gz "<blob URL with read permission>"
gunzip -t gnl-prod.sql.gz && gunzip -k gnl-prod.sql.gz
tail -1 gnl-prod.sql            # must read: -- Dump completed

docker network create gnl-net 2>/dev/null || true
docker run -d --name gnl-mysql-prodcopy --network gnl-net -p 3307:3306 \
  -e MYSQL_ROOT_PASSWORD=root_password -e MYSQL_DATABASE=GYM_BACKEND \
  -e MYSQL_USER=gym_user -e MYSQL_PASSWORD=gym_user \
  mysql:5.7.41
until docker exec gnl-mysql-prodcopy mysqladmin ping -u gym_user -pgym_user --silent; do sleep 2; done

docker exec -i gnl-mysql-prodcopy mysql -uroot -proot_password GYM_BACKEND < gnl-prod.sql
```

Port 3307 keeps it apart from the normal local `gnl-mysql` on 3306.

Run Steps 1 to 3 from section 4 against this container (replace `docker compose exec mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD"` with `docker exec -i gnl-mysql-prodcopy mysql -uroot -proot_password`).

Preview the SQL without touching the database:

```sh
cd backend
DB_URL="mysql+pymysql://gym_user:gym_user@localhost:3307/GYM_BACKEND" \
  uv run alembic upgrade 658616cf0c2b:head --sql > planned.sql
```

The range starts at the first revision on purpose: `--sql` from base cannot run, because the first revision inspects the live database. The output is exactly what an existing database receives.

Run it:

```sh
export DB_URL="mysql+pymysql://gym_user:gym_user@localhost:3307/GYM_BACKEND"
uv run alembic current            # empty: no alembic_version yet
time uv run alembic upgrade head
uv run alembic current            # c4e1a9b72d50 (head)
uv run alembic check              # "No new upgrade operations detected."
```

Then Step 6 from section 4, and start the app against it:

```sh
docker build -t gnl-backend:prodcopy .
docker run -d --name gnl-backend-prodcopy --network gnl-net -p 5006:5002 \
  -e DB_URL="mysql+pymysql://gym_user:gym_user@gnl-mysql-prodcopy:3306/GYM_BACKEND" \
  -e ADMIN_TOKEN=devtoken -e JWT_SECRET_KEY=devsecret -e JWT_ALGORITHM=HS256 \
  -e TOKEN_TIME=60 -e REFRESH_TOKEN_TIME=1440 \
  -e BOT_CLIENT_TOKEN=dummy -e BOT_WEBHOOK_URL=http://localhost:9999 \
  -e FRONTEND_URL=http://localhost:5003 gnl-backend:prodcopy
curl -fsS http://localhost:5006/health
curl -s http://localhost:5006/stats/career -D - | head -20
```

The container runs `alembic upgrade head` again, finds the database at head, and emits no DDL. That is the expected behaviour on every later restart in production too.

Compare `/stats/career`, `/teams/season/{id}` and a fantasy leaderboard against what the live site shows. The derived numbers must match the stored ones the old app displayed.

Tear down: `docker rm -f gnl-backend-prodcopy gnl-mysql-prodcopy`.

## 6. Rollback

`alembic downgrade` restores structure only. It re-adds columns empty, and it cannot bring back the rows revision 7 deleted or the flags revision 8 changed. A migration that fails on its second `ALTER` leaves the first applied and `alembic_version` on the previous revision, which no downgrade repairs.

So the rollback is the dump, loaded by the same image the other way:

1. In the stack editor, set the backend **and** frontend image tags back to the previous ones. Update the stack. Then stop the backend container (Containers → backend → Stop) so nothing writes during the restore.
2. Daniel sends a SAS URL for the dump blob with **read** permission.
3. Containers → Add container, as in Step 4, with these differences: name `gnl-db-restore`, Command `restore.sh` (Advanced → Command & logging → Command), and one more env `CONFIRM_RESTORE` = `yes`. Without that variable the container refuses to run.
4. Open its log. Expect `restoring GYM_BACKEND on mysql`, `restored`, and the table list. The dump drops and recreates every table it holds.
5. Start the backend container. Verify against the Step 2 screens. Remove the restore container.

Roll both services back together. The old frontend and the new backend do not agree on the series payload.

A dump taken before the migration has no `alembic_version` table, which is right: after a restore the database is back on the Flask schema, and the old backend image does not run Alembic. A later attempt at the new image replays the whole chain.

## 7. Adding a migration later

```sh
export DB_URL="mysql+pymysql://gym_user:gym_user@localhost:3306/GYM_BACKEND"
uv run alembic revision --autogenerate -m "Add the column"
```

Read what autogenerate wrote. It compares the models in `app/models/` against the connected database and will drop a column the models no longer declare. `tests/test_migrations.py` fails if the migrated schema and the models disagree, so the test suite catches a forgotten migration.

The next planned migration is `users.w3c_synced_at DATETIME NULL` from the W3C sync work (see [HANDOVER.md](HANDOVER.md)). It is add-only and reversible. It should deploy in its own window, after this chain has landed, and still after a dump.
