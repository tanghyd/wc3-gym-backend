"""Our ladder numbers against the ones wc3.no publishes for GNL S18.

Run it with `W3C_ORACLE=1 uv run pytest tests/test_ladder_oracle.py -q`; it
is skipped otherwise, because it calls w3champions for real. It needs no
database: it fetches the matches, applies the scope and core.ladder, and
compares.

EXPECTED is the wc3.no GNL S18 table, read from the live page on
2026-08-27, with the race each player is registered with. Its points column
also carries achievement points, so the comparison rebuilds the ladder
points from its own wins and losses.

The race is part of the scope, not decoration: wc3.no asks w3champions for
one race per player (`playerRace`), and four of these players played other
races beside their league race. Reading every race instead gives kovic 8/3
where wc3.no shows 7/2, and LOSu2 19/22 where it shows 10/12.
"""

import os
from datetime import datetime

import pytest
import requests

from app.core import ladder
from app.models.enums import Race
from app.services.w3c import W3CService

# The real function, captured before conftest blocks third party calls.
REAL_REQUEST = requests.Session.request

# GNL season 18, inclusive at both ends.
START = datetime(2026, 7, 6)
END = datetime(2026, 8, 9, 23, 59, 59, 999999)

# battle tag, league race, wins, losses
EXPECTED = [
    ("thanks#11187", Race.NE, 108, 117),
    # 104/100, not the 103/100 the wc3.no table shows. Every offset from UTC-12 to
    # UTC+14, with the end date inside the window or outside it, was tried against
    # w3champions' own answer and none produces 103/100, while UTC with the end date
    # inside produces 104/100 exactly. His 215 matches are all Night Elf, all
    # distinct and all inside the window, and the race filter changes nothing. So
    # the extra win is one wc3.no did not see, and w3champions is the source.
    ("doctajones#11327", Race.NE, 104, 100),
    ("Psike#1331", Race.UD, 60, 76),
    ("ThreeWayKay#2610", Race.HU, 56, 58),
    ("indrew613#1342", Race.OC, 40, 38),
    ("Elusirei#2178", Race.NE, 39, 37),
    ("Solanum#21803", Race.OC, 20, 6),
    ("MrDrCooper#1551", Race.OC, 22, 5),
    ("MIsTKy#2462", Race.HU, 29, 31),
    ("Gunnar#1165", Race.HU, 22, 31),
    ("ObnoxiousDMG#1727", Race.NE, 21, 6),
    ("Sacktikkla#1398", Race.NE, 12, 15),
    ("kovic#21111", Race.HU, 7, 2),
    ("LOSu2#1716", Race.HU, 10, 12),
    ("Elkiador#1553", Race.HU, 10, 14),
]

pytestmark = pytest.mark.skipif(
    os.getenv("W3C_ORACLE") != "1", reason="set W3C_ORACLE=1 to call w3champions"
)

_season: list[int] = []


def season(service: W3CService) -> int:
    """The newest w3champions season, asked for once."""
    if not _season:
        _season.append(service.latest_season())
    return _season[0]


@pytest.mark.parametrize(("battle_tag", "race", "wins", "losses"), EXPECTED)
def test_our_numbers_match_wc3_no(
    monkeypatch: pytest.MonkeyPatch,
    battle_tag: str,
    race: Race,
    wins: int,
    losses: int,
) -> None:
    """Wins, losses and ladder points over the GNL S18 window."""
    monkeypatch.setattr(requests.Session, "request", REAL_REQUEST)
    service = W3CService()

    matches = service.get_player_matches(battle_tag, season(service), START)
    mine = [
        row
        for row in matches
        if row.battleTag.lower() == battle_tag.lower()
        and row.race is race
        and START <= row.start_time <= END
    ]
    totals = ladder.totals(mine)

    expected_points = ladder.WIN_POINTS * wins + ladder.LOSS_POINTS * losses
    print(
        f"{battle_tag:20} {race.value:6} ours {totals.wins:4}W {totals.losses:4}L "
        f"{totals.points:5}p   wc3.no {wins:4}W {losses:4}L {expected_points:5}p"
    )
    assert (totals.wins, totals.losses, totals.points) == (
        wins,
        losses,
        expected_points,
    )
