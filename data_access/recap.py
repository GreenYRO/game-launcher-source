"""The recap's queries (Phase 96): the figures of one period -- a month, a year -- and nothing new.

Every figure on the recap card is one of these, and every one that counts sessions starts from the
reports' own `sessions` CTE (data_access/reports.py: a session counts when its game is not marked a
tool, installed or not), so the card, the Stats page and report 5 count the same sessions. A period
is half-open, [start, end), in local wall time as `session.started_local` holds it -- a session at
23:59 on the 31st belongs to that month, one at 00:00 on the 1st to the next -- and a session counts
in the period it began in, whole, as the chart and the reports count it.

Nothing here writes: the queries run through `Reports.rows`, with SQLite's `query_only` on.
"""

from __future__ import annotations

from data_access import reports as reports_module

SESSIONS = reports_module.SESSIONS  # the one rule, never redefined here
IN_PERIOD = "started_local >= :start AND started_local < :end"

# A game is its name here: one game installed twice is two records (a reinstall into another folder, a
# version from another source -- four games so on the user's library, S.T.A.L.K.E.R. 2's 1130 minutes
# split 889 and 241), and the card counts it once, as a person would.
TOTALS = f"""WITH {SESSIONS}
SELECT COUNT(*)                              AS sessions,
       COALESCE(SUM(s.minutes), 0)           AS minutes,
       COUNT(DISTINCT lower(v.name))         AS games,
       COALESCE(SUM(s.origin = 'observed'), 0) AS observed,
       MIN(s.started_local)                  AS first,
       MAX(s.started_local)                  AS last
FROM sessions s
JOIN v_library v ON v.id = s.game_id
WHERE s.{IN_PERIOD.replace(" AND ", " AND s.")}"""

# The games played in the period, the most time first; a tie goes to the name. A game's records together:
# the installed one's name and key (its tile's cover), else the first; any record's appid and cover.
GAMES = f"""WITH {SESSIONS}
SELECT COALESCE(MAX(CASE WHEN v.installed = 1 THEN v.name END), MIN(v.name))                 AS name,
       COALESCE(MAX(CASE WHEN v.installed = 1 THEN v.identity_key END), MIN(v.identity_key)) AS identity_key,
       MAX(v.steam_appid) AS steam_appid, MAX(v.installed) AS installed, MAX(g.cover_path) AS cover_path,
       SUM(s.minutes) AS minutes, COUNT(*) AS sessions
FROM sessions s
JOIN v_library v ON v.id = s.game_id
JOIN game g      ON g.id = s.game_id
WHERE s.{IN_PERIOD.replace(" AND ", " AND s.")}
GROUP BY lower(v.name)
ORDER BY minutes DESC, name COLLATE NOCASE
LIMIT :top"""

LONGEST = f"""WITH {SESSIONS}
SELECT v.name, s.minutes, s.started_local
FROM sessions s
JOIN v_library v ON v.id = s.game_id
WHERE s.{IN_PERIOD.replace(" AND ", " AND s.")}
ORDER BY s.minutes DESC, s.started_local, v.name
LIMIT 1"""

# Report 5's hours and weekdays (session_hours, session_weekdays), for one period.
HOURS = f"""WITH {SESSIONS}
SELECT local_hour AS hour, COUNT(*) AS sessions, SUM(minutes) AS minutes
FROM sessions
WHERE {IN_PERIOD}
GROUP BY local_hour
ORDER BY local_hour"""

WEEKDAYS = f"""WITH {SESSIONS}
SELECT CAST(strftime('%w', substr(started_local, 1, 10)) AS INTEGER) AS weekday,  -- 0 Sunday
       COUNT(*)     AS sessions,
       SUM(minutes) AS minutes
FROM sessions
WHERE {IN_PERIOD}
GROUP BY weekday
ORDER BY weekday"""

# Report 5's months -- the Stats chart's stats_months -- for one period: a year's twelve bars.
MONTHS = f"""WITH {SESSIONS}
SELECT CAST(substr(started_local, 1, 4) AS INTEGER) AS year,
       CAST(substr(started_local, 6, 2) AS INTEGER) AS month,
       SUM(minutes) AS minutes,
       COUNT(*)     AS sessions
FROM sessions
WHERE {IN_PERIOD}
GROUP BY year, month
ORDER BY year, month"""

# When the history the card can see begins: a month that began before it was not fully recorded.
HISTORY = f"""WITH {SESSIONS}
SELECT MIN(started_local) AS first
FROM sessions"""

# Every session that counts, for the Stats page (logic/stats.py), which works its figures out of them.
COUNTED = f"""WITH {SESSIONS}
SELECT game_id, started_at, minutes, origin
FROM sessions
ORDER BY started_at"""

# Games new to the library in the period: first seen in it, after the library's first day (game.first_seen is local time with its
# offset; its first 19 characters are the wall time, as started_local is), with a name of its own,
# not a game by the grid's rule a tool, not a later install of one already there -- carried over
# (lineage), or a name the library knew before -- and the time played on it in the period.
NEW_GAMES = f"""WITH {SESSIONS}
SELECT v.name, g.first_seen,
       (SELECT COALESCE(SUM(s.minutes), 0) FROM sessions s
        WHERE s.game_id = g.id AND s.{IN_PERIOD.replace(" AND ", " AND s.")}) AS minutes
FROM game g
JOIN v_library v ON v.id = g.id
WHERE substr(g.first_seen, 1, 19) >= :start AND substr(g.first_seen, 1, 19) < :end
  -- what the first scan found was there already: the library's first day is no game's arrival
  AND substr(g.first_seen, 1, 10) > (SELECT substr(MIN(first_seen), 1, 10) FROM game)
  AND v.name <> g.identity_key
  AND COALESCE(g.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
  AND COALESCE(v.is_tool, CASE WHEN v.app_type IS NOT NULL AND v.app_type <> 'game'
                                AND v.appid_source = 'manifest' THEN 1 ELSE 0 END) = 0
  AND NOT EXISTS (SELECT 1 FROM lineage l WHERE l.game_id = g.id AND l.relation = 'carried_from')
  AND NOT EXISTS (SELECT 1 FROM game o JOIN v_library ov ON ov.id = o.id
                  WHERE o.id <> g.id AND lower(ov.name) = lower(v.name) AND o.first_seen < g.first_seen)
ORDER BY minutes DESC, g.first_seen, v.name COLLATE NOCASE"""

# What was paid in the period, by the day it was bought; a purchase with no such day belongs to none.
PURCHASES = """SELECT v.name, pu.paid_cents, pu.currency, pu.bought_on
FROM purchase pu
JOIN v_library v ON v.id = pu.game_id
WHERE pu.bought_on >= :start_day AND pu.bought_on < :end_day
ORDER BY pu.bought_on, v.name COLLATE NOCASE"""

# The wished games' largest fall in price seen inside the period: one observation against the one
# before it, in the same currency. price_snapshot.observed_at is UTC, so the bounds are too.
WISHLIST_DROP = """WITH steps AS (
    SELECT p.appid, p.observed_at, p.final_cents, p.currency,
           LAG(p.final_cents) OVER (PARTITION BY p.appid ORDER BY p.observed_at) AS before_cents,
           LAG(p.currency)    OVER (PARTITION BY p.appid ORDER BY p.observed_at) AS before_currency
    FROM price_snapshot p
    WHERE p.kind = 'priced'
      AND p.appid IN (SELECT appid FROM v_wishlist_now WHERE lists > 0))
SELECT s.name, st.before_cents, st.final_cents, st.currency, st.observed_at
FROM steps st
JOIN steam_app s ON s.appid = st.appid
WHERE st.observed_at >= :start_utc AND st.observed_at < :end_utc
  AND st.before_currency = st.currency AND st.before_cents > st.final_cents
ORDER BY st.before_cents - st.final_cents DESC, s.name
LIMIT 1"""

# Report 6's wishlist figures (money_wishlist): how many wished games are on sale today.
WISHLIST_NOW = reports_module.MONEY_WISHLIST

# Whether the library has Steam games at all: then the card says what of Steam it cannot see.
STEAM_GAMES = """SELECT COUNT(*) AS games
FROM v_library
WHERE installed = 1 AND source = 'steam'"""

QUERIES: dict[str, str] = {
    "recap_totals": TOTALS,
    "recap_games": GAMES,
    "recap_longest": LONGEST,
    "recap_hours": HOURS,
    "recap_weekdays": WEEKDAYS,
    "recap_months": MONTHS,
    "recap_history": HISTORY,
    "recap_counted": COUNTED,
    "recap_new_games": NEW_GAMES,
    "recap_purchases": PURCHASES,
    "recap_wishlist_drop": WISHLIST_DROP,
    "recap_wishlist_now": WISHLIST_NOW,
    "recap_steam_games": STEAM_GAMES,
}


class Recap(reports_module.Reports):
    """The queries above on one connection -- the window's store's -- each read-only (`query_only`)."""

    queries = QUERIES
