# Database recipes. Every one takes a deployment path and an environment:
#   just db <recipe> local
#   just db <recipe> azure staging     over SSH, inside the backend container on the box
#   just db <recipe> vercel prod
#   just db <recipe> vercel staging
# `just db url <path> <env>` prints the URL a pair resolves to, from .env. azure prod refuses every recipe.

# Recipes run from the repository root, one level up from this file.
set working-directory := '..'

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load

seed_repo := "Warcraft-Gym/wc3-gym-backend-db-seed"
local_default := "postgresql+psycopg://gym_user:gym_user@localhost:5432/gym_backend"

default:
    @just --list db

# Print the DB_URL a path and environment resolve to. The values come from .env; never commit real ones.
url path env="":
    #!/usr/bin/env bash
    set -euo pipefail
    target=$(echo {{ path }} {{ env }})
    case "$target" in
    (local)
        echo "${LOCAL_DB_URL:-{{ local_default }}}" ;;
    ("vercel prod")
        echo "${VERCEL_PROD_DB_URL:?VERCEL_PROD_DB_URL is not set in .env}" ;;
    ("vercel staging")
        echo "${VERCEL_STAGING_DB_URL:?VERCEL_STAGING_DB_URL is not set in .env}" ;;
    ("azure staging")
        echo "not implemented: the box has no URL reachable from here; the recipes reach it over SSH" >&2; exit 2 ;;
    ("azure prod")
        echo "not implemented: production is EAShibby's box, reached only through Portainer" >&2; exit 2 ;;
    (*)
        echo "unknown target $target: use local, azure staging, vercel prod or vercel staging" >&2; exit 2 ;;
    esac

# Bring the database to the latest migration. For vercel staging: the template and the shared database.
migrate path env="":
    #!/usr/bin/env bash
    set -euo pipefail
    target=$(echo {{ path }} {{ env }})
    case "$target" in
    ("azure staging")
        : "${AZURE_STAGING_HOST:?set AZURE_STAGING_HOST in .env}"
        ssh "azureuser@$AZURE_STAGING_HOST" 'cd /opt/gnl && sudo docker compose exec -T backend alembic upgrade head' ;;
    ("vercel staging")
        DB_URL="$(just db url vercel staging)" uv run python scripts/vercel_staging_db.py migrate ;;
    (*)
        DB_URL="$(just db url {{ path }} {{ env }})" uv run alembic upgrade head ;;
    esac

# Show the revision the database is on, and the revisions that exist.
status path env="":
    #!/usr/bin/env bash
    set -euo pipefail
    target=$(echo {{ path }} {{ env }})
    case "$target" in
    ("azure staging")
        : "${AZURE_STAGING_HOST:?set AZURE_STAGING_HOST in .env}"
        ssh "azureuser@$AZURE_STAGING_HOST" 'cd /opt/gnl && sudo docker compose exec -T backend sh -c "alembic current && alembic history"' ;;
    (*)
        url=$(just db url {{ path }} {{ env }})
        DB_URL="$url" uv run alembic current
        DB_URL="$url" uv run alembic history ;;
    esac

# Write a migration for the current models against the local database. Read it before committing: autogenerate also drops.
revision message:
    DB_URL="$(just db url local)" uv run alembic revision --autogenerate -m "{{ message }}"

# Drop every table of the local database, then build the schema again. Deletes all data.
reset:
    DB_URL="$(just db url local)" uv run alembic downgrade base
    DB_URL="$(just db url local)" uv run alembic upgrade head

# Migrate, then load the private seed repo. No access to it is not an error: the database stays migrated and empty.
seed path env="":
    #!/usr/bin/env bash
    set -euo pipefail
    seed=$(mktemp -d)
    trap 'rm -rf "$seed"' EXIT
    if gh repo clone {{ seed_repo }} "$seed" -- -q --depth 1 2>/dev/null; then
        echo "seed: $(ls "$seed"/*.csv | wc -l) tables from {{ seed_repo }}"
    else
        echo "seed: no access to {{ seed_repo }}, the database stays empty" >&2
    fi
    target=$(echo {{ path }} {{ env }})
    case "$target" in
    ("azure staging")
        : "${AZURE_STAGING_HOST:?set AZURE_STAGING_HOST in .env}"
        just db migrate azure staging
        if [ -f "$seed/users.csv" ]; then
            # The image carries scripts/seed_db.py, so only the CSVs travel.
            tar -C "$seed" -cz . | ssh "azureuser@$AZURE_STAGING_HOST" 'rm -rf /tmp/seed && mkdir /tmp/seed && tar -C /tmp/seed -xz && chmod -R a+rX /tmp/seed && cd /opt/gnl && sudo docker compose run --rm --no-deps -T -v /tmp/seed:/seed backend sh -c "python scripts/seed_db.py /seed \"\$DB_URL\""'
        fi ;;
    ("vercel staging")
        url=$(just db url vercel staging)
        if [ -f "$seed/users.csv" ]; then
            DB_URL="$url" uv run python scripts/vercel_staging_db.py seed "$seed"
        else
            DB_URL="$url" uv run python scripts/vercel_staging_db.py migrate
        fi ;;
    (*)
        url=$(just db url {{ path }} {{ env }})
        DB_URL="$url" uv run alembic upgrade head
        if [ -f "$seed/users.csv" ]; then uv run python scripts/seed_db.py "$seed" "$url"; fi ;;
    esac

# List the databases of the vercel staging project: the template, the shared database and the branch copies.
list path env="":
    #!/usr/bin/env bash
    set -euo pipefail
    [ "{{ path }} {{ env }}" = "vercel staging" ] || { echo "not implemented: only the vercel staging project holds more than one database" >&2; exit 2; }
    DB_URL="$(just db url vercel staging)" uv run python scripts/vercel_staging_db.py list

# Drop one branch copy on the vercel staging project. The template, the shared database and every other target are refused.
drop path env database:
    #!/usr/bin/env bash
    set -euo pipefail
    [ "{{ path }} {{ env }}" = "vercel staging" ] || { echo "not implemented: nothing is dropped anywhere but the vercel staging project" >&2; exit 2; }
    DB_URL="$(just db url vercel staging)" uv run python scripts/vercel_staging_db.py drop "{{ database }}"

# Turn a prod /dump zip into a seed directory: no Nightbot token, no test seasons, no derived columns.
clean-dump zip out_dir *seasons:
    uv run python scripts/clean_dump.py "{{ zip }}" "{{ out_dir }}" {{ seasons }}
