# Ce poate spune baza de date: unsprezece rapoarte

Capitolul de analiză al lucrării. Fiecare raport este **o întrebare fixă, interogările SQL care îi
răspund (exact cum sunt în cod), răspunsul pe datele mele, ce nu pot vedea cifrele și ideea din
spatele lui**, cu numele ei în engleză între paranteze prima dată când apare. Aceleași unsprezece rapoarte
sunt în launcher, în tabul **Reports**, și pot fi scoase oricând din linia de comandă.

- Interogările: `data_access/reports.py` (câte o constantă pentru fiecare; un test verifică faptul că
  fiecare bloc SQL de mai jos este identic cu cel din cod).
- Forma raportului, coeficientul Gini și propozițiile: `logic/reports.py`.
- Linia de comandă: `reports.py` în rădăcina proiectului.

**Cifrele rapoartelor 1, 3, 5 și 7 sunt din 14 octombrie 2026**, de pe o copie a bazei mele
(`data\library.db`), la versiunea 5 a schemei; **ale rapoartelor 2, 4, 6 și 8, din 16 octombrie** (faza 91,
după cele trei corecturi de mai jos), la versiunea 6; ale secțiunii despre lista de dorințe, din 15 octombrie.
**Faza 93 (18 octombrie)** a adus sesiunile observate (secțiunea următoare) și versiunea 7 a schemei; în ziua
aceea biblioteca nu avea încă nicio sesiune observată, așa că niciun răspuns de mai jos nu s-a mișcat — se
vor mișca rapoartele 4, 5 și 7, pe măsură ce launcher-ul vede jocuri rulând. **Raportul 9** (faza 98) are cifrele din 18 octombrie 2026, **raportul 10** (faza 102) pe cele din 20 octombrie, **raportul 11** (faza 103) pe cele din 21 octombrie. **Când lucrarea are nevoie de ele din nou (în iunie), le reîmprospătez așa:**

```powershell
& .venv\Scripts\python.exe reports.py --markdown --out $env:TEMP\rapoarte.md
```

Comanda deschide baza **numai pentru citire** (nu poate scrie nimic în ea, iar launcher-ul poate fi
deschis în timp ce rulează) și scrie fiecare raport cu rândurile lui și cu data. Din fișierul acela
se copiază cifrele în secțiunile „Răspunsul” de mai jos. `--sql` adaugă și interogările, iar `--csv
<folder>` scrie câte un fișier CSV pentru fiecare raport, pentru Excel (punct și virgulă, virgulă
zecimală, ca în comparația exporturilor).

## Cuprins

- [Două surse de ore, niciodată amestecate](#două-surse-de-ore-niciodată-amestecate)
- [Ora de pe ceas și momentul](#ora-de-pe-ceas-și-momentul)
- [1. Concentrarea](#1-concentrarea)
- [2. Abandonul](#2-abandonul)
- [3. Profilurile](#3-profilurile)
- [4. Ce așteaptă (backlog)](#4-ce-așteaptă-backlog)
- [5. Sesiunile](#5-sesiunile)
- [6. Banii](#6-banii)
- [7. Calitatea datelor](#7-calitatea-datelor)
- [Lista de dorințe: preferința declarată lângă cea dezvăluită](#lista-de-dorințe-preferința-declarată-lângă-cea-dezvăluită)
- [8. Declarat și dezvăluit](#8-declarat-și-dezvăluit)
- [Recapitularea](#recapitularea)
- [9. Recomandarea](#9-recomandarea)
- [Notele: ce spun, lângă ce joc](#notele-ce-spun-lângă-ce-joc)
- [10. Spus și jucat](#10-spus-și-jucat)
- [Semnele, și când au fost puse](#semnele-și-când-au-fost-puse)
- [11. Terminarea](#11-terminarea)

## Două surse de ore, niciodată amestecate

Orele jucate vin din **două surse**, iar fiecare raport spune pe care o citește:

1. **Cronometrul launcher-ului** (`game.playtime_seconds` și tabela `session`): jocurile pornite de
   launcher prin executabilul lor, cronometrate la secundă de programul care le-a pornit
   (**instrumentare**, *instrumentation*), și — din faza 93 — jocurile pe care launcher-ul le **vede
   rulând** în lista proceselor cât timp rulează și el, oricine le-ar fi pornit (Steam, Epic, Xbox,
   scurtătura jocului): o **sesiune observată** (*observed session*), luată de un **observator pasiv**
   (*passive observer*) care se uită o dată la câteva secunde, deci cu fiecare capăt nesigur cu o
   privire (**rezoluția măsurării**, *measurement resolution*). Coloana `session.origin` spune care e
   care (`launched` sau `observed`). Un joc Steam are de acum sesiuni, dar orele lui rămân contorul
   Steam: o sesiune observată a unui joc Steam nu adaugă nimic la `playtime_seconds`, așa că cele două
   surse tot nu măsoară niciodată aceeași oră (**numărarea dublă**, *double counting*, evitată prin
   regula din `docs/BAZA_DE_DATE.md`). Ce s-a jucat cât launcher-ul nu rula nu e nicăieri.
2. **Contoarele Steam**, pe conturile marcate „Mine” în Settings (vederea `v_steam_time_mine`): timpul
   total pe care Steam îl ține singur, în minute întregi, de la crearea contului. Nu are sesiuni.

Vederea **`v_hours`** (versiunea 5 a schemei, `upgrades/005_hours.sql`; doar o vedere, ca versiunea 4)
le pune una lângă alta:

- **un rând pentru fiecare aplicație Steam**, oriunde există una: minutele Steam o singură dată, plus
  timpul launcher-ului al fiecărui joc legat de aplicația aceea, adunat. Două foldere ale aceluiași
  joc (cele două `Silent Hill 2` ale mele) împart o aplicație, deci nicio aplicație nu e numărată de
  două ori;
- **un rând pentru fiecare joc fără aplicație Steam** (o instalare din folder, nelegată de Steam);
- **fiecare joc cunoscut vreodată**, instalat sau nu. Mutarea istoriei unui joc pe o instalare nouă
  (faza 36) mută timpul, nu îl copiază, deci nimic nu apare de două ori;
- coloana `source` spune de unde vine timpul: `launcher`, `steam`, `both` (amândouă) sau nimic.

Patru jocuri au timp din ambele surse: o copie cronometrată de launcher și copia mea din Steam. Sunt
două jocuri diferite, deci adunarea lor este corectă. Trei dintre legături vin însă dintr-o
potrivire după nume, iar raportul 7 le arată.

```sql
-- view v_hours (upgrades/005_hours.sql)
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
```

**Ce e joc.** Rapoartele 1–5 numără doar jocuri (expresia comună `games`, prezentă în fiecare
interogare):

- **lăsate deoparte, peste tot:** Spacewar (480) și Source SDK Base 2007 (218) (`rules.STEAM_NOT_GAMES`).
  Orele lor sunt ale altor jocuri: un joc care folosește Steam fără să fie vândut acolo își raportează
  timpul sub Spacewar, iar modurile Source rulează pe SDK. Sunt lăsate deoparte **la analiză, nu la
  colectare**: baza și exporturile prietenilor le păstrează așa cum au fost citite. Comparația
  exporturilor le lasă deoparte la fel;
- **nici uneltele** pe care le-am marcat așa;
- **numărate:** aplicațiile marcate „joc”, cele de tip Steam „game” și cele al căror tip nu e cunoscut
  încă (fără fișă în magazin).

Demo-urile, modurile și aplicația publicitară apar numai în raportul 7.

## Ora de pe ceas și momentul

O sesiune se păstrează ca **ora locală cu decalajul ei** (*wall time with an offset*): `+03:00` vara,
`+02:00` iarna. Funcțiile de dată ale lui SQLite **trec întâi în UTC**, așa că
`strftime('%H', started_at)` ar da ora UTC: vara cu trei ore mai devreme, iarna cu două. De aceea ora
zilei și ziua săptămânii se citesc **din textul stocat** (coloanele generate `started_local` și
`local_hour`, BAZA_DE_DATE §9, „Fusul orar”). Testul fazei 83 pune o sesiune de vară
(`2026-08-14T05:53:32+03:00`, ora 5 pe ceas, ora 2 după `strftime`) lângă una de iarnă
(`2026-11-03T21:15:00+02:00`, ora 21 pe ceas, 19 după `strftime`).

Momentele launcher-ului, adică ora unei citiri, ora unei observații de preț sau „când a fost luată fișa
din magazin”, sunt în schimb **momente** (*instants*), păstrate în UTC. Rapoartele le arată doar ca
zile.

## 1. Concentrarea

**Întrebarea.** Cât de inegal se împart orele între jocuri?

```sql
-- concentration
WITH games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0)
SELECT ROW_NUMBER() OVER ranked                                         AS rank,
       name, appid, game_id, source, minutes,
       minutes / SUM(minutes) OVER ()                                   AS share,
       SUM(minutes) OVER (ranked ROWS UNBOUNDED PRECEDING)
           / SUM(minutes) OVER ()                                       AS cumulative
FROM games
WHERE minutes > 0
WINDOW ranked AS (ORDER BY minutes DESC, name)
ORDER BY rank
```

Ponderile și sumele cumulate sunt SQL: funcții fereastră (*window functions*) peste jocurile ordonate
după minute. Coeficientul Gini se termină în Python (`logic/reports.gini`), din aceleași minute
sortate crescător $x_1 \le \dots \le x_n$:

$$G = \frac{2\sum_{i=1}^{n} i\,x_i}{n\sum_{i=1}^{n} x_i} - \frac{n+1}{n}$$

$G$ este 0 când toate jocurile au aceleași ore și $(n-1)/n$ când unul singur le are pe toate. Testul
verifică formula și pe definiția coeficientului, adică jumătate din diferența absolută medie relativă.

**Răspunsul (14 octombrie 2026).**

| Măsura | Valoarea |
|---|---|
| Jocuri cu ore | 343 |
| Ore pe ele | 10.145 |
| Primul (Counter-Strike 2) | 39% din ore |
| Primele 5 | 67% |
| Primele 10 | 78% |
| Primele 20 | 86% |
| Câte jocuri fac jumătate din ore | 2 |
| Câte fac 80% | 12 |
| Coeficientul Gini | 0,931 |

Counter-Strike 2 are singur 39% din orele mele, iar Team Fortress 2 adaugă 13%: două jocuri din 343
fac jumătate din tot timpul.

**Ce nu poate vedea.** Contează doar conturile Steam marcate ale mele și cronometrul launcher-ului
pentru restul. Timpul jucat cât launcher-ul nu rula — înainte să-l instalez, sau cu el închis — nu
apare; din faza 93, un joc pornit din scurtătura lui e văzut și numărat cât timp launcher-ul rulează.

**Ideea.** **Distribuția Pareto** (*Pareto distribution*, „regula 80/20”): câteva elemente țin cea
mai mare parte din total. **Curba Lorenz** (*Lorenz curve*) arată ce parte din ore au cele mai puțin
jucate x% dintre jocuri. Cu cât coboară mai mult sub diagonală, cu atât împărțirea e mai inegală.
**Coeficientul Gini** (*Gini coefficient*) este dublul ariei dintre curbă și diagonală.

## 2. Abandonul

**Întrebarea.** Câte dintre jocurile pornite în Steam au fost lăsate devreme?

```sql
-- abandonment
WITH games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0),
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
ORDER BY bucket
```

Expresia `started` dă fiecărei aplicații pornite **felul** ei, cum îl definește
`rules.REPORT_APP_KINDS`: **gratuită** dacă Steam o marchează gratuită (`is_free`) **sau** are genul Free To
Play (37), **fără înregistrare** dacă magazinul nu are nimic despre ea, **plătită** în rest (și cele care nu
se mai vând: s-au vândut cândva). Amândouă semnele de gratuitate contează pentru că fiecare prinde jocuri pe
care celălalt le scapă: pe 16 octombrie, dintre jocurile pornite, 65 le aveau pe amândouă, 8 doar semnul
(jocuri date gratis: Cry of Fear, Life is Strange – Episode 1), iar 20 doar genul (jocuri free-to-play a
căror înregistrare nu poartă semnul: Loadout, Robocraft).

**Răspunsul (16 octombrie 2026).** 315 jocuri pornite în Steam:

| Timp în Steam | Jocuri | Ponderea |
|---|---|---|
| sub 10 minute | 57 | 18% |
| 10 minute – 1 oră | 66 | 21% |
| 1–2 ore (fereastra de rambursare) | 51 | 16% |
| 2–10 ore | 81 | 26% |
| 10–100 de ore | 48 | 15% |
| peste 100 de ore | 12 | 3,8% |

**Dintre cele 165 de jocuri plătite pornite în Steam, 82 (50%) au rămas sub două ore**, fereastra de
rambursare Steam; alte 55 de titluri free-to-play și 37 de aplicații fără înregistrare au fost lăsate tot
sub două ore și se numără separat. Pe feluri:

| Felul | sub 10 minute | 10 minute – 1 oră | 1–2 ore | sub 2 ore | 2 ore sau mai mult |
|---|---|---|---|---|---|
| plătite | 21 | 35 | 26 | 82 (50%) | 83 |
| free-to-play | 21 | 24 | 10 | 55 (59%) | 38 |
| fără înregistrare | 15 | 7 | 15 | 37 (65%) | 20 |

Ponderea fiecărui fel e din propriile lui jocuri pornite. Pe 14 octombrie, toate la un loc, propoziția
spunea „177 de jocuri (56%)”: cifra amesteca jocuri care n-au costat nimic cu jocuri plătite, iar
jocurile gratuite sunt lăsate devreme mai des (59% față de 50%).

**Ce nu poate vedea.**

- „Pornit cel puțin o dată”: fișierul Steam conține doar aplicațiile lansate, așa că un joc cumpărat și
  nedeschis niciodată nu apare deloc. Un joc pornit, dar fără minute înregistrate, intră la „sub 10
  minute”.
- Fereastra de rambursare e aici **doar un prag de timp**: datele nu au data cumpărării, așa că nu spun
  niciodată că o rambursare ar fi fost posibilă.
- Fără înregistrare nu se poate spune nici dacă o aplicație a costat ceva; de aceea are rândul ei.

**Ideea.** **Fereastra de rambursare** (*refund window*): Steam returnează banii pentru un joc jucat
sub două ore, în 14 zile de la cumpărare. Este granița naturală dintre „am încercat” și „l-am
păstrat”. **Abandonul** (*attrition*): ponderea celor lăsate devreme. **Variabila de confuzie**
(*confounding variable*): ceva ce influențează și lucrul comparat, și rezultatul. Aici modelul de
afaceri (linia free-to-play a raportului 3) amestecă „lăsat devreme” cu „încercat pentru că era
gratis”: un joc gratuit se încearcă fiindcă încercarea nu costă nimic. De aceea jocurile plătite se
numără singure, iar celelalte separat.

## 3. Profilurile

**Întrebarea.** Spre ce fel de jocuri merg orele: gen, editor, dezvoltator, deceniul lansării?

```sql
-- profile_coverage
WITH games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0)
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
WHERE g.minutes > 0
```

```sql
-- profile_genres
WITH games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0)
SELECT genre.name                 AS label,
       SUM(g.minutes)             AS minutes,
       COUNT(*)                   AS apps
FROM games g
JOIN steam_app_genre sg ON sg.appid = g.appid
JOIN genre              ON genre.id = sg.genre_id
WHERE g.minutes > 0
  AND genre.id NOT IN (SELECT value FROM json_each(:not_genres))
GROUP BY genre.id
ORDER BY minutes DESC, label
```

```sql
-- profile_companies
WITH games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0)
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
ORDER BY c.role, minutes DESC, label
```

Editorii și dezvoltatorii vin dintr-o singură rulare (din faza 98), despărțiți după rol: fiecare rulare a expresiei `games` citește din nou orele din `v_hours`, iar cele nouă rapoarte trebuie să rămână sub 50 ms împreună. Răspunsul e același, rând cu rând.

```sql
-- profile_decades
WITH games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0)
SELECT substr(s.release_date, 1, 3) || '0s'   AS label,
       SUM(g.minutes)                         AS minutes,
       COUNT(*)                               AS apps
FROM games g
JOIN steam_app s ON s.appid = g.appid
WHERE g.minutes > 0 AND s.release_date IS NOT NULL
GROUP BY label
ORDER BY label
```

**Răspunsul (14 octombrie 2026).**

- **Acoperirea.** 9.988 din 10.145 ore au un gen cunoscut (98%), 9.928 un editor, 9.989 un dezvoltator
  și 9.991 o dată de lansare.
- **Genuri** (ponderea din orele cu gen): Action 87%, Adventure 20%, Strategy 17%, Indie 17%, Simulation
  15%, Massively Multiplayer 10%, RPG 6,2%.
- **Free To Play.** 62% din toate orele (6.274) sunt pe titluri gratuite.
- **Editori.** Valve 53%, Paradox Interactive 9,2%, Offworld 4,1%, Activision 3,5%.
- **Dezvoltatori.** Valve 53%, Paradox Development Studio 9,0%, Offworld 4,1%, Treyarch 3,2%.
- **Deceniul lansării.** Anii 2000: 13%; anii 2010: 74%; anii 2020: 12%.

**Ce nu poate vedea.**

- Un joc cu mai multe genuri, editori sau dezvoltatori se numără la fiecare, deci ponderile unei liste
  însumează mai mult de 100%. Testul pune un joc cu două genuri și îl găsește la amândouă.
  Comparația exporturilor (faza 81) împarte în schimb orele unui joc **egal** între genurile lui, ca
  ponderile fiecărui participant să însumeze 100%. Sunt două măsuri diferite, fiecare spusă unde
  apare.
- Early Access, Violent și Nudity nu sunt genuri: primul e o stare a lansării, celelalte descriu
  conținutul (`rules.STEAM_NOT_GENRES`).
- Numai aplicațiile cu fișă în magazinul Steam au genuri, editori și date. Un joc din folder fără
  legătură cu Steam nu are niciuna.

**Ideea.** **Acoperirea** (*coverage*): partea din date pe care o poate vedea o cifră, spusă lângă
fiecare pondere. **Model de afaceri, nu gen** (*business model versus genre*): Free To Play spune cum
își face un joc banii, nu ce fel de joc e. De aceea are linia lui, iar costul pe oră din raportul 6
se sprijină pe el.

## 4. Ce așteaptă (backlog)

**Întrebarea.** Ce e instalat și așteaptă: nejucat niciodată, sau abia încercat?

```sql
-- backlog
WITH installed AS (
    SELECT v.*, h.minutes, h.minutes_steam, h.steam_last_played
    FROM v_library v
    LEFT JOIN v_hours h ON h.appid = v.steam_appid
                        OR (v.steam_appid IS NULL AND h.game_id = v.id)
    WHERE v.installed = 1
      AND COALESCE(v.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(v.is_tool,
                   CASE WHEN v.app_type IS NOT NULL AND v.app_type != 'game'
                         AND v.appid_source = 'manifest' THEN 1 ELSE 0 END) = 0)
SELECT i.name, i.source, i.launch_kind, i.size_on_disk, i.steam_appid,
       COALESCE(i.minutes, 0)                                           AS minutes,
       p.kind                                                           AS price_kind,
       p.initial_cents, p.final_cents, p.currency,
       CASE WHEN i.launch_kind != 'exe' AND i.source != 'steam'
                 AND COALESCE(i.minutes, 0) = 0 AND i.last_played IS NULL   THEN 'unknown'
            WHEN COALESCE(i.minutes, 0) = 0 AND i.store_last_played IS NULL
                 AND i.last_played IS NULL AND i.steam_last_played IS NULL THEN 'never'
            WHEN COALESCE(i.minutes, 0) < :backlog_under                THEN 'under'
            ELSE 'played' END                                           AS state,
       i.id AS game_id, i.identity_key, i.hidden, i.status,
       i.last_played, i.store_last_played, i.steam_last_played,
       COALESCE(s.has_record, 0)                                        AS has_record
FROM installed i
LEFT JOIN v_price_latest p ON p.appid = i.steam_appid
LEFT JOIN steam_app s      ON s.appid = i.steam_appid
ORDER BY i.name COLLATE NOCASE
```

Expresia comună `installed` aplică regula grilei: o unealtă e o unealtă după semnul meu, sau după
tipul Steam când magazinul a spus ce aplicație este. Fiecare joc instalat primește orele lui din
`v_hours`. Din faza 98 interogarea poartă și câteva coloane pe care raportul 4 nu le arată
(înregistrarea, dacă jocul e ascuns sau marcat, cele trei date la care a fost jucat): **jocurile care
așteaptă din For you și din raportul 9 sunt chiar rândurile acestea**, nu o a doua copie a regulii.

**Răspunsul (16 octombrie 2026).**

- **Nejucate niciodată, nicăieri:** 3 jocuri instalate (Star Wars Episode I – Racer, The First
  Berserker Khazan, Worship). Ocupă 54,0 GB și valorează 89,24 € la prețul de listă și tot atât azi:
  niciunul nu e redus.
- **Jucate sub două ore, cu totul:** încă 8 (BloodBorne, Cinderia, CULTIC, Hytale Launcher, LEGO
  Batman: Legacy of the Dark Knight, PRAGMATA, SnowRunner, WARDOGS Playtest). Cinderia e redusă azi:
  17,49 € la prețul de listă, 13,99 € azi.
- **Nu se poate spune:** 2 jocuri Xbox (Minecraft Dungeons II, Minecraft Launcher).

**Ce nu poate vedea.** „Niciodată” înseamnă: niciun timp aici — nici pornit din launcher, nici văzut
rulând cât rula el —, nicio dată de la magazinul lui și niciun timp Steam pe conturile mele. Un joc
jucat cât launcher-ul nu rula, sau înainte de instalarea lui, pare nejucat. Un joc Epic, Xbox sau
Ubisoft fără niciun timp văzut e „nu se poate spune”: magazinul lui nu spune niciodată; cu timp văzut
(din faza 93), e jucat sau abia încercat, ca oricare altul. Două foldere ale aceluiași joc își împart
orele.

**Ideea.** **Backlog** (*„pile of shame”*): jocurile deținute care așteaptă să fie jucate. Valoarea lor
de două ori: la **prețul de listă** (*list price*, prețul fără nicio reducere) și **azi**, cu reducerile
zilei: **valoarea de înlocuire** (*replacement value*) a raportului 6. Niciuna nu e ce s-a plătit.

## 5. Sesiunile

**Întrebarea.** Cât durează și când au loc ședințele cu un joc?

```sql
-- session_summary
WITH sessions AS (
    SELECT s.game_id, s.started_at, s.minutes, s.started_local, s.local_hour, s.origin
    FROM session s JOIN game g ON g.id = s.game_id
    WHERE COALESCE(g.is_tool, 0) = 0),
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
FROM ordered
```

```sql
-- session_origins
SELECT s.origin, COUNT(*) AS sessions, SUM(s.minutes) AS minutes, MIN(s.started_local) AS first
FROM session s JOIN game g ON g.id = s.game_id
WHERE COALESCE(g.is_tool, 0) = 0
GROUP BY s.origin
ORDER BY s.origin
```

```sql
-- session_lengths
WITH sessions AS (
    SELECT s.game_id, s.started_at, s.minutes, s.started_local, s.local_hour, s.origin
    FROM session s JOIN game g ON g.id = s.game_id
    WHERE COALESCE(g.is_tool, 0) = 0)
SELECT CASE WHEN minutes < :quarter_hour THEN 1
            WHEN minutes < :half_hour    THEN 2
            WHEN minutes < :hour         THEN 3
            WHEN minutes < :two_hours    THEN 4
            ELSE 5 END                   AS bucket,
       COUNT(*)                          AS sessions,
       SUM(minutes)                      AS minutes
FROM sessions
GROUP BY bucket
ORDER BY bucket
```

```sql
-- session_hours
WITH sessions AS (
    SELECT s.game_id, s.started_at, s.minutes, s.started_local, s.local_hour, s.origin
    FROM session s JOIN game g ON g.id = s.game_id
    WHERE COALESCE(g.is_tool, 0) = 0)
SELECT local_hour AS hour, COUNT(*) AS sessions, SUM(minutes) AS minutes
FROM sessions
GROUP BY local_hour
ORDER BY local_hour
```

```sql
-- session_weekdays
WITH sessions AS (
    SELECT s.game_id, s.started_at, s.minutes, s.started_local, s.local_hour, s.origin
    FROM session s JOIN game g ON g.id = s.game_id
    WHERE COALESCE(g.is_tool, 0) = 0)
SELECT CAST(strftime('%w', substr(started_local, 1, 10)) AS INTEGER) AS weekday,  -- 0 Sunday
       COUNT(*)     AS sessions,
       SUM(minutes) AS minutes
FROM sessions
GROUP BY weekday
ORDER BY weekday
```

Mediana este media celor unul sau două rânduri din mijloc (`ROW_NUMBER`). Percentila 90 e cea după
rang (*nearest rank*): valoarea de pe rangul $\lceil 0{,}9\,n \rceil$, scris în numere întregi
`(9n + 9) / 10`.

**Răspunsul (14 octombrie 2026).**

- **Câte și cât durează:** 116 sesiuni din 14 august 2026. Mediana e 16 minute, media 46, iar
  percentila 90 e 118 minute.
- **Lungimile:** 47% dintre sesiuni sunt sub 15 minute, 7,8% între 15 și 30, 15% între 30 și 60, 21%
  între o oră și două și 9,5% peste două ore.
- **Noaptea:** 51% din minute au început între miezul nopții și ora 6.
- **Zilele:** marțea are cele mai multe minute (1.354), apoi lunea (1.052). Duminica are cele mai
  puține (394).
- **Cum au fost măsurate (18 octombrie, ziua în care a început observarea):** toate cele 122 de sesiuni
  de atunci au fost pornite de aici și cronometrate la secundă; niciuna observată încă.

**Ce nu poate vedea.** Fiecare joc care are sesiuni: cele pornite de launcher, cronometrate la secundă,
și — din faza 93 — cele pe care le vede rulând cât rulează și el, oricum ar fi fost pornite, un joc
Steam inclus, cu fiecare capăt nesigur cu o privire (câteva secunde). Contoarele Steam au totaluri,
nu sesiuni, iar ce s-a jucat cât launcher-ul nu rula nu e aici. O sesiune sub un minut nu se
păstrează. Fiecare se numără la ora la care a început, fără să fie împărțită pe ore.

**Ideea.** **Mediana și media** (*median versus mean*): într-o distribuție asimetrică (*skewed*),
mediana e sesiunea obișnuită, iar media e trasă în sus de cele lungi (aici 16 față de 46).
**Percentila 90** (*90th percentile*): nouă sesiuni din zece sunt mai scurte. **Ora de pe ceas și
momentul**: secțiunea de la început. **Instrumentare față de observare** (*instrumentation versus
observation*): o sesiune pornită de aici e măsurată de programul care a pornit jocul; una observată,
de cineva care doar se uită — cu o rezoluție de o privire; `session_origins` le numără separat.

## 6. Banii

**Întrebarea.** Cât valorează biblioteca și cât costă o oră de joc?

```sql
-- money_library
WITH installed AS (
    SELECT v.*
    FROM v_library v
    WHERE v.installed = 1
      AND COALESCE(v.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(v.is_tool,
                   CASE WHEN v.app_type IS NOT NULL AND v.app_type != 'game'
                         AND v.appid_source = 'manifest' THEN 1 ELSE 0 END) = 0),
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
LEFT JOIN v_price_latest p ON p.appid = t.steam_appid
```

```sql
-- money_paid
SELECT v.name, pu.purchases, pu.paid_cents, pu.currency, pu.currencies,
       h.minutes,
       CASE WHEN pu.currencies = 1 AND h.minutes > 0
            THEN pu.paid_cents * 60.0 / h.minutes END                 AS cents_per_hour
FROM (SELECT game_id, COUNT(*) AS purchases, SUM(paid_cents) AS paid_cents,
             MIN(currency) AS currency, COUNT(DISTINCT currency) AS currencies
      FROM purchase GROUP BY game_id) pu
JOIN v_library v ON v.id = pu.game_id
LEFT JOIN v_hours h ON h.appid = v.steam_appid
                    OR (v.steam_appid IS NULL AND h.game_id = v.id)
ORDER BY v.name COLLATE NOCASE
```

```sql
-- money_proxy
WITH games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0)
SELECT g.name, g.minutes, p.initial_cents, p.currency,
       p.initial_cents * 60.0 / g.minutes      AS cents_per_hour
FROM games g
JOIN v_price_latest p ON p.appid = g.appid AND p.kind = 'priced'
WHERE g.minutes >= :proxy_min_minutes
  AND NOT EXISTS (SELECT 1 FROM purchase pu JOIN game x ON x.id = pu.game_id
                  WHERE x.steam_appid = g.appid)
ORDER BY cents_per_hour, g.name
```

```sql
-- money_sales
SELECT s.name, p.discount_percent, p.initial_cents, p.final_cents, p.currency,
       EXISTS (SELECT 1 FROM game g JOIN install i ON i.game_id = g.id
               WHERE g.steam_appid = p.appid)                         AS installed
FROM v_price_latest p
JOIN steam_app s ON s.appid = p.appid
WHERE p.kind = 'priced' AND p.discount_percent > 0
ORDER BY p.discount_percent DESC, s.name
```

```sql
-- money_lowest
WITH installed AS (
    SELECT v.*
    FROM v_library v
    WHERE v.installed = 1
      AND COALESCE(v.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(v.is_tool,
                   CASE WHEN v.app_type IS NOT NULL AND v.app_type != 'game'
                         AND v.appid_source = 'manifest' THEN 1 ELSE 0 END) = 0),
titles AS (SELECT steam_appid, MIN(name) AS name FROM installed
           WHERE steam_appid IS NOT NULL GROUP BY steam_appid)
SELECT t.name, p.final_cents AS now_cents, p.currency,
       r.lowest_cents, r.lowest_on, r.observations
FROM titles t
JOIN v_price_latest p ON p.appid = t.steam_appid AND p.kind = 'priced'
JOIN v_price_range  r ON r.appid = t.steam_appid
ORDER BY (p.final_cents - r.lowest_cents) DESC, t.name
```

Din faza 98 `money_lowest` pornește din lista jocurilor instalate fără orele lor (`installed` fără `v_hours`, ca `money_library` din faza 91): nu are nevoie de ele, iar citirea lor costa 1,3 ms din 2,9. Aceleași 18 rânduri.

```sql
-- money_wishlist
SELECT COUNT(*)                                                       AS items,
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
WHERE lists > 0
```

```sql
-- money_series
SELECT COUNT(*)                 AS observations,
       COUNT(DISTINCT appid)    AS apps,
       MIN(observed_at)         AS first,
       MAX(observed_at)         AS last
FROM price_snapshot
```

`money_library` folosește aceeași regulă a grilei ca `installed`, dar fără orele din `v_hours`
(`INSTALLED_TITLES`): nu are nevoie de ele, iar citirea lor degeaba îi lua 3 ms din 3,4 (faza 91).

**Răspunsul (16 octombrie 2026).**

- **Prețul de listă și costul de azi:** cele 28 de jocuri instalate **au un preț de listă de 723,75 € și
  ar costa azi 720,25 €**: unul din cele 18 titluri cu preț e redus (Cinderia, −20%). Dintre cele 22 de
  titluri Steam, 18 au preț, 3 sunt gratuite și unul nu se mai vinde; 5 jocuri nu au aplicație Steam.
  Pe 14 octombrie propoziția spunea „750,25 € la prețul de listă”, dar aduna prețurile de azi, cu
  reduceri; acum cele două sume sunt separate și numite.
- **Ce așteaptă:** cele 3 jocuri nejucate niciodată valorează 89,24 € la prețul de listă și tot atât azi.
- **Ce am plătit:** 127,98 € pentru 4 jocuri. Crimson Desert Enhanced (70,00 €, 15 h 34 min) a costat
  4,50 € pe oră, Slow Roads (5,00 €, 2 h 49 min) 1,77 €, WARDOGS (39,99 €, 36 h 49 min) 1,09 €;
  Gears of War: E-Day (12,99 €) nu are încă nicio oră.
- **Prețul de listă pe oră** (un înlocuitor, acolo unde nu am trecut ce am plătit), pe 110 jocuri
  jucate cel puțin o oră: cel mai ieftin e Squad 44 (0,05 € pe oră), apoi Hearts of Iron IV (0,06 €).
  Din faza 91 se împarte chiar **prețul de listă**, cum spune numele; înainte se împărțea prețul de azi,
  așa că o reducere făcea ora să pară mai ieftină.
- **La reducere azi:** 29 de aplicații; cea mai mare reducere e de 95% (Slash It).
- **Mai ieftine decât azi:** 3 din cele 18 titluri instalate cu preț au fost văzute mai ieftin, toate
  pe 14 septembrie (Silent Hill 2: 27,99 € față de 69,99 € azi).
- **Seria de prețuri:** 386 de prețuri pentru 321 de aplicații, între 12 august și 16 octombrie 2026.
- **Lista de dorințe:** 23 de jocuri pe singura listă publică a conturilor mele; 14 au preț
  (296,62 € la prețul de listă, 251,39 € la prețurile de azi: 3 sunt reduse), 3 nu se vând, iar 6 nu au
  încă preț. Celelalte trei conturi nu au dat nimic de citit (secțiunea despre lista de dorințe, mai jos).
- **Țintele (din faza 101).** Când am pus cel puțin o țintă de preț pe un joc dorit, raportul adaugă o
  propoziție: „You watch N wished games with a target; M are below it today.” Fără nicio țintă, nu spune
  nimic despre ele. Interogarea `money_wishlist` le citește din aceeași trecere prin `v_wishlist_now`
  (o legătură la stânga cu `price_target`), deci nu costă încă o citire a vederii; o țintă se compară doar
  cu un preț în moneda ei.

**Ce nu poate vedea.**

- Seria de prețuri e tânără, așa că un „cel mai mic văzut” se sprijină pe foarte puține prețuri.
- Prețurile sunt cele ale magazinului Steam pentru România și nu se convertesc niciodată între monede.
- Costul pe oră împarte la orele din ambele surse. Pagina jocului numără doar orele launcher-ului,
  așa că cele două cifre pot diferi; fiecare spune ce numără.
- Jocurile gratuite și cele fără aplicație Steam nu au preț de listă.
- Prețurile listei de dorințe se cer zilnic abia de la prima citire a listei (15 octombrie), așa că o
  reducere de dinainte nu e în serie, iar „cel mai mic văzut” al unui joc dorit spune doar ce s-a
  văzut de atunci.

**Ideea.** **Valoarea de înlocuire** (*replacement value*): cât ar costa biblioteca, cumpărată din
nou azi, la prețurile de azi, cu reduceri cu tot. **Prețul de listă** (*list price*): prețul fără nicio
reducere. **Diferența dintre ele** e cât iau reducerile zilei din valoarea bibliotecii. **Costul pe oră**
(*cost per hour*): prețul împărțit la orele jucate. **Măsura-înlocuitor** (*proxy measure*): o cifră
folosită în locul celei care lipsește și numită așa, aici prețul de listă pe oră. **Seria de timp**
(*time series*): același preț, observat din nou și din nou.

## 7. Calitatea datelor

**Întrebarea.** Ce nu pot vedea cifrele acestea și cât de sigure sunt?

```sql
-- quality_types
SELECT CASE WHEN appid IS NULL AND marked_tool = 1 THEN 'tool (no Steam app)'
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
ORDER BY minutes DESC
```

```sql
-- quality_set_aside
SELECT appid, minutes_steam AS minutes, steam_last_played
FROM v_hours
WHERE appid IN (SELECT value FROM json_each(:set_aside))
ORDER BY appid
```

```sql
-- quality_sources
SELECT source, COUNT(*) AS apps, SUM(minutes) AS minutes,
       SUM(minutes_launcher) AS minutes_launcher, SUM(minutes_steam) AS minutes_steam
FROM v_hours
WHERE minutes > 0
  AND COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
GROUP BY source
ORDER BY minutes DESC
```

```sql
-- quality_links
SELECT h.name, h.games, h.minutes_launcher, h.minutes_steam,
       group_concat(DISTINCT g.appid_source) AS linked_by
FROM v_hours h
JOIN game g ON g.steam_appid = h.appid
WHERE h.source = 'both'
GROUP BY h.appid
ORDER BY h.minutes DESC
```

```sql
-- quality_untimed
WITH installed AS (
    SELECT v.*, h.minutes, h.minutes_steam, h.steam_last_played
    FROM v_library v
    LEFT JOIN v_hours h ON h.appid = v.steam_appid
                        OR (v.steam_appid IS NULL AND h.game_id = v.id)
    WHERE v.installed = 1
      AND COALESCE(v.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(v.is_tool,
                   CASE WHEN v.app_type IS NOT NULL AND v.app_type != 'game'
                         AND v.appid_source = 'manifest' THEN 1 ELSE 0 END) = 0)
SELECT name, source,
       CASE WHEN source = 'steam' THEN 'no account marked mine holds it'
            ELSE 'timed only while the launcher watches' END AS why
FROM installed
WHERE (launch_kind != 'exe' AND source != 'steam')
   OR (source = 'steam' AND minutes_steam IS NULL AND steam_last_played IS NULL)
ORDER BY source, name COLLATE NOCASE
```

```sql
-- quality_currencies
SELECT currency, COUNT(*) AS observations
FROM price_snapshot
WHERE kind = 'priced'
GROUP BY currency
ORDER BY observations DESC
```

```sql
-- stats_lifetime
SELECT SUM(COALESCE(playtime_seconds, 0)) AS seconds,
       (SELECT SUM(COALESCE(playtime_seconds, 0)) FROM game) AS seconds_ever
FROM v_library WHERE installed = 1
```

**Răspunsul (14 octombrie 2026).** Din 10.839 ore:

- **Lăsate deoparte:** 616. Source SDK Base 2007 are 314, Spacewar 301.
- **Ce sunt restul:** 9.996 ore (92%) sunt pe jocuri și 134 pe 71 de aplicații fără fișă în magazin.
  Mai rămân 67 pe moduri, 15 pe jocuri fără aplicație Steam și 10 pe demo-uri.
- **Cine le-a cronometrat:** Steam 10.098 ore, launcher-ul 89. Patru jocuri au timp din ambele surse:
  - Silent Hill 2, legat **după nume** (potrivire de cel puțin 0,85);
  - American Truck Simulator, Chained Together și Cyberpunk 2077, legate printr-o legătură păstrată
    dintr-o înregistrare veche.
- **Timpul launcher-ului:** 90 de ore pe toate jocurile cunoscute vreodată și 38 pe cele instalate
  acum. 38 este cifra „lifetime” din pagina Stats.
- **Fără nicio sursă de timp:** 3 jocuri instalate, toate Xbox. Din faza 93 lista se cheamă „cronometrate
  doar privind, sau deloc”: un joc Xbox sau Epic are timp cât timp launcher-ul îl vede rulând.
- **Monede:** toate prețurile sunt în euro.

**Testul fazei 83 folosește pagina Stats ca oracol** (*test oracle*). Timpul de o viață, cele mai
jucate jocuri, minutele pe luni și numărul jocurilor pe surse sunt calculate o dată în Python
(`logic/stats.py`) și o dată în SQL (`stats_lifetime`, `stats_top`, `stats_months`, `stats_sources`
din `data_access/reports.py`). Pe biblioteca mea, cele două dau aceleași cifre.

**Ce nu poate vedea.** Raportul acesta e chiar limitele, ca cifre:

- ce e lăsat deoparte;
- de unde vine fiecare oră;
- care legături dintre un joc din folder și o aplicație Steam sunt presupuneri;
- ce jocuri sunt cronometrate doar privind (cât timp rulează launcher-ul) sau nu au ore din nicio sursă.

**Ideea.** **Calitatea datelor** (*data quality*) are trei fețe:

- **completitudinea** (*completeness*): ce lipsește;
- **proveniența** (*provenance*): ce sursă a spus fiecare lucru;
- **rezolvarea entităților** (*entity resolution*): hotărârea că un joc din folder și o aplicație Steam
  sunt același joc, aici după o potrivire de nume de cel puțin 0,85.

Arătate ca rezultat, nu ascunse, ele spun cât de mult se poate sprijini restul pe cifrele de mai sus.

## Lista de dorințe: preferința declarată lângă cea dezvăluită

Din faza 86 baza ține **două feluri de preferință**. Orele sunt **preferința dezvăluită** (*revealed
preference*): ce am ales de fapt să joc, măsurat. Lista de dorințe Steam este **preferința declarată**
(*stated preference*): ce am spus că vreau. Alături stă seria de prețuri. Pagina Wishlist (faza 87) le
pune împreună: jocurile dorite, întâi cele reduse, după cât de mare e reducerea, apoi după cât de bine
se potrivesc cu ce joc, cu un semn acolo unde prețul de azi e cel mai mic văzut. **Nu se prezice
nimic**: fiecare rând e un fapt cu sursa lui, iar singura ordonare e spusă în cuvinte pe rând.

**Ce se citește.** Pentru fiecare cont marcat „Mine”, o dată pe zi, lista publică a contului, de la
serviciul de liste de dorințe al Steam (adresa a opta din `CLAUDE.md`, fără cheie, numai citire).
Tabelele `wishlist_read` și `wishlist` și vederea `v_wishlist_now` sunt în `docs/BAZA_DE_DATE.md`
(secțiunile 4 și 5, versiunea 6). Pe 15 octombrie: un cont cu o listă publică de 16 jocuri și trei
care au răspuns „nimic” — iar unul dintre cele trei arată „Wishlist 6” în magazin. **O listă privată
răspunde ca una goală**, așa că „nimic de citit” nu scoate niciodată un joc de pe listă.

```sql
-- wishlist_now
SELECT *
FROM v_wishlist_now
ORDER BY removed_at IS NOT NULL, appid
```

**Potrivirea** (*fit*) se calculează în Python (`logic/wishlist.py`), din două interogări: jocurile mele
cu ore, câte un rând pentru fiecare gen (aceleași jocuri și aceleași genuri ca la raportul 3, fără
Free To Play și fără descriptorii de conținut), și genurile fiecărui joc dorit.

```sql
-- wishlist_profile
WITH games AS (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0)
SELECT g.appid, g.minutes, sg.genre_id
FROM games g
JOIN steam_app_genre sg ON sg.appid = g.appid
WHERE g.minutes > 0
  AND sg.genre_id NOT IN (SELECT value FROM json_each(:not_genres))
ORDER BY g.appid, sg.genre_id
```

```sql
-- wishlist_genres
SELECT w.appid, genre.id AS genre_id, genre.name
FROM v_wishlist_now w
JOIN steam_app_genre sg ON sg.appid = w.appid
JOIN genre              ON genre.id = sg.genre_id
WHERE genre.id NOT IN (SELECT value FROM json_each(:not_genres))
ORDER BY w.appid, genre.name
```

**De la faza 89, fiecare gen are o greutate după cât de rar este.** Prima formă (faza 86) era o
reuniune: partea din orele mele care a mers la jocuri cu cel puțin un gen al jocului dorit. Cum Action
are 87% din orele mele cu un gen, orice joc cu Action ieșea între 87% și 99%; 9 din cele 16 jocuri
dorite stăteau acolo, iar cifra nu le mai deosebea. Acum un gen pe care îl au aproape toate jocurile
spune puțin despre un joc, iar unul rar spune mult. Greutatea vine din toate aplicațiile Steam despre
care baza are o înregistrare (306 pe 15 octombrie), nu doar din ale mele:

```sql
-- wishlist_idf
SELECT sg.genre_id,
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
ORDER BY apps DESC, sg.genre_id
```

    greutate(gen) = ln(aplicații cu vreun gen / aplicații cu genul acesta)

Action, pe 227 de aplicații din 306, cântărește ln(306/227) = 0,30; Adventure 0,80; Indie 0,84;
Simulation 1,55; Strategy, pe 41, cântărește 2,01. Un gen pe care îl au toate ar cântări 0.

Un joc este atunci un **vector**: câte o componentă pentru fiecare gen al lui, egală cu greutatea
genului, totul împărțit la lungimea vectorului, ca lungimea să fie 1. Orele mele sunt și ele un
vector: vectorul fiecărui joc jucat, înmulțit cu minutele lui, adunate, apoi aduse la lungimea 1.
Potrivirea este **cosinusul** dintre cele două, adică produsul lor scalar:

    potrivire = Σ pe genuri  joc(gen) × ore(gen)        (amândoi vectorii de lungime 1)

1 înseamnă același amestec de genuri ca orele mele; 0, niciun gen în comun. Rândul o spune în
cuvinte și numește cele (cel mult) două genuri care adaugă cel mai mult: „33% like what you play ·
Strategy, Action”.

**Răspunsul (15 octombrie 2026, pe o copie).** Toate cele 16 jocuri dorite au acum înregistrare și
genuri.

| Jocul dorit | Reuniunea (faza 86) | Cosinusul (faza 89) |
|---|---|---|
| Deadlock | 87% | 94% · Action |
| Ready or Not | 90% | 41% · Action, Adventure |
| Police Shootout | 99% | 36% · Action, Simulation |
| Beyond The Wire | 99% | 35% · Strategy, Action |
| Day of Infamy | 99% | 33% · Strategy, Action |
| Wolf Ridge | 99% | 33% · Strategy, Action |
| Another Try 2 | 90% | 31% · Action, Massively Multiplayer |
| God of War | 89% | 28% · Action, Adventure |
| Order of Wallachia | 89% | 28% · Action, Adventure |
| Pacific Drive | 99% | 21% · Action, Simulation |
| Autumn | 28% | 19% · Strategy, Casual |
| Kona | 30% | 18% · Adventure, Indie |
| Paradise Lost | 30% | 18% · Adventure, Indie |
| The Lightkeeper | 30% | 18% · Adventure, Indie |
| Little Nightmares II | 20% | 17% · Adventure |
| Mount Your Friends | 27% | 10% · Simulation, Sports |

Cifrele s-au răspândit de la 20-99% la 10-94%, iar ordinea s-a schimbat acolo unde reuniunea nu
deosebea nimic: Pacific Drive (Action, dar și Racing, Indie, Adventure, Simulation) a coborât de la
99% la 21%, pentru că genurile lui rare sunt cele pe care le joc puțin.

**Ce nu poate vedea.**

- Un joc cu un singur gen este acel gen, oricât de comun: vectorul lui are o singură componentă, de
  lungime 1. Deadlock (numai Action) iese la 94% pentru că orele mele sunt aproape numai Action, nu
  pentru că Action ar spune mult. Greutatea contează doar între genurile aceluiași joc.
- Genurile sunt ale magazinului, câte o etichetă largă; „Strategy” acoperă jocuri foarte diferite.
- Greutățile vin din aplicațiile pe care le știe baza mea (ce am, ce am jucat, ce doresc), nu din tot
  magazinul; o bibliotecă de alt fel ar da alte greutăți.
- O listă privată nu se poate citi și nu se poate deosebi de una goală; launcher-ul nu poate schimba
  o setare a profilului Steam.
- Un joc fără înregistrare nu are nici preț, nici genuri: rândul lui spune „not fetched yet”.

**Linia prețurilor (faza 89).** De la al treilea preț văzut, rândul unui joc dorit desenează lângă preț
o linie mică a seriei: cel mai vechi preț în stânga, cel de azi ca un punct în dreapta, mai jos
însemnând mai ieftin. O linie dreaptă înseamnă că prețul nu s-a mișcat. Se iau numai prețurile în
moneda de azi a jocului; „Free” și „Not sold” nu au linie.

```sql
-- wishlist_series
SELECT p.appid, p.observed_at, p.final_cents, p.currency
FROM price_snapshot p
WHERE p.kind = 'priced'
  AND p.appid IN (SELECT appid FROM v_wishlist_now)
ORDER BY p.appid, p.observed_at
```

**Alertele de preț (faza 101).** Seria de prețuri devine un instrument de decizie: pentru un joc dorit
pot pune o **țintă** (din meniul rândului, „Alert me under...”), iar lansatorul îmi spune **o singură dată
pentru fiecare scădere** când prețul ajunge la ea sau sub ea. Fără nicio țintă, mă anunță și când un joc
ajunge **la cel mai mic preț văzut vreodată** — dar numai dacă seria are cel puțin trei prețuri în aceeași
monedă (`rules.ALERT_MIN_OBSERVATIONS`). „Cel mai mic văzut” este un **punct de referință**: ancorează
ideea de preț bun, dar numai după ce există ceva față de care să fie mai mic. Pe o serie de unul sau două
prețuri, „cel mai mic” nu spune nimic, iar o alertă ar fi doar zgomot. Se judecă doar prețurile abia
sosite, deci o țintă pusă azi nu declanșează nimic singură. Același preț văzut și mâine nu e o alertă
nouă; o nouă scădere este. Fiecare alertă se scrie întâi în jurnalul `price_alert` (doar adăugat), apoi
apare mesajul: în fereastră, sau lângă ceas când launcher-ul stă acolo. Pe 20 octombrie niciun preț al
celor 23 de jocuri dorite nu se mișcase de la începutul seriei, deci regula n-ar fi alertat niciodată până
atunci. Pagina Wishlist are lista alertelor din ultimele 30 de zile (`rules.ALERT_KEEP_DAYS`), una pentru
fiecare scădere.

```sql
-- price_targets
SELECT appid, cents, currency, set_at
FROM price_target
```

```sql
-- price_alerts
SELECT a.appid, s.name, a.observed_at, a.kind, a.final_cents, a.currency, a.sent_at
FROM price_alert a
JOIN steam_app s ON s.appid = a.appid
ORDER BY a.sent_at DESC, a.appid
```

**Ideea.** **Preferința declarată și preferința dezvăluită** (*stated and revealed preference*): ce
spune cineva că vrea, față de ce alege. **Filtrarea după conținut** (*content-based filtering*): un
lucru e recomandat după cât seamănă însușirile lui (aici genurile) cu ale celor deja alese — folosită
aici doar ca să ordoneze o listă pe care am ales-o eu, niciodată ca să ghicească ce mi-ar plăcea.
**TF-IDF** (*term frequency–inverse document frequency*): o însușire cântărește mai mult cu cât e mai
rară; „frecvența inversă în documente” este aici ln(aplicații / aplicații cu genul). **Similaritatea
cosinus** (*cosine similarity*): cât de mult arată doi vectori în aceeași direcție, de la 0 la 1,
oricât de lungi ar fi. **Linia mică** (*sparkline*): o serie de timp desenată cât un cuvânt, fără axe,
lângă cifra pe care o explică.
**Monitorizarea prețurilor** (*price monitoring*): același preț întrebat zilnic, ca o reducere să fie
văzută cât ține. **Punctul de referință** și **ancorarea** (*reference point*, *anchoring*): o valoare
văzută înainte — aici cel mai mic preț — după care judecăm dacă un preț e bun. **Alerta de prag**
(*threshold alert*): un mesaj care pleacă atunci când o valoare trece de un prag ales. **Notificarea
idempotentă** (*idempotent notification*): aceeași cauză, oricât de des ar fi văzută, dă un singur mesaj. **O santinelă pentru „încă nu”** (*sentinel value*): `has_record = 0` și „not fetched
yet” spun că un lucru nu se știe încă, nu că e zero sau gol.

## 8. Declarat și dezvăluit

**Întrebarea.** Ce spun că vreau, față de ce joc?

Raportul 3 împarte orele pe genuri; secțiunea de mai sus pune lista de dorințe lângă ele, joc cu joc.
Raportul acesta le pune una lângă alta pe genuri: ce parte din jocurile dorite are fiecare gen, ce
parte din jocurile pe care le-am jucat și ce parte din orele mele.

```sql
-- stated_revealed
WITH games AS MATERIALIZED (
    SELECT * FROM v_hours
    WHERE COALESCE(appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(marked_tool,
                   CASE WHEN app_type IS NULL OR app_type = 'game' THEN 0 ELSE 1 END) = 0),
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
ORDER BY genre.name
```

Jocurile și orele sunt cele de la raportul 3 (aceleași excluderi, același „joc”); lista de dorințe
este cea de azi a conturilor marcate „Mine”, citită direct din tabelul `wishlist`, fără prețuri.

    pe listă(gen)  = jocuri dorite cu genul / jocuri dorite cu vreun gen
    în jocuri(gen) = jocuri jucate cu genul / jocuri jucate cu vreun gen
    în ore(gen)    = minutele jocurilor cu genul / minutele jocurilor cu vreun gen
    diferența      = pe listă − în ore, în puncte procentuale

**Răspunsul (16 octombrie 2026, pe o copie).** Indie este pe 71% din jocurile mele dorite, în 41% din
jocurile pe care le-am jucat și în 17% din orele mele. Action invers: în 87% din ore și în 76% din
jocurile jucate, pe 65% din dorințe.

| Genul | Pe listă | În jocurile jucate | În ore | Diferența (listă − ore) |
|---|---|---|---|---|
| Action | 65% | 76% | 87% | −22 de puncte |
| Adventure | 71% | 42% | 20% | +51 de puncte |
| Indie | 71% | 41% | 17% | +54 de puncte |
| Simulation | 24% | 20% | 15% | +8 puncte |
| Strategy | 24% | 13% | 17% | +6 puncte |
| Casual | 12% | 19% | 5,3% | +6 puncte |
| RPG | 18% | 17% | 6,2% | +11 puncte |
| Massively Multiplayer | 12% | 17% | 10% | +1 punct |
| Racing | 5,9% | 3,7% | 2,7% | +3 puncte |
| Sports | 5,9% | 2,2% | 3,1% | +3 puncte |

17 din cele 23 de jocuri dorite au un gen (6 nu au încă înregistrare); jocurile jucate sunt cele 271
cu un gen și cu cel puțin un minut; orele sunt cele 9.996 de ore ale jocurilor cu un gen. Propoziția
numește cea mai mare diferență pozitivă dintr-un gen cu cel puțin două jocuri dorite
(`rules.REPORT_STATED_MIN_GAMES`), ca un singur joc să nu facă un titlu, și cea mai mare negativă.

Coloana din mijloc schimbă citirea: Indie e în 41% din jocurile jucate, nu în 17%; lista de dorințe
(71%) e tot peste ea, dar distanța e de 30 de puncte, nu de 54. Restul distanței vine din ore.

**Ce nu poate vedea.**

- 17 jocuri dorite cu gen sunt puține: un joc mută o cotă cu 6 puncte.
- Fiecare joc dorit se numără o dată, oricât ar costa; orele sunt pe toată viața, din amândouă sursele,
  iar o dorință poate avea ani (Autumn e pe listă din 2016).
- Un joc are de obicei mai multe genuri, așa că fiecare coloană trece de 100%.
- **Coloana orelor e abruptă** pentru că puține jocuri țin cele mai multe ore (raportul 1): orele spun
  cât rămâi la un joc, numărul de jocuri cât de des încerci unul.
- Se văd doar listele publice; un joc fără înregistrare nu are genuri.
- Mult Indie pe listă și puțin în ore poate fi o preferință care nu se face faptă — sau doar jocuri
  necumpărate încă; datele nu le deosebesc.

**Ideea.** **Preferința declarată și preferința dezvăluită** (*stated and revealed preference*), puse
față în față pe aceeași scară. Distanța dintre ele este **decalajul dintre intenție și comportament**
(*intention–behaviour gap*): ce spunem că vrem nu e mereu ce facem. Aici distanța poate fi și o
dorință neîmplinită încă, un joc necumpărat, nu doar o intenție abandonată. **Marja extensivă și marja
intensivă** (*extensive and intensive margin*): câte jocuri de un fel iei, față de cât timp petreci cu
fiecare. Lista de dorințe numără jocuri, deci comparația ei de la egal la egal sunt jocurile jucate; orele
adaugă marja intensivă și, odată cu ea, **concentrarea** (*concentration*) raportului 1.

## Recapitularea

**Ce este.** Din faza 96, pagina Stats are un card **Recap** și butonul **Share as image...**: o lună sau
un an, desenat ca o singură imagine de 1080 × 1350 de pixeli, pe care o copiez sau o salvez ca s-o trimit
(*shareable artefact*). Cardul nu măsoară nimic nou. Arată, pentru o perioadă, cifrele pe care
rapoartele le au deja: ale raportului 5 (orele din sesiuni, câte sunt, partea zilei și ziua săptămânii),
ale raportului 6 (ce am plătit, cea mai mare scădere de preț a unui joc dorit) și, în subsol, ce spune
raportul 7 despre cum a fost măsurat (câte sesiuni au fost doar văzute, ce nu vede din timpul Steam).

**O singură regulă.** O sesiune contează dacă jocul ei nu e marcat ca unealtă, instalat sau nu: e
CTE-ul `sessions` al raportului 5, folosit acum și de pagina Stats și de card. Până în faza 96, pagina
Stats număra doar jocurile instalate acum, iar septembrie 2026 avea acolo 26h 25m, față de cele 49h 06m
ale sesiunilor (Marvel's Spider-Man 2, dezinstalat de atunci, avea singur 16h 40m). Acum cele trei dau
aceeași cifră pentru aceeași lună (*consistency of figures*), iar un test le ține egale.

**Perioada.** O lună e un interval semi-deschis (*half-open interval*): [1 ale lunii, 00:00; 1 ale lunii
următoare, 00:00), în ora de pe ceas (`started_local`). O sesiune de la 23:59 din ultima zi intră, una
de la 00:00 din ziua următoare nu; o sesiune se numără întreagă în perioada în care a început. Un an e
la fel, de la 1 ianuarie la 1 ianuarie. Un joc instalat de două ori (două înregistrări, ca
S.T.A.L.K.E.R. 2, ale cărui 1130 de minute erau împărțite 889 și 241) e un singur joc pe card, după nume.

**Ce nu arată.** O cifră necunoscută nu se desenează ca zero: nu compară cu o lună înregistrată doar pe
jumătate (august 2026 începe pe 14) și nici o lună care încă nu s-a terminat; o cumpărătură fără zi nu
intră în nicio lună; jocurile găsite la prima scanare nu sunt „noi”; o lună fără sesiuni spune asta.
Timpul jucat în Steam cât launcher-ul nu rula lipsește, iar subsolul o spune.

**Ideea.** Un **artefact de împărtășit** (*shareable artefact*): aceleași cifre ca raportul, într-o
formă pe care un prieten o înțelege în două secunde. **Randare independentă de dispozitiv**
(*device-independent rendering*): imaginea are aceiași pixeli pe televizor, la 225%, ca la birou, la
100%. **Cifre umanizate** (*humanized figures*): „8h 13m” și „after midnight”, nu 493 de minute și ora 1.

## 9. Recomandarea

**Întrebarea.** Din ce e instalat și neînceput, ce seamănă cel mai mult cu ce joc — și spune asta ce joc
mai departe?

**Ce este.** Din faza 98, launcher-ul are un loc al lui, **For you**, sub Library: jocurile care așteaptă,
cele mai asemănătoare cu ce joc, fiecare cu motivul, și **Tonight**, jocurile a căror sesiune obișnuită
încape în timpul pe care îl am. Raportul acesta pune aceleași cifre pe hârtie și se uită înapoi: dacă
ordinea ar fi pus pe primele locuri jocul pe care chiar l-am început.

**Ce așteaptă.** Jocurile care așteaptă sunt **rândurile raportului 4**: interogarea `backlog` de mai sus,
starea ei „never” sau „under” (`BACKLOG_STATE`), apoi cele pe care le văd — nu ascunse, nu marcate
Finished sau Dropped (Playing încă așteaptă). Cele jucate în ultimele 7 zile (de launcher, de magazinul lor
sau de Steam) sunt lăsate deoparte și numite: Jump back in le oferă deja.

**Asemănarea.** Este funcția listei de dorințe (faza 89), mutată în faza 98 în `logic/fit.py`, ca For you și
lista de dorințe să o citească din același loc:

    pondere(gen)  = ln(aplicații cu vreun gen / aplicații cu genul)                 (IDF)
    vector(joc)   = ponderile genurilor lui, de lungime 1
    gust          = Σ minute(joc) × vector(joc), peste jocurile jucate, de lungime 1
    asemănare     = vector(joc) · gust                                              (cosinus)

Genurile vin dintr-o interogare a lor, aceleași pe care le compară lista de dorințe; gustul se face din
rândurile raportului 1 (jocurile jucate, cu minutele lor) și genurile acestea — **exact profilul** pe care
îl citește lista de dorințe din `wishlist_profile`, iar un test le ține egale; ponderile sunt cele din
`wishlist_idf`.

```sql
-- recommend_genres
SELECT sg.appid, genre.id AS genre_id, genre.name
FROM steam_app_genre sg
JOIN genre ON genre.id = sg.genre_id
WHERE genre.id NOT IN (SELECT value FROM json_each(:not_genres))
ORDER BY sg.appid, genre.name
```

**Sesiunea obișnuită.** Mediana sesiunilor unui joc (amândouă originile: pornite din launcher și văzute
rulând), numai de la 3 sesiuni în sus (`rules.SESSION_MEDIAN_MIN`); un joc e numele lui, ca la Recap, iar
rândul care îl poate porni e cel instalat. Tonight oferă jocurile instalate, neascunse, nemarcate Dropped, a
căror mediană încape în timpul ales (30 de minute, o oră, două, o seară), ordonate după partea sesiunilor
care au încăput, apoi după cel jucat ultimul.

```sql
-- session_lengths_by_game
WITH sessions AS (
    SELECT s.game_id, s.started_at, s.minutes, s.started_local, s.local_hour, s.origin
    FROM session s JOIN game g ON g.id = s.game_id
    WHERE COALESCE(g.is_tool, 0) = 0),
installed AS (
    SELECT v.*
    FROM v_library v
    WHERE v.installed = 1
      AND COALESCE(v.steam_appid, 0) NOT IN (SELECT value FROM json_each(:set_aside))
      AND COALESCE(v.is_tool,
                   CASE WHEN v.app_type IS NOT NULL AND v.app_type != 'game'
                         AND v.appid_source = 'manifest' THEN 1 ELSE 0 END) = 0)
SELECT lower(v.name) AS name_key, v.name, v.identity_key, v.id AS game_id, v.steam_appid, s.minutes, s.started_local,
       CASE WHEN v.id IN (SELECT id FROM installed) AND v.hidden = 0
                 AND COALESCE(v.status, '') <> :dropped THEN 1 ELSE 0 END  AS offered
FROM sessions s
JOIN v_library v ON v.id = s.game_id
ORDER BY name_key, s.started_local
```

**Privirea înapoi.** Pentru fiecare joc, prima lui sesiune: în seara dinainte, ce aștepta, ordonat după
asemănarea de atunci — gustul făcut doar din sesiunile launcher-ului de până atunci —, și pe ce loc a ieșit
jocul pe care l-am început. Un joc e aplicația lui Steam acolo unde are una (două foldere ale aceleiași
aplicații sunt un singur joc), altfel înregistrarea lui. Ziua în care a fost văzut prima dată ține locul
zilei în care a sosit (launcher-ul nu păstrează data instalării).

```sql
-- recommend_history
WITH sessions AS (
    SELECT s.game_id, s.started_at, s.minutes, s.started_local, s.local_hour, s.origin
    FROM session s JOIN game g ON g.id = s.game_id
    WHERE COALESCE(g.is_tool, 0) = 0),
first AS (SELECT game_id, MIN(started_local) AS first_played FROM sessions GROUP BY game_id)
SELECT v.id AS game_id, v.name, v.steam_appid, substr(v.first_seen, 1, 19) AS first_seen_local,
       f.first_played,
       CASE WHEN m.minutes > 0 THEN 1 ELSE 0 END AS steam_counted
FROM v_library v
LEFT JOIN first f             ON f.game_id = v.id
LEFT JOIN v_steam_time_mine m ON m.appid = v.steam_appid
WHERE COALESCE(v.is_tool, 0) = 0
ORDER BY v.id
```

    în primele 3   = serile în care jocul ales a ieșit pe locul 1, 2 sau 3 / serile care au putut fi judecate
    locul mediu    = media locurilor jocului ales, în serile acelea

**Răspunsul (18 octombrie 2026, pe o copie).** Din 6 jocuri care așteaptă și pot fi comparate, LEGO
Batman: Legacy of the Dark Knight și PRAGMATA vin primele, 50% asemănătoare cu ce joc; privind înapoi,
jocul început a fost printre primele 3 în 3 din 4 seri care au putut fi judecate, pe locul 3,5 în medie —
prea puține ca să spună dacă asemănarea prezice ceva.

| | Jocul | Asemănarea | Genurile | Jucat |
|---|---|---|---|---|
| 1 | LEGO Batman: Legacy of the Dark Knight | 50% | Action, Adventure | 26 min |
| 2 | PRAGMATA | 50% | Action, Adventure | 30 min |
| 3 | Worship | 37% | Strategy, Action | niciodată |
| 4 | Cinderia | 28% | Action, Adventure | 1 min |
| 5 | SnowRunner | 20% | Simulation, Adventure | 24 min |
| 6 | Star Wars Episode I – Racer | 12% | Action, Racing | niciodată |

BloodBorne nu are genuri cu care să fie comparat (nu e o aplicație Steam); CULTIC, Hytale Launcher și
Max Payne 3 au fost jucate în ultimele 7 zile.

Sesiunea obișnuită a fost judecată pentru 13 jocuri (încă 18 au mai puțin de 3 sesiuni); 7 dintre ele pot
fi oferite în seara asta:

| Jocul | Sesiuni | Mediana | Cea mai scurtă | Cea mai lungă | Poate fi oferit |
|---|---|---|---|---|---|
| CULTIC | 4 | 3 min | 2 min | 17 min | da |
| Slow Roads | 9 | 13 min | 1 min | 1h 05m | da |
| The Blood of Dawnwalker | 6 | 41 min | 5 min | 1h 58m | da |
| The Witcher 3 | 9 | 42 min | 3 min | 1h 26m | da |
| CONTROL Resonant | 3 | 58 min | 36 min | 1h 25m | da |
| RV There Yet OFME | 4 | 2h 09m | 8 min | 2h 27m | da |
| SILENT HILL Townfall | 5 | 2h 15m | 2 min | 4h 59m | da |
| S T A L K E R 2 Heart Of Chornobyl | 26 | 6 min | 1 min | 3h 15m | nu (dezinstalat) |
| Marvel's Spider-Man 2 | 15 | 50 min | 2 min | 7h 51m | nu (dezinstalat) |

(Celelalte patru nu mai sunt instalate: Halloween The Game, American Truck Simulator, 007 First Light,
Theskinstapler.) Mediana spune altceva decât media: la S.T.A.L.K.E.R. 2, 26 de sesiuni cu una de peste trei
ore au mediana de 6 minute — multe porniri scurte, câteva seri lungi.

Privirea înapoi a avut 25 de prime sesiuni. **18 au venit chiar în ziua în care a sosit jocul** — nu a
așteptat nicio seară, deci nu avea cum să fie recomandat; încă 6 au fost lăsate deoparte (5 jocuri pe care
Steam le numără, al căror prim joc poate fi mai vechi decât al launcher-ului, și unul jucat înainte să fie
văzut). Din cele 7 rămase, 4 au putut fi judecate:

| Jocul | Prima sesiune | Locul în seara dinainte | Din | Asemănarea de atunci |
|---|---|---|---|---|
| Marvel's Spider-Man 2 | 15 aug. 2026 | 1 | 10 | 100% |
| The Last Of Us Part I | 15 aug. 2026 | 3 | 10 | 100% |
| Snowrunner | 18 aug. 2026 | 7 | 8 | 23% |
| PRAGMATA | 30 aug. 2026 | 3 | 7 | 58% |

Celelalte trei: Beamng Drive și LEGO Batman (14 august) nu aveau încă nimic jucat înainte cu care să fie
comparate, iar RV There Yet OFME nu are genuri. La pasul 0 al fazei, o numărătoare mai grosieră (fiecare
folder un joc, jocurile Steam lăsate în grămada de atunci) dădea 1 din 4 și locul 6,8; diferența arată cât
de puțin înseamnă patru seri.

**Ce nu poate vedea.**

- Asemănarea vede numai genurile: nu lungimea unui joc, prețul, recenziile, prietenii sau starea de
  spirit. Un joc fără înregistrare Steam nu are genuri: e numit, nu pus pe ultimul loc cu zero.
- Asemănarea nu e o prezicere că jocul îmi va plăcea, iar pagina o spune o dată.
- Ziua în care un joc a fost văzut prima dată ține locul zilei în care a sosit; nu se știe când a fost
  dezinstalat un joc, deci grămada unei seri vechi poate cuprinde jocuri șterse deja.
- Gustul de atunci se face doar din sesiunile launcher-ului (orele Steam nu au date), cu ponderile
  genurilor de azi.
- Patru seri sunt prea puține ca să spună ceva: un singur joc mută rata cu 25 de puncte. Cifra devine
  interesantă după zeci de seri (`rules.REPORT_LOOK_BACK_MIN`, 10, e pragul sub care propoziția o spune).

**Ideea.** **Filtrarea bazată pe conținut** (*content-based filtering*): fiecare joc descris prin
trăsăturile lui — aici genurile, ponderate după cât de rare sunt (*TF-IDF*) —, gustul ca un profil
ponderat de ore și **similaritatea cosinus** (*cosine similarity*) dintre ele. **Filtrarea colaborativă**
(*collaborative filtering*), care recomandă ce au ales oameni asemănători, ar avea nevoie de alegerile
altora; launcher-ul le are pe ale unui singur om. **Pornirea la rece** (*cold-start problem*): un joc fără
trăsături nu poate fi așezat nicăieri. **Mediana** (*median*): mijlocul pe care o singură sesiune foarte
lungă nu îl mută (*robust statistic*). **Evaluarea offline** (*offline evaluation*): ascunzi ce s-a
întâmplat, ordonezi ca în seara dinainte și te uiți unde a ieșit alegerea reală — **rata de nimerire în
primele 3** (*hit rate at 3*) și **locul mediu** (*mean rank*).

## Notele: ce spun, lângă ce joc

Până în faza 102, tot ce știa launcher-ul despre gustul meu era ce fac: orele. Din faza 102 mă și întreabă.
După o sesiune de cel puțin 10 minute (`rules.RATE_MIN_MINUTES`), pornită din launcher sau văzută rulând, un
card mic în colțul ferestrei spune „<joc>, 1h 12m. How was it?”, cu cinci stele și **Skip**; o stea apăsată
scrie un rând în tabela `rating` (jocul, începutul sesiunii, stelele, momentul notei), Skip nu scrie nimic, iar
după 20 de secunde fără răspuns cardul pleacă singur. Un joc e întrebat cel mult o dată pe zi. Cu launcher-ul
lângă ceas, întrebarea vine ca notificare Windows, iar un clic aduce cardul. Pe pagina unui joc, la Recent
sessions, se poate nota și mai târziu, o sesiune din ultimele 14 zile (`rules.RATE_LATE_DAYS`). Întrebarea se
oprește din Settings → After a game.

La pasul 0 al fazei, pe o copie: 128 de sesiuni între 14 august și 19 octombrie, mediana 16 minute, iar a
zecea percentilă 2 minute; 70 de sesiuni (55%) au 10 minute sau mai mult, și doar 3 sunt între 10 și 15 —
pragul cade între pornirile scurte și jocul adevărat. Cu regula „o dată pe zi pe joc”, cele 70 ar fi dat 51 de
întrebări, cam 0,8 pe zi.

Notele sunt **feedback explicit** (*explicit feedback*): ce spun despre un joc. Orele sunt **feedback
implicit** (*implicit feedback*): ce fac cu el. Raportul 10 le pune față în față.

## 10. Spus și jucat

**Întrebarea.** Jocurile pe care le notez bine primesc și orele mele — și asemănarea lui For you îmi ghicește
notele?

**Ce numără.** Pentru fiecare joc notat — aplicația lui Steam acolo unde are una, ca în `v_hours`, altfel
înregistrarea lui —: câte note are, media stelelor și câte note au venit „târziu” (date în altă zi decât
sesiunea lor). O sesiune contează după regula unică (jocul ei nu e marcat unealtă), iar Spacewar și Source SDK
Base 2007 sunt lăsate deoparte, ca peste tot. **Orele sunt rândul jocului din raportul 1**, citit o singură
dată pentru amândouă rapoartele: o a doua citire a `v_hours` ar fi costat rapoartele 1,6 ms din cele 50. Un joc
notat pentru care raportul 1 nu are ore (un joc Steam pe niciun cont marcat „Mine”, un demo) e arătat cu „—”,
niciodată cu 0, și lăsat afară din ce se pune lângă ore. Media unui joc se socotește numai de la 2 note
(`rules.REPORT_RATED_MIN`); jocurile notate o singură dată sunt numărate, nu puse în tabel.

```sql
-- said_played
SELECT g.steam_appid                                                    AS appid,
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
ORDER BY mean_stars DESC, name
```

**Corelația de ranguri.** Orele au o coadă lungă (raportul 1): un joc de sute de ore ar decide singur o
corelație obișnuită. De aceea raportul compară **rangurile**, nu valorile — **corelația Spearman** (*Spearman's
rank correlation*, ρ): fiecare listă e înlocuită cu locurile ei (1 cel mai mic; valorile egale primesc media
locurilor pe care le ocupă), apoi se calculează corelația Pearson a locurilor. Fără egalități, ea are o formă
scurtă:

    ρ = 1 − 6 · Σ d² / (n · (n² − 1)),   d = diferența dintre cele două ranguri ale unui joc

ρ = 1 înseamnă aceeași ordine, −1 ordinea inversă, 0 nicio legătură. Cu mai puțin de 5 jocuri
(`rules.REPORT_SPEARMAN_MIN`) raportul nu o calculează deloc; sub 10 (`rules.REPORT_SPEARMAN_HINT`) o numește
„un indiciu, nu o concluzie”; de la 10 îi spune mărimea în cuvinte (sub 0,2 „aproape nicio legătură”, sub 0,4
„slabă”, sub 0,6 „moderată”, altfel „puternică” — benzile obișnuite, o convenție, nu un test).

**Unde nu se potrivesc.** Raportul numește jocurile notate bine (media 4 sau mai mult) jucate sub două ore, și
pe cele jucate mult (10 ore sau mai mult) notate slab (media 2,5 sau mai puțin) — pragurile sunt în
`rules.py` (`REPORT_RATED_WELL`, `REPORT_BARELY_PLAYED_MINUTES`, `REPORT_RATED_LOW`, `REPORT_PLAYED_MUCH_MINUTES`).

**A doua verificare a recomandării.** Raportul 9 se uita înapoi după ce am jucat. Raportul 10 se uită după
ce am spus: pentru fiecare joc notat, asemănarea lui cu ce joc (aceeași funcție ca For you și lista de
dorințe, `logic/fit.py`, cu genurile din `recommend_genres` și ponderile din `wishlist_idf`) lângă media
stelelor, tot ca o corelație Spearman. **Gustul se face fără jocul însuși** (*leave-one-out*): un joc notat a
fost jucat, iar orele lui ar intra altfel în gustul cu care e comparat — orice joc jucat mult ar ieși
asemănător doar pentru că a fost jucat mult. Un joc fără înregistrare Steam sau fără genuri e numărat deoparte.

**Un exemplu lucrat de mână** (datele plantate ale testului, `tests/phase102_tests.py`). Cinci jocuri notate
de câte două ori și unul, F, o singură dată (3 stele, 1h 40m); genurile: A și E Action, B și F RPG, C Action
și RPG, D Puzzle, toate cu aceeași pondere:

| Jocul | Note | Media | Ore | Rangul stelelor (↑) | Rangul orelor (↑) | d | d² |
|---|---|---|---|---|---|---|---|
| A | 5, 5 | 5,0 | 30 | 5 | 5 | 0 | 0 |
| B | 4, 5 | 4,5 | 1 | 4 | 1 | 3 | 9 |
| C | 3, 3 | 3,0 | 12 | 2 | 2 | 0 | 0 |
| D | 2, 2 | 2,0 | 15 | 1 | 3 | −2 | 4 |
| E | 4, 4 | 4,0 | 20 | 3 | 4 | −1 | 1 |

Σ d² = 14, n = 5: ρ = 1 − 6 · 14 / (5 · 24) = 1 − 0,70 = **0,30** — pe cinci jocuri, un indiciu, nu o
concluzie. B (4,5 stele, o oră) este „notat bine, jucat puțin”, D (2 stele, 15 ore) „jucat mult, notat slab”.
Asemănarea, cu fiecare joc scos din propriul gust (F rămâne în gust, cu orele lui): A 84%, B 17%, C 71%, D
deloc (genul lui nu e în gustul celorlalți), E 90%; rangurile ei față de ale stelelor dau Σ d² = 10, deci
ρ = 1 − 60/120 = **0,50**. Cu propriile ore în gust, A ar fi ieșit 95% — de aceea jocul se scoate. Testul
verifică exact aceste cifre.

**Răspunsul (20 octombrie 2026, pe o copie).** O singură notă, în prima zi a întrebării: sesiunea de
CULTIC începută la 15:59, 5 stele, dată la 17:22 din card. Niciun joc nu are încă două note, deci nu e nimic de
pus lângă ore, iar raportul o spune în cuvinte („1 rating on 1 game, none rated twice yet, which a game's mean
takes.”). Cifrele vin pe măsură ce joc; în iunie le reîmprospătez ca pe celelalte.

**Ce nu poate vedea.**

- **Cine răspunde și când nu e întâmplător** (*response bias*): Skip și lipsa răspunsului nu scriu nimic, așa
  că sesiunile notate sunt cele pe care am avut chef să le notez — poate cele foarte bune sau foarte proaste.
- O singură întrebare pe joc pe zi: o zi cu trei sesiuni ale aceluiași joc dă o singură notă.
- O notă poate veni târziu, de pe pagina jocului, până la 14 zile după sesiune; mai vechi nu se cere. Raportul
  spune câte note au fost târzii.
- Orele sunt de-a lungul vieții jocului (și din Steam), notele încep din faza 102: un joc jucat ani de zile și
  notat de două ori e judecat după două seri.
- Puține jocuri: pe 5 jocuri un singur joc mută ρ cu zeci de sutimi; cifra devine o concluzie abia de la 10.
- **Raritatea notelor** (*rating sparsity*): cele mai multe sesiuni nu vor fi notate niciodată, iar cele mai
  multe jocuri nu vor avea două note. Tabelul jocuri × note e aproape gol.

**Ideea.** **Feedback explicit și implicit** (*explicit and implicit feedback*): ce spun față de ce fac;
sistemele de recomandare învață mai ales din al doilea, pentru că primul e rar. **Corelația de ranguri**
(*rank correlation*, Spearman): ordinea contează, nu mărimea, așa că o coadă lungă nu decide singură.
**Părtinirea răspunsului** (*response bias*): cine răspunde și când nu e un eșantion întâmplător. **Raritatea
notelor** (*rating sparsity*): de ce o recomandare nu poate aștepta stelele. **Interacțiunea dintr-o atingere**
(*one-tap interaction*): întrebarea costă un clic sau nimic — cu cât e mai ușor de răspuns, cu atât mai mulți
răspund, și cu atât mai puțin părtinitor e ce rămâne.

## Semnele, și când au fost puse

Rapoartele 2 și 4 se sprijină pe semnele pe care le pun singur — **Playing**, **Finished**, **Dropped** — și le
pun târziu sau deloc: un joc lăsat în august poate scrie încă Playing. Din faza 101, baza ține și **momentul** în
care a fost pus semnul (`game.status_changed_at`); din faza 103, For you are un rând al lui, **Left behind**, pentru
jocurile marcate Playing de care nu s-a mai auzit nimic de 30 de zile (`rules.LEFT_BEHIND_DAYS`) — nicio sesiune
numărată, niciun semn pus, nicio întrebare răspunsă —, cu trei răspunsuri: **Finished** și **Dropped** pun semnul,
datat, iar **Still playing** scrie doar momentul răspunsului (`game.nudged_at`), ca jocul să fie lăsat în pace încă
30 de zile. Un **ghiont** (*nudge*): întrebarea vine unde o văd, nu mă urmărește cu mesaje.

La pasul 0 al fazei, pe o copie (21 octombrie): 3 jocuri cu semn — 2 Playing (SILENT HILL Townfall, ultima sesiune
pe 22 septembrie; The Witcher 3, pe 11 octombrie) și 1 Dropped (The First Berserker Khazan, nejucat) —, **toate fără
dată**, puse înainte de versiunea 8. Townfall intră în Left behind pe 22 octombrie la 23:44.

**Orele, calculate o singură dată.** Cincisprezece dintre interogări citesc `v_hours`, iar fiecare citire o
calcula din nou din tabelele ei — cam 1,6 ms de fiecare dată, peste 20 din cele 46 ms ale celor zece rapoarte. Din
faza 103, la începutul fiecărei construcții `v_hours` și `v_steam_time_mine` sunt copiate în câte un **tabel
temporar** cu același nume (SQLite caută întâi în schema temporară), pe care toate interogările îl citesc în locul
vederii; la sfârșit tabelele dispar. Textul fiecărei interogări rămâne exact cel citat aici, răspunsurile sunt
aceleași, iar în fișierul bibliotecii nu se scrie nimic: cele zece rapoarte au trecut de la 46 la 24 ms, iar cele
unsprezece iau 24-25 ms.

## 11. Terminarea

**Întrebarea.** Din jocurile pe care le marchez, câte termin — și cât îmi ia?

**Ce numără.** Fiecare joc cu semn (fără unelte, fără Spacewar și Source SDK Base 2007), cu prima și ultima lui
sesiune numărată, momentul semnului și al întrebării, celelalte date de joc și ultima dată Steam pe conturile
marcate „Mine” (regula Left behind le citește). Orele sunt rândul jocului din raportul 1.

```sql
-- finishing
WITH sessions AS (
    SELECT s.game_id, s.started_at, s.minutes, s.started_local, s.local_hour, s.origin
    FROM session s JOIN game g ON g.id = s.game_id
    WHERE COALESCE(g.is_tool, 0) = 0),
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
ORDER BY v.name COLLATE NOCASE
```

**Ce calculează.**

- câte jocuri sunt Finished, Dropped și încă Playing, și câte dintre ele sunt **lăsate în urmă** după regula de mai
  sus;
- **rata de terminare** (*completion rate*): Finished din Finished plus Dropped — un joc încă Playing nu e hotărât,
  deci nu intră; sub 5 jocuri hotărâte (`rules.REPORT_DECIDED_MIN`) raportul o numește „un indiciu, nu o concluzie”;
- **timpul până la Finished** (*time to event*): de la prima sesiune numărată la semnul Finished, numai pentru
  semnele datate — mediana și intervalul;
- **cenzurarea** (*censoring*): un joc încă Playing nu are încă un sfârșit. Dacă l-aș lăsa deoparte, aș păstra doar
  terminările rapide și mediana ar ieși prea mică. De aceea raportul pune lângă mediana simplă estimarea
  **Kaplan–Meier** (*Kaplan–Meier estimator*): fiecare joc încă Playing contează ca „neterminat după N zile”, un joc
  Dropped datat ca „neterminat după zilele până la Dropped”, iar mediana e momentul până la care jumătate ar fi
  terminat;

      S(t) = Π (1 − terminate la t / încă în curs la t),   peste fiecare t la care se termină un joc
      mediana = primul t la care S(t) ≤ 1/2

- **orele la Finished și la Dropped**, ca două mediane: le abandonez devreme sau târziu?

**Un exemplu lucrat de mână** (datele plantate ale testului, `tests/phase103_tests.py`), pe 10 septembrie:

| Jocul | Semnul | Prima sesiune | Semnul pus | Zile | Ore |
|---|---|---|---|---|---|
| A | Finished | 1 aug. | 11 aug. | 10 | 20 |
| B | Finished | 1 aug. | 31 aug. | 30 | 5 |
| C | Finished | 1 iul. | fără dată | — | 8 |
| D | Dropped | 1 aug. | 6 aug. | 5 (cenzurat) | 1 |
| E | Playing, lăsat în urmă (ultima sesiune 5 aug.) | 1 aug. | — | 40 (cenzurat) | 3 |
| F | Playing | 21 aug. | — | 20 (cenzurat) | 2 |

Rata: 3 din 4 jocuri hotărâte, 75% — pe patru, un indiciu. Mediana simplă a celor două terminări datate: (10 +
30) / 2 = **20 de zile**. Kaplan–Meier: la 5, D iese din calcul (cenzurat): 4 rămân; la 10 se termină A: S = 1 −
1/4 = 0,75, rămân 3; la 20 iese F: rămân 2; la 30 se termină B: S = 0,75 × (1 − 1/2) = 0,375 ≤ 0,5 — mediana este
**30 de zile**. Diferența arată exact ce face cenzurarea: lăsând deoparte jocurile încă în curs, aș fi crezut că
termin în 20 de zile. Orele: mediana la Finished 8h (20, 5 și 8), la Dropped 1h. Testul verifică aceste cifre.

**Răspunsul (21 octombrie 2026, pe o copie).** 3 jocuri cu semn: niciunul Finished, 1 Dropped, 2 încă Playing
(niciunul lăsat în urmă încă); 0 din 1 joc hotărât terminat — pe unul, un indiciu; niciun semn Finished nu e datat.
Cifrele vin pe măsură ce răspund la Left behind și pun semne; în iunie le reîmprospătez.

**Ce nu poate vedea.**

- Un semn e al meu și întârzie prin natura lui: îl pun când îmi amintesc — Left behind cere doar semnele restante.
- Semnele de dinainte de versiunea 8 nu au dată: sunt numărate, nu cronometrate; la fel un semn pus înainte de
  prima sesiune numărată a jocului (un joc hotărât înainte ca launcher-ul să-l vadă jucat): un timp negativ n-ar
  spune nimic.
- Baza ține semnul de acum și momentul în care a fost pus ultima oară, nu istoria lui: un joc marcat Playing și
  apoi Finished contează o dată, ca Finished.
- Orele sunt cele de azi (contorul Steam nu are date) — pentru un joc terminat, aproape cele de la terminare.
- Puține jocuri: o singură terminare în plus mută rata cu zeci de puncte.

**Ideea.** **Rata de terminare** (*completion rate*), **timpul până la eveniment** (*time to event*, din analiza
supraviețuirii, *survival analysis*), **cenzurarea** (*censoring*) și estimatorul **Kaplan–Meier**, **mediana**
ca statistică robustă (*robust statistic*): mijlocul pe care un singur joc foarte lung sau foarte scurt nu îl
mută. **Semnul datat** (*dated mark*): o hotărâre cu momentul ei, fără de care timpul până la eveniment nu se poate
măsura. **Ghiontul** (*nudge*): o întrebare pusă la momentul potrivit, unde va fi văzută, care face semnele să
existe.
