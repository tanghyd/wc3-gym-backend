#!/bin/sh
# Dumps one MySQL database: a full mysqldump plus one TSV per table, as one
# tar.gz. Writes it to /out and, when UPLOAD_URL is set, POSTs it there
# (Supabase Storage: https://<project>.supabase.co/storage/v1/object/<bucket>/<name>).
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

if [ -n "${UPLOAD_URL:-}" ]; then
    curl -fsS -X POST -H "Authorization: Bearer ${UPLOAD_TOKEN:?}" -H "Content-Type: application/gzip" \
        --data-binary "@$archive" "$UPLOAD_URL/$(basename "$archive")"
    echo "uploaded to $UPLOAD_URL"
fi
