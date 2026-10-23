-- Game Launcher: schema version 1 -> 2 (Phase 73), prices.
-- docs/BAZA_DE_DATE.md, section 18, explains the upgrade; section 4 the two tables.
--
-- Additive only -- expand before contract: two tables, an index and three views are added;
-- nothing is dropped, renamed or rewritten. data_access/library_db.upgrade runs this file in
-- one transaction with the version bump, so the file is either upgraded whole or left as it
-- was. schema.sql holds the same statements, word for word, for a database created fresh.

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
