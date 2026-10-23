"""For you's queries (Phase 98): the genres it compares by, how long each game's sessions run, and -- for
report 9's look back -- when each game arrived and was first played.

Built on the reports' own rules, never a second copy of one. The waiting games are report 4's own rows:
For you reads the `backlog` query itself (data_access/reports.py: INSTALLED, and BACKLOG_STATE's 'never' or
'under'), and logic/recommend.waiting keeps the ones the user can see -- not hidden, not Finished or
Dropped, not played in the last FORYOU_RECENT_DAYS. The sessions are report 5's `sessions` (a game not
marked a tool, installed or not, both origins). The fit itself is logic/fit.py's, fed by the wishlist's
own profile and IDF queries (`wishlist_profile`, `wishlist_idf`).

The queries below join the reports' own (`reports_module.QUERIES`) as this module loads, so every reports
runner answers them -- report 9 is built from them. Nothing here writes: they run through `Reports.rows`,
with SQLite's `query_only` on.
"""

from __future__ import annotations

from data_access import reports as reports_module

R = reports_module

# The genres of every Steam app the library knows, the ones the wishlist compares by: For you's waiting
# games, report 9's look back at what was waiting then, and its taste (report 1's games, with these).
GENRES = """SELECT sg.appid, genre.id AS genre_id, genre.name
FROM steam_app_genre sg
JOIN genre ON genre.id = sg.genre_id
WHERE genre.id NOT IN (SELECT value FROM json_each(:not_genres))
ORDER BY sg.appid, genre.name"""

# Every counted session with its game -- by name, as the recap counts a game (Phase 96) -- and whether that
# record is one the user can play tonight: installed by the grid's rule, not hidden, not Dropped.
SESSION_LENGTHS = f"""WITH {R.SESSIONS},
{R.INSTALLED_TITLES}
SELECT lower(v.name) AS name_key, v.name, v.identity_key, v.id AS game_id, v.steam_appid, s.minutes, s.started_local,
       CASE WHEN v.id IN (SELECT id FROM installed) AND v.hidden = 0
                 AND COALESCE(v.status, '') <> :dropped THEN 1 ELSE 0 END  AS offered
FROM sessions s
JOIN v_library v ON v.id = s.game_id
ORDER BY name_key, s.started_local"""

# Report 9's look back: every game not marked a tool, the day it was first seen -- the stand-in for the day
# it arrived, as the launcher keeps no install date -- its first counted session, and whether Steam counts
# hours for it on the accounts marked yours (those hours have no dates: its first play may come earlier).
HISTORY = f"""WITH {R.SESSIONS},
first AS (SELECT game_id, MIN(started_local) AS first_played FROM sessions GROUP BY game_id)
SELECT v.id AS game_id, v.name, v.steam_appid, substr(v.first_seen, 1, 19) AS first_seen_local,
       f.first_played,
       CASE WHEN m.minutes > 0 THEN 1 ELSE 0 END AS steam_counted
FROM v_library v
LEFT JOIN first f             ON f.game_id = v.id
LEFT JOIN v_steam_time_mine m ON m.appid = v.steam_appid
WHERE COALESCE(v.is_tool, 0) = 0
ORDER BY v.id"""

# Left behind (Phase 103): the games marked Playing -- installed, not hidden, not marked a tool -- each with its last
# counted session (the one rule, `sessions`), its other dates of play (the launcher's, its store's, Steam's), the
# moments its mark was set and its nudge last answered, and its hours as the reports count them (v_hours, once).
LEFT_BEHIND = f"""WITH {R.SESSIONS},
last AS (SELECT game_id, MAX(started_at) AS last_session FROM sessions GROUP BY game_id),
hours AS MATERIALIZED (SELECT appid, game_id, minutes FROM v_hours)
SELECT v.identity_key, v.name, v.steam_appid, g.status_changed_at, g.nudged_at, l.last_session,
       v.last_played, v.store_last_played, m.last_played AS steam_last_played, h.minutes
FROM v_library v
JOIN game g                   ON g.id = v.id
LEFT JOIN last l              ON l.game_id = v.id
LEFT JOIN v_steam_time_mine m ON m.appid = v.steam_appid
LEFT JOIN hours h             ON h.appid = v.steam_appid OR (v.steam_appid IS NULL AND h.game_id = v.id)
WHERE v.status = :playing AND v.installed = 1 AND v.hidden = 0 AND COALESCE(v.is_tool, 0) = 0
ORDER BY v.name COLLATE NOCASE"""

QUERIES: dict[str, str] = {
    "recommend_genres": GENRES,
    "session_lengths_by_game": SESSION_LENGTHS,
    "recommend_history": HISTORY,
}

# Report 9 reads them too: every reports runner answers them (data_access/reports.py imports this module last).
reports_module.QUERIES.update(QUERIES)

# The page's own (Phase 103): For you asks them, no report is built from them.
PAGE_QUERIES: dict[str, str] = {
    "left_behind": LEFT_BEHIND,
}


class Recommend(reports_module.Reports):
    """The queries above and the reports' own (report 4's backlog, the wishlist's profile and IDF) on one
    connection, read-only."""

    queries = {**reports_module.QUERIES, **QUERIES, **PAGE_QUERIES}
