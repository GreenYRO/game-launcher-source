"""Prototip de unica folosinta (8 octombrie 2026): incarca datele JSON ale launcherului in schema propusa
pentru faza 54 si verifica, prin numarare, ca nimic nu s-a pierdut. Citeste doar data/; nu scrie nimic acolo.

    python build.py <folderul data> <fisierul .db de creat>
"""
import json, sqlite3, sys, os
from datetime import datetime
from pathlib import Path

DATA = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
if OUT.exists():
    OUT.unlink()

DDL = """
CREATE TABLE steam_app (
  appid INTEGER PRIMARY KEY, name TEXT NOT NULL, app_type TEXT, is_free INTEGER,
  release_date TEXT, release_text TEXT,
  price_initial_cents INTEGER, price_final_cents INTEGER, discount_percent INTEGER, currency TEXT,
  metacritic_score INTEGER, recommendations INTEGER, controller_support TEXT, required_age INTEGER,
  achievements_total INTEGER, short_description TEXT, fetched_at TEXT, stub INTEGER NOT NULL DEFAULT 0);
CREATE TABLE genre (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE steam_app_genre (appid INTEGER NOT NULL REFERENCES steam_app(appid), genre_id INTEGER NOT NULL REFERENCES genre(id), PRIMARY KEY (appid, genre_id));
CREATE TABLE category (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE steam_app_category (appid INTEGER NOT NULL REFERENCES steam_app(appid), category_id INTEGER NOT NULL REFERENCES category(id), PRIMARY KEY (appid, category_id));
CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE steam_app_company (appid INTEGER NOT NULL REFERENCES steam_app(appid), company_id INTEGER NOT NULL REFERENCES company(id), role TEXT NOT NULL CHECK (role IN ('developer','publisher')), PRIMARY KEY (appid, company_id, role));
CREATE TABLE game (
  id INTEGER PRIMARY KEY, identity_key TEXT NOT NULL UNIQUE, source TEXT NOT NULL, source_id TEXT,
  known_as TEXT NOT NULL, custom_name TEXT, custom_exe TEXT, launch_args TEXT,
  steam_appid INTEGER REFERENCES steam_app(appid), appid_source TEXT CHECK (appid_source IN ('manifest','search')),
  is_tool INTEGER, hidden INTEGER NOT NULL DEFAULT 0, favorite INTEGER NOT NULL DEFAULT 0,
  status TEXT CHECK (status IN ('playing','finished','dropped')), notes TEXT, is_new INTEGER NOT NULL DEFAULT 0,
  first_seen TEXT NOT NULL, last_played TEXT, playtime_seconds INTEGER NOT NULL DEFAULT 0,
  cover_path TEXT, banner_path TEXT, save_dirs_checked TEXT, carried_to INTEGER REFERENCES game(id), carried_at TEXT);
CREATE TABLE install (
  game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE, install_dir TEXT NOT NULL,
  launch_kind TEXT NOT NULL CHECK (launch_kind IN ('exe','uri')), launch_target TEXT NOT NULL, working_dir TEXT,
  icon_hint TEXT, size_on_disk INTEGER, detection TEXT, alternatives TEXT NOT NULL DEFAULT '[]',
  extra TEXT NOT NULL DEFAULT '{}', store_last_played TEXT, scanned_at TEXT NOT NULL);
CREATE TABLE session (id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL, minutes INTEGER NOT NULL, UNIQUE (game_id, started_at));
CREATE TABLE save_folder (game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE, path TEXT NOT NULL,
  ignored INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (game_id, path));
CREATE TABLE lineage (game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
  earlier_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
  relation TEXT NOT NULL CHECK (relation IN ('carried_from','not_same')), PRIMARY KEY (game_id, earlier_id));
CREATE VIEW v_library AS
  SELECT g.id, g.identity_key, g.source, COALESCE(g.custom_name, g.known_as) AS name,
         i.game_id IS NOT NULL AS installed, i.launch_kind, i.size_on_disk, i.store_last_played, g.steam_appid, g.appid_source,
         g.is_tool, g.hidden, g.favorite, g.status, g.first_seen, g.last_played, g.playtime_seconds,
         s.app_type, s.price_final_cents, s.currency, s.release_date, s.metacritic_score, s.controller_support
  FROM game g LEFT JOIN install i ON i.game_id = g.id LEFT JOIN steam_app s ON s.appid = g.steam_appid;
"""

def parse_release(text):
    if not text:
        return None
    for fmt in ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y", "%b %Y", "%B %Y", "%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None

def key_source(key):
    for s in ("steam", "gog", "epic", "ubisoft", "xbox"):
        if key.startswith(s + ":"):
            return s, key[len(s) + 1:]
    return "folders", None

sys.path.insert(0, str(DATA.parent))
from shared import naming
search = json.loads((DATA / "cache" / "steam_search.json").read_text(encoding="utf-8")).get("names", {})
recovered = []
con = sqlite3.connect(OUT)
con.execute("PRAGMA foreign_keys = ON")
con.executescript(DDL)
notes = []

# --- steam_app and satellites, from the cached full records
details_dir = DATA / "cache" / "steam_details"
web = json.loads((DATA / "cache" / "steam_web.json").read_text(encoding="utf-8")).get("apps", {})
unparsed = []
for f in sorted(details_dir.glob("*.json")):
    r = json.loads(f.read_text(encoding="utf-8"))
    if "steam_appid" not in r:
        notes.append(f"{f.name}: no steam_appid (has_details false?) skipped")
        continue
    appid = int(r["steam_appid"])
    price = r.get("price_overview") or {}
    rel = (r.get("release_date") or {}).get("date")
    rel_iso = parse_release(rel)
    if rel and not rel_iso:
        unparsed.append((appid, rel))
    ra = r.get("required_age")
    try:
        ra = int(ra) if ra not in (None, "") else None
    except ValueError:
        ra = None
    con.execute("""INSERT INTO steam_app (appid, name, app_type, is_free, release_date, release_text,
        price_initial_cents, price_final_cents, discount_percent, currency, metacritic_score, recommendations,
        controller_support, required_age, achievements_total, short_description, fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        appid, r.get("name"), r.get("type"), int(bool(r.get("is_free"))), rel_iso, rel,
        price.get("initial"), price.get("final"), price.get("discount_percent"), price.get("currency"),
        (r.get("metacritic") or {}).get("score"), (r.get("recommendations") or {}).get("total"),
        r.get("controller_support"), ra, (r.get("achievements") or {}).get("total"),
        r.get("short_description"), (web.get(str(appid)) or {}).get("fetched_at")))
    for g in r.get("genres") or []:
        con.execute("INSERT OR IGNORE INTO genre (id, name) VALUES (?, ?)", (int(g["id"]), g["description"]))
        con.execute("INSERT OR IGNORE INTO steam_app_genre VALUES (?, ?)", (appid, int(g["id"])))
    for c in r.get("categories") or []:
        con.execute("INSERT OR IGNORE INTO category (id, name) VALUES (?, ?)", (int(c["id"]), c["description"]))
        con.execute("INSERT OR IGNORE INTO steam_app_category VALUES (?, ?)", (appid, int(c["id"])))
    for role, field in (("developer", "developers"), ("publisher", "publishers")):
        for name in r.get(field) or []:
            con.execute("INSERT OR IGNORE INTO company (name) VALUES (?)", (name,))
            cid = con.execute("SELECT id FROM company WHERE name = ?", (name,)).fetchone()[0]
            con.execute("INSERT OR IGNORE INTO steam_app_company VALUES (?, ?, ?)", (appid, cid, role))

# --- games: every override record, plus any catalog entry without one
ov = json.loads((DATA / "overrides.json").read_text(encoding="utf-8"))["games"]
cat = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
entries = {e["identity_key"]: e for e in cat["entries"]}
keys = list(ov.keys()) + [k for k in entries if k not in ov]
ids = {}
stubs = 0
for key in keys:
    rec = ov.get(key, {})
    e = entries.get(key)
    if e:
        source, source_id = e["source"], e["source_id"]
        name = rec.get("known_as") or e["display_name"]
        appid = (e.get("extra") or {}).get("appid")
        appid_source = "search" if (e.get("extra") or {}).get("appid_source") else ("manifest" if appid else None)
    else:
        source, source_id = key_source(key)
        folder = key.replace("/", chr(92)).rsplit(chr(92), 1)[-1]
        name = rec.get("known_as") or rec.get("name") or naming.clean_folder_name(folder)
        appid = rec.get("appid")
        appid_source = "search" if appid else None
        if not appid and source == "folders":
            hit = search.get(naming.normalize(name))
            if hit and hit.get("appid") and float(hit.get("ratio") or 0) >= 0.85:
                appid, appid_source = hit["appid"], "search"
                recovered.append((name, hit["matched_name"]))
    appid = int(appid) if appid else None
    if appid and not con.execute("SELECT 1 FROM steam_app WHERE appid = ?", (appid,)).fetchone():
        w = web.get(str(appid)) or {}
        con.execute("INSERT INTO steam_app (appid, name, app_type, fetched_at, stub) VALUES (?,?,?,?,1)",
                    (appid, name, w.get("app_type"), w.get("fetched_at")))
        stubs += 1
    is_tool = rec.get("is_tool")
    is_tool = None if is_tool is None else int(bool(is_tool))
    cur = con.execute("""INSERT INTO game (identity_key, source, source_id, known_as, custom_name, custom_exe, launch_args,
        steam_appid, appid_source, is_tool, hidden, favorite, status, notes, is_new, first_seen, last_played,
        playtime_seconds, cover_path, banner_path, save_dirs_checked, carried_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        key, source, source_id, name, rec.get("name"), rec.get("exe"), rec.get("args"), appid, appid_source,
        is_tool, int(bool(rec.get("hidden"))), int(bool(rec.get("favorite"))), rec.get("status"), rec.get("notes"),
        int(bool(rec.get("new"))), rec.get("first_seen") or cat["generated_at"], rec.get("last_played"),
        int(rec.get("playtime_seconds") or 0), rec.get("cover"), rec.get("banner"),
        json.dumps(rec.get("save_dirs_checked")) if rec.get("save_dirs_checked") is not None else None,
        rec.get("carried_at")))
    ids[key] = cur.lastrowid

dup_sessions = 0
for key, rec in ov.items():
    gid = ids[key]
    for s in rec.get("sessions") or []:
        before = con.total_changes
        con.execute("INSERT OR IGNORE INTO session (game_id, started_at, minutes) VALUES (?,?,?)",
                    (gid, s["start"], int(s["minutes"])))
        if con.total_changes == before:
            dup_sessions += 1
    for p in rec.get("save_dirs") or []:
        con.execute("INSERT OR IGNORE INTO save_folder VALUES (?,?,0)", (gid, p))
    for p in rec.get("save_dirs_ignored") or []:
        con.execute("INSERT OR IGNORE INTO save_folder VALUES (?,?,1)", (gid, p))
    for old in rec.get("earlier_keys") or []:
        if old in ids:
            con.execute("INSERT OR IGNORE INTO lineage VALUES (?,?,'carried_from')", (gid, ids[old]))
        else:
            notes.append(f"earlier key not found for {key[:40]}")
    for old in rec.get("not_same_as") or []:
        if old in ids:
            con.execute("INSERT OR IGNORE INTO lineage VALUES (?,?,'not_same')", (gid, ids[old]))
    if rec.get("carried_to") in ids:
        con.execute("UPDATE game SET carried_to = ? WHERE id = ?", (ids[rec["carried_to"]], gid))

for key, e in entries.items():
    con.execute("""INSERT INTO install (game_id, install_dir, launch_kind, launch_target, working_dir, icon_hint,
        size_on_disk, detection, alternatives, extra, store_last_played, scanned_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
        ids[key], e["install_dir"], e["launch_kind"], e["launch_target"], e.get("working_dir"), e.get("icon_hint"),
        e.get("size_on_disk"), e.get("detection"), json.dumps(e.get("alternatives") or []),
        json.dumps(e.get("extra") or {}),
        datetime.fromtimestamp(int(e["extra"]["last_played_unix"])).astimezone().isoformat(timespec="seconds")
            if (e.get("extra") or {}).get("last_played_unix") else None,
        cat["generated_at"]))
con.commit()

# --- the round-trip check: what the JSON holds versus what the tables hold
json_games = len(ov)
json_sessions = sum(len(r.get("sessions") or []) for r in ov.values())
json_minutes = sum(s["minutes"] for r in ov.values() for s in r.get("sessions") or [])
json_playtime = sum(int(r.get("playtime_seconds") or 0) for r in ov.values())
json_saves = sum(len(r.get("save_dirs") or []) for r in ov.values())
q = lambda sql: con.execute(sql).fetchone()[0]
print("CHECK games (override records):", json_games, "->", q("SELECT COUNT(*) FROM game WHERE identity_key IN (%s)" % ",".join("?" * 0) if False else "SELECT COUNT(*) FROM game"), "(catalog-only extras:", len(keys) - json_games, ")")
print("CHECK installs:", len(entries), "->", q("SELECT COUNT(*) FROM install"))
print("CHECK sessions:", json_sessions, "->", q("SELECT COUNT(*) FROM session"), "duplicates ignored:", dup_sessions)
print("CHECK session minutes:", json_minutes, "->", q("SELECT SUM(minutes) FROM session"))
print("CHECK playtime seconds:", json_playtime, "->", q("SELECT SUM(playtime_seconds) FROM game"))
print("CHECK save folders:", json_saves, "->", q("SELECT COUNT(*) FROM save_folder WHERE ignored = 0"))
print("CHECK steam_app:", q("SELECT COUNT(*) FROM steam_app"), "of which stubs (appid known, no cached record):", stubs)
print("CHECK genres:", q("SELECT COUNT(*) FROM genre"), "categories:", q("SELECT COUNT(*) FROM category"), "companies:", q("SELECT COUNT(*) FROM company"))
print("CHECK lineage rows:", q("SELECT COUNT(*) FROM lineage"), "carried_to set:", q("SELECT COUNT(*) FROM game WHERE carried_to IS NOT NULL"))
print("CHECK release dates unparsed:", unparsed)
print("CHECK fk violations:", con.execute("PRAGMA foreign_key_check").fetchall())
for n in notes:
    print("NOTE", n)
print("RECOVERED appids by name through the search cache:", len(recovered))
for a, b in recovered:
    print("   ", a, "->", b)
print("UNLINKED games with playtime and no appid:", con.execute("SELECT COUNT(*) || ' games, ' || ROUND(SUM(playtime_seconds)/3600.0,1) || ' h' FROM game WHERE steam_appid IS NULL AND playtime_seconds > 0").fetchone()[0])
print("   ", [r[0] for r in con.execute("SELECT known_as FROM game WHERE steam_appid IS NULL AND playtime_seconds > 1800 ORDER BY playtime_seconds DESC")])
con.close()
