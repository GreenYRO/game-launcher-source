-- Game Launcher: schema version 4 -> 5 (Phase 83), v_hours: every hour the library knows of, from
-- both its sources, in one place. A view only, like version 4: no table changes, no row moves.
-- docs/BAZA_DE_DATE.md section 5 (Versiunea 5) and docs/ANALIZA.md explain it; schema.sql holds
-- the same view.
--
-- Two sources of hours, never confused:
--   * the launcher's own timing -- game.playtime_seconds, exe games only (a game Steam starts is
--     never timed here, so the two never measure the same play);
--   * Steam's lifetime counters on the accounts marked mine -- v_steam_time_mine, whole minutes.
-- One row per Steam app wherever there is one: Steam's minutes once, and the launcher's time of
-- every game linked to that app added up (two folders of one game share one app) -- so an app is
-- never counted twice. One row per game that has no Steam app. Every game ever known counts,
-- installed or not: carrying a history over moves its time, so nothing is there twice.
-- `source` says where an app's time came from: 'launcher', 'steam', 'both', or NULL for none.
-- `marked_tool` is the user's mark on the linked games (1 a tool, 0 a game, NULL no mark), and
-- `app_type` Steam's type -- the reports decide what is a game from the two.
--
-- The two sources meet in one FULL JOIN, so Steam's counters are read once: 1.9 ms on the
-- user's library (381 rows), where a UNION of the apps and then a join read them twice (2.8 ms),
-- and the reports read this view some twenty times a page.

CREATE VIEW v_hours AS
WITH linked AS (
    SELECT steam_appid                                 AS appid,
           COUNT(*)                                    AS games,
           MAX(is_tool)                                AS marked_tool,
           MIN(COALESCE(custom_name, known_as))        AS game_name,
           SUM(COALESCE(playtime_seconds, 0)) / 60.0   AS minutes
    FROM game
    WHERE steam_appid IS NOT NULL
    GROUP BY steam_appid)
SELECT COALESCE(l.appid, m.appid)                                  AS appid,
       NULL                                                        AS game_id,
       COALESCE(s.name, l.game_name, 'app ' || COALESCE(l.appid, m.appid)) AS name,
       s.app_type,
       l.marked_tool,
       COALESCE(l.games, 0)                                        AS games,
       l.minutes                                                   AS minutes_launcher,
       m.minutes                                                   AS minutes_steam,
       m.last_played                                               AS steam_last_played,
       COALESCE(l.minutes, 0) + COALESCE(m.minutes, 0)             AS minutes,
       CASE WHEN l.minutes > 0 AND m.minutes > 0 THEN 'both'
            WHEN m.minutes > 0 THEN 'steam'
            WHEN l.minutes > 0 THEN 'launcher' END                 AS source
FROM linked l
FULL JOIN v_steam_time_mine m ON m.appid = l.appid
LEFT JOIN steam_app         s ON s.appid = COALESCE(l.appid, m.appid)
UNION ALL
SELECT NULL,
       v.id,
       v.name,
       NULL,
       v.is_tool,
       1,
       COALESCE(v.playtime_seconds, 0) / 60.0,
       NULL,
       NULL,
       COALESCE(v.playtime_seconds, 0) / 60.0,
       CASE WHEN v.playtime_seconds > 0 THEN 'launcher' END
FROM v_library v
WHERE v.steam_appid IS NULL;
