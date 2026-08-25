#!/bin/sh
# Download a gzipped dump from DUMP_URL (a blob URL with read permission) and load it into the database.
# Every table in the dump is dropped and recreated. Stop the backend first.
# Env: MYSQL_ROOT_PASSWORD, DUMP_URL, CONFIRM_RESTORE=yes; optional DB_HOST (mysql), DB_NAME (GYM_BACKEND).
set -eu
: "${MYSQL_ROOT_PASSWORD:?set MYSQL_ROOT_PASSWORD}"
: "${DUMP_URL:?set DUMP_URL to a blob URL with read permission}"
DB_HOST="${DB_HOST:-mysql}"
DB_NAME="${DB_NAME:-GYM_BACKEND}"
[ "${CONFIRM_RESTORE:-}" = "yes" ] || { echo "set CONFIRM_RESTORE=yes to overwrite $DB_NAME" >&2; exit 1; }

echo "restoring $DB_NAME on $DB_HOST"
curl -fsS "$DUMP_URL" | gunzip | mysql -h "$DB_HOST" -uroot -p"$MYSQL_ROOT_PASSWORD" "$DB_NAME"
echo "restored"
mysql -h "$DB_HOST" -uroot -p"$MYSQL_ROOT_PASSWORD" "$DB_NAME" -e "SHOW TABLES;"
