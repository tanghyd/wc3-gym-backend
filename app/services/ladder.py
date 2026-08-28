"""Store the w3champions ladder matches of the GNL players.

The ladder page aggregates these rows at read time, so the sync only has to
put every match of every signed-up player in the table once.
"""

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession

from app.core.db import Session
from app.core.exceptions import NotFoundError, W3CThrottledError
from app.models.relationships import DBUserSeasonSignup
from app.models.season import Season
from app.models.user import User, UserReduced
from app.models.w3c_ladder_match import (
    LadderSyncResult,
    W3CLadderMatch,
    W3CLadderMatchCreate,
)
from app.models.w3c_stats import W3CSyncFailure, W3CSyncResult
from app.services.users import W3C_SYNC_WORKERS
from app.services.w3c import THROTTLED_MESSAGE, W3CService

if TYPE_CHECKING:
    from app.services.settings import SettingsService

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """UTC without a zone, the shape the DATETIME columns hold."""
    return datetime.now(UTC).replace(tzinfo=None)


class LadderService:
    """Ladder matches are written by the sync alone, so this service has no CRUD."""

    def __init__(self, settings_app_service: "SettingsService | None" = None) -> None:
        self.settings_app_service = settings_app_service

    def sync_season(
        self, season_id: int, offset: int = 0, limit: int = 10
    ) -> LadderSyncResult:
        """Sync one chunk of the players signed up for the season.

        The window starts at the season start date, so a chunk backfills as
        well as it refreshes.
        """
        with Session.begin() as session:
            season = session.get(Season, season_id)
            if season is None:
                raise NotFoundError("Season not found")
            # A season without a start date reads every match the walk reaches
            since = datetime.combine(season.start_date or date.min, time.min)
            total = session.scalar(
                select(func.count())
                .select_from(DBUserSeasonSignup)
                .where(DBUserSeasonSignup.season_id == season_id)
            )
            rows = session.execute(
                select(User.id, User.name, User.battleTag)
                .join(DBUserSeasonSignup, DBUserSeasonSignup.user_id == User.id)
                .where(DBUserSeasonSignup.season_id == season_id)
                .order_by(User.id)
                .offset(offset)
                .limit(limit)
            ).all()

        users = [
            UserReduced(id=row.id, name=row.name, battleTag=row.battleTag)
            for row in rows
        ]
        result = self.sync_users(users, since)
        done = offset + len(users)
        return LadderSyncResult(
            **result.model_dump(),
            total=total or 0,
            next_offset=done if done < (total or 0) else None,
        )

    def sync_users(self, users: list[UserReduced], since: datetime) -> W3CSyncResult:
        """Store the matches these players started at or after `since`."""
        result = W3CSyncResult()
        if not users:
            return result

        w3c_service = W3CService(settings_app_service=self.settings_app_service)
        season = w3c_service.current_season()
        owners = self._user_ids_by_battle_tag()
        synced: set[int] = set()
        failures: dict[int, str] = {}
        throttled = False

        # Each worker opens its own session; the threads share the engine only
        with ThreadPoolExecutor(W3C_SYNC_WORKERS) as pool:
            futures = {
                pool.submit(self._sync_user, u, w3c_service, season, since, owners): u
                for u in users
            }
            for future in as_completed(futures):
                if future.cancelled():
                    continue
                user = futures[future]
                try:
                    future.result()
                except W3CThrottledError:
                    throttled = True
                    for other in futures:
                        other.cancel()
                except Exception as e:
                    # The reason reaches the client, so it names no statement
                    reason = (
                        "Database error" if isinstance(e, SQLAlchemyError) else str(e)
                    )
                    failures[user.id] = reason
                    logger.warning(
                        f"Failed to sync ladder matches for user {user.name} "
                        f"(BattleTag: {user.battleTag}): {reason}"
                    )
                else:
                    synced.add(user.id)

        if throttled:
            stopped = [u for u in users if u.id not in synced and u.id not in failures]
            for user in stopped:
                failures[user.id] = THROTTLED_MESSAGE
            logger.warning(
                f"W3Champions throttled the sync, {len(stopped)} player(s) not synced"
            )

        # The report follows the order the caller passed, not the order the
        # workers finished in.
        for user in users:
            if user.id in synced:
                result.synced.append(user.id)
            else:
                result.failed.append(
                    W3CSyncFailure(
                        id=user.id,
                        name=user.name,
                        battleTag=user.battleTag,
                        reason=failures[user.id],
                    )
                )
        return result

    def _sync_user(
        self,
        user: UserReduced,
        w3c_service: W3CService,
        season: int,
        since: datetime,
        owners: dict[str, int],
    ) -> None:
        """Fetch one player's matches and write every row a GNL player owns."""
        matches = w3c_service.get_player_matches(user.battleTag, season, since)
        by_user: dict[int, list[W3CLadderMatchCreate]] = defaultdict(list)
        for row in matches:
            # The opponent's row is written from the same payload; the unique
            # index makes his own sync a no-op.
            owner = owners.get(row.battleTag.lower())
            if owner is not None:
                by_user[owner].append(row)

        with Session.begin() as session:
            for user_id, rows in by_user.items():
                self._write_matches(session, user_id, rows)
            # The stamp says when the app last asked, not that matches were found
            session.execute(
                update(User).where(User.id == user.id).values(ladder_synced_at=_now())
            )

    def _write_matches(
        self, session: OrmSession, user_id: int, rows: list[W3CLadderMatchCreate]
    ) -> None:
        """Insert the matches this player has no row for yet."""
        stored = set(
            session.scalars(
                select(W3CLadderMatch.w3c_match_id).where(
                    W3CLadderMatch.user_id == user_id
                )
            )
        )
        for row in rows:
            if row.w3c_match_id in stored:
                continue
            values = row.model_dump(exclude={"battleTag"}) | {"user_id": user_id}
            try:
                # A savepoint, so a lost race rolls back the insert alone
                with session.begin_nested():
                    W3CLadderMatch.add(session, values)
            except IntegrityError:
                # Another worker wrote the row from the opponent's payload
                pass
            stored.add(row.w3c_match_id)

    @staticmethod
    def _user_ids_by_battle_tag() -> dict[str, int]:
        """Every GNL player, keyed by battle tag in lower case."""
        with Session.begin() as session:
            return {
                tag.lower(): user_id
                for user_id, tag in session.execute(select(User.id, User.battleTag))
            }
