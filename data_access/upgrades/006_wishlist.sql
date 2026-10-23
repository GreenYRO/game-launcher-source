-- Game Launcher: schema version 5 -> 6 (Phase 86), the Steam wishlist: what the user said he
-- wants (stated preference), beside what he plays (revealed preference, v_hours) and the price
-- series. Additive only: two tables and a view; nothing in the earlier versions changes.
-- docs/BAZA_DE_DATE.md section 5 (Versiunea 6) and docs/ANALIZA.md explain it; schema.sql holds
-- the same objects.
--
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
