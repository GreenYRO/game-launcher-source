-- Game Launcher: the library database, schema version 8 (Phase 67; prices in Phase 73; Steam's playtime in Phase 75;
-- v_steam_time_mine in one pass in Phase 76; v_hours for the reports in Phase 83; the wishlist in Phase 86; a
-- session's origin in Phase 93; price alerts, ratings and dated marks in Phase 101).
-- docs/BAZA_DE_DATE.md explains every table, in Romanian, for the thesis.
--
-- SQLite 3.37 or newer (STRICT tables); the venv ships 3.50.4. data_access/library_db.py
-- runs this file once, when it creates a database, and sets PRAGMA foreign_keys = ON on
-- every connection it opens: SQLite leaves foreign keys off by default, and a declared
-- constraint that is never enforced would be a lie.

-- This file is always the whole current schema, for a database created fresh. A database
-- made by an older version is brought up to it by the numbered scripts in upgrades/
-- (docs/BAZA_DE_DATE.md, section 18); a test proves the two arrive at the same schema.

-- One row describing the file itself. PRAGMA user_version repeats schema_version.
CREATE TABLE meta (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version  INTEGER NOT NULL,
    created_at      TEXT    NOT NULL,
    migrated_from   TEXT,                -- 'overrides.json + catalog.json', or NULL
    migrated_at     TEXT
) STRICT;

-- A projection of the cached Steam records (cache/steam_details/<appid>.json). A price here
-- is the list price on the day the record was fetched, in its own currency, never converted.
CREATE TABLE steam_app (
    appid                INTEGER PRIMARY KEY,
    has_record           INTEGER NOT NULL CHECK (has_record IN (0, 1)),  -- 0: appid known, no record cached
    name                 TEXT,
    app_type             TEXT,
    is_free              INTEGER CHECK (is_free IN (0, 1)),
    release_date         TEXT,           -- ISO date where release_text parses; never guessed
    release_text         TEXT,           -- exactly as Steam wrote it, e.g. '9 Dec, 2020'
    coming_soon          INTEGER CHECK (coming_soon IN (0, 1)),
    price_initial_cents  INTEGER CHECK (price_initial_cents >= 0),
    price_final_cents    INTEGER CHECK (price_final_cents >= 0),
    discount_percent     INTEGER CHECK (discount_percent BETWEEN 0 AND 100),
    currency             TEXT,           -- ISO 4217, as Steam answered
    metacritic_score     INTEGER CHECK (metacritic_score BETWEEN 0 AND 100),
    recommendations      INTEGER CHECK (recommendations >= 0),
    controller_support   TEXT,           -- 'full', 'partial' or NULL, as Steam says
    required_age         INTEGER CHECK (required_age >= 0),
    achievements_total   INTEGER CHECK (achievements_total >= 0),
    short_description    TEXT,
    fetched_at           TEXT,
    CHECK ((price_final_cents IS NULL) = (currency IS NULL)),
    CHECK (has_record = 1 OR (release_text IS NULL AND price_final_cents IS NULL))
) STRICT;

CREATE TABLE genre (
    id    INTEGER PRIMARY KEY,           -- Steam's own id
    name  TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE steam_app_genre (
    appid     INTEGER NOT NULL REFERENCES steam_app (appid) ON DELETE CASCADE,
    genre_id  INTEGER NOT NULL REFERENCES genre (id),
    PRIMARY KEY (appid, genre_id)
) STRICT;

-- Not UNIQUE on name: Steam reuses a name under two ids. Group by name with COUNT(DISTINCT appid).
CREATE TABLE category (
    id    INTEGER PRIMARY KEY,           -- Steam's own id
    name  TEXT NOT NULL
) STRICT;

CREATE TABLE steam_app_category (
    appid        INTEGER NOT NULL REFERENCES steam_app (appid) ON DELETE CASCADE,
    category_id  INTEGER NOT NULL REFERENCES category (id),
    PRIMARY KEY (appid, category_id)
) STRICT;

CREATE TABLE company (
    id    INTEGER PRIMARY KEY,           -- surrogate: Steam gives companies no id
    name  TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE steam_app_company (
    appid       INTEGER NOT NULL REFERENCES steam_app (appid) ON DELETE CASCADE,
    company_id  INTEGER NOT NULL REFERENCES company (id),
    role        TEXT    NOT NULL CHECK (role IN ('developer', 'publisher')),
    PRIMARY KEY (appid, company_id, role)
) STRICT;

-- One row per game the launcher has ever known, installed or not. The scan never writes
-- the user's columns here; the merge stamps first_seen, is_new and known_as, as
-- catalog_io.merge does today. first_seen is NULL only for a game a scan has just written
-- and the merge has not stamped yet -- the record of it does not exist until then.
-- status_changed_at and nudged_at (version 8, Phase 101): when the mark was last set or cleared, and when the
-- launcher last nudged about it (Phase 103). The last columns, where version 8's ALTER TABLE puts them, NULL
-- for every game made before; status_changed_at is written from Phase 101 on.
CREATE TABLE game (
    id                 INTEGER PRIMARY KEY,
    identity_key       TEXT    NOT NULL UNIQUE,
    source             TEXT    CHECK (source IN ('folders', 'steam', 'gog', 'epic', 'ubisoft', 'xbox')),
                                                     -- NULL: an uninstalled folder key, store not recorded
    source_id          TEXT,
    known_as           TEXT,                         -- the detected name, kept current by the merge
    name_origin        TEXT    NOT NULL CHECK (name_origin IN ('scan', 'folder', 'steam', 'none')),
    custom_name        TEXT,
    custom_exe         TEXT,
    launch_args        TEXT,
    steam_appid        INTEGER REFERENCES steam_app (appid),
    appid_source       TEXT    CHECK (appid_source IN ('manifest', 'search', 'chosen', 'recovered')),
    is_tool            INTEGER CHECK (is_tool IN (0, 1)),   -- NULL no opinion; 0 game; 1 tool
    hidden             INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
    favorite           INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
    status             TEXT    CHECK (status IN ('playing', 'finished', 'dropped')),
    notes              TEXT,
    is_new             INTEGER NOT NULL DEFAULT 0 CHECK (is_new IN (0, 1)),
    first_seen         TEXT,
    last_played        TEXT,
    playtime_seconds   INTEGER CHECK (playtime_seconds >= 0),  -- lifetime total; NULL never timed
    cover_path         TEXT,
    banner_path        TEXT,
    save_dirs_checked  TEXT,                         -- when the saves were last looked for (a time)
    carried_to         INTEGER REFERENCES game (id), -- the direct successor its history went to
    carried_at         TEXT,
    status_changed_at TEXT CHECK (status_changed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9][+-][0-9][0-9]:[0-9][0-9]'),
    nudged_at TEXT CHECK (nudged_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9][+-][0-9][0-9]:[0-9][0-9]'),
    CHECK ((steam_appid IS NULL) = (appid_source IS NULL)),
    CHECK ((carried_to IS NULL) = (carried_at IS NULL)),
    CHECK (carried_to IS NULL OR carried_to <> id)
) STRICT;

-- One row per scan: a log, and the answer to "sizes as of when".
CREATE TABLE scan (
    id           INTEGER PRIMARY KEY,
    started_at   TEXT,                   -- NULL only for the one the migration brings in
    finished_at  TEXT    NOT NULL,
    roots        TEXT    NOT NULL DEFAULT '[]' CHECK (json_valid(roots)),
    entry_count  INTEGER NOT NULL CHECK (entry_count >= 0),
    trigger      TEXT    NOT NULL CHECK (trigger IN
                     ('first_run', 'startup', 'manual', 'watch', 'uninstall', 'migration'))
) STRICT;

-- What the last scan found: one row per installed game, rewritten by every scan in one
-- transaction. A game with no row here is not installed.
CREATE TABLE install (
    game_id            INTEGER PRIMARY KEY REFERENCES game (id) ON DELETE CASCADE,
    position           INTEGER NOT NULL UNIQUE,      -- the order the scan found them in
    display_name       TEXT    NOT NULL,             -- as this scan detected it
    install_dir        TEXT    NOT NULL,
    launch_kind        TEXT    NOT NULL CHECK (launch_kind IN ('exe', 'uri')),
    launch_target      TEXT    NOT NULL,
    working_dir        TEXT    NOT NULL,
    icon_hint          TEXT    NOT NULL,
    size_on_disk       INTEGER CHECK (size_on_disk >= 0),
    detection          TEXT    NOT NULL,
    alternatives       TEXT    NOT NULL DEFAULT '[]' CHECK (json_valid(alternatives)),  -- diagnostic
    extra              TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(extra)),         -- the provider's own bag
    store_last_played  TEXT,                         -- the store's own date, copied out of extra
    scan_id            INTEGER NOT NULL REFERENCES scan (id)
) STRICT;

-- One row per exe launch. Local wall time with its offset, second precision, as written
-- today. The generated columns read the local time off the text, because SQLite's own
-- date functions convert to UTC first.
-- origin (version 7, Phase 93): how a session was measured -- 'launched', timed from the launcher's
-- own start; 'observed', seen in the process list, whoever started it. The last column, where
-- version 7's ALTER TABLE puts it, and no comment inside the table: SQLite keeps the table's text
-- as written, so a fresh file and an upgraded one only read alike without one.
CREATE TABLE session (
    id             INTEGER PRIMARY KEY,
    game_id        INTEGER NOT NULL REFERENCES game (id) ON DELETE CASCADE,
    started_at     TEXT    NOT NULL CHECK (started_at GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9][+-][0-9][0-9]:[0-9][0-9]'),
    minutes        INTEGER NOT NULL CHECK (minutes >= 0),
    started_local  TEXT    GENERATED ALWAYS AS (substr(started_at, 1, 19)) VIRTUAL,
    local_hour     INTEGER GENERATED ALWAYS AS (CAST(substr(started_at, 12, 2) AS INTEGER)) VIRTUAL,
    origin         TEXT    NOT NULL DEFAULT 'launched' CHECK (origin IN ('launched', 'observed')),
    UNIQUE (game_id, started_at)
) STRICT;

-- Where a game keeps its saves; replaces save_dirs and save_dirs_ignored. position keeps
-- each list's order, which the code compares.
CREATE TABLE save_folder (
    game_id   INTEGER NOT NULL REFERENCES game (id) ON DELETE CASCADE,
    path      TEXT    NOT NULL,
    ignored   INTEGER NOT NULL DEFAULT 0 CHECK (ignored IN (0, 1)),
    position  INTEGER NOT NULL,
    PRIMARY KEY (game_id, path)
) STRICT;

-- A game's earlier installs (carried over) and the ones the user said are another game;
-- replaces earlier_keys and not_same_as. position keeps each list's order.
CREATE TABLE lineage (
    game_id     INTEGER NOT NULL REFERENCES game (id) ON DELETE CASCADE,
    earlier_id  INTEGER NOT NULL REFERENCES game (id) ON DELETE CASCADE,
    relation    TEXT    NOT NULL CHECK (relation IN ('carried_from', 'not_same')),
    position    INTEGER NOT NULL,
    PRIMARY KEY (game_id, earlier_id),
    CHECK (game_id <> earlier_id)
) STRICT;

CREATE INDEX session_by_start   ON session (started_at);
CREATE INDEX game_by_appid      ON game (steam_appid);
CREATE INDEX lineage_by_earlier ON lineage (earlier_id);

-- Every game, installed or not, with what the analysis needs beside it.
CREATE VIEW v_library AS
SELECT g.id,
       g.identity_key,
       g.source,
       COALESCE(g.custom_name, g.known_as, i.display_name, s.name, g.identity_key) AS name,
       g.name_origin,
       i.game_id IS NOT NULL                                       AS installed,
       i.launch_kind,
       i.size_on_disk,
       i.store_last_played,
       g.steam_appid,
       g.appid_source,
       g.is_tool, g.hidden, g.favorite, g.status,
       g.first_seen, g.last_played, g.playtime_seconds,
       s.app_type, s.price_final_cents, s.currency, s.release_date,
       s.metacritic_score, s.controller_support
FROM game g
LEFT JOIN install   i ON i.game_id = g.id
LEFT JOIN steam_app s ON s.appid = g.steam_appid;

-- The lifetime total beside the windowed history, for every game where they differ.
CREATE VIEW v_playtime_check AS
SELECT g.identity_key,
       COALESCE(g.custom_name, g.known_as, g.identity_key)                AS name,
       COALESCE(g.playtime_seconds, 0)                                    AS total_seconds,
       COALESCE(SUM(se.minutes), 0) * 60                                  AS session_seconds,
       COALESCE(g.playtime_seconds, 0) - COALESCE(SUM(se.minutes), 0) * 60 AS difference_seconds,
       COUNT(se.id)                                                       AS sessions
FROM game g
LEFT JOIN session se ON se.game_id = g.id
GROUP BY g.id
HAVING total_seconds <> session_seconds;

-- == Version 2 (Phase 73): prices. The same statements as upgrades/002_prices.sql. ==

-- What the store answered, each time it was asked: a time series, only ever added to.
-- 'free' and 'unavailable' are observations too -- "when did this stop being sold" is a
-- question the series must answer. A request that failed is not an observation, and is
-- not here. observed_at is the moment of the fetch, always UTC, so text order is time order.
CREATE TABLE price_snapshot (
    appid             INTEGER NOT NULL REFERENCES steam_app (appid),
    observed_at       TEXT    NOT NULL CHECK (observed_at GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'),
    kind              TEXT    NOT NULL CHECK (kind IN ('priced', 'free', 'unavailable')),
    currency          TEXT,           -- ISO 4217, as the store answered; never converted
    initial_cents     INTEGER CHECK (initial_cents >= 0),
    final_cents       INTEGER CHECK (final_cents >= 0),
    discount_percent  INTEGER CHECK (discount_percent BETWEEN 0 AND 100),
    PRIMARY KEY (appid, observed_at),
    CHECK (CASE kind
               WHEN 'priced' THEN currency IS NOT NULL AND initial_cents IS NOT NULL
                              AND final_cents IS NOT NULL AND discount_percent IS NOT NULL
               ELSE currency IS NULL AND initial_cents IS NULL
                AND final_cents IS NULL AND discount_percent IS NULL
           END)
) STRICT;

-- What the user paid, typed by hand: zero or more rows per game (a game bought twice, a DLC
-- later). 0 is a real purchase (a gift, a bundle, a subscription); a game with no row is
-- unknown, not free.
CREATE TABLE purchase (
    id           INTEGER PRIMARY KEY,
    game_id      INTEGER NOT NULL REFERENCES game (id) ON DELETE CASCADE,
    paid_cents   INTEGER NOT NULL CHECK (paid_cents >= 0),
    currency     TEXT    NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3 AND currency = upper(currency)),
    store        TEXT    NOT NULL CHECK (length(trim(store)) > 0),
    bought_on    TEXT    CHECK (bought_on IS NULL OR date(bought_on) IS bought_on),  -- an ISO date, or unknown
    note         TEXT,
    recorded_at  TEXT    NOT NULL
) STRICT;

CREATE INDEX purchase_by_game ON purchase (game_id);

-- The newest observation of every app: "what does it cost now". The one answer to that
-- question from version 2 on; steam_app's price columns are the cached record's.
CREATE VIEW v_price_latest AS
SELECT appid, observed_at, kind, currency, initial_cents, final_cents, discount_percent
FROM (SELECT p.*, ROW_NUMBER() OVER (PARTITION BY appid ORDER BY observed_at DESC) AS newest
      FROM price_snapshot p)
WHERE newest = 1;

-- Per app: how often it was seen, first and last, and the lowest and highest price seen
-- (each the first time it was seen at that price).
CREATE VIEW v_price_range AS
SELECT seen.appid,
       seen.observations,
       seen.first_observed,
       seen.last_observed,
       low.final_cents   AS lowest_cents,
       low.currency      AS lowest_currency,
       low.observed_at   AS lowest_on,
       high.final_cents  AS highest_cents,
       high.currency     AS highest_currency,
       high.observed_at  AS highest_on
FROM (SELECT appid, COUNT(*) AS observations,
             MIN(observed_at) AS first_observed, MAX(observed_at) AS last_observed
      FROM price_snapshot GROUP BY appid) seen
LEFT JOIN (SELECT appid, final_cents, currency, observed_at,
                  ROW_NUMBER() OVER (PARTITION BY appid ORDER BY final_cents, observed_at) AS rank
           FROM price_snapshot WHERE kind = 'priced') low
       ON low.appid = seen.appid AND low.rank = 1
LEFT JOIN (SELECT appid, final_cents, currency, observed_at,
                  ROW_NUMBER() OVER (PARTITION BY appid ORDER BY final_cents DESC, observed_at) AS rank
           FROM price_snapshot WHERE kind = 'priced') high
       ON high.appid = seen.appid AND high.rank = 1;

-- Per game: the latest list price, what was paid (a total only within one currency -- never
-- converted), the launcher's playtime, and what an hour cost where both are known.
CREATE VIEW v_game_money AS
SELECT g.id AS game_id,
       g.identity_key,
       COALESCE(g.custom_name, g.known_as, i.display_name, s.name, g.identity_key) AS name,
       g.steam_appid,
       pl.kind          AS list_kind,
       pl.final_cents   AS list_cents,
       pl.currency      AS list_currency,
       pl.observed_at   AS list_observed_at,
       pu.purchases,
       pu.paid_cents,
       pu.paid_currency,
       g.playtime_seconds,
       CASE WHEN pu.paid_cents IS NOT NULL AND g.playtime_seconds > 0
            THEN ROUND(pu.paid_cents * 3600.0 / g.playtime_seconds) END AS cents_per_hour
FROM game g
LEFT JOIN install        i  ON i.game_id = g.id
LEFT JOIN steam_app      s  ON s.appid = g.steam_appid
LEFT JOIN v_price_latest pl ON pl.appid = g.steam_appid
LEFT JOIN (SELECT game_id,
                  COUNT(*) AS purchases,
                  CASE WHEN COUNT(DISTINCT currency) = 1 THEN SUM(paid_cents) END AS paid_cents,
                  CASE WHEN COUNT(DISTINCT currency) = 1 THEN MIN(currency) END   AS paid_currency
           FROM purchase GROUP BY game_id) pu
       ON pu.game_id = g.id;

-- == Version 3 (Phase 75): Steam's own playtime. The same statements as upgrades/003_steam_time.sql. ==

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
-- the moment, across offsets), and how many of the accounts hold it. As version 4 has it
-- (upgrades/004_steam_time_mine.sql): the rows ranked once by a window function, where
-- version 3 read the newest observations again for every app.
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

-- == Version 5 (Phase 83): v_hours, the hours from both sources side by side. The same view as
-- upgrades/005_hours.sql, which explains it. ==

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

-- == Version 6 (Phase 86): the Steam wishlist -- two tables and a view. The same objects as
-- upgrades/006_wishlist.sql, which explains them. ==

-- wishlist_read is the read log, as steam_read is Steam's playtime's: one row per account per
-- answer from IWishlistService. 'items' is a list read; 'nothing' an answer with no items -- a
-- private list and an empty one answer alike (read on 15 October), so 'nothing' never takes
-- anything off the list. A request with no answer at all is no reading, and is not recorded.
CREATE TABLE wishlist_read (
    account_id  INTEGER NOT NULL REFERENCES steam_account (account_id),
    read_at     TEXT    NOT NULL CHECK (read_at GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'),
    state       TEXT    NOT NULL CHECK (state IN ('items', 'nothing')),
    items       INTEGER NOT NULL CHECK (items >= 0),
    PRIMARY KEY (account_id, read_at),
    CHECK ((state = 'items') = (items > 0))
) STRICT;

-- One row per game per account, inserted the first time a list holds it. last_seen moves with
-- every list read that holds it; a list read without it sets removed_at (that read's moment) --
-- never a delete: what was wanted and stopped being wanted is itself data. A game that comes
-- back clears removed_at. Each of the three moments is a read of that account's list.
CREATE TABLE wishlist (
    account_id  INTEGER NOT NULL REFERENCES steam_account (account_id),
    appid       INTEGER NOT NULL REFERENCES steam_app (appid),
    priority    INTEGER CHECK (priority >= 0),   -- Steam's own ranking on the list; 0 for every item here
    date_added  TEXT    CHECK (date_added GLOB   -- when it was added on Steam, as Steam says
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'),
    first_seen  TEXT    NOT NULL,
    last_seen   TEXT    NOT NULL,
    removed_at  TEXT,
    PRIMARY KEY (account_id, appid),
    FOREIGN KEY (account_id, first_seen) REFERENCES wishlist_read (account_id, read_at),
    FOREIGN KEY (account_id, last_seen)  REFERENCES wishlist_read (account_id, read_at),
    FOREIGN KEY (account_id, removed_at) REFERENCES wishlist_read (account_id, read_at),
    CHECK (first_seen <= last_seen),
    CHECK (removed_at IS NULL OR removed_at > last_seen)
) STRICT;

-- One row per game on the lists of the accounts marked mine -- a game on two lists is one row,
-- both accounts named -- with its newest price, the lowest and highest the series has seen, how
-- many prices, and the hours already played on it (another account may own it already): the
-- same sum v_hours makes, the launcher's linked games plus Steam's newest counters on the
-- accounts marked mine. `lists` counts the lists that hold it now; none, and removed_at is when
-- the last one let it go. is_lowest_now: today's price is the lowest seen, the series holds two
-- prices or more, and it has seen a higher one -- a price that never moved is not "at its lowest".
-- Every part reads the wishlist's own apps only (`IN (SELECT appid FROM items)`): through
-- v_price_latest, v_price_range and v_hours, which read every app, the view took 4.0 ms for 16
-- games on the user's library; this way 0.5 ms, the same rows (checked row for row).
CREATE VIEW v_wishlist_now AS
WITH mine AS (
    SELECT w.appid, w.priority, w.date_added, w.first_seen, w.last_seen, w.removed_at,
           COALESCE(a.persona, 'Account ' || a.account_id) AS account
    FROM wishlist w
    JOIN steam_account a ON a.account_id = w.account_id
    WHERE a.is_mine = 1),
items AS (
    SELECT appid,
           COALESCE(GROUP_CONCAT(CASE WHEN removed_at IS NULL THEN account END, ', ' ORDER BY account),
                    GROUP_CONCAT(account, ', ' ORDER BY account)) AS accounts,
           COUNT(*) - COUNT(removed_at)                       AS lists,
           MIN(priority)                                      AS priority,
           MIN(date_added)                                    AS date_added,
           MIN(first_seen)                                    AS first_seen,
           MAX(last_seen)                                     AS last_seen,
           CASE WHEN COUNT(removed_at) = COUNT(*) THEN MAX(removed_at) END AS removed_at
    FROM mine
    GROUP BY appid),
series AS (
    SELECT p.*,
           ROW_NUMBER() OVER (PARTITION BY p.appid ORDER BY p.observed_at DESC) AS newest,
           COUNT(*)     OVER (PARTITION BY p.appid)                            AS observations,
           MIN(p.observed_at) OVER (PARTITION BY p.appid)                      AS first_observed
    FROM price_snapshot p
    WHERE p.appid IN (SELECT appid FROM items)),
priced AS (
    SELECT appid, final_cents, observed_at,
           ROW_NUMBER() OVER (PARTITION BY appid ORDER BY final_cents, observed_at)      AS low,
           ROW_NUMBER() OVER (PARTITION BY appid ORDER BY final_cents DESC, observed_at) AS high
    FROM series WHERE kind = 'priced'),
steam AS (
    SELECT appid, SUM(minutes_total) AS minutes
    FROM (SELECT t.appid, t.minutes_total,
                 ROW_NUMBER() OVER (PARTITION BY t.account_id, t.appid ORDER BY t.observed_at DESC) AS newest
          FROM steam_playtime t
          JOIN steam_account a ON a.account_id = t.account_id AND a.is_mine = 1
          WHERE t.appid IN (SELECT appid FROM items))
    WHERE newest = 1
    GROUP BY appid),
launcher AS (
    SELECT steam_appid AS appid, SUM(COALESCE(playtime_seconds, 0)) / 60.0 AS minutes
    FROM game
    WHERE steam_appid IN (SELECT appid FROM items)
    GROUP BY steam_appid)
SELECT i.appid, s.name, s.has_record, s.app_type,
       i.accounts, i.lists, i.priority, i.date_added, i.first_seen, i.last_seen, i.removed_at,
       p.kind, p.currency, p.initial_cents, p.final_cents, p.discount_percent, p.observed_at,
       p.observations, p.first_observed, low.final_cents AS lowest_cents, low.observed_at AS lowest_on,
       high.final_cents AS highest_cents,
       CASE WHEN p.kind = 'priced' AND p.observations >= 2 AND p.final_cents = low.final_cents
                 AND high.final_cents > low.final_cents THEN 1 ELSE 0 END AS is_lowest_now,
       CASE WHEN l.minutes IS NOT NULL OR st.minutes IS NOT NULL
            THEN COALESCE(l.minutes, 0) + COALESCE(st.minutes, 0) END AS minutes_played
FROM items i
JOIN steam_app s ON s.appid = i.appid
LEFT JOIN series   p    ON p.appid = i.appid AND p.newest = 1
LEFT JOIN priced   low  ON low.appid = i.appid AND low.low = 1
LEFT JOIN priced   high ON high.appid = i.appid AND high.high = 1
LEFT JOIN steam    st   ON st.appid = i.appid
LEFT JOIN launcher l    ON l.appid = i.appid;

-- == Version 8 (Phase 101): three tables -- the price alerts of Phase 101, the ratings of Phase 102 -- and
-- game's two columns above. The same objects as upgrades/008_alerts_ratings_marks.sql, which explains
-- them. ==

-- One target per wished game: "tell me when it costs this or less". cents is the amount in the currency the
-- game's price was in when the target was set; set_at, when. A new target replaces the old one; "Remove
-- alert" deletes the row -- a setting, not a series.
CREATE TABLE price_target (
    appid     INTEGER PRIMARY KEY REFERENCES steam_app (appid),
    cents     INTEGER NOT NULL CHECK (cents > 0),
    currency  TEXT    NOT NULL CHECK (length(currency) = 3 AND currency = upper(currency)),
    set_at    TEXT    NOT NULL CHECK (set_at GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00')
) STRICT;

-- The alert log: one row per alert sent, only ever added to. (appid, observed_at) is the price that set it
-- off -- a row of the series; kind, why: 'lowest', strictly below every earlier price of the game, or
-- 'target', at or under its target. The key is what makes an alert fire once per drop: the same price seen
-- again is no new row. final_cents and currency are the price as the message told it; sent_at, when.
CREATE TABLE price_alert (
    appid        INTEGER NOT NULL,
    observed_at  TEXT    NOT NULL,
    kind         TEXT    NOT NULL CHECK (kind IN ('lowest', 'target')),
    final_cents  INTEGER NOT NULL CHECK (final_cents >= 0),
    currency     TEXT    NOT NULL CHECK (length(currency) = 3 AND currency = upper(currency)),
    sent_at      TEXT    NOT NULL CHECK (sent_at GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'),
    PRIMARY KEY (appid, observed_at, kind),
    FOREIGN KEY (appid, observed_at) REFERENCES price_snapshot (appid, observed_at),
    CHECK (sent_at >= observed_at)
) STRICT;

-- Phase 102's: a session's rating, 1 to 5 stars, and when it was given. Created here, read by nothing yet.
-- The session is named by its game and its start (session's own UNIQUE pair, which survives a rewrite --
-- its id does not). Checked when the transaction ends, not at each statement: the store writes a game's
-- sessions by deleting them and putting them back in one transaction (write_record), and a check at the
-- delete would refuse every save of a rated game. A session that is gone at the end -- pruned after
-- SESSION_KEEP_DAYS -- must take its rating with it in the same write: Phase 102's to do.
CREATE TABLE rating (
    game_id     INTEGER NOT NULL,
    started_at  TEXT    NOT NULL,
    stars       INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
    rated_at    TEXT    NOT NULL CHECK (rated_at GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9][+-][0-9][0-9]:[0-9][0-9]'),
    PRIMARY KEY (game_id, started_at),
    FOREIGN KEY (game_id, started_at) REFERENCES session (game_id, started_at) DEFERRABLE INITIALLY DEFERRED
) STRICT;
