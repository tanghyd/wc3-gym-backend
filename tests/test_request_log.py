"""The request id and the request log line.

The application puts the filter on the handlers that basicConfig makes.
The caplog fixture installs its own handler, so these tests put the same
filter on it.
"""

import logging
import re
from typing import Any

import pytest
from httpx2 import Client

from app.core.logging import LOG_FORMAT, request_id_filter

REQUEST_LINE = re.compile(
    r"^request id=(?P<id>\S+) method=(?P<method>\S+) path=(?P<path>\S+) "
    r"status=(?P<status>\d+) dur_ms=(?P<dur_ms>\S+)$"
)


@pytest.fixture(autouse=True)
def stamped_caplog(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    caplog.handler.addFilter(request_id_filter)


def request_lines(caplog: pytest.LogCaptureFixture) -> list[re.Match[str]]:
    found = [REQUEST_LINE.match(record.getMessage()) for record in caplog.records]
    return [match for match in found if match is not None]


def test_request_line_holds_the_fields(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    resp = client.get("/maps")
    assert resp.status_code == 200

    (line,) = request_lines(caplog)
    assert re.fullmatch(r"[0-9a-f]{8}", line["id"])
    assert line["method"] == "GET"
    assert line["path"] == "/maps"
    assert line["status"] == "200"
    assert float(line["dur_ms"]) >= 0


def test_request_line_holds_the_query_string(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    client.get("/user-info", params={"battleTag": "Nobody#1"})

    (line,) = request_lines(caplog)
    assert line["path"] == "/user-info?battleTag=Nobody%231"


def test_two_requests_get_two_ids(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    client.get("/maps")
    client.get("/maps")

    first, second = request_lines(caplog)
    assert first["id"] != second["id"]


def test_a_record_in_the_request_holds_the_request_id(
    client: Client, seeded: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """The 404 handler logs. Its record and the request line share the id."""
    resp = client.get("/maps/999999")
    assert resp.status_code == 404

    (line,) = request_lines(caplog)
    handler_records = [record for record in caplog.records if record.name == "app.main"]
    assert handler_records
    for record in handler_records:
        assert record.request_id == line["id"]


def test_a_record_outside_a_request_holds_a_dash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logging.getLogger("tests.outside").info("no request here")

    (record,) = caplog.records
    assert record.request_id == "-"
    assert "[-]" in logging.Formatter(LOG_FORMAT).format(record)
