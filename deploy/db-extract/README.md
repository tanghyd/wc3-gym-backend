# db-extract

One container that dumps a MySQL database: a full `mysqldump` and one TSV per
table, in one `tar.gz`. It runs once and exits.

Image: `ghcr.io/tanghyd/gnl-db-extract:latest` (built by the `DB extract image`
workflow on every push to `main` that touches this directory).

## Run it from Portainer

Add a container on the same network as the MySQL container (prod: `gnl-network`):

| env | value |
| --- | --- |
| `DB_HOST` | the MySQL container name (prod: `gnl-mysql`) |
| `DB_USER`, `DB_PASSWORD`, `DB_NAME` | the values the backend uses |
| `BLOB_SAS_URL` | optional. A write SAS URL for one blob; the archive is PUT there |

Mount a volume on `/out` if you want the archive on the box instead of, or as
well as, the blob.

Equivalent command line:

    docker run --rm --network gnl-network -v gnl-extract:/out \
      -e DB_HOST=gnl-mysql -e DB_USER=... -e DB_PASSWORD=... -e DB_NAME=GYM_BACKEND \
      -e BLOB_SAS_URL='https://<account>.blob.core.windows.net/<container>/<name>.tar.gz?<sas>' \
      ghcr.io/tanghyd/gnl-db-extract:latest

## Load tables into Postgres

`load-tables.sh` copies named tables from the archive into a Postgres database
whose schema is at `alembic upgrade head`. Tables must be empty; ids are kept
and the `id` sequence is moved past the highest id.

    deploy/db-extract/load-tables.sh GYM_BACKEND-<stamp>.tar.gz "$DB_URL" \
      koth_events koth_signups koth_matches koth_match_participants

Order parents before children. The KOTH tables reference nothing outside
themselves, so this is the whole KOTH move.
