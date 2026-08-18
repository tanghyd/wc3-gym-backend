> [!NOTE]
> Written by Claude.

## Problem

`GET /fantasy/bets` reads the whole database into one answer, and the cost grows with the number of bets.

At 2 seasons and 1,200 bets it took 14 statements, 5,426 rows, 99.4 MB peak and 8.64 s. At 20 seasons and 12,000 bets the process was killed at 5.77 GB. Production holds about 9,250 bets on a 2 GB box.

## Cause

Every bet builds four Public users (`user`, `winner`, `series.player1`, `series.player2`), and each of them carries `w3c_stats`, `gnl_stats` and `signup_seasons`. The bet also builds the season with its map pool. The eager-load options load all of that per bet, so 1,200 bets repeat the same collections 1,200 times.

## Fix

The list route now builds the bet from reduced builders: `UserPublic.from_user_reduced`, `SeriesPublic.from_series_reduced`, `SeasonPublic.from_season_without_maps` and `FantasyBetPublic.from_fantasy_bet_reduced`. They never read a collection attribute, so no lazy load fires, and `FantasyBet.list_eager_options` keeps only the to-one joins.

Every JSON key stays and every scalar keeps its value. Only the collections inside the embedded models answer `[]`.

`GET /fantasy/bets/{id}` and `POST /fantasy/bets/search` are untouched.

The keys stay because the consumers are not all known: Nightbot is unseen and two SDKs publish `getAllBets`, so a dropped key can break a caller with no error from the backend. The `search` route already answers this collection-free shape to the same admin store, so the shape is proven in use.

## Proof

| scale | run | stmts | rows | peak MB | s |
| --- | --- | --- | --- | --- | --- |
| 2 seasons, 1,200 bets | before | 14 | 5,426 | 99.4 | 8.64 |
| 2 seasons, 1,200 bets | after | 1 | 1,200 | 20.7 | 1.59 |
| 20 seasons, 12,000 bets | before | - | - | killed at 5.77 GB | - |
| 20 seasons, 12,000 bets | after | 1 | 12,000 | 197.6 | 17.94 |

The 20-season sweep now completes; the process high-water mark is 1.15 GB, and its peak comes from `POST /series/search`, not from the bets.

The OpenAPI schema is byte-identical to main, and so is the `GET /fantasy/bets/{id}` body for the same bet on the same seed. The list body differs from main in 13 places only: `season.maps` and the three collections on each of the four users. Every key path and every scalar matches.

Tests: 239 passed, 1 xfailed. New tests pin the list keys and the empty collections, the full graph of the single-bet route, and one statement for the list.
