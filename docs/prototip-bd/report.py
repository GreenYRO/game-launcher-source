"""Cele 15 intrebari ale prototipului, ca SQL, cu rezultatele ca tabele Markdown.

    python report.py <fisierul .db> [--out report.md]
"""
import sqlite3, sys, io
if "--out" in sys.argv:
    sys.stdout = io.TextIOWrapper(open(sys.argv[sys.argv.index("--out") + 1], "wb"), encoding="utf-8")
con = sqlite3.connect(sys.argv[1])
con.row_factory = sqlite3.Row

LIB = """lib AS (
  SELECT v.*, CASE WHEN v.is_tool IS NOT NULL THEN v.is_tool
                   WHEN v.app_type IS NOT NULL AND v.app_type != 'game' AND v.appid_source = 'manifest' THEN 1
                   ELSE 0 END AS non_game
  FROM v_library v)"""

def show(title, sql, note=None):
    print(f"\n### {title}\n")
    print("```sql\n" + sql.strip() + "\n```\n")
    rows = con.execute(sql).fetchall()
    if not rows:
        print("_(niciun rând)_")
    else:
        cols = rows[0].keys()
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for r in rows:
            print("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    if note:
        print(f"\n{note}")

show("1. Biblioteca pe surse", f"""
WITH {LIB}
SELECT source AS sursa, COUNT(*) AS cunoscute, SUM(installed) AS instalate,
       SUM(installed AND NOT hidden AND NOT non_game) AS vizibile,
       ROUND(SUM(playtime_seconds) / 3600.0, 1) AS ore_cronometrate,
       ROUND(SUM(CASE WHEN installed THEN size_on_disk ELSE 0 END) / 1e9, 0) AS gb_pe_disc
FROM lib GROUP BY source ORDER BY cunoscute DESC;""")

show("2. Ore jucate pe gen (orele unui joc cu mai multe genuri se împart egal între ele)", """
WITH g AS (
  SELECT game.id, game.playtime_seconds, sag.genre_id, COUNT(*) OVER (PARTITION BY game.id) AS n
  FROM game JOIN steam_app_genre sag ON sag.appid = game.steam_appid
  WHERE game.playtime_seconds > 0),
total AS (SELECT SUM(playtime_seconds) AS s FROM game WHERE id IN (SELECT id FROM g))
SELECT genre.name AS gen, ROUND(SUM(g.playtime_seconds / 3600.0 / g.n), 1) AS ore,
       ROUND(100.0 * SUM(g.playtime_seconds * 1.0 / g.n) / (SELECT s FROM total), 0) AS procent,
       COUNT(DISTINCT g.id) AS jocuri
FROM g JOIN genre ON genre.id = g.genre_id GROUP BY genre.name ORDER BY ore DESC;""",
note=con.execute("SELECT ROUND(SUM(playtime_seconds)/3600.0,1) || ' ore din ' || (SELECT ROUND(SUM(playtime_seconds)/3600.0,1) FROM game) || ' sunt pe jocuri fără înregistrare Steam, deci fără gen (' || COUNT(*) || ' jocuri).' FROM game WHERE playtime_seconds > 0 AND steam_appid IS NULL").fetchone()[0])

show("3. Când joc: sesiuni pe ora locală a zilei", """
SELECT CASE WHEN h < 6 THEN 'noapte 00-05' WHEN h < 12 THEN 'dimineață 06-11'
            WHEN h < 18 THEN 'după-amiază 12-17' ELSE 'seară 18-23' END AS interval,
       COUNT(*) AS sesiuni, SUM(minutes) AS minute, ROUND(AVG(minutes), 0) AS medie_min
FROM (SELECT CAST(substr(started_at, 12, 2) AS INTEGER) AS h, minutes FROM session)
GROUP BY 1 ORDER BY MIN(h);""")

show("3b. Capcana fusului orar: aceeași întrebare cu strftime, care convertește la UTC", """
SELECT substr(started_at, 20) AS offset_stocat, COUNT(*) AS sesiuni,
       SUM(strftime('%H', started_at) != substr(started_at, 12, 2)) AS ora_raportata_gresit
FROM session GROUP BY 1;""")

show("4. Sesiuni pe ziua săptămânii (ora locală)", """
SELECT CASE strftime('%w', substr(started_at, 1, 19))
         WHEN '1' THEN '1 luni' WHEN '2' THEN '2 marți' WHEN '3' THEN '3 miercuri' WHEN '4' THEN '4 joi'
         WHEN '5' THEN '5 vineri' WHEN '6' THEN '6 sâmbătă' ELSE '7 duminică' END AS zi,
       COUNT(*) AS sesiuni, SUM(minutes) AS minute
FROM session GROUP BY 1 ORDER BY 1;""")

show("5. Cât durează o sesiune: mediana pe joc (jocurile cu cel puțin 3 sesiuni)", f"""
WITH {LIB}, ranked AS (
  SELECT game_id, minutes, ROW_NUMBER() OVER (PARTITION BY game_id ORDER BY minutes) AS rn,
         COUNT(*) OVER (PARTITION BY game_id) AS n FROM session),
med AS (SELECT game_id, n, AVG(minutes) AS mediana FROM ranked
        WHERE rn IN ((n + 1) / 2, (n + 2) / 2) GROUP BY game_id)
SELECT lib.name AS joc, med.n AS sesiuni, ROUND(med.mediana, 0) AS mediana_min,
       ROUND(AVG(s.minutes), 0) AS medie_min, MAX(s.minutes) AS maxim_min
FROM med JOIN lib ON lib.id = med.game_id JOIN session s ON s.game_id = med.game_id
WHERE med.n >= 3 GROUP BY med.game_id ORDER BY med.mediana;""",
note="Mediana tuturor sesiunilor: " + str(con.execute("WITH r AS (SELECT minutes, ROW_NUMBER() OVER (ORDER BY minutes) rn, COUNT(*) OVER () n FROM session) SELECT AVG(minutes) FROM r WHERE rn IN ((n+1)/2,(n+2)/2)").fetchone()[0]) + " minute. Media: " + str(round(con.execute("SELECT AVG(minutes) FROM session").fetchone()[0])) + " minute (media e trasă în sus de câteva sesiuni lungi, de aceea recomandarea „ce încape în timpul disponibil” va folosi mediana).")

show("6. Cost pe oră la prețul de listă (proxy: nu e prețul plătit)", f"""
WITH {LIB}
SELECT name AS joc, ROUND(price_final_cents / 100.0, 2) AS pret_lista_eur,
       ROUND(playtime_seconds / 3600.0, 1) AS ore,
       ROUND(price_final_cents / 100.0 / (playtime_seconds / 3600.0), 2) AS eur_pe_ora
FROM lib WHERE playtime_seconds >= 1800 AND price_final_cents > 0
ORDER BY eur_pe_ora LIMIT 10;""",
note=con.execute("SELECT 'Suma prețurilor de listă ale jocurilor cunoscute cu preț: ' || ROUND(SUM(price_final_cents)/100.0, 0) || ' EUR pe ' || COUNT(*) || ' jocuri; ' || SUM(discount_percent > 0) || ' aveau reducere în ziua interogării Steam.' FROM steam_app WHERE price_final_cents > 0").fetchone()[0])

show("7. Instalate și nepornite niciodată (nici aici, nici în Steam; Xbox nu știe)", f"""
WITH {LIB}
SELECT name AS joc, source AS sursa, ROUND(size_on_disk / 1e9, 1) AS gb,
       CAST(julianday('now') - julianday(first_seen) AS INTEGER) AS zile_de_cand_e_stiut
FROM lib WHERE installed AND NOT hidden AND NOT non_game AND playtime_seconds = 0
  AND last_played IS NULL AND store_last_played IS NULL
  AND (launch_kind = 'exe' OR source = 'steam')  -- Xbox si Epic nu spun cand a fost jucat ceva: necunoscut, nu niciodata
  AND (launch_kind = 'exe' OR source = 'steam')  -- Xbox și Epic nu spun când a fost jucat ceva: necunoscut, nu „niciodată"
ORDER BY gb DESC;""")

show("8. Spațiu de recuperat: instalate, cronometrabile, nejucate de peste 60 de zile", f"""
WITH {LIB}
SELECT name AS joc, ROUND(size_on_disk / 1e9, 1) AS gb, ROUND(playtime_seconds / 3600.0, 1) AS ore,
       CAST(julianday('now') - julianday(COALESCE(last_played, first_seen)) AS INTEGER) AS zile_de_la_ultima_sesiune
FROM lib WHERE installed AND launch_kind = 'exe' AND NOT hidden AND NOT non_game
  AND julianday('now') - julianday(COALESCE(last_played, first_seen)) > 60
ORDER BY gb DESC;""")

show("9. Dezvoltatori și editori cu mai mult de un joc în bibliotecă", """
SELECT company.name AS companie, sac.role AS rol, COUNT(*) AS jocuri,
       ROUND(SUM(COALESCE(g.playtime_seconds, 0)) / 3600.0, 1) AS ore
FROM steam_app_company sac JOIN company ON company.id = sac.company_id
  LEFT JOIN game g ON g.steam_appid = sac.appid
GROUP BY company.name, sac.role HAVING COUNT(*) > 1 ORDER BY jocuri DESC, ore DESC;""")

show("10. Totalul stocat față de suma sesiunilor (bugul din faza 53, nereparat retroactiv)", f"""
WITH {LIB}, s AS (SELECT game_id, COUNT(*) AS n, SUM(minutes) AS minute FROM session GROUP BY game_id)
SELECT lib.name AS joc, s.n AS sesiuni, ROUND(lib.playtime_seconds / 3600.0, 2) AS ore_total,
       ROUND(s.minute / 60.0, 2) AS ore_sesiuni,
       ROUND(100.0 * lib.playtime_seconds / 60.0 / s.minute, 0) AS procent
FROM s JOIN lib ON lib.id = s.game_id ORDER BY s.minute DESC LIMIT 8;""",
note=con.execute("WITH s AS (SELECT game_id, SUM(minutes) m FROM session GROUP BY game_id) SELECT 'Pe toate jocurile cu sesiuni: ' || ROUND(SUM(g.playtime_seconds)/3600.0,1) || ' ore în totaluri față de ' || ROUND(SUM(s.m)/60.0,1) || ' ore în sesiuni (' || ROUND(100.0*SUM(g.playtime_seconds)/60.0/SUM(s.m),0) || '%).' FROM s JOIN game g ON g.id = s.game_id").fetchone()[0])

show("11. Metacritic față de orele mele (doar 8 jocuri au scor: prea puține pentru o concluzie)", f"""
WITH {LIB}
SELECT name AS joc, metacritic_score AS metacritic, ROUND(playtime_seconds / 3600.0, 1) AS ore, status
FROM lib WHERE metacritic_score IS NOT NULL ORDER BY metacritic_score DESC;""")

show("12. Cât de vechi sunt jocurile: după anul lansării", f"""
WITH {LIB}
SELECT CASE WHEN release_date < '2010' THEN 'înainte de 2010' WHEN release_date < '2020' THEN '2010-2019'
            WHEN release_date < '2024' THEN '2020-2023' ELSE '2024-2026' END AS perioada,
       COUNT(*) AS jocuri, ROUND(SUM(playtime_seconds) / 3600.0, 1) AS ore
FROM lib WHERE release_date IS NOT NULL GROUP BY 1 ORDER BY MIN(release_date);""")

show("13. Trăsături: controller, single/multiplayer, DualSense", """
SELECT category.name AS categorie, COUNT(DISTINCT sac.appid) AS jocuri,
       ROUND(100.0 * COUNT(DISTINCT sac.appid) / (SELECT COUNT(*) FROM steam_app WHERE app_type = 'game'), 0) AS procent_din_jocurile_steam
FROM steam_app_category sac JOIN category ON category.id = sac.category_id
  JOIN steam_app ON steam_app.appid = sac.appid AND steam_app.app_type = 'game'
WHERE category.name IN ('Single-player', 'Multi-player', 'Full controller support', 'Partial Controller Support',
                        'DualSense Controller Support', 'Steam Achievements', 'Co-op', 'Online PvP')
GROUP BY category.name ORDER BY jocuri DESC;""")

show("14. Ce nu vede baza de date: jocurile al căror timp e necunoscut", f"""
WITH {LIB}
SELECT CASE WHEN launch_kind = 'uri' THEN 'pornite prin Steam/Epic/Xbox (necronometrate)' ELSE 'cu exe propriu (cronometrate)' END AS fel,
       COUNT(*) AS jocuri_vizibile, ROUND(SUM(playtime_seconds) / 3600.0, 1) AS ore_cunoscute
FROM lib WHERE installed AND NOT hidden AND NOT non_game GROUP BY 1;""",
note="Prima sesiune înregistrată: " + con.execute("SELECT MIN(substr(started_at,1,10)) FROM session").fetchone()[0] + ". Jocuri Steam cu „ultima jucare” din manifestul Steam dar fără nicio oră cunoscută aici: " + str(con.execute("SELECT COUNT(*) FROM install i JOIN game g ON g.id = i.game_id WHERE g.source = 'steam' AND i.extra LIKE '%last_played_unix%'").fetchone()[0]) + ".")

show("15. Sămânța recomandării: cele mai asemănătoare jocuri cu cel mai jucat joc cu înregistrare Steam (Jaccard pe genuri + categorii)", """
WITH feat AS (SELECT appid, 'g' || genre_id AS f FROM steam_app_genre
              UNION ALL SELECT appid, 'c' || category_id FROM steam_app_category),
sz AS (SELECT appid, COUNT(*) AS n FROM feat GROUP BY appid),
t AS (SELECT steam_appid AS appid, COALESCE(custom_name, known_as) AS name FROM game
      WHERE steam_appid IS NOT NULL ORDER BY playtime_seconds DESC LIMIT 1),
shared AS (SELECT b.appid, COUNT(*) AS k FROM feat a JOIN t ON a.appid = t.appid
           JOIN feat b ON b.f = a.f AND b.appid != a.appid GROUP BY b.appid)
SELECT t.name AS pentru, s.name AS asemanator, shared.k AS trasaturi_comune,
       ROUND(shared.k * 1.0 / (sa.n + sb.n - shared.k), 2) AS jaccard,
       ROUND(COALESCE(g.playtime_seconds, 0) / 3600.0, 1) AS ore_jucate_deja
FROM shared JOIN t JOIN steam_app s ON s.appid = shared.appid
  JOIN sz sa ON sa.appid = t.appid JOIN sz sb ON sb.appid = shared.appid
  LEFT JOIN game g ON g.steam_appid = s.appid
WHERE s.app_type = 'game' ORDER BY jaccard DESC LIMIT 6;""")
