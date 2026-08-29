"""Datetime input is stored as naive UTC whatever zone the client sent."""

from datetime import datetime

from app.core.query import QueryUtil
from app.models.series import Series, SeriesUpdate


def test_zoned_input_lands_as_naive_utc() -> None:
    assert SeriesUpdate(date_time="2026-07-05T20:30:00+04:00").date_time == datetime(
        2026, 7, 5, 16, 30
    )
    assert SeriesUpdate(date_time="2026-07-05 20:30:00").date_time == datetime(
        2026, 7, 5, 20, 30
    )
    assert QueryUtil.read_value(
        Series.date_time, "date_time", "2026-07-05T20:30:00Z"
    ) == datetime(2026, 7, 5, 20, 30)
