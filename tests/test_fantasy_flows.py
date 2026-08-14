"""The fantasy write flows: score calculation, bets, team players.

The seeded league has one fantasy team with no drafted players. Its
captain P1 won the only played series 2-1 with a 10-point bet on
himself, and his race (HU) won its only series, so the race takes the
18 first-place points of week 1.
"""

from typing import Any

from httpx2 import Client


def get_json(client: Client, path: str) -> Any:  # noqa: ANN401  # a JSON body
    resp = client.get(path)
    assert resp.status_code == 200
    return resp.json()


def test_calculate_writes_totals_and_bet_results(
    client: Client, seeded: dict[str, Any], auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        f"/fantasy/season/{seeded['season_id']}/calculate/", headers=auth_headers
    )
    assert resp.status_code == 204

    team = get_json(client, f"/fantasy/teams/{seeded['fantasy_team_id']}")
    assert team["player_points"] == 0
    assert team["bench_points"] == 0
    assert team["team_points"] == 0
    assert team["race_points"] == 18
    assert team["bet_points"] == 10
    assert team["total_points"] == 28

    bets = get_json(client, "/fantasy/bets")
    assert bets[0]["bet_result"] == 10


def test_calculate_scores_drafted_players(
    client: Client, seeded: dict[str, Any], auth_headers: dict[str, str]
) -> None:
    """A drafted player earns series points for played weeks and bench
    points for the weeks without a series."""
    team_id = seeded["fantasy_team_id"]
    p1 = seeded["player_ids"][0]
    resp = client.post(
        f"/fantasy/teams/addPlayers/{team_id}",
        json={"player_ids": [p1]},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/fantasy/season/{seeded['season_id']}/calculate/", headers=auth_headers
    )
    assert resp.status_code == 204

    team = get_json(client, f"/fantasy/teams/{team_id}")
    # Week 1: won 2-1 = 8 points. Weeks 2-4: no series = 3 * 5 bench points.
    assert team["player_points"] == 8
    assert team["bench_points"] == 15
    assert team["total_points"] == 8 + 15 + 18 + 10


def test_breakdown_answers_the_race_value(
    client: Client, seeded: dict[str, Any]
) -> None:
    """The public page keys its race icons by the plain value ("HU"),
    so the breakdown must never answer the enum repr ("Race.HU")."""
    body = get_json(
        client,
        f"/fantasy/teams/{seeded['fantasy_team_id']}"
        f"/season/{seeded['season_id']}/breakdown",
    )
    race_breakdown = body["race_breakdown"]
    assert race_breakdown["race"] == "HU"
    assert race_breakdown["total_points"] == 18
    assert race_breakdown["all_race_points"] == {"HU": 18}


def test_bet_update_without_bet_points_keeps_them(
    client: Client, seeded: dict[str, Any], auth_headers: dict[str, str]
) -> None:
    bet = get_json(client, "/fantasy/bets")[0]
    other_player = seeded["player_ids"][2]
    resp = client.put(
        f"/fantasy/bets/{bet['id']}",
        json={"winner_id": other_player},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    updated = get_json(client, f"/fantasy/bets/{bet['id']}")
    assert updated["winner_id"] == other_player
    assert updated["bet_points"] == 10


def test_bet_update_carrying_bet_points_validates_them(
    client: Client, seeded: dict[str, Any], auth_headers: dict[str, str]
) -> None:
    bet = get_json(client, "/fantasy/bets")[0]
    for bad_value in (0, ""):
        resp = client.put(
            f"/fantasy/bets/{bet['id']}",
            json={"bet_points": bad_value},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "bet_points" in resp.json()["error"]


def test_calculate_twice_is_stable(
    client: Client, seeded: dict[str, Any], auth_headers: dict[str, str]
) -> None:
    path = f"/fantasy/season/{seeded['season_id']}/calculate/"
    assert client.post(path, headers=auth_headers).status_code == 204
    first = get_json(client, f"/fantasy/teams/{seeded['fantasy_team_id']}")
    assert client.post(path, headers=auth_headers).status_code == 204
    second = get_json(client, f"/fantasy/teams/{seeded['fantasy_team_id']}")
    assert first == second
