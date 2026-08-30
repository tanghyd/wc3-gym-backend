# The Azure staging box, over SSH. Terraform in deploy/ owns the box (`just terraform`); the recipes
# here own what it runs. The backend image, Postgres, nginx and the box files deploy from this repo;
# the frontend image deploys from the frontend repo (`just deploy` there), which reads the same host.
# The host comes from `.env` (AZURE_STAGING_HOST) or, when that is unset, from the Terraform state.

# Recipes run from the repository root, one level up from this file.
set working-directory := '..'

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load

# Expanded by the shell when a recipe runs, not when just parses this file.
host := env("AZURE_STAGING_HOST", "$(terraform -chdir=deploy output -raw fqdn 2>/dev/null)")
box := "azureuser@" + host
api := "http://" + host + ":5002"
registry_image := "ghcr.io/tanghyd/gnl-backend"

default:
    @just --list azure

# Fail with the fix when no host is known.
_host:
    @[ -n "{{ host }}" ] || { echo "no box: set AZURE_STAGING_HOST in .env, or apply deploy/ with: just terraform plan && just terraform apply" >&2; exit 1; }

# Log in to the box.
ssh *args: _host
    ssh -t {{ box }} {{ args }}

# Print the URLs, /health, the pinned image tags and every container.
status: _host
    #!/usr/bin/env bash
    set -euo pipefail
    echo "dashboard http://{{ host }}"
    echo "api       {{ api }}"
    curl -fsS "{{ api }}/health" && echo
    # No --format: just reads the braces of a Go template as an interpolation of its own.
    ssh {{ box }} bash -s <<'REMOTE'
    cat /opt/gnl/.env 2>/dev/null || echo "no /opt/gnl/.env yet, run: just azure sync"
    cd /opt/gnl && sudo docker compose ps
    REMOTE

# Copy the box files (compose, nginx, DB credentials) up and restart what changed.
# cloud-init writes these on first boot; this recipe is how they change afterwards.
sync: _host
    #!/usr/bin/env bash
    set -euo pipefail
    # Read the secret BEFORE the heredoc. A failed substitution inside one is silent, and
    # an empty POSTGRES_PASSWORD recreates the container with a healthcheck that never passes.
    db_password=$(terraform -chdir=deploy output -raw db_password)
    [ -n "$db_password" ] || { echo "terraform holds no db password; apply first" >&2; exit 1; }
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    cp deploy/box/compose.yaml deploy/box/nginx.conf "$tmp/"
    cat >"$tmp/postgres.env" <<EOF
    POSTGRES_DB=gym_backend
    POSTGRES_USER=gym_user
    POSTGRES_PASSWORD=$db_password
    EOF
    scp -q "$tmp/compose.yaml" "$tmp/nginx.conf" "$tmp/postgres.env" {{ box }}:/tmp/
    ssh {{ box }} bash -s <<'REMOTE'
    set -euo pipefail
    sudo install -m 0644 /tmp/compose.yaml /tmp/nginx.conf /opt/gnl/
    sudo install -m 0600 /tmp/postgres.env /opt/gnl/postgres.env
    # backend.env comes from cloud-init, which Terraform ignores after first boot, so sync owns DB_URL.
    db_password=$(sed -n 's/^POSTGRES_PASSWORD=//p' /tmp/postgres.env)
    sudo sed -i "s#^DB_URL=.*#DB_URL=postgresql+psycopg://gym_user:$db_password@postgres:5432/gym_backend#" /opt/gnl/backend.env
    rm -f /tmp/compose.yaml /tmp/nginx.conf /tmp/postgres.env
    cd /opt/gnl && sudo docker compose up -d --remove-orphans
    # install writes a new inode; a single-file bind mount keeps the old one until the container is recreated
    sudo docker compose up -d --force-recreate nginx
    REMOTE
    echo "box files synced"

# Fail unless the tag can be pulled anonymously. This is what the box does at deploy.
check-image-exists tag="staging":
    #!/usr/bin/env bash
    set -euo pipefail
    token=$(curl -fsS "https://ghcr.io/token?scope=repository:tanghyd/gnl-backend:pull&service=ghcr.io" \
        | uv run python -c 'import json, sys; print(json.load(sys.stdin)["token"])')
    code=$(curl -fsS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $token" \
        -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json' \
        "https://ghcr.io/v2/tanghyd/gnl-backend/manifests/{{ tag }}")
    [ "$code" = "200" ] || { echo "{{ registry_image }}:{{ tag }} is not anonymously pullable (HTTP $code)" >&2; exit 1; }
    echo "{{ registry_image }}:{{ tag }} is pullable"

# Print the sha tag main builds to, for pinning or rollback.
current-tag:
    @git fetch origin --quiet && echo "sha-$(git rev-parse --short=8 origin/main)"

# Run the "Staging image" workflow and wait for it. Use after a merge if you do not want to wait.
ci:
    #!/usr/bin/env bash
    set -euo pipefail
    gh workflow run staging-image.yml
    sleep 5
    run=$(gh run list --workflow=staging-image.yml --limit 1 --json databaseId --jq '.[0].databaseId')
    gh run watch "$run" --exit-status

# Pin the box to a published image tag and restart the backend. The frontend line in /opt/gnl/.env is left alone.
deploy tag="staging": _host (check-image-exists tag)
    #!/usr/bin/env bash
    set -euo pipefail
    image="{{ registry_image }}:{{ tag }}"
    ssh {{ box }} bash -s <<REMOTE
    set -euo pipefail
    cd /opt/gnl
    sudo touch .env
    grep -q '^BACKEND_IMAGE=' .env && sudo sed -i 's#^BACKEND_IMAGE=.*#BACKEND_IMAGE=$image#' .env \
        || echo 'BACKEND_IMAGE=$image' | sudo tee -a .env >/dev/null
    sudo docker compose config | grep -q "image: $image" \
        || { echo 'compose.yaml does not read BACKEND_IMAGE from .env; run: just azure sync' >&2; exit 1; }
    sudo docker compose pull -q backend && sudo docker compose up -d backend
    sudo docker image prune -f >/dev/null
    REMOTE
    for _ in $(seq 1 60); do
        curl -fsS "{{ api }}/health" >/dev/null 2>&1 && break
        sleep 3
    done
    curl -fsS "{{ api }}/health"; echo

# Follow a container log. service is backend, postgres, frontend or nginx.
logs service="backend" tail="200": _host
    ssh -t {{ box }} "cd /opt/gnl && sudo docker compose logs -f --tail={{ tail }} {{ service }}"

# Bring the database to the latest migration, inside the backend container.
migrate: _host
    ssh {{ box }} 'cd /opt/gnl && sudo docker compose exec -T backend alembic upgrade head'

# Run any alembic command inside the backend container, for example `just azure alembic current`.
alembic *args: _host
    ssh {{ box }} 'cd /opt/gnl && sudo docker compose exec -T backend alembic {{ args }}'

# Migrate, then load the private seed repo. The image carries scripts/seed_db.py, so only the CSVs travel.
seed: _host migrate
    #!/usr/bin/env bash
    set -euo pipefail
    seed=$(mktemp -d)
    trap 'rm -rf "$seed"' EXIT
    just _fetch-seed "$seed"
    if [ -f "$seed/users.csv" ]; then
        tar -C "$seed" -cz . | ssh {{ box }} 'rm -rf /tmp/seed && mkdir /tmp/seed && tar -C /tmp/seed -xz && chmod -R a+rX /tmp/seed && cd /opt/gnl && sudo docker compose run --rm --no-deps -T -v /tmp/seed:/seed backend sh -c "python scripts/seed_db.py /seed \"\$DB_URL\""'
    fi
