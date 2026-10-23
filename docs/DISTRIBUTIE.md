# Distribuția: launcher-ul pe PC-ul altcuiva

**Stare:** fazele 77–80 sunt făcute: verificarea actualizărilor (faza 79) este secțiunea 9,
exportul anonim pentru analiză (faza 80) secțiunea 10. Nota pentru prieteni este
`docs/CITESTE-MA.md`.

Până în faza 76, launcher-ul presupunea că rulează pe PC-ul meu: căuta jocuri în `C:\games` și
`C:\voices38`, iar Settings nu le putea schimba. Pe alt PC, fără foldere de jocuri, ar fi arătat
doar jocurile din magazine, fără nicio explicație. Documentul acesta spune ce s-a schimbat ca să
meargă pe PC-ul altcuiva și cum a fost dovedit.

## Cuprins

1. [Installer-ul și unde stau datele](#1-installer-ul-și-unde-stau-datele)
2. [Prima pornire](#2-prima-pornire)
3. [Numărul versiunii](#3-numărul-versiunii)
4. [Arhiva de diagnostic](#4-arhiva-de-diagnostic)
5. [Proba automată a installer-ului](#5-proba-automată-a-installer-ului)
6. [Testul în Windows Sandbox](#6-testul-în-windows-sandbox)
7. [Lista de verificat în Sandbox](#7-lista-de-verificat-în-sandbox)
8. [Pe PC-ul meu](#8-pe-pc-ul-meu)
9. [Verificarea actualizărilor (faza 79)](#9-verificarea-actualizărilor-faza-79)
10. [Exportul pentru analiză (faza 80)](#10-exportul-pentru-analiză-faza-80)
11. [Glosar](#11-glosar)

---

## 1. Installer-ul și unde stau datele

`packaging\build.py` face `dist\GameLauncher-Setup.exe` (circa 70 MB, în jumătate de minut):
îngheață programul cu PyInstaller, îl arhivează și pune arhiva într-un installer. Installer-ul:

- **instalează pentru utilizatorul curent**, în `%LOCALAPPDATA%\Programs\Game Launcher`, deci nu
  cere parolă de administrator, iar folderul rămâne al lui;
- **ține datele lângă program**, în același folder: `config.json`, `library.db`, `launcher.log`,
  `cache\`, `backups\`, `save_backups\`. O copie de rezervă înseamnă să copiezi un singur folder;
- pune patru scurtături (Desktop și Start, normal și TV) și o intrare în Add/Remove Programs, cu
  versiunea.

**O actualizare** (noul Setup.exe rulat peste cel vechi) șterge doar programul: folderul
`_internal` și fișierele de la rădăcină care nu sunt pe lista de păstrat (`USER_DATA`). Folderele
(`cache`, `backups`, `save_backups`) rămân întotdeauna. **Găsit în faza 78:** jurnalul
(`launcher.log` și cele două copii mai vechi) nu era pe listă, deci o actualizare îl ștergea, iar
un prieten care actualizează și apoi are o problemă ar fi trimis o arhivă de diagnostic fără
jurnalul de dinainte. Acum e pe listă, în installer și în copia ei din `logic/uninstall.py`.

**Dezinstalarea** (din Windows, sau `GameLauncher.exe --uninstall`) întreabă înainte și întreabă
separat dacă să șteargă și datele; răspunsul implicit le păstrează.

**Pornirea cu Windows** (faza 92). Comutatorul „Start with Windows” scrie o valoare în cheia Run a
utilizatorului, `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, cu numele **Game Launcher**:
`"<folderul instalării>\GameLauncher.exe" --background` la o copie instalată (din sursă,
`"<venv>\pythonw.exe" "<proiect>\launcher.py" --background`). Valoarea e singura lui înregistrare (nu
e în `config.json`), deci comutatorul arată mereu ce va face Windows. Comutatorul din Startup apps al
Windows (Task Manager, Setări) nu șterge valoarea: scrie 12 octeți cu același nume în
`...\Explorer\StartupApproved\Run`, cu primul octet 02 pornit și 03 oprit (citiți pe PC-ul meu pe 17
octombrie); launcher-ul îi citește și nu-i scrie niciodată, iar rândul din Settings spune când Windows
l-a oprit. **O actualizare** nu atinge valoarea: exe-ul rămâne la aceeași cale, deci valoarea rămâne
bună. **Dezinstalarea** o șterge, dacă pornește exe-ul ei (altfel Windows ar încerca, la fiecare
conectare, să pornească un exe care nu mai există); o valoare care pornește altă copie rămâne.

## 2. Prima pornire

**O instalare nouă nu are `config.json`.** Fereastra amână prima scanare, apare, întreabă
„Where do you keep your games?” și abia după răspuns scanează (*first-run experience*). Pe PC-ul
meu întrebarea nu apare niciodată, fiindcă fișierul există; nici în suitele de teste, fiindcă
fiecare își copiază `config.json`-ul.

**Ce propune.** Pe fiecare disc fix (fără stick-uri USB, fără unități de rețea, după răspunsul
Windows, `GetDriveTypeW`), folderele de pe primul nivel al căror nume conține unul dintre cuvintele
`games`, `game`, `gaming`, `jocuri`, `joc`. Nu propune niciodată:

- bibliotecile magazinelor (SteamLibrary, Epic Games, GOG Games, XboxGames, Riot Games și altele):
  jocurile din ele le găsesc deja sursele lor;
- un folder care conține `steamapps` (o bibliotecă Steam, oricum s-ar numi);
- folderele Windows (Windows, Program Files, Users...), cele ascunse și legăturile.

Pe PC-ul meu ar propune exact `C:\Games`; `C:\voices38` nu are un cuvânt de joc în nume, așa că un
asemenea folder se adaugă de mână.

**Răspunsurile posibile:**

- **Continue** scrie folderele bifate (plus cele adăugate) și alegerea pentru Xbox;
- **„I only use Steam, GOG, Epic or Xbox”**, sau închiderea ferestrei, scrie o listă goală, iar
  aceasta e un răspuns valid. În ambele cazuri întrebarea nu mai apare niciodată, nici măcar
  pentru o listă goală.

**A doua întrebare (faza 79): „Want more cover art?”.** Imediat după prima, cu scanarea pornită
deja în spate: dacă vrei o cheie SteamGridDB. Steam are coperți doar pentru jocurile lui; pentru
restul, launcher-ul poate căuta și pe SteamGridDB, dar doar cu o cheie gratuită a utilizatorului.
Fereastra spune cum se face una (pe steamgriddb.com, cu contul Steam, Preferences → API), are un
buton care deschide pagina în browser, un câmp în care se lipește cheia, **Test** (întreabă
SteamGridDB dacă merge) și **Skip** / **Save key**. Sărită sau închisă, nu scrie nimic: câmpul e
același cu cel din Settings → Artwork and the internet. Salvată, cheia se scrie singură în
`config.json` (fără să atingă restul), nu apare niciodată în jurnal și nu intră în arhiva de
diagnostic. La televizor, controlerul începe pe Skip, fiindcă acolo nu se poate scrie.

**O unitate întreagă** (de exemplu `D:\`) nu se mai poate alege, de la 1.2.2 (faza 82: un
avertisment nu oprea pe nimeni, iar primul prieten a ales `C:\`): lista o refuză, spune de ce și pune
în locul ei folderele de jocuri de pe acea unitate, bifate; un folder Windows (Program Files,
Users...) e refuzat la fel, nu e scanat și nu poate fi șters niciodată, iar un `config.json` mai vechi
care conține o unitate întreagă nu e scanat, ci numit în bibliotecă până când îl schimbă utilizatorul.

**`rules.DEFAULT_ROOTS`** (`C:\games`, `C:\voices38`) mai contează doar acolo unde nu întreabă
nimeni: `scanner.py` rulat fără configurație și un `config.json` fără cheia `roots`, adică PC-ul meu.

**În Settings**, la Finding games → Game folders, aceeași listă se poate schimba oricând. O listă
schimbată pornește imediat o scanare, iar un folder scos din listă nu șterge nimic.

**Biblioteca goală spune de ce e goală:**

- nu e ales niciun folder și niciun magazin nu are jocuri instalate;
- folderele alese nu sunt de găsit, iar mesajul le numește (un disc deconectat);
- folderele există, dar nu s-a găsit nimic în ele;
- în timpul primei scanări: „Looking for your games...”.

## 3. Numărul versiunii

**Un singur loc pentru versiune** (*single source of truth*): `shared/version.py`, cu `APP_VERSION =
"1.2.10"`. Din el citesc:

1. `packaging/build.py`, care scrie versiunea în `_internal\VERSION` și ziua construirii în
   `_internal\BUILD`;
2. installer-ul, care trece versiunea în Add/Remove Programs;
3. `launcher.log`, care începe fiecare pornire cu „Game Launcher 1.2.10, built 2026-10-23”;
4. Settings, a cărui ultimă secțiune, About, arată versiunea și ziua construirii, sau „Run from
   source” pentru copia mea.

Un test verifică toate patru. **Versionare semantică** (*semantic versioning*), MAJOR.MINOR.PATCH:

- PATCH crește pentru o reparație;
- MINOR pentru ceva nou care nu strică nimic;
- MAJOR pentru ceva care schimbă ce exista.

Prietenii văd versiuni, nu numere de fază. 1.0 a fost installer-ul construit prima dată (faza 47);
1.1.0 a fost construit în faza 78 și nu a fost dat nimănui (nu știe să verifice actualizările);
**1.2.0** (faza 79) este primul dat cuiva, publicat pe GitHub; **1.2.1** (faza 80) adaugă exportul
anonim; **1.2.2** (faza 82) e o reparație: o unitate întreagă nu mai poate fi un folder de jocuri;
**1.2.3** (faza 85) aduce pagina **Reports**, cele șapte rapoarte din fazele 83–84 (`docs/ANALIZA.md`);
**1.2.4** (faza 88) aduce lista de dorințe Steam și pagina **Wishlist** (fazele 86–87);
**1.2.5** (faza 90) aduce potrivirea mai precisă a listei de dorințe, raportul 8 („Stated and
revealed”) și linia prețurilor fiecărui joc dorit (faza 89); **1.2.6** (faza 95) aduce viața lângă ceas
(iconița, o singură copie pornită, Start with Windows, faza 92), sesiunile jocurilor pornite din afara
launcher-ului (faza 93, biblioteca trece la versiunea 7 a bazei) și somnul PC-ului care nu se mai
numără drept joc (faza 94); **1.2.7** (faza 97) aduce cardul **Recap** de pe pagina Stats, luna sau anul
ca o imagine de trimis, și regula unică după care Stats numără orele oricărui joc jucat (faza 96);
**1.2.8** (faza 100) aduce locul **For you** și raportul 9 (faza 98), întrebarea pusă o singură dată despre
iconița de lângă ceas, culoarea de accent, ecranul **Starting…** și filtrul de gen (faza 99); **1.2.9**
(faza 104) aduce alertele de preț pe lista de dorințe (faza 101, biblioteca trece la versiunea 8 a bazei),
întrebarea **How was it?** de după o sesiune și raportul 10 (faza 102), orele unui joc pe pagina lui (extensia
fazei 102), rândul **Left behind** din For you și raportul 11 (faza 103); **1.2.10** (faza 107) aduce
coperțile lipsă căutate toate deodată pe SteamGridDB (faza 105) și fereastra **What's new**, cu notele fiecărei
versiuni ținute în proiect și puse în program (faza 106).

**Regula mea, din 12 octombrie: fiecare versiune nouă crește ultimul număr cu unu** (1.2.1, 1.2.2,
...), chiar și pentru ceva nou: pași mai mici decât cere versionarea semantică pentru MINOR.
Verificarea actualizărilor are nevoie doar ca fiecare număr nou să fie mai mare.

**Pentru o versiune nouă:**

0. scrii întâi notele versiunii, `docs/release-notes/<versiune>.md` (faza 106): româna sub `## Română`, engleza
   sub `## English`; `packaging\build.py` nu construiește o versiune fără ele, iar pagina de pe GitHub se face din
   fișier (`--notes-file`), deci cele două nu diferă niciodată;
1. crești `APP_VERSION`;
2. pui deoparte `dist\GameLauncher-Setup.exe`, installer-ul versiunii de acum, pe care îl au
   prietenii (construirea îl înlocuiește);
3. rulezi `packaging\build.py`;
4. rulezi `tests\check_installer.py --over <installer-ul pus deoparte>` (secțiunea 5);
5. faci testul din Sandbox (secțiunile 6–7);
6. o publici pe GitHub, ca release (secțiunea 9): de acolo o descarcă prietenii, iar copiile lor mai
   vechi află singure că există.

## 4. Arhiva de diagnostic

Settings → Your library data → **Save diagnostics...** scrie un singur zip (*diagnostics bundle*),
pe care un prieten mi-l trimite când ceva nu merge. Conține:

| Fișier | Ce ține |
|---|---|
| `about.txt` | versiunea, ziua construirii, Windows, Python, PySide6, folderul de date |
| `config.json` | setările, **fără cheia SteamGridDB** (spune doar dacă există una) |
| `scan.json` | când a rulat ultima scanare, folderele cu jocuri (care sunt de găsit și care nu) și fiecare joc găsit: sursa, folderul, ce îl pornește, cum a fost ales exe-ul, exe-urile ocolite, ce spun fișierele magazinului și exe-ul ales de mână, dacă există |
| `summary.txt` | același lucru, ca tabel de citit (ce arată `scanner.py --summary`) |
| `launcher.log` (+ `.1`, `.2`) | jurnalul |

**Căile sunt incluse intenționat**: un joc din foldere se găsește după calea lui, iar o cale
greșită este răspunsul obișnuit la „nu-mi găsește jocul”.

**Nu sunt incluse** sesiunile, timpul jucat, notițele, semnele, cumpărăturile, prețurile și
conturile Steam. Jurnalul poate numi totuși un cont Steam într-un rând rar (un contor care a scăzut,
un fișier care nu s-a citit). De aceea, în copie, fiecare id de cont și fiecare SteamID64 cunoscut
devine „steam-account-N”, iar cheia, dacă ar apărea vreodată într-un rând, e scoasă. Arhiva se
scrie întreagă sau deloc (întâi un fișier temporar, apoi înlocuit).

## 5. Proba automată a installer-ului

`tests\check_installer.py` rulează installer-ul construit, nu sursa lui. Nu face parte din
`run_all`, pentru că are nevoie de o construire proaspătă. Totul se întâmplă într-un **profil
fals**: `USERPROFILE`, `APPDATA` și `LOCALAPPDATA` arată spre un folder temporar. Motivul e că
dezinstalarea șterge orice scurtătură cu identitatea programului, iar cele patru scurtături reale
ale mele o au; testul le verifică, octet cu octet, înainte și după. Singurul lucru din afara
profilului fals este intrarea din Add/Remove Programs (HKCU): trebuie să lipsească la început, iar
testul o scoate pe a lui, chiar dacă se oprește la jumătate.

Ce dovedește, în ordine:

1. installer-ul e construit din codul de acum: versiunea scrisă în el, schema cu scripturile ei de
   actualizare și fonturile, octet cu octet;
2. o primă instalare: scurtăturile și intrarea în Add/Remove Programs, cu versiunea;
3. **prima pornire, cum o vede PC-ul unui prieten**:
   - întrebarea apare înainte de orice scanare;
   - închisă, scrie o listă goală de foldere și alegerea pentru Xbox, apoi programul scanează
     magazinele;
   - urmează a doua întrebare, cheia SteamGridDB; închisă, nu scrie nimic (faza 79);
   - jurnalul începe cu versiunea și spune că a fost o primă pornire;
   - **verificarea actualizărilor**, singura cerere adevărată către GitHub a testului: răspunsul
     ținut minte și nimic mai nou oferit (faza 79);
4. **a doua instalare peste prima** (*idempotent upgrade*):
   - baza de date, setările, jurnalul cu cele două copii, cache-ul, copiile de siguranță și copiile
     salvărilor rămân octet cu octet;
   - ce lăsase o construire veche dispare;
   - programul ajunge exact cum îl lăsase prima instalare (264 de fișiere), deci a doua rulare a
     aceluiași installer nu schimbă nimic;
5. copia actualizată pornește fără întrebările primei porniri și nu mai întreabă GitHub în aceeași zi;
   - **întrebarea despre iconița de lângă ceas** (faza 99) apare acum, o singură dată (prima pornire n-o
     pune niciodată); închisă, înseamnă „Not now”: ziua e scrisă, comutatorul rămâne oprit;
   - **ce aduce 1.2.8, pe ecranul copiei instalate** (faza 100): locul For you în fereastră și, după un
     clic pe Settings, rândul Accent cu cele cinci culori; Settings închis, nu se scrie nimic. Testul
     citește ecranul cum îl citește un cititor de ecran (*screen reader*), prin UI Automation din
     Windows, chemat din PowerShell, fără nicio bibliotecă nouă;
   - **ce aduce 1.2.9** (faza 104): în același Settings, rândul After a game, cu „Ask how a session was”,
     comutatorul întrebării de după o sesiune;
   - **What's new** (faza 107, pentru 1.2.10): pe drumul prietenilor, la pornirea de după actualizare, întâi
     fereastra „What's new in 1.2.10”, citită de pe ecran, cu versiunea văzută încă cea veche cât e deschisă și cea
     nouă abia după ce e închisă; abia apoi întrebarea despre iconița de lângă ceas;
6. o dezinstalare tăcută păstrează datele;
   - **pornirea cu Windows** (faza 92): valoarea din cheia Run, pusă cum o scrie copia instalată,
     rămâne neschimbată după actualizare și dispare după dezinstalare. Cheia nu e cea adevărată:
     HKCU nu poate fi mutată ca folderele profilului, așa că fiecare proces pornit de test primește
     `GAME_LAUNCHER_TEST_STARTUP_KEY`, o cheie a testului, ștearsă la sfârșit; valoarea mea reală e
     comparată înainte și după;
7. scurtăturile mele n-au fost atinse;
8. **cu `--over <installer-ul versiunii de dinainte>`** (faza 85): drumul prietenilor, într-un al
   doilea profil fals. Versiunea veche se instalează și pornește ca la un prieten (cele două
   întrebări închise, o scanare, o bibliotecă a ei), apoi noul installer trece peste ea. Copia
   actualizată pornește fără să întrebe nimic, **își aduce biblioteca la versiunea de acum a bazei**
   (*schema migration*) după o copie de siguranță care ține fișierul vechi, păstrează rând cu rând
   jocurile bibliotecii și setările, iar jurnalul nu are nicio eroare.
   - **o alertă de preț, cum o întâlnește un prieten** (faza 104): în biblioteca adusă la zi, testul pune un
     cont al lui cu un joc pe lista de dorințe, o țintă de 20,00 €, un preț vechi peste ea, iar în fișierul
     prin care scanarea îi dă ferestrei prețurile noi (*hand-off*), unul sub ea; rețeaua oprită, deci nu se
     cere nimic. La pornirea următoare prețul intră în bibliotecă și alerta e scrisă în jurnalul alertelor o
     dată, cu vorbele ei („under your 20,00 € target”); același preț pus încă o dată nu mai anunță nimic.

Pe 11 octombrie (1.1.0): **31 din 31**. Pe 12 octombrie (1.2.0, cu a doua întrebare și verificarea
actualizărilor): **35 din 35**; singura cerere adevărată către GitHub a răspuns „niciun release
încă”, iar a doua pornire din aceeași zi nu a mai întrebat. Tot pe 12 octombrie (1.2.1, cu exportul
anonim): **35 din 35**; GitHub a răspuns „1.2.0”, deci nimic mai nou de oferit. Pe 15 octombrie
(1.2.3, cu `--over` installer-ul 1.2.2): **47 din 47**; biblioteca copiei 1.2.2 (12 jocuri, versiunea 4)
a ajuns la versiunea 5, cu jocurile și setările neschimbate. Tot pe 15 octombrie (1.2.4, cu `--over`
installer-ul 1.2.3): **47 din 47**; biblioteca a trecut de la versiunea 5 la 6 (lista de dorințe). Pe 16
octombrie (1.2.5, cu `--over` installer-ul 1.2.4): **45 din 45**; schema a rămas la versiunea 6, deci nu
era nimic de adus la zi, iar cele două verificări ale trecerii la o versiune nouă devin un singur rând.
Pe 17 octombrie (codul fazei 92, construit doar pentru probă, nepublicat): **38 din 38**, cu cele două
verificări ale pornirii cu Windows. Pe 18 octombrie (1.2.6, cu `--over` installer-ul 1.2.5): **51 din
51**; biblioteca copiei 1.2.5 (11 jocuri, versiunea 6) a ajuns la versiunea 7, după o copie de
siguranță, cu jocurile și setările neschimbate, iar copia instalată citește lista proceselor (1.2.6 e
prima care se uită la jocurile pornite din afara ei). Tot pe 18 octombrie (1.2.7, cu `--over` installer-ul
1.2.6): **49 din 49**; schema a rămas la versiunea 7, deci nu era nimic de adus la zi. Pe 19 octombrie
(1.2.8, cu `--over` installer-ul 1.2.7): **61 din 61**, cu douăsprezece verificări noi: întrebarea despre
iconița de lângă ceas (niciodată la prima pornire, o dată la următoarea și o dată după actualizare), apoi
For you și rândul Accent citite de pe ecranul copiei instalate, și iconița nouă a launcher-ului, în program
și în iconițele lui `GameLauncher.exe` și `Setup.exe`; schema a rămas la versiunea 7. Pe 22 octombrie (1.2.9,
cu `--over` installer-ul 1.2.8): **73 din 73**, cu douăsprezece verificări noi: rândul After a game citit de pe
ecranul copiei instalate; biblioteca copiei 1.2.8 (10 jocuri, versiunea 7) adusă la versiunea 8 după o copie de
siguranță care ține versiunea 7, cu toate cele nouă vederi răspunzând, coloanele jocurilor din 1.2.8 rând cu rând
și cele două coloane noi goale; setările neschimbate, în afară de versiunea cu care a rulat ultima dată, care
spune acum 1.2.9; apoi alerta plantată, scrisă o dată, cu vorbele ei, și același preț din nou, fără nicio alertă.
Pe 23 octombrie (1.2.10, cu `--over` installer-ul 1.2.9): **75 din 75**; la pornirea de după actualizare a venit
întâi „What's new in 1.2.10”, citită de pe ecran, cu versiunea văzută încă 1.2.9 cât a fost deschisă și 1.2.10 după
ce s-a închis, abia apoi întrebarea despre iconița de lângă ceas; notele versiunii sunt în build octet cu octet;
schema a rămas la versiunea 8, deci nu era nimic de adus la zi.

**O a doua construire peste prima se oprea** („Access is denied”): PyInstaller copiază folderele cu
atributele lor, iar `data_access\upgrades` poartă semnul ReadOnly al folderelor din octombrie
(CLAUDE.md, faza 69). `packaging\build.py` scoate acum semnul și șterge din nou (găsit în faza 79).

## 6. Testul în Windows Sandbox

Windows Sandbox este o funcție din Windows 11 Pro: un Windows curat, de unică folosință, fără
Python, fără Steam și fără foldere de jocuri, adică exact cum arată PC-ul unui prieten pentru
launcher. Tot ce se face în el dispare când îi închizi fereastra.

**Cum îl pornești** (o singură dată; pe PC-ul meu nu era activat pe 11 octombrie):

1. Start → scrie **„Activare sau dezactivare caracteristici Windows”** (*Turn Windows features on or
   off*) și deschide-l;
2. bifează **Windows Sandbox** → OK → repornește PC-ul când îți cere;
3. dacă „Windows Sandbox” e gri (nu se poate bifa), virtualizarea e oprită: în Task Manager →
   Performance → CPU trebuie să scrie „Virtualization: Enabled”. Dacă scrie „Disabled”, se pornește
   din BIOS/UEFI.

**Fișierul pentru Sandbox**, `packaging\sandbox\GameLauncher.wsb`, e scris de
`packaging\sandbox\make_sandbox.py`. Fișierul conține căi absolute de pe PC-ul acesta, așa că nu e
în git; după o mutare a proiectului îl refaci cu:

```powershell
& .venv\Scripts\python.exe packaging\sandbox\make_sandbox.py
```

Aduce în Sandbox două foldere, amândouă **doar pentru citire**:

- `dist\`, pe Desktop, ca „Installer”;
- un joc din foldere, `C:\games\Slow Roads` (unul fără nimic ales pentru el), tot pe Desktop.

La pornire îl copiază în `C:\Games\Slow Roads` din Sandbox, ca întrebarea de la prima pornire să
găsească singură `C:\Games`, iar scanarea să găsească jocul într-un folder obișnuit. Folosește o
copie, nu folderul adus direct, pentru că nu e sigur că un folder adus arată din interior ca o
legătură, iar scanarea sare peste legături. Când copierea s-a terminat, se deschide File Explorer
pe „Installer”.

**SmartScreen nu apare în Sandbox**: fișierul vine de pe PC, nu de pe internet, deci nu e marcat
ca descărcat. Prietenii îl vor vedea; `CITESTE-MA.md` le spune ce să apese.

## 7. Lista de verificat în Sandbox

Dublu-clic pe `packaging\sandbox\GameLauncher.wsb`. Durează un minut să pornească, apoi încă câteva
secunde pentru copierea lui Slow Roads (481 MB), până se deschide Explorer.

1. **Instalarea:** dublu-clic pe `GameLauncher-Setup.exe` → „Install Game Launcher?” → Yes →
   „Open it now?” → Yes.
2. **Prima pornire:** apare „Where do you keep your games?”.
   - `C:\Games` e propus și bifat;
   - Xbox e oprit, fiindcă Sandbox-ul nu are folder XboxGames;
   - apasă **Continue**;
   - apare a doua întrebare, „Want more cover art?”. **Open steamgriddb.com** deschide pagina în
     browserul din Sandbox; apasă **Skip** (sau lipește cheia ta, apasă Test, apoi Save key).
3. **Folderul găsit:** biblioteca arată „Slow Roads” (singurul joc; Sandbox-ul nu are Steam sau
   alte magazine). Pune-i o stea, ca să vezi la pasul 7 că a rămas.
4. **O pagină deschisă:** clic pe Slow Roads. Pagina lui se deschide. Coperta vine de la Steam
   dacă rețeaua din Sandbox merge.
5. **Versiunea:** Settings → ultima secțiune, About: „Game Launcher 1.2.10” și „Built ...” cu ziua
   construirii. Dedesubt, **Updates**: „You have the newest version. Checked today at ...” (launcher-ul
   a întrebat GitHub la câteva secunde după ce a pornit). **Open the download page** deschide pagina
   versiunilor. În Finding games → Game folders apare `C:\Games`.
6. **Arhiva de diagnostic:** Settings → Your library data → Save diagnostics... → pe Desktop. Rândul
   spune unde a salvat-o. Deschide zip-ul: `summary.txt` arată Slow Roads cu calea lui. Apoi, din
   același loc, **Anonymous export...** → fereastra spune ce conține → Save... → pe Desktop.
   Deschide-l în Notepad: Slow Roads e acolo, cu numele Steam și timpul, fără nicio cale (faza 80).
7. **Același Setup.exe, încă o dată:** închide launcher-ul și rulează din nou
   `GameLauncher-Setup.exe` → „Update Game Launcher?” → Yes → Open → nu mai pune întrebările primei
   porniri; apare o singură dată „Keep Game Launcher running?” → **Not now**. Slow Roads e acolo, cu steaua.
8. **`--silent`:** închide launcher-ul. Start → `cmd`, apoi:
   `"%USERPROFILE%\Desktop\Installer\GameLauncher-Setup.exe" --silent`. Scrie „updated to ...”,
   fără nicio întrebare. Pornit din scurtătura de pe Desktop, launcher-ul e tot cum l-ai lăsat.
9. **Închide fereastra Sandbox-ului.** Tot ce s-a făcut în el dispare.

Dacă ceva arată ciudat, jurnalul din Sandbox e în
`%LOCALAPPDATA%\Programs\Game Launcher\launcher.log`. Arhiva de la pasul 6 îl conține deja.

## 8. Pe PC-ul meu

Două verificări, făcute pe 11 octombrie: Settings arată versiunea (1.1.0, „Run from source”) și
rândul Game folders cu cele două foldere ale mele; iar prima mea pornire nu s-a schimbat cu nimic,
fiindcă `config.json` există.

## 9. Verificarea actualizărilor (faza 79)

**Ce face.** O copie instalată întreabă GitHub, o dată pe zi, dacă a apărut o versiune mai nouă
decât a ei. Dacă da, apare un mesaj la pornire („Game Launcher 1.3.0 is out. Settings, under About,
has the download page.”), iar Settings → About → Updates arată versiunea nouă și butonul **Open the
download page**. Butonul deschide în browser pagina ultimei versiuni; de acolo prietenul descarcă
noul Setup.exe și îl rulează peste cel vechi, ca la orice actualizare (secțiunea 1).

**Doar spune; nu descarcă și nu instalează nimic singur** (*update notification*, nu *auto-update*).
Un program nesemnat care descarcă și rulează alte programe e exact ce suspectează antivirusurile, și
ar trebui să dovedească singur că fișierul descărcat e al meu. Drumul prin browser și SmartScreen
e cel pe care prietenii îl știu deja.

**De unde află.** Codul stă într-un depozit GitHub **privat**, iar unul privat nu se poate citi fără
parolă; o parolă nu are ce căuta într-un fișier dat altcuiva. De aceea installerele stau într-un
depozit **public**, separat, care nu conține cod: `GreenYRO/game-launcher-releases`, făcut pe 11
octombrie (doar un README, în engleză și română). Fiecare versiune dată prietenilor devine acolo un
*release*: eticheta `vX.Y.Z` și fișierul `GameLauncher-Setup.exe`. Launcher-ul cere

`https://api.github.com/repos/GreenYRO/game-launcher-releases/releases/latest`

**a șaptea adresă** de pe lista celor permise (CLAUDE.md): o cerere anonimă, doar de citire, fără
cont și fără cheie. GitHub vede adresa de internet a conexiunii, ca Steam, și nimic altceva.

**Răspunsurile, citite de pe GitHub pe 11 octombrie** și păstrate în `tests/fixtures`:

- un release are `tag_name` („v4.1”), `name`, `draft`, `prerelease` și `published_at`;
- un depozit fără niciun release răspunde **404** („Not Found”). E un răspuns („nimic mai nou”),
  nu o eroare;
- GitHub permite 60 de întrebări pe oră de la o conexiune (*rate limit*); launcher-ul pune una pe zi.

**Regulile:**

- **doar o copie instalată întreabă.** Copia mea, rulată din sursă, nu întreabă niciodată (e mereu
  cea mai nouă), deci adresele cu care vorbește PC-ul meu rămân aceleași;
- „Allow network lookups” oprit înseamnă că nu întreabă;
- întreabă la ~6 secunde după ce apare fereastra, pe alt fir decât al ferestrei, deci nu o oprește
  niciodată;
- un răspuns e bun o zi; o întrebare fără răspuns (fără internet, GitHub căzut sau limita atinsă)
  se repune după 6 ore. Ultimul răspuns stă în `cache\update_check.json`, de unde îl citește
  Settings;
- **compară numerele, nu textul**: 1.10.0 e mai nou decât 1.9.0. O etichetă care nu e o versiune,
  un *draft* sau un *pre-release* nu sunt oferite niciodată;
- butonul deschide **mereu aceeași pagină**, niciodată o adresă luată din răspuns;
- mesajul apare cel mult o dată pe zi, doar când chiar a întrebat GitHub.

**Cum scot o versiune nouă** (după pașii 1–5 din secțiunea 3):

1. pe GitHub, în `GreenYRO/game-launcher-releases` → Releases → **Draft a new release**;
2. eticheta: `v` plus versiunea exactă din `shared/version.py` (de exemplu `v1.2.0`);
3. un titlu, două rânduri despre ce s-a schimbat, `dist\GameLauncher-Setup.exe` atașat. **Din 1.2.6
   (cererea mea, 18 octombrie), notele sunt în română și în engleză**: întâi româna, apoi același text
   în engleză;
4. **Publish release**. Un *draft* nu îl vede nimeni, deci îl poți pregăti din timp.

Același lucru din linia de comandă:

```powershell
gh release create v1.2.0 dist\GameLauncher-Setup.exe --repo GreenYRO/game-launcher-releases --title 1.2.0 --notes "Ce s-a schimbat"
```

Copiile mai vechi ale prietenilor află în cel mult o zi.

**Primul release: 1.2.0, publicat pe 12 octombrie** (la cererea mea, înainte de testul din Sandbox,
care rămâne de făcut): `github.com/GreenYRO/game-launcher-releases/releases/tag/v1.2.0`, cu
`GameLauncher-Setup.exe` (71.906.555 octeți, SHA-256 `19246f92…a5e275`, același cu cel din `dist\`,
verificat după încărcare). Înainte de publicare: cheia mea SteamGridDB nu e nicăieri în installer sau
în cele 264 de fișiere pe care le despachetează, și nici setările, biblioteca sau jurnalul meu. Citit
apoi cum îl citește launcher-ul: versiunea 1.2.0, nici *draft*, nici *pre-release*; o copie 1.2.0
spune „You have the newest version”, una mai veche ar afla de el.

**Al doilea release: 1.2.1, publicat tot pe 12 octombrie** (exportul anonim, după ce l-am încercat):
`.../releases/tag/v1.2.1`, 71.931.436 octeți, SHA-256 `d21cec9b…853e39`, verificat la fel. Copiile
1.2.0 ale prietenilor află de el în cel mult o zi.

**Al treilea release: 1.2.2, publicat pe 14 octombrie** (reparația din faza 82, după ce am încercat
pe PC-ul meu că `C:\` e refuzat): `.../releases/tag/v1.2.2`, 71.937.531 octeți, SHA-256
`5c4c49ec…812e14`, verificat la fel: cheia mea în niciunul dintre cele 264 de fișiere, apoi citit cum
îl citește launcher-ul (1.2.2, nici *draft*, nici *pre-release*, mai nou decât 1.2.1), iar fișierul de
pe GitHub e același cu cel din `dist\`. Copiile 1.2.1 ale prietenilor află de el în cel mult o zi.

**Al patrulea release: 1.2.3, publicat pe 15 octombrie** (pagina Reports, după ce am deschis-o pe
PC-ul meu): `.../releases/tag/v1.2.3`, 71.997.643 octeți, SHA-256 `79e5e942…84df716e`, verificat la
fel: cheia mea în niciunul dintre cele 265 de fișiere, drumul prietenilor încercat cu installer-ul
1.2.2 adevărat (`check_installer.py --over`), apoi citit cum îl citește launcher-ul (1.2.3, nici
*draft*, nici *pre-release*, mai nou decât 1.2.2), iar fișierul de pe GitHub e același cu cel din
`dist\`. Copiile 1.2.2 ale prietenilor află de el în cel mult o zi; la prima pornire a lui 1.2.3,
biblioteca lor trece la versiunea 5 a bazei, după o copie de siguranță.

**Al cincilea release: 1.2.4, publicat tot pe 15 octombrie** (lista de dorințe și pagina Wishlist, după
ce am deschis-o pe PC-ul meu): `.../releases/tag/v1.2.4`, 72.055.112 octeți, SHA-256 `79c724c2…ff2e6a3`,
verificat la fel: cheia mea în niciunul dintre cele 266 de fișiere, drumul prietenilor încercat cu
installer-ul 1.2.3 adevărat (`check_installer.py --over`: biblioteca de la versiunea 5 la 6), apoi citit
cum îl citește launcher-ul (1.2.4, mai nou decât 1.2.3), iar fișierul de pe GitHub e același cu cel din
`dist\`. Copiile 1.2.3 ale prietenilor află de el în cel mult o zi.

**Al șaselea release: 1.2.5, publicat pe 16 octombrie** (potrivirea mai precisă a listei de dorințe,
raportul 8 și linia prețurilor, din faza 89): `.../releases/tag/v1.2.5`, 72.064.086 octeți, SHA-256
`97d3f80e…1125096d`, verificat la fel: cheia mea în niciunul dintre cele 266 de fișiere, drumul
prietenilor încercat cu installer-ul 1.2.4 adevărat (`check_installer.py --over`: aceeași schemă, nimic
de adus la zi), apoi citit cum îl citește launcher-ul (1.2.5, mai nou decât 1.2.4), iar fișierul de pe
GitHub e același cu cel din `dist\`. Copiile 1.2.4 ale prietenilor află de el în cel mult o zi.

**Al șaptelea release: 1.2.6, publicat pe 18 octombrie** (viața lângă ceas, jocurile pornite din afara
launcher-ului și somnul PC-ului, din fazele 92–94), primul cu notele în română și în engleză:
`.../releases/tag/v1.2.6`, 72.119.556 octeți, SHA-256 `3a8efa8e…5a17a29917`, verificat la fel: cheia mea
în niciunul dintre cele 267 de fișiere, drumul prietenilor încercat cu installer-ul 1.2.5 adevărat
(`check_installer.py --over`: biblioteca de la versiunea 6 la 7), apoi citit cum îl citește launcher-ul
(1.2.6, mai nou decât 1.2.5), iar fișierul de pe GitHub e același cu cel din `dist\`. Copiile 1.2.5 ale
prietenilor află de el în cel mult o zi; la prima pornire a lui 1.2.6, biblioteca lor trece la
versiunea 7 a bazei, după o copie de siguranță.

**Al optulea release: 1.2.7, publicat tot pe 18 octombrie** (cardul Recap de pe pagina Stats și regula
unică după care Stats numără orele, din faza 96), cu notele în română și în engleză:
`.../releases/tag/v1.2.7`, 72.166.532 octeți, SHA-256 `ef9d1a0d…183eb5031`, verificat la fel: cheia mea
în niciunul dintre cele 267 de fișiere, drumul prietenilor încercat cu installer-ul 1.2.6 adevărat
(`check_installer.py --over`: aceeași schemă, nimic de adus la zi), apoi citit cum îl citește launcher-ul
(1.2.7, mai nou decât 1.2.6), iar fișierul de pe GitHub e același cu cel din `dist\`. Copiile 1.2.6 ale
prietenilor află de el în cel mult o zi.

**Al nouălea release: 1.2.8, publicat pe 19 octombrie** (For you și raportul 9, din faza 98; întrebarea
despre iconița de lângă ceas, culoarea de accent, ecranul Starting… și filtrul de gen, din faza 99; iconița
nouă), cu notele în română și în engleză: `.../releases/tag/v1.2.8`, 72.569.885 octeți, SHA-256
`1550fbf2…f6545b45`, verificat la fel: cheia mea în niciunul dintre cele 267 de fișiere, drumul prietenilor
încercat cu installer-ul 1.2.7 adevărat (`check_installer.py --over`: 61 din 61, aceeași schemă), apoi citit
cum îl citește launcher-ul (1.2.8, mai nou decât 1.2.7), iar fișierul de pe GitHub e același cu cel din
`dist\`. Pregătit întâi ca *draft*, ca să citesc notele înainte să plece. Copiile 1.2.7 ale prietenilor află
de el în cel mult o zi și, la prima pornire după actualizare, primesc întrebarea o singură dată.

**Al zecelea release: 1.2.9, publicat pe 22 octombrie** (alertele de preț, din faza 101; întrebarea „How was
it?” și raportul 10, din faza 102, cu pastila orelor din extensia ei; rândul Left behind și raportul 11, din faza
103), cu notele în română și în engleză, întrebarea de după joc întâi: `.../releases/tag/v1.2.9`, 72.649.526
octeți, SHA-256 `c5e17a96…c876083d`, verificat la fel: cheia mea și adresa de e-mail în niciunul dintre cele 268
de fișiere, drumul prietenilor încercat cu installer-ul 1.2.8 adevărat (`check_installer.py --over`: 73 din 73,
biblioteca de la versiunea 7 la 8 și o alertă de preț plantată, anunțată o singură dată), apoi citit cum îl
citește launcher-ul (1.2.9, mai nou decât 1.2.8), iar fișierul de pe GitHub e același cu cel din `dist\`.
Pregătit întâi ca *draft*. Copiile 1.2.8 ale prietenilor află de el în cel mult o zi; la prima pornire a lui
1.2.9, biblioteca lor trece la versiunea 8 a bazei, după o copie de siguranță, iar după următoarea sesiune de
cel puțin 10 minute îi întreabă „How was it?”.

**Al unsprezecelea release: 1.2.10, publicat pe 23 octombrie** (coperțile lipsă căutate toate deodată, din faza 105;
fereastra What's new și notele fiecărei versiuni ținute în proiect, din faza 106), primul a cărui pagină e făcută din
fișierul de note (`--notes-file docs/release-notes/1.2.10.md`): `.../releases/tag/v1.2.10`, 72.693.456 octeți,
SHA-256 `b43f683e…aaa51c69`, verificat la fel: cheia mea și adresa de e-mail în niciunul dintre cele 273 de fișiere,
drumul prietenilor încercat cu installer-ul 1.2.9 adevărat (`check_installer.py --over`: 75 din 75, întâi What's new,
apoi întrebarea despre iconiță), apoi citit cum îl citește launcher-ul (1.2.10, mai nou decât 1.2.9), cu notele
paginii identice cu fișierul, iar fișierul de pe GitHub e același cu cel din `dist\`. Copiile 1.2.9 ale prietenilor
află de el în cel mult o zi; la prima pornire după actualizare le arată o dată „What's new in 1.2.10”.

### Ce aduce o versiune: What's new (faza 106)

Notele fiecărei versiuni stau în proiect, în `docs/release-notes/<versiune>.md` -- din 1.2.6 încoace, cele
publicate copiate de pe GitHub (singura schimbare: cele două etichete îngroșate au devenit titluri) -- și intră în
build. Pagina de pe GitHub se face din același fișier, deci ce citesc prietenii acolo și ce le arată launcher-ul sunt
același text. La prima pornire după o actualizare, launcher-ul arată o dată **What's new in 1.2.10**: partea
engleză a notelor, într-o fereastră care se derulează, cu Close; abia după ce e închisă scrie versiunea văzută
(`version_seen`), deci o pornire ascunsă lângă ceas sau una care se închide înainte o lasă pentru data următoare,
iar iconița de lângă ceas spune între timp „updated to 1.2.10”. Întrebarea despre iconița de lângă ceas, dacă mai e
datorată, vine abia după ea, la o secundă -- niciodată două ferestre una peste alta. Oricând: Settings → About →
**What's new**; iar când verificarea a găsit o versiune mai nouă, rândul Updates are **See what's new in ...**, cu
notele ei, din răspunsul pe care verificarea îl ține deja -- nimic cerut în plus.

## 10. Exportul pentru analiză (faza 80)

**Ce e.** Un fișier JSON, făcut de prieten din Settings → Your library data → **Anonymous
export...**, pentru comparația bibliotecilor din lucrare. Promisiunea din `CITESTE-MA.md` îl
definește: *ce jocuri ai și cât le-ai jucat, fără căi de foldere și fără nume de conturi; alegerea
ta*. Din launcher nu pleacă nimic: fișierul se salvează unde spune prietenul, se poate citi în
Notepad, iar trimiterea e a lui.

**Lista de dorințe Steam** (faza 86), pe care launcher-ul o citește o dată pe zi pentru conturile marcate
„Mine” (numărul contului merge doar la Steam, iar o listă privată nu dă nimic), nu intră în exportul
anonim: e ce a spus prietenul că vrea, nu ce joacă, iar comparația nu o folosește.

**Fereastra de dinainte** arată, cu numerele bibliotecii lui, ce va conține și ce nu va conține
niciodată, are un comutator pentru ce a plătit (oprit) și butoanele Cancel și Save... Merge și cu
controlerul: începe pe comutator, A îl schimbă, în jos până la Save, A salvează, B renunță.

**Principiile** (*privacy by design*):

- **minimizarea datelor** (*data minimisation*): doar ce cere comparația. Sesiunile pleacă doar ca
  totaluri pe lună, pe oră a zilei și pe zi a săptămânii, niciodată cu momentele lor; datele de
  „văzut prima dată” și „jucat ultima dată” doar ca lună. **Din versiunea 2 a formatului** (faza 93),
  totalurile spun și cum au fost măsurate sesiunile (`sessions.by_origin`): `launched` — pornite de
  launcher și cronometrate la secundă —, `observed` — văzute rulând în lista proceselor, oricine ar fi
  pornit jocul, cu câteva secunde de nesiguranță la fiecare capăt; fiecare joc are și numărul și
  minutele sesiunilor lui observate. Fișierul însuși o spune (`sessions.origin_means`). Un export de
  versiunea 1 nu are împărțirea: toate sesiunile lui au fost pornite de launcher, iar
  `compare_exports.py` îl citește așa;
- **pseudonimizarea conturilor Steam** (*pseudonymisation*): doar conturile marcate „Mine”, fiecare
  devenind „A”, „B”, ... în ordinea minutelor; numerele (id, SteamID64) și numele nu pleacă deloc.
  Conturile nemarcate (ale altcuiva de pe același PC) nu apar;
- **numele unui joc doar dacă l-a dat un magazin**: numele Steam pentru un joc legat de Steam,
  titlul magazinului pentru unul din GOG, Epic sau Xbox. Un joc găsit doar într-un folder și
  nelegat de nimic **nu are nume** în fișier: numele lui e al folderului, iar un nume de folder poate
  spune mai mult decât voia cineva să spună (de exemplu, de unde e o copie);
- **jocurile ascunse și uneltele rămân pe dinafară**, după aceeași regulă ca grila (`GameView`);
  un joc a cărui istorie a fost mutată pe o instalare mai nouă nu e numărat de două ori;
- **un cod de participant aleator** (`p-` și zece cifre hexazecimale), făcut la primul export și
  păstrat în `config.json`, ca două exporturi de pe același PC să fie recunoscute drept ale aceleiași
  persoane și nimic mai mult. **Nu intră niciodată în arhiva de diagnostic**, care are căi: cele două
  nu trebuie să poată fi legate;
- **o ultimă verificare** (*defence in depth*): înainte de a scrie un octet, tot exportul e căutat
  după fiecare cale, număr de cont și notiță din bibliotecă (`LibraryStore.personal_values`). Dacă
  apare vreuna, nu se scrie nimic, iar rândul din Settings spune ce fel de lucru a apărut (niciodată
  valoarea).

**Formatul** (`game-launcher-analysis`, versiunea 1), câmp cu câmp:

| Câmp | Ce ține |
|---|---|
| `format`, `version`, `app_version`, `made_on`, `participant` | ce fel de fișier e, versiunea launcher-ului, ziua (fără oră), codul |
| `about`, `never_in_it` | ce e fișierul, în română și engleză, și lista a ce nu e niciodată în el |
| `paid_included`, `left_out` | dacă are cumpărăturile; câte jocuri au rămas pe dinafară și de ce (ascunse, unelte, instalări vechi fără nimic) |
| `games[]` | `"source"`, `"installed"`, `"name"`, `"steam_appid"`, `"steam_type"`, `"genres"`, `"first_seen"` (lună), `"last_played"` (lună), `"status"`, `"favorite"`, `"launcher_minutes"` (timpul măsurat de launcher; `null` pentru un joc pe care nu-l cronometrează), `"sessions"`, `"session_minutes"`, `"steam_minutes"` (timpul Steam pe conturile marcate „Mine”), `"steam_accounts"` și, doar la cerere, `"paid"` (sumă, monedă, magazinul din lista ferestrei sau „other”, luna; niciodată notița) |
| `sessions` | `count`, `minutes`, `first_month`, `last_month`, `by_month`, `by_hour` (0–23, ora locală la care a început), `by_weekday` |
| `steam.accounts[]` | `account` („A”...), `minutes`, `apps_with_time`, `last_read` (lună) |
| `steam.history[]` | fiecare aplicație din istoria Steam a conturilor marcate: `steam_appid`, `name`, `steam_type`, `genres`, `minutes`, `accounts`, `last_played` (lună) |

**Ce nu e niciodată în el:** căi de foldere și nume de exe, numele jocurilor găsite doar în foldere,
numele și numerele conturilor Steam, notițele, copertele alese, setările, cheia SteamGridDB,
jurnalul și orele sesiunilor.

**Pe biblioteca mea** (12 octombrie, pe o copie): 51 de jocuri (27 instalate), 106 sesiuni, timpul
Steam pentru 335 de aplicații pe cele 4 conturi marcate („A”–„D”), 5 jocuri fără nume, 1 joc ascuns
și 5 unelte lăsate pe dinafară; aproximativ 70 KB.

### Comparația (faza 81)

Fișierele primite de la prieteni (și exportul meu, făcut la fel) le pun în **`data\exports\`** (git îl
ignoră: datele lor nu ajung niciodată în depozit, nici anonime), apoi rulez:

```powershell
& .venv\Scripts\python.exe compare_exports.py
```

Scrie **`data\exports\comparison\index.html`** și îl deschide în browser, plus opt fișiere CSV pentru
Excel (separate prin punct și virgulă, cu virgulă zecimală, ca Excel în română). Ce face:

- citește fiecare `*.json`; ce nu e un export (alt fișier, stricat, un format mai nou, fără cod) e
  lăsat deoparte, cu motivul spus;
- dintr-un participant cu mai multe fișiere ține **cel mai nou**; participanții se numesc **P1, P2,
  ...** în ordinea zilei primului lor fișier, ca un prieten care trimite din nou să-și păstreze eticheta;
- **pagina** (în română): tabelul participanților; orele prin launcher și orele pe Steam, în **două
  grafice separate** (nu se adună: una e de la instalarea launcher-ului, cealaltă de-a lungul vieții
  conturilor); de unde vin jocurile instalate; când se joacă (ora din zi, ziua din săptămână); genurile,
  ca parte din timpul Steam; **cât de asemănătoare sunt bibliotecile** (indicele Jaccard pe jocurile
  jucate: cele comune împărțite la toate); jocurile jucate de mai mulți; cele mai jucate; semnele; ce
  au plătit (doar cei care au ales); fișierele; cum se citesc cifrele;
- **fiecare grafic are alături tabelul cu cifrele**, iar trecând cu mausul peste o bară îi vezi
  valoarea. Graficele mici puse unul lângă altul au aceeași scară. Culorile sunt verificate pentru
  cititorii care nu deosebesc anumite culori (*colour-blind safe*), în modul luminos și în cel întunecat;
- **numele fișierelor apar doar în secțiunea „Fișierele”**: dacă ai numit un fișier după cine ți l-a
  trimis, nu o copia în lucrare.

Nu trimite și nu descarcă nimic. Prietenii nu au nevoie de el: launcher-ul lor nu s-a schimbat.

## 11. Glosar

| Termen | În engleză | Pe scurt |
|---|---|---|
| prima pornire | first-run experience, onboarding | ce vede un utilizator nou înainte de orice altceva; aici, o singură întrebare |
| o singură sursă de adevăr | single source of truth | o valoare scrisă într-un singur loc, citită de toți ceilalți |
| versionare semantică | semantic versioning | MAJOR.MINOR.PATCH: ce înseamnă fiecare număr crescut |
| arhivă de diagnostic | diagnostics bundle, support bundle | un fișier cu ce trebuie pentru a înțelege o problemă, fără ce e personal |
| actualizare idempotentă | idempotent upgrade | rulată de două ori, lasă același rezultat ca o dată |
| profil fals | fake profile | variabile de mediu care mută folderele utilizatorului într-un loc temporar, pentru teste |
| semnătură digitală de cod | code signing | ce ar opri avertismentul SmartScreen; costă bani pe an, deci installer-ul nu o are |
| Windows Sandbox | Windows Sandbox | un Windows curat, de unică folosință, pornit dintr-un fișier `.wsb` |
| notificare de actualizare | update notification | programul spune că există o versiune nouă; omul o descarcă și o instalează (spre deosebire de *auto-update*) |
| release | GitHub Releases | o versiune publicată pe GitHub: o etichetă (`v1.2.0`), câteva rânduri și fișierele atașate |
| limită de cereri | rate limit | câte întrebări primește un serviciu de la o conexiune într-un timp dat; la GitHub, 60 pe oră fără cont |
| comparare de versiuni | semantic version comparison | numerele comparate pe rând, MAJOR, apoi MINOR, apoi PATCH; nu ca text |
| minimizarea datelor | data minimisation | doar datele de care e nevoie pentru scop, la granularitatea de care e nevoie (luna, nu ora) |
| pseudonimizare | pseudonymisation | un identificator înlocuit cu un cod fără legătură cu el („contul A”); cine are doar fișierul nu poate afla cine e |
| indicele Jaccard | Jaccard index | cât de asemănătoare sunt două mulțimi: câte elemente au în comun, împărțit la câte au împreună (0 = nimic, 1 = la fel) |
| grafice mici multiple | small multiples | același grafic, unul pentru fiecare participant, pe aceeași scară, puse unul lângă altul |
| apărare în adâncime | defence in depth | o a doua protecție independentă de prima: exportul nu cere date personale și, în plus, e verificat că nu le are |
