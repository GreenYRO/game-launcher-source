-- Game Launcher: schema version 2 -> 3 (Phase 75), Steam's own playtime.
-- docs/BAZA_DE_DATE.md, section 18, explains the upgrades; section 4 the three tables.
--
-- Additive only -- expand before contract: three tables, an index and two views are added;
-- nothing is dropped, renamed or rewritten. Run by data_access/library_db.upgrade in one
-- transaction with the version bump. schema.sql holds the same statements, word for word.

-- The Steam accounts that have used this machine: one row per userdata\<account id> folder.
-- The id is the low 32 bits of the SteamID64 (entity resolution: the folder name, the
-- SteamID64 in loginusers.vdf and the account are one). is_mine is three-valued, as
-- game.is_tool is: NULL not decided, 1 mine, 0 not mine -- set only from Settings, never
-- assumed. Names come from loginusers.vdf when it lists the account, otherwise NULL.
CREATE TABLE steam_account (
    account_id    INTEGER PRIMARY KEY CHECK (account_id > 0),
    steam_id64    INTEGER NOT NULL UNIQUE CHECK (steam_id64 = account_id + 76561197960265728),
    account_name  TEXT,
    persona       TEXT,
    is_mine       INTEGER CHECK (is_mine IN (0, 1)),       -- NULL: not decided
    most_recent   INTEGER CHECK (most_recent IN (0, 1)),   -- loginusers.vdf's MostRecent, when it says
    last_login    TEXT,                                    -- loginusers.vdf's Timestamp, an instant
    first_seen    TEXT    NOT NULL,
    last_seen     TEXT    NOT NULL
) STRICT;

-- One row per account per reading: when the launcher looked, and what the file looked like.
-- It is what bounds a difference: a counter that moved between two readings was played
-- between those two moments. A file that did not parse gives no row. Only ever added to.
CREATE TABLE steam_read (
    account_id      INTEGER NOT NULL REFERENCES steam_account (account_id),
    read_at         TEXT    NOT NULL CHECK (read_at GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'),
    file_modified   TEXT    NOT NULL CHECK (file_modified GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'),
    apps_in_file    INTEGER NOT NULL CHECK (apps_in_file >= 0),
    apps_with_time  INTEGER NOT NULL CHECK (apps_with_time BETWEEN 0 AND apps_in_file),
    PRIMARY KEY (account_id, read_at)
) STRICT;

-- Steam's lifetime playtime counter per account and app, as a series: a row the first time a
-- pair is seen and whenever one of its four values changes; an unchanged pair writes nothing
-- (its read row says it was looked at). Only ever added to: a counter that went down is kept
-- as it was read. observed_at is its reading's read_at, which the foreign key holds to.
CREATE TABLE steam_playtime (
    account_id            INTEGER NOT NULL,
    appid                 INTEGER NOT NULL REFERENCES steam_app (appid),
    observed_at           TEXT    NOT NULL,
    minutes_total         INTEGER CHECK (minutes_total >= 0),         -- NULL: LastPlayed but no Playtime
    minutes_2wks          INTEGER CHECK (minutes_2wks >= 0),
    minutes_disconnected  INTEGER CHECK (minutes_disconnected >= 0),
    last_played           TEXT,                                       -- local time with its offset
    PRIMARY KEY (account_id, appid, observed_at),
    FOREIGN KEY (account_id, observed_at) REFERENCES steam_read (account_id, read_at)
) STRICT;

CREATE INDEX steam_playtime_by_app ON steam_playtime (appid);

-- The newest observation of every account and app, with whose account it is.
CREATE VIEW v_steam_time_latest AS
SELECT t.account_id, a.persona, a.is_mine, t.appid, t.observed_at,
       t.minutes_total, t.minutes_2wks, t.minutes_disconnected, t.last_played
FROM (SELECT p.*, ROW_NUMBER() OVER (PARTITION BY account_id, appid ORDER BY observed_at DESC) AS newest
      FROM steam_playtime p) t
JOIN steam_account a ON a.account_id = t.account_id
WHERE t.newest = 1;

-- Per app, over the accounts marked mine only: the minutes summed, the newest last played (by
-- the moment, across offsets), and how many of the accounts hold it.
CREATE VIEW v_steam_time_mine AS
SELECT l.appid,
       SUM(l.minutes_total) AS minutes,
       COUNT(*)             AS accounts,
       (SELECT n.last_played FROM v_steam_time_latest n
        WHERE n.appid = l.appid AND n.is_mine = 1 AND n.last_played IS NOT NULL
        ORDER BY julianday(n.last_played) DESC LIMIT 1) AS last_played
FROM v_steam_time_latest l
WHERE l.is_mine = 1
GROUP BY l.appid;
