#!/bin/sh
# Dumps one MySQL database: a full mysqldump plus one TSV per table, as one
# tar.gz. Writes it to /out and, when BLOB_SAS_URL is set, PUTs it there.
set -eu
: "${DB_HOST:?}" "${DB_USER:?}" "${DB_PASSWORD:?}" "${DB_NAME:?}"
export MYSQL_PWD="$DB_PASSWORD"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
work=/tmp/$DB_NAME-$stamp
mkdir -p "$work/tsv" /out

mysqldump -h "$DB_HOST" -u "$DB_USER" --single-transaction --no-tablespaces --routines --triggers "$DB_NAME" > "$work/$DB_NAME.sql"
mysql -h "$DB_HOST" -u "$DB_USER" -N -B -e "SHOW TABLES" "$DB_NAME" | while read -r t; do
    # --raw keeps tabs and newlines inside a cell unescaped; --batch prints NULL as NULL
    mysql -h "$DB_HOST" -u "$DB_USER" -B --raw -e "SELECT * FROM \`$t\`" "$DB_NAME" > "$work/tsv/$t.tsv"
    echo "$t $(($(wc -l < "$work/tsv/$t.tsv") - 1)) rows"
done

archive=/out/$DB_NAME-$stamp.tar.gz
tar -C /tmp -czf "$archive" "$(basename "$work")"
echo "wrote $archive ($(du -h "$archive" | cut -f1))"

if [ -n "${BLOB_SAS_URL:-}" ]; then
    curl -fsS -X PUT -H "x-ms-blob-type: BlockBlob" --data-binary "@$archive" "$BLOB_SAS_URL"
    echo "uploaded to blob"
fi
