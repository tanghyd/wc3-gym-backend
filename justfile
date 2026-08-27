# The backend commands. Run them with `uv run just <recipe>`; the dev dependencies install just.
#
# A recipe that reaches a deployment takes a path and an environment, as `just db` does:
#   local            the Docker stack on this machine (the default where one applies)
#   azure staging    the Terraform box, reached over SSH; AZURE_STAGING_HOST in .env
#   azure prod       EAShibby's box, reached only through Portainer: every recipe refuses
#   vercel prod      the Vercel project, deployed by a push to main or `just deploy vercel prod`
#   vercel staging   the Vercel preview of the current branch
# README.md, "Where the backend runs", is the table of what each pair supports.

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load

image := "gnl-backend:local"
container_db_url := "postgresql+psycopg://gym_user:gym_user@gnl-postgres:5432/gym_backend"

default:
    @just --list

# Migrate, seed, list and drop databases by path and environment. `just db` lists them.
mod db './just/db.just'

# Run the tests as CI runs them. Takes pytest arguments, for example `just test -k koth`.
test *args:
    uv run pytest {{ args }}

# Check formatting and lint. CI runs this recipe too.
lint:
    uv run ruff format --check .
    uv run ruff check .

# Format the code and apply the lint fixes ruff can make.
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Build the image from the working tree, then start Postgres and the backend in Docker.
up:
    #!/usr/bin/env bash
    set -euo pipefail
    docker network inspect gnl-net >/dev/null 2>&1 || docker network create gnl-net
    if ! docker ps -a --format '{{{{.Names}}' | grep -qx gnl-postgres; then
        docker run -d --name gnl-postgres --network gnl-net -p 5432:5432 \
            -e POSTGRES_DB=gym_backend -e POSTGRES_USER=gym_user -e POSTGRES_PASSWORD=gym_user \
            -v gnl-postgres-data:/var/lib/postgresql/data postgres:17
    else
        docker start gnl-postgres >/dev/null
    fi
    docker build -t {{ image }} .
    docker rm -f gnl-backend >/dev/null 2>&1 || true
    docker run -d --name gnl-backend --network gnl-net -p 5002:5002 \
        -e DB_URL={{ container_db_url }} \
        -e ADMIN_TOKEN=devtoken -e JWT_SECRET_KEY=devsecret -e JWT_ALGORITHM=HS256 \
        -e TOKEN_TIME=60 -e REFRESH_TOKEN_TIME=1440 \
        -e BOT_CLIENT_TOKEN=dummy -e BOT_WEBHOOK_URL=http://localhost:5002/nowhere \
        -e FRONTEND_URL=http://localhost:5003 \
        {{ image }}
    echo "Waiting for the backend..."
    for _ in $(seq 1 60); do
        curl -fsS -o /dev/null http://localhost:5002/health 2>/dev/null && { echo "Backend: http://localhost:5002 (token: devtoken)"; exit 0; }
        sleep 2
    done
    echo "The backend did not answer on 5002. Log tail:" >&2
    docker logs --tail 20 gnl-backend >&2
    exit 1

# Start the containers again after a stop. Does not rebuild; `just up` does.
restart:
    docker start gnl-postgres gnl-backend

# Stop and remove the two containers. The data stays in the gnl-postgres-data volume.
down:
    docker rm -f gnl-backend gnl-postgres 2>/dev/null || true

# Open psql on the local database.
psql:
    docker exec -it gnl-postgres psql -U gym_user -d gym_backend

# Run the app as Vercel runs it: api/index.py, no image, no migration at start. Reads .env.
serve:
    DB_URL="$(just db url local)" uv run uvicorn api.index:app --reload --port 5002

# Import the S18 and S17 workbooks from tests/data into a running backend, S18 first.
import-xlsx api="http://localhost:5002" token="devtoken":
    #!/usr/bin/env bash
    set -euo pipefail
    access=$(curl -fsS -X POST "{{ api }}/login" -H 'Content-Type: application/json' -d '{"token": "{{ token }}"}' \
        | uv run python -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')
    for f in tests/data/GNL_S18_export_v2.xlsx tests/data/GNL_S17_export_v2.xlsx; do
        curl -fsS -X POST "{{ api }}/import?create_new=true" -H "Authorization: Bearer $access" -F "file=@$f"; echo
    done

# Ship the backend. azure staging pins the box to a published GHCR tag; vercel deploys the working tree.
deploy path env="" tag="staging":
    #!/usr/bin/env bash
    set -euo pipefail
    target=$(echo {{ path }} {{ env }})
    case "$target" in
    ("azure staging")
        : "${AZURE_STAGING_HOST:?set AZURE_STAGING_HOST in .env: terraform -chdir=infra output -raw fqdn, in the gym root}"
        image="ghcr.io/tanghyd/gnl-backend:{{ tag }}"
        token=$(curl -fsS "https://ghcr.io/token?scope=repository:tanghyd/gnl-backend:pull&service=ghcr.io" \
            | uv run python -c 'import json, sys; print(json.load(sys.stdin)["token"])')
        code=$(curl -fsS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $token" \
            -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json' \
            "https://ghcr.io/v2/tanghyd/gnl-backend/manifests/{{ tag }}")
        [ "$code" = "200" ] || { echo "$image is not anonymously pullable (HTTP $code)" >&2; exit 1; }
        # The box reads BACKEND_IMAGE from /opt/gnl/.env; the frontend line in that file belongs to the frontend.
        ssh "azureuser@$AZURE_STAGING_HOST" bash -s <<REMOTE
        set -euo pipefail
        cd /opt/gnl
        sudo touch .env
        grep -q '^BACKEND_IMAGE=' .env && sudo sed -i 's#^BACKEND_IMAGE=.*#BACKEND_IMAGE=$image#' .env \
            || echo 'BACKEND_IMAGE=$image' | sudo tee -a .env >/dev/null
        sudo docker compose config | grep -q "image: $image" \
            || { echo 'compose.yaml does not read BACKEND_IMAGE from .env; run: just azure sync, in the gym root' >&2; exit 1; }
        sudo docker compose pull -q backend && sudo docker compose up -d backend
        sudo docker image prune -f >/dev/null
    REMOTE
        for _ in $(seq 1 60); do
            curl -fsS "http://$AZURE_STAGING_HOST:5002/health" >/dev/null 2>&1 && break
            sleep 3
        done
        curl -fsS "http://$AZURE_STAGING_HOST:5002/health"; echo
    ;;
    ("azure prod")
        echo "not implemented: production is EAShibby's box, reached only through Portainer" >&2; exit 2 ;;
    ("vercel prod")
        npx vercel deploy --prod ;;
    ("vercel staging")
        npx vercel deploy ;;
    (local)
        echo "not implemented: the local stack is not deployed; run: just up" >&2; exit 2 ;;
    (*)
        echo "unknown target $target" >&2; exit 2 ;;
    esac

# Follow the backend log.
logs path="local" env="":
    #!/usr/bin/env bash
    set -euo pipefail
    target=$(echo {{ path }} {{ env }})
    case "$target" in
    (local)
        docker logs -f --tail 200 gnl-backend ;;
    ("azure staging")
        : "${AZURE_STAGING_HOST:?set AZURE_STAGING_HOST in .env}"
        ssh -t "azureuser@$AZURE_STAGING_HOST" "cd /opt/gnl && sudo docker compose logs -f --tail=200 backend" ;;
    ("azure prod")
        echo "not implemented: production is EAShibby's box, reached only through Portainer" >&2; exit 2 ;;
    ("vercel prod")
        npx vercel logs --prod ;;
    ("vercel staging")
        echo "not implemented: a preview has no fixed URL; run: npx vercel logs <preview url>" >&2; exit 2 ;;
    (*)
        echo "unknown target $target" >&2; exit 2 ;;
    esac

# Show what is running: the containers, the pinned image, or the Vercel deployments.
status path="local" env="":
    #!/usr/bin/env bash
    set -euo pipefail
    target=$(echo {{ path }} {{ env }})
    case "$target" in
    (local)
        docker ps -a --filter name=gnl- ;;
    ("azure staging")
        : "${AZURE_STAGING_HOST:?set AZURE_STAGING_HOST in .env}"
        echo "api http://$AZURE_STAGING_HOST:5002"
        curl -fsS "http://$AZURE_STAGING_HOST:5002/health" && echo
        ssh "azureuser@$AZURE_STAGING_HOST" 'grep ^BACKEND_IMAGE /opt/gnl/.env; cd /opt/gnl && sudo docker compose ps backend' ;;
    ("azure prod")
        echo "not implemented: production is EAShibby's box, reached only through Portainer" >&2; exit 2 ;;
    ("vercel prod")
        npx vercel ls --prod ;;
    ("vercel staging")
        npx vercel ls ;;
    (*)
        echo "unknown target $target" >&2; exit 2 ;;
    esac
