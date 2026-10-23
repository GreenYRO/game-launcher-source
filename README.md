<div align="center">

# Game Launcher

**Every game you own, in one window.**<br>
<sub>Toate jocurile de pe PC într-o singură fereastră: de pe disc și din Steam, GOG, Epic, Ubisoft Connect și Xbox.</sub>

[![Installer](https://img.shields.io/github/v/release/GreenYRO/game-launcher-releases?label=installer&color=7c6cf0)](https://github.com/GreenYRO/game-launcher-releases/releases/latest)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-3b82f6)](LICENSE)
[![Python 3.14](https://img.shields.io/badge/python-3.14-3776ab?logo=python&logoColor=white)](requirements.txt)
[![PySide6](https://img.shields.io/badge/Qt-PySide6-41cd52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![Thesis](https://img.shields.io/badge/UniTBv-licen%C8%9B%C4%83%202026--2027-8b5cf6)](docs/)

<a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/game-launcher-trailer.mp4"><img src="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/trailer.gif" alt="The trailer: the library, For you, Starting..., How was it?, the recap card, the wishlist, TV mode and the five accents" width="820"></a><br>
<sub>▶ <a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/game-launcher-trailer.mp4">The trailer with sound</a> (37 s, 9.4 MB) · trailer-ul cu sunet</sub>

</div>

A Windows game launcher written in Python with PySide6 (Qt), and the source code of the bachelor's thesis
built on it at Transilvania University of Brașov (Faculty of Economic Sciences and Business
Administration, Economic Informatics, 2026-2027). **[Română](#română)** · **[English](#english)**

<table>
<tr>
<td width="50%" valign="top"><a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/library.jpg"><img src="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/library.jpg" alt="The library"></a><br><sub><b>Library</b> · every game from folders, Steam, GOG and Xbox in one grid, the three played last up top</sub></td>
<td width="50%" valign="top"><a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/for-you.jpg"><img src="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/for-you.jpg" alt="For you"></a><br><sub><b>For you</b> · what to play next and why, what fits tonight, what was left behind</sub></td>
</tr>
<tr>
<td width="50%" valign="top"><a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/game-page.jpg"><img src="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/game-page.jpg" alt="A game's page"></a><br><sub><b>A game's page</b> · the art, the facts, Play, a note, the recent sessions and their ratings</sub></td>
<td width="50%" valign="top"><a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/wishlist.jpg"><img src="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/wishlist.jpg" alt="The wishlist"></a><br><sub><b>Wishlist</b> · today's prices, the lowest seen, a line of each game's prices, an alert when one drops</sub></td>
</tr>
<tr>
<td width="50%" valign="top"><a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/stats.jpg"><img src="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/stats.jpg" alt="Stats"></a><br><sub><b>Stats</b> · this week, this month, all time, a year of months, where the games came from</sub></td>
<td width="50%" valign="top"><a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/tv-mode.jpg"><img src="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/tv-mode.jpg" alt="TV mode"></a><br><sub><b>TV mode</b> · the same window from the couch, worked with a controller, its real buttons in the hint bar</sub></td>
</tr>
</table>

<p align="center">
<a href="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/recap.jpg"><img src="https://raw.githubusercontent.com/GreenYRO/game-launcher-releases/main/docs/media/recap.jpg" alt="The recap card" width="340"></a><br>
<sub><b>The recap card</b> · a month in review, painted by the launcher as one image to share</sub>
</p>

## Română

Un launcher de jocuri pentru Windows: toate jocurile unui PC într-o singură fereastră, de pe disc și din
Steam, GOG, Epic, Ubisoft Connect și Xbox. Scris în Python cu PySide6 (Qt). Acest depozit este codul sursă
al lucrării de licență construite pe el, la Universitatea Transilvania din Brașov, Facultatea de Științe
Economice și Administrarea Afacerilor, specializarea Informatică Economică (2026-2027).

### Ce face

- **Găsește jocurile**: în folderele alese de utilizator (jocul e recunoscut după motor, Unity, Unreal sau
  Godot, altfel euristic) și în bibliotecile Steam, GOG, Epic, Ubisoft Connect și Xbox; dublurile dintre
  surse sunt eliminate.
- **Le arată și le pornește**: grila de coperți, pagina fiecărui joc (descriere, capturi, noutăți de la
  Steam, sesiuni, stare, notă), căutare și filtre, coperți de la Steam și, opțional, de la SteamGridDB cu
  cheia utilizatorului; controller și mod TV; tray și pornire cu Windows.
- **Măsoară timpul de joc** la nivel de proces (Job Object), inclusiv pentru jocurile pornite din afara
  launcher-ului; păstrează istoricul sesiunilor; copiază salvările după fiecare sesiune și înainte de
  dezinstalare.
- **Ține o bază de date SQLite** (`data\library.db`): biblioteca, sesiunile, timpul propriu al Steam citit
  din fișierele clientului, seria săptămânală a prețurilor, wishlist-ul Steam cu alerte de preț, notele
  date sesiunilor.
- **Analizează**: unsprezece rapoarte (concentrarea timpului, abandonul, profilurile de joc, backlog-ul,
  sesiunile, banii, calitatea datelor, preferința declarată și cea arătată, recomandarea, nota și timpul,
  finalizarea), pagina „For you”, cardul recapitulativ lunar; un export anonim pentru comparația dintre
  biblioteci.
- **Se instalează la prieteni**: un installer (PyInstaller), notificare când apare o versiune nouă,
  upgrade-ul bazei de date cu un snapshot înainte.

### Cum e construită

Șapte straturi, fiecare în pachetul lui; dependențele merg doar în jos, iar un test verifică regula la
fiecare rulare (`tests\check_layers.py`):

| Pachet | Rol |
|---|---|
| `presentation/` | fereastra și paginile (PySide6); `ui_rules.py` ține toate valorile de aspect |
| `adapters/` | Qt care nu desenează: fire de execuție, controllerul, folderele urmărite |
| `logic/` | regulile launcher-ului, fără Qt: lansare, sesiuni, salvări, rapoarte, recomandări |
| `providers/` | de unde se citesc jocurile instalate (foldere, Steam, GOG, Epic, Ubisoft, Xbox) |
| `web/` | singurul cod care vorbește cu internetul (Steam, SteamGridDB, GitHub) |
| `data_access/` | singurul cod care citește și scrie datele: baza SQLite, schema, upgrade-urile, backup-urile |
| `shared/` | ce folosesc toate straturile: modelele, căile, `rules.py` cu toate constantele |

Documentele lucrării, în română, în `docs/`: `ARHITECTURA.md` (arhitectura și restructurarea),
`BAZA_DE_DATE.md` (baza de date și migrarea), `ANALIZA.md` (rapoartele: întrebarea, SQL-ul, răspunsul),
`DISTRIBUTIE.md` (installer-ul, prima rulare, versiunile), `CITESTE-MA.md` (pagina primită de prieteni).
`ISTORIC.md` este jurnalul construcției, în engleză, fază cu fază; `release-notes/` ține notele fiecărei
versiuni.

### Cum se rulează din sursă

Windows și Python 3.14 (versiunea pe care a fost dezvoltat). În folderul proiectului:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe launcher.py
```

La prima pornire întreabă unde sunt jocurile. Datele (biblioteca, setările, cache-ul, backup-urile) stau în
`data\`, care nu face parte din depozit. `scanner.py --summary` arată ce ar găsi, fără fereastră. Testele:
`.venv\Scripts\python.exe tests\run_all.py` rulează fiecare suită pe o copie temporară a datelor, apoi
plasele de siguranță (importuri, straturi, migrare). Installer-ul se face cu `requirements-build.txt` și
`packaging\build.py`.

Installer-ul gata făcut, pentru prieteni: [GreenYRO/game-launcher-releases](https://github.com/GreenYRO/game-launcher-releases).

### Ce nu e aici, și de ce

Depozitul de dezvoltare rămâne privat: istoria lui ține setările și biblioteca autorului din primele faze.
Ce se vede aici e un instantaneu al unui commit al lui, făcut de `packaging/export_public.py`: `git archive`
al arborelui, fără căile marcate `export-ignore` în `.gitattributes` (fișierele de lucru ale Claude Code,
explicațiile scrise pentru autor, artwork-ul folosit la machete), verificat înainte de publicare să nu
conțină nicio cheie, nicio adresă de e-mail și niciun cont. Nicio dată personală nu e în depozit:
biblioteca, setările și cheia SteamGridDB stau în `data\`, pe PC-ul fiecăruia. Capturile și trailer-ul de
mai sus sunt făcute pe o copie de test a bibliotecii, cu conturile redenumite.

Rețea: launcher-ul vorbește doar cu `store.steampowered.com` și `api.steampowered.com` (înregistrări,
artwork, prețuri, noutăți, wishlist), cu `api.github.com` (dacă a apărut o versiune nouă; doar copiile
instalate întreabă) și, opțional, cu `steamgriddb.com`, cu cheia utilizatorului. Totul e citire, anonim,
cu cache pe disc; lista completă și regulile sunt în `shared/rules.py` și în `docs/DISTRIBUTIE.md`.

### Cum a fost construit

Programul a fost construit cu Claude Code (Anthropic), în faze: fiecare fază a avut un brief, o verificare
pe PC-ul real și teste proprii (peste 3.400 de verificări la ultima rulare completă), iar din octombrie 2026
fiecare fază e și explicată înapoi de autor, în cuvintele lui. Folosirea AI-ului e aprobată de
coordonatorul lucrării, cu condiția ca autorul să poată explica ce face programul. Jurnalul fiecărei faze e
`docs/ISTORIC.md`.

### Licență

MIT, în `LICENSE`. Fonturile Inter (SIL OFL 1.1) și Phosphor Icons (MIT) sunt în `presentation/fonts/`,
cu licențele lor; PySide6 (LGPL v3) și pygame-ce (LGPL) se instalează din `requirements.txt`.

Autor: Nicolae-Andrei Dulama ([GreenYRO](https://github.com/GreenYRO)).

## English

A Windows game launcher: every game on a PC in one window, from folders on disk and from Steam, GOG, Epic,
Ubisoft Connect and Xbox. Written in Python with PySide6 (Qt). This repository is the source code of the
bachelor's thesis built on it (Transilvania University of Brașov, 2026-2027).

### What it does

- **Finds the games**: in the folders the user chooses (a game is recognised by its engine, Unity, Unreal
  or Godot, otherwise heuristically) and in the Steam, GOG, Epic, Ubisoft Connect and Xbox libraries;
  duplicates across sources are dropped.
- **Shows and starts them**: a cover grid, a page per game (description, screenshots, news from Steam,
  sessions, status, a note), search and filters, covers from Steam and, optionally, from SteamGridDB with
  the user's own key; controller and TV mode; the tray and starting with Windows.
- **Measures playtime** at the process level (Job Objects), also for games started outside the launcher;
  keeps the session history; copies saves after every session and before an uninstall.
- **Keeps an SQLite database** (`data\library.db`): the library, the sessions, Steam's own playtime read
  from the client's files, the weekly price series, the Steam wishlist with price alerts, the ratings
  given to sessions.
- **Analyses**: eleven reports (concentration of time, abandonment, play profiles, the backlog, sessions,
  money, data quality, stated and revealed preference, recommendation, rating and time, finishing), the
  "For you" page, the monthly recap card; an anonymous export for the comparison between libraries.
- **Installs on friends' PCs**: an installer (PyInstaller), a notice when a newer version is out, the
  database upgraded with a snapshot first.

### How it is built

Seven layers, each its own package; dependencies point down only, and a test checks the rule on every run
(`tests\check_layers.py`):

| Package | Role |
|---|---|
| `presentation/` | the window and its pages (PySide6); `ui_rules.py` holds every appearance value |
| `adapters/` | Qt that draws nothing: threads, the controller, watched folders |
| `logic/` | the launcher's rules, no Qt: launching, sessions, saves, reports, recommendations |
| `providers/` | where installed games are read from (folders, Steam, GOG, Epic, Ubisoft, Xbox) |
| `web/` | the only code that talks to the internet (Steam, SteamGridDB, GitHub) |
| `data_access/` | the only code that reads and writes data: the SQLite database, its schema, upgrades, backups |
| `shared/` | what every layer uses: the models, the paths, `rules.py` with every constant |

The thesis documents, in Romanian, are in `docs/`: `ARHITECTURA.md` (the architecture and the
restructuring), `BAZA_DE_DATE.md` (the database and the migration), `ANALIZA.md` (the reports: question,
SQL, answer), `DISTRIBUTIE.md` (the installer, the first run, the versions), `CITESTE-MA.md` (the page the
friends get). `ISTORIC.md` is the build log, in English, phase by phase; `release-notes/` holds each
version's notes.

### Running from source

Windows and Python 3.14 (the version it was built on). In the project folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe launcher.py
```

The first start asks where the games are. The data (the library, the settings, the cache, the backups)
lives in `data\`, which is not part of the repository. `scanner.py --summary` shows what would be found,
without a window. Tests: `.venv\Scripts\python.exe tests\run_all.py` runs every suite on a throwaway copy
of the data, then the safety nets (imports, layers, migration). The installer is built with
`requirements-build.txt` and `packaging\build.py`.

The ready-made installer, for friends: [GreenYRO/game-launcher-releases](https://github.com/GreenYRO/game-launcher-releases).

### What is not here, and why

The development repository stays private: its history holds the author's own settings and library from
the early phases. What you see here is a snapshot of one of its commits, made by
`packaging/export_public.py`: `git archive` of the tree, minus the paths marked `export-ignore` in
`.gitattributes` (Claude Code's working files, the explanations written for the author, the artwork the
mockups were made with), checked before publishing to hold no key, no e-mail address and no account. No
personal data is in the repository: the library, the settings and the SteamGridDB key live in `data\`, on
each user's own PC. The screenshots and the trailer above were made on a test copy of the library, with
the accounts renamed.

Network: the launcher talks only to `store.steampowered.com` and `api.steampowered.com` (records,
artwork, prices, news, the wishlist), to `api.github.com` (whether a newer version is out; installed
copies only) and, optionally, to `steamgriddb.com`, with the user's own key. All of it is read-only,
anonymous and cached on disk; the full list and the rules are in `shared/rules.py` and
`docs/DISTRIBUTIE.md`.

### How it was built

The program was built with Claude Code (Anthropic), in phases: each phase had a brief, a check on the real
PC and tests of its own (over 3,400 checks in the last full run), and since October 2026 each phase is
also explained back by the author, in his own words. The use of AI is approved by the thesis coordinator,
on the condition that the author can explain what the program does. The log of every phase is
`docs/ISTORIC.md`.

### Licence

MIT, in `LICENSE`. The Inter (SIL OFL 1.1) and Phosphor Icons (MIT) fonts are in `presentation/fonts/`
with their licences; PySide6 (LGPL v3) and pygame-ce (LGPL) are installed from `requirements.txt`.

Author: Nicolae-Andrei Dulama ([GreenYRO](https://github.com/GreenYRO)).
