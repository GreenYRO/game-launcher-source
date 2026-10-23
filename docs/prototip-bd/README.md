# Prototipul bazei de date (8 octombrie 2026)

Un prototip de unică folosință (în engleză: *spike*, *throwaway prototype*), făcut înainte de faza 54, ca să
răspundă la întrebarea „ce se poate analiza din baza de date” cu cifre reale, nu cu presupuneri. Nu atinge
aplicația: `build.py` citește `data/overrides.json`, `data/catalog.json` și `data/cache/` și construiește un
fișier SQLite cu schema propusă în `claude/brief-faza-54-baza-de-date.md`; `report.py` rulează cele 15 întrebări
ca SQL și scrie `report.md`. Totul este citire pe `data/`; singurul fișier scris este baza de date dată ca argument.

## Cum se rulează (PowerShell, din folderul proiectului)

```powershell
& .venv\Scripts\python.exe docs\prototip-bd\build.py data docs\prototip-bd\library.db
& .venv\Scripts\python.exe docs\prototip-bd\report.py docs\prototip-bd\library.db --out docs\prototip-bd\report.md
```

`build.py` tipărește verificările (același număr de jocuri, sesiuni, minute, secunde de joc, foldere de salvări
ca în JSON; nicio încălcare de cheie străină). Baza se poate deschide cu DB Browser for SQLite ca să se vadă
tabelele. A fost rulat pe 8 octombrie cu Python 3.10 și SQLite 3.37 pe o copie a datelor; pe Windows cu
Python 3.14 din venv ar trebui să meargă identic (nu folosește nimic în afara bibliotecii standard și a
modulului `shared.naming` al proiectului).

## Ce a ieșit (pe datele din 8 octombrie)

- Încărcarea e fără pierderi: 65 de jocuri, 33 instalate, 109 sesiuni (5.304 minute), 272.398 secunde de joc,
  15 foldere de salvări, 47 de înregistrări Steam, 12 genuri, 57 de categorii, 77 de companii, 1 legătură de
  descendență, 0 încălcări de chei străine, toate datele de lansare parsate.
- Cele 15 întrebări (sursă, ore pe gen, ora zilei, ziua săptămânii, mediana sesiunilor, cost pe oră, instalate
  și nepornite, spațiu de recuperat, companii, total față de sesiuni, Metacritic, anul lansării, trăsături,
  acoperire, sămânța recomandării) sunt toate JOIN-uri și GROUP BY-uri peste tabelele propuse. Rezultatele
  în `report.md`.
- Două dintre ele reproduc exact cifrele paginii Stats din Python (oracolul): 3 jocuri instalate și nepornite,
  57,9 GB; 75,6 ore în totaluri față de 88,4 ore în sesiuni (86%).

## Ce a schimbat în schemă (intrat în brief)

1. `category.name` nu poate fi UNIQUE: Steam folosește același nume sub id-uri diferite („Steam Workshop” 30 și
   51, „DualShock Controller Support” 55 și 56, „DualSense Controller Support” 57 și 58). Orice interogare care
   grupează pe numele categoriei numără `COUNT(DISTINCT appid)`; fără asta „DualSense” dădea 113% din jocuri.
2. `install` primește coloana `store_last_played` (LastPlayed din manifestul Steam, azi în `extra`). Fără ea,
   „instalate și nepornite niciodată” lista Counter-Strike 2 și Overwatch, jocuri jucate prin Steam. Pentru
   Xbox și Epic nu există o asemenea dată, deci răspunsul e „necunoscut”, nu „niciodată”.
3. Migrarea trebuie să recupereze ce catalogul a pierdut pentru jocurile dezinstalate: 31 de înregistrări nu au
   niciun nume stocat (`known_as` există doar din faza 36), iar appid-ul unui joc dezinstalat dispare odată cu
   catalogul. Numele vine din `naming.clean_folder_name` pe numele folderului; legătura Steam din
   `cache/steam_search.json`, cu același prag 0,85. Recuperarea a relegat 17 jocuri: orele cu gen cunoscut au
   urcat de la 37 la 63 din 76. Rămân 5 jocuri (12,5 ore) fără legătură: RV There Yet, The Witcher 3 (folderul nou,
   „The Witcher 3” față de „The Witcher 3: Wild Hunt” e sub prag), Gospodar's Tales.
4. Fusul orar, dovedit: toate cele 109 sesiuni ar fi raportate la altă oră prin `strftime`, pentru că SQLite
   convertește „+03:00” la UTC. Ora locală se ia din textul stocat (`substr(started_at, 12, 2)`), sau dintr-o
   coloană `started_local`. Sesiunile de iarnă vor avea „+02:00”, deci greșeala ar fi fost și inegală.

## De verificat mai departe, nu de presupus

- Prețul de listă din înregistrarea Steam pentru S.T.A.L.K.E.R. 2 este 229,99 EUR, ceea ce nu arată a ediție
  standard; prețurile de listă au nevoie de o verificare de bun-simț înainte să intre într-un indicator. Oricum,
  prețul de listă nu e prețul plătit: e un proxy, și pentru o bibliotecă în mare parte din afara magazinelor,
  unul slab. Tabela `purchase` (preț plătit) e faza de după baza de date.
- Numele companiilor nu sunt canonice: „GSC Game World” și „GSC Game World (worldwide)”, „SEGA (Japan)”.
  O regulă de curățare sau o tabelă de sinonime, mai târziu.
- 15 sesiuni cu mediana de 3 minute la S.T.A.L.K.E.R. 2 arată a porniri eșuate sau crash-uri, nu a joc.
  `SESSION_MIN_MINUTES = 1` nu le filtrează; „porniri eșuate pe joc” poate fi un raport în sine.
- Jocurile Steam (8 vizibile) au 0 ore cunoscute aici. `localconfig.vdf` al lui Steam ar putea ține timpul de
  joc per aplicație; de citit de pe disc înainte de orice plan.
- Numele din `report.md` pentru jocurile dezinstalate înainte de faza 36 sunt curățate din numele folderului,
  deci unele arată ca numele de release. Pentru lucrare se folosesc numele Steam (`steam_app.name`) unde există.
