# Game Launcher — citește-mă

Versiunea 1.2.10. Ce face programul, ce citește, ce nu face niciodată și ce faci dacă nu merge.

## Ce face

Pune toate jocurile de pe PC într-un singur loc: cele din Steam, GOG, Epic și Xbox, plus cele pe
care le-ai pus singur într-un folder (copiate, dezarhivate sau instalate cu installer-ul lor).
Le arată ca o grilă de coperți, pe care o filtrezi și după gen (lângă sortare), le pornește (cât se
deschide jocul scrie **Starting…**, iar Esc te întoarce), ține minte cât ai jucat și face copii ale
salvărilor, cu controlerul și pe televizor; culoarea o alegi în Settings → Accent. **For you** (sub Library)
îți arată ce ai instalat și n-ai început, în ordinea asemănării cu ce joci, și ce încape diseară. Pagina
**Reports** (după Storage) îți arată unsprezece rapoarte despre biblioteca ta, calculate pe PC-ul tău, fără
să trimită nimic. Pe pagina **Stats**, cardul **Recap** face din luna sau anul tău o imagine:
**Share as image...** o copiază sau o salvează; imaginea nu are căi de foldere, conturi sau e-mail.
Pe pagina **Wishlist**, din meniul unui joc, **Alert me under...** îi pune o sumă: când prețul scade sub ea
sau la cel mai mic văzut vreodată, te anunță o dată, în fereastră sau lângă ceas. După o sesiune de cel
puțin 10 minute, în colțul ferestrei te întreabă **How was it?**: o stea apăsată o notează, **Skip** trece
mai departe, iar pe pagina jocului notezi și mai târziu; întrebarea o oprești din Settings → After a game.
Un joc marcat **Playing** pe care nu l-ai mai jucat de 30 de zile apare în For you, la **Left behind**:
**Finished**, **Dropped** sau **Still playing**, care îl lasă în pace încă 30 de zile.

## Ce citește de pe PC-ul tău

- **folderele cu jocuri pe care le alegi tu.** La prima pornire te întreabă unde îți ții jocurile;
  le schimbi oricând din Settings → Finding games → Game folders. Alege folderul în care stau
  jocurile, nu un disc întreg ca `C:\`: pe acela nu-l primește și îți pune în loc folderele de jocuri
  de pe el. A doua întrebare e dacă vrei o cheie SteamGridDB (mai jos); poți sări peste ea;
- **ce au instalat Steam, GOG, Epic și Xbox**, din fișierele lor de pe PC;
- **timpul jucat pe care Steam îl ține singur**, pentru fiecare cont care a intrat pe PC. Tu alegi
  în Settings care conturi sunt ale tale;
- **numele și datele fișierelor din folderele de salvări** (Documente, AppData), ca să afle unde își
  ține salvările un joc pornit din launcher. Nu le deschide și nu le citește conținutul.

## Ce nu face niciodată

- **nu are cont și nu cere niciun login;**
- **nu trimite nimic despre tine nicăieri.** Tot ce știe rămâne pe PC-ul tău;
- de pe internet cere doar **pagini publice ale magazinului Steam** (coperți, descrieri, prețuri și
  știrile unui joc când îi deschizi pagina) și, o dată pe zi, întreabă **GitHub** dacă a apărut o
  versiune nouă a launcher-ului. Nu trimite nume sau altceva despre tine. Poți opri tot asta:
  Settings → „Allow network lookups”;
- **lista de dorințe Steam:** pentru conturile marcate „Mine”, întreabă Steam o dată pe zi ce e pe lista ta
  publică (după numărul contului, singurul lucru despre tine care pleacă, și doar spre Steam) și îi urmărește
  prețurile pe pagina **Wishlist**, dar nu o schimbă niciodată și nu intră în cont; o listă privată nu apare;
- **SteamGridDB** (mai multe coperți), doar cu o cheie gratuită a ta: pe steamgriddb.com intri cu contul Steam,
  Preferences → API, generezi cheia și o lipești la prima pornire sau în Settings → Artwork and the internet;
  acolo, **Fill missing covers...** caută dintr-o dată coperți pentru jocurile fără una, după o copie de siguranță.

## Instalare

Descarci `GameLauncher-Setup.exe` de pe **github.com/GreenYRO/game-launcher-releases** (ultima versiune, „Latest”)
și îl rulezi. Nu cere parolă de administrator și pune scurtături pe Desktop și în meniul Start.

**Windows o să te avertizeze**: „Windows a protejat PC-ul” (*Windows protected your PC*). Apasă pe
**„Mai multe informații”** (*More info*), apoi pe **„Rulează oricum”** (*Run anyway*). Apare pentru că
fișierul nu e semnat digital de o firmă; o astfel de semnătură costă bani în fiecare an. Nu
înseamnă că programul are ceva. Rulează-l doar dacă vine de la mine: direct sau de pe pagina de
mai sus.

## Unde îi stau datele

Toate stau într-un singur folder: **`%LOCALAPPDATA%\Programs\Game Launcher`**. Scrie asta în bara
de adrese din File Explorer și apasă Enter. Acolo sunt setările, biblioteca, copiile de siguranță
și copiile salvărilor. Dacă vrei o copie de rezervă, copiezi tot folderul.

## Actualizare

Launcher-ul îți spune singur când a apărut o versiune nouă: un mesaj la pornire și, în Settings →
About → Updates, **See what's new** (ce aduce) și **Open the download page**, de unde o descarci. Nu
descarcă și nu instalează nimic singur. Închide launcher-ul (dacă stă lângă ceas: clic dreapta → Quit),
apoi rulează noul `GameLauncher-Setup.exe` peste cel vechi; păstrează jocurile, timpul jucat, coperțile și setările.
La prima pornire după actualizare îți arată o dată ce e nou (**What's new**); oricând, în Settings → About.

## Să rămână pornit în fundal

În Settings → **Running in the background** sunt trei comutatoare:
- **Keep running when the window is closed**: oprit la început, dar te întreabă o dată dacă îl vrei pornit. Închizi
  fereastra și launcher-ul rămâne ca iconiță lângă ceas; clic: fereastra; clic dreapta: jocuri, Settings..., **Quit**.
- **Start with Windows** (oprit): pornește ascuns, doar cu iconița, când intri în Windows (cere și primul).
- **Notice games started outside the launcher** (pornit): notează sesiunile unui joc de-al tău oricum l-ai
  pornit (din Steam, din scurtătura lui), cât rulează launcher-ul; nu se uită la altceva și nu ține altceva.

Le schimbi oricând din Settings, și un „Not now” dat întrebării. Al doilea clic pe scurtătură aduce launcher-ul în față.

## Dacă ceva nu merge

În launcher: **Settings → Your library data → Save diagnostics...**, salvezi fișierul zip și mi-l
trimiți. Conține jurnalul programului, versiunea, setările fără cheia SteamGridDB și ce a găsit ultima
căutare de jocuri, cu căile folderelor: din ele văd de ce nu găsește un joc.

**Nu conține** timpul jucat, notițele, ce ai plătit pe jocuri sau conturile tale Steam.

## Pentru lucrarea mea de licență

Launcher-ul este lucrarea mea de licență. S-ar putea să te rog să-mi trimiți un **export anonim**
al bibliotecii tale: ce jocuri ai, cât le-ai jucat și ce note le-ai dat (stelele și ziua), fără căi de
foldere și fără nume de conturi. M-ar ajuta să compar mai multe biblioteci în lucrare. **E alegerea ta.**
Dacă nu vrei, nu se trimite nimic, iar launcher-ul merge exact la fel.

Dacă vrei: Settings → Your library data → **Anonymous export...**. Fereastra îți arată ce conține,
cu numerele bibliotecii tale, salvezi un fișier și îl poți deschide în Notepad ca să citești tot ce e
în el. Din launcher nu pleacă nimic singur: fișierul mi-l trimiți tu, dacă vrei. Ce ai plătit pe
jocuri intră doar dacă bifezi asta; conturile tale Steam apar ca „A”, „B”, fără nume sau numere.

## Dezinstalare

În Windows: Setări → Aplicații → Game Launcher → Dezinstalare. Te întreabă dacă vrei să păstrezi
setările și timpul jucat, ca să le regăsești dacă îl instalezi din nou. Dacă era pornit **Start with
Windows**, dezinstalarea îl scoate și pe el, ca Windows să nu mai încerce să-l pornească.
