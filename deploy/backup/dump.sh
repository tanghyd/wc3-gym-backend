#!/bin/sh
# Dump one database and upload it, gzipped, to DUMP_URL (an Azure Blob SAS URL with write permission).
# Env: MYSQL_ROOT_PASSWORD, DUMP_URL; optional DB_HOST (mysql), DB_NAME (GYM_BACKEND).
set -eu
: "${MYSQL_ROOT_PASSWORD:?set MYSQL_ROOT_PASSWORD}"
: "${DUMP_URL:?set DUMP_URL to a blob URL with write permission}"
DB_HOST="${DB_HOST:-mysql}"
DB_NAME="${DB_NAME:-GYM_BACKEND}"
file=/tmp/dump.sql.gz

echo "dumping $DB_NAME from $DB_HOST"
mysqldump -h "$DB_HOST" -uroot -p"$MYSQL_ROOT_PASSWORD" \
  --single-transaction --routines --triggers "$DB_NAME" | gzip > "$file"

last=$(gunzip -c "$file" | tail -1)
case "$last" in
  "-- Dump completed"*) ;;
  *) echo "dump did not complete: $last" >&2; exit 1 ;;
esac
echo "dump complete, $(wc -c < "$file") bytes gzipped"

echo "uploading"
curl -fsS -X PUT -H "x-ms-blob-type: BlockBlob" --upload-file "$file" "$DUMP_URL"
echo "uploaded"
