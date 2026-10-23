-- Game Launcher: schema version 7 -> 8 (Phase 101), planned for three phases at once, so a friend's library
-- is upgraded once: price alerts on the wishlist (Phase 101), a session's rating (Phase 102), dated status
-- marks and nudges (Phase 103). Additive only: three tables and two columns on game; nothing in the earlier
-- versions changes, and every row already there keeps every value it had.
-- docs/BAZA_DE_DATE.md section 5 (Versiunea 8) explains it; schema.sql holds the same objects.
--
-- The moments: a price's are UTC, as the price series is (price_snapshot.observed_at); a game's and a
-- session's are local wall time with the offset, as session.started_at and game.last_played are.

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

-- Phase 103's: when a game's mark (Playing, Finished, Dropped) was last set or cleared, and when the
-- launcher last nudged about it. NULL for every game already there: when a mark was set before version 8 is
-- not known, and is not guessed. status_changed_at is written from Phase 101 on, so the dates gather.
ALTER TABLE game ADD COLUMN status_changed_at TEXT CHECK (status_changed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9][+-][0-9][0-9]:[0-9][0-9]');
ALTER TABLE game ADD COLUMN nudged_at TEXT CHECK (nudged_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9][+-][0-9][0-9]:[0-9][0-9]');
