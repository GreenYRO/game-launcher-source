-- Game Launcher: schema version 3 -> 4 (Phase 76), v_steam_time_mine in one pass.
-- docs/BAZA_DE_DATE.md, section 18, explains the upgrades; section 4 the view.
--
-- A view holds no data, so replacing one loses nothing: every row of every table is as it
-- was. Version 3's view found each app's newest last played with a correlated subquery that
-- read v_steam_time_latest again for every app -- 93 ms for the 335 apps on the user's
-- accounts, on the GUI thread at every reload. This one ranks the rows once with a window
-- function and takes the first: 0.8 ms, and the same answer for every app (proven on the
-- real data under three different sets of marks). schema.sql holds the same view.

DROP VIEW v_steam_time_mine;

-- Per app, over the accounts marked mine only: the minutes summed, the newest last played (by
-- the moment, across offsets), and how many of the accounts hold it.
CREATE VIEW v_steam_time_mine AS
SELECT r.appid,
       SUM(r.minutes_total) AS minutes,
       COUNT(*)             AS accounts,
       MAX(CASE WHEN r.latest_play = 1 THEN r.last_played END) AS last_played
FROM (SELECT l.appid, l.minutes_total, l.last_played,
             ROW_NUMBER() OVER (PARTITION BY l.appid
                                ORDER BY julianday(l.last_played) DESC NULLS LAST) AS latest_play
      FROM v_steam_time_latest l
      WHERE l.is_mine = 1) r
GROUP BY r.appid;
