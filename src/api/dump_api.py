import csv
import io
import zipfile
from datetime import datetime, timezone

from flask import Blueprint, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import inspect, text

dump_blueprint = Blueprint('dump_api', __name__)


@dump_blueprint.route('/dump', methods=['GET'])
@jwt_required()
def dump():
    """Every table as CSV (NULL written as \\N) plus schema.sql, in one zip. Requires a bearer token."""
    engine = dump_blueprint.engine
    buf = io.BytesIO()
    with engine.connect() as conn, zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        schema = []
        for table in inspect(engine).get_table_names():
            schema.append(conn.execute(text(f'SHOW CREATE TABLE `{table}`')).one()[1] + ';\n')
            rows = conn.execute(text(f'SELECT * FROM `{table}`'))
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(rows.keys())
            writer.writerows([r'\N' if v is None else v for v in row] for row in rows)  # NULL vs '' stay distinct
            zf.writestr(f'{table}.csv', out.getvalue())
        zf.writestr('schema.sql', '\n'.join(schema))
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{engine.url.database}-{stamp}.zip')
