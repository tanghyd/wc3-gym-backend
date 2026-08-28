import logging
import os
import urllib.parse
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import requests

from app.core.exceptions import ExternalServiceError, NotFoundError, W3CThrottledError
from app.models.enums import Race
from app.models.w3c_ladder_match import W3CLadderMatchCreate
from app.models.w3c_stats import W3CStatsCreate

if TYPE_CHECKING:
    from app.services.settings import SettingsService

logger = logging.getLogger(__name__)

# Seconds a w3champions call can hold the thread before it fails.
REQUEST_TIMEOUT = 10

# The w3champions API base, used when neither the setting nor the environment names one.
DEFAULT_BASE_URL = "https://website-backend.w3champions.com/api"

# What the admin reads when w3champions turns the sync away.
THROTTLED_MESSAGE = "W3Champions throttled the sync, try again in a few minutes"

# Matches per match search call, the largest page w3champions serves.
MATCH_PAGE_SIZE = 100

# Seasons the match walk may step back from the one it starts at. The search
# needs a season id and w3champions publishes no season dates, so a window
# that reaches into an older season is walked, not looked up.
MATCH_SEASON_STEPS = 4

# One connection pool for every w3champions call, so a sync pays no new TCP handshake.
_session = requests.Session()


def _is_throttled(response: requests.Response) -> bool:
    """W3Champions turns a burst away with 429, or with 503 and a Retry-After."""
    if response.status_code == 429:
        return True
    return response.status_code == 503 and "Retry-After" in response.headers


class W3CService:
    def __init__(self, settings_app_service: "SettingsService | None" = None) -> None:
        self.settings_app_service = settings_app_service

    GET = "GET"

    def _setting(self, key: str) -> str | None:
        """A settings value, or None when the row is absent."""
        if not self.settings_app_service:
            return None
        try:
            setting = self.settings_app_service.get_setting(key)
        except NotFoundError:
            return None
        return setting.get("value") if setting else None

    def base_url(self) -> str:
        """The w3champions API base: the setting, then the environment, then the default."""
        url = self._setting("w3c_url") or os.getenv("W3C_URL") or DEFAULT_BASE_URL
        # Configuration written before the base URL split stored the players endpoint.
        return url.rstrip("/").removesuffix("/players")

    def latest_season(self) -> int:
        """The newest season w3champions lists."""
        seasons = self.send_request(
            method=self.GET, url=f"{self.base_url()}/ladder/seasons"
        )
        return max(int(season["id"]) for season in seasons)

    def current_season(self) -> int:
        """The configured season, or the newest one w3champions lists."""
        season = self._setting("current_wc3_season")
        return int(season) if season else self.latest_season()

    def validate_player(self, bnet_name: str) -> bool:
        """
        Validate that a player exists on W3Champions.
        Uses the /players endpoint which is simpler and doesn't require season info.
        Returns True if player exists, False otherwise.
        """
        try:
            result = self.send_request(
                method=self.GET,
                url=f"{self.base_url()}/players/{urllib.parse.quote(bnet_name)}",
            )
            # If we get a successful response, the player exists
            return result is not None
        except Exception as e:
            logger.debug(f"Player validation failed for {bnet_name}: {e!s}")
            return False

    def get_player_stats(
        self, bnet_name: str, season_override: int | None = None
    ) -> list[W3CStatsCreate]:
        season_to_fetch = (
            season_override if season_override is not None else self.current_season()
        )

        param = {"gateWay": 20, "season": season_to_fetch}
        result = self.send_request(
            method=self.GET,
            url=f"{self.base_url()}/players/{urllib.parse.quote(bnet_name)}/game-mode-stats",
            params=param,
        )
        if not result:
            # A season the player did not play is an empty answer, not a failure
            logger.debug(f"no stats found for player {bnet_name} on w3c")
            return []
        stats: list[W3CStatsCreate] = []
        for gmode_stats in result:
            if gmode_stats.get("gameMode") and gmode_stats.get("gameMode") == 1:
                stats.append(
                    W3CStatsCreate(
                        wc3_season=gmode_stats.get("season"),
                        wins=gmode_stats.get("wins"),
                        losses=gmode_stats.get("losses"),
                        games=gmode_stats.get("games"),
                        mmr=gmode_stats.get("mmr"),
                        winrate=gmode_stats.get("winrate"),
                        race=self.get_race_enum(gmode_stats.get("race")),
                        league=gmode_stats.get("leagueOrder"),
                    )
                )
        return stats

    def get_player_matches(
        self, battle_tag: str, season: int, since: datetime
    ) -> list[W3CLadderMatchCreate]:
        """Every 1v1 match this player started at or after `since`.

        Pages the season newest first and steps back a season while the
        oldest match seen is still newer than `since`.
        """
        rows: dict[str, list[W3CLadderMatchCreate]] = {}
        empty_seasons = 0
        for step in range(MATCH_SEASON_STEPS + 1):
            current = season - step
            if current < 0:
                break
            reached, seen = self._page_season(battle_tag, current, since, rows)
            empty_seasons = 0 if seen else empty_seasons + 1
            # Two silent seasons in a row mean the player has nothing older
            if reached or empty_seasons == 2:
                break
        matches = [row for match_rows in rows.values() for row in match_rows]
        return sorted(matches, key=lambda row: row.start_time)

    def _page_season(
        self,
        battle_tag: str,
        season: int,
        since: datetime,
        rows: dict[str, list[W3CLadderMatchCreate]],
    ) -> tuple[bool, bool]:
        """Page one season into `rows`. Answers whether `since` was reached
        and whether the season held any match.

        Matches are keyed by their w3champions id, so a match that arrives at
        the head between two calls cannot land twice.
        """
        offset = 0
        seen = False
        while True:
            body = self.send_request(
                method=self.GET,
                url=f"{self.base_url()}/matches/search",
                params={
                    "playerId": battle_tag,
                    "gateway": 20,
                    "gameMode": 1,
                    "season": season,
                    "pageSize": MATCH_PAGE_SIZE,
                    "offset": offset,
                },
            )
            page = (body or {}).get("matches") or []
            if not page:
                return False, seen
            seen = True
            oldest = None
            for match in page:
                parsed = self.parse_match(match)
                if not parsed:
                    continue
                rows[match["id"]] = parsed
                start = parsed[0].start_time
                oldest = start if oldest is None else min(oldest, start)
            if oldest is not None and oldest < since:
                return True, seen
            if len(page) < MATCH_PAGE_SIZE:
                return False, seen
            offset += len(page)

    def parse_match(self, match: dict[str, Any]) -> list[W3CLadderMatchCreate]:
        """One row per player of a 1v1 match. Anything else answers nothing."""
        players = [
            team["players"][0]
            for team in match.get("teams") or []
            if team.get("players")
        ]
        if len(players) != 2:
            return []
        start_time = datetime.fromisoformat(match["startTime"]).astimezone(UTC)
        return [
            W3CLadderMatchCreate(
                battleTag=player["battleTag"],
                w3c_match_id=match["id"],
                wc3_season=match["season"],
                start_time=start_time.replace(tzinfo=None),
                duration_s=match["durationInSeconds"],
                map_name=match.get("mapName"),
                race=self._played_race(player),
                opp_battletag=opponent.get("battleTag"),
                opp_race=self._played_race(opponent),
                won=bool(player.get("won")),
                mmr_before=player.get("oldMmr"),
                mmr_after=player.get("currentMmr"),
            )
            for player, opponent in zip(players, reversed(players), strict=True)
        ]

    def _played_race(self, player: dict[str, Any]) -> Race | None:
        """The race the player played: the random pick when the pick is known."""
        race = self.get_race_enum(player.get("race"))
        if race is Race.RANDOM:
            return self.get_race_enum(player.get("rndRace")) or Race.RANDOM
        return race

    def get_race_enum(self, race_int: int | None) -> Race | None:
        if race_int is None:
            return None
        race_mapping = {0: Race.RANDOM, 8: Race.UD, 1: Race.HU, 4: Race.NE, 2: Race.OC}
        race = race_mapping.get(race_int)
        return race

    def send_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> Any:  # noqa: ANN401  # the w3champions body has no fixed shape
        try:
            # Send the request
            response = _session.request(
                method,
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            if _is_throttled(response):
                raise W3CThrottledError(THROTTLED_MESSAGE)

            # Check the status code
            if response.status_code in [200, 201]:
                try:
                    return response.json()  # Parse JSON response
                except ValueError:
                    raise ExternalServiceError(response.text)
            if response.status_code == 204:
                return response.text
            else:
                # Log or raise an error for non-200 status codes
                raise ExternalServiceError(
                    f"Request failed with status code {response.status_code}: {response.text}"
                )

        except requests.exceptions.RequestException as e:
            # Handle network-related errors
            raise ExternalServiceError(f"An exception occurred: {e!s}")
