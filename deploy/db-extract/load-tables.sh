#!/bin/sh
# Loads TSV tables from an extract archive into Postgres, by column name.
# usage: load-tables.sh <archive.tar.gz> <postgres-url> table [table...]
# The target tables must exist (alembic upgrade head) and be empty.
set -eu
archive=$1; url=$2; shift 2
work=$(mktemp -d)
tar -xzf "$archive" -C "$work"
dir=$(find "$work" -type d -name tsv)
for t in "$@"; do
    cols=$(head -1 "$dir/$t.tsv" | tr '\t' ',')
    psql "$url" -v ON_ERROR_STOP=1 -qc "\\copy $t ($cols) from '$dir/$t.tsv' with (format text, header, null 'NULL')"
    psql "$url" -v ON_ERROR_STOP=1 -Atc "select setval(pg_get_serial_sequence('$t','id'), coalesce(max(id),1)) from $t" >/dev/null 2>&1 || true
    echo "$t $(psql "$url" -Atc "select count(*) from $t") rows"
done
