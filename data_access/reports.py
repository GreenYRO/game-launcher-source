"""The reports (Phase 83): what the library database can say, one query at a time.

Every report on the Reports page, in `reports.py --markdown` and in docs/ANALIZA.md is built from
the queries below -- SQL a reader can follow, each a module constant so the document quotes it
exactly (a test holds the two together). logic/reports.py shapes the rows into a report; nothing
here formats, and **nothing here writes**: the page's queries run with SQLite's `query_only`
switched on, and the command line opens the file read-only.

Hours come from two sources, and every query says which it reads -- the view v_hours (schema
version 5) puts them side by side: the launcher's own timing of exe games, and Steam's counters
on the accounts marked mine. Two CTEs recur:

  * `games` -- the rows of v_hours that are games: not set aside (rules.STEAM_NOT_GAMES: Spacewar
    and Source SDK Base 2007, whose hours are other games'), not marked as a tool, and either
    marked as a game or of Steam's type "game" or of no type known yet;
  * `installed` -- the installed games by the grid's own rule (a tool by the user's mark, or by
    Steam's type when the store said which app it is), with each one's hours from v_hours.

Local time is read off the stored text (session.started_local, local_hour), never through
SQLite's date functions, which convert to UTC first: a session is wall time with its offset.

**The hours are worked out once for a whole build** (Phase 103, `Reports.worked_out_once`): fifteen of the
queries read v_hours, and each read worked it out again from its tables -- about 1.6 ms each, some 22 of the ten
reports' 46 ms. A temporary table of the same name is made from each of the two views at the start (SQLite looks
in the temporary schema first, so every query's text stays exactly as quoted and reads the copy, one moment's
answer for the whole build) and dropped at the end: 46 -> 24 ms, every answer the same. Nothing reaches the
library file.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from shared import rules

log = logging.getLogger(__name__)

NEEDS_VERSION = 8  # price_target, which money_wishlist joins (Phase 101), and rating, report 10's (Phase 102); before it: v_hours arrives with version 5 (upgrades/005_hours.sql), the wishlist with 6 (Phase 86),
#                   a session's origin with 7 (Phase 93)

GAMES = """games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0)"""

# The same rows worked out once, for a query that reads them more than once (Phase 102): report 8 read `games`
# in two CTEs, and SQLite ran the view behind it twice -- 4.3 ms of the reports' 50, 2.4 once (the same answer).
GAMES_ONCE = GAMES.replace("games AS (", "games AS MATERIALIZED (", 1)

INSTALLED_RULE = """    WHERE v.installed = 1
      AND COALESCE(v.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(v.is_tool,
                   CASE WHEN v.app_type IS NOT NULL AND v.app_type != 'game'
                         AND v.appid_source = 'manifest' THEN 1 ELSE 0 END) = 0)"""

INSTALLED = f"""installed AS (
    SELECT v.*, h.minutes, h.minutes_steam, h.steam_last_played
    FROM v_library v
    LEFT JOIN v_hours h ON h.appid = v.steam_appid
                        OR (v.steam_appid IS NULL AND h.game_id = v.id)
{INSTALLED_RULE}"""

# The same games for a query that needs none of their hours (Phase 91): reading v_hours for nothing
# cost the money report 3 ms of its 3.4 (measured on the user's library, the same rows either way).
INSTALLED_TITLES = f"""installed AS (
    SELECT v.*
    FROM v_library v
{INSTALLED_RULE}"""

# -- 1. Concentration -----------------------------------------------------------------------------

CONCENTRATION = f"""WITH {GAMES}
SELECT ROW_NUMBER() OVER ranked                                         AS rank,
       name, appid, game_id, source, minutes,
       minutes / SUM(minutes) OVER ()                                   AS share,
       SUM(minutes) OVER (ranked ROWS UNBOUNDED PRECEDING)
           / SUM(minutes) OVER ()                                       AS cumulative
FROM games
WHERE minutes > 0
WINDOW ranked AS (ORDER BY minutes DESC, name)
ORDER BY rank"""

# -- 2. Abandonment -------------------------------------------------------------------------------
# Each started app's kind -- paid, free, unknown -- as rules.REPORT_APP_KINDS defines it (Phase 91).

ABANDONMENT = f"""WITH {GAMES},
started AS (
    SELECT g.minutes_steam,
           CASE WHEN s.appid IS NULL OR s.has_record = 0                         THEN 'unknown'
                WHEN s.is_free = 1
                  OR EXISTS (SELECT 1 FROM steam_app_genre f
                             WHERE f.appid = g.appid AND f.genre_id = :free_to_play) THEN 'free'
                ELSE 'paid' END                                                 AS kind
    FROM games g
    LEFT JOIN steam_app s ON s.appid = g.appid
    WHERE g.minutes_steam IS NOT NULL OR g.steam_last_played IS NOT NULL)
SELECT CASE WHEN COALESCE(minutes_steam, 0) < :ten_minutes   THEN 1
            WHEN minutes_steam < :one_hour                   THEN 2
            WHEN minutes_steam < :refund_window              THEN 3
            WHEN minutes_steam < :ten_hours                  THEN 4
            WHEN minutes_steam < :hundred_hours              THEN 5
            ELSE 6 END                                       AS bucket,
       COUNT(*)                                              AS apps,
       SUM(COALESCE(minutes_steam, 0))                       AS minutes,
       SUM(kind = 'paid')                                    AS paid,
       SUM(kind = 'free')                                    AS free,
       SUM(kind = 'unknown')                                 AS unknown
FROM started
GROUP BY bucket
ORDER BY bucket"""

# -- 3. Profiles ----------------------------------------------------------------------------------

PROFILE_COVERAGE = f"""WITH {GAMES}
SELECT SUM(g.minutes)                                                   AS played,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM steam_app_genre sg WHERE sg.appid = g.appid
                             AND sg.genre_id NOT IN (SELECT value FROM json_each(:not_genres)))
                THEN g.minutes END)                                     AS with_genre,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM steam_app_genre sg WHERE sg.appid = g.appid
                             AND sg.genre_id = :free_to_play)
                THEN g.minutes END)                                     AS free_to_play,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM steam_app_company c WHERE c.appid = g.appid
                             AND c.role = 'publisher') THEN g.minutes END) AS with_publisher,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM steam_app_company c WHERE c.appid = g.appid
                             AND c.role = 'developer') THEN g.minutes END) AS with_developer,
       SUM(CASE WHEN s.release_date IS NOT NULL THEN g.minutes END)     AS with_release
FROM games g
LEFT JOIN steam_app s ON s.appid = g.appid
WHERE g.minutes > 0"""

PROFILE_GENRES = f"""WITH {GAMES}
SELECT genre.name                 AS label,
       SUM(g.minutes)             AS minutes,
       COUNT(*)                   AS apps
FROM games g
JOIN steam_app_genre sg ON sg.appid = g.appid
JOIN genre              ON genre.id = sg.genre_id
WHERE g.minutes > 0
  AND genre.id NOT IN (SELECT value FROM json_each(:not_genres))
GROUP BY genre.id
ORDER BY minutes DESC, label"""

# Both roles in one run, split by the role (Phase 98): each run of the games reads the hours again.
PROFILE_COMPANIES = f"""WITH {GAMES}
SELECT c.role,
       company.name               AS label,
       SUM(g.minutes)             AS minutes,
       COUNT(*)                   AS apps
FROM games g
JOIN steam_app_company c ON c.appid = g.appid
                        AND c.role IN (SELECT value FROM json_each(:company_roles))
JOIN company             ON company.id = c.company_id
WHERE g.minutes > 0
GROUP BY c.role, company.id
ORDER BY c.role, minutes DESC, label"""

PROFILE_DECADES = f"""WITH {GAMES}
SELECT substr(s.release_date, 1, 3) || '0s'   AS label,
       SUM(g.minutes)                         AS minutes,
       COUNT(*)                               AS apps
FROM games g
JOIN steam_app s ON s.appid = g.appid
WHERE g.minutes > 0 AND s.release_date IS NOT NULL
GROUP BY label
ORDER BY label"""

# -- 4. Backlog -----------------------------------------------------------------------------------

# A game's state in report 4 -- no time anywhere and no date from its store or Steam is 'never'; under
# REPORT_BACKLOG_UNDER_MINUTES is 'under'; an Epic, Xbox or Ubisoft game with no time seen is 'unknown',
# since its store never says. For you's waiting games are this query's own rows (Phase 98), which is why it
# also carries what For you reads -- the record, whether it is hidden or marked, the three dates of play.
BACKLOG_STATE = """CASE WHEN i.launch_kind != 'exe' AND i.source != 'steam'
                 AND COALESCE(i.minutes, 0) = 0 AND i.last_played IS NULL   THEN 'unknown'
            WHEN COALESCE(i.minutes, 0) = 0 AND i.store_last_played IS NULL
                 AND i.last_played IS NULL AND i.steam_last_played IS NULL THEN 'never'
            WHEN COALESCE(i.minutes, 0) < :backlog_under                THEN 'under'
            ELSE 'played' END"""

BACKLOG = f"""WITH {INSTALLED}
SELECT i.name, i.source, i.launch_kind, i.size_on_disk, i.steam_appid,
       COALESCE(i.minutes, 0)                                           AS minutes,
       p.kind                                                           AS price_kind,
       p.initial_cents, p.final_cents, p.currency,
       {BACKLOG_STATE}                                           AS state,
       i.id AS game_id, i.identity_key, i.hidden, i.status,
       i.last_played, i.store_last_played, i.steam_last_played,
       COALESCE(s.has_record, 0)                                        AS has_record
FROM installed i
LEFT JOIN v_price_latest p ON p.appid = i.steam_appid
LEFT JOIN steam_app s      ON s.appid = i.steam_appid
ORDER BY i.name COLLATE NOCASE"""

# -- 5. Sessions ----------------------------------------------------------------------------------

# The one rule for a session that counts (Phase 96): its game is not marked a tool, installed or not --
# uninstalling a game does not unplay it. The reports, the Stats page and the recap all count with it.
SESSIONS = """sessions AS (
    SELECT s.game_id, s.started_at, s.minutes, s.started_local, s.local_hour, s.origin
    FROM session s JOIN game g ON g.id = s.game_id
    WHERE COALESCE(g.is_tool, 0) = 0)"""

# How each session was measured (Phase 93): timed from the launcher's own start, or seen running.
SESSION_ORIGINS = """SELECT s.origin, COUNT(*) AS sessions, SUM(s.minutes) AS minutes, MIN(s.started_local) AS first
FROM session s JOIN game g ON g.id = s.game_id
WHERE COALESCE(g.is_tool, 0) = 0
GROUP BY s.origin
ORDER BY s.origin"""

SESSION_SUMMARY = f"""WITH {SESSIONS},
ordered AS (SELECT minutes,
                   ROW_NUMBER() OVER (ORDER BY minutes) AS rn,
                   COUNT(*) OVER ()                     AS n
            FROM sessions)
SELECT MAX(n)                                                         AS sessions,
       SUM(minutes)                                                   AS minutes,
       AVG(minutes)                                                   AS mean,
       AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN minutes END) AS median,
       MIN(CASE WHEN rn >= (9 * n + 9) / 10 THEN minutes END)         AS p90,
       (SELECT MIN(started_local) FROM sessions)                      AS first,
       (SELECT MAX(started_local) FROM sessions)                      AS last
FROM ordered"""

SESSION_LENGTHS = f"""WITH {SESSIONS}
SELECT CASE WHEN minutes < :quarter_hour THEN 1
            WHEN minutes < :half_hour    THEN 2
            WHEN minutes < :hour         THEN 3
            WHEN minutes < :two_hours    THEN 4
            ELSE 5 END                   AS bucket,
       COUNT(*)                          AS sessions,
       SUM(minutes)                      AS minutes
FROM sessions
GROUP BY bucket
ORDER BY bucket"""

SESSION_HOURS = f"""WITH {SESSIONS}
SELECT local_hour AS hour, COUNT(*) AS sessions, SUM(minutes) AS minutes
FROM sessions
GROUP BY local_hour
ORDER BY local_hour"""

SESSION_WEEKDAYS = f"""WITH {SESSIONS}
SELECT CAST(strftime('%w', substr(started_local, 1, 10)) AS INTEGER) AS weekday,  -- 0 Sunday
       COUNT(*)     AS sessions,
       SUM(minutes) AS minutes
FROM sessions
GROUP BY weekday
ORDER BY weekday"""

# -- 6. Money -------------------------------------------------------------------------------------

MONEY_LIBRARY = f"""WITH {INSTALLED_TITLES},
titles AS (SELECT DISTINCT steam_appid FROM installed WHERE steam_appid IS NOT NULL)
SELECT (SELECT COUNT(*) FROM installed)                               AS games,
       (SELECT COUNT(*) FROM installed WHERE steam_appid IS NULL)     AS no_app,
       COUNT(*)                                                       AS titles,
       SUM(p.kind = 'priced')                                         AS priced,
       SUM(p.kind = 'free')                                           AS free,
       SUM(p.kind = 'unavailable')                                    AS unavailable,
       SUM(p.kind IS NULL)                                            AS never_priced,
       SUM(p.kind = 'priced' AND p.discount_percent > 0)              AS on_sale,
       SUM(CASE WHEN p.kind = 'priced' THEN p.initial_cents END)      AS list_cents,
       SUM(CASE WHEN p.kind = 'priced' THEN p.final_cents END)        AS today_cents,
       COUNT(DISTINCT p.currency)                                     AS currencies,
       MIN(p.currency)                                                AS currency
FROM titles t
LEFT JOIN v_price_latest p ON p.appid = t.steam_appid"""

MONEY_PAID = """SELECT v.name, pu.purchases, pu.paid_cents, pu.currency, pu.currencies,
       h.minutes,
       CASE WHEN pu.currencies = 1 AND h.minutes > 0
            THEN pu.paid_cents * 60.0 / h.minutes END                 AS cents_per_hour
FROM (SELECT game_id, COUNT(*) AS purchases, SUM(paid_cents) AS paid_cents,
             MIN(currency) AS currency, COUNT(DISTINCT currency) AS currencies
      FROM purchase GROUP BY game_id) pu
JOIN v_library v ON v.id = pu.game_id
LEFT JOIN v_hours h ON h.appid = v.steam_appid
                    OR (v.steam_appid IS NULL AND h.game_id = v.id)
ORDER BY v.name COLLATE NOCASE"""

MONEY_PROXY = f"""WITH {GAMES}
SELECT g.name, g.minutes, p.initial_cents, p.currency,
       p.initial_cents * 60.0 / g.minutes      AS cents_per_hour
FROM games g
JOIN v_price_latest p ON p.appid = g.appid AND p.kind = 'priced'
WHERE g.minutes >= :proxy_min_minutes
  AND NOT EXISTS (SELECT 1 FROM purchase pu JOIN game x ON x.id = pu.game_id
                  WHERE x.steam_appid = g.appid)
ORDER BY cents_per_hour, g.name"""

MONEY_SALES = """SELECT s.name, p.discount_percent, p.initial_cents, p.final_cents, p.currency,
       EXISTS (SELECT 1 FROM game g JOIN install i ON i.game_id = g.id
               WHERE g.steam_appid = p.appid)                         AS installed
FROM v_price_latest p
JOIN steam_app s ON s.appid = p.appid
WHERE p.kind = 'priced' AND p.discount_percent > 0
ORDER BY p.discount_percent DESC, s.name"""

MONEY_LOWEST = f"""WITH {INSTALLED_TITLES},
titles AS (SELECT steam_appid, MIN(name) AS name FROM installed
           WHERE steam_appid IS NOT NULL GROUP BY steam_appid)
SELECT t.name, p.final_cents AS now_cents, p.currency,
       r.lowest_cents, r.lowest_on, r.observations
FROM titles t
JOIN v_price_latest p ON p.appid = t.steam_appid AND p.kind = 'priced'
JOIN v_price_range  r ON r.appid = t.steam_appid
ORDER BY (p.final_cents - r.lowest_cents) DESC, t.name"""

MONEY_WISHLIST = """SELECT COUNT(*)                                                       AS items,
       SUM(kind = 'priced')                                           AS priced,
       SUM(kind = 'free')                                             AS free,
       SUM(kind = 'unavailable')                                      AS unavailable,
       SUM(kind IS NULL)                                              AS never_priced,
       SUM(kind = 'priced' AND discount_percent > 0)                  AS on_sale,
       SUM(CASE WHEN kind = 'priced' THEN initial_cents END)          AS list_cents,
       SUM(CASE WHEN kind = 'priced' THEN final_cents END)            AS today_cents,
       COUNT(DISTINCT w.currency)                                     AS currencies,
       MIN(w.currency)                                                AS currency,
       MIN(observed_at)                                               AS oldest_price,
       COUNT(t.appid)                                                 AS targets,
       SUM(kind = 'priced' AND w.currency = t.currency AND final_cents <= t.cents) AS below_target
FROM v_wishlist_now w
LEFT JOIN price_target t ON t.appid = w.appid
WHERE lists > 0"""

MONEY_SERIES = """SELECT COUNT(*)                 AS observations,
       COUNT(DISTINCT appid)    AS apps,
       MIN(observed_at)         AS first,
       MAX(observed_at)         AS last
FROM price_snapshot"""

# -- 7. Data quality ------------------------------------------------------------------------------

QUALITY_TYPES = """SELECT CASE WHEN appid IS NULL AND marked_tool = 1 THEN 'tool (no Steam app)'
            WHEN appid IS NULL           THEN 'no Steam app (the launcher''s time)'
            WHEN marked_tool = 1         THEN 'tool (marked)'
            WHEN app_type IS NULL        THEN 'unknown (no store record)'
            ELSE app_type END            AS kind,
       COUNT(*)                          AS apps,
       SUM(minutes)                      AS minutes
FROM v_hours
WHERE minutes > 0
  AND COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
GROUP BY kind
ORDER BY minutes DESC"""

QUALITY_SET_ASIDE = """SELECT appid, minutes_steam AS minutes, steam_last_played
FROM v_hours
WHERE appid IN (SELECT value FROM json_each(:set_aside))
ORDER BY appid"""

QUALITY_SOURCES = """SELECT source, COUNT(*) AS apps, SUM(minutes) AS minutes,
       SUM(minutes_launcher) AS minutes_launcher, SUM(minutes_steam) AS minutes_steam
FROM v_hours
WHERE minutes > 0
  AND COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
GROUP BY source
ORDER BY minutes DESC"""

QUALITY_LINKS = """SELECT h.name, h.games, h.minutes_launcher, h.minutes_steam,
       group_concat(DISTINCT g.appid_source) AS linked_by
FROM v_hours h
JOIN game g ON g.steam_appid = h.appid
WHERE h.source = 'both'
GROUP BY h.appid
ORDER BY h.minutes DESC"""

QUALITY_UNTIMED = f"""WITH {INSTALLED}
SELECT name, source,
       CASE WHEN source = 'steam' THEN 'no account marked mine holds it'
            ELSE 'timed only while the launcher watches' END AS why
FROM installed
WHERE (launch_kind != 'exe' AND source != 'steam')
   OR (source = 'steam' AND minutes_steam IS NULL AND steam_last_played IS NULL)
ORDER BY source, name COLLATE NOCASE"""

QUALITY_CURRENCIES = """SELECT currency, COUNT(*) AS observations
FROM price_snapshot
WHERE kind = 'priced'
GROUP BY currency
ORDER BY observations DESC"""

# -- the Stats page's own figures, by SQL: the Python of logic/stats.py is the oracle ---------------
# Its lifetime, most played and sources count the games installed now (its views are the grid's), so
# these do too; its sessions count by the one rule above since Phase 96, so stats_months does.

STATS_LIFETIME = """SELECT SUM(COALESCE(playtime_seconds, 0)) AS seconds,
       (SELECT SUM(COALESCE(playtime_seconds, 0)) FROM game) AS seconds_ever
FROM v_library WHERE installed = 1"""

STATS_TOP = """SELECT name, playtime_seconds AS seconds
FROM v_library
WHERE installed = 1 AND launch_kind = 'exe' AND playtime_seconds > 0
ORDER BY playtime_seconds DESC, name
LIMIT :top"""

STATS_MONTHS = f"""WITH {SESSIONS}
SELECT CAST(substr(started_local, 1, 4) AS INTEGER) AS year,
       CAST(substr(started_local, 6, 2) AS INTEGER) AS month,
       SUM(minutes)                                 AS minutes
FROM sessions
GROUP BY year, month
ORDER BY year, month"""

STATS_SOURCES = """SELECT source, COUNT(*) AS games
FROM v_library
WHERE installed = 1 AND hidden = 0
  AND COALESCE(is_tool, CASE WHEN app_type IS NOT NULL AND app_type != 'game'
                              AND appid_source = 'manifest' THEN 1 ELSE 0 END) = 0
GROUP BY source
ORDER BY games DESC, source"""

# -- The wishlist (Phase 86): what was said to be wanted, beside what is played -----------------

WISHLIST_NOW = """SELECT *
FROM v_wishlist_now
ORDER BY removed_at IS NOT NULL, appid"""

# What the fit line compares with: every game of mine with hours, one row per genre it has (the
# same games and the same genres as report 3, Free To Play and the content descriptors left out).
WISHLIST_PROFILE = f"""WITH {GAMES}
SELECT g.appid, g.minutes, sg.genre_id
FROM games g
JOIN steam_app_genre sg ON sg.appid = g.appid
WHERE g.minutes > 0
  AND sg.genre_id NOT IN (SELECT value FROM json_each(:not_genres))
ORDER BY g.appid, sg.genre_id"""

WISHLIST_GENRES = """SELECT w.appid, genre.id AS genre_id, genre.name
FROM v_wishlist_now w
JOIN steam_app_genre sg ON sg.appid = w.appid
JOIN genre              ON genre.id = sg.genre_id
WHERE genre.id NOT IN (SELECT value FROM json_each(:not_genres))
ORDER BY w.appid, genre.name"""

# How rare each genre is among the apps the library has a Steam record of (Phase 89): what weighs a
# genre in the fit line -- one most games have says little about a game.
WISHLIST_IDF = """SELECT sg.genre_id,
       COUNT(DISTINCT sg.appid)             AS apps,
       (SELECT COUNT(DISTINCT x.appid)
        FROM steam_app_genre x
        JOIN steam_app xs ON xs.appid = x.appid
        WHERE xs.has_record = 1
          AND x.genre_id NOT IN (SELECT value FROM json_each(:not_genres))) AS corpus
FROM steam_app_genre sg
JOIN steam_app s ON s.appid = sg.appid
WHERE s.has_record = 1
  AND sg.genre_id NOT IN (SELECT value FROM json_each(:not_genres))
GROUP BY sg.genre_id
ORDER BY apps DESC, sg.genre_id"""

# Every price a wished game has had, oldest first (Phase 89): the small line on its row.
WISHLIST_SERIES = """SELECT p.appid, p.observed_at, p.final_cents, p.currency
FROM price_snapshot p
WHERE p.kind = 'priced'
  AND p.appid IN (SELECT appid FROM v_wishlist_now)
ORDER BY p.appid, p.observed_at"""

# The price alerts (Phase 101): the targets set, and the log of the alerts sent, each with its game's name.
# Small tables, read whole; logic/alerts.py keeps the last ALERT_KEEP_DAYS for the page.
PRICE_TARGETS = """SELECT appid, cents, currency, set_at
FROM price_target"""

PRICE_ALERTS = """SELECT a.appid, s.name, a.observed_at, a.kind, a.final_cents, a.currency, a.sent_at
FROM price_alert a
JOIN steam_app s ON s.appid = a.appid
ORDER BY a.sent_at DESC, a.appid"""

# -- 8. Stated and revealed (Phase 89) ----------------------------------------------------------------

STATED_REVEALED = f"""WITH {GAMES_ONCE},
played AS (
    SELECT sg.genre_id, SUM(g.minutes) AS minutes, COUNT(*) AS games
    FROM games g
    JOIN steam_app_genre sg ON sg.appid = g.appid
    WHERE g.minutes > 0
      AND sg.genre_id NOT IN (SELECT value FROM json_each(:not_genres))
    GROUP BY sg.genre_id),
played_all AS (
    SELECT SUM(g.minutes) AS minutes, COUNT(*) AS games
    FROM games g
    WHERE g.minutes > 0
      AND EXISTS (SELECT 1 FROM steam_app_genre sg
                  WHERE sg.appid = g.appid
                    AND sg.genre_id NOT IN (SELECT value FROM json_each(:not_genres)))),
on_lists AS (
    SELECT DISTINCT w.appid
    FROM wishlist w
    JOIN steam_account a ON a.account_id = w.account_id
    WHERE a.is_mine = 1
      AND w.removed_at IS NULL),
wished AS (
    SELECT sg.genre_id, COUNT(DISTINCT w.appid) AS games
    FROM on_lists w
    JOIN steam_app_genre sg ON sg.appid = w.appid
    WHERE sg.genre_id NOT IN (SELECT value FROM json_each(:not_genres))
    GROUP BY sg.genre_id),
wished_all AS (
    SELECT COUNT(*) AS games,
           SUM(EXISTS (SELECT 1 FROM steam_app_genre sg
                       WHERE sg.appid = w.appid
                         AND sg.genre_id NOT IN (SELECT value FROM json_each(:not_genres)))) AS with_genre
    FROM on_lists w)
SELECT genre.name                                  AS genre,
       COALESCE(played.minutes, 0)                 AS minutes,
       (SELECT minutes FROM played_all)            AS minutes_all,
       COALESCE(played.games, 0)                   AS played_games,
       (SELECT games FROM played_all)              AS played_games_all,
       COALESCE(wished.games, 0)                   AS wished,
       (SELECT with_genre FROM wished_all)         AS wished_with_genre,
       (SELECT games FROM wished_all)              AS wished_games
FROM genre
LEFT JOIN played ON played.genre_id = genre.id
LEFT JOIN wished ON wished.genre_id = genre.id
WHERE played.minutes > 0 OR wished.games > 0
ORDER BY genre.name"""

# -- 10. Said and played (Phase 102) ------------------------------------------------------------------
# Each rated game's ratings -- a game is its Steam app where it has one, as in v_hours, else its record -- and
# whether a rating came late (given on a later day than its session). Its hours are report 1's rows, read once
# for both (a second read of v_hours would cost the reports 1.6 ms of their 50). A session counts by the one
# rule (its game not marked a tool), and Spacewar and Source SDK Base 2007 are set aside as everywhere.

SAID_PLAYED = """SELECT g.steam_appid                                                    AS appid,
       CASE WHEN g.steam_appid IS NULL THEN g.id END                    AS game_id,
       COALESCE(MIN(s.name), MIN(COALESCE(g.custom_name, g.known_as)))  AS name,
       COUNT(*)                                                         AS ratings,
       AVG(r.stars)                                                     AS mean_stars,
       SUM(substr(r.rated_at, 1, 10) > substr(r.started_at, 1, 10))     AS late,
       COALESCE(MAX(s.has_record), 0)                                   AS has_record
FROM rating r
JOIN game g           ON g.id = r.game_id
LEFT JOIN steam_app s ON s.appid = g.steam_appid
WHERE COALESCE(g.is_tool, 0) = 0
  AND COALESCE(g.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
GROUP BY g.steam_appid, CASE WHEN g.steam_appid IS NULL THEN g.id END
ORDER BY mean_stars DESC, name"""

# -- 11. Finishing (Phase 103) ----------------------------------------------------------------------
# Every game with a mark -- not marked a tool, not set aside -- with the first and last of its counted sessions,
# when its mark was set (dated since version 8) and its nudge last answered, its other dates of play and Steam's
# newest last played on the accounts marked mine (Left behind's rule reads them). Its hours are report 1's rows.

FINISHING = f"""WITH {SESSIONS},
span AS (SELECT game_id, MIN(started_at) AS first_session, MAX(started_at) AS last_session
         FROM sessions GROUP BY game_id)
SELECT v.identity_key, v.name, v.steam_appid AS appid,
       CASE WHEN v.steam_appid IS NULL THEN v.id END AS game_id,
       v.status, v.installed, v.launch_kind, g.status_changed_at, g.nudged_at,
       sp.first_session, sp.last_session, v.last_played, v.store_last_played, m.last_played AS steam_last_played
FROM v_library v
JOIN game g                   ON g.id = v.id
LEFT JOIN span sp             ON sp.game_id = v.id
LEFT JOIN v_steam_time_mine m ON m.appid = v.steam_appid
WHERE v.status IS NOT NULL
  AND COALESCE(v.is_tool, 0) = 0
  AND COALESCE(v.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
ORDER BY v.name COLLATE NOCASE"""

# Every query by name, in the order the reports use them: what the markdown and the document quote.
QUERIES: dict[str, str] = {
    "concentration": CONCENTRATION,
    "abandonment": ABANDONMENT,
    "profile_coverage": PROFILE_COVERAGE,
    "profile_genres": PROFILE_GENRES,
    "profile_companies": PROFILE_COMPANIES,
    "profile_decades": PROFILE_DECADES,
    "backlog": BACKLOG,
    "session_summary": SESSION_SUMMARY,
    "session_origins": SESSION_ORIGINS,
    "session_lengths": SESSION_LENGTHS,
    "session_hours": SESSION_HOURS,
    "session_weekdays": SESSION_WEEKDAYS,
    "money_library": MONEY_LIBRARY,
    "money_paid": MONEY_PAID,
    "money_proxy": MONEY_PROXY,
    "money_sales": MONEY_SALES,
    "money_lowest": MONEY_LOWEST,
    "money_wishlist": MONEY_WISHLIST,
    "money_series": MONEY_SERIES,
    "quality_types": QUALITY_TYPES,
    "quality_set_aside": QUALITY_SET_ASIDE,
    "quality_sources": QUALITY_SOURCES,
    "quality_links": QUALITY_LINKS,
    "quality_untimed": QUALITY_UNTIMED,
    "quality_currencies": QUALITY_CURRENCIES,
    "stats_lifetime": STATS_LIFETIME,
    "stats_top": STATS_TOP,
    "stats_months": STATS_MONTHS,
    "stats_sources": STATS_SOURCES,
    "wishlist_now": WISHLIST_NOW,
    "wishlist_profile": WISHLIST_PROFILE,
    "wishlist_genres": WISHLIST_GENRES,
    "wishlist_idf": WISHLIST_IDF,
    "wishlist_series": WISHLIST_SERIES,
    "price_targets": PRICE_TARGETS,
    "price_alerts": PRICE_ALERTS,
    "stated_revealed": STATED_REVEALED,
    "said_played": SAID_PLAYED,
    "finishing": FINISHING,
}

# The views a build reads most, worked out once for it (Phase 103): `Reports.worked_out_once`.
ONCE = ("v_steam_time_mine", "v_hours")


def parameters() -> dict:
    """The named values every query may use, from rules.py -- never a number in the SQL itself."""
    return {
        "set_aside": json.dumps(sorted(rules.STEAM_NOT_GAMES)),
        "not_genres": json.dumps(sorted(rules.STEAM_NOT_GENRES)),
        "free_to_play": rules.STEAM_FREE_TO_PLAY_GENRE,
        "ten_minutes": rules.REPORT_TEN_MINUTES,
        "one_hour": rules.REPORT_ONE_HOUR,
        "refund_window": rules.REPORT_REFUND_WINDOW_MINUTES,
        "ten_hours": rules.REPORT_TEN_HOURS,
        "hundred_hours": rules.REPORT_HUNDRED_HOURS,
        "backlog_under": rules.REPORT_BACKLOG_UNDER_MINUTES,
        "quarter_hour": rules.REPORT_SESSION_EDGES[0],
        "half_hour": rules.REPORT_SESSION_EDGES[1],
        "hour": rules.REPORT_SESSION_EDGES[2],
        "two_hours": rules.REPORT_SESSION_EDGES[3],
        "proxy_min_minutes": rules.REPORT_PROXY_MIN_MINUTES,
        "top": rules.STATS_TOP_GAMES,
        # For you (Phase 98): what is not waiting any more, by the user's own mark; Tonight's Dropped.
        "dropped": rules.STATUS_DROPPED,
        "playing": rules.STATUS_PLAYING,  # Left behind (Phase 103)
        "company_roles": json.dumps(sorted(rules.REPORT_COMPANY_ROLES)),
    }


class Reports:
    """The queries above, run on one connection -- the window's store's, or a read-only one."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    queries = QUERIES  # the recap's own set takes this place (data_access/recap.py, Phase 96)

    @contextmanager
    def worked_out_once(self):
        """For one build: each view of ONCE copied into a temporary table of the same name, which every query
        reads in its place (the temporary schema is looked in first), dropped at the end -- nothing reaches the
        library file. The same answers, each view worked out once rather than at every query that reads it."""
        made = []
        try:
            for name in ONCE:
                self.conn.execute(f"DROP TABLE IF EXISTS temp.{name}")
                self.conn.execute(f"CREATE TEMP TABLE {name} AS SELECT * FROM main.{name}")
                made.append(name)
            yield self
        finally:
            for name in reversed(made):
                self.conn.execute(f"DROP TABLE IF EXISTS temp.{name}")

    def rows(self, name: str, **extra) -> list[dict]:
        """One query's rows as dicts. SQLite refuses any write while it runs (`query_only`)."""
        values = parameters()
        values.update(extra)
        self.conn.execute("PRAGMA query_only = ON")
        try:
            cursor = self.conn.execute(self.queries[name], values)
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        finally:
            self.conn.execute("PRAGMA query_only = OFF")

    def one(self, name: str, **extra) -> dict:
        found = self.rows(name, **extra)
        return found[0] if found else {}


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def open_read_only(path: Path | str) -> Reports:
    """Reports on a connection of their own that cannot write -- for the command line.

    Refuses a file that is not there (opening read-only never creates one) and one older than
    version 5, which has no v_hours yet: the launcher upgrades it at its next start.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"no library database at {path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    have = schema_version(conn)
    if have < NEEDS_VERSION:
        conn.close()
        raise RuntimeError(f"the library database is at version {have}; the reports need version "
                           f"{NEEDS_VERSION} -- start the launcher once and it upgrades the file")
    return Reports(conn)


# Report 9 (Phase 98) reads For you's queries, which live beside its page in data_access/recommend.py and are
# built on this module's CTEs. recommend.py adds them to QUERIES as it loads, so every runner of the reports --
# the Reports page, reports.py, the tests -- answers them; imported here, last, so that it has loaded whichever
# of the two is imported first. Nothing is read from it here: it may still be loading.
from data_access import recommend as _recommend  # noqa: E402,F401
