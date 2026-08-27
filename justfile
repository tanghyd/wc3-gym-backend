# The everyday backend commands. The recipe groups live in just/.
# just installs with the dev dependencies; run recipes with `uv run just <recipe>`.

set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

# The local dev stack in Docker: up, restart, down, logs, psql, status, import-xlsx.
mod containers './just/containers.just'

# Migrate, seed, list and drop databases by deployment path and environment. `just db` lists them.
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
