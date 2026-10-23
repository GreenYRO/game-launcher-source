# Istoricul construirii

Jurnalul construirii launcher-ului, fază cu fază, așa cum a fost scris în timpul lucrului: **în engleză,
în cuvintele de atunci**, cu ce s-a măsurat, ce s-a greșit, ce s-a reparat și ce a rămas deschis.

Până în faza 91 a stat în `CLAUDE.md`, fișierul pe care asistentul AI îl citește la începutul fiecărei
sesiuni; acolo ajunsese la 404 KB din 479 și se încărca de fiecare dată întreg. Pe 16 octombrie 2026
(faza 91) a fost mutat aici **neschimbat și în aceeași ordine**. În `CLAUDE.md` au rămas regulile,
arhitectura, comenzile, tabelul fazelor și o secțiune scurtă, „Lessons that still bind”: câte un rând
pentru fiecare lecție care încă leagă, cu numărul fazei ei, ca povestea întreagă să fie aici, la o căutare
distanță („## Phase 82 notes”, de pildă).

Este și **metoda** la care poate trimite declarația despre folosirea inteligenței artificiale din lucrare:
fiecare fază a fost cerută de mine, construită de asistent, încercată pe PC-ul meu înainte să înceapă
următoarea, iar aici e scris pentru fiecare ce s-a făcut, cum s-a dovedit (testele, cu câte verificări
și cum pică pe codul de dinainte) și ce a rămas de hotărât.

Ordinea nu e cronologică, ci cea din `CLAUDE.md`: întâi câteva note timpurii (fazele 2-12 și ce a fost
raportat din folosire după ele), apoi de la cea mai nouă (91) înapoi până la faza 17, apoi restul
celor timpurii (fazele 16-3, instalatorul, EA, Xbox, rețeaua).

## Phase 2 traps, all found by looking at a rendered window

Three of these produced a window that looked plausible in code and wrong on screen. Verify GUI
changes by rendering (`QWidget.grab().save(path)` under the native platform) and looking, not by
reasoning about the widget tree.

- **`QMenu.addMenu("text")`** — PySide6 does not keep the returned wrapper alive and the C++
  QMenu is destroyed before the menu is shown, so "Choose a different exe" silently died. Build
  submenus as `QMenu(title, parent)` and `addMenu(submenu)`.
- **`setUniformItemSizes(True)`** — forces every item to the *first* item's size hint, clipping
  every name longer than whatever happens to sort first. Must stay off.
- **Shell icon sizes are a lie.** `availableSizes()` advertises 256 for an exe whose largest real
  icon is 48, and `QIcon.pixmap()` ignores the requested size — asking for 256, 48 or 32 returns
  the same padded 256 canvas with the small bitmap in the top-left corner; only asking for 16
  yields the genuine bitmap. `icons.py` therefore judges the pixmap it receives, never the size
  it asked for. Getting this wrong renders one tile as a speck.
- **`first_seen` lives in `overrides.json`**, written by the GUI at merge time, because the
  "recently added" sort needs it and the catalog is disposable. This does not violate the
  separation rule: `scanner.py` and discovery never touch overrides.
- **"Started" and "trackable" are different questions.** `ui_actions.play` once read
  `if result.ok and result.running is not None`, which put a "would not start" dialog — with an
  empty reason, because there was no error — in front of every Steam, Epic and Xbox game that
  had just launched perfectly. URI launches always return `running=None`; only exe launches
  yield a process handle. Branch on `result.ok` alone, then check `running` separately to decide
  whether to time it. Reported by the user against real games; the tests had inspected the URI
  path but never called `play()`, which is exactly where the bug lived.
- **Playtime is a lower bound, by design.** `launch.PlaytimeTracker` watches only the process it
  started. Verified live: `notepad.exe` exits within two seconds while the real app keeps running,
  which is exactly how launcher/shim-fronted games behave. Do not add Job Object process-tree
  tracking unless asked.

## Phase 5 notes (the Steam-style UI)

- **Uniform tiles are not `setUniformItemSizes`.** That flag is still off, and must stay off —
  the Phase 2 trap is unchanged. Tiles are identical because `CoverDelegate.sizeHint` returns one
  size, which is a different mechanism entirely.
- **Cropping only suits portrait art.** `_crop_to_fill` on a landscape image throws away most of
  it: Aimlabs' wide logo came out as three enormous letters filling the tile. Anything wider than
  `ui_rules.COVER_CROP_MAX_ASPECT` is instead scaled whole onto the game's accent panel
  (`_fit_on_panel`). Steam header images and logos both land in that branch.
- **The old square-canvas icon fit still exists** in `icons.py` and is still right for exe icons.
  The grid no longer uses it; identical 2:3 tiles solve the row-alignment problem it existed for.
- **A generated banner must not repeat the name.** The banner for an art-less game is built from
  its placeholder, and the placeholder contains the title — so the detail page showed the name
  twice, once blurred. `cover(..., with_name=False)` exists for exactly this, and a game with no
  art at all now gets a plain accent wash rather than a blurred, boxy exe icon.
- **Size the detail cover from the banner's height, not a fixed width.** A fixed 200 px width
  implied a 300 px tall cover in a 300 px banner, so the guard skipped it and the cover silently
  never drew. Found by rendering, not by reading.
- **The banner needs two scrims.** A vertical one alone left white text on Counter-Strike's
  near-white diagonal; a left-to-right scrim under the title guarantees contrast regardless of art.
- **`config.json` is now shared** between scan settings and UI preferences, so everything that
  writes it must merge. `config_io.save_config` does (it was `discovery.save_config` until
  Phase 46), and `scanner.py --write-config` goes through it. Rewriting the file from a fixed set of keys would silently delete the other half.
- **Fixed in passing:** `scanner.py` built a fresh three-key config and dropped `allow_network`
  and `enable_xbox`, so the CLI silently ignored both and produced a different catalogue than the
  GUI. It now starts from the loaded config and layers CLI overrides on top.

## Phase 12 notes (SteamGridDB heroes in the banner cycle — the only approved item)

- **Measure who benefits before building an optional extra.** Five games in this library
  qualify (no Steam screenshots, no hand-picked banner) and *all five are hidden* — 3DMark
  Demo plus the four tools. The feature is correct and future-proof for non-Steam games, but
  it changed nothing visible on the day it shipped, and that was reported rather than glossed.
- **Fortnite is the one real candidate and is excluded by design**, because the user chose its
  banner in Phase 9 and a chosen banner never cycles. Proven end to end by lifting that
  override *temporarily* in a test that snapshots and restores the record: name resolved to
  SteamGridDB game 36136, four heroes downloaded, five frames, five dots.
- **The same 0.85 gate as the Steam name search** (`rules.SGDB_MATCH_RATIO` is literally
  `STEAM_SEARCH_MATCH_RATIO`). A wrong match here paints another game's art across the banner.
- **Name→SteamGridDB-id lookups are cached, misses included** (`cache/sgdb_names.json`), so a
  game that is simply not there is not searched for on every page open. "3DMark Demo" is
  already cached as a miss.
- Heroes are only sought when Steam supplied no screenshots, so games with a Steam record
  never pay for a lookup. Nothing here writes to `overrides.json`.

## Phase 11 notes (the cycling banner)

- **Two navigations in one rectangle was the trap, and it was avoided by moving one out.**
  The prev/next *game* arrows used to sit in the banner's corners. The dots that move between
  a game's *images* now live inside the banner, so the game arrows became labelled buttons on
  their own row underneath. Distinguishing two sets of arrows by styling alone would still
  have been a guess.
- **That row split was forced by rendering it.** Appending the two buttons to the existing
  action row squeezed every button until its text clipped — "Play" rendered as "Pl". Only
  visible in a screenshot.
- **Frame 0 is always whatever the banner would otherwise be**; screenshots are appended as
  their full-size downloads land, so the cycle grows instead of waiting for a complete set.
  Capped by `ui_rules.BANNER_CYCLE_MAX_FRAMES` because each frame is a real download.
- **A hand-picked banner never cycles, and gains no frames at all.** `add_frame` refuses when
  `cycling_allowed` is false, so no dots appear — dots would invite the user to cycle away
  from the image they deliberately chose.
- **The timer stops dead when the page is not visible** (`hideEvent`) and while the mouse is
  over the banner. Reduce animations stops auto-advance but keeps the dots working as manual
  navigation.
- **The next frame is built before the fade starts**, so the incoming image never appears
  half-drawn. Scrims and the title are painted *after* the crossfade, so the title stays
  legible through the blend.

## Phase 10 notes (the filled-in detail page)

- **Full records live one file per game**, `cache/steam_details/<appid>.json`, because each is
  17-29 KB and the shared `steam_web.json` is read by every scan. Only the game whose page you
  open is ever parsed. 20 records is about 500 KB.
- **Old cache entries upgrade on the next scan, not lazily.** Records written before the
  widening have no `has_details` key; the scan re-fetches exactly those, once. That was the
  choice over per-game lazy fetching so opening a page never waits on the network — the one
  scan cost ~20s and every scan after is 1.6s with zero requests. Delisted apps are recorded
  with `has_details: False` so they are not retried forever.
- **Strip markup, but do not replace every tag with a space.** Steam's fields carry `<strong>`
  and `<br>` inline; blanket-replacing turned "English<strong>*</strong>, French" into
  "English * , French". Break-like tags become a space, everything else is removed, then
  whitespace collapses and spaces before punctuation are dropped.
- **Full controller support has two independent signals**: the top-level `controller_support`
  field, and a "Full controller support" entry in `categories`. Silent Hill 2 and Hole Is Mine
  have both; Counter-Strike 2 has neither. Check both.
- **The screenshot URLs are literal values from the record.** Nothing is derived, so the rule
  about never constructing hashed asset paths is intact.
- **A QThread still running when its owner is destroyed aborts the process.** The screenshot
  fetchers did exactly that: tests printed their results and then exited non-zero.
  `DetailPage.stop_downloads()` is called from `MainWindow.closeEvent`. Any future worker needs
  the same.
- **The empty state is the normal state for a third of this library.** No appid means no
  description, no genres and no screenshots, ever. Every block is added only when it has
  content, so those pages show art, actions and a short facts list and look deliberate.

## Phase 9 notes (two artwork slots, and a data-safety lesson)

- **A game has two independent slots**, `ROLE_COVER` and `ROLE_BANNER` in `models.py`. Every
  action in `ui_cover_actions` takes a role and writes exactly one override key
  (`SLOT_KEY[role]`). Setting or clearing one must never read or alter the other; the tests
  assert both directions.
- **The role decides which image is fetched**, not which search runs. Steam's storefront search
  returns *games*, so the role is stamped on the candidate afterwards and picks the capsule or
  the hero at download time. SteamGridDB genuinely has two endpoints, so its grids feed the
  cover and its heroes feed the banner, including the picker thumbnails.
- **Overrides written before this phase keep working unchanged** — the `cover` and `banner`
  keys are the same ones. The old `appid` override key is no longer written or cleared by
  artwork actions; `GameView.matched_appid` still reads it for backwards compatibility.

- **A test destroyed real user data, twice.** It read the current `cover_source`, assumed it was
  auto-detected, overwrote it, then "restored" the wrong value — and a later run crashed before
  its cleanup, leaving a game pointing at a deleted temp file. **Any test that writes
  `overrides.json` must pick a game with no customisation of its own, deep-copy that game's
  whole record first, and restore it in a `finally`.** Never treat the value you happen to read
  as a baseline: the user has been using this launcher between sessions.
- **Do not hardcode the number of games in a test.** The user installs things; the count went
  from 24 to 25 mid-phase and broke two suites. Derive the baseline in the same run.
- **Do not use the user's most-customised game as the subject of a try-this list.** The Phase 9
  list told him to test "Remove" on Silent Hill 2, which cleared the SteamGridDB art he had
  chosen for it. Pick a plain game for destructive steps, or say plainly that the step will
  discard a customisation.

## Two bugs reported from real use, after Phase 9

- **A searched appid must never hide a game.** `GameView.is_non_game` used to trust Steam's
  `app_type` no matter where the appid came from. For a folder game the appid is a *name-match
  guess*, and one wrong guess made a game the user had just installed vanish from the grid
  unless "Show demos & tools" was ticked. Now the type is recorded and shown but only hides
  entries whose appid came from a launcher manifest (`rules.APPID_SOURCE_SEARCH` marks the
  guesses). A demo the user really did install can still be hidden by hand.
- **A blanket `QWidget { color: ... }` beats Qt's disabled palette.** "Remove cover" was
  correctly unclickable but looked identical to the live entries, so it read as broken rather
  than unavailable. `QMenu::item:disabled` now sets `ui_rules.COLOR_DISABLED` explicitly.
  Anything else that relies on Qt's automatic disabled styling needs the same treatment —
  check by rendering the widget, not by reading the stylesheet.

## Windows integration, and games that leave (after Phase 12)

Three things the user asked for once the launcher was in daily use.

- **The taskbar icon needs an AppUserModelID, not just an icon.** The app never called
  `setWindowIcon` at all, and even with one it would still have shown Python's logo: Windows
  groups taskbar buttons by the launching exe unless the process claims its own identity.
  `launcher.claim_taskbar_identity()` calls `SetCurrentProcessExplicitAppUserModelID` with
  `Andrei.GameLauncher` **before `QApplication` exists** — after a window is created it has no
  effect. `MainWindow` sets the icon on itself too, because a window built before the
  application icon is applied keeps the default. Verified by reading the id back
  (`GetCurrentProcessExplicitAppUserModelID` → hr=0), by `WM_GETICON` returning real handles,
  and by photographing the taskbar and magnifying the button.
- **Windows Search indexes the Start Menu, not the Desktop.** A desktop shortcut alone makes
  an app unfindable. Shortcuts now exist in both places, normal and TV, all four pointing at
  the venv's `pythonw.exe` with `launcher.ico,0`; `Get-StartApps` lists them. They hold
  absolute paths, so moving the project breaks all four.
- **An AppUserModelID is half a mechanism, and half of it is worse than none.** With the
  process claiming `Andrei.GameLauncher` but no shortcut *declaring* it, "Pin to taskbar" had
  nothing to resolve the id to. Windows fell back to the exe that started the process, so the
  pin became **"Python", running `pythonw.exe` with no arguments, which opens nothing** — the
  user reported exactly that. The running button looked perfect the whole time, which is why
  photographing the taskbar was not enough to catch it. Both halves are now written by
  `taskbar.py`:
  - Shortcuts are built through `IShellLink` + `IPropertyStore`, stamping
    `System.AppUserModel.ID` **before the file is saved**, so a .lnk is never on disk in the
    state that produces the Python pin. `WScript.Shell` cannot do this at all — it has no way
    to reach a property store — so the PowerShell script that made the first set of shortcuts
    could never have worked.
  - The live window also gets `RelaunchCommand`, `RelaunchDisplayNameResource` and
    `RelaunchIconResource`, so pinning works, and the jump list is headed correctly, even if
    the shortcuts are missing. Set from `showEvent`, because the handle must exist first.
  - **Normal and TV have different ids** (`…GameLauncher` / `…GameLauncher.TV`). One id on two
    shortcuts leaves Windows two pin candidates and no way to choose, so pinning "Game
    Launcher" could hand back the fullscreen TV one.
  - The id follows the **shortcut used to start the app**, from `--tv` in argv — not the mode
    it is currently in. Switching to TV inside the normal window must still pin the normal
    shortcut, and there is a test for it.
  - `SHChangeNotify` is fired per shortcut so Explorer re-reads them without a sign-out. Use
    `SHCNF_PATHW` (0x5); `shellcon.SHCNF_PATH` is the ANSI form and pywin32 demands bytes.
  - Verified by reading all four properties back off the live window of an instance started
    from the real Desktop shortcut, not from a test harness.
- **A game deleted from disk disappears by itself.** Every provider already refuses to emit an
  entry whose install directory is missing, so a rescan could never re-add one — but the
  window opens on the *last saved catalog*, so a game deleted since the last scan still had a
  tile that could not launch. `catalog_io.prune_missing` now drops those at startup.
  - It runs **in memory only**. Nothing is written, `catalog.json` keeps the stale record
    until the next scan rewrites it, and the check therefore re-runs every start — a game on
    a drive that was merely unplugged comes back on its own when the drive does.
  - **Overrides are deliberately kept.** Playtime, chosen artwork and a custom name survive an
    uninstall, so reinstalling into the same folder restores all of it. The identity key is
    the install path, which is what makes that work.
  - An exe entry is judged by the exe **the user picked**, if they picked one — judging the
    detected one would drop a game they had already pointed somewhere valid. Loose exes are
    judged by the exe too, since their `install_dir` is the scan root and never missing.
  - The notice re-asserts itself once. The status bar said "Removed 1 game…" for about
    50 ms before the controller announcement replaced it; it now reposts when the bar next
    falls silent. Anything else added to that bar at startup will race the same way.
- **Tests must not be pinned to one game.** Deleting Hole Is Mine broke two suites: one
  asserted it was visible, another compared the grid against the raw catalog count. Both now
  assert the property under test — "no game with a guessed appid is hidden", "nothing kept is
  missing from disk" — which made the first cover eleven games instead of one.

## Back to library sits on the banner (reported from use)

Asked for as "it feels more natural there", and it does: the one control that is about
*leaving* the page rather than about the game now floats over the banner's top-left corner
instead of sharing a row with Previous/Next game.

- It is a child of the `Banner`, positioned in `_place_overlay` rather than by a layout: a
  layout inside the banner would reserve space in it, and the banner paints edge to edge.
- **`#Nav` is the style for controls that sit on artwork** -- a dark translucent plate --
  and the banner's existing scrims mean the label stays readable over a bright sky.
- **`Banner` gained a real `apply_metrics`.** The overlay has to be repositioned when the
  scale changes, and the call landed in `DetailPage.apply_metrics` first, where
  `_place_overlay` does not exist -- every TV-mode toggle would have raised AttributeError.
  Caught by rendering the TV path rather than by reading it.

## The facts row is two columns (reported from use)

Asked for as "details on the left, recent sessions on the right, screenshots below". It
works, and the thing that decided the design was the install path.

- **A path is the one value that cannot wrap.** No spaces to break at, so in a narrow
  column Qt clips the tail rather than wrapping it -- and it does so however the size
  policy is set. `Ignored` plus `setHeightForWidth(True)` both failed; QGridLayout's
  height-for-width support is not up to it.
- So **any value longer than `ui_rules.DETAIL_WIDE_VALUE_CHARS` gets its own full-width
  line beneath the two columns**, which in practice means Runs and nothing else. Simpler
  than fighting the layout, and it reads better than a path wrapped three times.
- **The right column disappears entirely when a game has no sessions** -- every URI game,
  and any exe game not yet played -- and the facts take the full width again, so the page
  never shows a conspicuous empty half.

## The public repository (24 October 2026)

**The user's ask**: the whole source on GitHub, not just the installers, with nothing private in it (the
SteamGridDB key, "the conversation with Claude"). **Step 0 measured**, read only: the private repository
`GreenYRO/game-launcher` holds only `master`, the launcher before the thesis; `licenta` (137 commits, 107
tags) had never been pushed; until Phase 69 `config.json` (18 commits, 15 holding a SteamGridDB key -- the
one replaced on 10 October; the current key in no commit) and `overrides.json` (32 commits: playtime, the
game list, paths with the Windows user name) were tracked, and every commit carries the Gmail address, so
the existing repository cannot be made public; `BAZA_DE_DATE.md` §17 had planned a fresh export. In the
tree: `.claude/settings.local.json` and `CLAUDE.md` (the tool's files; CLAUDE.md speaks about the user),
`docs/explicatii/` (16 explanations written for him), 32 Steam hero images under the design handoff, the
word "repack" on 21 lines of 11 files outside CLAUDE.md, `C:\Users\andre` in 7 files; no key, no address,
no account id in any tracked file (the only SteamID-shaped number is Steam's base constant).

**The user's decisions**: a new public repository, `GreenYRO/game-launcher-source` (not a rename of the
private one: `origin` here would then point at the public one, and a habitual push would publish this
history); `.claude`, `CLAUDE.md`, `docs/explicatii` and the artwork left out, `docs/ISTORIC.md` kept (23
suites read it through `sources.build_log()`, and it is the record of the method); "repack" reworded
first; the MIT licence.

**Built**: `.gitattributes` marks the four paths `export-ignore`, so `git archive` leaves them out and
anyone can read what is missing and why; `packaging/export_public.py` (HEAD only, uncommitted changes
refused; the archive; a scan of every file for the current key, every key an old committed config.json
held, every address this repository has committed under, any Steam account id but the base constant;
a `data` folder, an excluded path or a missing README or LICENSE refused; the sibling folder
`../game-launcher-source` as a repository of its own, a clone of the published one when it exists; one
commit per export under the no-reply address; the publish command printed, never run; `--check`,
`--verify`); `README.md` (the trailer and the screenshots served from the friends' repository, so no
media enters this one; Romanian, then English) and `LICENSE`. Proven on a clone in the session's VM:
287 files of 334, exactly the four paths missing; a second run "nothing changed"; a dirty tree refused;
a planted address, a planted account id, the old key from the history and a planted current key each
refused by file name; `--verify` on a `file://` URL matching file for file.

**The wording**: 15 single-line replacements in 11 files ("packaged builds" and "Steam emulators" for
"repacks"), comments, docstrings and docs only, plus suite 80's planted name; `"repack"` stays in
`NAME_STRIP_TOKENS` (a word the scanner removes from folder names) and in five lines of the sections
suite 91 guards word for word (Phases 27, 29, 30, 76, 80); CLAUDE.md's two mentions are not exported.
The emulators' names stay where they are functional (`rules.py`, `saves.py`): a knowing reader can still
tell the library's nature; the rewording makes the documents less explicit, it hides nothing.

**Published on 24 October** on the user's word ("please do it yourself"): the first snapshot, "Source
as of 1.2.10", pushed from the session's container; the friends' page had been refreshed the same night
(its commit 2c2022b: the 1.2.10 trailer, the GIF, seven screenshots), and the README here points at them.

## Phase 107 notes (release 1.2.10: the missing covers in one go, and What's new)

The user's word (23 October), in the message that held Phase 106's explain-back: "let's also publish those changes
to the public github repository". Tag `before-phase-107` on 7153580 (that explain-back's commit).

- **What the friends get**: Phase 105 -- Settings' Missing covers and Fill missing covers..., with their own
  SteamGridDB key, a backup first; and the fix that keeps a "slow down" from being remembered as "not on SteamGridDB";
  Phase 106 -- What's new once on the first start after an update, About's What's new, Updates' "See what's new in".
  **No schema change** (still version 8, the last script 008): a friend's library is not upgraded.
- **The notes first**, as the rule since Phase 106 says: `docs/release-notes/1.2.10.md`, Romanian under its heading
  then English, the friends' words -- what What's new shows them is its English, and the GitHub page is the file.
  `build.check_notes()` passed before the build ran.
- **CLAUDE.md first**: rows 101, 102 and 104 condensed (115,543 -> 113,995 bytes), row 101 keeping "**done**" and
  `logic/alerts.py` (suite 101).
- **The documents**: `shared/version.py` 1.2.10 and its history line; CITESTE-MA "Versiunea 1.2.10." (110 lines;
  Phases 105-106 had put their sentences in); DISTRIBUTIE §3 (the version, the log line, 1.2.10 in the list), §5 (the
  check's What's new step, its figure), §7's step 5; CLAUDE.md's version paragraph. Suite 104 asked for 1.2.9
  exactly: it reads the version at its publish commit (311c3a2). `tests/try_whats_new.py`'s sample newer version is
  the next one after whatever this is, so it never stops being newer.
- **`check_installer.py`**: `meets_whats_new` on the friend's path -- "What's new in 1.2.10" up first and the one
  question not yet; the version seen still 1.2.9 while it is open; its title and Close read off the screen through UI
  Automation; closed by its window, 1.2.10 written and the notes gone -- then `answer_offer` as before. Section 1's
  bundled notes check (Phase 106) ran for the first time on a build.
- **The build** (23 October): 32 s, 273 files (1.2.9's 268 and the five notes files), 72,693,456 bytes, sha256
  `b43f683e...aaa51c69`, stamped 1.2.10. The 1.2.9 installer kept aside first (sha256 `c5e17a96...c876083d`).
- **The first check run stopped half way, in the check**: section 6 printed GitHub's kept answer, which holds the
  release's notes since Phase 106 -- 1.2.9's, with Romanian letters -- to output in the console's code page
  (cp1252), and the print raised; the cleanup then raised again opening a test Run key root that was not there. It
  left its own Add/Remove entry and fake profile behind (pointing into `installer_test_nivathge`), removed after
  looking at where it pointed. The check's output is UTF-8 now, the answer is printed with its notes as a length, and
  the cleanup says when there is no root to tidy.
- **`check_installer.py --over` the real 1.2.9: 75/75** -- section 1's notes check, section 8's four What's new
  checks; a library at schema 8 with 11 game rows, "the same schema version, 8: nothing to upgrade", all nine views
  answering, the games and settings as 1.2.9 left them but the version seen, the planted alert once and silent the
  second time; GitHub asked once for real, answering 1.2.9: nothing newer than 1.2.10 offered.
- **Before the publish**: the key (text and UTF-16) and the e-mail address in none of the 273 files, nor in
  payload.zip's 273 members, nor in Setup.exe; no data file among them; no Add/Remove entry left.
- `tests/phase107_tests.py`: the version, newer than 1.2.9 as a number; its notes ready, their English what What's
  new will show, the Romanian first; 1.2.9's schema (8) and this one's the same, no script changed;
  check_installer's What's new step before the one question, and the bundled notes; CITESTE-MA, DISTRIBUTIE, the
  explanation page, CLAUDE.md and its size; the layers; no network; the real data untouched. 21/21.
- **The release suites on this code** (77, 79, 80, 82, 85, 88-91, 95-97, 99-107 and the import and layer nets): all
  green but two. Suite 99's pad walk to the genre pill failed once in the loop and passed 82/82 alone. **Suite 103
  failed alone too, and it was the suite's**: written when the user's copy had no game left behind, it planted two
  and pressed down a fixed number of times to reach their answers -- and his library has its own now (BloodBorne and
  Cinderia on 23 October, as the rule says they should be), so the row had a second line, the walk went past the first,
  Still playing landed on one of his, and section 4 met a planted game never marked. The copy's own Playing games are
  answered "Still playing" a moment before the planting now, so the row is the planted ones alone, and the walk stops
  at the first answers: 72/72.
- **Published on 23 October** on the user's word ("let's also publish those changes to the public github
  repository"), at once, as 1.2.6 and 1.2.7 were: `gh release create v1.2.10 dist/GameLauncher-Setup.exe --repo
  GreenYRO/game-launcher-releases --target main --title 1.2.10 --notes-file docs/release-notes/1.2.10.md --latest` at
  23:06 (20:06:08 UTC) -- the first release whose page is the notes file. Read back through `updates.fetch`: 1.2.10,
  newer than 1.2.9 and not newer than itself; the page's body equal to the file; GitHub's asset digest the local
  file's sha256 (`b43f683e...aaa51c69`, 72,693,456 bytes). The 1.2.10 installer kept aside for the next `--over`. The
  friends' 1.2.9 copies will say 1.2.10 is out within a day, and show "What's new in 1.2.10" once after the update.
- **The explain-back held the same day**: "1.2.10 gives my friends the covers button and what's new". Filled in:
  the first start after they update shows "What's new in 1.2.10" once -- its notes are the GitHub page, made from
  the file written first -- and the tray question only after it; the covers button needs their own SteamGridDB key
  and takes a backup first; the "slow down" fix goes with it; their library is not changed (still version 8); their
  launchers say 1.2.10 is out within a day, and they install it themselves.

## Phase 106 notes (What's new: an update explains itself, once, on the first start after it)

The user's brief (22 October), after Phase 105's explain-back. Tag `before-phase-106` on 67ce267.

- **Step 0.** The start's order: the first-run question queued at once (a first run only), the tray offer a second
  after the window appears (retried every 2 s for a minute while another dialog is up), then `begin()` -- whose last
  steps wrote `version_seen` at once, at a `--background` start too, so a start hidden in the tray would have spent an
  update's first start silently. The published notes, fetched through the update check's own client: **two read-only
  requests where the brief said one** -- the first answered, and the script crashed printing a Romanian letter to the
  console before it saved; the second saved first. 1.2.9's body 4,760 characters, 1.2.6-1.2.8's 2,023-3,830: no
  headings, lists or links -- paragraphs with bold phrases and two code spans, the languages under the bold labels
  **Română** and **English** with a `---` between; each equal to the file it was published from. Three findings, all
  taken ("yes to all three"): the update check did not keep a release's notes, so "See what's new" needed them kept;
  every test copy held his real `version_seen`, so a release raising the version would have stood every suite's
  window on the dialog; his source launcher shows a new version's notes once too.
- **First, CLAUDE.md**: rows 99 and 100 condensed (115,731 -> 113,584 bytes), row 99 keeping its three "N of 3
  done" (suite 99).
- **`docs/release-notes/`**: 1.2.6.md to 1.2.9.md, the published bodies with one change -- the two labels made
  `## Română` and `## English`, the rule between them dropped -- each proven by putting the labels and the rule back
  and getting the published body exactly. Romanian first, as published and as his rule for the notes.
- **`logic/whats_new.py`**: `notes_dir` (resource_dir's docs/release-notes: the project's from source, the bundle's
  installed), `read`, `section` (the text under a heading or under the published labels, up to the next; a text in
  one language whole), `ready` (the file, both headings, words under each), `due` (a version seen, and another one;
  never a first run's), `english`. `rules.RELEASE_NOTES_DIR`, `RELEASE_NOTES_HEADINGS`, `WHATS_NEW_DELAY_MS`,
  `_RETRY_MS`, `_TRIES`. **`packaging/build.py`** `check_notes()`, the first thing `main()` does, before anything is
  deleted; `app.spec` bundles the folder at the same place; `check_installer.py` checks this version's file in the
  build byte for byte.
- **The window**: `_whats_new` worked out with the config; `showEvent` queues `show_whats_new` a second after the
  window appears and marks the offer queued; `_note_version` writes nothing when the notes are due; `show_whats_new`
  waits for a window to be seen (not hidden, minimised or in the tray, no dialog up -- every 2 s, a minute, then the
  next shown start), shows the dialog, then writes `version_seen` and queues the offer a second later. The tray's
  tooltip: "Game Launcher -- updated to 1.2.10; open it to see what's new" until then (`ui_tray.tooltip`'s `updated`).
  **`presentation/ui_whats_new.py`**: `QTextBrowser.setMarkdown`, links opened in the browser only when they are web
  pages (`open_link`), Close. The pad (`_drive_dialog`): up and down scroll the words and at either end move on, A
  presses Close. **A text box's Tab steps between its links first** -- Qt's QTextBrowser.focusNextPrevChild -- so
  up at the top stopped on a link; keyboard link-stepping is off (`TextSelectableByMouse | LinksAccessibleByMouse`),
  links stay the mouse's, and Tab leaves the words.
- **Settings, About**: What's new beside the version (off, with a word, when a copy carries no notes); Updates gains
  "See what's new in X" when the kept answer is newer and has notes. **`web/updates.py`**: `Answer.notes`, the
  release's `body`, kept in update_check.json and read back ("" from an answer kept before).
- **`tests/test_sandbox.py`**: every copy's `version_seen` is this version (read from shared/version.py as text, as
  the sandbox may load nothing of the project's before `start()`); suite 99 removes it, suite 106 plants 1.2.8.
- **Rendered and looked at**: the dialog over the window at 1.09 s with 1.2.8 still the version seen, the offer at
  2.81 s with 1.2.9 written; About with its button.
- **Documents**: CLAUDE.md (the row, the layout, the release rule in the version paragraph, the test copies' lesson),
  DISTRIBUTIE (§3's checklist starts with the notes; §9's "Ce aduce o versiune"), CITESTE-MA (See what's new and
  What's new in the update paragraph; the install paragraph a line shorter, still 110), `docs/explicatii/faza-106.md`.
- `tests/phase106_tests.py`: the files and their headings, `section` on the three forms, `ready` and the build's
  refusal without building, `due`; the window's order, the version seen before and after, the offer after and never
  stacked, nothing the next time, a hidden window waiting; the tray start and its tooltip; the dialog's Markdown,
  links, the pad; About and Updates from a planted answer; the copies; the documents. 47/47 -- after the first
  run's one failure of its own: up at the top of the notes stopped on a link (above).
- **Full run: 3409 of 3410 suite checks**, every net clean. The one was suite 79's "the answer kept ... and
  nothing else", which named the kept answer's five keys: it holds the release's notes now, as this phase meant --
  the check asks for six, the notes among them; 63/63 alone.
- **The click-through's tool**: `tests/try_whats_new.py` -- a throwaway copy whose version seen is 1.2.8 (the brief
  said 1.2.9, but this copy is still 1.2.9 itself: with 1.2.9 seen nothing is due), the tray question planted as not
  asked, a sample newer answer planted ("1.2.10", its notes saying they are a sample) with the Updates row shown as an
  installed copy's, the network refused. Tried without a person: "What's new in 1.2.9", then "Keep Game Launcher
  running?"; About's What's new on; "See what's new in 1.2.10"; the version seen 1.2.9 after; "unchanged".
- **Tried and explained, 23 October**: "yep so basically this gives up a new window that says 'what's new' in the
  launcher" -- and, in the same message, "let's also publish those changes" (Phase 107). Filled in: it shows once,
  on the first start after an update, a second after the window appears; the version counts as seen only once it is
  closed, so a start hidden in the tray, or one that ends first, keeps it for the next one; the tray question waits
  a second after it, never on top; About's What's new any time, and Updates' "See what's new in" before an update;
  the words come from docs/release-notes/<version>.md -- written first for every release, the GitHub page made from
  it, and a build without it refused.

## Phase 105 notes (missing covers filled in one go, from SteamGridDB, with the user's key)

The user's brief (22 October), after Phase 104's explain-back. Tag `before-phase-105` on 80153a8.

- **Step 0** (a copy of the library, read only, no network): 32 installed entries, 4 without a cover -- DS4,
  Eden, Lightroom Classic and Nvpi, folder entries he marked as tools, out of the grid -- so every game the grid
  shows has one, and on his library the row says "Every game has a cover"; the button is for the friends'. The name
  cache: 17 names, 7 hits and 10 misses (DS4's and Nvpi's 71 and 60 days old, past the 7 a miss is trusted). The
  logs from 30 September: 216 SteamGridDB lines (33 searches, 150 hero lists, 27 images), not one HTTP error, no
  429; no Retry-After ever seen, because nothing read a response's headers. **The find**: a 429 was logged and
  returned as no answer, and a name search that met one cached the name as a miss for 7 days -- so a batch slowed
  down would have marked every game it was asking about as "not on SteamGridDB". Shown on the old code, loaded
  from git as a module of its own: a 429 cached `hollowknight` as a miss, and Test said "That key was refused";
  now nothing is cached, and Test says SteamGridDB asked to slow down. The user's go: "lets continue - and do what
  seems best there" -- so the list is the grid's games: not hidden, not a tool or demo, no cover set by hand.
- **`web/steamgriddb.py`** tells three answers apart: a match, a miss (an answer with nothing past the 0.85 gate,
  cached as before), and no answer -- refused (401), unreachable, or asked to slow down (429, its Retry-After read
  as seconds or a date) -- never cached. `strict=True` raises it (`RateLimited`, `NoAnswer`); every other caller
  gets the empty answer it always had. `known_game_id` (the cache's word without a request), `cover_url`,
  `cover_on_disk` and `download_cover` (the file `fetch_for` keeps a cover in). The error body read that used to be
  `except Exception: pass` now says so at debug.
- **`logic/fill_covers.py`**: `missing(views)`, `row_words`, `run` (a plain loop, no Qt: the cache first, a
  search, the tall grid, the image; `pause` between requests, `wait` for a 429 -- answering False on Cancel --
  `stopped` before each game), `summary`. **`adapters/cover_fill_worker.py`** runs it on a QThread, each step a
  signal; **`presentation/ui_fill_covers.py`** the dialog; the window is its host (`missing_covers`,
  `fill_missing_covers`, `scan_running`, `fill_backup`, `cover_found`, `track_fill`), holds a scan back in
  `start_scan` while `_filling` and runs it after, redraws the grid at most once a second
  (`FILL_COVERS_REFRESH_MS`) and stops the worker on Quit. `backups.snapshot_or_newest`: a snapshot, or the newest
  when nothing changed since it (it holds the library already) -- None only when neither, and then nothing is
  looked up. `GameView.cover_chosen`. Settings' row reads the key field and the switch as the window has them.
- **Rendered and looked at**: the row, the dialog before, running and after, the grid after (the toast "3 covers
  filled from SteamGridDB"). The first picture cut the fifth name in half -- a row's height guessed at 26 px; the
  list is measured from its first row once styled now -- and showed a "--" where a dash belongs.
- `tests/phase105_tests.py` on a fake SteamGridDB in the suite's own process (searches, tall grids, the image
  server, 429s queued with or without Retry-After, down, refusing; anything else refused and counted): the three
  answers, Test's words, the list, the row's words; the batch with its waits recorded -- the gate, 9 requests and 8
  gaps for four games, a second run costing none, the 429 paths, Cancel, unreachable, a refused key, the words;
  the window on a copy with planted games -- the row and its button, the dialog driven, the backup named, the covers
  in the cover slot of the copy's cache, a banner untouched, a hand-set cover kept, the grid redrawn, a scan held
  and run after, Escape and a scan under way, no backup no lookup, the restore; the key never in the log; the
  user's own SteamGridDB cache byte for byte. Its first run: 40 of 60 -- the suite's test picture compressed below
  the 4,096-byte floor, so every download was rightly refused as too small; a noisier picture. 63/63.
- **Full run: 3359 of 3361 suite checks**, every net but the scanner's clean. Suite 59's "overrides.json,
  config.json and catalog.json are byte for byte unchanged" named library.db: the user's own launcher, in the tray,
  ran its half-hourly tick at 20:47:08 and landed a price observation and Steam's readings into his library while
  the suite compared it; 19/19 alone. Suite 65's stand-in for the Settings dialog (`Recorder`) took no `covers`
  argument -- given one, as it was given `focus` in Phase 77; 21/21. **The scanner net met his machine**, not this
  phase (no provider changed): SnowRunner renamed SnowRunner Research and Restore, Khazan gone, and the eight Steam
  games' folders written in capitals -- a packaged build's installer pointed HKCU's `SteamPath` at its own
  `Sources\Bin\Steam`, which does not exist, so the provider finds Steam through HKLM: the same folder, its
  name's case as Windows keeps it. A Steam game is known by its appid, so no record moved. The run saved anew (the
  old one kept as `tests/baseline/scanner-until-2026-10-22.json`), 0 differences.
- **The click-through's tool**: `tests/try_fill_covers.py` -- the launcher on a throwaway copy of his library, its
  own data folder and lock (his launcher in the tray undisturbed), network lookups on as his are, no scan at the
  start, five planted games without a cover leading the grid (Hollow Knight, Celeste, Hades, Stardew Valley and
  Zzqx Planted Game, which nothing is like); at its end it says whether his real files are as they were. Tried
  without a click (no request): the row "5 games have no cover.", the button on, "unchanged".
- **The click-through, 22 October**, his, on the copy with the real SteamGridDB and his key: "it works, found 4 of
  5 covers and zzqx didn't match" -- Hollow Knight, Celeste, Hades and Stardew Valley found, Zzqx Planted Game
  under the gate, as planted. Checked read only after: his own SteamGridDB cache untouched (the names file still
  from 18:07, the 71 pictures), the copy and its covers gone with it.
- **The explain-back held the same day**: he had a new Settings option that finds the missing covers in one go --
  the games without one, not hidden and not tools, looked up on SteamGridDB with his key; the covered games and the
  tools skipped; SteamGridDB slowing his key down waited out, its seconds or 30, then "try again later"; the undo a
  backup put back. Filled in: the undo is Restore... with the backup the last sentence names, taken just before
  (Import is the export zip's), or one cover removed from its game's menu; a cover he set himself is never
  replaced, which is why those are left out, and a name or a picture already known costs no request; a second
  "slow down", or a wait over 60 seconds, stops it, and nothing it was asking about is then remembered as "not on
  SteamGridDB" -- the fix step 0 found; the 85% name match is why Zzqx got no cover rather than a wrong one; Cancel
  lets the game under way finish.

## Phase 104 notes (release 1.2.9: price alerts, the session rating, Left behind and reports 10-11)

The user's brief (22 October), after Phase 103's explain-back. Tag `before-phase-104` on ac1496b.

- **What the friends get**: Phase 101 -- price alerts on the wishlist (Alert me under..., the Alerts chip, the
  balloon's click); Phase 102 -- How was it? after a session of 10 minutes or more (five stars, Skip, the card
  gone by itself after 20 s, once a game a day, never while a game runs, in the tray a balloon; the switch in
  Settings, After a game), late stars on a game's page for 14 days, report 10, the ratings in the anonymous export
  (format 3, stars and a day); its extension, the hours pill; Phase 103 -- Left behind in For you, the "since"
  line under a dated mark, report 11, the reports' hours worked out once. **A schema change**: version 7 to 8 at
  a friend's first start (`008_alerts_ratings_marks.sql`, additions only), a snapshot first.
- **The documents**: `shared/version.py` 1.2.9 and its history line; CITESTE-MA "Versiunea 1.2.9." (110 lines;
  Phases 101-103 had put their sentences in already); DISTRIBUTIE §3 (the version, the log line, 1.2.9 in the
  list), §5 (the check's two new steps and its figure), §7's step 5; CLAUDE.md's version paragraph. Suite 100
  asked for 1.2.8 exactly: it reads the version at its publish commit (176b287), and its log line follows
  `APP_VERSION`. No other suite pins it.
- **The build** (22 October): 31 s, 268 files (1.2.8's 267 and the script 008), 72,649,526 bytes, sha256
  `c5e17a96...c876083d`, stamped 1.2.9. The 1.2.8 installer kept aside first (sha256 `1550fbf2...f6545b45`, the
  file published on 19 October).
- **`check_installer.py` learnt 1.2.9.** In `shows_whats_new`, Settings' After a game row and its switch's
  name, "Ask how a session was", read with the Accent row (found on a sandbox window from source first). On the
  friend's path, `plant_alert`: in the library just upgraded, an account marked the friend's (123456789, its
  SteamID64 by the schema's own rule), a wishlist read holding one game (appid 9999901, a `steam_app` row without
  a record), one price of 29,99 EUR on 20 October and a target of 20,00 EUR; then, in the price hand-off where a
  scan leaves what it fetched for the window, a new price of 19,99 EUR, the network off in config.json. The next
  start lands it: "price alerts: 1 set off, 1 written to the log", the row (9999901, its moment, 'target', 1999),
  the words "under your 20,00 EUR target" -- not 'lowest', which needs three prices. The same price planted
  again lands as there already and sets nothing off: still one row. Dry-run first on a sandbox copy from source;
  suite 104 runs the check's own `plant_alert` through `prices.land` and `alerts.land` the same way.
- **Two runs found two things in the check, none in the program.** The first, 70 of 71: "the games row for
  row" compared `SELECT *`, and version 8 adds two columns to `game`; it compares 1.2.8's columns now, and a new
  check asks the two added ones to be empty in every row (the upgrade dates no mark). The second, 71 of 72: the
  same check held the settings too, and `version_seen`, written by 1.2.8's first run (Phase 99; 1.2.7 had no
  such key, so 1.2.8's run never met it), now rightly says 1.2.9; games and settings are two checks, the
  settings all as they were but that key, which must name this version.
- **`check_installer.py --over` the real 1.2.8: 73/73** -- twelve more than 1.2.8's 61: the After a game row
  at section 5's start and after the update; the library (schema 7, 10 game rows) brought to 8 with the snapshot
  holding 7, all nine views answering, the games row for row on 1.2.8's columns and the two new ones empty, the
  settings but the version seen; the planted alert, said, once, and the same price silent; no error. GitHub
  asked once for real, answering 1.2.8: nothing newer offered.
- **Before the draft**: the SteamGridDB key (as text and as UTF-16) and the user's e-mail address in none of the
  268 files, nor in payload.zip's 268 members, nor in Setup.exe; no config, library, overrides, catalogue or log
  among them.
- **The notes, in Romanian and English**, the rating question first -- the thing a friend meets first, after
  their next session -- with Skip, the card that goes by itself, how seldom it asks, the late stars and the switch
  named, and what reaches the anonymous export; then the price alerts, Left behind, the hours pill, the two
  reports, and that the library moves to version 8 after a backup copy.
- `tests/phase104_tests.py`: the version, newer than 1.2.8; 1.2.8's schema (7) against this one's (8, the one
  new script, additions only); check_installer's `--over` steps; the planted alert run on a copy here; CITESTE-MA,
  DISTRIBUTIE, the explanation page, CLAUDE.md and its size; the layers; no network; the real data untouched.
  23/23.
- **The release suites on this code**: 77 74/74, 79 63/63, 80 51/51, 82 55/55, 85 17/17, 88 10/10, 89 45/45,
  90 11/11, 91 51/51, 95 14/14, 96 91/91, 97 12/12, 100 18/18, 102 105/105, 103 72/72, 104 23/23; the import and
  layer nets clean. **Two failed, alone too, and each was its suite's, not the program's** (no program file
  changed in this phase). Suite 101's "nothing about a target in config.json" photographed the settings before
  its window had started, and a start on a new version writes `version_seen` (Phase 99): the sandbox copies the
  user's settings, which say 1.2.8 until his launcher restarts on this code. It photographs them after the start
  now: 77/77. Suite 99's "asked a second after the first paint" read its clock after `show()`, but the first
  paint happens inside it -- the first row's covers read from disk, 72 ms for twelve; the show 207-216 ms in three
  measurements, `begin()` 2 ms of it -- while the question's second is counted from the show event: 0.85-0.9 s
  against a floor of 0.9. Its clock reads before `show()` now: 1.1 s, 82/82. Found with a wrapper printing every
  `config_io.save_config` call and its caller, and a profile of the show.
- **Published on 22 October** on the user's word ("yes looks ok - publish it"), after reading the draft and its
  notes: `gh release create v1.2.9 dist/GameLauncher-Setup.exe --repo GreenYRO/game-launcher-releases --target
  main --title 1.2.9 --notes-file ... --draft` (the draft's address `.../untagged-d3fc158f496a65b10cbd`; GitHub's
  latest still 1.2.8 meanwhile), then `gh release edit v1.2.9 --draft=false --latest` at 20:05 (17:05:48 UTC).
  Read back through `updates.fetch`: 1.2.9, newer than 1.2.8 and not newer than itself; GitHub's asset digest is
  the local file's sha256 (`c5e17a96...c876083d`, 72,649,526 bytes). The 1.2.9 installer kept aside for the next
  `--over`. The friends' 1.2.8 copies will say 1.2.9 is out within a day; their first start on it brings their
  library to version 8 after a snapshot, and their next session of 10 minutes or more meets How was it?.
- **The explain-back held the same day**: he had that 1.2.9 brings the friends the price alerts, the ratings and
  Left behind, and brings their database to version 8 by adding new tables. Filled in: the hours pill and
  reports 10 and 11 go with it; the upgrade is a backup copy first, then one script that only adds -- the
  targets, the alert log and the ratings as tables, and two date columns on the games for when a mark was set
  and when it was last nudged -- deleting and changing nothing, in one transaction, so a refusal leaves the
  library as it was; the friends learn of it from their own update check within a day and install it
  themselves; the ratings stay on their PCs and reach the anonymous export only as stars and a day; and the
  release was tried on the real 1.2.8 first, a planted price alert included.

## Phase 103 notes (Left behind -- a nudge for games stopped without saying so; report 11, Finishing)

The user's brief (21 October): reports 2 and 4 rest on marks given by hand, late or never -- a game stopped in
August still says Playing; a nudge at the right moment makes the marks, and dated marks give the thesis how many
started games get finished and how long it takes. Tag `before-phase-103` on 67df963 (the Phase 102 extension's
explain-back). No schema change: version 8 laid `game.nudged_at` for this phase and has dated the marks since
Phase 101.

- **Step 0, on a copy, read only**: 3 games carry a mark -- 2 Playing (SILENT HILL Townfall, last session 22
  September 23:44, 28 days; The Witcher 3, 11 October, 9 days), 1 Dropped (The First Berserker Khazan, never
  played), none Finished -- and **all three are undated**, set before version 8; no nudge yet. At 30 days nothing
  is nudged on 21 October: Townfall from 22 October 23:44, The Witcher 3 from 10 November; at 45 days nothing until
  6 November. The Left behind row rendered as a concept under Tonight.
- **What step 0 changed**: the library keeps a game's current mark and the moment it was last set, not a history:
  "ever marked Playing" cannot be read for a game now Finished, so report 11 counts games by their mark; a game
  marked Playing with no counted session is judged on its newest date of play from anywhere, and one with none
  is never asked (unknown is not long ago); the time to Finished has censoring -- a game still Playing has no end
  yet -- so the median of the finished is set beside a Kaplan-Meier estimate that counts the still-playing as not
  yet; "hours at Finished" are today's hours (Steam's counter has no dates).
- **The user's go**: "lets continue", after the extension's explain-back.
- **Commit 1, the row and the page's line**:
  - `logic/recommend.left_behind` (no Qt, no SQL): a game marked Playing is left behind when nothing has been heard
    of it for LEFT_BEHIND_DAYS (30) -- its last counted session (the `sessions` rule), or with none its newest
    date of play (the launcher's, its store's, Steam's), and no mark set and no nudge answered in that time (a
    mark set lately is fresh: the brief's rule gained the mark's own date); the days shown are since the play;
    the longest left first, a tie by name, at most LEFT_BEHIND_GAMES (4). `LeftBehind.words`: "Left 45 days ago
    at 12h 38m", the hours v_hours' (the pill's own number).
  - `data_access/recommend.py`'s `left_behind` query: the installed, shown, not-tool games marked Playing (an
    uninstalled game has no page for the answers to act on), each with its last counted session, its dates of
    play, the mark's and the nudge's moments and its hours (v_hours worked out once); `parameters()` names
    `:playing`.
  - The store: `nudged_at` joins `MARK_FIELDS`, kept with the record as the mark's date is, read and written only
    at version 8. `ui_actions.still_playing` writes the moment and nothing else -- the mark stays Playing,
    undated as it was; Finished and Dropped go through `set_status`, which dates the mark.
  - For you: Left behind after Tonight -- its section, the rule's words, two cards a line (`FORYOU_LEFT_PER_LINE`:
    each carries three answers), each with its cover, name and words; a line of answers is one row for the pad,
    A gives the answer the ring is on, X the game's menu; the TV's hints `FORYOU_ANSWER` ("A Answer") while the
    ring is on one; the row away when nothing is left behind. No message and no balloon announce a nudge.
  - A game's page: "Finished since 21 Oct" under the switch when the mark is dated (`GameView.status_since`),
    nothing when it is not; a label of the picture's own, placed under the switch by hand (`_place_since`, again
    once the layout has settled), in the room between the Play row and the first card, so the Play row keeps its
    measured place (suite 57).
  - Renders: For you with two planted games left behind, at the desk; a game's page with a dated mark, at the
    desk and in TV mode. The For you suites (84, 87, 98) run as they will once Townfall is left behind
    (LEFT_BEHIND_DAYS lowered for the run): 87 and 98 green with the row there; 84's one timing check failed once
    at 53 ms (the ten reports, no change of this commit), 43 and 50 ms run again.
  - **The first full run started two of the user's games.** 3216 of 3240: suites 52, 57, 74 and 98's pad and
    ring checks failed together at about 03:13-03:16 (no launcher window in front), and in suite 74 -- X for a
    game's menu, then A for "What I paid..." -- the menu never opened, so A landed on the page's Play: its copy
    started Cinderia (03:15:32) and Silent Hill 2 (03:15:42), the real ones in C:\games. The user's own launcher,
    in the tray, saw them running and wrote an observed session of 1 minute for Cinderia into the real library at
    03:16:58 (Silent Hill 2's, under a minute, left nothing) -- which suite 77, running then, caught as the real
    library changed. Both games had closed when it was looked at; the session was left in place for the user to
    decide. **The repair**: a test copy never starts a game. test_sandbox names the copy's folder in the
    launcher's own variable (`rules.TEST_COPY_ENV`, as `STARTUP_TEST_KEY_ENV` names its Run key), and
    `launch_game` and `launch_elevated` refuse a start there as if it were made -- nothing to time, no dialog to
    hold a suite up -- writing it into the folder (`TEST_COPY_STARTS`), which `finish()` reports as a change: a
    slip of the pad now fails its suite by the game's name instead of starting it. No suite started a game on
    purpose (26 and 99 stand in for the start). Suite 103's section 5 proves it. Suite 83 asks every query a report
    is built from quoted in ANALIZA, and For you's queries join the reports' list as recommend.py loads: the Left
    behind query, which no report reads, moved to the page's own (`PAGE_QUERIES`). The six suites green alone:
    52 17/17, 57 59/59, 74 56/56, 83 70/70, 98 117/117, 103 39/39. The user's choice on the observed minute: "you don't have to remove it it's fine" -- left in his
    library.
  - **The second full run**: 3230 of 3243 -- the first guard refused every start in a test copy, and suites 28,
    92 and 93 start fake games of their own on purpose (pythonw or cmd, their folder made in the temp folder);
    the guard now lets a game start in a test copy only when its folder is in the temp folder, and refuses
    the user's games and every store's link (suite 103 asks both). Suite 57's real-data check met the user's
    own tick landing 15 prices at 03:39:42. Green alone: 28 19/19, 92 100/100, 93 80/80, 103 41/41; every net
    clean.

- **Commit 2, report 11 and the documents**:
  - **The time first.** The ten reports read 43-53 ms on the copy that night -- the nine about 47-48, a PC busy
    after its start before -- and report 11 had no room. Measured: the queries sum to 40 ms, and fifteen of them
    read v_hours, each working it out again from its tables (v_hours 1.65 ms alone, v_steam_time_mine 0.99 of it).
    Materializing every query's CTE had helped none but report 8 (Phase 102). The repair is the build's, not the
    queries': `Reports.worked_out_once` copies v_steam_time_mine and v_hours into temporary tables of the same
    name before the queries and drops them after -- SQLite looks in the temporary schema first, so every query's
    text stays exactly as ANALIZA quotes it and reads the copy, one moment's answer for the whole build; nothing
    reaches the library file, and a read-only connection (reports.py's) makes them as well. The ten 46.2 -> 24.0
    ms (read-only 45.9 -> 23.5), every query's answer the same; the eleven 24-25 ms.
  - Report 11, Finishing: `finishing` -- every game with a mark (not a tool, not set aside), its first and last
    counted session, the mark's and the nudge's moments, its other dates of play and Steam's last played (Left
    behind's rule reads them); the hours report 1's rows (a game the launcher starts with none: 0; another:
    unknown, never 0). The counts; the games left behind by For you's own rule, uncapped
    (`recommend.all_left_behind`, which `left_behind` caps); the completion rate, Finished over Finished and
    Dropped, a hint under REPORT_DECIDED_MIN (5) decided games; the time from the first session to a dated
    Finished mark, its median and range, beside `kaplan_meier_median` -- each still-Playing game censored at its
    days so far, a dated Dropped one at its days to the drop, the finishes before the censored at a tie; the
    hours at Finished and at Dropped as two medians. Its parts: the marks as bars and the undated counted; the
    Finished (days, or none for an undated mark), the not finished yet (censored, left behind or not), the
    Dropped. Nothing marked: said in words. **Found by rendering it**: a Finished mark planted before its game's
    first session read "(-3 to 10)" -- a mark set before the first counted session is now counted, never
    timed (`_to_mark`), and the sentence says how many were (suite 103 asks it).
  - The worked example (suite 103 and ANALIZA): six games on 10 September -- A and B finished 10 and 30 days
    after their first session, C finished undated, D dropped at 5 days, E Playing 40 days and left behind, F
    Playing 20 days; 3 of 4 decided (75%, a hint); the plain median 20 days, Kaplan-Meier's 30 (D out at 5, A at
    10: S 0.75; F out at 20; B at 30: S 0.375); the hours 8h at Finished, 1h at Dropped. With C dated too: three
    timed, the same medians. On the copy of 21 October: 3 marks, 0 Finished, 1 Dropped, 2 Playing, 0 of 1 decided.
  - Eleven, everywhere: the Reports page's intro, reports.py, ANALIZA's title and contents ("unsprezece
    rapoarte"), CITESTE-MA, the suites 83, 84, 89, 90, 91, 93, 96, 98, 101 and 102 (suite 98's "zece rapoarte not
    in the readme" became " zece rapoarte": "unsprezece rapoarte" holds "zece rapoarte"). ANALIZA's new section
    "Semnele, și când au fost puse" (the nudge, step 0's marks, the hours worked out once) and section 11;
    BAZA_DE_DATE (nudged_at written by Still playing); CITESTE-MA's two lines on Left behind (110 lines);
    `docs/explicatii/faza-103.md` and its index.
  - **The full run**: suite 103 72/72; 3271 of 3276 -- suite 75's five pad checks in Settings' Steam accounts
    (102/102 alone, the window not in front); every net clean. **No release.**
- **On the user's PC, 22 October**: checked read only, he restarted on this code at 18:07 and 19:27, no error
  logged; For you said "0 left behind" -- SILENT HILL Townfall's last session is 30 days old only at 23:44.
- **The explain-back held the same day**: he had a place that shows the games marked Playing and not touched for
  a long time, waiting where he goes (For you) rather than coming to him, and the reports' time cut almost in half
  because the hours are worked out once instead of many times. Filled in: the three answers -- Finished and
  Dropped set the mark with its date, Still playing records only the moment and leaves the game alone 30 days --
  and the rule (no session, no mark, no answer for 30 days; a fresh mark not asked; no known date never asked;
  four at most); the game's page carries not the nudge but the "since" line of a dated mark; report 11 -- the
  completion rate over the decided games only, the time to Finished, the still-Playing counted as "not finished
  yet" (censoring, Kaplan-Meier) so the median is not too short, the hours at Finished and at Dropped, the marks
  before 19 October counted but not timed; the hours' copy is temporary and nothing is written to his library;
  and the guard that keeps any test from starting one of his games.

## Phase 102 extension notes (the hours pill on a game's page)

The user's brief, written while Phase 102's second commit ran (20 October): "add a pill next to when i've played
and the size with the total hours played for the game on the game page" -- held until Phase 102's click-through
and explain-back, as the build discipline asks. Named "Phase 102 extension" by him; Phase 103 stays the reminders'
(`game.nudged_at`, laid by version 8). Tag `before-phase-102-extension` on 04f5293. No schema change.

- **Step 0, on a copy, read only (21 October)**: of 32 installed games, the page's Played pill showed for the 25
  the launcher starts (and for Epic or Xbox games seen running) and never for a Steam game -- whose hours were only
  in Details as "On Steam". By v_hours' rule (the reports' count) 7 Steam games gain it (Counter-Strike 2 3964
  hours, Aimlabs 236, Overwatch 113, WARDOGS 39h 19m, Crimson Desert 15h 34m, Left 4 Dead 2 14h 33m, 3DMark Demo
  1h 39m); 4 change because the total is the game's, not one copy's (Silent Hill 2's two copies 19h 12m: 24 min
  timed here and 18h 48m on Steam; SnowRunner 22 -> 24 min and The Blood of Dawnwalker 4h 22m -> 4h 28m, an older
  copy's minutes); 14 stay; 7 have none (Minecraft Launcher's time unknown, three tools, three never played).
- **The user's go**: "go with the pill, yes to both choices" -- the game's total, the sources apart on a hover;
  the order Last played, hours, size, with Usually after them.
- **What was built**: `LibraryStore.hours()` -- each game's row of v_hours (by its Steam app, else its record),
  v_hours worked out once (`MATERIALIZED`), read once a reload in `_read_steam_times` beside Steam's hours (1.5-2
  ms; a tile never asks); `MainWindow.hours_of`; the page's `hours_for`. The Played pill: the total, rounded once;
  "Not played yet" for an exe game with none, no pill for a store game with none -- never 0; a store that cannot
  count (the JSON library) the launcher's own time, as before. Its words on a hover (`played_tip`): "18h 48m on
  Steam, 24 min timed by this launcher", "Steam's own count, on the Steam accounts marked yours", "Timed by this
  launcher". A pill lets the mouse through by design (Phase 33), so the hover lands on its row, and the row --
  `ui_hero.PillRow`, a clear widget of its own -- shows the words of the pill under the mouse. First this was an
  event filter the page put on the row: it met the scroll area not yet built (an AttributeError at the page's
  build), and then, in the first full run, suite 79 ended in a native crash (0xC0000005) mid-scan, with no check
  printed, which five runs alone never repeated. A filter object watching a descendant can be called while its
  window is torn down, and suite 79 opens and closes several; whether or not that was the cause, the row now
  answers its own hover and nothing outside it watches it. `PILLS`: Running, Last played, Played, Installed,
  Usually, Saves copied, Controller.
- **Rendered** on a copy at the desk: Silent Hill 2 (19h 12m, its hover split), Counter-Strike 2 (3964 hours,
  Steam's count), CULTIC (1h 49m, the launcher's; and its five stars of 20 October in Recent sessions).
- **Tests**: suite 102's section 9 -- the store's hours against v_hours read raw, every game's page against its
  hours, the two sources added and said apart (a Steam game given ten launcher minutes), Steam's alone and the
  launcher's alone, the order, the hover through the row and nothing between the pills; with only the old page put
  back (copied aside and back, sha256), its every-page check fails. Suite 33's "a store game has no played pill"
  became "exactly when its hours are known, never 0"; suite 98 asks the new order.
- **The full runs**: the first, 3141 of 3141 checks, with suite 79 ended by the native crash above before
  it printed a check (its stdout held in a buffer the crash lost; the log stops in its third scan); suites 102,
  33, 57 and 98 green on the row's own hover and suite 79 63/63 three times more; then **ALL GREEN 3204/3204**,
  every net clean. **No release.**
- **Tried by the user on 21 October**: checked read only, he restarted at 02:39:40 on this code and opened game
  pages -- Silent Hill 2's and SnowRunner's among them, by the news fetched for them -- with no error logged.
- **The explain-back held the same day**: he had "a new pill with the play time -- the total one that comes from
  my database". Filled in: the total is the launcher's own time and Steam's counter on the accounts marked his,
  an app counted once -- v_hours, the reports' own rule, so the page and report 1 say one number; a Steam game
  shows its hours there now, where it showed none; a hover says which source gave what; a game whose time is not
  known has no pill, never 0, and one the launcher starts and nobody has played says "Not played yet"; the order
  Last played, Played, Installed; read once a refresh, never by a tile.

## Phase 102 notes ("how was it?" -- a session's rating; report 10, Said and played)

The user's brief (20 October): explicit feedback beside the implicit hours -- one quiet question after a
session, five stars, one tap -- so that his ratings can be set against his hours, the recommender judged
against what he said, and the friends' exports carry ratings for March. Tag `before-phase-102` on 996851d;
no schema change (version 8 made the rating table in Phase 101, empty until now).

- **Step 0, measured on a copy, read only**: 128 sessions from 14 August to 19 October, the median 16 min, the
  quartiles 3 and 66, the 10th percentile 2 min; 70 at 10 minutes or more (55%) and only 3 between 10 and 15 --
  the quick starts and bounces below, play above, so RATE_MIN_MINUTES stays 10. Those 70 were 29 games (August
  23 sessions, 12 games; September 35, 12; October so far 12, 6), 67 launched and 3 seen running, and 51 questions
  with one a game a day (about 0.8 a day). launcher.log (from 25 September) holds 8 qualifying ends; since the
  tray (17 October) 5, the window shown at 4 and hidden at 1 (WARDOGS, 19 October): the balloon is the path one
  time in five. Call of Duty: Modern Warfare 4 SP's launched process ended after 3 s and the watcher timed its 33
  minutes -- the card follows both kinds of session. Concepts rendered at the desk and on the TV at 85%.
- **What step 0 changed**: the anonymous export's number is `ANALYSIS_FORMAT_VERSION` (2), not TRANSFER_FORMAT
  (the Settings zip, 1); a save that prunes a rated session, and a carry to a reinstall (the old record's sessions
  merged into the new, `lineage.carry_over`), must take a rating along, or the commit's deferred key refuses the
  save; ratings travel in the Settings zip too (the user's yes); report 10 begins sparse and says so.
- **The user's go**: "go with phase 102, yes to the ratings in the zip".
- **Commit 1, the card, the balloon, the late rating, the switch**:
  - `logic/rate.py` (no Qt): `due` -- the switch, a tool, the minimum, a game running, once a game a day (asked today
    in memory, rated today from the store, so a restart does not ask twice); `Ask`, the question, the balloon's
    words, `rateable` (RATE_LATE_DAYS, 14), `last_unrated`.
  - `presentation/ui_rate.py`: `RateCard`, a widget of its own where the toast floats (the toast is transparent to
    the mouse by design); the stars light under the mouse; a star answers ("Thanks -- 4 stars", gone after
    RATE_THANKS_MS), Skip goes, RATE_CARD_S (20) unanswered it goes; `step`/`press` for the pad; no fade with
    Reduce animations; styled as the toast (`#RateCard`).
  - The window: `_ask_rating` at the two ends of a session -- the playtime poll's ended loop (its live session's start
    and length, read before it is dropped; one question, for the last to end) and `_bank_observed(final=True)`; the
    card while the window is shown, `Tray.say(rate.balloon, clicked=_rate_from_balloon)` while it is hidden;
    `_show_rating` waits behind a dialog, a menu or the splash (RATE_RETRY_MS, RATE_TRIES), then leaves the session
    to its page; the pad's left, right, A and B are the card's while it asks, and the TV's hints say so
    (`ui_tv.RATE`); a message floats above it (`_stack_toast`); Play and a hide to the tray take it away.
  - The store: `rate_session` (an upsert on the session's key: rated again, the stars replaced -- the one new write),
    `ratings_of`, `rated_on`, `keeps_ratings`; `write_record` deletes the ratings of sessions it did not put back;
    `carry` writes the new record, moves the ratings whose session came along, then the old one, in one
    transaction.
  - A game's page: SessionBars draws each session's stars after its length -- filled as rated, five quiet ones a click
    rates for a session of 10 minutes or more of the last 14 days -- `rateClicked`, `DetailPage.rateRequested`,
    `MainWindow.rate_late`. The pad: a game's page steps no buttons (A plays, left and right walk the games, up and
    down scroll), so its late path is the game's menu, "Rate your last session...", offered only when one waits,
    opening the same card. Settings: a section, After a game, "Ask how a session was", on.
  - Every test copy has the question off (`test_sandbox.ALWAYS_WRITTEN`), so no other suite's ended session finds
    the card holding the pad; suite 102 turns it on. The Wishlist's Y hint said "On sale / All" since Phase 101's
    third chip: "Next chip" now (suite 87).
  - Renders: the card at the desk with a toast above it and on the TV above the hint bar; a game's page with a
    rated session (four stars), one to rate (five quiet) and one too short (none).
- **The full run on commit 1**: suite 102 47/47; 3140 of 3146 -- suite 91 caught the new lesson about a
  row the store deletes and puts back, written without its phase in brackets (rewritten; 51/51), and suites 31
  (Ctrl+F's focus) and 56 (the Continue card's ring and glow), focus and foreground checks, passed alone (42/42,
  32/32); every net clean. The user asked for the PC to be shut down when the tests were done (20 October,
  04:20): commit 2 -- report 10, the anonymous export's format 3, the ratings in the zip, the documents --
  waits for the next session.
- **Commit 2, the same evening (20 October, from 23:46), report 10, the export's format 3, the zip, the documents**,
  drafted before the shutdown as edit scripts and applied after it. The user had rated a first session by then:
  CULTIC's of 15:59, 5 stars, from the card at 17:22 (the log's "rated ... 5 star(s)").
  - Report 10, Said and played: `said_played` (the ratings by game -- its Steam app where it has one, as in v_hours,
    else its record -- their mean, how many came late, the record), the hours report 1's own rows; `ranks` (ties
    their mean place), `spearman` (Pearson on the ranks), `correlation_words` (none under REPORT_SPEARMAN_MIN, 5; a
    hint under REPORT_SPEARMAN_HINT, 10; then its strength by REPORT_CORRELATION_WORDS and its way); the
    disagreements (REPORT_RATED_WELL and REPORT_BARELY_PLAYED_MINUTES, REPORT_RATED_LOW and
    REPORT_PLAYED_MUCH_MINUTES); the recommender's second check, each rated game's fit against its mean stars, the
    taste made **without the game itself** (leave-one-out: with its own hours A of the worked example read 95%
    where 84%); a rated game report 1 has no hours for (a Steam game on no account marked mine, a demo) shown with
    none, never 0, and left out of what is set against the hours.
  - **The time.** The drafted query joined v_hours, and the ten took 50.5-53.7 ms on the copy (the nine alone
    about 47-48 today, a PC twelve minutes after its start). So report 10 reads report 1's rows (CONCENTRATION gained
    `game_id`, the one column it lacked to name a game with no Steam app; said_played 1.6 -> 0.1-0.2 ms), and report
    8's query, which read `games` in two CTEs and so ran v_hours twice, works it out once (`GAMES_ONCE`, the CTE
    `MATERIALIZED`: 4.3 -> 2.4 ms, every answer the same). Materializing every query's CTE was measured too and
    helped none but report 8's.
  - The Settings zip: `ratings.json` beside purchases.json, written only when something is rated; `all_ratings`,
    `add_ratings` -- a union after the records (a rating names its session, which the merge has just brought in),
    a session rated here keeping its own stars, one with no session or not 1-5 skipped and counted, one
    transaction; ExportReport and ImportReport count them and the message says so.
  - The anonymous export's format 3 (`ANALYSIS_FORMAT_VERSION`): per game `ratings` -- the stars and the session's
    local day, nothing more -- and `status_since`, the day its mark was set (version 8's column); the dialog's
    summary names them; `analysis_source` reads them only where the library keeps them. The comparison reads
    formats 1-3: a format-2 export has `ratings` None, shown as "— (format 2)" and left empty in the CSV files,
    never 0.
  - The documents: ANALIZA "zece rapoarte", its contents, "Notele: ce spun, lângă ce joc" (step 0's figures) and
    section 10 with a worked example by hand (rho 0.30 and 0.50, the same numbers the test asks), report 1's and
    report 8's SQL quoted anew from the code; ARHITECTURA 5.8 (from a session's end to the card) and the map's two
    rows; BAZA_DE_DATE (rating written, by whom); CITESTE-MA (the question, Skip, the switch, the export's ratings;
    the diagnostics' list put in one sentence to stay on one page: 108 lines); `docs/explicatii/faza-102.md` and the
    index; the Reports page's intro and `reports.py` say ten.
  - The older suites: nine reports became ten in 83, 84, 89, 90, 91, 93, 96, 98 and 101 (report 9 found by its place
    now that it is not last; suite 83 asks the tenth empty exactly when nothing is rated). Suite 102's "no answer"
    check waits for the card to go instead of 1.6 s (it failed once, the PC busy after its start).
- **The full run on commit 2**: suite 102 94/94 (47 new); 3183 of 3193 -- suite 65 compares the Settings zip's
  reports with the old code's, and the two new counts (`ratings`, `ratings_skipped`) joined its LATER_FIELDS, as
  the purchases' did (21/21); suite 80 asked for format 2 and only months -- it asks for the current format and
  allows the days format 3 adds, a rated session's and a mark's, still never a time (51/51); suite 93 asked for
  format 2 (2 or later now) and, run alone, met the user's own launcher writing a Steam playtime reading at its
  tick of 00:18 (80/80 run again); every net clean. The user's launcher, started on this code at about 00:15,
  logged no error. **No release.**
- **Tried by the user on 21 October** ("yeah looks great"). Checked read only: the card asked about CULTIC at
  17:22:38 on 20 October, after a session of 82 minutes, and he gave it 5 stars three seconds later; Aimlabs at
  23:51 was not asked (shorter than 10 minutes, the log says so); that one rating is still the library's only one.
- **The explain-back held the same day**: he had a new way for the user to give explicit feedback -- a rating
  for each session, asked once a day per game -- and why it matters to the analysis: the ratings can be compared
  in the exports, and he has an active way to tell the launcher something. Filled in: report 10 itself (a game's
  mean stars against its hours, compared by their order, not their size -- Spearman's rank correlation -- because
  a few games hold most of the hours; nothing said under 5 games, a hint under 10); the disagreements; For you's
  second check, the fit against the stars with each game left out of its own taste; the 10 minutes from step 0
  (about half the sessions are quick starts); rating late from a game's page within 14 days; where a rating lives
  (one row tied to its session, gone with it, moved with a carry, carried in the Settings zip); format 3's stars
  and day only, never the time, a friend's older export read as never asked, never as zero; and the two caveats
  the committee may ask about, response bias and rating sparsity.

## Phase 101 notes (schema version 8 for three phases; price alerts on the wishlist)

The user's brief (20 October): a target price per wished game and an alert at each new drop, once per drop,
where he is -- the window or the tray; and schema version 8 laid for the two phases after it (a session's
rating; dated status marks and nudges), so the friends upgrade their library once. Tag `before-phase-101` on
176b287; the data's undo, `data/library.before-phase-101.db`, a backup() copy from a read-only connection, the
same content as the live file (version 7, 72 games, 128 sessions), marked read only.

- **Step 0, measured on that copy, read only**:
  - **The wished games**: 23 on the lists, 18 priced and 5 not sold (Deadlock, Dear Passengers, METAMORPHOSIS,
    Order of Wallachia, Wolf Ridge); 0 at their lowest now; none with fewer than three prices (4 to 6 each);
    one currency, EUR (88 priced observations; the store is asked with `cc=RO`), no series in two. **No
    wished price has moved since the series began**: every newest price is its lowest, and the 'lowest' rule
    run over the whole series would have alerted 0 times.
  - **launcher.log**: since 16 October each wished game has exactly one observation a day (23 a day), landed
    in one batch -- at a start, or by the tray's tick (19 October 15:16). Price landings: 2 on the 17th, 5 on
    the 18th, 3 on the 19th, one of them each day carrying the wished games. So at most one alert message a
    day, and only on a day something drops.
  - **What the design had to meet**: the store writes a game's sessions by `DELETE FROM session WHERE game_id`
    and inserting them again in one transaction (`write_record`), so a rating's key to the session, checked
    at the delete, would refuse every save of a rated game, and ON DELETE CASCADE would wipe every rating at
    every save: the key is DEFERRABLE INITIALLY DEFERRED, checked at the commit, when the sessions are back
    (sessions pruned after SESSION_KEEP_DAYS, 400, must take their rating with them in the same write --
    Phase 102's). "Once per drop" for a target needs more than the log's key: a price staying under the target
    would be a new observation every day, so a 'target' alert needs the previous price above the target, or
    above the new one. Phase 87's once-a-day notice goes through the status queue, which shows nothing in the
    tray -- where most landings happen since Phase 92: the alert goes to the balloon there, as the recap's
    offer does. The library export (Settings, the zip) carries each game's whole record, so the mark's date
    will travel in it; the anonymous export does not change.
- **The user's go**: "Yes, we can start".
- **Commit 1, the schema**: `data_access/upgrades/008_alerts_ratings_marks.sql` -- `price_target` (one per
  wished game: cents, the currency of the game's price when set, set_at; a setting, replaced or deleted),
  `price_alert` (the log, only added to: the price -- a row of the series, by a composite key to
  price_snapshot -- its kind, the price as told, sent_at; keyed by the price and the kind), `rating` (Phase
  102's: 1-5 stars for a session named by its game and start, the key deferred), `game.status_changed_at` and
  `game.nudged_at` (Phase 103's; local time with the offset, as session.started_at). STRICT, additions only,
  NULL for every game already there. `schema.sql` the same objects, the two columns after `carried_at` where
  ALTER TABLE puts them (tried first: SQLite inserts an added column after the last column, before the table's
  CHECKs), no comment inside the table; its header said version 6 and now says 8. On the copy the upgrade took
  2.3 ms; 20 of 20 tables kept every row; the result reads as a fresh database. `check_migration.py` gains
  `prove_upgrade`: the newest script on its own copy of the real library, taken back first when the user's
  start has run it, every row as it was, the added columns empty, the made tables empty, a fresh database's
  schema, no key broken -- before the store opens the copy, which would upgrade it in place.
  `test_sandbox.COLUMNS_BEFORE` names game's version-7 columns. Suites 67 (the tables), 73, 75, 76 and 86
  (what an upgrade adds), 93 (version 7 or later) take version 8; 95, 97 and 100 read what each release
  shipped at its own commit (a3e4792, c4127b2, 176b287) instead of today's tree. `tests/phase101_tests.py`
  section 1: the launcher's own door on the copy, a snapshot of 7 first, the rows, the NULLs, the empty STRICT
  tables, the fresh schema, the script additions only, nine constraints refusing, a rated game saved through
  the store with its rating kept and a rated session gone at the commit refused, and `undo_upgrades` back to
  version 7's schema read out of git. CLAUDE.md: rows 92 and 93 condensed to a line each (this file holds
  them whole), so this phase's row fits under suite 91's limit. Suite 101 23/23; the full run 3048 of 3048, every net clean but the scanner's: Call of Duty: Modern Warfare 4 SP gone, which the user uninstalled from the launcher on 19 October at 01:37 (to the Recycle Bin, in launcher.log) -- the run saved again, 33 of 33.

- **Commit 2, the alerts**:
  - `logic/alerts.py` (no Qt, no SQL): `decide` judges only the prices a landing has just added -- `prices.Landed.fresh`,
    the landed keys not in `observation_keys()` before (the store's own names, so suite 73's list of
    observation methods holds) -- for each wished game on a list and not hidden: 'lowest', strictly below every
    earlier price in the same currency, from ALERT_MIN_OBSERVATIONS (3) prices; 'target', at or under the target
    in its currency, with the price before above the target or above the new one. A target set today never
    fires by itself, and an old price never does after the upgrade. `message` names a game once (both kinds in
    one line), at most ALERT_NAMED_MAX (2), then "and N more"; `target_line` the row's words (a currency
    mismatch said, never compared); `drops` the Alerts list, one line a drop (the first render showed a drop
    twice, once a kind). `land` reads through the reports' queries and writes through `log_price_alerts`, which
    answers only what the log took (ON CONFLICT DO NOTHING, rowcount), so a message never repeats one.
  - The store: `keeps_alerts`, `set_price_target` (an upsert: a setting), `remove_price_target`, `log_price_alerts`
    (append-only); `MARK_FIELDS` maps `status_changed_at`, written and read only where `has_marks` (version 8),
    as `has_origin` does for version 7; `ui_actions.set_status` writes the moment with the mark.
  - The queries `price_targets` and `price_alerts`, quoted in ANALIZA (suite 83 holds every report query
    quoted); `money_wishlist` joins `price_target` in its one pass through v_wishlist_now (no second read: the
    nine reports' time kept), so `NEEDS_VERSION` is 8. Report 6: "You watch N wished games with a target; M
    are below it today." only when a target is set.
  - The page: a third chip, Alerts (`ALERT_KEEP_DAYS`, 30; Y walks the three), the target's words where the count
    of prices was (the row's height kept), the alert line in the accent on the Alerts list, and the summary's
    "N at their lowest price seen" -- Phase 87's daily toast retired (`wishlist.notice`, `_wishlist_notice` and
    the `wishlist_notice` key gone; a config.json holding the key keeps it, unread). The menu: Alert me under...
    (Change alert... with one), Remove alert. `presentation/ui_alert.py`: the amount in the game's currency, from
    the target or the lowest seen, a step of 1,00, no button answering Return (the purchases dialog's rule); the
    pad's right steps it and B closes it, proven through the window's pad routing.
  - Delivery: `MainWindow._price_alerts` after the landing, in Phase 87's place -- the toast while the window is
    shown, `Tray.say(text, clicked=open_alerts)` in the tray; `messageClicked` wired for the first time, a
    balloon's click doing what that balloon asked (another balloon's, nothing); `open_alerts` brings the window
    back on the Wishlist's Alerts, the remembered chip left the user's own.
  - Found by writing the suite: a stand-in for QMenu.exec did not take, and a real menu waited for a click until
    the suite's time ran out -- the menus are read off the screen and closed now (suite 52's way), the dialog
    with a watchdog; money's words carry a no-break space before the sign (`humanize.money`), so the expected
    words come from it; a game of 1,03 € left no room under it for a target and two drops (the suite picks
    one of 10 € or more).
  - **The user started his launcher at 02:37:43 on 20 October**, in TV mode, on the code of this commit's
    working tree: his library went from version 7 to 8 (the startup snapshot 2026-10-20_02-37-43 holds 7;
    72 games, 128 sessions, the file whole), and suite 98's photograph of the real library met that start's
    write.
  - **A slip, and the rule made the code's.** A loop of `phaseNN_tests.py` meant to re-run the suites around play,
    marks, the pad and the tray held suite 23, which runs only through `run_sandboxed.py`: bare, it opened a
    window on the real data from 02:39:16 to 02:39:28 while the user's launcher ran. What it wrote, read only
    after: one startup scan (scan 103, 02:39:19, the same 33 games as his own at 02:37), one startup snapshot
    (backups/2026-10-20_02-39-17), and config.json put back as it found it -- the suite's own last step; no
    session, price, alert, target or mark, the file whole, the Run value as it was. Both left in place: removing
    them would be another write to his live library. The third such slip (after Phases 70 and 87), so the rule
    is the code's now: `test_sandbox.require_sandbox(__file__)` first in suites 22-25 refuses the real data
    when run bare, with the command to use (proven both ways: 24 bare refused, config.json byte for byte; 23
    through the wrapper 73/73).
  - Suite 101 77/77; suites 23 (sandboxed), 27, 35, 36, 52, 73, 83, 84, 86, 87, 89, 91, 92, 96, 99 and 100 green on
    this code; the full run 3094 of 3099 -- suite 57's five ring checks while the user's launcher, in TV mode,
    held the foreground (59/59 alone) -- every net clean.

- **Tried by the user on 20 October** ("ok looks great"). Checked read only after: he restarted at 03:13-03:14
  on this code, a landing at 03:14:15 judged no new price of a wished game ("nothing set off"), and he set a
  first target at 03:14:33 -- Onimusha: Way of the Sword under 50,00 € (69,99 € today); no alert yet, no mark
  dated yet.
- **The explain-back held the same day**: he had a new function -- told when a wished game falls under a price he
  set -- built on two new tables, the targets and the past alerts, and why it matters to the analysis: the
  wishlist now gives back something active. Filled in: the second kind, 'lowest', from three prices only (the
  reference point, anchoring; a series of one is noise), his own target from the first; once a drop by the log,
  written before the message, a price staying under the target silent, a further drop new, a target never
  firing by itself; the toast, the balloon and its click, the Alerts list's 30 days; version 8 holding Phase
  102's rating and Phase 103's two dates too, so the friends upgrade once, the mark's date written from now;
  and the target named for the thesis as a stated willingness to pay, which report 6 now counts.

## Phase 100 notes (release 1.2.8: For you, the one question, the accent, Starting and the genre pill)

The user's brief (19 October), after trying Phase 99 and holding its explain-back. Tag `before-phase-100` on
862764b.

- **What the friends get**: Phase 98 -- For you under Library (the waiting games ranked by the fit, Tonight)
  and report 9, Recommendation; Phase 99 -- the one question (asked once, at the first start after the update,
  unless the switch is already on), five accents, Starting... and the genre pill, the pills painted round.
  **No schema change** (still version 7, the last script 007): a friend's library is not upgraded.
- **The documents**: `shared/version.py` 1.2.8 and its history line; CITESTE-MA "Versiunea 1.2.8." (110 lines;
  For you, the accent, Starting and the genre filter came with Phases 98-99); DISTRIBUTIE §3 (the version, the
  log line, 1.2.8 in the list), §5 (what the check proves now, and its figure), §7's steps 5 and 7 (the
  Sandbox's second start meets the question); CLAUDE.md's version paragraph. Suite 97 asked for 1.2.7 exactly
  and suite 99 that the version was 1.2.7: 97 asks for 1.2.7 or later, 99 reads the version at its own last
  commit (b665ee2). **CLAUDE.md had 374 bytes left** under suite 91's limit (a quarter of its size before
  Phase 91): the tails of rows 92, 93 and 98 condensed to a line each, their stories whole in these notes.
- **The build** (19 October): 32 s, 267 files, a 69 MB installer (72,258,032 bytes, sha256
  `3b565716...777d1512`), stamped 1.2.8. The 1.2.7 installer kept aside first (sha256 `ef9d1a0d...183eb5031`,
  the file published on 18 October).
- **`check_installer.py` learnt the one question and the screen**: a first run's start never shows it; the
  next start does, and closing it is Not now (the day written, the switch off) -- `answer_offer`, at section 5's
  start and at the start after the update over 1.2.7. Then `shows_whats_new` reads the installed copy's own
  screen through Windows' UI Automation, from PowerShell (`-EncodedCommand`; no new dependency): "For you" among
  the window's named controls; Settings pressed by UI Automation's Invoke (Qt's button clicks a moment later,
  nothing waits on it), the dialog's "Accent" and the five swatches' names ("Violet accent", ...); Settings
  closed, config.json byte for byte. Tried first on a sandbox window from source. **The first run found two
  things in the check, none in the program**: the first run's answer carries `version_seen` (Phase 99's
  design), and an installed copy titles the dialog "Settings - Game Launcher" (Qt adds the application's name,
  as it does to the first-run questions), so it was pressed but not found, and stayed open over the close.
- **`check_installer.py --over` the real 1.2.7: 60/60** -- 1.2.7's 49 and eleven new: no question on a first
  run's start; at section 5's start the question, Not now, For you, the Accent row, nothing written; the same
  five after the update over 1.2.7 (a library at schema 7, 10 game rows; "the same schema version, 7: nothing
  to upgrade"; all nine views answering; the games and settings as 1.2.7 left them; no error). GitHub asked
  once for real, answering 1.2.7: nothing newer offered.
- **Then the icon, the user's** (his ask while the release was a draft, 19 October: "can you also update the
  launcher icon to this one?"): `launcher.ico` replaced by the file he gave (119,841 bytes, sha256
  `4ff3efdd...431b9c72`; nine PNG pictures, 16 to 256 pixels, where the old one had seven): a dark tile, four
  violet game tiles, a play mark on the first, a plain 2 x 2 grid at 16-32 pixels. Nothing generates the file:
  the window, the tray, the shortcuts (from source their icon is this file), GameLauncher.exe and Setup.exe
  all take it. The window's own brand mark is a Phosphor glyph in the accent, not the icon, and stays.
  check_installer.py's section 1 learnt it: the built copy byte for byte, and its largest picture inside
  GameLauncher.exe's and Setup.exe's own icons (an icon resource keeps the .ico's PNG bytes as they are).
  Rebuilt: 27 s, 267 files, 72,569,885 bytes, sha256 `1550fbf2...f6545b45`; `--over` the real 1.2.7 again:
  61/61; the key and the address again in none of it. The draft's file and notes replaced (a line on the icon,
  in both languages).
- **Before the publish**: the SteamGridDB key (as text and as UTF-16) and the user's e-mail address in none of
  the 267 files, nor in payload.zip's 267 members, nor in Setup.exe; no config, library, overrides, catalogue
  or log among them.
- `tests/phase100_tests.py`: the version and that it is newer than 1.2.7; 1.2.7's schema against this one's;
  check_installer's `--over`, its question by the dialog's own title, For you and the five accents by name,
  UI Automation from PowerShell; CITESTE-MA, DISTRIBUTIE, CLAUDE.md and its size; the layers; no network; the
  real data untouched. 16/16.
- Suites 77 74/74, 79 63/63, 80 51/51, 82 55/55, 85 17/17, 88 10/10, 89 45/45, 90 11/11, 91 51/51,
  95 14/14, 96 91/91, 97 12/12, 99 82/82 and 100 16/16 on this code; 98's five pad and ring checks on the For
  you page failed once in that loop and passed 117/117 alone, no program file changed (Phase 99's full run
  was not repeated for a version and the documents).
- **Published on 19 October** on the user's word ("yes looks ok - publish it"), after reading the draft:
  `gh release create v1.2.8 dist/GameLauncher-Setup.exe --repo GreenYRO/game-launcher-releases --target main
  --title 1.2.8 --notes-file ... --draft`, the file and notes replaced once for the icon (`gh release upload
  --clobber`, `gh release edit --notes-file`; a draft's address changes at each edit), then `gh release edit
  v1.2.8 --draft=false --latest` at 00:41 (21:41:35 UTC on the 18th). The notes in Romanian and English, the
  one question first, then For you and Tonight, report 9, the accent, Starting..., the genre filter and the
  pills, the icon, and that the library is not changed. Read back through `updates.fetch`: 1.2.8, not a draft
  or pre-release, newer than 1.2.7 and not newer than itself; GitHub's asset digest is the local file's
  sha256 (`1550fbf2...f6545b45`, 72,569,885 bytes). The 1.2.8 installer kept aside for the next `--over`.
  The friends' 1.2.7 copies will say 1.2.8 is out within a day.

## Phase 99 notes (one question for the friends, and three things for the eye)

The user's brief (18 October): the tray offered once to a friend who never found the switch; an accent of
one's own; something to look at between Play and the game; and a genre filter beside the sort. No version
and no release: that is Phase 100, after a day or two of use. Tag `before-phase-99` on 463c0ea.

- **Step 0, measured on a copy, read only, and rendered**:
  - **The offer's gate as written could not work.** Settings' OK writes `keep_running: false` even when the
    switch was never touched, so "the key is absent" would have skipped every friend who had once opened
    Settings (to paste a SteamGridDB key, say). The gate became: the switch off, and never offered.
  - **Launch times**, from launcher.log: Play to the process handed back 0-4.4 s, once 13.1 s (Hellraiser's
    first start, Windows checking a program it had not seen). The wait is Windows' own start call, on the GUI
    thread: nothing could paint. No Steam game had been started from the launcher since 25 September, so
    there was nothing to measure there; the watcher looks every 5 s, and Steam can take 10-30 s when it is
    not open. The splash's backstop became 30 s.
  - **Genres**: 28 visible installed games, 11 genres, 6 games with no genre known; Steam's Nudity and
    Violent are content warnings, not kinds of game, and stay out.
  - **The accent**: four families built as the design sheet built Violet -- in OKLCH, Violet's lightness at
    every step, another hue. The main shade's contrast on the background (4.5 needed): Violet 5.45, Teal 5.99,
    Amber 5.56, Rose 5.35, Slate 5.66.
- **The user's go**: "go with phase 99, yes to all three changes" -- the offer's gate as above; for an exe
  the tracker taking the process is not an end of the splash (the game has only begun to load), only its
  closing at once is; and an exe's start off the GUI thread. And "you can make the accent change some more
  colors in the launcher that match it so it's more noticeable -it's up to you".
- **Commit 1** (ee4dd2f): `presentation/ui_offer.py` and `MainWindow.offer_tray` -- a second after the window
  first appears, once; "Not now" the default and Escape; "Keep it running" turns the first switch on and
  nothing else; `tray_offer_shown` (the day) written on both answers; another dialog up, it waits and asks
  again, 30 tries at most; never on a first run's start. `version_seen` written at every start but a first
  run's, whose answer carries it. Every test copy writes the question as asked (`test_sandbox.ALWAYS_WRITTEN`):
  a copy has the switch off, and every suite's window would otherwise stand on the question. A suite that
  ended with the process watch still running aborted at exit (0xC0000409): suite 99 stops it.
- **Commit 2** (57be550): the accent -- five swatches in Settings, Look and feel; `ui_rules.ACCENTS`,
  `ACCENT_STEPS`, `ACCENT_FORMS`; `ui_theme.use_accent`; `MainWindow.apply_accent` (the stylesheet rebuilt,
  every page's metrics put again so the icons painted once in the accent are painted again). More carries it:
  the small uppercase labels, a chosen chip's fill, the rail's ground, a scroll bar under the mouse. A game's
  own colour and its art's glow are the game's. **Settings opened with the focus on OK**: Qt gives a dialog's
  first push button to the default button; it opens on the chosen swatch now, and a swatch is never a default
  (autoDefault off -- a focused one had taken OK's outline, caught by suite 58). **The pills, reported from use
  ("jacked" lines)**: magnified at 125%, the stylesheet's 1-px, 16% edge fell on one row of pixels along the
  sides and over two half-lit ones round the ends; painting the capsule alone changed little, the edge at 1 px
  times the interface's size and 22% read even.
- **Commit 3**: Starting... and the genre pill.
  - `presentation/ui_splash.py`: one picture made when it begins (Phase 34's way), the dots on a timer, a
    fade unless Reduce animations; the surfaces through `MainWindow.begin_starting`/`end_starting`/`is_starting`
    (the tile's line, the page's Play, the Continue, Jump back in and For you cards, the tray's tooltip).
  - `adapters/launch_worker.py`: the exe's start on a QThread, waited for in a local event loop
    (`MainWindow.run_launch`), so `ui_actions.play` keeps its synchronous answer and the window paints and
    answers Escape and the pad meanwhile. A store's address is handed over at once.
  - The ends: `QApplication.applicationStateChanged` to anything but active, the tracker's tick that the game
    closed, the watcher's `_on_seen`, the timer, and Escape, B or a click. The pad, while it shows, has only
    B and A (both end it); every other button is swallowed. TV mode's switch ends it.
  - The genre pill: `GenrePill` (a `SortBox`, a delegate for the counts), `LibraryStore.genres()` (identity
    key to genre names, through `steam_app_genre`), `library_genre`. Two traps: the pick is restored before
    the genres are read, so the wish is kept apart from the list (`_wanted`); and a refill fires
    `currentIndexChanged`, so the wave follows `activated` only.
  - The pad's row of controls: up past the Continue card (or past the top row with no card), left and right
    along the chips, the two switches, the genre and the sort, A opens a list or presses, down comes back; a
    `FocusRing` with each control's half height for its radius. **Found by suite 32**: up at the top row with
    no card left the pad on the row; a tile then chosen another way (the window's `select_key`, later a click)
    left it there, and up did nothing. Both take it off the row now, the ring with it.
  - Suite 99 at 82/82; suites 27, 28, 31-35, 49, 52, 53, 55-58, 60, 92, 93, 96 and 98 green on this code.
- **For Phase 100**: `check_installer.py`'s second start meets the offer (an installed copy's switch is off)
  and must answer it; no release before the user's word.
- **Tried by the user on 19 October** ("looks great"). Checked read only after, in launcher.log and config.json:
  restarted at 00:02:31, `version_seen` 1.2.7 written ("before: none written"), the five accents clicked in
  Settings and Rose kept by OK; no error logged; **no Play since the restart**, so Starting... has not met a
  real start on his PC yet; no genre picked and kept (`library_genre` absent); the offer never shown (his
  switch is on), as designed.
- **The explain-back held the same day**: he had the four in his own words -- the question whether to keep the
  launcher running after a close, five accent colours, a screen of its own after Play, a genre list. Filled in:
  the question is asked once, and only while the switch is off (why the gate is not "the key is missing");
  an accent is a family of nine shades built at Violet's lightness, so the contrast holds (a test computes
  it), the ground stays dark and a game's colours stay the game's -- an accent, not a theme; the screen is
  there because the window used to freeze -- Windows' start call ran on the window's own line of work, now on
  a thread of its own -- and it ends when the game takes the screen, is seen running, after 30 s, or on Esc;
  the genres are Steam's, two content warnings left out, a game not on Steam under "No genre known", and the
  list narrows together with the filters and the search; the pad's way up to that row.

## Phase 98 notes (For you: what to play next and why, what fits tonight)

The user's brief (18 October): of what is installed and not started, what is most like what he plays, and
why; and, with the time there is tonight, what fits. Tag `before-phase-98` on c4127b2.

- **Step 0, measured on a copy, read only**: report 4's backlog held 10 waiting games (2 never, 8 under two
  hours), 8 with genres -- the cold start BloodBorne and Hytale (no Steam app); the ranking by Phase 89's fit;
  14 games with 3 sessions or more, 7 installed; Tonight per choice; a rough look back (each folder a game,
  Steam's games left in the pile) that read 1 of 4 in the top three, mean rank 6.8 -- and 21 of 29 first plays
  on the day the game arrived. The eight reports took about 42 ms of the 50.
- **The user's two decisions**: For you as a card in the library looked "way too cluttered", so a place of
  its own under Library in the rail and after it in the top bar ("go with A"); and the games played in the
  last 7 days left out, as Jump back in offers them ("yes leave the recent ones out") -- named, not hidden.
- **Commit 1** (40ad6c1): the fit's maths moved verbatim from logic/wishlist.py into logic/fit.py, the
  wishlist importing the same functions (its 23 fits on the copy identical before and after); report 4's state
  as one constant, `BACKLOG_STATE`; `data_access/recommend.py`, `logic/recommend.py`, `presentation/ui_foryou.py`
  (three large, the rest a line each, the cold start and the recent games named, Tonight's chips and cards);
  Phosphor's sparkle (E6A2, read from the package's CSS: the TTF's post table has no names); the pad's walk
  Library, For you, Stats, ... and Stats' hint "For you / Storage"; a game's page: "Usually N a session" and
  the Fit fact. Two repairs found by writing the suite: on a library with nothing played every waiting game
  read "no genres to compare by" (the reason was another: it says nothing played yet now); and Y on a game
  rebuilt the page and lost the ring (`_refill` keeps the row and place). 91/91 new; suites 31, 33, 35, 50,
  57, 58, 60, 74, 76, 84, 86, 87, 89, 93 and 96 green (60 picked the rail's places by position: by name now).
- **Commit 2**: report 9, Recommendation -- the ranking, the typical sessions (judged from 3, with whether
  Tonight may offer each), and the look back: for each game's first counted session, the waiting games of the
  evening before ranked by the fit as it stood then (the taste from the launcher's sessions before it, today's
  weights), and where the game started came. A game is its Steam app where it has one; a game Steam counts is
  left out (its hours have no dates), and so is one played before it was first seen; the ones played the day
  they arrived are counted, not listed. On the copy: 3 of 4 evenings among the first three, mean rank 3.5, 18
  of 25 first plays on the day of arrival -- the sentence says too few to tell. Step 0's 1 of 4 came from the
  rougher count; both are four evenings.
- **The 50 ms.** Report 9 as first written took the nine to 52.8 ms: every query that reads `v_hours` costs
  about 1.5 ms, and report 9 added three. Taken back without changing an answer: For you's waiting games are
  report 4's own `backlog` rows (widened by the record, its marks and the three dates of play) filtered by
  `recommend.waiting` -- the candidates query is gone, and with it the second copy of the rule; report 9's
  taste is `fit.profile_from` on report 1's rows, equal to `profile_of(wishlist_profile)` (272 apps, a test
  holds them equal); `money_lowest` on `INSTALLED_TITLES` (it read no hours: 2.9 -> 1.6 ms, the same 18 rows);
  report 3's publishers and developers in one run, split by role (2.8 -> 1.8 ms, the same rows); the look
  back's Steam test on `v_steam_time_mine` rather than `v_hours`. The eight 40.9 ms, the nine 44.9 ms (best of
  9; median 45.1). ANALIZA quotes the three changed queries again, and says why.
- **A cycle avoided**: report 9's queries live in data_access/recommend.py, built on the reports' CTEs; they
  join `reports.QUERIES` as recommend.py loads, and reports.py imports it last without reading from it -- the
  first try read `_recommend.QUERIES` mid-load and broke whenever recommend.py was imported first.
- **Found by the first full run** (2929 of 2935): suite 62's Storage map at 125% in a 1280 x 820 window did not
  give way -- it passed 27/27 on the code before this phase, set aside and back by sha256. The rail's sixth
  place had made the rail 925 px tall at 125% (745 at 100%, more than a 1366 x 768 laptop leaves above its
  taskbar), and a layout that will not shrink makes the window taller than asked: 820 became 925. Now the
  rail's minimum is the rail without "Found in", which folds away when there is no room for it (the places,
  the filters and the foot always show; rows a scan adds are told too, as Qt shows a new child a moment later
  unless it was hidden explicitly). Suites 83 and 89 asked the companies query for one role and took the last
  report for the eighth (both follow now); suite 35's one check met the user's own launcher writing the
  library (78/78 alone); the scanner's run saved again after the user's Call of Duty: Modern Warfare 4 and
  the Minecraft Dungeons II that left.
- **Documents**: ANALIZA "nouă rapoarte" and its section 9 (the formulas, the four tables, the caveats, the
  ideas: content-based and collaborative filtering, TF-IDF, the cosine, the cold start, the median, offline
  evaluation, hit rate at 3, mean rank); CITESTE-MA's first paragraph (For you, nouă rapoarte; 110 lines);
  ARHITECTURA's maps and 5.5; `docs/explicatii/faza-98.md`; CLAUDE.md's row, layout and two lessons. Older
  suites count nine (83, 84, 89, 90; 91, 93 and 96's timing words).
- `tests/phase98_tests.py`, 115 checks, the look back worked out by hand on a planted library (Dropped One 2nd
  of 10, Hollow Deep 4th of 9, Empire Lines 7th of 7, Siege Plans 8th of 8). On the code before this phase it
  cannot import (no logic/fit.py). Full run after the repairs 2944 of 2945 -- suite 52's pad check "down moves through it" with the window not in front (17/17 alone); every net clean
- No version and no release: Phase 98 goes to the friends with 1.2.8, on the user's word.
- **Tried by the user on 18 October**, after a restart (Quit from the tray, the shortcut): "for you works and
  looks great". Checked read only after: the log has the page worked out on his library at 21:27:11 and
  21:27:26 (6 ranked, 2 with no genres, 3 played lately, Tonight 3 of 7 judged) and `foryou_tonight` saved
  (30 min). The second game with no genres is Call of Duty: Modern Warfare 4 SP, installed after the test
  copy: a folder game the storefront search did not link to a Steam app -- the cold start, named apart.
- **The explain-back held the same day.** In his words: content-based filtering on the genres of the games
  he plays, recommending the similar ones by genre only; Tonight takes a median and shows the games that fit
  it. Corrected: the median is each game's own (the middle of its sessions -- CULTIC's 2, 3, 3 and 17 minutes
  read 3), and the chosen time is only the limit it must fit under. Filled in: Tonight's order (the share of
  sessions that fit, then the one played last), TF-IDF (Action is in nearly everything, so it weighs
  little), the cold start (BloodBorne and the new Call of Duty named, never 0%), the 7 days, report 9's look
  back as an offline evaluation (3 of 4, too few). His "more data, better recommendations" only in part:
  Steam's hours were in the taste from the start; the watch adds sessions, so Tonight judges more games and
  the look back gets more evenings; the ranking still sees only genres and only installed games.

## Phase 97 notes (release 1.2.7: the recap card in the friends' version)

The user's "lets also release" (18 October), after trying Phase 96 and holding its explain-back. Tag
`before-phase-97` on 6e7db2f.

- **What the friends get**: Phase 96 -- the Stats page's Recap card and Share as image... (This month, Last
  month, This year; Copy image, Save image...), the offer once a month (and the year's from 15 December),
  and the one rule by which Stats counts the sessions of every game played, installed or not. **No schema
  change** (still version 7, the last script 007): a friend's library is not upgraded and no snapshot is
  taken for one; the anonymous export's format is the same.
- **The documents**: CITESTE-MA "Versiunea 1.2.7." (the Recap sentence came with Phase 96; 110 lines);
  DISTRIBUTIE §3 (the version, the log line, 1.2.7 in the list), §5 (the check below), §7's step 5;
  `shared/version.py`'s history line; CLAUDE.md's version paragraph. Suite 95 asked for 1.2.6 exactly; it
  now asks for 1.2.6 or later.
- **The build** (18 October): 30 s, 267 files -- as 1.2.6: the recap's three modules are inside the
  program's own archive, not files of their own -- a 69 MB installer (72,166,532 bytes, sha256
  `ef9d1a0d...183eb5031`), stamped 1.2.7. The 1.2.6 installer kept aside first (sha256 `3a8efa8e...5a17a29917`,
  the file published on 18 October).
- **`check_installer.py --over` the real 1.2.6: 49/49** -- sections 1-7 as 1.2.6's (stamped 1.2.7, both
  first-run questions, the process list read, GitHub asked once for real and answering 1.2.6 -- nothing newer
  offered -- the update byte for byte, the Run value kept and then removed, the user's shortcuts and Run
  value untouched) and section 8: 1.2.6 installed and started as a friend's PC starts it (a library at
  schema 7, 10 game rows), this installer over it, started as 1.2.7 with no question, "the same schema
  version, 7: nothing to upgrade", all nine views answering, the games and settings as 1.2.6 left them, no
  error. Two checks fewer than 1.2.6's 51 by design: the upgrade's two become that line. An installed copy
  that could not import the recap would not have opened its window: it did, twice.
- **Before the publish**: the SteamGridDB key (as text and as UTF-16) in none of the 267 files, nor in
  payload.zip's members, nor in Setup.exe; no config, library, overrides, catalogue or log among them; the
  user's e-mail address nowhere.
- `tests/phase97_tests.py`, 12 checks: the version and that it is newer than 1.2.6; 1.2.6's schema against
  this one's (the same, and no script or schema line changed); check_installer's `--over`; CITESTE-MA (1.2.7,
  the Recap card, 110 lines), DISTRIBUTIE (1.2.7, the notes in two languages), CLAUDE.md; the layers; no
  network; the real data untouched.
- Suites 77 74/74, 79 63/63, 80 51/51, 82 55/55, 85 17/17, 88 10/10, 89 45/45, 90 11/11, 95 14/14,
  96 91/91 and 97 12/12 on this code; Phase 96's full run (ALL GREEN, 2796 of 2796) was not repeated
  for a version and the documents.
- **Published on 18 October** on the user's word ("lets also release"): `gh release create v1.2.7
  dist/GameLauncher-Setup.exe --repo GreenYRO/game-launcher-releases --target main --title 1.2.7`, the
  notes in Romanian and English (the recap as an image, the offer once a month, Stats counting every game
  played; the library not changed; quit from the tray and run the new Setup.exe over the old). Read back
  through `updates.fetch`: 1.2.7, not a draft or pre-release, newer than 1.2.6 and not newer than itself;
  GitHub's asset digest is the local file's sha256 (`ef9d1a0d...183eb5031`, 72,166,532 bytes). The
  friends' 1.2.6 copies will say 1.2.7 is out within a day.

## Phase 96 notes (the recap card: a month in review as an image to share)

The user's brief (18 October): the figures the database already holds, turned into one image a friend
sees in two seconds and passes on -- how the launcher reaches the next friend, whose library is the
thesis's comparison data, and a demonstration for the committee. Tag `before-phase-96` on a3e4792.

- **Step 0, A**: `docs/explicatii/`, a page in Romanian per phase for the user to understand and rehearse
  (what was built, why it matters, how it works, five words, three committee questions with answers in
  the first person, what it cannot do): its CITESTE-MA and faza-92 to faza-95, committed on their own
  (c6ce2a0). **B**, on a read-only copy: September 2026 49h 06m in 47 sessions of 13 games (Marvel's
  Spider-Man 2 16h 40m, SILENT HILL Townfall 12h 38m, The Witcher 3 5h 28m), the longest 7h 51m, most
  starts after midnight (26 of 47), most time on Tuesdays, 12 new games once filtered (17 raw: an Xbox
  record whose name is its key, four reinstalls), no purchase (they begin on 11 October), no wishlist drop
  (its daily prices begin on 15 October); October so far 8h 13m, 23 sessions, 9 games, 2 watched, two
  purchases dated (75,00 EUR; two more have no day), 3 wished games on sale. **The finding that changed
  decision 7**: Stats counted the games installed now, so its September read 26h 25m (22 sessions, 7
  games) where report 5's rule read 49h 06m; October agreed only because nothing played in it had been
  uninstalled. Also: no comparison against a month only partly recorded (August from the 14th) or for a
  month still running; the part of the day rather than one hour (10 of 47 starts at 05:00). **C**: two
  concept PNGs, September's real figures and covers and a quiet month from made-up figures.
- **The user's go**: "go with phase 96, yes to the one rule".
- **The one rule**: a session counts when its game is not marked a tool, installed or not -- uninstalling
  a game does not unplay it. The reports' `sessions` CTE is that rule; it now also selects the game, the
  start with its offset and the origin (what the recap and Stats read), and every report's answer is the
  same (they select what they read). `stats_months` counts by it; `logic/stats.counted_sessions` asks the
  store (`recap_counted`), so the Stats page's chart, week and month figures do too -- its September bar
  rose from 26h 25m to 49h 06m. Its lifetime total, most played and sources still count the games
  installed now, as the page always said. A store without the database (suite 23's empty stand-in) is
  read through the views as before. ANALIZA's four session queries quoted again from the code.
- **`data_access/recap.py`**: one query per figure -- totals, games (the most time first, a tie to the
  name), the longest session, the hours and the weekdays (report 5's, for a period), the months, where
  history begins, every counted session, the new games, the purchases, the wishlist's drop, the wished
  games on sale (report 6's `money_wishlist`), whether there are Steam games -- each from `sessions`,
  each with `:start`/`:end` (local wall time, half-open), `:start_day`/`:end_day` for a purchase's day,
  `:start_utc`/`:end_utc` for price_snapshot's UTC. Run through `Reports.rows` (its `queries` a class
  attribute now, the recap's set taking its place): read-only, `query_only` on. `LibraryStore.recap()`.
- **`logic/recap.py`** (no Qt): `Period` (a month; its bounds, its previous and next, its file name);
  `build` -> `Recap`, every line a sentence with its numbers in `raw`, a line only when it has something
  to say: the big number (minutes under an hour, one decimal under ten hours, whole hours after); the
  counts; the comparison only when the month is over and history began before the month before it; the
  top three; one game: its lines beside its one cover instead of facts about sessions; the facts --
  longest session, when you played (the part of the day with the most starts, the weekday with the most
  time), new this month (a name of its own, not a tool, not a later install: lineage or a name seen
  before), money (purchases by the day bought, each currency its own, and the wishlist's largest drop in
  the period or, this month only, how many are on sale today); the footer (how the sessions were measured,
  "recorded from" when history began inside the month, and what of Steam it cannot see); a month with
  none says so. `summary` is the Stats card's line; `strings` every word the card draws.
- **`presentation/ui_recap.py`**: the card painted straight onto a 1080 x 1350 image at device pixel
  ratio 1 -- no widget tree, no stylesheet. **The first render under QT_SCALE_FACTOR=2.25 in a second
  process differed from the one at 100% in some 60,000 pixels, every one of them text**: `QFontMetrics(font)`
  measures on the screen, and a new QImage takes the screen's dpi. Now every font is measured on a 96-dpi
  image (`_metrics`), the canvas has its own dots per metre, and fonts are unhinted (hinting fits outlines to
  the device's grid): identical, pixel for pixel. Unhinted, "Marvel's Spider-Man 2" just fitted one line by
  its advance and was then cut by the ellipsis, so a name splits with a line's slack to spare. Covers at the
  card's own size from a cover factory of its own (ratio 1); an uninstalled game's from its chosen cover or
  Steam's in the cache; a game without art its accent panel, its name in the card's pixels. The painter's
  spacings are tokens (`RECAP_*` in ui_rules), a pure refactor checked pixel for pixel.
- **The dialog**: the card scaled to fit (on the TV, a share of the screen), This month / Last month as one
  row of chips (one Tab stop, moved by the arrows), Copy image (the image itself onto the clipboard), Save
  image... (a PNG, Pictures through `saves.known_folder`, "Game Launcher - September 2026.png"), Close. The
  Stats page's Recap card at its top: the line ("October so far: 8h 13m across 9 games, 23 sessions") and
  Share as image...; A on the pad on Stats opens it; the TV hint bar says so.
- **Suite 96**, 61 checks: the period arithmetic; a planted September worked out by hand (590 minutes --
  the tool's 500 and August's and October's left out -- the top three with a tie to the name, Charlie
  uninstalled and still counted, every fact, the comparison against a whole August); the months adding up
  to report 5's totals; the card = Stats = `stats_months` on the copy of the user's library, every recorded
  month; the quiet month and an empty one; nothing personal among 60 strings; the second process at 225%;
  Copy (into a stand-in: the user's clipboard is never touched) and Save; the dialog driven by the pad; the
  render 16 ms (best of 3, the busiest month), the eight reports 41.8 ms.
- **Older suites**: 23 recounts its oracle by the rule (every record not marked a tool, not the grid's
  views); 58 measured the Stats column's start by the first figure card, and measures it by the Recap
  card now, the figures on its left edge. Green: 23, 32, 35, 50, 58, 60, 62, 83, 84, 93, 94.
- **The second commit: the year.** `Period` with month 0 is a calendar year, [1 January, the next 1
  January); the chooser adds This year, and Last year in January. The year's card: the top five (five
  covers in the three's width), "N games played at least once", the twelve months as Stats' chart draws
  them (a month before history or not yet begun a faint stub), the busiest named with when in the day and
  the week beside it (so the year's facts are the longest session, the year's new games and its money, in
  one row of three), "Year in review" or "Year so far".
- **A game is its name on the card**: rendering 2026 showed S.T.A.L.K.E.R. 2's 1130 minutes split across two
  records (889 and 241: reinstalled into another folder) and four such games on the user's library. The
  card's games and its count group by the name, the installed record's name and key first; 2026 is 31
  games, not 35, and September 12, not 13 (The Blood of Dawnwalker had two records).
- **New is after the library's first day**: the year read "52 games new this year" -- everything the first
  scan (11 August) found. A game first seen on the library's first day was there already; 2026 is 35.
- **Narrow cards**: a year's facts are a third of the width. A list of names that leaves its first name less
  than RECAP_NAME_ROOM of the card shows that name alone, shortened; a fact's `short` (the money's
  "3 purchases") stands in for a detail that does not fit.
- **Room**: a planted September with a comparison and all four facts ran into its footer. The comparison is
  now a third line beside the big number (the counts move up a line for it), and a card whose content would
  still come within RECAP_FOOTER_CLEARANCE of its footer is painted again with its covers that much shorter,
  never below RECAP_SQUEEZE_FLOOR of their height: the covers give way, never the words. `paint` returns
  `Painted` (the image, the strings, the content's bottom, the footer's top); suite 96 holds the bottom above
  the footer for the planted month and year and for every recorded month and this year of the user's library.
- **The offer**: `recap.offers` -- the month just ended, once, when it holds a session; the year from
  RECAP_YEAR_OFFER_DAY (15 December) to the end of January, once -- called by `MainWindow.offer_recap`
  RECAP_OFFER_DELAY_MS after the start and at every tick: one toast through the status queue, or the tray's
  balloon when the window is hidden; remembered by config.json's `recap_offered` and `recap_year_offered`;
  never in a first run. **A quiet sandbox copy holds both as already shown** (`test_sandbox._recaps_offered`),
  so no suite's window gains a toast of its own at its start; suite 96 sets them back to test it.
- **The documents**: CITESTE-MA, a sentence for the friends (where the button is, that the image holds no
  folder paths, account names or e-mail addresses), its page still 110 lines (two lines tightened);
  ARHITECTURA, the three modules in its maps and 5.4 with the one rule; ANALIZA, "Recapitularea" (Romanian,
  the English terms in brackets) -- the card shows report 5's figures for a period, report 6's money and
  report 7's way of measuring in its footer, and nothing the database does not hold (the brief said reports
  4, 5 and 7: report 4, the backlog, has nothing on the card); `docs/explicatii/faza-96.md`.
- **Suite 96**, 91 checks now: the year (695 minutes on the planted library, its top five, the twelve months'
  recorded and unrecorded, the busiest, the year's new games after the library's first day, its money), one
  game in two records counted once, the room above the footer, the offer in all its cases, and the documents.
- **The full run: ALL GREEN, 2796 of 2796**; every net clean (imports, layers, paths, the scanner, the
  migration, the original folder).
- **Tried by the user, 18 October**: "restarted it, the recap card works". The log, read only: the offer of
  September's recap at 18:41:52 (config.json's `recap_offered` 2026-09), then the three periods painted in
  10-39 ms. **The explain-back, the same day**: he had it as the data the launcher already keeps, shown in a
  way that is easy to share as an image from the Stats page. Filled in: the one rule, which ended Stats and
  the reports disagreeing about the same month (26 against 49 hours); an image painted at a fixed size with
  its letters measured on itself, not a screenshot -- the 225% difference the test's second process found;
  no unknown drawn as zero (money, the comparison, an empty month, the footer's Steam line); the half-open
  month; nothing private on the image; the offer once a month.

## Phase 95 notes (release 1.2.6: Phases 92-94 in the friends' version)

The user's "lets also release" (18 October), after trying Phases 93 and 94 and holding their
explain-back: "release" is the word he said he would give ("I will daily-drive it and say 'release'
myself", Phase 93's brief), so the build and the publish are one phase, as 1.2.5's were. Tag
`before-phase-95` on 75b2103.

- **What the friends get**: Phase 92 -- Settings' "Running in the background": Keep running when the
  window is closed (off), Start with Windows (off, needs the first), one launcher at a time, the tick;
  Phase 93 -- Notice games started outside the launcher (on), observed sessions, "Running — timed by
  watching", report 5's "How they were measured", the anonymous export's format 2; Phase 94 -- a
  sleep is not play. **A schema change**: their library goes from 6 to 7 at the first start of 1.2.6,
  a snapshot first (`007_observed.sql`, one added column, every session already there 'launched').
- **One repair the release asked for**: the installer refuses while the launcher is open (its files are
  locked) and said "Please close it and run this again" -- with Keep running on, closing the window
  leaves it in the tray, and the message would come back with no way out named. It now adds "If its
  icon is beside the clock, right-click it and choose Quit"; CITESTE-MA's Actualizare says the same
  ("dacă stă lângă ceas: clic dreapta → Quit"), its page still 110 lines. A 1.2.5 copy has no tray,
  so this release's update is never met by it; the next one's can be.
- **The documents**: CITESTE-MA "Versiunea 1.2.6."; DISTRIBUTIE §3 (the version, the log line, 1.2.6 in
  the list), §5 (the check below), §7's step 5; `shared/version.py`'s history line; CLAUDE.md's version
  paragraph. Suite 90 asked for 1.2.5 exactly, "Versiunea 1.2.5." and '"1.2.5"' in DISTRIBUTIE; it now
  asks for 1.2.5 or later and the current version (88's were loosened the same way in Phase 90).
- **The build** (18 October): 32 s, 267 files -- one more than 1.2.5's 266, the upgrade script 007 --,
  a 69 MB installer (72,119,556 bytes, sha256 `3a8efa8e...5a17a29917`), stamped 1.2.6. The 1.2.5
  installer kept aside first (sha256 `97d3f80e...1125096d`, the file published on 16 October; `dist\`
  still held it, Phase 92's proof build having put it back).
- **`check_installer.py` gains one check**: the installed copy's log says the process watch began and
  that the process list was read ("refuse to be asked their path" -- the first look's line), since 1.2.6
  is the first copy handed out that looks at it: ctypes in a frozen app, proven, not assumed.
- **`check_installer.py --over` the real 1.2.5: 51/51** -- sections 1-7 (stamped 1.2.6, Add/Remove 1.2.6,
  both first-run questions, the process list read, GitHub asked once for real and answering 1.2.5 --
  nothing newer offered -- not asked again that day, the update over it byte for byte with the Run value
  kept, a quiet uninstall keeping the data and removing the Run value, the four real shortcuts and the
  user's own Run value untouched) and section 8: 1.2.5 installed and started as a friend's PC starts it
  (a library at schema 6, 11 game rows), this installer over it, started as 1.2.6 with no question, the
  library brought from 6 to 7 with a snapshot holding 6 first, all nine views answering, the games row
  for row and the settings as 1.2.5 left them, no error. The first run, before the process-list check
  was added, was 50/50.
- **Before the publish**: the SteamGridDB key (as text and as UTF-16) in none of the 267 files, nor in
  payload.zip's 267 members, nor in Setup.exe; no config, library, overrides, catalogue or log among
  them; the user's e-mail address nowhere either.
- `tests/phase95_tests.py`, 14 checks: the version and that it is newer than 1.2.5; 1.2.5's schema 6
  against this one's 7, the one new script 007 and that it only adds a column; the scripts bundled;
  check_installer's `--over` and its process-list check; the installer's Quit words; CITESTE-MA (1.2.6,
  the three switches, Quit before an update, 110 lines), DISTRIBUTIE, CLAUDE.md; the layers; no
  network; the real data untouched.
- Suites 77 74/74, 79 63/63, 80 51/51, 82 55/55, 85 17/17, 88 10/10, 89 45/45, 90 11/11, 92 100/100,
  93 80/80, 94 46/46 and 95 14/14 on this code; the full run of 75b2103 (2683 of 2690, each failure
  explained) was not repeated for a version, a message and the documents.
- **The notes in two languages from now on** (the user, while this release was prepared: "can you
  publish the update notes in english too besides romanian from now on?"): Romanian first, then the
  same text in English; DISTRIBUTIE §9's step 3 says so.
- **Published on 18 October** on the user's word ("lets also release"): `gh release create v1.2.6
  dist/GameLauncher-Setup.exe --repo GreenYRO/game-launcher-releases --target main --title 1.2.6`, the
  notes in Romanian and English (the tray and Start with Windows, the games seen running and their
  hours never counted twice, a sleep not counted; the library upgraded after a backup copy; close the
  launcher and run the new Setup.exe over the old). Read back through `updates.fetch`: 1.2.6, not a
  draft or pre-release, newer than 1.2.5 and not newer than itself; GitHub's asset digest is the local
  file's sha256 (`3a8efa8e...5a17a29917`, 72,119,556 bytes). The friends' 1.2.5 copies will say 1.2.6 is
  out within a day.

## Phase 94 notes (a sleep is not play)

Found at Phase 93's step 0 (18 October), measured and proposed on its own, and built on the user's go:
"Go with Phase 94: cap each gap at three polls (9 s), suite proven both ways". Built in a worktree of
its own (branch `phase-94`, from `licenta` at fb258fa) while Phase 93 was being built in the project
folder: the two share `rules.py` and `ui_window.py`, in different places, and Phase 94 came onto
`licenta` after Phase 93 was committed. Restore point `before-phase-94`, set where it landed.

- **The cause, by reasoning.** `PlaytimeTracker.poll` measured a session as
  `int(time.monotonic() - started)` (Phase 53). On this Python (3.14.5) `time.monotonic()` is
  `QueryPerformanceCounter()` -- read off `time.get_clock_info`, and the same value as a direct QPC
  read to the microsecond. Microsoft documents `QueryUnbiasedInterruptTime` as leaving sleep and
  hibernation out, `QueryInterruptTime` and `GetTickCount64` as counting them; QPC is reported to
  count them too. The window's 3-second timer does not fire while the PC sleeps, and the game's job
  still holds its processes when it wakes, so the first look after waking added the whole sleep to
  the total and to the session's minutes -- and banked it at once, the once-a-minute write being
  long overdue by then.
- **Not observable on this PC, and said so.** No sleep since the last boot (17 October 14:06): the
  five clocks read the same within 0.03 s, interrupt time and unbiased interrupt time equal. The
  System log, from 26 August, holds one sleep: 8 October 16:06:53-16:07:06, 13 s, no game timed. The
  PC has S3 and hibernate, no Modern Standby, and on mains power never sleeps or hibernates by itself
  (both timeouts 0), so a sleep is always the user's own choice. A test cannot force one, and putting
  the user's PC to sleep is not the assistant's to do. The fix is right either way: if QPC stopped
  during a sleep, no gap would ever be long and the cap would never come into play.
- **The library, read only on a copy: nothing to repair.** 122 sessions of 34 games; the only one
  far longer than its game's others is Marvel's Spider-Man 2 on 2 September, 471 minutes against a
  median of 50 -- and the System log holds no sleep that day. STALKER 2's 183 and 195 minutes (17 and
  21 August) are older than the log, but ordinary for that game's other install (median 66, up to
  183). `launcher.log` and its two copies, 25 September to 18 October: 982 banks, the largest 63 s;
  a sleep would be one bank of hours. No stored total was touched, as the brief asked.
- **The fix, in `launch.py`.** Each `RunningGame` keeps `played`: every gap between two looks added
  on, each at most `rules.PLAYTIME_GAP_MAX_S` -- three looks' worth, `3 * PLAYTIME_POLL_MS // 1000`,
  9 s: the rule Phase 93's watcher uses for its own looks (`WATCH_GAP_MAX_S`, three of its 5 s
  looks). `total = int(played)`, rounded once, and `seconds` is what the tick adds to it, so the
  ticks still sum to the total (Phase 53's fraction). A cut gap is said at info, so `launcher.log`
  holds it: "<game>: 7200s between two looks, counted as 9s -- the PC was asleep, or the launcher
  stood still". The window, its banking and `_session_update` are unchanged: they read
  `total_seconds`, which now leaves the sleep out, so the session's minutes and the tray's
  "Playing ... for" follow by themselves.
- **Why a cap, not another clock.** `QueryUnbiasedInterruptTime` would leave a sleep out exactly, but
  what it does in a sleep is just as unobservable here, it would be a ctypes call in `logic/`, and
  Phase 93's watcher -- which only sees processes at its looks -- needs the gap rule anyway. The cap
  rests only on what the launcher saw itself: no look for longer than three looks.
- **What it costs.** A sleep counts at most 9 s, which also holds the few seconds of real play on
  either side of it. A launcher that stood still for more than 9 s while a game ran would lose that
  time too -- never seen (the largest bank in three weeks is 63 s), and the log line says when.
- **`PLAYTIME_POLL_MS` moved into `rules.py`** from `ui_window.POLL_INTERVAL_MS`, the number
  ARHITECTURA §12 item 10 listed outside the two tunables files, since the cap is counted from it.
  That item's message durations stay where they are.
- **`tests/phase94_tests.py`, 46 checks, on a fake clock** as suite 53 does (`time` swapped in
  `launch` and `ui_window`; a sleep is the clock jumping with no look between). The rule: 3 s, 9 s,
  no interval of the window's own. The tracker alone: 8.9 s and 9 s count in full, 10.5 s counts 9,
  a two-hour sleep counts 9 and is said once at info, a sleep before the first look, a day's
  hibernation, a game found closed on waking, two games through one sleep, the ticks still summing
  to the total across two sleeps. Through the window and the real banking: half an hour, two hours
  asleep, half an hour (3609 s gained for 3604 played, the session 60 min, no write over 65 s, the
  tray's figure right after waking); two sleeps in an evening at the real timer's pace; a night's
  hibernation with the game found closed; and Phase 53's promise with nothing asleep at three paces,
  the slowest 8.9 s -- within a second, nothing cut, the log silent. **Proven both ways**: 46/46;
  with the three files put back as they were at fb258fa (copied aside and back, checked by md5), 24
  fail -- the two-hour sleep counted 7209 s, the night 36003 s, the tray saying 9004 s after 1804
  played -- and the 22 that pass are the no-sleep checks, as they should be. Suite 53 19/19,
  unchanged.
- **Onto `licenta` after Phase 93**, which its session committed in four commits (cdf47c4, 17fa14c,
  a7bdf47, d67880c) while this was built; both conditions -- Phase 93 in the history, the project
  folder clean -- checked before anything moved. The rebase met only the notes: row 94 above row 93
  (row 92 taken from Phase 93's side, which had updated it; this side's copy was fb258fa's, checked
  by md5), these notes above Phase 93's, the playtime lesson in place of Phase 53's with Phase 93's
  three new lessons kept. Phase 93's observed sessions have their own gap rule (`_bank_observed`,
  `WATCH_GAP_MAX_S`), so nothing in them needed this one. Suites 94 and 53 46/46 and 19/19 on the
  combined code; then `before-phase-94` on d67880c and `licenta` fast-forwarded.
- **Full run 2689 of 2690** (Phase 93's 2644 and these 46): suite 32's "and is on the page, at full
  height" found the Continue card placed but still 0 px of 268, 0.6 s after the window appeared --
  69/69 alone, and nothing it measures is touched here. Every net clean: imports, layers, paths, the
  scanner (34 games, 0 differences), the migration (122 sessions, 5656 minutes), the original folder.
- **Not covered, and said so**: whether QPC counts a sleep on this PC (above); a game started
  outside the launcher, which is Phase 93's watcher and its own rule.
- **The explain-back, 18 October, with Phase 93's** (the user: "phase 94 fixed the issue with the pc
  going to sleep and potentially tracking my games when i actually didn't play them"). Filled in: the
  cap is on the launcher's own timer, for the games its Play starts; the watcher's sessions had their
  own cap from Phase 93 (`WATCH_GAP_MAX_S`, 15 s a gap).

## Phase 93 notes (sessions for games started outside the launcher)

Asked for as a brief (a game started from Steam, Epic, Xbox or its own shortcut left no session; Steam
games had hours, Steam's counter, but no sessions, so every report about the hour of the day or the
length of a sitting left them out). Step 0 measured and stopped; the user's go: "go with phase 93, yes
to all five". Restore point `before-phase-93` (on the commit that ignores `data/library.before-*.db`:
the brief said data/ was ignored as a whole, and it is not -- only file by file); the data's undo,
`data/library.before-phase-93.db`, a backup() copy from a read-only connection, the same content as
the live file (version 6, 122 sessions), marked read only.

- **Phase 92's health, read off launcher.log first**: clean -- but three repairs, in their own commit
  before anything of Phase 93 (see the Phase 92 notes): the tick said "nothing due" at debug, which the
  file never holds; a double click on the icon brought the window back twice; the sandbox copied the
  user's new `keep_running` and `tray_hint_shown`.
- **Step 0's measurements** (18 October, read only, scratch scripts deleted after): 321 processes, one
  full look 3.0 ms (median of 20, 2.8-3.3); 159 gave their path, 162 refused -- all Windows services,
  drivers and system parts (svchost x89, Defender, NVIDIA, VPN, VMware, Sunshine, steamservice), none
  named as an exe of a game here. The 34 games: folders 23, Steam 8, Xbox 2, GOG 1, every install_dir a
  folder on disk, no loose exe here; 30 watched, the 4 the user marked as tools left out; WARDOGS
  Playtest hidden and watched; and the brief's Doom/Doom2 case for real: `common\WARDOGS` beside
  `common\WARDOGS Playtest`. **Aimlabs started from Steam while a watcher looked every 5 s**: first
  seen 00:37:34 (2 processes, the game and its crash handler), up to 8 (six of them its embedded web
  view), last seen 00:38:34, all gone by the next look and none back in 19 -- no gap at the start
  either. So the measured gap is 0 looks; `WATCH_GONE_POLLS` is 2, one more for a starter that hands
  over in the instant between two looks. **The tracker and sleep**: `PlaytimeTracker.poll` measures
  from the session's start on `time.monotonic()`, which here is `QueryPerformanceCounter()`; Microsoft
  names QueryUnbiasedInterruptTime as the clock that leaves sleep out, so a timed game left open over a
  sleep is most likely credited it -- not observed, not fixed here; its own task (Phase 94, in another
  session's worktree).
- **The five nods** (all yes): the worker in `adapters/` (every background thread lives there, save_worker
  among them); the brief's "two-store hole" is not a double count -- Steam's counter never holds the
  other copy's time -- and is documented so in BAZA_DE_DATE; the page's words will be "Running — timed
  by watching" (true also for a Steam game started from the launcher's own Play, a URI hand-off the
  tracker never times); the saves search after an observed session for exe games only (Steam, Epic,
  Xbox keep cloud saves); Stats' lifetime figure (the launcher's hours) and its month chart (sessions)
  will read differently for Steam games, to be audited and worded in the second commit.
- **`logic/observe.py`**: `processes()` (K32EnumProcesses, OpenProcess with
  PROCESS_QUERY_LIMITED_INFORMATION, QueryFullProcessImageNameW through ctypes; never this launcher's own
  pid; the refusals' names from a Toolhelp snapshot, which names a process without opening it);
  `watched_games(views, roots)` (never a tool by the user's mark, never a Steam type outside
  `rules.WATCH_GAME_TYPES` -- game, demo, mod -- when the appid is certain, never a scan root or a drive;
  a loose exe by its exact path); `owners(paths, games)` (inside the folder, compared as normalised
  paths with the separator added); `Observer.feed` (pure, the clock given with each look: opens at the
  first look, ends after `WATCH_GONE_POLLS` empty looks at its last sighting, each gap counted at most
  `WATCH_GAP_MAX_S` = 15 s, never a game the tracker owns, and one the launcher takes over ends there);
  `adds_hours` (the rule, `rules.HOURS_KEPT_BY_STORE` = steam).
- **`adapters/process_worker.py`**: a QThread, a look every `WATCH_PROCESS_POLL_S` (5 s), matched
  against the watched games the window hands it (replaced at every reload of the views, so a game
  installed today is watched today and one marked a tool stops at once), the keys seen sent as a
  signal with the look's moment; the refusals named once a run and again only for a new name; a look
  slower than `WATCH_ENUMERATION_MAX_MS` (30) said once.
- **The window** (one writer): `_on_seen` feeds the Observer with the tracker's games as owned;
  `_bank_observed` writes on `PLAYTIME_WRITE_INTERVAL_S` and at the end -- the session
  (`sessions.upsert(..., SESSION_OBSERVED)`), last played, and playtime only when `adds_hours`;
  nothing at all under `SESSION_MIN_MINUTES` (a minute of a crash handler or an updater in a game's
  folder is not play); a session over `SESSION_MAX_HOURS` (12) recorded and said at warning; the saves
  search queued after it for an exe game. `game_running()` -- launched or observed -- now holds the
  folder watch's scan, the tick's, the saves search and coming back to the front. The watch starts
  with `begin()` when `watch_games` (on by default) and the library keeps a session's origin (version
  7), stops at once when either goes and in `shutdown()`, where its live sessions are banked at their
  last sighting; the first day it watched is kept as `watch_games_since`, by its own key. The tray's
  tooltip says "Playing" for an observed game too.
- **Schema version 7** (`upgrades/007_observed.sql`): `ALTER TABLE session ADD COLUMN origin TEXT NOT
  NULL DEFAULT 'launched' CHECK (origin IN ('launched', 'observed'))`. SQLite writes the added column
  after the last column, before the table's UNIQUE, on the same line; `schema.sql` has it in the same
  place, and **no comment inside the table** -- SQLite keeps a table's text as written, so a comment
  inside it made a fresh file and an upgraded one differ (suite 83 compares without stripping comments).
  The store writes and reads the column only on a version-7 file (`library_db.has_origin`); a record's
  session dict says `"origin": "observed"` only for an observed one, so every record of before keeps its
  shape and JSON comparisons stay byte for byte; `sessions.merge` keeps the longer with its origin.
- **The older suites**: 67 asks for version 7; 73, 75, 76 count session's changed text as version 7's;
  73's list of price-observation methods leaves `keeps_observed` out; 75, 76, 83, 86 compare a session's
  rows in the columns it had (`test_sandbox.rows_in_old_columns`); 86 counts the upgrade from 5 through
  7; 90 reads the schema 1.2.5 shipped at its release commit (096f816). `test_sandbox.undo_upgrades`
  takes an added column off again (DROP COLUMN: SQLite drops a column with its own CHECK, and the text
  reads as before -- tried first), and only for scripts the file itself ran (a copy still at version 6
  has no column to drop). Suite 75's pad walk through Settings failed once (5 checks, one cascade) and
  passed twice after: the dialog must stay the active window, the PC was in use; with the watch off,
  with the thread only sleeping, it passed too -- not this phase.
- **A task's worktree inside the project**: the Phase 94 session works in `.claude/worktrees/...`, a whole
  copy of the project, and the import, layer and network nets walked into it. `.claude` joined
  `sources.NOT_SOURCE`, and suites 73, 79 and 86's own walks skip it.
- **Suite 93**, so far 51 checks: the path rule on made-up views; the session rules on a turned clock;
  **a real game not started by the launcher** -- a made-up folder holding a copy of cmd as the starter
  and a copy of ping as the game, started as a shortcut would, the starter gone at once -- seen 0.5 s
  after it started, banked live at minute 1 while running, ended on its own, one observed session of 1
  minute, 74 s added for about 75 played, last played moved; the same game started from the launcher
  timed by the tracker and never observed; the minimum; the 12-hour warning; the switch off and on;
  the double-count rule through v_hours on the copy (a Steam game's 50 observed minutes: playtime and
  minutes_launcher unchanged, minutes still its counter; a folder game's 30 grow it by 30); the upgrade
  (version 7, the 122 old sessions 'launched', 'guessed' refused, the origin through a record, the file
  and a merge, the migration net green); one look 2.9 ms; the layers; the real data, config and Run key.
- **The second commit, what is shown and said.** Settings' "Running in the background" gains "Notice
  games started outside the launcher" (`watch_games`, on by default), its quieter line the brief's,
  and "Sessions seen since <day>" from `watch_games_since` once the watch has begun; Settings' OK
  turns the looks on or off at once (`_apply_watch`). **Found by the suite: Settings already had a
  `watch_box`**, the folder watch's (Phase 26) -- the new switch took its name, the later one wrote
  over it, and "notice games" answered with the folder watch's value; the new one is `observe_box`.
- **While a game is seen running** (`observer.running()`): its page shows a pill first, "Running — timed
  by watching", Play reads "Running" and rests (disabled, its tooltip says why), and there is no Stop
  -- nothing the launcher did not start is ever stopped by it; its tile's second line says the same
  (`tile_subtitle(..., observed)`); Play from the tile, the card, the tray menu or the pad comes through
  `MainWindow._already_running` and never starts a second copy; the tray lists it as "X is running",
  greyed. The words are "timed by watching" rather than the brief's "started outside the launcher":
  a Steam game started from the launcher's own Play is a URI hand-off the tracker never times, and is
  observed too (the user's nod). An administrator start says "timed by watching" when the watch is on.
- **Recent sessions** shows for every game with sessions (it was exe games only), an observed one's
  length written "≈ 47 min"; an Epic or Xbox game with time seen gets the Played pill. The Continue card
  is unchanged: it picks by last played, which an observed session moves.
- **The words** (the brief's audit): Stats' caveats -- with the watch on, "Since <day> the launcher sees
  them running while it is open ... a Steam game's hours stay Steam's own counter, an Epic or Xbox game's
  are the time seen", a line when some sessions were seen rather than started (the chart and the week
  count them all; the lifetime total is the launcher's own time), and administrator starts timed by
  watching; with it off, the old sentences and a pointer to the switch. Reports: 4's caveat ("never" is
  no time here, launched or seen), 5's caveat, empty sentence and idea (instrumentation versus
  observation, measurement resolution), 7's caveat, its part "Installed, timed only by watching or not
  at all" and its reason "timed only while the launcher watches". ANALIZA: the two sources (observed
  sessions, the no-double-count rule), reports 1, 4, 5 and 7's limits, report 5's new answer line and
  idea, report 7's list, a date line for Phase 93; every SQL block quoted from the code again (32).
  Suite 93 holds that none of the old sentences is left where it was.
- **The queries**: `BACKLOG` says "cannot tell" only for an Epic, Xbox or Ubisoft game with no time and
  no last played; `QUALITY_UNTIMED`'s reason; `SESSION_ORIGINS`, new (report 5's "How they were measured":
  started here, timed to the second; seen running, each end within a look). `NEEDS_VERSION` is 7. The
  eight reports: 44.9-45.2 ms (best of 5) on the copy, under the 50.
- **Which figures moved on the user's library**: none, the day this shipped -- his library held no
  observed session yet (122 sessions, all launched; his file still at version 6 until his next start).
  What will move as the launcher sees games: report 5 (sessions, the hours of the day, the night share --
  Steam games' sessions join them), Stats' month chart and week figures (every session), report 4's
  "cannot tell" (an Xbox game seen played leaves it), report 7's "who timed the hours" (an Epic or Xbox
  game's watched minutes are the launcher's). What will not: Steam games' hours in v_hours, reports 1,
  2, 3, 6 and 8 for Steam games (their hours stay Steam's counter), Stats' lifetime total for them.
- **The anonymous export**: format version 2 (`rules.ANALYSIS_FORMAT_VERSION`); `sessions.by_origin`
  (launched and observed, count and minutes), `sessions.origin_means` (what the two words mean, Romanian
  and English), per game `observed_sessions` and `observed_minutes`; `LibraryStore.analysis_source` reads
  the origin on a version-7 file. `compare_exports.py` reads a format-1 export as every session launched
  (`Participant.observed_*` 0) and a format-2 one with its split; participants.csv gains the two columns.
  Suite 81's "newer format" file is the current version plus one (it was a literal 2).
- **The first look is slow**: 94 ms once in a render run, against about 3 ms for every look after; the
  slow-look line in the log never counts the first.
- **Suite 93**, 78 checks now: sections 1-6 as above; the third switch (the row, on by default, its
  words, since when, off and on from Settings); a page while seen running (the pill, Play resting, no
  Stop, the tile, Play refused from five ways in, Play back when it ends), Recent sessions with "≈", the
  Continue card's pick; the export (format 2, the split, the per-game counts, its words) and a format-1
  export compared as launched; the old sentences gone from seven files, the new ones in Stats, report 5
  and ANALIZA; the reports' time; one look's time; the layers; the real data, config and Run key.
- **The first full run: 2611 of 2623**, and every net clean (imports, layers, paths, scanner, migration, the
  original folder). Suites 77, 79 and 82 found a real fault: the watch wrote `watch_games_since` at every
  start, so a first run's config.json existed before its question was answered and a friend's untouched
  file gained a key. The day is written now only when there is something to date -- the first observed
  session, or the switch turned on in Settings (`_keep_watch_since`); suite 93 holds that a start alone
  writes nothing. Suite 76's stand-in for `tile_subtitle` took two arguments, now three. **Suite 93's
  last check found the real library changed**: the user's own launcher (Phase 92's code, started 00:18)
  ran its tick scan at 01:48:07, inside the suite's 97 seconds -- a legitimate write. The same log
  showed the tick scanning every half hour for "Steam's playtime files due" (00:48, 01:18, 01:48):
  Steam rewrites localconfig.vdf without any play, so the rule fired nearly every beat -- repaired in
  its own commit after this one (the Phase 92 notes). After the fixes: 76 60/60, 77 74/74, 79 63/63,
  82 55/55, 93 79/79.
- **Tried by the user, 18 October**: version 7 ran at his start (03:16:12, a snapshot first); he played
  Aimlabs from Steam with the launcher in the tray and saw it shown as running: "works great". The log
  says "noticed Aimlabs running, started outside the launcher" (03:17:43) and "Aimlabs closed: 2 min,
  observed (each edge within 5 s); its hours stay its store's counter" (03:20:34). Checked read only
  after: version 7, the session with origin `observed`, and Aimlabs's launcher minutes in v_hours still
  0 beside Steam's 14,169 -- no hour counted twice. The look at 03:16:12 found 161 programs refusing
  their path, all Windows services, antivirus, VPN and driver helpers.
- **The explain-back, the same day, with Phase 94's**: he had a watcher for the games the launcher does
  not start, and Phase 94 as sleep no longer counted. Filled in: a running program is matched to a game
  by where its program file sits on disk (inside the game's install folder, which Steam's own record
  gives for a Steam game), never by a process id, which Windows hands out afresh at every start; every
  store's games are watched, the folder games among them (one started from its own exe is seen too),
  and a game the launcher's own Play started is left to its timer; the watcher only reads the list,
  asks Steam nothing and touches no game; a Steam game's session is kept, its hours stay Steam's.
- **The full run after his start: 2683 of 2690.** His library was now at version 7 with an observed
  session of his own, and three checks had been written for one that had none:
  - suite 93's "a start alone writes nothing to config.json for the watch": the copy carried his
    `watch_games_since`, written by his first observed session. `test_sandbox.NEVER_COPIED` drops it now:
    a copy begins as if nothing had been seen, as the first run's case needs;
  - suite 93's "every session the user's library had reads 'launched'": his copy was already at 7, so
    nothing was upgraded and his Aimlabs session read 'observed'. The suite now opens the copy without
    the sandbox's upgrade, takes it back to 6 with `undo_upgrades` (as suite 86 does), and lets the
    window's own open upgrade it: 123 sessions, every one 'launched'. 80/80;
  - suite 33's "Recent sessions appear exactly when there is something" still asked for exe games only;
    Aimlabs, a Steam game, now has a session and the card. Every game with sessions, since this phase. 60/60.
  Suite 79's real-data check met his launcher's tick at 03:46:12 (suite 79 ran 03:44:06-03:46:32): the
  repaired rule at work -- a Steam game seen played, so one scan, which landed Aimlabs's moved counter
  (Steam's minutes 14,169 -> 14,172; the launcher's still 0). 63/63 alone. Suites 52 (two pad-menu checks)
  and 56 (three focus checks): 17/17 on a third run alone, 32/32 alone. Every net clean.

## Phase 92 notes (the launcher lives in the tray)

Asked for as a brief: every reading the thesis depends on (prices, Steam's hours, the wishlists) is
taken with a scan, and a scan only ran when the window opened -- so the series grew only on the days
the launcher was opened, and closing the window ended the timing of a game still running. Step 0
replaced the freeze of 16 October with the feature window of 17 October (Build discipline), its own
commit; the user's go: "go with phase 92, record the tick as watch". Restore point `before-phase-92`,
on Phase 91's last commit.

- **Settings, "Running in the background"**, after "Controller and TV": "Keep running when the window
  is closed" (`rules.KEEP_RUNNING_KEY`, `keep_running`), off by default so no copy changes until
  someone touches it; Settings' answers carry it, written with Settings' own keys on OK, as every row.
- **The tray icon** (`presentation/ui_tray.py`, `Tray`, owned by the window): exactly while the switch
  is on; launcher.ico, the tooltip "Game Launcher", or "Playing <name> for 1h 12m" while a game started
  from here is timed (`ui_tray.tooltip`, refreshed by `_bank_playtime` -- once a minute -- and when a
  session starts or ends; the names from the tracker, since a bank reloads the views). A left click or
  a double click: `MainWindow.bring_forward` (shown, un-minimised, through `focus.bring_to_front` --
  Phase 28's lock applies to a tray click too). The menu, a child of the window so it wears its
  stylesheet, filled each time it opens: Open Game Launcher; the `RECENT_TRAY_GAMES` (5) games played
  last (`ui_tray.recent_games`: a game running now first, then by last played, never a hidden game, a
  demo or tool, or one never played), "Play <name>" through `window._play_key` -> `ui_actions.play`,
  "Stop <name>" through `_stop_key` -> `ui_actions.stop` and its question; Rescan (off while a scan
  runs); Settings...; Quit. A name's "&" is doubled (a menu reads it as a shortcut letter).
- **A close with the switch on hides** (`closeEvent` -> `hide_to_tray`): the playtime polled and banked
  at that moment, the window's place saved, hidden; the poll timer, the pad's poll, the folder watch
  and every worker go on; a game being timed goes on being timed and banked, and its session is written
  and its saves looked at when it ends. The first hide ever says, through the icon, "Game Launcher is
  still running here. Right-click the icon to quit, or turn this off in Settings." -- once,
  `rules.TRAY_HINT_KEY` (`tray_hint_shown`) written by its own key. In TV mode a close hides too; Escape
  still leaves TV mode. While in the tray the status queue holds nothing (`queue_status` drops and logs
  at debug): there is nothing to show it on, and a message kept for hours would be stale.
- **Qt quits when the last window closes**, and with the window hidden every dialog -- Stop's
  question, Settings opened from the tray -- is the last window: closing it would have quit the
  launcher. `_apply_keep_running` turns that off while the tray holds the launcher and on again with
  the switch. A close that is not a hide with it still off (no tray to hide into, or Windows signing
  out -- `isSavingSession`, whose close must never be refused or the sign-out stalls) quits explicitly
  (`_exit_application`), so the launcher is never left running with no window and no icon.
- **Quit** (`quit_launcher`) and a real close share `MainWindow.shutdown()`, once (`_shut_down`): the
  old closeEvent's body, in its order -- the hooks, the timers, the pad, the folder watch, the save copy
  waited for, the downloads and the workers, the window's place, the scan waited for, the playtime
  polled and banked, the database let go of -- then the icon hidden. **The brief listed "bank" first;
  the code banks last** (after the threads stop, so the seconds spent waiting are counted) and that
  order was kept; suite 92 records the calls and holds it.
- **Off while hidden** (Settings' OK from the tray menu): the window is shown at once, the icon removed,
  quitting on the last close restored; the next close quits. Settings' switches apply on OK, as every
  other setting; Cancel changes nothing.
- **TV mode while in the tray**: Settings' OK re-applies the mode (Phase 72), and `set_tv_mode` would
  have shown the window fullscreen; in the tray it sets the window's state alone, for when it is
  brought back.
- **Phase 28 in the tray**: a game ending while the window is in the tray leaves it there -- started
  from the tray menu with the window hidden, or hidden while the game ran. The brief said "comes back
  only if it was on screen when the game started"; the case of a window closed to the tray during the
  game stays hidden too, because closing it was the user's word.
- **One launcher at a time** (`adapters/single_instance.py`): `key(data_dir)` is `GameLauncher-` and
  16 hex digits of a sha256 of the data folder's path (normalised: case, a trailing backslash), so a
  copy with data of its own -- an installed one, a test's sandbox -- has its own lock and channel and
  never answers for another. The lock is `QLockFile` in the temp folder (`%TEMP%\GameLauncher-....lock`),
  not the data folder, so the installer's keep-list never meets it. Measured first on this machine,
  with another process as the owner: while it lives the lock is refused (Windows keeps the file open)
  even past its age; killed, it leaves the file behind and the next start takes it over -- Qt reads
  the owner's process id. The stale time is 0: never judged by age, only by whether the owner lives.
  The channel is a `QLocalServer` (a named pipe), open to this user only.
- **The order at start** (`launcher.main`): the taskbar identity claimed (before QApplication, as
  always), QApplication, then the lock -- before the window, so before anything reads or writes the
  library or takes the startup snapshot. Held elsewhere: `second_start` asks on the channel ("show", or
  "show tv" for `--tv`), trying again while the running one may still be building its window, and
  ends with 0 on its "ok" -- `MainWindow.bring_forward(tv)`, shown after the answer is sent. No answer
  within `SINGLE_INSTANCE_TIMEOUT_MS` (10 s): "Game Launcher is already running but not responding;
  check the tray or Task Manager.", and the end, code 1 -- never a second launcher over a wedged one.
- **`--background`** (`rules.BACKGROUND_ARGUMENT`; `launcher.present`): the tray icon and no window
  (`MainWindow.start_hidden`). A first run (no config.json) shows the window, to ask where the games
  are; Keep running off is a contradiction (nothing to hide into): shown, and the log says why. A
  window first shown from the tray opens in TV mode if the saved setting says so, as the plain shortcut
  would.
- **One startup routine** (`MainWindow.begin`, once): the startup scan after `STARTUP_SCAN_DELAY_MS`,
  the first look for saves after `SAVES_STARTUP_DELAY_MS`, the update check after
  `UPDATE_CHECK_DELAY_MS`. The window's first show calls it, and so does a hidden start; the hint
  hooks, the window's taskbar tags, the first-run question and the tiles' first wave stay with the
  first show.
- **The tray late at sign-in**: Windows starts the Run entries before the shell has its tray.
  `ui_window.tray_available()` (`QSystemTrayIcon.isSystemTrayAvailable`) is asked every
  `TRAY_RETRY_MS` (2 s) for `TRAY_RETRY_MAX_S` (120 s); the icon appears when it can, and if it never
  can the window is shown. Meanwhile a close quits (there is nothing to hide into). Never a launcher
  with no window and no icon.
- **Not tried on the real data**: while the user's launcher (the code before this phase, which holds
  no lock) is open, a new `launcher.py` from source would be a second launcher on the same library.
  Every start in suite 92 is on a sandbox copy; the second starts are real processes started there.
- **Suite 32's see-through check** sampled the glow of whichever game the backdrop followed at one
  point between the first two tiles, and that game's art was the ground's colour there (22, 24, 37)
  after the user's library changed -- failing alone and the same way on the code before this phase
  (four app files copied aside, put back at the tag, run, copied back, identical by sha256). It now
  glows a game it can tell there first, as suite 56 was changed in Phase 63. Its "card at full
  height" check failed once in three runs (0 px after 0.6 s on a busy machine), the other two green.
- **The tick** (`MainWindow._tick`, `rules.BACKGROUND_TICK_MINUTES` = 30, started by `begin()`, stopped by
  `shutdown()`), shown or hidden: the update check first (`_check_for_updates(quiet=True)`: web.updates
  keeps its once a day, `UPDATE_CHECK_HOURS`, which already was the daily interval; from source it
  never asks), then `readings_due()` -- `prices.due` and `wishlist.due` asked with `say=False` (logged
  at debug, not as "this scan") and Steam's playtime files. **`steam_time.due` is not a cadence**: it
  answers yes whenever the library can keep Steam's hours, so taken as the brief wrote it the tick
  would scan every half hour. The tick asks instead whether an account's localconfig.vdf was written
  since the last scan began (`steam_time.files_changed_since`, `steam_userdata.localconfig_files`:
  file dates, local, no network, no database). A reading due, no game started from here running, no
  scan under way, not a first run: a quiet scan (`start_scan(background=True, trigger="watch")`).
  **Recorded as `watch`, the user's choice** ("record the tick as watch"): `scan.trigger` takes six
  fixed reasons (a CHECK), "tick" would be refused and the scan's findings lost, and allowing it would
  be a schema change; launcher.log names the tick ("tick: prices due; a quiet scan (recorded as a watch
  scan)"), at info when it scans and at debug when it does not, and why not. **What a day in the tray
  costs in requests**: what a day of opening the launcher once costs -- the due rules decide (a
  wishlist once in 20 hours per account, a wished game's price once in 20 hours in the daily batch,
  the rest weekly, at most `PRICE_REQUESTS_PER_SCAN` a scan). The one difference: the records of
  Steam-history apps with none (20 a scan) arrive over fewer days, each still fetched once.
- **Start with Windows** (`logic/autostart.py`): HKCU's `...\CurrentVersion\Run`, value "Game
  Launcher" (`rules.STARTUP_*`): from source `"<project>\.venv\Scripts\pythonw.exe"
  "<project>\launcher.py" --background`, installed `"<GameLauncher.exe>" --background` --
  `taskbar.launch_command` decides, as for the shortcuts; written again it writes the same (an
  idempotent startup entry). No shortcut, so the shortcuts' app-id trap does not apply. **Windows'
  Startup apps toggle** never deletes the value: it writes a 12-byte REG_BINARY of the same name under
  `...\Explorer\StartupApproved\Run`. Read off this PC first (read only): 23 entries, every one 12
  bytes, the first byte 02 for those allowed (Steam, LGHUB, GoogleDriveFS) and 03 for those turned off
  (Discord, OneDrive, EpicGamesLauncher...); Run values never toggled (Claude) have none. So an odd
  first byte is off, none is on; the launcher reads it and never writes it (it is Windows' record of
  the user's choice). The user confirmed it in Task Manager on 18 October: Steam "Enabled", Discord
  "Disabled".
- **The switch has no key in config.json**: the Run value is its record (`autostart.state()`: on,
  off, or blocked -- there, and Windows has it off), so it never disagrees with what sign-in will do.
  Settings' row "Start with Windows" under Keep running: "Starts hidden in the tray when you sign in.",
  or "Windows has turned this off in Startup apps. Turn it back on there (Task Manager, Startup apps),
  or switch it off here." with the switch off. Turning it on turns Keep running on; Keep running off
  turns it off; `values()` answers Keep running on whenever it is on. Only a change is written, on OK
  (`dialog.start_with_windows()` against `started_with_windows`): on writes the value, off deletes it,
  Keep running untouched.
- **`shared/registry.py`** gained `read_binary`, `write_string` (making the key if missing) and
  `delete_value` (absent counts as deleted), non-raising, logged, as the readers are.
- **The uninstall** (`logic/uninstall.run`) calls `autostart.remove_if_ours(sys.executable)` after the
  Add/Remove entry: the value goes if it starts this exe (compared as paths, case aside), and a value
  that starts another copy -- one run from source -- stays. The installer's upgrade never touches it
  (the exe keeps its path, the value stays right).
- **No test touches the real Run key.** `test_sandbox.start()` sets `GAME_LAUNCHER_TEST_STARTUP_KEY`
  to `Software\GameLauncherTest\<the sandbox's folder>` for the process and every child it starts --
  `autostart.keys()` then answers `<root>\Run` and `<root>\StartupApproved\Run` -- photographs the
  real value and its StartupApproved bytes (`real_startup`, in `real_changes`), and `finish()` deletes
  its own key and the empty root. `check_installer.py` does the same for every process it starts
  (`installer-<pid>`), since HKCU cannot be redirected the way the profile's folders are: the value,
  planted as the installed copy writes it, is unchanged after the update and gone after the uninstall;
  the real value compared before and after. **38/38** on the build of this code (the update check's one
  real request answered 1.2.5); the build was for the proof only -- `dist\GameLauncher-Setup.exe` was
  put back to the published 1.2.5 after (sha256 `97d3f80e...1125096d`, the same file as before). The
  build carries `Qt6Network.dll` and `QtNetwork.pyd` (the channel) and the three new modules.
- **Docs**: ARHITECTURA 5.3 "Viața în fundal" (one paragraph: start, shown or hidden; the tick; the
  readings; Quit); CITESTE-MA "Să rămână pornit în fundal" (the two switches in the friends' words, how
  each is turned off, Quit in the icon's menu, a second click on the shortcut) and a line under
  Dezinstalare; DISTRIBUTIE §1 (the Run value, Windows' toggle, what an update keeps and the uninstall
  removes) and §5 (the two checks, the test key). **No version bump and no release**: the friends keep
  1.2.5 until the user says "release"; CITESTE-MA describes the switches for the version that will carry
  them.
- **Suite 92**, 98 checks: the switch and its section; the tray, its tooltip and its menu (Play through
  `ui_actions.play`); a real shim game (cmd starting pythonw in the job and gone) banked at the hide and
  growing after it; the balloon once; the game ending in the tray; Keep running off while hidden; Quit's
  order recorded; the lock (a live owner refused, a killed one's taken over); a real second start and
  one with `--tv`, `launcher.py` in another process on the sandbox's data (0.8 s, exit 0); a wedged
  owner (1.6 s, the message, exit 1, the box stood in for); `--background` hidden, shown on a first run
  or with Keep running off; the tray late and never; Start with Windows in the dialog (linked both
  ways, the pad working both rows, Windows' off said in words) and on the test key (both command forms,
  02/03/no bytes, delete, the uninstall's rule, Settings' OK writing only a change); the tick's decision
  table. Proven both ways: 98/98; with the eleven changed app files put back as at the tag and the three
  new ones set aside (copied aside and back, identical by sha256), 15 failures and 5 passes (a tray here,
  the shim timed, its session ending, the layers, the real data). The new modules are imported
  tolerantly so each section fails on its own on the old code, not the whole suite at its first import.
- **The full run: 2560 of 2562**, and the scanner net with 1 difference. Suite 73's "nothing is due any
  more" failed once in the long run (83/83 alone; this phase changed `prices.due` only in what it logs).
  Suite 78 holds CITESTE-MA to a page (110 lines): the new section made it 118, so it was shortened to
  fit (31/31). The scanner net found the user's Max Payne 3 (`c:\games\max.payne.3.v1.0.0.272`,
  installed on 17 October at 03:38): the saved run saved again, the old one kept as
  `tests/baseline/scanner-until-2026-10-18.json`, then 0 differences. Every other net clean: imports,
  layers (0 upward, sqlite3 only in data_access/), paths 20/20, the migration, the original folder.
- **Repaired at Phase 93's step 0** (18 October, the log read from the Phase 92 commits on): the user's
  first day was clean -- every hide, show, Quit, the Run value written as planned, no warning -- but
  (1) the tick logged its "nothing due" at debug, which launcher.log never holds, so whether it fired
  could not be told from the file (neither run so far had lasted the first 30 minutes): every beat now
  says its decision at info, one line in half an hour; (2) a double click on the icon arrives as a
  click and a double click, and the window was brought back twice (00:11:50.97, 00:11:51.15): the click
  alone acts; (3) the user now runs with Keep running on and the balloon seen, the sandbox copied both,
  and suite 92's balloon checks found it already said (and every older suite's window would hide on
  close): `keep_running` and `tray_hint_shown` joined `NEVER_COPIED`. Suite 92 98/98, paths 20/20.
- **Repaired again, after Phase 93's first full run** (its own commit): the log of the user's running
  launcher showed the tick scanning every half hour, each time for "Steam's playtime files due" (00:48,
  01:18, 01:48 on 18 October), and each reading landing no changed counter. Steam rewrites
  localconfig.vdf with no play at all, so "written since the last scan" was true nearly every beat --
  a disk walk and a write of the library 48 times a day for nothing, and a write that can land inside
  any suite's run (suite 93's real-data check met one at 01:48:07). Now the files are due only when
  they were written AND either a Steam game was seen being played since the last scan (Phase 93's
  watch: `_steam_played_since_scan`, set when an observed Steam session ends) or the last scan is
  `STEAM_TIME_TICK_HOURS` (12) old. Suite 92's tick table asks the three cases (100/100); suite 93 that
  a Steam game's session ending marks the files due.
- **The full run after the repair: 2643 of 2644**, every net clean. The one was suite 86's real-data
  check: it ran 02:17:54-02:18:11 and the user's own launcher, still on the Phase 92 code (it was
  started before either commit), made a tick's scan at 02:18:07, writing his library mid-check. Alone,
  at 02:22, suite 86 passed 95 of 95. The repaired tick takes effect at his next start, with version 7.

## Phase 91 notes (three corrections to the analysis; the build log out of CLAUDE.md; the feature freeze)

Asked for as a brief ("the last building phase": the thesis is judged on what the database can say,
and three reports said something a statistician would challenge). Step 0 measured, read only, on a
copy, and matched the user's three figures exactly; approved as "go with phase 91, and yes switch the
proxy". One tag (`before-phase-91`, on Phase 90's publish) before three commits: the corrections with
ANALIZA; the move to ISTORIC; the freeze. Nothing touches the schema or the data.

- **Step 0's figures (16 October, a copy)**: report 2's 315 started games -- under two hours 55 free, 37
  no record, 82 paid (174); two hours or more 38, 20, 83 (141); the same whichever kind is tried first;
  24 of the 165 paid no longer sold. Played games with a genre: 271 (Action 76%, Adventure 42%, Indie
  41%, ...). Installed Steam titles: 22, 18 priced, 723,75 € at list price and 720,25 € today, one on
  sale (Cinderia -20%); the never-played backlog 89,24 € both ways.
- **1. Report 2.** ABANDONMENT gains a `started` CTE giving each app its kind and three sums per bucket.
  **Both free signals count** (`rules.REPORT_APP_KINDS`' comment): of the games started, 65 carry both,
  8 only Steam's `is_free` flag (games given away: Cry of Fear, Life is Strange Episode 1), 20 only the
  Free To Play genre (Loadout, Robocraft). No record (`has_record` 0) is "unknown"; a game no longer sold
  is paid. The bars stay on all games; the six-bucket table (the CSV's) gains Paid, Free, No record; a
  visible table "Under two hours, by kind" gives the refund window's three buckets, under and over, and
  each kind's own share -- paid 50%, free 59%, no record 65%, which is the confounding said in numbers.
  The sentence is the brief's: "Of the 165 paid games started on Steam, 82 (50%) stayed under two
  hours, Steam's refund window; another 55 free-to-play titles and 37 apps with no store record were
  also left under two hours and are counted apart." The caveat: a threshold of time only, no purchase
  date. The idea: the confounding variable, the business model, report 3's line.
- **2. Report 8.** STATED_REVEALED's `played` and `played_all` count the games as well as sum the
  minutes (`played_games`, `played_games_all`) -- the same `games`, minutes > 0, the not-genres out. A
  third list of bars, "In the games you have played", sits between the wishlist's and the hours'; all
  three share one order (the largest of the three shares first). The table: Genre, Wishlist, Games
  played, Hours, "Wishlist − hours" -- one gap, named in its heading. The CSV: `played_share`. The
  sentence: "Indie is on 71% of your wished games, in 41% of the games you have played and in 17% of
  your hours; Action the other way: ...". The two-game rule stays. The caveat: the hours column is
  steep (report 1's concentration); the idea: the extensive and the intensive margin. **"+1 points"**
  read wrong in the table: `_points` says "+1 point".
- **3. Reports 6 and 4.** MONEY_LIBRARY's `list_cents` was the sum of `final_cents` -- today's price,
  sales included, called a list price; now `list_cents` is the undiscounted `initial_cents`,
  `today_cents` today's, `on_sale` the titles discounted. The sentence: "Your installed library lists at
  723,75 € and would cost 720,25 € to buy today (1 of 18 titles on sale)", or "lists at X and would cost
  the same to buy today (none of N titles on sale)". BACKLOG gains `initial_cents`; `_value` answers
  (list, today, currencies) and `value_words` one figure when equal ("89,24 € at list price and today")
  or both; the backlog's tables show both prices under their own headings. **The stand-in per hour
  divides the list price** (MONEY_PROXY, the user's yes): it divided today's, so a sale made an hour
  look cheaper. Nothing on a game's own page changed (`v_game_money` is its own).
- **MONEY_LIBRARY read `v_hours` for nothing**: it uses the installed games' Steam numbers, not their
  hours, but the `installed` CTE joins `v_hours` through an OR condition. `INSTALLED_TITLES` is the same
  rule (`INSTALLED_RULE`, shared) without the join: 3.4 -> 0.5 ms, the same row. Every other query's text
  is byte for byte what it was (checked against the queries as they stood). **The eight reports take
  42-47 ms** on the real library, under the brief's 50.
- **ANALIZA**: the date line says which reports carry which day (1, 3, 5, 7: 14 October; 2, 4, 6, 8: 16
  October; the wishlist section 15 October); the five changed queries quoted from the code by a script;
  each answer rewritten from `reports.py --markdown` on a copy, with what changed from the 14th said
  (report 2's 56% mixed free and paid games; report 6's "750,25 € at list price" was today's prices);
  the caveats and ideas gained the confounding variable, the extensive and intensive margin with the
  concentration, list price against replacement value.
- **Suite 86's time bomb, found by this phase's run**: its section 4 landed a first wishlist read at the
  real moment and then "later" reads dated 16-18 October at fixed hours. Written on the 15th, they were
  later; run on the 16th at 23:39 the read of the 16th at 12:00 was older than the real one, and the
  store rightly does not apply an older answer -- 4 failures, the code unchanged. The later reads are now
  dated from the real one (`after(days)`). 95/95.
- `tests/phase91_tests.py`, sections 1-4 here (40 checks): the kinds on a made-up library (the flag, the
  genre and both each free once; no record unknown; no longer sold paid; under and over two hours; the
  sentence; the table by kind; the caveat; the idea; no paid game at all); report 8's games played by
  hand (a game with no minutes and one whose only genre is Free To Play left out), the three lists in
  one order, the one gap, the CSV; on the real copy the counts equal to report 3's and to a direct
  count; the money with a planted sale and without, the backlog in both reports, the stand-in on the
  list price; nothing written, `query_only` put back; `reports.py --markdown` and `--csv`; ANALIZA; the
  time. Proven both ways: 40/40; with the three app files put back as at the tag (copied aside and back,
  identical by sha256), 6 failures and 8 passes (nothing written, the documents' dates and ideas, the
  time, the layers, the network, the real data). Suite 83 asks the paid sentence, 89,96 € at list price
  and 59,97 € today, and the stand-in at 59,98 € over 10 hours; suite 89 the three measures. 83 70/70,
  84 36/36, 86 95/95, 89 45/45.
- Rendered on a copy at 1280 x 900: the kind table, the money table's two figures and the three-measure
  table sit inside the cards; nothing wraps.
- **The build log out of CLAUDE.md** (the second commit): CLAUDE.md weighed 479 KB on disk, 404 of them the
  phase notes and the sections "reported from use" -- all loaded at the start of every session. Every
  section but the nine kept (What this is, Build discipline with the table and the network list,
  Architecture and the file layout, Commands, Domain rules, Deliberate departures, Constraints,
  Environment) moved here by a script, verbatim and in their order: 98 sections, 89 of them "## Phase N
  notes", the Windows integration, Packaging, EA and network-layer notes among the rest (their standing
  rules became lessons). The script refused to write unless every old heading was here and none left
  there, and the kept and moved texts added up to the old file exactly. "Lessons that still bind": 88
  lines in 108, each with its phase. Four cross-references point here now (the EA row and the layout's
  "see below", row 51's Phase 38 notes, the Commands' Windows integration notes). CLAUDE.md: 87 KB.
- **The suites that asked for their notes in CLAUDE.md** (80, 82-90) ask `sources.build_log()` -- one
  function in tests/sources.py reading this file -- and still find their row in CLAUDE.md's table.
  `check_move_diff`'s NOT_APP already covered `docs/`.
- **`.gitattributes`** (`* text=auto`): the index was LF everywhere (219 text files LF, 43 binary -- jpg,
  ttf, ico, pdf, rightly so -- and 6 one-line JSON fixtures with no line end), so `git add --renormalize
  .` in a clean worktree of the first commit staged the new file and nothing else. No binary line: git
  misdetects no type here.
- **The feature freeze** (the third commit): a paragraph in CLAUDE.md's Build discipline, dated 16 October
  2026 -- repairs reported from use and the thesis's own needs only, until the user writes "freeze lifted"
  -- and row 91 says so. CITESTE-MA and DISTRIBUTIE untouched (suite 91 compares them with the tag); no
  1.2.6: the friends keep 1.2.5, which Phase 91 changes nothing in.
- **Suite 72 asked for a window the machine no longer gives it.** The user switched TV mode on in Settings
  on 16 October (config.json written at 00:08), and a saved TV mode makes launcher.py open fullscreen. The
  sandbox copies that setting, but suite 72 builds its window directly, at the desk, so Settings' OK -- the
  dialog built from the copied settings -- rightly went to TV mode: "after OK it is still maximised" read
  (False, True), alone too, and the same on the three app files put back as at the tag. Nothing in the
  launcher was wrong; the suite now asks for the desk in its copy (`start({"tv_mode": False})`), 23/23.
  The same assumption as Phases 26 and 62: a suite asks for the state it tests.
- **The full run: 2463 of 2464**, the one suite 72's check above (fixed after, 23/23 alone). The scanner
  net found 2 differences, the user's library again: Clive Barker's Hellraiser Revival installed on 15
  October (and played 3h 20m), Gears of War: E-Day gone from C:\XboxGames. The saved run was saved again,
  the old one kept as `tests/baseline/scanner-until-2026-10-16.json`, and then 0 differences. Every other
  net clean: imports, layers (0 upward, sqlite3 only in data_access/), paths, the migration, the original
  folder untouched. Suite 28 passed this time.

## Phase 90 notes (release 1.2.5: Phase 89 in the friends' version)

The user's "let's build and publish it for my friends too if that hasn't been done already" (16
October) -- it had not: GitHub's latest was 1.2.4. Both words in one message, so the build and the
publish are one phase, as 1.2.4's were two commits of Phase 88. Tag `before-phase-90` on Phase 89's
commit.

- **What the friends get**: Phase 89 -- the rarity-weighted fit line on the Wishlist page, report 8
  (Stated and revealed) on the Reports page, and a line of each wished game's prices from its third
  price. **No schema change** (still version 6, the last script 006), so a friend's library is not
  upgraded and no snapshot is taken for one; the anonymous export's format is the same.
- **The documents**: CITESTE-MA "Versiunea 1.2.5." and "opt rapoarte"; DISTRIBUTIE §3 (the version,
  the log line, the list of releases with 1.2.5), §5 and §9 (the check and the publish, below), §7's
  Sandbox step 5. `shared/version.py`'s history line. Suite 88 asked for 1.2.4 exactly and
  "Versiunea 1.2.4."; it now asks for 1.2.4 or later and the current version in the friends' note (85's
  were loosened the same way in Phase 88).
- **The build** (16 October): 31 s, 266 files (as 1.2.4: no new file), a 69 MB installer (72,064,086
  bytes, sha256 `97d3f80e...1125096d`), stamped 1.2.5 and built 2026-10-16. The 1.2.4 installer was
  kept aside first (sha256 `79c724c2...ff2e6a3`, the file published on 15 October).
- **`check_installer.py --over` the real 1.2.4: 45/45** -- sections 1-7 (stamped 1.2.5, Add/Remove 1.2.5,
  both first-run questions, the log's "Game Launcher 1.2.5", GitHub asked once for real and answering
  1.2.4 -- nothing newer offered -- not asked again that day, the update over it byte for byte, a quiet
  uninstall keeping the data, the four real shortcuts untouched) and section 8: 1.2.4 installed and
  started as a friend's PC starts it (a library at schema 6, 11 game rows), this installer over it,
  started as 1.2.5 with no question, "the same schema version, 6: nothing to upgrade", all nine views
  answering, the games row for row and the settings as 1.2.4 left them, no error. **Two checks fewer
  than 1.2.4's 47 by design**: with no schema change, the two upgrade checks (the version reached, the
  snapshot holding the older one) become that one line.
- **Before the publish**: the SteamGridDB key in none of the 266 files, nor in payload.zip's members,
  nor in Setup.exe; no config, library, overrides, catalogue or log among the files; the user's e-mail
  address nowhere in them either.
- `tests/phase90_tests.py`, 11 checks: the version and that it is newer than 1.2.4; the schema 1.2.4's
  (version 6, the last script 006); eight reports, the eighth `preference`; check_installer's `--over`;
  CITESTE-MA (1.2.5, "opt rapoarte", no "șapte rapoarte"), DISTRIBUTIE, CLAUDE.md; the layers; no
  network; the real data untouched.
- **Published on 16 October** on the user's word, given with the build's ("let's build and publish it for
  my friends too"): `gh release create v1.2.5 dist/GameLauncher-Setup.exe --repo
  GreenYRO/game-launcher-releases --target main --title 1.2.5`, the notes in Romanian like 1.2.4's (the
  Wishlist's fit telling games apart, the price line from a game's third price, report 8; the library
  not changed; run the new Setup.exe over the old). Read back through `updates.fetch`: 1.2.5, not a
  draft or pre-release, newer than 1.2.4 and not newer than itself; GitHub's asset digest is the local
  file's sha256 (`97d3f80e...1125096d`, 72,064,086 bytes). The friends' 1.2.4 copies will say 1.2.5 is
  out within a day. Suites 77 74/74, 79 63/63, 80 51/51, 82 55/55, 85 17/17, 88 10/10, 89 45/45 and
  90 11/11 on this code; the code is Phase 89's, whose full run was 2398 of 2402 (suite 28's
  foreground checks, the screen idle), so the full run was not repeated for a version and two
  documents.

## Phase 89 notes (the wishlist's three extensions: a sharper fit, report 8, a price line)

Offered after 1.2.4 as three things the four ideas could still give, and asked for together: "publish
it, and go with 1 and 2 AND 3" (the publish was Phase 88's). One phase, one tag (`before-phase-89`, on
the 1.2.4 publish commit), no new table, no new address, no new dependency.

- **1. The fit, measured first on a copy.** Phase 86's union of the hours put 9 of the 16 wished games
  at 87-99%: Action holds 87% of the hours with a genre, so any game with Action read near the top
  and the figure stopped telling games apart. Now each genre weighs `ln(apps with a genre / apps with
  it)` over every app the database has a record of (306 on 15 October; `wishlist_idf`, Free To Play
  and the descriptors out as everywhere): Action 0.30 (227 apps), Adventure 0.80, Indie 0.84,
  Simulation 1.55, Strategy 2.01 (41). A game is the vector of its genres' weights, of length 1; the
  hours are every played game's vector times its minutes, summed, of length 1 (`taste`); the fit is
  their dot product, the cosine -- TF-IDF and cosine similarity, the textbook content-based
  filtering. The row says "33% like what you play · Strategy, Action", the (at most two,
  `WISHLIST_FIT_GENRES_NAMED`) genres that add the most; "unlike what you play" at 0, "under 1%"
  below half a percent. **A one-genre game is that genre, however common**: Deadlock (Action only)
  reads 94% because the hours are nearly all Action, not because Action says much -- the weight
  matters only between a game's own genres; ANALIZA says so. A game whose genres all weigh 0 says
  "no genre to compare". The before/after table for all 16 is in ANALIZA.
- **2. Report 8, Stated and revealed** (`logic/reports.preference`, key `preference`): per genre, the
  share of the wished games now on a marked account's list (that have a genre) against the share of
  the minutes (report 3's games and genres -- suite 89 holds the minutes equal to `profile_genres`),
  and the gap in points. Two lists of bars in one order (the larger of the two shares first) so
  they read across, and a side-by-side table; the CSV has the shares as numbers. The sentence names
  the largest positive gap among genres on at least `REPORT_STATED_MIN_GAMES` (2) wished games -- one
  game is 6 points of 16, and should not make a headline -- and the largest negative. On 15 October:
  **Indie on 75% of the wishes and 17% of the hours; Action 87% of the hours, 62% of the wishes.** The
  idea: stated and revealed preference, the intention-behaviour gap -- which here may also be a game
  not bought yet; the caveat says the data cannot tell them apart.
- **The query reads the `wishlist` table, not `v_wishlist_now`**: the first form read the view twice
  (6.25 ms, the slowest query); the lists themselves are all it needs (4.0 ms, the same rows -- suite
  89 holds the wished counts equal to the view's). **The eight reports take 43-47 ms** on the real
  library (best of 3-5) against the brief's 50 for seven: close. The heaviest are still money_library
  (4.3), stated_revealed (4.0), money_lowest (3.5) -- each reads `v_hours`. If the budget is ever
  broken, materialising `v_hours` once per page is the lever, not any one report.
- **Suite 83's copy has no wishlist**: its section 1 takes the copy back to version 4 and up again,
  which drops and re-makes version 6's tables empty. Its "none empty on the real library" now asks
  the first seven to answer and the eighth to be empty exactly when the copy holds no list.
- **3. The price line** (`Row.series`, `WishlistDelegate._paint_series`, `spark_rect`): from the
  third priced observation (`WISHLIST_SERIES_MIN`), only those in today's currency (a zloty price
  among euro ones is dropped, and with it the line if fewer than three remain), never for "Free" or
  "Not sold". 72 x 24 px in the accent, just left of the price column, the same place on every row
  (a column of lines, as in a table); oldest on the left, today's the dot, lower cheaper; a price
  that never moved is a flat line through the middle. The row's words stop before it. **On the day
  it shipped no row draws one**: daily prices for wished games began on 15 October, so the first
  lines appear on the 17th. Rendered with a planted week in a sandbox (100% and TV): it reads.
- **Words that changed elsewhere**: ui_reports' INTRO ("Eight questions ... the seventh card shows
  them" -- the set-aside apps are report 7, no longer the last), the docstrings of ui_reports,
  ui_window, ui_rules, reports.py, logic/reports; ANALIZA's title "opt rapoarte", its date line, the
  contents, the fit section rewritten (the formula, the table, the caveats, TF-IDF, cosine
  similarity, sparkline as ideas), the price line with `wishlist_series`, "## 8. Declarat și
  dezvăluit" with `stated_revealed`. **The friends' documents are untouched** (CITESTE-MA still
  says what 1.2.4 does) until a release carries this.
- `tests/phase89_tests.py`, 45 checks: the weights against the test's own count, the vectors of
  length 1, every fit in [0, 1] and in the page's words naming only the game's own genres; report 8
  on a made-up library worked out by hand (an account not mine, a game taken off, Free To Play and a
  record not fetched all left out; 67% / 10% and 33% / 90%; the gaps; the bars; the note; the CSV),
  the two-game rule, no wishlist and no genre in words, an empty library's eight; report 8 on the
  real copy by two other roads; the Reports page's eighth card at 100% and TV; the line's rules and,
  on the live window with a planted week in the copy, accent pixels where a row has prices and none
  where it has not; the time; the documents; the layers. Suite 86's section 6 asks the new fit by
  hand-worked cosines (1/sqrt(2) = 71%, 1/sqrt(10) = 32%, 4/sqrt(20) = 89%, a common genre with a rare
  one 5% where the union said 90%). Proven both ways: 45/45; with the nine changed app files put back
  as at the tag (copied aside, then back, identical by sha256 -- not stashed: a stash pop rewrote
  line endings in Phase 82), 8 failures and 2 passes (no network, the real data untouched).
- **The full run: 2398 of 2402**, the 4 in suite 28 (the launcher coming back to the front after a game):
  `GetForegroundWindow` answered 0 -- no window had the foreground at all, the screen idle while the
  user followed from another device -- so its probe could not start behind another program. Alone it
  failed the same 4, and the same 4 on the nine app files put back as at the tag (copied aside and back,
  identical by sha256). Nothing here touches focus. Suite 22 at 46 (no pad plugged in). Every net clean:
  imports, layers (0 upward, sqlite3 only in data_access/), paths 20/20, the scanner 0 differences, the
  migration (69 records, 320 Steam apps, nothing refused), the original folder untouched.

## Phase 88 notes (release 1.2.4: the wishlist in the friends' version)

The user's "restarted it, wishlist tab works - build 1.2.4 for them" -- 1.2.4 by his own rule (each
release raises the last number), not the 1.3.0 the brief floated. "Build" is not "publish": the
release waits for its own word, as every publish does.

- **What the friends get**: Phases 86-87 -- their library upgraded to schema version 6 at the first
  start after the update (a snapshot first; additive), the eighth address (their accounts marked
  theirs read once a day, the account's number going only to Steam -- CITESTE-MA says so since Phase
  86), wished games' prices asked daily, the Wishlist tab. A friend who marks no account, or whose
  lists are private, gets the page's words for that and nothing read.
- **The friends' path, proven with the real 1.2.3 installer** (kept aside before the build; sha256
  `79e5e942...84df716e`, the file published on 15 October): `check_installer.py --over <it>` **47/47** --
  sections 1-7 (stamped 1.2.4, both first-run questions, GitHub asked once for real and answering 1.2.3,
  nothing newer offered; the update over it byte for byte) and section 8: 1.2.3 installed and started as a
  friend's PC starts it (a library at schema 5, 12 game rows), this installer over it, the updated copy
  bringing it to 6 with the startup snapshot holding version 5, all nine views answering, the games and
  the settings as the old version left them, no error.
- **The build**: 31 s, 266 files (one more than 1.2.3: `006_wishlist.sql`), a 69 MB installer
  (72,055,112 bytes, sha256 `79c724c2...ff2e6a3`). The SteamGridDB key in none of the 266 files nor
  Setup.exe, and no config, library or log among them.
- **Tests**: suite 88, 10 checks (the version and that it is newer than 1.2.3, the upgrade scripts
  bundled with 006, the documents, the layers); suite 85's "version 1.2.3" and "Versiunea 1.2.3" now
  ask for 1.2.3 or later and the current version (82's were loosened the same way in Phase 85). The
  suites that read the version and the documents alone: 77 74/74 (its first run in a batch printed no
  result line, cause not captured; alone it passed), 79 63/63, 80 51/51, 82 55/55, 85 17/17, 87 68/68.
  The code is Phase 87's, whose full run was 2334 of 2343 (suites 28 and 57's foreground checks, both
  green alone); this phase changed the version and the documents only, so no full run was repeated.
- **Published on 15 October** on the user's word ("publish it, and go with 1 and 2 AND 3"): `gh release
  create v1.2.4 ... --title 1.2.4`, the notes in Romanian (the Wishlist page; the lists of the accounts
  marked theirs read once a day, only the account's number going to Steam, never changed; a private one
  not shown; the library's one-time upgrade). Read back through `updates.fetch`: 1.2.4, newer than 1.2.3
  and not newer than itself; GitHub's asset digest is the local file's sha256 (`79c724c2...ff2e6a3`,
  72,055,112 bytes). The friends' 1.2.3 copies will say 1.2.4 is out within a day.

## Phase 87 notes (the Steam wishlist, step 2 of 2: the Wishlist tab)

On the user's "restarted it, wishlist shows 16 games - go with phase 87" (his start ran schema 6 and
the first reads; by the next scans the 13 unknown games had their records and prices -- three of the
16 on sale that day: Police Shootout -93%, Autumn -86%, Pacific Drive -60%).

- **The tab, everywhere Reports went in Phase 84**: `TAB_WISHLIST` in `ui_topbar.TABS` and
  `ui_pageshell.TABS` (last), `ui_rail.NAV` with Phosphor 2.1.2's `heart` (**E2A8, read off the
  package's own CSS**, as every icon; Windows' fallback borrows the outlined star),
  `LibraryPage.wishlistRequested`, the window's `WISHLIST_PAGE` (5), `TAB_SEQUENCE` (and so
  `GLOWING_PAGES`, `TAB_ORDER` and `_arrival`), `TOP_BAR_TABS`, `PAGE_HINTS`, the header hidden, the
  rail's column, the backdrop's see-through rules. `ui_tv.WISHLIST`: A Open in Steam, B Back, X Menu, Y
  On sale / All, ◀ ▶ Reports, Settings; Reports' set says "Storage / Wishlist". Every set fits 1920 at
  every TV size.
- **The pad** on the page reads like Storage's: up and down move the selection (`STORAGE_KEYS`), A the
  store page or a fold opened, X the menu, **Y -- "play something" everywhere else -- switches the
  chips**, left and right walk the tabs (the fifth is the end), B and View go back.
- **The rows** (`ui_wishlist.WishlistDelegate`): the portrait cover cropped to fill (cached in
  `cache/steam_art/<appid>.jpg`, the same file a scan fetches for an installed game; the rest fetched by
  `screenshot_worker.CapsuleWorker` while the page is looked at, at most `rules.WISHLIST_ART_PER_VISIT`
  (20) a visit, a second apart, only with the network on -- `steam_web.fetch_capsule` writes the image
  and never steam_web.json, which a scan may be writing on its own thread); the name and "Lowest seen"
  after it when `is_lowest_now`; the fit line; "Added <day>", whose list (only when more than one account
  is marked mine) and "Already played: 42 min"; on the right today's price, the one before struck through
  and the discount when on sale, "lowest seen X on <day>" when the series has seen lower, and "N prices
  since <day>" -- "1 price so far" only for a priced game (the first render said it under "Not sold").
  The words are `logic/wishlist.row_of`'s, each part empty when its data does not exist.
- **The order** (`wishlist.order`): on sale first, the deepest discount first, then the fit share
  (unknown last), then the name -- said on every row by the discount and the fit line. **The chips**: All
  and On sale, the choice kept in config.json (`wishlist_filter`). **The folds**: "No longer on your list"
  (removed from every list, newest first) and "Hidden from this page", each "· N · show/hide", opened by a
  click or A.
- **The menu** (the window's `_wishlist_menu`, MENU hints around it): Open in Steam; Hide from this page
  or Show on this page again -- `wishlist_hidden` in config.json, one key, never the Steam list.
- **The store page** (`MainWindow.open_store`): `steam://store/<appid>` through `ui_settings.open_in_browser`
  (QDesktopServices -- the opener a test stands in for); when nothing takes it, the store's web page in
  the browser. Confirmed in Phase 86 on this machine.
- **The empty page says why**: no account marked mine (and where to mark one), never read (once a day
  with a scan) or the network off, nothing to read (private on Steam, or empty -- both said), nothing on
  the list now, nothing on sale today (the On sale chip), or the library cannot answer. A footnote says
  when the lists were read, from whom, and which accounts gave nothing.
- **The notice** (`wishlist.notice`, the window's `_wishlist_notice` after `wishlist.land`): "2 wishlist
  games at their lowest price seen" through the status queue, at most once a day and only when one of
  them is new since the last notice (`wishlist_notice` in config.json: the day and the games); never a
  hidden or removed game; never a dialog.
- **Rendered** (a copy of the real library, 1280 x 820 and TV at 1920 x 1080): the three sales first, the
  struck prices and discount tags, the folds, the hint bar. The covers were blank there (the network is
  blocked in a render); the real launcher fetches them on the first visit.
- **Two older suites asked for four tabs**: suite 84's pad walk ("right walks Storage, Reports, and stops
  there" -- past Reports is now the Wishlist; it walks two steps and suite 87 walks the five) and its
  Reports hint words; suite 60's rail places. Updated.
- `tests/phase87_tests.py`, 68 checks: the tab in the bar and the rail (the heart, Windows' stand-in),
  opened from each, lit, the glow kept, the page's own title beside the rail; the pad from the library
  (View, right four times -- Stats, Storage, Reports, Wishlist, Wishlist -- down to the next row, A the
  store page through the stood-in opener, Y On sale and back, X the menu's two entries and B closing it,
  left four times back, B back), pressed through `pads.action` from inside a timer; the hint set and every
  set at every TV size; each row's parts on made-up rows (seen once, on sale with today the lowest, seen
  cheaper, never moved, free and not sold with no count, not fetched yet, the hours, added or first seen,
  whose list only with several accounts, removed); the order (the deepest sale, the fit between two
  alike, the unknown fit last) and the chips; every empty page on made-up stores (no account, never read,
  the network off, nothing to read, everything let go or hidden -- and the footnote's names), "nothing on
  sale today", the library that cannot answer; the notice (two, the same day, the next day the same two,
  one new, "its", none; never hidden or removed) and the window posting it once and keeping its key; the
  store page and the web page after it; hiding and showing again, one key of config.json; the covers
  (one request each, into steam_art, not asked again, at most a visit's share, none with the network off);
  at 100% and TV on the real wishlist (the rows inside, nothing sideways, a row's glass, the ring),
  Escape; the documents, the layers, no network. Proven both ways: 68/68; with the sixteen changed files
  stashed back to the tag and `ui_wishlist.py` set aside (identical by hash after, the two LF files put
  back to LF), 15 failures and 3 passes (the layers, no network, the real data).
- **A slip on the way, and what it did**: suite 23 was run bare once (`python tests\phase23_tests.py`)
  instead of through `run_sandboxed.py` -- the rule for suites 22-25, broken a second time (Phase 70's
  was suite 24). It opened a real window on the real data, with the user's launcher closed: its startup
  snapshot (`2026-10-15_14-50-03`), one startup scan (scan 47, the same 33 games), a reading of Steam's
  playtime files (4 read rows, no counter changed, the accounts' last_seen moved). Checked against that
  snapshot table by table: nothing else -- no game, session, price, wishlist row or setting (config.json
  equal to the snapshot's). True records of a scan that did happen; nothing undone. Then 73/73 through
  the sandbox runner.
- **The full run: 2334 of 2343**, the 9 in suites 28 (the launcher coming back to the front after a game)
  and 57 (the focus rings' colours) -- both need the window in front, and both passed alone, 19/19 and
  59/59. Every net clean: imports, layers (0 upward, sqlite3 only in data_access/), paths, the scanner 0
  differences, the migration, the original folder untouched.

## Phase 86 notes (the Steam wishlist, step 1 of 2: read, kept, priced, set against what is played)

Asked for as a brief ("Phases 85 and 86: the wishlist" -- 85 was already the 1.2.3 release, so these
are 86 and 87); step 0 reported the two verifications and five places where the decisions met the
data, approved as "yes to both, go with phase 86" (daily prices for wished games; the hours already
played on a row).

- **Verified first, one request per account marked mine** (15 October, the brief's address): HTTP
  200 each. One account (GreenYRO) answered `{"response":{"items":[{"appid":296470,"priority":0,
  "date_added":1463944159},...]}}` -- 16 games, added 2016 to 2025, priority 0 for all; three of
  them (Day of Infamy, Ready or Not, Deadlock) already had a record, 13 had none. **The other three
  answered `{"response":{}}`, byte for byte alike, and one of them is the account signed in to the
  client, whose store page shows "Wishlist 6"**: a private list answers as an empty one would, and
  the two cannot be told apart. Kept as `tests/fixtures/steam_wishlist_public_2026-10-15.json` and
  `..._nothing_...` (no Steam number in them or their notes). `steam://store/<appid>` was confirmed
  the same way as rungameid -- HKCR's handler is `steam.exe -- "%1"`, Steam's console_log recorded
  `ExecCommandLine: ... steam://store/1144200`, and a capture of the screen showed the client's own
  store page for Ready or Not (for step 87).
- **Where the decisions met the data, each built as proposed in step 0**: (1) "wishlist private"
  cannot be said as such -- Settings says "nothing to read -- private on Steam, or empty", and such
  an answer never sets `removed_at` (a list made private would otherwise look like every game let
  go); a read log, `wishlist_read`, beside `wishlist`, says when each list was read and what came
  back; (2) **`is_lowest_now` needs a higher price seen too**: prices are recorded at every asking,
  changed or not, so a game never discounted would be "at its lowest" at its second observation;
  (3) **the fit is a union of the hours, not a sum of genre shares**: report 3 counts a game in each
  of its genres, so the brief's sum could pass 100% and would not mean "71% of your hours"; (4)
  wished games priced daily (the user's yes); (5) the hours already played on a wished game, in the
  view (`minutes_played`; Ready or Not is on one account's list and played on another).
- **Schema version 6** (`upgrades/006_wishlist.sql`, the same in `schema.sql`, additive): `wishlist_read`
  (account, read_at UTC, state `items`/`nothing`, items; `(state = 'items') = (items > 0)`), `wishlist`
  (PK (account, appid); priority, date_added as Steam says, first_seen, last_seen, removed_at -- **each of
  the three moments a read of that account, three composite foreign keys**; `first_seen <= last_seen <
  removed_at`), and `v_wishlist_now` (one row per game on the lists of the accounts marked mine, a game
  on two lists one row with both named; `lists` now holding it; the newest price, the lowest and highest
  seen, the count, `is_lowest_now`, `minutes_played`). **First draft 4.0 ms for 16 games**, through
  v_price_latest, v_price_range and v_hours (each reads every app); every part restricted to the
  wishlist's own apps: **0.5 ms, the same rows** (checked row for row). The upgrade on a copy of the real
  library: 4.6 ms.
- **The read** (`logic/wishlist.py`, steam_time's shape): `due` (GUI thread: the accounts marked mine not
  read in 20 hours; none with the network off), `read` (scan thread: `web.steam_wishlist.fetch` an account
  a second apart, the answers to `cache/wishlist.json`; a request with no answer is no reading, logged,
  asked again next scan), `land` (GUI thread, after steam_time's: `LibraryStore.land_wishlist`, one
  transaction an answer -- the read row, steam_app rows with `has_record = 0` for unknown games, new rows,
  last_seen moved and removed_at cleared, removed_at set for the games a list no longer holds; a reading
  older than the newest landed is not applied; a refused one stays). `ScanWorker(wishlists=)`.
  **No DELETE of a wishlist row anywhere** (suite 86 searches).
- **Records and prices**: `steam_records_wanted` gives the played apps first, then the wished ones without
  a record by date added; `prices_due(days, wishlist_hours=)` asks for a wished game's price once 20 hours
  have passed, everything else weekly as before (`prices.due` passes it; its log line says both).
- **The fit** (`wishlist.fit`, `fits(source)`): the hours of my games sharing at least one genre with the
  wished one over the hours of every game with a genre -- from `wishlist_profile` (report 3's games and
  genres, one row a genre) and `wishlist_genres`, Free To Play and the content descriptors never named;
  the genres in the order of my hours in each; "not fetched yet" (no record), "no genre to compare",
  "nothing played to compare with", "under 1%", "none of your hours". On the copy: Day of Infamy "Action,
  Strategy, Indie: 99% of your hours", Ready or Not 90%, Deadlock 87% -- **Action holds 87% of the hours,
  so the line mostly tells Action games from the rest** (said in ANALIZA).
- **The queries** (`data_access/reports.py`): `wishlist_now`, `wishlist_profile`, `wishlist_genres`, and
  `money_wishlist` for report 6, whose new part "Your wishlist at today's prices" gives the list price
  and today's prices summed, the on-sale count, and how young the series is. `NEEDS_VERSION` is 6; the
  page's "cannot answer" card no longer names a number. **The seven reports took 46.5 ms (best of 5) on
  the copy**, under the 50 of suites 83 and 84 but closer: about 1 ms is the wishlist's, the rest the
  queries reading v_hours (about 2 ms each) -- they took 38-43 ms on 14 October.
- **Settings' account rows** (`ui_settings.wishlist_words`): an account marked mine says "Wishlist: 16
  games · read today", "Wishlist: nothing to read -- private on Steam, or empty · asked ...", or "not read
  yet"; one not marked mine says nothing about a wishlist.
- **Old suites that count the schema** (67, 73, 75, 76, 83) take the three new objects; **76 and 83 go
  back a version through `test_sandbox.undo_upgrades(conn, to_version)`** -- it drops what the later
  scripts made (it refuses a script that drops or alters, like 004), so the next upgrade does not leave a
  suite to count by hand again.
- **CITESTE-MA said "Nu trimite nume, cont sau altceva despre tine"**, and the wishlist request sends the
  account's Steam number to Steam: the line now says "nume sau altceva", and the new sentence says the
  number is the one thing that leaves, and only to Steam.
- `tests/phase86_tests.py`, 91 checks: the parser on the two real answers and on eight that are no
  reading (none, not JSON, no response object, items not a list, no item readable) and a mixed list (the
  readable ones kept, a repeated game once, a bad priority or date left empty); the request (the address
  with the account's number, a GET with nothing sent, the User-Agent, no key, the timeout, an HTTP error no
  reading, the number in no log line); the upgrade on a copy of the real library (taken back to 5 with
  `undo_upgrades` when the user's start has reached 6 -- a snapshot holding 5, the user's rows, the Steam
  tables keeping theirs, meta only its version, the three objects and nothing else, STRICT and empty,
  fresh = upgraded, 1 -> 6 through every script); the read and landing on made-up accounts (only the two
  marked mine asked, none with the network off; the answer with no reading kept out of the hand-off;
  UTC moments; landed, the read rows, a has_record 0 row for an unknown game; once a day; landing twice
  one set; last_seen moved; removed_at set, nothing deleted; "nothing" takes nothing off; a game back;
  an older answer not applied; a refused answer kept; no DELETE anywhere; due again after 20 hours);
  the view (one row for two lists, the account not mine out, one price / a price never moved / seen
  cheaper before not "at its lowest", the lowest and its day, let go by one list or by all, the hours
  from both sources with an unmarked account's left out, agreeing with v_price_range); the fit (the
  union 90% where the sum would be 150%, the order of the genres, the four sentences in words, Free To
  Play never named, from the queries); prices daily for a wished game and weekly for the rest, the log
  line, the records played-first; Settings' three wordings and the dialog's rows; the window's scan with
  the network on (each account once by its number, on the scan thread, landed on the GUI thread, 16 games,
  the hand-off gone, the next scan asking nothing); report 6's lines summed from the view; nothing writes
  to Steam, the network only in web/; the five documents; the layers. Proven both ways: 91/91; with the
  ten changed app files and the five documents stashed back to the tag and the three new files set aside
  (identical by hash after -- the two LF files came back CRLF from the stash and were put back to LF
  first), 15 failures and 4 passes (the copy at version 5, the user's rows and the Steam tables as they
  were, the real data).
- **The run, before it was green**: the affected suites alone first -- 83 failed one check (its "every
  table as it was" listed tables, and the copy taken back to 4 now loses the two wishlist tables, which the
  upgrade makes again empty: it now compares the tables it had), 79 four: the address count ("these
  seven") and three TV-pad checks of the key question. **Those three passed on the code before this phase
  and with the wishlist read switched off for the experiment** -- traced by a throwaway copy of the suite
  printing its chain: the TV window's first step saw the key question already up. The chain's watchdog,
  a one-shot timer a minute out, was never cancelled; the first window's fired after its chain had ended
  and closed the TV window's first-run question, the wishlist's three seconds a scan having moved that
  minute onto it. It now stands down once its own loop has ended (Phase 52's lesson holds: it is still
  armed for as long as the chain runs). Suite 77's first-run scan asks the wishlist service too (the
  copy's accounts are marked mine): its host list now allows api.steampowered.com for that service only.
  **Then ALL GREEN, 2275/2275**, every net clean: imports, layers (0 upward, sqlite3 only in data_access/),
  paths, the scanner 0 differences, the migration, the original folder untouched.

## Phase 85 notes (release 1.2.3: the Reports tab in the friends' version)

The user's answer to the question Phases 83-84 left him: "yes lets put it in their version too".
A release, so its own phase and tag (`before-phase-85` on 84's commit).

- **What the friends get**: the Reports tab as built in Phase 84, and their library upgraded to schema
  version 5 at the first start after the update (`migration.open_library`, the startup snapshot holding
  the version-4 file first; v_hours is a view only, so their tables are row for row as they were).
  Nothing else of theirs changes: the anonymous export's format is the same (Spacewar and Source SDK are
  set aside in the comparison, never in the file).
- **Two things an installed copy said wrongly, found by reading the page as a friend would**: a table cut
  short ended "... and N more: reports.py --csv has them all", and reports.py lives beside the source
  only -- `ui_reports.more_rows` asks `paths.FROZEN` when called and says "... and N more." in an
  installed copy; and the opening line said "the accounts marked yours" without where -- a friend who
  never opened Settings' Steam accounts would read reports of the launcher's hours alone, so it now
  names the section.
- **The friends' path, proven with the real 1.2.2 installer** (kept aside before the build replaced
  `dist\`; sha256 `5c4c49ec...812e14`, the file published on 14 October): `tests/check_installer.py
  --over <it>` adds section 8 in a second fake profile -- the old version installed (Add/Remove says
  1.2.2), started as a friend's PC starts it (both questions closed, a scan, a library at schema 4),
  closed; this installer over it (Add/Remove 1.2.3); the updated copy starts with no question, logs
  "the library database is at version 5 now (snapshot <stamp> first)", the snapshot named holds the
  library at version 4, every view answers (v_hours among them), the library's `game` rows and the
  settings are as the old version left them, no error; then a quiet uninstall. `SCHEMA` is the number of
  the newest upgrade script, so the check needs no import of the data layer; with the same schema in
  both versions it says there is nothing to upgrade. DISTRIBUTIE §3's release steps now keep the old
  installer aside before a build and run the check `--over` it.
- **Suite 82 pinned the version** (1.2.2, and "Versiunea 1.2.2" in CITESTE-MA); it now asks for 1.2.2
  or later and for the current version in the friends' note.
- `tests/phase85_tests.py`, 17 checks: the version and that it is newer than 1.2.2; a table cut
  short as an installed copy shows it (`paths.FROZEN` stood in) and from source; the opening line and
  Settings' section by one name; the spec bundling the upgrade scripts with 005 among them; the
  installer check's `--over` and section 8, and its refusal of an installer that is not there (asked
  only of a check that knows the option -- one that does not would go on and install); CITESTE-MA,
  DISTRIBUTIE, CLAUDE.md; the layers. Proven both ways: 17/17; with the six changed files stashed back to
  the tag (identical by hash after), 11 failures and 6 passes (the from-source table, a table that fits,
  the spec, the layers, no network, the real data).
- **The build**: 33 s, 142 MB / **265 files** (one more than 1.2.2: `005_hours.sql`), a 69 MB installer
  (71,997,643 bytes, sha256 `79e5e942...84df716e`); `presentation.ui_reports`, `logic.reports` and
  `data_access.reports` in the PYZ, none in the warnings. **`check_installer.py --over` 47/47**: sections
  1-7 as before (GitHub asked once for real, answered 1.2.2: nothing newer than 1.2.3 offered) and section
  8 (the 1.2.2 copy's library at schema 4 with 12 game rows, brought to 5, the startup snapshot holding
  version 4, eight views answering, the rows and settings as they were). The key in none of the 265 files
  Setup.exe unpacks, nor in Setup.exe, and no config, library or log among them.
- **The full run: 2179 of 2184**, the 5 suite 27's pad-driven menu checks ("right opens the submenu", the
  mark, B closing). Alone it failed 4 once, then passed 44/44 twice on this code and 44/44 on the code
  before it -- the machine, as in Phases 47 and 62 (Chrome open). Every net clean: imports, layers, paths
  20/20, the scanner 0 differences, the migration, the original folder untouched.
- **The user's own library was already at version 5** (read read-only on 15 October): his restart after
  Phase 84 ran the upgrade.
- **Published on 15 October** on the user's word ("restarted it, reports look good - publish it"):
  `gh release create v1.2.3 dist/GameLauncher-Setup.exe --repo GreenYRO/game-launcher-releases --target
  main --title 1.2.3 --notes-file <the notes>`, the notes in Romanian like 1.2.2's (the Reports page, the
  library's one-time upgrade after a backup, run the new Setup.exe over the old). Read back through
  `updates.fetch`: 1.2.3, not a draft or pre-release, newer than 1.2.2 and not newer than itself; GitHub's
  asset digest is the local file's sha256 (`79e5e942...84df716e`, 71,997,643 bytes). The friends' 1.2.2
  copies will say 1.2.3 is out within a day.

## Phase 84 notes (the reports, step 2 of 2: the Reports tab)

On the same go as Phase 83 (the brief ran "then 83, then 84, each with its own tag"; `before-phase-84` is
on 83's commit). The page is the Stats page's kind: worked out on the way in, the cards in one column
beside the rail or under the top bar, see-through on the library's glow.

- **The tab**: `TAB_REPORTS` in `ui_topbar.TABS` (after Storage), `ui_rail.NAV` with its icon -- Phosphor
  2.1.2's `presentation-chart`, **E656, read off the package's own CSS** (the Phase 59 download is still
  in the scratch folder; Phosphor.ttf carries no glyph names -- its `post` table is version 3 -- so the
  font cannot be asked); Windows' fallback borrows Stats' chart glyph -- `ui_pageshell.TAB_REPORTS`,
  `LibraryPage.reportsRequested`, the window's `REPORTS_PAGE` (4), `TAB_SEQUENCE` and `GLOWING_PAGES`
  (the tabs, which keep the library's glow), `TAB_ORDER` from the sequence, `TOP_BAR_TABS`,
  `PAGE_HINTS`, the backdrop's see-through rules (`ReportsScroll`, `ReportsViewport`, `ReportsPage QLabel`).
- **The pad**: left and right on a tab page walk `TAB_SEQUENCE` -- Library, Stats, Storage, Reports --
  and stop at either end (`MainWindow._cross`; two tabs used to swap with `PageHeader.other()`, kept for
  the header; `PageHeader.step` answers the neighbour). Reports reads like Stats: up and down scroll
  (`_scroll_stats` takes the page's scroll), B and View go back, Start opens Settings. Hints:
  `ui_tv.REPORTS` (Back, ◀ ▶ Storage, Scroll, Library, Settings); Stats says "Library / Storage",
  Storage "Stats / Reports". Every set fits 1920 at every TV size (widest 1,194 px, the game page's).
- **`ui_reports.ReportsPage`**: an intro line (the two sources, what is set aside), then a `ReportCard`
  per report -- `ui_cards.Card` with the report's number and title, the question (muted), the sentence
  (the card's words, 15 px), the parts (a heading in small capitals; `ShareBars` for bars; a table as
  **one rich-text label**, every cell escaped, numbers right-aligned, the first column on the card's
  edge, at most `REPORT_TABLE_ROWS` with "... and N more: reports.py --csv has them all"; a note), then
  **What it cannot see.** and **The idea.** in the quiet colour. The concentration card paints its
  Lorenz curve (`LorenzCurve`: the diagonal dashed, the curve in the accent, the area between at 18%).
  A part kept only for the CSV (the abandonment's minutes, the sessions' by-length table) is not drawn,
  nor printed in the Markdown. An empty library's cards say so in words and draw nothing else; a store
  that cannot answer (JSON, or below version 5) gets one card: "start the launcher again".
- **`ui_cards.ShareBars`**: the session bars' look for shares -- a row's bar is its fraction of the
  room on a full-width track, a zero draws the track alone (no sliver: a share of nothing is nothing),
  every list's words one column wide (`REPORT_BAR_LABEL_MAX`, 240 px) so the bars start in one place on
  every card -- **the first render had each list choose its own width**, so the bars jumped from card
  to card -- and a label longer than that is cut with an ellipsis, its words in the tooltip.
- **Speed, measured**: the queries and shaping 38-41 ms on every visit. The cards are built only when an
  answer changed (a `Report` is a frozen dataclass, so equal answers compare equal; the page keeps what
  it last built and at what scale) -- a visit with nothing new costs the queries alone. **The first visit
  of a session took 518 ms**, nearly all of it Qt laying out the word-wrapped rich-text tables again at
  every width the layout tried; a table never needs to wrap, and with `setWordWrap(False)` the first
  visit is ~220 ms (Qt's first styling of the new widgets, 150 ms of it), once.
- **Found by rendering** (1280 x 820 at 100%, the rail, TV at 1920 x 1080): the tables sat indented by
  their first column's padding; " -- " where the words wanted a dash (an em dash now, in logic/reports'
  strings -- one began a source line and was missed by the first pass, found in the second render); the
  same buckets twice on the abandonment card; a CSV-only part's heading over nothing; the bars'
  starting points (above). Each fixed and rendered again.
- `tests/phase84_tests.py`, 36 checks: the tab in the bar and the rail (with its icon), opening the
  page from each, lit, the glow kept, the page's own title beside the rail; the pad from the library --
  View, right three times (Stats, Storage, Reports, Reports), down / page down / up scrolling, left three
  times back to the library, B and View back -- pressed through `pads.action` from inside a timer; the
  hint sets and their widths at every TV size; the seven cards and their parts, the curve's ends, every
  bar as long as its share, the tables as rich text, no rebuild on an equal visit, an empty library's
  words, the store that cannot answer, a planted `<script>` escaped; the time; at 100% and in TV mode the
  cards inside the window with nothing to scroll sideways, the first card's surface and its first bar
  painted; Escape back; the layers. Proven both ways: 36/36; with the eleven changed app files stashed
  back to the tag and `ui_reports.py` set aside (identical by hash after), 9 failures and 4 passes (the
  documents, the layers, no network, the real data) -- the old walk swapping Stats and Storage, 2 3 2 3.
- **Two older suites asked for the three tabs**: suite 24 for exactly four pages in the window and
  Storage's right going to Stats (it now asks that the page sits where the window routes it, and that
  left from Storage reaches Stats and right comes back -- the walk's order), suite 60 for the rail's
  three places (now four). 71/71 and 46/46.
- **The first full run was 2165 of 2168** (those 3); **the second ALL GREEN, 2168/2168**, every net
  clean: imports, layers (0 upward, sqlite3 only in data_access/), paths, the scanner 0 differences,
  the migration, the original folder untouched. That run covers Phase 83 too.

## Phase 83 notes (the reports, step 1 of 2: what the database can say, one query at a time)

Asked for as a brief (the coordinator judges the thesis on what can be analysed from the database:
seven fixed questions, the SQL the user's, "the Python one is the oracle where a figure exists in
both"); step 0 reported read only and approved as "yeah lets continue", with one ask added: **leave
Spacewar and Source SDK out of the data** -- done everywhere, the friends' comparison included, and
shown apart in report 7 (left out at analysis, never at collection: the database and the exports keep
them). Step 84 (the Reports tab) follows on the same go, as the brief has it.

- **Measured first, on a copy, read only** (14 October): Steam's counters on the four accounts marked
  mine hold 10,749 hours over 335 apps -- the brief's "9,988 of 10,749 hours have a known genre" is
  exactly Steam's alone; the launcher has timed 90 hours on 37 games; 116 sessions, 14 Aug - 13 Oct;
  339 price rows, all EUR; 2 purchases. 73 apps with 750 Steam hours have no store record, 480
  (301 h) and 218 (315 h) among them, and 56 of the 73 never will (the store answers "no such app").
- **`v_hours`** (`upgrades/005_hours.sql`, the same in `schema.sql`; a view only, version 5): one row
  per Steam app wherever there is one -- Steam's minutes once, the launcher's of every game linked to
  it summed (the two Silent Hill 2 folders share 2124490) -- and one per game with no app; every game
  ever known, installed or not (a carry moves time, so nothing doubles); `source` launcher / steam /
  both / NULL; `marked_tool` (MAX of the linked games' is_tool), `app_type`, `steam_last_played`.
  **"Both" is 4 apps (6 linked games): 72 minutes of the launcher's beside 2,030 of Steam's** (step 0
  said "72 hours": minutes, corrected in the report to the user) -- a copy timed here plus the user's
  Steam copy is two plays, so adding is right; 3 of the 4 links are a name match or a link kept from
  an old record, listed in report 7. **First draft 2.8 ms, read v_steam_time_mine twice** (a UNION of the apps,
  then a join); one `FULL JOIN` reads it once: **1.9 ms**, the same 381 rows and names (checked row
  for row) -- and the reports read the view some twenty times a page, so that is the page's budget.
- **What is a game** (the `games` CTE in every query of reports 1-5): not set aside
  (`rules.STEAM_NOT_GAMES`, a comment per entry, passed as a JSON parameter, never a number in the
  SQL), not marked a tool, and marked a game, or of Steam type "game", or of no type known yet.
  Demos (11), mods (3), the advertising app (1) and tools appear only in report 7. No linked game
  with launcher time had a non-game type, so the simple rule loses nothing (checked). The
  installed-game reports (4, 6) use the grid's own rule (`installed` CTE, as GameView decides).
- **`data_access/reports.py`**: 27 queries, each a module constant (`QUERIES`), named parameters from
  `rules.py` (`parameters()`: the bucket edges, the refund window, the set-aside apps, the "not
  genres"). **Nothing writes**: `Reports.rows` switches SQLite's `query_only` on around every query
  (and back), `open_read_only` gives the command line a `mode=ro` connection that refuses a missing
  file (never creating one) or a file below version 5 ("start the launcher once"). Local hour and
  weekday from `started_local`/`local_hour`, never `strftime` on the stored text. Median by
  `ROW_NUMBER`, the 90th percentile by nearest rank (`(9n + 9) / 10`).
- **`logic/reports.py`**: `Report(number, key, title, question, sentence, caveat, concept, parts,
  queries, curve, empty)`, `Part(heading, columns, rows, data, bars, note, data_columns)`, `Bar`;
  **the brief's fields, with the tables and bars as parts** -- most reports have several. `fetch`
  runs each query once (the backlog's rows feed the money report too), `build` makes the seven,
  `gini` and `lorenz` (the formula in the module's docstring and in ANALIZA), `markdown`, `tables`
  (for the CSV). Formats through humanize; totals as "10,145 hours".
- **Calls made** (step 0, reported): Free To Play out of the genre bars with its own line, and also
  Early Access, Violent and Nudity (`rules.STEAM_NOT_GENRES` -- a release state, content descriptors);
  a genre's share is of the hours that have a genre (the coverage line beside it); two genres count
  in both (the comparison of exports splits equally -- two measures, each said where it is); the
  night share by the hour a session began; the abandonment population "started at least once" (2
  apps with a last played and no minutes go under ten minutes); the backlog's "never" only where it
  can be known (exe and Steam games; Epic, Xbox, Ubisoft "cannot tell"); cost per hour over both
  sources' hours (the game page's fact counts the launcher's only -- said in the report); a list price
  per hour only for games played an hour or more with no purchase.
- **The answers on 14 October** (all in ANALIZA.md): Counter-Strike 2 39% of 10,145 hours, 2 games make
  half, 12 make 80%, Gini 0.931; of 318 games started on Steam 177 (56%) under the refund window, 60
  under ten minutes, 12 over a hundred hours; Action 87% of the hours with a genre, Free To Play 62%
  of all, 98% coverage; 3 installed games never played (54 GB, 89,24 EUR), 8 under two hours, 3 Xbox
  "cannot tell"; sessions median 16 min, mean 46, p90 118, 51% of the minutes begun between 00:00
  and 06:00; installed library 750,25 EUR at today's list prices, 44,99 EUR paid for 2 games, 23 apps on
  sale; 616 hours set aside, 134 on apps with no record, 4 games timed by both.
- **`reports.py`** (a fourth entry point, `check_layers.ENTRY`): `--markdown` (with the day; `--sql`
  adds each report's SQL; `--out FILE`), `--csv FOLDER` (one file per report, each part a block,
  BOM, semicolons, decimal commas, raw numbers), `--library FILE`. **The Markdown is what refreshes
  docs/ANALIZA.md's figures in June** -- its docstring and the document say so.
- **`docs/ANALIZA.md`** (Romanian): the two sources and `v_hours` (quoted), what is a game, wall time
  versus instants, then per report the question, the SQL **as it is in the code** (written by a
  script from `QUERIES`; suite 83 holds every ```sql block marked `-- <name>` equal to the code), the
  answer on 14 October, the caveat, the concept with its English term. BAZA_DE_DATE §5 has "Versiunea
  5" and §8 points to it.
- **The comparison of the friends' exports** (Phase 81's tool, the user's ask): `comparison._counted`
  drops 480 and 218 from each participant's Steam history, played set and the games in common;
  `Participant.set_aside_minutes` keeps how much; the page's "how to read" names them and who had
  time on them. The exports themselves are unchanged (the friends' 1.2.2 is untouched).
- **Timing on the real library**: all seven in **39 ms** (best of 3) -- under the brief's 50, not far
  under; the slowest queries money_library 3.8 ms, money_lowest 3.2, concentration 2.7 (each reads
  v_hours and v_price_latest). The Stats page recomputes on show the same way.
- **Version 5 runs at the user's next start** (a `before-schema-5` snapshot first, like 4); until then
  `reports.py` on his file says to start the launcher once.
- **Suite 67 asked for seven views and version 4**; it asks for eight and 5 now. 49/49.
- `tests/phase83_tests.py`, 70 checks: the upgrade on a copy (a snapshot holding version 4 first, the
  user's tables row for row, the Steam tables keeping every app and price -- the seeding projection
  may refresh a record, suite 76's lesson -- meta only its version, fresh = upgraded, v_hours the one
  object added); v_hours on made-up data (one row per app, two games' 60 + 30 minutes summed with
  Steam's 120 once, an unmarked account's 999 nowhere, both sources' totals exact); Gini (equal 0,
  one of n (n - 1)/n for n = 2, 4, 10, equal to the definition on a sample), the Lorenz curve; each
  report on made-up data with answers worked out by hand -- the concentration's games, shares, marks
  and Gini; the abandonment buckets (a start with no minutes, no demo, no Spacewar); two genres
  counting twice, Free To Play apart at 70%, the coverage, publishers, decades; Spacewar's 5,000
  minutes set aside and shown; the demo and the tool in report 7; the link and its kind; sessions'
  median 5.5, mean 5.5, p90 9, the tool's session left out; **the summer session at 5 and the winter
  one at 21 where strftime says 2 and 19**; weekdays from the clock's date; the night share; the
  backlog's states; the money (59,97 EUR, 10,00 EUR an hour, the proxy, the sale, the lowest seen);
  the games no source times; nothing written, query_only put back; an empty library answering in
  words; the Stats oracle on the real copy (lifetime 136,680 s, most played, three months, the
  sources -- equal); the time; reports.py (Markdown with the day, --sql quoting the code, the CSV
  files, nothing written, a version-4 file and a missing one refused, help); the comparison's
  exclusion; ANALIZA quoting the code; the layers. Proven both ways: 70/70; with the five changed app
  files stashed back to the tag and the four new ones set aside (identical by hash after), 13 failures
  and 5 passes (the user's rows as they were, the Steam tables, fresh = upgraded -- both version 4
  there -- nothing written by a command that is not there, the real data).
- **Suites 73, 75 and 76 counted exactly what their own upgrade adds** (an upgrade from version 1, 2
  or 3 now goes through script 5 too, which adds v_hours) and suite 76 named version 4 as the newest;
  they now ask for v_hours among the objects added and for `SCHEMA_VERSION`, and suite 76 drops
  v_hours before it rebuilds version 3 in its copy (a real library at 5 would otherwise make the
  view twice). Suite 81's real-export sums take the set-aside minutes into account (35/35).
- **The full run was 2125 of 2132**: those 7 checks in suites 73, 75, 76, before the updates; after
  them 83/83, 102/102, 60/60 alone. Every net clean: imports, layers (0 upward, sqlite3 only in
  data_access/), paths, the scanner 0 differences, the migration, the original folder untouched.

## Phase 82 notes (a whole drive is not a game folder; the 1.2.2 hotfix)

Reported by the user from the first friend to install 1.2.1: he answered "Where do you keep your
games?" with `C:\`. Phase 77 allowed a drive root with a warning (the user's decision, which he
called wrong: "a warning is not a guard"). Every top-level folder of C:\ became a game candidate,
each walked six levels deep, about ten minutes at every start, a pile of tools on the grid. The
user's five decisions were built as given, with one correction the code forced and one finding.

- **Windows' folders are told by where they sit, not by name.** The brief said "the walk never
  enters them"; read literally, by name, that would have walked past what is inside real games:
  a read-only search of this PC's two roots found **13** game subfolders called `Windows` or
  `ProgramData` (every Unreal game's `Engine\Binaries\ThirdParty\Windows`, Townfall's and Silent
  Hill 2's `Content\Windows`, Lightroom's `Data\ProgramData`). So `rules.SYSTEM_FOLDERS` holds
  each one's **path below the drive's root**, in lower case -- `windows`, `program files`,
  `program files\windowsapps`, `users`, `$recycle.bin`, ... 22 of them, the first run's old
  `FIRST_RUN_SYSTEM_FOLDERS` folded in (one constant) -- and `drives.is_system_folder` compares
  `drives.below_root(path)` with it. A folder *inside* one (C:\Users\andre, C:\Windows\System32)
  is not one; only the folders themselves are refused.
- **The judgements live in `shared/drives.py`** (`below_root`, `is_drive_root`,
  `is_system_folder`, `on_drive_root`, `drive_name`, `not_a_game_folder` -- the sentence the user
  reads -- and `split_roots`), because five layers ask: the first run and Settings refuse,
  discovery does not scan, the provider and the walk do not enter, removal does not delete.
  `first_run.is_drive_root` is the same function; `first_run.instead_of(drive)` is the finder on
  that drive. **`drive_name` always ends in a backslash**: Windows reads `D:` as that drive's
  current folder, not its root, so `D:` alone must never be listed.
- **1. Refused when chosen** (`ui_folders.FolderList.choose`, for the first run's list and
  Settings' alike): a drive is not added; the line under the list says "D:\ is a whole drive,
  not a game folder." and either "The folders on it that look like game folders are added
  instead" (they are, ticked in the first run) or "No folder on it looks like one"; a Windows
  folder is refused with nothing in its place. `DRIVE_WARNING` is gone. A refused folder already
  in config.json is listed as it is, with "It is not scanned: remove it, and add the folder that
  holds the games."
- **2. Never walked**: `walk.walk_tree` skips a system folder whatever it started from
  (`WalkReport.system_folders`), the folder provider skips one as a top-level candidate
  (`FolderProvider.kept_out`), and the scan says so once at its end ("kept out of N Windows
  folder(s), never game folders: ..."). With discovery never handing over a drive this is defence
  in depth; suite 82 proves it by handing the provider a made-up drive directly.
- **3. Removal's fifth rule** (`removal.protected`): never a whole drive, a Windows folder, or a
  folder directly on a drive's root -- asked in `refuse_reason` (before rules 2-3, so the plan
  says why) **and again in `send_to_recycle_bin`**, the one place that destroys (restoring saves
  goes through it too; a save folder directly on a drive would now be refused, which none here
  is). **Found by running suite 82 on the old code: 1.2.1 already refused removal under `C:\`,
  by accident.** `under_scan_root` tests `target.startswith(root + os.sep)`, and a drive's root
  `c:\` already ends in the separator, so it looked for `c:\\...` and nothing was ever "inside"
  -- the plan read "not inside a folder you told the launcher to scan". The fifth rule makes it
  a rule; the accident stays (it is a correct refusal) and is not relied on.
- **4. A config.json already holding a drive** (the friend's, until he changes it):
  `discovery.run_discovery` passes the provider only `split_roots(...)[0]` and logs "not
  scanned: C:\ (C:\ is a whole drive, not a game folder.)"; the folder watch watches only those
  roots; the empty library's first message, after "Looking for your games...", is "C:\ is a
  whole drive, not a game folder" -- "The launcher does not look in it: every folder there would
  be taken for a game. Choose the folder that holds your games instead." -- with Game folders...;
  and **a message card at every start** says the same with where to change it (`_report_refused_roots`):
  the friend's library is not empty -- his Steam games -- so the empty state alone would never
  have told him. Nothing writes his list: the program never takes a folder out of it. His
  catalogue's junk shows until the startup scan, about a second, and no plan can remove any of it.
- **5. No timer and no cap**: not walking a drive and Windows' folders is what bounds a scan
  (said in discovery's comment and here).
- **Not done, and raised with the user**: a user's own folder (`C:\Users\<name>`) as a root is
  the same mistake one level down -- Documents, Desktop and AppData would become games and be
  removable -- and nothing here refuses it; and the diagnostics bundle still lists a refused root
  among the folders "there" (its log says "not scanned"). "No other change rides along."
- **Version 1.2.2** (`shared/version.py`; DISTRIBUTIE §2 and §3, CITESTE-MA one sentence each; the
  release notes in Romanian, as 1.2.1's).
- **Suite 77 asked for the old decision** (a drive added with the warning; section 2) and now asks
  that it is refused and said why, with the finder stood in so the real D: stays out. 74/74.
- `tests/phase82_tests.py`, 55 checks: the judgements on real paths (a game's own `Windows` not
  one); the list on a made-up drive (a folder of the suite's own that `drives.below_root` takes
  for a drive) -- the drive refused, its `Games` and `Jocuri` added ticked, Continue answering
  them, a Windows folder refused, an empty drive said so; on this PC's real `C:\` in Settings'
  list, `C:\Games` offered (read only: the finder lists the top of C:\); the scan on the made-up
  drive -- the provider keeping out of four Windows folders, said once, the walk never entering
  them and still walking a game's own `Content\Windows`, discovery refusing the drive and saying
  so; the fifth rule's three cases in `plan` for the friend's `C:\` root and in
  `send_to_recycle_bin` -- **against a stand-in for Windows' shell that removes nothing**, which
  an ordinary folder still reaches; a window on a config.json holding `C:\` with the stores stood
  out (the walk stood in for too, raising at a drive, so broken code fails in a second instead of
  walking C:\ for ten minutes) -- the card, no watch, no walk, the log line, the empty library's
  words and button, Settings' line, his file byte for byte; the documents; the layers. Proven both
  ways: 55/55 (54 and CLAUDE.md before this note); with the ten changed app files stashed back to
  the tag, 14 failures and 6 passes (the documents, the layers, no network, the real data).
  **`git stash pop` rewrote six files' line endings**: they had mixed CRLF and LF (lines added
  through a bash heredoc), and came back all CRLF, so their sha256 could not match either way; the
  restored diff was checked instead (10 files, 223 added, 26 removed, as before) and the suite
  passed again.
- **The backslash trap a ninth time**: a block appended to `drives.py` through a bash heredoc lost
  backslashes in its docstrings and one `rstrip("\\/")`; rewritten with the Edit tool.
- **Two full runs.** The first, 2052 of 2062, and the scanner net with 5 differences: the user's
  library again -- since 12 October he uninstalled Spider-Man 2, Rehaunted and SILENT HILL f
  (checked: their folders are gone from disk, so the scan rightly lost them) and installed the
  Hytale Launcher and, through Xbox, Gears of War: E-Day. The saved run was saved again
  (`check_scanner.py save`, 33 games, then 0 differences), the old one kept as
  `tests/baseline/scanner-until-2026-10-14.json`. Suites 49, 52 and 57 lost the foreground to a
  browser playing a video (20/20, 17/17, 59/59 alone). **Suite 75 failed 2 checks, the same on the
  code before this phase**: its "at most 20 asked, in the history's order" assumed none of the
  wanted apps was already answered by the cache, and the user's scans since Phase 75 have cached
  "no store entry" misses, which the fetch rightly skips. The check now works out what a scan will
  really ask -- the wanted apps less those the cache answers, by the fetch's own rule (15 of 71 on
  the day) -- and asks that the two rounds are exactly its first and second twenty. 102/102.
- The second run: **2059 of 2062**, suite 57's three colour checks with the Claude app in front
  (59/59 alone), every net clean: imports, layers (0 upward, sqlite3 only in data_access/), paths
  20/20, the scanner 0 differences, the migration, the original folder untouched. Suite 29 counts
  49, not 50: its "Spider-Man 2 does not claim another game's Saved Games folder" needs Spider-Man 2
  installed. Suite 22 at 47 (the pad plugged in).
- **The installer**: `packaging\build.py`, 30 s, 142 MB / 264 files, 69 MB installer (71,937,531
  bytes, sha256 `5c4c49ec...812e14`); `check_installer.py` 35/35 -- stamped 1.2.2, Add/Remove 1.2.2,
  the first start asking both questions, the log's "Game Launcher 1.2.2", GitHub asked once for real
  (it answered 1.2.1, so nothing newer is offered), the update over it byte for byte (380 files),
  the four real shortcuts untouched. Before any publish: the user's SteamGridDB key is in none of
  the 264 files Setup.exe unpacks, and no config, library or log is among them.
- **Published on 14 October** on the user's word ("restarted it, C:\ gets refused - publish it"):
  `gh release create v1.2.2 dist/GameLauncher-Setup.exe --target main`, title 1.2.2, the notes in
  Romanian like 1.2.1's (a whole drive refused and its game folders offered; one already chosen not
  scanned, with a message; nothing on a drive's top ever removable). Read back through
  `updates.fetch`: 1.2.2, not a draft or pre-release, newer than 1.2.1 and not newer than itself;
  GitHub's asset digest is the local file's sha256 (`5c4c49ec...812e14`, 71,937,531 bytes). The
  friends' 1.2.1 copies will say 1.2.2 is out within a day.

## Phase 81 notes (comparing the exports, for the thesis)

Asked as "build the tool to compare the exports". It is the user's, not the friends': nothing in the
launcher or its installer changed, and the version stays 1.2.1.

- **How it runs**: `compare_exports.py` (an entry point beside `launcher.py` and `scanner.py`;
  `check_layers.ENTRY` knows it) reads every `*.json` in `data\exports\` (`rules.COMPARISON_DIRNAME`,
  made if missing, **git-ignored** -- the friends' files, anonymous or not, are never committed), writes
  `data\exports\comparison\` (index.html and eight CSV files) and opens the page in the default
  browser. Files or folders and `--out` can be named; `--no-open` for tests. The user's own library is
  a participant like any other: his own export saved into the same folder.
- **Reading** (`logic/comparison.load`): a file over 20 MB, not JSON, not `game-launcher-analysis`, of a
  newer format version, with no participant code, or missing games/sessions/Steam is **left out with
  the reason** (printed and on the page). Two files with one code: the newest `made_on` (then the one
  with more sessions) is kept, the other listed as replaced. **P1, P2, ... by the day of each
  participant's first file**, then the code -- so a friend who sends a newer export keeps the label the
  thesis already uses.
- **Measures** (`_measure`): games, installed by store, the launcher's minutes and sessions, Steam's
  minutes and apps played on the accounts marked theirs, accounts, nameless games, marks, stars, what
  was paid (only where included, never converted between currencies); **played** = the Steam numbers
  with launcher or Steam time above zero. Hours of day and weekdays as shares of the launcher's
  minutes; **genres as shares of Steam time, a game's minutes split equally among its genres**, so each
  participant's add up to 100. **The launcher's time (since it was installed) and Steam's (lifetime) are
  never added** -- the page says so; the one place they are summed is the common games' "hours in all",
  said as a measure of how played a game is.
- **Between them**: Jaccard on the played sets (`|A and B| / |A or B|`; none for two empty sets; 1 on
  the diagonal), the games played by more than one (by how many, then minutes), the genres shown side
  by side (the largest shares across everyone, "(fără gen)" never among them).
- **The page** (`logic/comparison_report.page`): self-contained -- inline style, one small script for
  tooltips, SVG drawn here, nothing fetched (no new dependency). Romanian, numbers as Romanian writes
  them ("1.234,5"). Sections: the participants (a table), hours through the launcher and hours on Steam
  (**two charts, never one with two scales**), where the installed games came from (100% stacked bars,
  2 px surface gaps, a legend), when they play (small multiples: 24 hours, 7 days), genres (small
  multiples), similarity (a heatmap on the blue ramp, the value written in each cell), the games played
  by more than one, the most played, the marks, what was paid, the files, how to read the numbers.
  **Every chart has its numbers as a table** (`<details>`), every mark a tooltip on hover and on focus;
  light and dark follow the system (`data-theme` overrides). **The palette is the dataviz reference,
  validated before use** (`validate_palette.js`: 7 slots light and dark pass; three light slots under
  3:1 on the surface, so every chart carries labels and its table). **Found by rendering** (headless
  Edge, both themes): charts drawn 640 wide and shown in 320 px cards had 6 px words -- each is now
  drawn at the width it is shown at and never scaled up; a 47% bar ran past its 40% axis (the last tick
  now reaches the largest value); **small multiples each had their own scale**, so equal bars meant
  different things -- every set now shares one (`top`, `peak`).
- **Escaped**: every name comes from someone else's file; all text goes through `html.escape` (a game
  called `<script>` stays text -- suite 81 plants one). **File names appear only in the files
  section**, which says not to copy it into the thesis if a file is named after its sender.
- **The CSV files** (participants, games, steam_history, hours, weekdays, genres, similarity,
  common_games): semicolons, decimal commas, UTF-8 with its mark -- Excel in Romanian opens them as
  they are; similarity to three decimals.
- `tests/phase81_tests.py`, 35 checks: nine files (three exports, an older one from the same
  participant, one not JSON, one not an export, one of a newer format, one with no code, a .txt) --
  three read, four left out with their reasons, one replaced and its sender still P1; the measures
  worked out by hand (minutes, stores, played sets, 75/25 hours, a Friday, Action 600 of 900); Jaccard
  0,25 both ways, 0 and none; the one common game, 660 minutes; the page (whole, nothing fetched,
  every chart with a table, the <script> name escaped, the file names only in their section, both
  palettes); the CSV rows, the decimal comma, the BOM, three decimals; the command from the command
  line, with an empty folder (says where, writes nothing, 1) and with no folder named (the data
  folder's, made); an export of the real library read back to its own sums, against a twin; the
  layers; git ignoring the folder. Proven both ways: 35/35; with `shared/rules.py` stashed back to the tag and the three new
  files set aside (identical by hash after), every section stops at its first use of what this phase
  added -- 8 failures and 4 passes (the layers, git ignoring the folder, the documents, the real data
  untouched).
- **Two full runs, neither all green, and neither about this phase's code.** The first, 2004 of 2008:
  suite 28's three foreground checks (19/19 alone), and **suite 76's "every row of every other table as
  it was"**. The user had closed his launcher at 01:31:36 while its startup scan was still fetching six
  Steam history records into the cache (Phase 75's 20 a scan), so the cache held records the database
  had not projected yet; the suite's upgrade runs the projection, which refreshed those `steam_app`
  rows in place -- and the check allowed the Steam tables only to gain rows. Nothing was lost (the next
  window scan projects them). The check now says what is true: the user's own tables exactly as they
  were; `steam_app` and its three link tables keep every app they knew (a refreshed record replaces its
  genres, categories and companies); genre, category, company and the price series only gain. 60/60.
- The second, 1999 of 2008: 9 checks in suites 49, 52, 56 and 57 -- the pad's gate ("the window still
  counts as active"), the game menu under X, the focus rings drawn outside buttons -- while a browser
  playing a video held the foreground. Each suite passed alone: 20/20, 17/17, 32/32, 59/59. **Suite 22
  ended with 0xC0000409 (a fast-fail on exit)** after 47 of 47, nothing on stderr; through
  `run_sandboxed.py` again it passed 47/47 and exited 0 -- seen once, not reproduced. Every net clean:
  imports, layers (0 upward, sqlite3 only in data_access/), paths 20/20, the scanner 0 differences (34
  games), the migration (67 records, nothing refused), the original folder untouched.

## Phase 80 notes (an anonymous copy of the library, for the thesis)

Asked as "go with phase 80", with no brief of its own: the phase was built to what the friends were
already promised (CITESTE-MA: "ce jocuri ai și cât le-ai jucat, fără căi de foldere și fără nume de
conturi -- e alegerea ta") and to BAZA_DE_DATE §8's rule (Steam accounts pseudonymised, names never
leaving). No new dependency, no network, no new table; the SQL is two read-only store methods.

- **The data** (`LibraryStore.analysis_source`): the game rows (source, installed, Steam's number and
  how it was found, Steam's name and type, the store's title -- **only for a game a store installed**,
  marks, first seen, last played, playtime), sessions (start and minutes), genres, purchases, the
  accounts marked mine (their numbers only to join their minutes) and `v_steam_time_mine`. Asked for by
  column, so no path, custom name, note or picture is ever read. A record whose history was carried on
  is left out **unless installed again** -- the user's The Witcher 3 is exactly that (carried to the
  Remastered build in Phase 72, its folder renamed back in Phase 73), found by suite 80's count.
- **The shaping** (`logic/analysis.build`): hidden games and tools out, by GameView's own rule on the
  database's columns (`_is_tool`; suite 80 compares it game by game); an old install with nothing of
  the user's out; names from Steam or the store, **a folder game matched to nothing has no name** (its
  name is its folder's -- a repack's name says where it came from); months, never days or times;
  sessions as totals by month, local hour (the offset each start was written with) and weekday; Steam's
  history per app and the accounts as "A", "B", ... by minutes; `paid` only with the switch, a typed
  shop as "other", never the note. `summary` says it in a few lines for the dialog.
- **The participant code**: `p-` and ten random hex digits, made at the first export, kept in
  config.json (`rules.ANALYSIS_ID_SETTING`), read from the file itself at export time (the window's copy
  of the settings does not hold it). **Never in the diagnostics bundle**, which has paths.
- **The last check** (`analysis.leaks`/`write`, defence in depth): every string and number in the
  export searched for the library's paths, account numbers and SteamID64s, and notes or launch
  arguments of 12 characters or more (`LibraryStore.personal_values`; names are not searched for -- a
  persona can be a word in a game's title, and no field is drawn from them). Found: nothing written,
  `Refused` naming the kind, never the value. Written whole or not at all (a temporary file, replaced).
- **Settings, Your library data, "For a thesis"**: "Anonymous export..." opens `ui_analysis.AnalysisDialog`
  -- what is in it, in the library's numbers; what never is; "Include what I paid" (off); Cancel and
  Save... -- then the save dialog (Desktop, `GameLauncher-anonymous-<day>.json`); the row says where it
  went and that sending it is up to them. The pad: the switch first, A flips it, down to Save, A.
  **The rows' result lines are hidden until they have something to say** (`ui_settings.StatusLine`):
  an empty one had left a gap under Diagnostics since Phase 77.
- On the user's library, on a copy: 51 games (27 installed), 106 sessions, Steam's time for 335 apps on
  4 accounts (A-D), 5 games without a name, 1 hidden game and 5 tools left out, about 70 KB, nothing
  personal found by the check, no backslash in the file at all.
- **Version 1.2.1** (built first as 1.3.0; the user asked for smaller steps, and each release now
  raises the last number): the export is no use to the friends until an installer carries it. Built and
  proven (check_installer 35/35; its GitHub answer 1.2.0, nothing newer); **published on 12 October** on the user's word ("restarted it, export works - publish it"): the
  key checked absent from Setup.exe and its 264 files first; read back through `updates.fetch` --
  1.2.1, not a draft, newer than 1.2.0, the asset's sha256 the local file's (`d21cec9b...853e39`,
  71,931,436 bytes). The friends'
  1.2.0 copies will say 1.2.1 is out the day after it is.
- `tests/phase80_tests.py`, 51 checks, on a copy with a note, a custom name, an exe picked by
  hand, launch arguments and two purchases (one at a typed shop, with a note) planted: the format; no
  path of the library's, no backslash, no Steam number, no persona or account name, none of the
  planted things, not the key, no moment of any session; unmatched folder games nameless, matched
  ones Steam's name; tools by GameView's rule game by game; every installed game shown and none hidden;
  carried records not twice; the session totals agreeing with each other and with the database; Steam's
  history equal to the view, the accounts A.. by minutes; one unmarked, gone; paid only when asked, the
  shop "other", no note; the last check refusing a path, a number and a note, writing nothing; the
  code; Settings with the mouse and the pad (the switch, down, down, A), B cancelling; the diagnostics
  without the code; the documents; the layers. **The suite's own trap, a recursion**: a chain step
  that clicks a button opening a modal is called again by the chain's timer from inside that modal --
  a dialog in a dialog until the stack ran out (exit 127, faulthandler showed it); the click is
  scheduled now. Proven both ways: 51/51; with the seven
  changed app files stashed back to the tag and the two new ones set aside (identical by hash after),
  every one of sections 1-9 stops at what this phase added -- 9 failures, 11 passes (the documents, the
  layers, the real data untouched).
- **ALL GREEN 1973/1973** (1922 + 51) on the first full run, every net clean: imports, layers (0
  upward, no SQL outside data_access/), paths, the scanner 0 differences, the migration, the original
  folder untouched.

## Phase 79 notes (is a newer version out; the first run's second question)

Asked as "yes to both, you create the repo - go with phase 79", after the step 0 that named the new
address and the public repository -- and, in the same message, "a new prompt at the beginning after
game files asking them if they want a steamdb api key and a place for them to enter it". **SteamDB
has no keys for users; the launcher's key is SteamGridDB's** (Phase 8), so that is what it asks for,
and the report says so.

- **The repository**: `GreenYRO/game-launcher-releases`, public, made with `gh` (signed in as
  GreenYRO): one README, English and Romanian, no code. **Its first commit carried the user's own
  e-mail address** (the project's git identity) -- replaced at once, before anyone could have
  fetched it, with GitHub's no-reply address (`<id>+GreenYRO@users.noreply.github.com`), and force
  pushed over the one-minute-old single commit. Any later commit there should use the no-reply
  address too. **1.2.0 was published on 12 October**, on the user's word ("restarted it, settings
  show 1.2.0 - publish 1.2.0"; the Sandbox click-through is still his to do): `gh release create
  v1.2.0 dist/GameLauncher-Setup.exe --target main`, notes in Romanian. Checked first that his
  SteamGridDB key is in neither Setup.exe nor any of the 264 files it unpacks, and that no config,
  library or log is among them; checked after, through `updates.fetch`, that GitHub answers 1.2.0
  (not a draft or pre-release) and that the asset's sha256 is the local file's (`19246f92...a5e275`,
  71,906,555 bytes). Every later version: raise APP_VERSION, build, check_installer, then a release
  `v<version>` -- each publish is public, so each waits for his word.
- **Read off GitHub first** (11 October, two requests, `tests/fixtures/github_*`): rsms/inter's
  latest release, 200 -- `tag_name` "v4.1", `name`, `draft`, `prerelease`, `published_at`, assets;
  our repository with no release, **404 {"message": "Not Found"}**; `X-RateLimit-Limit` 60 an hour
  for an anonymous connection.
- **`web/updates.py`**: `fetch` (one GET with GitHub's Accept and API version headers and a plain
  User-Agent, no account), `read` (a draft or pre-release refused, a tag read as a version or
  refused), `Answer` (when, reached, latest, published, title -- and no address), `check` (the kept
  answer in `cache/update_check.json`: a day after an answer, six hours after none), `should_check`
  (an installed copy, network on). 404 is reached, nothing newer. `shared/version.parse`/`is_newer`
  compare as numbers ("1.10.0" > "1.9.0"; "v1.2" is 1.2.0; a suffix is no version); `is_newer`
  reads APP_VERSION when called, so a kept answer says nothing newer after the update it named.
- **The window**: `UPDATE_CHECK_DELAY_MS` (6 s) after it appears, `_check_for_updates` --
  `adapters/update_worker.UpdateWorker`, stopped in closeEvent (Phase 10's rule); `_on_update_answer`
  keeps it and, **only when GitHub was just asked**, queues "Game Launcher X is out. Settings, under
  About, has the download page." -- so at most once a day.
- **Settings, About, "Updates"** (`ui_settings.update_text`): "This copy runs from source and never
  asks" (here), "Not checked: Allow network lookups is off", "Not checked yet...", "Version X is out,
  published <day>. Open the download page and run the new Setup.exe over this one; everything is
  kept.", "You have the newest version. Checked today at HH:MM." (also with no release yet), "GitHub
  could not be reached (...)". The button, **Open the download page**, is always there and always
  opens `rules.UPDATE_PAGE_URL` through `ui_settings.open_in_browser` (QDesktopServices) -- the one
  helper both new buttons use, and the one a test replaces. The network row's line now says it
  covers the update check too.
- **The key question** (`ui_first_run.KeyDialog`, "Want more cover art?"): after the folders are
  written and the first scan has started; what SteamGridDB is, three steps (sign in -- with Steam
  is quickest; Preferences, API, generate; paste), **Open steamgriddb.com** (`rules.SGDB_KEY_PAGE_URL`,
  `/profile/preferences` -- the page SteamGridDB's own client README names; the site is a script-built
  page that answers 200 to any address, so its README is the evidence), a masked field, **Test**
  (`steamgriddb.check_key`, as Settings), Skip and **Save key** (enabled only with a key; the default,
  so a paste and Enter saves). Saved: `{"steamgriddb_key": key}` alone through `save_config`, into
  `self.config` and the game page, logged as "a key was added" -- never the key. Skipped or closed:
  nothing written. At a desk it opens on the field; in TV mode on Skip (a pad cannot type). The
  result line stays hidden until Test has something to say (the first render left a gap).
- **Suite 77 answers the second question now** (sections 4-6: skipped, or B on the couch); its
  version check asks for 1.1.0 or later. 74/74.
- **`check_installer.py`**: the first start closes both questions and finds no key written; the
  installed copy **asks GitHub for real** -- the only real request of any test -- and keeps "reached,
  no release"; the updated copy does not ask again that day. 35/35 on the 1.2.0 installer, 12 October.
- **The build failed the second time over an existing `build\`** ("Access is denied" removing
  `_internal\data_access\upgrades`): PyInstaller copies a folder with its attributes, and the source
  `data_access\upgrades` carries the October ReadOnly mark (Phase 69's notes). Phase 78's build worked
  only because `build\` had gone to the Recycle Bin in Phase 68. `build.py` now removes with
  `onexc=_writable_and_again` (on a PermissionError only: the mark off, the same call again).
- `tests/phase79_tests.py`, 63 checks: twelve version pairs; the real release read; the 404;
  a draft, a pre-release, a word for a tag, not JSON, no answer, 403, 500; the request (the address,
  GET, the headers, no Authorization, the timeout); a newer release's planted `html_url` kept nowhere;
  once a day (23 h no, 25 h yes; 5 h no, 7 h yes after no answer; an unreadable kept answer asks); the
  same answer after the update says nothing newer; from source the window never asks; an installed
  copy (`paths.FROZEN` stood in after the window is up) asks once, on another thread, and shows the
  card once; the same day no request and no card; network off no request; Settings' words in each
  state, its button with the mouse and the pad's A, both the fixed page; the key question (after the
  folders, the scan running, the field focused, Save waiting, the page, Test with the key stripped,
  written beside the folders, in use, logged without the key; Skip and closed writing nothing; TV
  size, the pad on Skip, down and up, A); the diagnostics bundle without the key; check_installer
  looking for the question by its title; CLAUDE.md, CITESTE-MA and DISTRIBUTIE §9; nothing outside
  `web/` reaching the internet; no request to GitHub from the suite. Proven both ways: 63/63; with the five changed app files stashed back to the tag and the two
  new ones set aside (identical by hash after), every section stops at its first use of what this
  phase added -- 8 failures and 2 passes (CLAUDE.md, read as it is now; the real data untouched).
- **ALL GREEN 1922/1922** (1859 + 63) on the first full run, every net clean: imports, layers (0
  upward), paths 20/20, the scanner 0 differences, the migration, the original folder untouched.

## Phase 78 notes (the first run, and what a friend's PC needs, step 2 of 2)

Approved as "restarted it, settings look right - go with phase 78" (his two checks on this
machine: Settings shows 1.1.0 and Game folders with his two roots; his first run unchanged).

- **The installer rebuilt from this code** (`packaging\build.py`: 34 s, a 142 MB app, a 69 MB
  installer, `_internal\VERSION` 1.1.0 and `_internal\BUILD` the day; every new module in the PYZ).
  `dist\` is kept: the Sandbox test and the friends need it. `build\` stays too (rebuilt each run).
- **`tests/check_installer.py`, permanent, by hand after a build, not in run_all** -- Phase 47's
  and 68's scratch tests made a fixture of the project. A fake profile (USERPROFILE, APPDATA,
  LOCALAPPDATA in a temporary folder), the four real shortcuts hashed before and after, the HKCU
  entry absent first and removed after -- **also when a run stops half way**: the first run of it
  stopped on a wrong window title and left its Add/Remove entry behind; it was removed by hand
  after checking it pointed into the test's temp folder, and the `finally` now does that itself.
  **Qt adds the application's name to a dialog's title** ("Where do you keep your games? - Game
  Launcher"): windows are found by process (the user's own launcher is open, same title) and by
  the start of the title. 31 checks: the build (newer than every source file, the version, the
  schema with its three upgrade scripts and the fonts byte for byte); a first install (shortcuts,
  Add/Remove 1.1.0, no config.json); **the first start as a friend's** -- the question up before any
  scan, closed by WM_CLOSE, `{"roots": [], "enable_xbox": <this PC's>}` written, the stores scanned,
  the log's first line "Game Launcher 1.1.0, built ... installed copy", no error, and 0 store
  requests (the Steam caches copied in first); **a second install over the first** -- the database,
  settings, log and its two copies, cache, backups and save copies (234 files) byte for byte, an old
  build's strays gone, and the program's 264 files identical to the first install's (an idempotent
  upgrade); the updated copy starts without asking; a quiet uninstall keeps the data; the real
  shortcuts untouched.
- **Found: an update deleted `launcher.log`, `.1` and `.2`** -- `clear_program_files` removes every
  top-level *file* not on `USER_DATA` (folders are kept). A friend who updates and then has a problem
  would have sent diagnostics without the log from before. All three are on the list now, in
  `packaging/installer.py` and `logic/uninstall.py` (which nothing reads; kept in step). Suite 78
  runs the installer of `before-phase-78` from git on a made-up install folder and shows it losing them.
- **The Windows Sandbox file** must name absolute paths on this PC, and no tracked file names the
  project folder (Phase 37): `packaging/sandbox/make_sandbox.py` writes `GameLauncher.wsb` (git
  ignores `packaging/sandbox/*.wsb`). Two mapped folders, read only: `dist\` onto the sandbox's
  Desktop as "Installer", and `C:\games\Slow Roads` (the plain game; 481 MB) onto the Desktop, then
  **copied** by the logon command to `C:\Games\Slow Roads` -- a copy, not the mapping, because
  whether a mapped folder looks like a link from inside is not known here and the scan skips links;
  `C:\Games` is also what the first-run finder offers by itself. Explorer opens on the installer
  when the copy is done. **Windows Sandbox is not enabled on this machine**; DISTRIBUTIE §6 says how
  (Turn Windows features on or off, a restart; virtualization in Task Manager). The click-through
  (§7, nine steps: install, the question, the game found, a page, About and Game folders, the
  diagnostics zip, the same Setup.exe again, `--silent`, close) is the user's.
- **`docs/CITESTE-MA.md`** (Romanian, one page, for the friends): what it does; what it reads (the
  chosen folders, the stores' install records, Steam's playtime file, the names and dates of files
  in save folders -- the Phase 29 search, said plainly); what it never does (no account, no login,
  nothing about them sent; Steam's public store pages only, which Settings can switch off;
  SteamGridDB only with their own key); installing and SmartScreen ("Mai multe informații" ->
  "Rulează oricum", and why: no code signing); where the data lives
  (`%LOCALAPPDATA%\Programs\Game Launcher`); updating over the old one; Save diagnostics; the thesis
  paragraph (an anonymised export may be asked for, their choice); uninstalling.
- **`docs/DISTRIBUTIE.md`** (Romanian): the installer and where data lives, the first run, the
  version and how to release one, the diagnostics bundle, the automatic installer proof, the Sandbox
  and its checklist, the two checks on this machine, places for Phase 79 (the update check -- a new
  address, so it asks first) and Phase 80 (the analysis export -- pseudonymised accounts), a glossary.
- `tests/phase78_tests.py`, 31 checks: the `.wsb` (well formed, both mappings read only and onto the
  Desktop, the copy then Explorer, refused with no build, git-ignored, the real one's folders there);
  the keep-list (the data, the logs, the uninstaller's copy in step); an update over a made-up install
  folder (every data file and folder byte for byte, the old program gone; the old installer losing
  the logs); the two documents say what they must; check_installer exists and stays out of run_all.
  Proven both ways: 31/31; with the two keep-list files stashed and the four new files set aside
  (identical by hash after), 5 failures and 5 passes.

## Phase 77 notes (the first run, and what a friend's PC needs, step 1 of 2)

Asked for as a brief (the launcher goes to a few friends as an installer, so their libraries can
be compared with this one in the thesis later); step 0 approved as "go with phase 77". Step 78 is
the installer rebuilt and proven, the Windows Sandbox file and checklist, `docs/CITESTE-MA.md` and
`docs/DISTRIBUTIE.md`; the update check becomes 79 and the analysis export 80.

- **Read first**: the window started its first scan inside its constructor, before it is shown,
  when there is no catalogue; nothing writes config.json before that (the startup snapshot only
  reads), and `packaging/installer.py` never creates one -- so "no config.json" is a fresh install,
  and nothing else. **Windows Sandbox is not enabled on this machine** (`WindowsSandbox.exe`
  absent): step 78's checklist says how to turn it on.
- **The candidate rule** (`logic/first_run.candidates`): fixed disks only (`shared/drives.py`,
  `GetDriveTypeW` == 3 -- not adapters/, as the brief offered: the finder is logic, and logic may
  not import adapters); the folders one level below each root whose name has a word (letters,
  any case) in `rules.FIRST_RUN_FOLDER_HINTS` (games, game, gaming, jocuri, joc); never one named
  in `FIRST_RUN_STORE_FOLDERS` (SteamLibrary, Epic Games, GOG Games, XboxGames, Riot Games, ...)
  or `FIRST_RUN_SYSTEM_FOLDERS` (since Phase 82 `SYSTEM_FOLDERS`), never one holding `steamapps` (a Steam library whatever its
  name), never hidden, system or a reparse point. **On this machine it offers exactly
  `C:\Games`** (leaving out GOG Games, Riot Games and XboxGames; `C:\voices38` has no game word)
  and turns Xbox on (`C:\XboxGames`).
- **The question** (`ui_first_run.FirstRunDialog`, Settings' look, TV size in TV mode): the found
  folders ticked, Add a folder... and Remove (`ui_folders.FolderList`), the Xbox switch, "I only
  use Steam, GOG, Epic or Xbox" and Continue. `MainWindow.first_run` is read before anything can
  write; until the answer the in-memory roots are `[]`, no scan runs (the no-catalog one included)
  and the quiet startup scan stands down for the answer's own; `showEvent` puts the question up
  once the window is on screen. Closing it is skipping: `{"roots": [], "enable_xbox": <switch>}`.
  A whole drive was allowed and warned against ("This treats every folder on D:\ as a possible
  game; pick the folder that holds the games instead."); nothing about removal changed. **Wrong,
  and undone in Phase 82**: a warning is not a guard, and the first friend chose `C:\`.
- **The pad**: `_drive_dialog` gained two rules, for every dialog. Up/down on a list goes on to
  the control before or after it **at either end, or in an empty list** -- a list the pad could
  enter and never leave was a trap; and A on a list marked `padActivate = "select"` is Space
  (ticks the folder) rather than Return (which pressed the dialog's default, Continue or OK, from
  inside the list). **Found by the suite**: the list started on its last folder (adding makes each
  current), so the pad's first Down left it and A opened the folder picker; it starts on the first.
  Add a folder... opens Windows' own picker, which a pad cannot work.
- **Settings, Finding games, Game folders**: the same list without ticks; "Folders to skip inside
  these are set in config.json". `values()` gains `roots`; a changed list (compared case-blind) is
  written with Settings' own keys only, the watch follows it (`_arm_watcher`) and a scan starts
  (trigger `manual` -- the database takes five triggers, and a sixth for one label would be a
  schema change); a folder taken out deletes nothing. `SettingsDialog(focus="roots")` opens on the
  row with Add a folder... focused.
- **The empty library** (`LibraryPage.set_empty`, `MainWindow._update_empty_state`, after every
  reload, scan start and scan end): "Looking for your games..." while a scan runs; "No games yet"
  (no folders, no store games) with "Choose game folders..."; "Your game folders cannot be
  reached" naming them; "No games found" naming them, and any not reachable. **The line was cut
  short twice in the renders**: a wrapped label has no width of its own (fixed to
  `EMPTY_TEXT_WIDTH`), and a centred one is never asked its height for that width (set from
  `heightForWidth`).
- **The version** (see the rule above): `shared/version.py`, `build.stamp_version(app_dir)` writes
  VERSION and BUILD, `installer.read_version` takes the first line, `version.describe()` heads the
  start line of launcher.log, Settings' "About" section (last) says "Game Launcher 1.1.0" and
  "Built <day>." or "Run from source, not an installed copy."
- **The diagnostics bundle** (`logic/diagnostics.write`, Settings' "Save diagnostics..."; the result
  is said in the row, no box): about.txt, config.json without `steamgriddb_key` (and whether one is
  set), scan.json (the last scan's time, the game folders there and missing, every install row --
  `GameEntry.to_dict()` -- with `chosen_exe`), summary.txt, launcher.log and its rotated copies. No
  sessions, notes, marks, purchases or Steam accounts; **the log can name a Steam account in a rare
  line**, so in the copy every account id and SteamID64 the library knows becomes
  "steam-account-N" (numbered by account id), and the key, if a line ever held it, is removed.
  Written whole or not at all (a temporary file, then replaced).
- `tests/phase77_tests.py`, 74 checks: the finder on three made-up drives (a junction made with
  `_winapi.CreateJunction`, a hidden folder, a Steam library under another name; fixed / removable /
  network through a stand-in for `drives`); the folder list; with a config.json no question;
  without one -- closed (written `[]` and Xbox, the scan on no folders, not asked again), answered
  (the ticked folders and one added, the scan and the watch on them, the startup scan standing
  down), on a couch (TV size, the pad: down, A unticks without pressing Continue, down past the end
  leaves the list, down to Continue, A); Settings (shown, added, written with its keys only, the
  watch, one scan; unchanged = no scan; taken out = nothing deleted, scanned); the four empty
  messages, the line whole, the button to the row; the version in build.py, the stamped files, the
  installer's reading, an installed copy's Settings (paths.FROZEN stood in), the log's start line;
  the bundle (members, the key nowhere, the account ids replaced, every install with its folder,
  nothing of the play history, no purchase). A fresh install has the network on by default, so its
  first scan asks Steam's store (blocked here): the suite checks only the sanctioned hosts are asked.
  Proven both ways: 74/74; with the nine changed app files stashed and the six new ones set aside
  (identical by hash after), 14 failures and 6 passes.
- **The full run was 1823 of 1826**: suite 35 asked for Settings' seven sections and its old set
  of answers (eight now, "About" last; `roots` among the answers), and suite 65's stand-in for the
  Settings dialog took no `focus` (the window passes it now). Updated; 78/78 and 21/21 alone; every
  net clean.

## Phase 76 notes (Steam's own playtime, step 2 of 2: on the page and the tile; schema version 4)

Approved as "restarted it, marked my accounts - go with phase 76" -- read only first: the real
database at version 3 (the startup snapshot held it, so "before-schema-3" was skipped as
unchanged), all four accounts marked mine, 390 counters, the second scan fetching 18 of 20 records.

- **The store answers once for the whole library**: `LibraryStore.steam_times()` -> {game key:
  minutes, accounts, last_played}, through `game.steam_appid` joined to `v_steam_time_mine`; empty
  below version 3, and the JSON store has none (`keeps_steam_time` guards it). The window keeps it
  (`MainWindow.steam_times`, handed to `LibraryPage.steam_times`) -- **a tile is painted many times
  a second and never asks the database**. Read again in `reload_views`, after `steam_time.land` in
  `_on_scanned`, and after Settings' OK (`_follow_steam_times`: only when the answer changed, the
  grid's viewport repainted and the open page's `set_view` re-run -- never `set_views`, so a scan or
  a mark never throws the grid back to its start).
- **Measured, and it forced version 4**: version 3's `v_steam_time_mine` took **93 ms** on the
  real data (105 in the suite's copy) -- its "newest last played" was a correlated subquery that
  re-read `v_steam_time_latest` for each of 335 apps -- and the window asks at every reload (once a
  minute while a game runs, at every star). `upgrades/004_steam_time_mine.sql` drops and recreates
  the view with `ROW_NUMBER() OVER (PARTITION BY appid ORDER BY julianday(last_played) DESC NULLS
  LAST)` and takes the first: **0.8-1.2 ms**, the same answer app for app under four sets of marks
  (as the user left them; half mine/half not; the other half mine/the rest undecided; none). A view
  holds no data, so this is not a contraction; `schema.sql` holds the new form for a fresh database,
  and 1/2/3 -> 4 all arrive at its schema. **SQLite creates a view naming a table that does not
  exist and complains only when it is read** -- the suite's first "broken script 4" passed for that
  reason; it now fails half way (after the DROP), and the rollback puts version 3's view back.
- **The page** (`gamedetails.steam_time_facts`, `STEAM_FACT = "On Steam"`, after Source, before the
  money facts; `DetailPage.steam_time_for = MainWindow.steam_time_of`): "113 hours on 2 accounts,
  last played 1 Sep" (Overwatch here), "33h 31m, last played 1 Oct" on one account (WARDOGS) -- `humanize.playtime`'s
  own words, not the brief's "23 h 30 min" (one time format in the program); 0 minutes with a last
  played "under a minute" (Steam counts whole minutes), without one "never played"; accounts holding
  only a last played give it alone. **Through `game.steam_appid`, so a folder game linked by name
  gets it too**: the user's Silent Hill 2 repack shows its 18 hours on Steam -- the brief's rule,
  and true.
- **The tile** (`ui_library.tile_subtitle(view, steam)`): only a game Steam starts
  (`entry.source == "steam"`, not an exe), and only with a minute or more -- "3964 hours on Steam" in
  place of "Steam"; the store's name otherwise. "on Steam" kept so it never reads as time the
  launcher measured. Games the launcher times keep their own time.
- **Not done, on purpose, listed for the analysis phase** (BAZA §8): Stats, Play something's
  weights, the Continue card and Jump back in, `last_played`, sessions from counter differences;
  suite 76 searches the code for anything else reading the hours.
- `tests/phase76_tests.py`, 60 checks, on a copy (`migrate=False`; a real library already at 4 has
  version 3's view put back from git first, every row kept): the upgrade (snapshot first, version
  4, the one schema change the view, every row of every table as it was, meta only its version, the
  same answer under four mark sets, 5x faster at least -- 105.3 ms -> 1.2 ms, fresh = 3->4 = 2->4 =
  1->4, a script 4 failing half way refused with version 3 still answering); the store's answer
  against the raw rows under the four sets; the fact and the tile line for every game under every
  set, the fact right after Source, every other fact (the money's) exactly as without it, the tiles
  on screen painted with it (`tile_subtitle` watched during a repaint); Overwatch's page;
  Settings' OK (every account Not mine, with the mouse) and a planted later reading landed by
  `_on_scanned` -- each reaching the open page, neither rebuilding the grid; the code search; the
  edge cases; a JSON library. Proven both ways: 60/60; with the six changed app files stashed back
  and `004` set aside (identical by hash after), 6 failures and 5 passes.
- **The full run was 1748 of 1754, and the 6 were suite 70's** -- not this phase's code: it picks
  its subjects from the start of the cached records, and the user's own scan after Phase 75 had
  fetched 18 history records, each carrying `details_at` and `details_cc` (Phase 70's notes).
  Section 3 rewrote such a record's file to make it "fetched again", but its moment is the
  summary's `details_at`, which the file does not move -- so nothing was re-projected and nothing
  refused; section 6 planted "zloty" records among ones already fetched for Romania, which
  `_mend_currency` rightly never asks for again. `as_fetched_before(appids, keys)` now takes the
  two notes off the records those sections use, in the copy's summary, as an older fetch left
  them (the suite's section 1 already picked such records). **`SteamWebCache.save()` writes only
  after `put()`**: a note popped by hand needs `_dirty` set, which the first version of the helper
  missed. 31/31 alone; every net clean (imports, layers, paths, scanner 0 differences, migration,
  the original folder).

## Phase 75 notes (Steam's own playtime, step 1 of 2: schema version 3)

Asked for as a brief (three tables, the reader, the hand-off, a three-way mark in Settings; the
page fact and the tile line are step 76), step 0 reported read only, approved as "go with phase
75" with three changes agreed: the views go into this upgrade, `PRICE_REQUESTS_PER_SCAN` to 8,
`steam_account.last_login`.

- **Read off this machine first, read only** (11 October): four `userdata` folders. 794996709
  GreenY, the account in use: 41 apps in its file, 30 with time, 2 with `LastPlayed` only, and one
  non-Steam shortcut (`-495349656`, a negative id, no store app -- skipped and counted).
  242635243: 209/205, Counter-Strike 2 at 135,352 minutes, **not in `loginusers.vdf`** (no name;
  its SteamID64 worked out). 313478584 GreenYRO: 141/136. 1146938852 greeny: 22/16 -- **its file
  says `Apps`**, and a case-sensitive read takes it for an account with nothing: the brief's "no
  apps block" was that trap, so every key is looked up case-insensitively. `MostRecent` is absent
  from every entry of `loginusers.vdf`; its `Timestamp` becomes `last_login`.
- **`003_steam_time.sql`** (and the same words at the end of `schema.sql`), additive only:
  `steam_account` (`account_id` the low 32 bits, `CHECK (steam_id64 = account_id +
  76561197960265728)` -- entity resolution; `is_mine` NULL/0/1, like `is_tool`; names, last login,
  first and last seen), `steam_read` (one row per account per reading: `read_at` and
  `file_modified` in UTC, apps in the file and with time -- **the read log is what bounds a
  difference**), `steam_playtime` (the four counters per account, app and reading, its
  `(account_id, observed_at)` a composite foreign key to `steam_read`, the app to `steam_app`),
  an index, `v_steam_time_latest` (the newest per pair, `ROW_NUMBER() OVER`) and `v_steam_time_mine`
  (the accounts marked mine only: minutes summed, accounts, the newest `last_played` by
  `julianday` -- it is local time with its offset, and text of two offsets does not order).
  `SCHEMA_VERSION` 3; a version-1 file goes through both scripts in one transaction.
- **The reader** (`providers/steam_userdata.py`): the Steam folder from `providers.steam.find_steam`
  (the registry; never a guessed path), `loginusers.vdf` for names, every
  `userdata\<id>\config\localconfig.vdf` for the counters (`rules.STEAM_LOCALCONFIG_APPS`,
  `STEAM_TIME_KEYS`). A file that does not parse (Steam rewrites it while it runs; the `vdf` package
  raises `SyntaxError` on one cut short) or holds no `UserLocalConfigStore` (an empty file parses to
  `{}`) is no reading, a line in the log. One moment for every account of a reading. `LastPlayed` is
  written as local time with its offset (0 is none), as `install.store_last_played` is.
- **The hand-off** (`logic/steam_time.py`), the prices' shape with a local source: the window
  computes `due(store)` (whenever the library keeps Steam time -- **local files, so with the network
  off too**) and `wanted(store, allow_network)` (every app on the accounts marked mine with no record,
  most played first; the whole list, not a slice -- the fetch skips apps whose "no store entry" is
  cached, and a cut-off list could hold only those); `ScanWorker(read_steam=, steam_records=)` calls
  `steam_time.read` after discovery and prices, which reads, appends the reading to
  `cache/steam_time.json` (`backups.atomic_write`) and fetches up to 20 records
  (`steam_web.fetch_records`); `_on_scanned` calls `steam_time.land` after the Steam projection and
  the prices, on the GUI thread -- one transaction per reading, oldest first, a refused one kept in
  the hand-off for the next scan.
- **Recorded only on change** (`LibraryStore.land_steam_time`): accounts upserted (names and last
  login by `COALESCE`, never `is_mine`), each read row added (`ON CONFLICT DO NOTHING`; a reading
  already landed adds nothing), a counter written only when new or one of its four values differs
  from that pair's newest row; an app with no `steam_app` row gets one with `has_record` 0. **A
  counter that went down is kept as read** and logged as odd. **No UPDATE or DELETE of `steam_read`
  or `steam_playtime` anywhere** (a test searches the program); `is_mine` is written by
  `set_account_mark` alone, from Settings. Rehearsed on a copy of the real library: 4 accounts,
  4 read rows, 390 counters; a second reading straight after, 0 counters.
- **The records of the history**: the fetched records reach the database through the existing
  projection, which also gives each its first price observation -- so they join the weekly batch
  (hence 8 requests). Rehearsed for real on a copy, three requests: Team Fortress 2 (free), Call of
  Duty Black Ops III (59,99 €), Rocket League (not sold any more).
- **Settings, "Steam accounts"** (`ui_settings._build_accounts`): a row "Whose time counts" ("Only
  accounts marked as yours count on a game's page and in sums. Read from Steam's files on this PC;
  nothing is sent anywhere."), then one row per account -- the persona or "Account <id>", "N games
  with time on Steam · updated <when>" -- with Mine / Not mine / Not decided as the game page's
  segmented switch at the dialog's size (`ui_rules.STEAM_ACCOUNT_MARKS`, `SETTINGS_SEGMENT_HEIGHT`),
  an exclusive `QButtonGroup`. **Saved on OK only**, by the window (`dialog.account_marks()` -> the
  changed ones -> `set_account_mark`). No account read yet, or no store: one row saying so.
- **The pad, measured before it was built**: Qt treats an exclusive group as **one stop for Tab**,
  landing on its first or last button, and moves within it by arrow keys -- choosing as it goes only
  when the focused button is the chosen one. So `ui_settings.MarkButton` hands a Tab/Backtab focus to
  the chosen choice (down lands on what the account says), and `_drive_dialog` sends left/right as
  arrow keys to a button in a group: left and right change the mark in place, as they change a
  size. The choice is ringed inside (`_ringed` says no; the stylesheet's `:focus`), with the sides'
  padding given up by what the wider ring takes -- the first render squeezed "Not mine".
- **Suite 73 asked for version 2's facts** (version 2, six objects added, "to 2" in the log, and a
  broken script 2 alone -- which at version 3 is refused for the missing script 3 before the broken
  one runs, a pass for the wrong reason); it now asks for the current version, the twelve objects,
  and the real scripts with 2 broken. Its "never more than N requests" planted 7 apps for a budget of
  2; it now plants more pairs than the budget, whatever it is. Suite 67: 19 tables, 7 views,
  version 3. 83/83 and 49/49.
- `tests/phase75_tests.py`, 102 checks, on a copy (`migrate=False`, the suite upgrades it): the
  upgrade 2 -> 3 (snapshot first, fresh equals upgraded, six objects added, the user's tables row
  for row, the projected ones only gaining) and 1 -> 3; nineteen refusals; the reader on the real
  files with **`builtins.open` watched (every Steam file opened `r`)** and every count made again
  by the test's own case-insensitive walk -- the "Apps" account, the shortcut, the unlisted
  account, last login from `Timestamp`, CS2 135,352 while its file is unchanged since 15 August;
  four made-up files (no apps block, cut short, empty, every key in another case); the landing
  (twice, unchanged, one minute more, lowered, the mark untouched, a refused reading whole and kept);
  the two views on planted rows (offsets across the instant); the records -- network off nothing,
  nobody marked nothing, the order, 20 a scan through a stand-in for the store (`steam_web._get`), the
  next scan none of them again, the projection names them and prices them, nothing to the network;
  Settings with the pad (Start, down lands on Not decided, left twice to Mine, nothing saved until
  OK, down to OK, A; then right, right, B: cancelled) and the mouse (a click, OK, only the changed
  mark), and the empty state; the window's scan (read on the scan thread, landed on the GUI thread,
  a read row per account, a counter only where one changed, no request). Proven both ways: 102/102;
  with the eight changed app files stashed back and the three new ones set aside (identical by
  hash after), 9 sections fail and 4 checks pass (the copy at version 2, Steam found, the layers,
  the real data untouched).
- **The full run was 1686 of 1694**, and the 8 were older checks, none about this phase's code
  being wrong: suite 35 asked for Settings' six sections (seven now, "Steam accounts" before the
  library's data); suite 54 allowed the ordinary weight (500) only in the window's rule and the
  game page's marks (Settings' segmented switch is the same control, so its stylesheet joins
  them); and **suite 74 counted exactly the 5 purchases it plants** -- the user's library now
  holds one of its own (Slow Roads, 5,00 €, key reseller, left by his click-through list on
  11 October), so the bundle carried 6. It now counts the purchases there are (the
  no-assumed-state rule again). After the updates: 35 78/78, 54 21/21, 74 56/56 alone; every net
  clean (imports, layers, paths 20/20, scanner 0 differences, migration, the original folder).
- **For step 76 and after** (BAZA_DE_DATE §8): the "share for analysis" export must pseudonymise
  account ids and personas -- they are personal.

## Phase 74 notes (prices, step 2 of 2: what I paid, and the money on a game's page)

Approved as "restarted it, upgrade worked - go with phase 74" -- read only first: the real
database at version 2, the backup taken (the startup one already held the file), 48 seeded, 42
observed by the startup scan in one request and landed: 90 observations, all EUR.

- **One money formatter**, `humanize.money(cents, currency)`: "59,99 €", "1.299,00 €", "12,50 lei",
  "5,00 USD" -- as the store writes it for Romania (decimal comma, dot thousands), the sign after
  the amount joined by a no-break space (`humanize.NO_BREAK`, written as an escape: the patch put a
  literal U+00A0 in first, invisible, and Phase 59 settled that code points are written as
  numbers). `rules.CURRENCY_SIGNS` holds "€" and "lei"; anything else keeps its code. Never a
  conversion. `humanize.day(value, year=None)`: "11 Oct", "20 Dec 2025" in another year, `year=True`
  always (a purchase); a moment with an offset read in local time.
- **The store** (`LibraryStore`, all SQL in `library_db`): `purchases(key)` (oldest first, an
  unknown date last, with ids), `add_purchase(key, ...)` (the game row made if needed; refused =
  None, logged), `remove_purchase(id)` -- **the one DELETE of this work, a row the user removes** --
  `all_purchases()` (by key, no ids, for the bundle), `add_purchases(by_key)` (a union by
  (bought_on, paid_cents, store), one transaction, None if refused), and `money(key)`: the latest
  observation, the range, the purchases, the paid total and currency, playtime and cents per hour,
  from `v_game_money`, `v_price_latest`, `v_price_range`. At version 1 (an upgrade refused) every one
  answers empty/None, and the menu entry is disabled.
- **The four facts** (`gamedetails.money_facts`, `MONEY_FACTS`): List price (the newest observation,
  with its discount and "as of <day>"; "free"; "not sold here"), Lowest seen (more than one
  observation and the lowest priced not the price now), Paid (one: amount, store, the whole date;
  several: the total "in N purchases"; mixed currencies: "N purchases, in more than one currency"),
  Cost per hour (paid over the launcher's hours, only within one currency and with time played).
  `metadata(record, view, money)` puts them after Source, so they land in the Details card; the
  page asks the window (`DetailPage.money_for` = `MainWindow.money_of`) as it asks for earlier
  installs. No pill, no tile, nothing on Stats.
- **What I paid...** (`ui_purchases.PurchaseDialog`, `purchases_flow`), in `ui_actions.build_menu`
  after the note, for every game: the list (or "Nothing recorded yet. A game with no purchase is
  unknown, not free."), a form -- amount (`QDoubleSpinBox`, Romanian locale so it reads "12,50"),
  currency (EUR, RON), store (an editable box with `rules.PURCHASE_STORES`, starting on the game's own
  store), date (today, or "Date unknown"), note -- Add, Remove selected... (Cancel the default,
  escape and focused button, as the uninstall question) and Close; **no button answers Return on its
  own**, so A on a box never adds half a purchase or closes the dialog. A change reloads the views.
- **The pad**, `MainWindow._drive_dialog` gained two cases: left/right on a `QAbstractSpinBox` step
  it (an amount by 1,00, a date's day), and A on an **editable** combo opens its list (Space would
  have typed a space into it).
- **The bundle** (`transfer`): `purchases.json` (`rules.TRANSFER_PURCHASES_MEMBER`,
  `{"version": 1, "games": {key: [rows]}}`), **written only when there are purchases** -- so a
  bundle without any is byte for byte what it was, and suites 26/65 are unchanged -- and counted in
  the manifest and the report. On import, after the records: `add_purchases`, never deleting; a
  bundle without the file imports as before; into a library that keeps none (JSON, or version 1)
  the rest imports and the report says how many purchases were not.
- **Every window scan says how many prices it asks for, zero included** (`prices.due`: "prices: N
  app(s) due for a price this scan", or why none: the network off, a library that keeps no
  prices) -- the click-through list's rescan needed a line to read on the six days a week nothing
  is due, when Phase 73 logged nothing at all.
- **Suite 65 compares the old export/import beside today's, report field by field**; the report
  gained `purchases` and `purchases_skipped`, so 7 of its checks failed in the first full run. It
  now takes a later field out only when it says nothing (0 -- the JSON library it runs on has no
  purchases), so a report that counted anything would still differ. The bundles were byte for byte
  the same throughout. 21/21.
- `tests/phase74_tests.py`, 56 checks: the formatter (seven amounts, the dates); the store on a
  folder game with nothing chosen for it (two purchases, a 0 one, the record unchanged, a negative
  refused, removing one, back to unknown); the dialog with the mouse (empty state, defaults, Add,
  Remove asks with Cancel safe, Cancel keeps, Remove removes, the record unchanged); **with the pad**
  -- X on the game's page, A on What I paid..., right x3 (3,00), down to Date unknown and A, down to
  Add and A, down to Remove and A (the question, Cancel under A), A (kept), A again, right to Remove,
  A (removed), B (closed), the gate open throughout -- pressed through `pads.action` from a timer;
  the four facts across every game against the views read independently, with purchases and a
  lower price planted in the copy, and their exact words; the bundle (every purchase, no ids, the
  manifest, no price series; imported, joined to one already there; twice = nothing; nothing taken
  away; an older bundle; a JSON library); the scan's price log line, network on and off. Proven both
  ways: 54/54 before the log line's two checks were added; with the eight changed app files
  stashed back and `ui_purchases.py` set aside (identical after), 13 failures and 2 passes (no
  dialog to close; the real data untouched).

## Phase 73 notes (prices, step 1 of 2: schema version 2 and the price series)

Asked for as a brief (the economic layer of the thesis: list prices over time, what was paid,
cost per hour), step 0 approved as "go with phase 73". Step 74 (the purchase dialog, the four
facts on a game's page, the money formatter, purchases in the bundle) waits for its own go.

- **The one request, kept**: `appdetails?appids=730,550,1&filters=price_overview&cc=RO&l=english`
  -- one HTTP 200 answer, a dict by appid: 730 `{"success": true, "data": []}` (free -- an empty
  *list*), 550 a `price_overview` (EUR 969, while the cached record still said 975), 1 (no such
  app) `{"success": false}`. One odd app did not spoil the batch. Saved as
  `tests/fixtures/appdetails_price_batch_2026-10-11.json` (+ `.meta.json`). **It went out twice**:
  the first script lost the answer to a backslash in a path before saving it (the trap again).
- **With the filter, `data: []` cannot tell a free game from one nothing is sold of** (a playtest):
  the cached full record's `is_free` decides (`free_hint`). A cached record with neither a price
  nor the flag is `unavailable` -- two here, the CoD MW4 beta and the WARDOGS playtest.
- **Schema evolution**: `library_db.SCHEMA_VERSION = 2`; `upgrade_scripts()` reads
  `data_access/upgrades/NNN_*.sql` (through `paths.resource_dir()`, so `app.spec` bundles the
  folder); `upgrade(conn)` runs every missing one and sets `meta.schema_version` and
  `PRAGMA user_version` **in one transaction** (both roll back) -- a script missing or refused
  raises and leaves the file as it was. **The door does it, not the store**:
  `migration.open_library()` -> `_upgraded(store)`: `backups.snapshot("before-schema-2")` (skipped
  as unchanged right after the window's startup snapshot, as the migration's is), the upgrade, then
  `_seed`. Refused: logged ("stays at version 1 ... refused"), the store stays at version 1 and its
  price methods answer None/empty -- the launcher runs as before. A store opened anywhere else (a
  test, an export) never upgrades. `schema.sql` is the whole current schema; the JSON migration
  creates version 2 directly and seeds too.
- **Additive only (expand before contract)**: two tables, an index, three views; nothing dropped or
  renamed. `steam_app` keeps its price columns -- SQLite cannot drop a column a CHECK names without
  rebuilding the table -- but `v_price_latest` is the answer to "what does it cost now" from here on;
  `v_library`'s price columns are the cached record's, unchanged. Their removal is a candidate for a
  later, separate upgrade.
- **`price_snapshot`**: `PRIMARY KEY (appid, observed_at)`, `kind` priced/free/unavailable, the four
  price columns all present for priced and all NULL otherwise (one CASE CHECK), **`observed_at`
  always UTC `+00:00`** (a GLOB CHECK) so text order is time order -- the seeded `details_at` is
  UTC already, and file times are written in UTC. Append-only: `LibraryStore.add_observations`
  (`INSERT ... ON CONFLICT DO NOTHING`, a savepoint per row, answering what is in the database and
  what was refused) is the only writer; no UPDATE/DELETE/REPLACE of it anywhere (suite 73 searches
  every `.py` and `.sql` outside tests).
- **`purchase`**: `paid_cents >= 0`, `currency` three capitals default EUR, `store` not blank,
  `bought_on` an ISO date or NULL (`date(x) IS x`), `recorded_at`; `game_id` ON DELETE CASCADE like
  the other per-game tables. No row = unknown, never zero. Created now, used from Phase 74.
- **Views**: `v_price_latest` (ROW_NUMBER per appid), `v_price_range` (count, first, last, lowest and
  highest priced, each the first time seen), `v_game_money` (latest list price via `steam_appid`,
  purchases count, a paid total only within one currency, playtime, cents per hour where both).
- **Seeding is the projection**: `steam_projection.refresh` now also turns each cached record into
  one observation dated by `details_fetched_at` (only 2 records have a `details_at`; 46 take their
  file's time) through `steam_web.price_observation`, the same function the weekly fetch uses, and
  only for records whose observation is missing -- so the first pass after the upgrade seeds 48
  rows (40 priced, 6 free, 2 unavailable) and every later pass adds only what is new.
- **The weekly observation** (`logic/prices.py`): `due(store, allow_network)` on the GUI thread
  before every window scan (`LibraryStore.prices_due(days, now)`: `has_record = 1`, newest older than
  7 days or none, the oldest first) -> `ScanWorker(config, parent, prices_due=)` (an argument, never
  config.json) -> after discovery, on the scan thread, `prices.observe` -> `steam_web.observe_prices`:
  a batch per request, at most 2 requests (a `_Budget` of its own: each stage of a scan has its own
  allowance, there is no one "scan budget"), one UTC moment per request, a failed request writes
  nothing, an app missing or odd in the answer is skipped and logged, a non-EUR currency logged and
  kept -> `cache/price_observations.json` (atomic; empty = no file) -> `_on_scanned`, after
  `steam_projection.refresh`, `prices.land(store)`: observations into the series, those in the
  database out of the hand-off, one refused stays (logged) for the next scan. Log lines: "steam
  prices: N app(s) due, M observation(s) recorded for the window" and "prices: N observation(s)
  landed in the library, M kept for the next scan". All window scans do it (startup, manual,
  watch, and the rare first-run and after-uninstall ones -- the due list is usually empty).
- **`test_sandbox.start()` upgrades a copy whose database an older version made**, through
  `open_library` (a snapshot in the copy's backups first, as the launcher will), so suites run on
  what the launcher runs on after the user's next start. `start(migrate=False)` keeps it as it is.
- `tests/phase73_tests.py`, 83 checks, the network blocked outright (`urllib.request.urlopen`
  replaced) and Steam's answers handed to `steam_web._get` where needed: the upgrade on a copy of
  the real library (snapshot first holding the v1 file, version 2 in store/meta/user_version,
  fresh v2 = upgraded v1 as normalised `sqlite_master`, six objects added and none removed, every
  record and entry as before, the log); the seeding (one row per cached record, its moment, its
  kind, its exact price; twice = no change); a refused upgrade, two ways (a script failing half way,
  a script missing) -- file fingerprint unchanged, the launcher opening on version 1 with the reason
  logged and no prices due, the next start upgrading; nine refusals of `price_snapshot` and five of
  `purchase`; append-only by search and by the store's methods; the fixture read (and 730 without
  its hint read as unavailable); failed requests (none, not JSON, not a dict) write nothing; one
  request for three apps; an app missing skipped; the 2-request cap; landing, a refused row kept,
  landing twice changing nothing, the views; the due list (a week old or none, oldest first,
  nothing when fresh, all a week later, nothing with the network off, everything on a new database,
  nothing on the JSON store); the window's own scan with the network on asking for the 40 due apps
  in 1 request and the GUI thread writing them, and with it off asking nothing; scanner.py imports
  nothing that observes prices. When the real library is already at version 2 the suite builds a
  version-1 copy from it with the Phase 67 schema read out of git, so it keeps proving the upgrade.
  Proven both ways: 83/83; with the ten changed app files stashed back and `logic/prices.py` and
  `002_prices.sql` set aside (identical after), 10 failures (19 checks hold either way -- the
  refusals pass vacuously when the tables do not exist, which is why each has an "is taken" twin
  that fails there).
- **Suite 67 asked for the old schema** (14 tables, 2 views, version 1); it now asks for 16, 5 and
  `SCHEMA_VERSION` (2). 49/49.
- **The first full run: 1533 of 1535 and the scanner net with 2 differences -- the user's library
  again, not this phase.** Between Phases 72 and 73 he renamed the Remastered Witcher 3 folder back
  to `C:\games\The Witcher 3` and played it there (13:49-13:53): the scanner net saw the reverse of
  Phase 72's move, and suite 36's "already carried" branch found **8** earlier copies of saves where
  it asked for 7 -- the Remastered install, gone again, had made one, and it is offered, rightly,
  as an earlier install's. The branch now asks that the GOG install's 7 are all offered, that every
  other one offered is an earlier install's (never one installed), and that each names the game it
  was made for. 47/47. The scanner's saved run re-saved; the one from Phase 72 kept as
  `tests/baseline/scanner-2026-10-11-remastered.json`.

## Phase 72 notes (a cover is not a banner; OK does not unmaximise)

Reported from use, after the click-through list ("all good"): "when I set a custom cover for
a game it automatically makes it a banner too sometimes (check Rehaunted) and it doesn't look
good ... only stays as a cover and cycles through the images as normal", and "when I open the
settings, then click OK, the launcher unmaximizes itself". Both read off the code and the real
data (read only) before anything changed.

- **The banner.** Nothing ever wrote the cover into the banner slot -- `banner_path` is NULL
  for Rehaunted; the slots stay independent (Phase 9). The picture's frame 0 is
  `covers.banner(view)`: the game's wide art, **else its cover blurred into a backdrop**
  (Phase 5, `_banner_from_cover`), else its colour. Steam has no hero for Rehaunted (4538140:
  only the capsule in `steam_art`), so its SteamGridDB cover was stretched across the page,
  first in the cycle, before its five screenshots. Four games here are like that: CONTROL
  Resonant, Rehaunted, SILENT HILL Townfall, WARDOGS -- a chosen cover, no wide art, screenshots.
- **The fix, in `ui_hero.Banner` only**: frame 0 of a game with no `banner_source` is a
  stand-in (`_stand_in`). The first real image to arrive -- a screenshot, or a SteamGridDB
  hero for a game Steam has no screenshots for (Phase 12) -- takes its place: at once if the
  stand-in was never painted (images already on disk land during `set_view`, before the page
  is drawn), by the cycle's own fade if it was (`_stand_in_seen`, `_replacing`; the stand-in
  is dropped in `_on_faded`, and no dots show while it leaves). `set_view` clears
  `_replacing` **before** stopping the animation: stopping it ends the fade, and a stand-in
  still marked as leaving would be dropped from the next game's frames (suite 72 checks it).
  Unchanged: a game with wide art of its own still starts on it; a banner chosen by hand is
  shown alone and never cycled; a game with no images at all keeps the stand-in (BloodBorne
  here, with the network off -- with the SteamGridDB key, its heroes replace it).
- **Settings' OK**: `open_settings` ends with `set_tv_mode(values["tv_mode"])` -- it re-applies
  the theme and every metric, so a scale change lands -- and its desk branch was
  `self.showNormal()`, every time, maximised or not. Now: entering TV mode is as before;
  **leaving it** (only when the window is fullscreen) is `showNormal()` then
  `restoreGeometry(self._normal_geometry)` -- in that order, since a maximised geometry
  restored onto a fullscreen window keeps it fullscreen -- so it comes back maximised if it
  was; and otherwise **the window's state is not touched at all**.
- **Found beside it, the same defect**: `_come_back_to_front` restored a minimised launcher
  with `showNormal()` (or `showFullScreen()` in TV mode), so a maximised launcher minimised
  while a game ran came back as a window. Now it clears only the minimised flag
  (`setWindowState(state & ~WindowMinimized | WindowActive)`) -- Windows keeps the
  maximised or fullscreen state under it -- and in TV mode makes sure of fullscreen.
- `tests/phase72_tests.py`, 23 checks on the live window, the cached screenshots copied in and
  nothing fetched: Rehaunted's picture starts on its first screenshot, the cover nowhere in the
  cycle, all five there in order, dots for them, the chosen cover still beside the title;
  Aimlabs (a hero of its own) still starts on it; CULTIC (a chosen banner) alone, not cycled;
  BloodBorne (no images) keeps the stand-in; a stand-in already on screen fades to the first
  image, no dots meanwhile, an image arriving mid-fade kept, a game opened mid-fade keeps its
  own frame; maximised -> Settings' OK -> still maximised; TV on and off -> maximised again;
  minimised from maximised -> back after a game -> maximised; in TV mode -> fullscreen.
  Proven both ways: 23/23; with `ui_hero.py` and `ui_window.py` stashed back to the tag
  (identical after), 7 failures -- the cover first in Rehaunted's cycle (6 frames for 5
  images), the fade's section, and all three unmaximisings -- the user's two reports exactly.
- **The first full run was not green, and none of it was this phase** (each re-run alone, and
  69 also on the code before it): the user was installing **The Witcher 3 Wild Hunt --
  Remastered [Build 25773555]** into a new folder while it ran, his launcher open. Its folder
  watch scanned at 04:17 with the copy half done ("no exe found among 9 files") and wrote the
  database -- suites 30 and 34's guards said so (`['library.db']`), as they should; suite 28 lost
  the foreground (19/19 alone); the scanner net saw the old Witcher folder gone and the new one
  arrived. Two tests assumed the machine stood still and were changed to check the rule instead:
  - **Suite 69, section 6**: restoring a pre-switch snapshot writes the database's install rows
    back out as `catalog.json` (Phase 68, by design), so the rebuilt library knows what the
    *last scan* found -- here 34, where the copy's older catalogue had 33. It now checks the
    snapshot's records exactly, that anything more is a newcomer carrying only what the merge
    stamps (`first_seen`, NEW, `known_as`), and that the installed games are the last scan's.
    32/32 (one check more).
  - **Suite 36, section 4**: written for two Witcher installs (GOG -> `c:\games\the witcher 3`),
    carried over by the user after Phase 36 (Phase 37 notes); now there is a third. The suite scans the disk itself
    when its copy does not know `NEW` (read only), and a new branch checks the chain: the
    Remastered build is offered `c:\games\the witcher 3` -- the install holding the history,
    6 h 15 min with the GOG time in it -- never the GOG record again; carrying it over adds the
    time and every session, `earlier_keys` holds both installs before it, the middle record
    keeps only its dates, name and where it went. 46/46. **On the real machine the Remastered
    build's page will ask "Played before?"** with exactly that offer.
  - **The scanner net's saved run re-saved** (`check_scanner.py save`), the old one kept as
    `tests/baseline/scanner-until-2026-10-11.json` (git-ignored, as before): a compare first
    showed only the Witcher move (plus the allowed drift).

## Phase 71 notes (the database, step 8 of 8: closing)

Approved as "yes to both, then go with phase 71" (both: `&cc=RO`, and the leftover test copies to
the Recycle Bin -- Phase 70's notes). **The database work, Phases 63-71, is complete.**

- **ARHITECTURA.md was still at Phase 53** in its status and data story. Brought up to the
  database: §1's data story and §2.7 (the library in `library.db`, all SQL in `data_access/`, the
  dict facade unchanged), the layer table and the diagram counted again (presentation 31,
  logic 17, data_access 4 + `schema.sql`; the files node `library.db · config.json`), §2.9 (35
  suites, six nets in `run_all`), §5's two walks (the window opens the library through
  `open_library`; a scan's findings and the Steam projection written on the GUI thread; a session
  written with its game in one transaction; save folders into `save_folder`), §10 closed, §12
  items 8-9 updated and 21-22 added (the ReadOnly folders; BAZA §16 for the rest).
- **§4, the module map, regenerated from the code** as at step 9 (scratch `module_map.py` +
  `map_update.py`): line counts and project imports, grouped by layer, read from every file --
  117 rows re-measured, 12 added (`library_db`, `migration`, `steam_projection`, `check_layers`,
  `check_migration`, suites 64-70); three descriptions the database changed rewritten
  (`catalog_io`, `backups`, `test_sandbox`).
- **BAZA_DE_DATE.md in its final form**: the status line and §1 in the past tense of a thing done
  (the switch at 23:05 on 10 October, its figures); §14 closes with **"Cum vezi baza"** -- a copy
  first, always; `python -m sqlite3` on it; seven queries (meta, sessions by month, by local hour,
  the last scans, playtime by Steam genre, prices not in euros, games known but not installed);
  DB Browser for SQLite with "Open Database Read Only..." -- and **"Verificarea finală, făcută de
  tine"**, ten steps on **Slow Roads** (checked read-only to carry nothing the user chose: no
  cover, banner, name, note, mark or star) that between them touch every table, with the query to
  run after each. Nothing in it carries over, restores, imports or uninstalls; step 7 only
  looks at SnowRunner's "Played before?" card (confirmed on a copy: SnowRunner and The Blood of
  Dawnwalker are the two pages that ask).
- **Every query was run on a copy of the real database** before it went in; one was wrong as
  first written (`install_dir`, which `v_library` does not have -- it has `installed`) and was
  corrected. The PowerShell commands were run as written, on a copy, the real file's hash the same
  after.
- `rules.STEAM_STORE_CURRENCY`'s comment said "46 of 48 records"; it is 38 of the 40 priced ones
  (8 have no price) -- corrected, in Phase 70's second-half commit.
- **Two commits, one evening**: Phase 70's second half was committed first (`before-phase-71` is
  on it); Phase 71's documents, written while its full run went, were set aside and put back
  on top of it, so each phase keeps its own restore point.
- **The closing run: ALL GREEN 1428/1428**, the six nets clean, the real data folder untouched
  (the two records already carried `details_cc`, so the scanner net asked for nothing). One
  leftover copy in the temp folder -- a check script of this phase that stopped on a wrong
  call before its clean-up -- went to the Recycle Bin like the 239.

## Phase 70 notes (the database, step 7 of 8: the Steam projection after every scan)

Approved as "yes fix the backups, then go with phase 70" -- the backups fix is its own commit,
before `before-phase-70` (see the Phase 69 notes). **The `&cc=RO` half is not built**: it changes
a web address, and BAZA_DE_DATE (§14, row 70) says it asks separately first.

- **Measured first, read only**: the real database's 48 `steam_app` rows matched the 48 cached
  records one for one, all `has_record = 1`; but their `fetched_at` is the summary's
  (`steam_web.json`), and that **moves whenever a picture is cached** (`SteamWebCache.put` stamps
  every write) -- 38 of 47 differ from when the record's file was written; Slow Roads' says
  6 October, its record is from 30 September. So the cache now says when a record was fetched:
  `_fetch_details` returns `details_at` beside `app_type`/`header_image`/`has_details`, only when
  the file was really written (`_store_details` returns a bool now), and `enrich` files it in the
  summary as before. `steam_web.details_fetched_at(cache_dir)` gives every stored record's
  moment: `details_at`, else its file's time -- the fetch itself, nothing else writes that file.
- **`logic/steam_projection.refresh(store)`**, called by `MainWindow._on_scanned` right after the
  scan's findings are written -- the GUI thread, the one writer. A record is projected again when
  the database has no row with a record for its appid or the row's `fetched_at` is not the cache's
  moment; only those files are read, so a quiet scan reads none. `LibraryStore.steam_fetched()`
  (appid -> moment; None if the database cannot say, logged) and `store_steam_records({appid:
  (record, moment)})` -- one transaction, a savepoint per record as the loader has it: one that
  does not fit is left as the database had it and named (`refused`), the rest land. The JSON store
  (after a refused migration) answers `steam_fetched()` with None: it keeps no projection, so
  nothing is read. Nothing is fetched here; the scan has done that under its own budget.
- **The migration uses the same moments**: `library_db.load(..., steam_fetched=)` from
  `migration.build` (`details_fetched_at`); without it, the summary's time, as before.
- **Moments are kept to the second**, as every time in the library is: the same record written
  twice inside one second would look unchanged. A fetch never does that (a request a second at
  most, a record fetched again after 30 days); suite 70's own rewrite waits a second.
- `tests/phase70_tests.py`, 23 checks, on the database copy with the Steam caches copied in and
  nothing fetched (`steam_web._get` handed Steam's answer): a record fetched says when, its file
  what Steam answered, the moment the cache gives is that one; 47 older records take their file's
  time, not the summary's (38 differ); after a real scan (`start_scan(background=True)`)
  `steam_app` and its three satellites equal a database made from the cache alone (48 apps, 113
  genres, 645 categories, 113 companies), the re-fetched record's new price and moment in it,
  written by the GUI thread (39 records the first time -- every one whose summary time had
  moved); a second scan writes none; a record that does not fit (a genre with no id) refused,
  named, logged, its row as it was, another changed in the same pass landed, and both taken in
  once put right; the JSON store reads and writes nothing; a migration writes the same moments.
  Proven both ways: 23/23; with the five app files stashed back to the tag and
  `logic/steam_projection.py` set aside (put back identical by hash, line endings aside), 6
  failures and 3 passes (a file written, the window on the database, the real library untouched).
- **A mistake on the way, and what it did**: suite 24 was run bare once (`python
  tests\phase24_tests.py`) instead of through `run_sandboxed.py` -- the rule at the top of this
  file. It opens a real `MainWindow` on the real data, which did what one start of the launcher
  does: a startup snapshot (`2026-10-10_23-28-55`; its rotation removed the 18 empty folders, with
  the fix, and the 20:28 snapshot, which the next start would have aged out the same way), a quiet
  startup scan (scan 3, `startup`), the news check, `config.json` rewritten with the same bytes --
  and, with this phase's code, the projection: 39 `steam_app` rows' `fetched_at` corrected, every
  other value the same. Checked by comparing the database with that snapshot row by row: only
  `install`, `scan` and those 39 rows differ; no game, session, save folder or lineage row.
- **The leftover test copies in the temp folder** (239, 158 MB by their files, 20 of them holding
  a `config.json` with a SteamGridDB key) went to the Recycle Bin on the user's yes, through
  `SHFileOperationW` with `FOF_ALLOWUNDO`: the bin grew by exactly 239 items and 158.4 MB, none
  left in the temp folder.

**The second half, on its own yes ("yes to both")**: the store is asked for Romania.

- `rules.STEAM_STORE_COUNTRY = "RO"` is in both store addresses -- appdetails gains `&cc=RO`, the
  search's `cc=RO` now comes from the same constant (the same string). `rules.STEAM_STORE_CURRENCY
  = "EUR"`: what the store answers in for it (38 of the 40 priced records here).
- **The two records in zloty are fetched again once, by a scan with the network on**: `steam_web._mend_currency`, at the end of `enrich`, asks once for every stored record
  priced in another currency and not fetched for the country -- **installed or not**: STALKER 2
  (1643320) is not installed, so no scan would ever have reached it; Slow Roads (3431300) is. A
  record fetched since carries `details_cc` beside `details_at`; one the store no longer sells
  there is marked and keeps its record (its summary's `app_type` untouched); a request with no
  answer is tried at the next scan. Reading the 48 records to look takes ~10 ms in the scan
  thread. Here that was **two requests, once** -- made at 23:51 on 10 October, not at the user's
  next start as planned, by **the scanner net in `run_all`**, which runs a real scan with the real
  config (network on) on the real cache. The store answered in euros (STALKER 2 5999, Slow Roads
  769 cents; `final_formatted` "59,99€", "7,69€"), which confirms `STEAM_STORE_CURRENCY`. The
  scanner writes no database, so the launcher's first scan projects them into `steam_app`. Found
  by checking the real data folder after the run: those two files and `steam_web.json` were the
  only files written; the three records the suite made to look foreign were written in its own
  copy only (the real ones still in euros, unmarked).
- Suite 70 section 6 (8 checks): both addresses name the country; three records made to look
  like the zloty ones beside the two real ones -- only those five asked for, each once, every
  request with `&cc=RO`; the one answered in euros; the one "no longer sold" kept and not asked
  again; the one with no answer asked again at the next scan, alone; the projection carries the
  euro price into the database. 31/31; with `rules.py` and `steam_web.py` stashed back
  (identical after), the address check fails and the section cannot run.

## Phase 69 notes (the database, step 6 of 8: the switch)

Approved as "go with phase 69". **The program now opens its library through
`logic/migration.open_library()`**: `data/library.db` if it exists; otherwise, with
`overrides.json` there, `migrate()`; otherwise a fresh database (a first run).

- **The migration**, as BAZA_DE_DATE §9 has it: a `before-database` snapshot (skipped as
  unchanged right after the window's startup one, which is named in the log instead); `build()`
  into `library.db.building`; only if `Built.good` renamed over `library.db`; then
  `overrides.json` and `catalog.json` moved into `data/migrated/<time>/` (`rules.MIGRATED_DIRNAME`)
  -- moved, never deleted. Refused: the build is kept as `library.db.refused`, the reasons go to
  the log as plain text (record and rule -- the first version logged a list's repr, doubling
  every backslash, which suite 69 caught), the window runs on `catalog_io.Overrides()` exactly as
  before, and the next start tries again. An `overrides.json` beside an existing database is not
  read and the log says so -- what an old launcher left open during the switch would leave.
- **The window**: `self.overrides = migration.open_library()`; the catalogue through the store
  (`load_catalog`, `save_catalog(entries, roots, trigger=, started_at=)`) -- the JSON store gained
  the same three methods (`load_catalog`, `save_catalog`, `last_scan_time`) and a no-op `close`,
  so the window speaks to either alike; `start_scan(..., trigger=)` records who asked
  (`first_run` from `__init__`, `startup`, `manual`, `watch`, `uninstall` from `ui_removal`) and
  when it began; `closeEvent` closes the store; `reload_after_restore` closes it and calls
  `open_library()` again. Storage's "sizes as of" is the store's `last_scan_time`.
- **LibraryStore can be released**: `close()` lets go of the file and the next use reopens it
  -- on the thread that made the store only, or sqlite3's ProgrammingError; `library_db.release(path)`
  closes every open store on a file (a `WeakSet` of them) so `backups.restore` can replace or move
  it -- Windows will not, with a connection open. `library_db.open_saved()` opens the library as
  saved without migrating (the database, else the JSON) -- for transfer with no window store
  (opened and closed per call now) and the tests.
- **Restoring a snapshot from before the switch** (from Phase 68): `backups.restore` writes the
  database's install rows back out as `catalog.json`, moves the database into
  `migrated/<the safety snapshot>-replaced/`, puts the JSON back, and says "The library database
  will be built again from them"; `reload_after_restore` then migrates. Suite 69 proves the
  rebuilt library equals the snapshot's records and still knows the installed games.
- **The tests run on a database now**: `test_sandbox.start(migrate=True)` (the default) runs the
  launcher's own migration on the copy before the suite begins whenever the copy is still JSON
  -- so suites run on what the launcher runs on, before and after the user's switch alike.
  `migrate=False` keeps the copy as it is for the JSON-era comparisons (64, 65, 67, 68), the
  migration's own suite (69), and `check_imports`, `check_paths`, `check_migration`. The real
  files are copied only if they exist (`read_real`), the real database read only
  (`copy_real_db`, which suite 26's own sandbox uses too); `finish` closes stores still open in
  the copy. The helpers are database-aware: `library()` (the store the app opens),
  `records`/`put_records`/`separate_store` (a database by default, `kind="json"` for the
  comparisons), `records_in` (a snapshot's database, read only), `real_records`/`real_stamp`.
  Suites 23-25, 27 and 37 used `catalog_io.Overrides()`/`load_catalog()` directly and now use
  `test_sandbox.library()`; suite 66 writes through it; suite 67's "not used yet" checks now say
  who uses the database (the migration, backups, transfer; the migration by the window) and that
  only the migration opens a `LibraryStore`. `check_migration`, after the switch, rebuilds a fresh
  database from what the copy's holds -- the round trip still proven.
- `tests/phase69_tests.py`, 31 checks, on a raw JSON copy: the migration (database in place,
  both files moved byte for byte, nothing half made left, 66 records and 34 entries back, the
  snapshot, the log line); a second start does nothing; a stray overrides.json beside the database
  ignored, and said; **a refused migration in a second process on a copy of its own** (a mark
  outside the three planted) -- JSON store, no database, both files untouched, the refused build
  kept, the reason logged, refused again next start; the window on the database -- a star saved
  and taken back, **a scan from the folder watch written by the GUI thread** (`write_catalog`
  watched), its scan row `watch` with its start, Storage's time; a database snapshot restored with
  the window's store open; a pre-switch snapshot restored, the database set aside, rebuilt by the
  migration, the records the snapshot's, the installed games kept.
- **Suite 24's stand-in store** (`FakeOverrides`, a `get` alone) failed the first full run once
  `storage.gather` asked the store for its scan time; it now answers `last_scan_time()` with None
  ("no scan known"), as a store must since this phase. 71/71.
- **The real migration is the user's** -- and he ran it, starting the launcher at 23:05:29 on
  10 October: the startup snapshot `2026-10-10_23-05-29` (overrides.json, config.json), then
  "built ... 0 misfit(s), 0 problem(s)" and "the library moved into library.db": 66 records,
  113 sessions, 5,378 minutes, 323,125 s, 15 save folders, 1 lineage, 34 installs, 48 Steam apps,
  0 foreign key violations; overrides.json and catalog.json in `data/migrated/2026-10-10_23-05-30/`,
  the snapshot holding the very file moved. Read back read-only afterwards: 66 of 66 records equal
  but one field written since (The Witcher 3's `save_dirs_checked`, by the saves search at
  23:06:05), 34 of 34 entries equal; scans `migration` then `startup`.
- **Then, on his yes, both data files left git's index** (`git rm --cached`, `/data/config.json`
  and `/data/overrides.json` in `.gitignore`); `config.json` stays on disk, as it must.
- **Found while checking, not fixed**: 18 empty snapshot folders in `data/backups/`, and a
  "could not remove the old backup ... Access is denied" warning for each at every start since
  7 October. Every snapshot folder created from the copy (6 Oct 15:07) until 10 Oct 14:45 carries
  Windows' **ReadOnly** folder attribute -- the ones from 20:28 that evening do not; what set it is
  not known -- and `RemoveDirectory` refuses a read-only folder even when empty, so the rotation
  deletes the files and leaves the folder. **Protection is intact**: 15 full snapshots, the
  newest five and one per day, none of the empties in the keep set. But the Restore dialog lists
  them as "empty". The fix waits for the user: prune clears the attribute and retries.
- **Fixed on his go ("yes fix the backups"), in its own commit before Phase 70.** Measured
  first: **113 of the project's 163 folders** carry the mark -- everything made from the copy
  (6 Oct 15:07) to 10 Oct 14:45, in `data/`, `docs/`, `tests/`, the cache -- none made since;
  nothing in the launcher sets it, and the cause is still unknown. Reproduced in a scratch
  folder: `shutil.rmtree` empties a read-only folder and then fails "Access is denied";
  `os.chmod(path, stat.S_IWRITE)` clears the mark on Python 3.14 and the folder goes.
  `backups.prune` now removes with `onexc=_clear_read_only` (on a `PermissionError` only: the
  mark off, the same call again; anything else still logged). The 18 empties are outside the
  keep set, so the next snapshot's rotation removes them. **Phase 61's note was wrong**: its 8
  folders were this mark, not the shell. The same mark reached the tests: `copytree` copies
  it, so `test_sandbox.finish` (`ignore_errors=True`) left every copy holding the cache or the
  save copies in the temp folder -- 235 of them, 104 MB, 20 holding a `config.json`. It now
  removes with the same clear-and-again (`_writable_and_again`), and says so if something
  still stays. Suite 68 gained section 8 (thirteen planted read-only snapshot folders, a
  read-only file in each: the four past both tiers removed, folder and all, every kept one
  whole) and a last check (the copy is gone): 27/27; with `backups.py` stashed, 2 failures --
  the rotation removes nothing, four emptied folders left; with the old clean-up, 1.
- **Found by that same run: the suites written for the JSON had broken at the user's switch.**
  `start(migrate=False)` meant "the copy as it is", and since 23:05 the real folder has no
  `overrides.json` or `catalog.json` -- suites 64, 65, 68, 69 and `check_paths` stopped on a
  missing file. `test_sandbox.start(as_json=True)` is the form they need: while the real folder
  was JSON a plain copy; since the switch the copy's database written out into the two files
  by `LibraryStore.export_records`/`load_catalog`, `Overrides.import_records` and
  `catalog_io.save_catalog`, and removed from the copy (the round trip check_migration proves).
  64, 65, 67, 68 and 69 (the child process too) ask for it; `check_paths` sections 3 and 3b
  plant a small file for a real one no longer there (`plant_stand_ins`). All eight that ran
  without migrating pass again: check_paths 20/20, check_migration, check_imports, 64 23/23,
  65 21/21, 67 49/49, 68 27/27, 69 31/31. **ALL GREEN 1397/1397**, every net clean, and the
  run's 35 sandboxes left nothing in the temp folder (239 there before it, 239 after).

## Phase 68 notes (the database, step 5 of 8: what protects the data learns the database)

Approved as "yes bundle the fonts too, go with phase 68". **The program still runs on the
JSON**; no `library.db` exists in the real data folder yet. Everything below is ready for the
day one does.

- **Snapshots** (`backups.py`): when `data/library.db` exists, a snapshot also holds a copy of
  it made with `library_db.copy_database` -- SQLite's `backup()` from a connection of its own,
  never a file copy of a database that may be open -- and "nothing changed" compares it with
  the newest snapshot's copy by `library_db.file_fingerprint` (sha256 of `iterdump()`), the two
  JSON files still byte for byte. `snapshot()` catches everything now (it never raises).
  **Restore** puts a held database back with `library_db.put_back`: a `backup()` copy into
  `library.db.restoring` beside it, `os.replace` over it; a journal left by a cut-short write
  is settled first by opening the old file once (SQLite rolls it back), so it cannot be applied
  to the new one; the store must be closed (Windows will not replace an open file -- Phase 69's
  `reload_after_restore` closes it). The message names three files as "a, b and c"; with two it
  is word for word what it was.
- **Moved to Phase 69, on purpose**: restoring a JSON-only snapshot after the switch must rebuild
  the database from it through the migration. That needs `logic/migration.py`, a layer above
  `backups.py`, so it is wired where the switch is. Today such a snapshot restores the two files
  and leaves any database alone (suite 68 checks).
- **The sandbox** (`test_sandbox.py`): `start()` copies a real `library.db`, if there is one,
  through `backup()` from a **read-only** connection (`file:...?mode=ro`, so the guard cannot
  write a byte of it), and `real_changes()` compares it by `db_fingerprint` -- computed in
  test_sandbox itself, not by the app's code, so the guard does not depend on what it guards.
  `check_paths` section 3b proves it as Phase 38 did: copied as it is; a write that leaves
  other bytes but the same content is no alarm; a planted change is reported. 20/20.
  `library_db` needs no place in `start()`'s guard: it binds no path at import.
- **Constants**: `rules.LIBRARY_DB_FILE`; the bundle's member names split off `PROTECTED_FILES`
  (`TRANSFER_RECORDS_MEMBER`, `TRANSFER_CONFIG_MEMBER`, the same names) so the bundle keeps its
  format when what is on disk changes; transfer and suites 26/65 use them.
- **Keep-lists**: `packaging/installer.py`'s `USER_DATA` has `library.db` and
  `library.db-journal` -- on the old list an upgrade deleted both (suite 68 shows it, on the
  stashed file); `logic/uninstall.py`'s copy, which nothing reads, kept in step. An uninstall
  that keeps the data removes only `_internal` and the exe, so the database stays.
- **`packaging/app.spec` bundles `data_access/schema.sql` and `presentation/fonts`** (Inter,
  Inter Display, Phosphor, their licences) -- ARHITECTURA §12 item 18, open since Phase 54,
  closed. **The installer was rebuilt (29 s, 72 MB) and run for real** in a fake profile
  (scratch `installer_test68.py`, 20/20): the schema and all 11 font files in the frozen app
  byte for byte; installed with its four shortcuts and its Add/Remove entry in the fake
  profile; an upgrade kept a planted `library.db` and journal byte for byte and removed a stray
  file; the installed program ran 25 s, logged "installed copy" and "bundled fonts: Inter, Inter
  Medium, Inter SemiBold, Inter Display, Inter Display SemiBold, Phosphor-Fill, Phosphor", no
  error; a quiet uninstall removed the program, kept the data, its shortcuts and its registry
  entry; the user's four real shortcuts byte for byte as before; no entry left in HKCU.
  Afterwards `build/`, `dist/` (372 MB) and seven `__pycache__` folders went to the Recycle Bin,
  as in Phase 47 -- `packaging\build.py` rebuilds the installer in half a minute.
- `tests/phase68_tests.py`, 22 checks, on a sandbox with a database built where the launcher
  will keep it: a snapshot without one is what it was; with one, its copy holds what the live
  one holds (copied while a `LibraryStore` holds it open); twenty snapshots and two windows, not
  one more; a change made and undone (other bytes), none; a real change, one; a restore puts the
  snapshot's library back, saves the replaced one first, opens as a store, leaves nothing beside
  it; a JSON-only snapshot restores the two files; the upgrade keep-list on a planted folder; the
  spec's two entries. Each section counts as one failure if it cannot run to its end; with the
  three changed files stashed back to the tag, 8 pass and 9 fail -- the upgrade deleting
  `library.db` and its journal among them.
- **Suite 67 asked for the old fact** ("only `logic/migration.py` uses the database module")
  and failed once in the first full run: `backups.py` uses its file helpers now. It now asks
  for the two users, and newly checks the property that matters -- nothing outside
  `library_db` opens a `LibraryStore` yet. 49/49.

## Phase 67 notes (the database, step 4 of 8: built beside the JSON, checked, not used)

Approved as "go with phase 67". **The program still runs on the JSON**; nothing in the app
imports the database code except `logic/migration.py`, and nothing imports that yet.

- **`data_access/schema.sql`** is the schema as BAZA_DE_DATE §5 has it, with three changes the
  code forced (each in §5): `game.first_seen` **may be NULL** -- the brief said NOT NULL, and the
  program's own order disproves it: a scan writes what it found before the merge stamps a new
  game, its install row needs a game row, and inventing a date would cost the game its NEW tag
  and its "New game" message; NULL means "no record yet". `install.position` keeps the scan's
  order (`ui_window._same_entries` compares the lists). `v_library` names an installed game
  from `install.display_name` too. Read through `paths.resource_dir()`, so the installer must
  bundle it (Phase 68, with the fonts).
- **`data_access/library_db.py`** holds all the SQL. Connections are opened with
  `autocommit=True` and `PRAGMA foreign_keys = ON`; every write is an explicit
  `BEGIN IMMEDIATE ... COMMIT`. `write_record` maps a record to its rows (the game row, and
  its sessions, save folders and lineage replaced), `read_records` maps back -- the same
  dict shape overrides.json holds, a game row with nothing of the user's on it being no
  record. `known_as` comes back only when the program wrote it (`name_origin = 'scan'`),
  `appid` only when chosen; the names and links the migration recovers stay for the
  analysis. Sessions are read in **instant** order (`julianday`, offset-aware), the order
  `sessions.dump` writes, not text order. `store_steam_app` is the one Steam projection
  (replaces the satellites, leaves a non-number or non-date NULL with a note, never converts
  a currency). `write_catalog`/`read_entries`/`last_scan_time` are the catalogue's; a scan
  sets a game's Steam link only where none was chosen, and keeps it when a later scan no
  longer finds the game. `load` builds the tables from the records, the entries and the
  Steam caches, each record in a savepoint, refusals listed whole and never coerced, then
  recovers names and links for games no longer installed. `verify` is the migration's test.
  `fingerprint` is a sha256 of `iterdump()` (for Phase 68's backups).
- **`LibraryStore`** is `catalog_io.Overrides` on SQLite: the same operations, the same live
  dicts from `get`, every change written through in one transaction; a refused write leaves
  the database as it was, re-reads memory from it, and answers False. No `save()`, no `.games`.
- **`catalog_io.merge` and `relocate_artwork` now use `values_of`/`update_many`** (the records
  come out exactly as before), so either store can be handed in; `relocate_entries` and
  `read_catalog_header` were split out of `load_catalog` for the database store and the
  migration. `web/steam_web.stored_detail_ids` lists the cached records (disk only).
- **`logic/migration.py`** `build(target)`: the records through the store, the catalogue
  through `catalog_io`, the Steam records and name lookups through `web/` (nothing fetched),
  built with `library_db`, checked, `Built.good` only with nothing refused and nothing
  different. Phase 69 runs it at startup; until then only the net does.
- **The fourth net, `tests/check_migration.py`, in `run_all`**: on a sandbox copy (with the Steam
  caches copied in, read only) -- 66 records, 113 sessions, 5,378 minutes, 323,125 s, 15 save
  folders, 1 lineage row, 1 carried, 34 installs, 47 Steam apps; nothing refused, no
  difference, LibraryStore reopened on the file gives the same records and catalogue; the
  same recovered names (folder 20, steam 5, none 6) and 17 links as the Phase 63 rehearsal.
  **Proven able to fail** with two faults put into the code in memory: a star never written
  (7 records differ) and a field lost on the way back (36) -- both "the migration would stop".
- **`check_layers`** refuses an import of sqlite3 outside `data_access/` (`sql_outside`;
  `imports_in` split out for it); `.gitignore` has `library.db` and `library.db-journal`.
- `tests/phase67_tests.py`, 48 checks: 14 tables, all STRICT, 2 views, version 1, foreign keys on
  (and off on a plain connection); nine constraints refused by probing SQL on a scratch
  database (tests may; the app may not); the projection; **LibraryStore against Overrides on the
  same sequence from the same copy** -- a note, a star given and taken, a session banked, two
  games' save folders, the merge with a new game (time fixed for both), a moved cover found
  again, a carry-over (Snowrunner onto SnowRunner) and its refusal, an export (the same 47
  members) and an import -- the same records in memory and saved after each; two refused
  writes leave the database and memory as they were; the catalogue in its order, the scan time,
  a link kept for a game gone, a game just found with no record until the merge; another thread
  refused; only `logic/migration.py` uses the module; the layer net can fail; the files ignored.

## Phase 66 notes (the database, step 3 of 8: the tests read through the store)

Approved as "lets move on with the next phase". **Only `tests/` changed.**

- **Five helpers at the end of `test_sandbox.py`**, each going through the store
  (`catalog_io.Overrides`, imported only when called, so `import test_sandbox` still loads no
  data module and `start()`'s guard holds -- the suite proves it in a fresh process):
  `records(store=None)` (what was **saved**, read back fresh -- with a store, what *it* saved,
  never its memory); `put_records(records, store=None)` (whole records planted through
  `import_records`, written at once; into a live window's store, which then shows them);
  `separate_store(name, records=None)` (a library of its own in the copy); `records_in(folder)`
  (what a snapshot holds); `real_records()` and `real_stamp()` (the user's real library, read
  only, for a suite's own "left alone" check). When the library moves into the database
  (Phase 69), `test_sandbox.py` is the one file in `tests/` that has to change.
- **43 places in 10 files moved**: suites 22-25's photographs of the real file (mtime and
  parsed records -> `real_stamp`/`real_records`; 25's restore of its subject -> `put_records`);
  26's reads and its own NEW-tag library (`separate_store`, and `store.update` where it wrote a
  live dict); 27's `record()`; 29's clearing of the saves search (`update_many`); 36's reads,
  its planted earlier installs (`put_records` into the window's store) and its snapshot check
  (`records_in(newest.path) == records()` -- the same records, where it compared bytes);
  37's simulated rename, now done by records (`put_records`) and catalogue entries
  (`load_catalog`/`save_catalog`), refusing if a key itself named the project; 64's stores
  (`separate_store`) and every `.games` comparison (`export_records`, `get`). Every moved suite
  has the same count as before.
- **`tests/phase66_tests.py`, 14 checks**: each helper does what it says; and a search of
  all 42 files in `tests/` -- a line naming `overrides.json` beside a read or write, or `.games`
  on anything called a store or overrides -- finds 43 places in 10 files at `before-phase-66`
  and none today outside four named ones: `test_sandbox.py` itself, `check_paths.py` (the guard's
  planted change; Phase 68), `phase65_tests.py` (the old code's JSON byte for byte; Phase 69),
  and `phase66_tests.py` (checking `real_records` against the file).
- **Left on purpose**: the sandboxes' own file copying and byte comparison (`start`/`finish`,
  suites 26 and 37) and the `OVERRIDES_PATH` checks (26, 27, `check_paths`) are Phase 68's --
  the sandbox learns the database there; `tests/playtime_report.py` (a tool reading a given
  file) and suites 64-65's comparisons with JSON-only code are Phase 69's.

## Phase 65 notes (the database, step 2 of 8: export and import through the store)

Approved as "go with phase 65" (and the user rotated the SteamGridDB key the same day: the
new one is in `data/config.json`, which is **not committed** -- the play-data commits ended in
Phase 63 -- so it never reaches git history).

- **`transfer.py` opens none of the launcher's files now.** Records come from the store,
  `Overrides.export_records()` (a deep copy), and go back through it,
  `Overrides.import_records({key: record})`: each replaces this PC's whole record for its game,
  in place, written once; if the write fails every record is put back -- a new one removed, a
  replaced one restored -- and it returns False, which transfer turns into the old "could not
  be saved" report. Settings through `config_io.load_saved()` (the file's own keys, no
  defaults: a bundle carries what this PC saved). `Overrides.save()` and
  `catalog_io._atomic_write` now return the writer's bool (nothing ignored it on purpose).
  **The rules stay in `transfer`**: imported wins, sessions combined by start time, nothing
  deleted, a snapshot first; the merge is worked out against a copy and handed over in one go.
- **Settings hands the window's store down** (`SettingsDialog(..., store=self.overrides)` ->
  `ui_transfer.export_flow/import_flow(store=)` -> `transfer.export_bundle/import_bundle(store=)`),
  so there is one place holding the library -- in the database, one connection. Without one
  (suite 26, any old call) transfer opens `catalog_io.Overrides()` -- the library as saved,
  exactly as it read the file before. The window still reloads after an import, as it did.
- **Two corners that differ, neither real here**: the bundle's records version is
  `OVERRIDES_VERSION` (1), where it was the file's own (1); and an import into a PC with no
  overrides file at all writes version 1 where it took the bundle's (always 1). And `config_io`
  is imported at the top of `transfer` now, so `check_imports` counts 18 imports inside
  functions, not 19.
- `tests/phase65_tests.py`, 21 checks, reads `transfer.py` as at `before-phase-65` out of git
  and runs it beside today's on the sandbox: export with and without the key, from the file and
  from a store -- 46 members, byte for byte, same report; an import of a bundle with a changed
  game, a new one, sessions to combine, settings with a root to union and another PC's window --
  `overrides.json`, `config.json` and the unpacked art byte for byte the old code's, the same
  report (the backup's stamp aside), the window's store equal to the file; a failed write --
  same report, both files untouched, and the store as it was; the wiring from the window to
  transfer, with the file dialogs and boxes stubbed. Each section counts as one failure if it
  cannot run to its end, so the suite runs on the old code too: with the six app files stashed
  back to the tag, 2 pass and 6 fail (the file calls found; the old signatures refuse `store`;
  Settings gets none).

## Phase 64 notes (the database, step 1 of 8: named operations, still on JSON)

Approved as "yes fix the settings ring, then go with phase 64" (the ring fix is its own
commit, before `before-phase-64`). **The data still lives in `overrides.json`**; this step only
moves who touches it, so that the switch (Phase 69) changes the inside of `data_access/` alone.

- **Five operations on the store** (`data_access/catalog_io.py`), each one write at most and
  each handing out the same live record dicts as `get` -- the views read them live:
  `values_of(field)` (every record's value of one field, where it has it), `uncarried()`
  (records whose history was not carried over), `update_many({key: {field: value}})`
  (`update` for several games, one write), `carry(old, new, old_record=, new_record=)` (both
  halves of a carry-over written together; the new record changed **in place**, the old one
  replaced, exactly as before), and the module function `last_scan_time()` (the catalogue's
  time, which `storage.catalog_written_at` now asks for).
- **Where they went**: lineage 105 and ui_window 1335 -> `uncarried()` (each keeps its own
  "not installed" test: lineage compares `_norm`ed keys, the window exact ones, as before);
  ui_window 397-411 -> `values_of` + `update_many`; 1095 -> `values_of("first_seen")`; 415
  (`mark_seen`) needed nothing new -- `get` answers `{}` for a missing key, the same falsy
  answer; lineage 210-286 -> `carry`. **The carry rules stay in `lineage`** (they are the
  app's rules, not storage's): `carry_over` now works on a copy of the new record and hands
  the store both halves at the end. The one difference on purpose: a carry stopped half way
  by an unforeseen error used to leave a half-changed record in memory for the next write to
  keep; now it changes nothing. On success the result is the same, byte for byte.
- `update_many` drops a record left empty, as `update` does; the old loop kept `{}`. No record
  can be emptied by it -- every one holds `first_seen` -- so the file is the same.
- **`tests/phase64_tests.py`, 23 checks, compares old and new code directly**: it reads
  `lineage.py`, `storage.py`'s function and three `MainWindow` methods as they were at
  `before-phase-64` out of git (compiled with `ast`, the module's own names as globals) and runs
  them beside today's on identical copies of the real library: all 646 pairs of a game showing
  and an earlier install carried both ways -- the same records, the same `Carried`, the same
  file bytes, one write each; the three refusals; dropping planted crash-report and telemetry
  folders; the NEW tag; the known keys; the 51 names that tell saves apart; the 19 earlier
  installs; the scan time with and without a catalogue. And an AST search finds no
  `overrides.games` / `overrides.save` outside `data_access/` -- the same search finds exactly
  the ten such places in the code at the tag. Proven both ways: 23/23; with the four app files
  stashed back to the tag, 21 pass (they compare old with old) and the 2 that must fail do --
  the ten places found, and the half-way carry leaving its trace.
- **A file in `web/` starts with a byte-order mark** (`steam_search.py`): `ast.parse` refuses
  U+FEFF, so source is read as `utf-8-sig`. And the backslash trap an eighth time: a
  `"\r\n"` written through a bash heredoc became real line breaks; fixed by a scratch script
  written with the Write tool.

## Phase 63 notes (the database, step 0: the plan, nothing of the app changed)

Asked for as a brief (SQLite through `sqlite3`, `data/library.db`, a normalised schema, no ORM,
the repository behind today's dict facade, play-data commits ending). **The plan, the DDL, the
field map, the migration and the steps are `docs/BAZA_DE_DATE.md`**; ARHITECTURA §10 points to it.

- **Measured, not assumed**: SQLite 3.50.4 in the venv (STRICT tables need 3.37, not the brief's
  3.35); `python -m sqlite3` is the shell, nothing to install. A rehearsal (scratch folder only)
  loaded the real data into the schema in memory: 66 games, 113 sessions, 5,378 minutes, 323,125
  s, 15 save folders, 1 lineage row, 34 installs, 47 Steam apps; 0 foreign-key violations, 0
  values that did not fit; read back through the dict shape, 66/66 records and 34/34 catalog
  entries equal field for field. `data/` checked unchanged.
- **What the data changed in the brief's schema**: `game.source` nullable (21 uninstalled folder
  keys say nowhere which store), `name_origin` and `appid_source` with `chosen`/`recovered`
  (recovered names and links are given back to the program *only* where it wrote them), nullable
  `playtime_seconds`, `install.display_name`, `install.scan_id` instead of `scanned_at`,
  `position` columns (the code compares lists), `steam_app.has_record`, generated
  `started_local`/`local_hour` (all 113 sessions land in the wrong hour through `strftime`, which
  converts to UTC first). `scan.trigger` takes the five real callers plus `migration`; no `cli`,
  because `scanner.py` writes no catalog. `carried_to` stays a column: `earlier_keys` is
  transitive (the new record inherits the old one's), `carried_to` names the direct successor.
- **The code proved one brief assumption wrong**: discovery never writes the catalog -- the scan
  worker emits entries and `_on_scanned` writes on the GUI thread. One writer is already the shape.
- **The steps run in a different order from the brief's**: named operations (64), transfer (65),
  tests through the store (66), the schema beside the JSON with the fourth net (67), backups and
  sandbox and keep-lists (68), *then* the migration and switch (69), the Steam projection with
  `cc=RO` (70, asks first: it changes a URL), closing (71). Anything still reading
  `overrides.json` after the data moves reads a stale file, and a sandbox that does not know the
  database cannot guard it.
- **Byte comparison cannot tell an unchanged database**: a backup after a change undone differs in
  bytes, equal in content. Skip-when-unchanged and the sandbox guard use a sha256 of `iterdump()`.
  `Connection.backup()` hangs if the same connection holds a write transaction: commit first.
- **The baseline was red for reasons outside the code, and only tests changed**: the scanner net
  had not seen BloodBorne (re-saved; the old run kept beside it); suite 33's "first timed game"
  became BloodBorne, whose page does not scroll (now the first timed game whose page does); suite
  56 expected art at the Continue card's right end and CULTIC's is near black there (now compared
  with the card's own art); suite 58's ring above a Settings size box was cut off -- on a 1032 px
  screen the box sat 2 px from the scroll view's top, wholly in view, and Qt's
  `ensureWidgetVisible` keeps its margin only for a widget *not* already in view. Measured: the
  pixel above was the ground; with the margin kept anyway the box sits 41 px in and the ring
  shows. The suite now centres the box first; the flaw itself was put on the user's list and,
  **on his go, fixed in its own commit before Phase 64**: `ui_settings._follow_focus` calls
  `ensureVisible` on the control's centre with half its size plus the margin, so the margin
  holds for a control already in view. Suite 58 gained the case on purpose (dialog held short,
  the box placed 2 px from the top, then focused): 52/52, and on the old line 2 px in, the
  ground where the ring should be -- 51/52. Suites 35, 49, 52 still green. First run 1226 of 1230 (those,
  and suite 49's gate with another window in front, 20/20 alone); after: **ALL GREEN 1230/1230**.
- **Found, not done** (BAZA_DE_DATE §16-17): the SteamGridDB key is in 15 versions of
  `config.json` in git history, 7 of them on the private GitHub remote -- the proposal is to
  rotate the key, stop tracking both files at the switch, and show the committee a fresh
  repository built from the final tree, never rewriting this one; an import replaces a game's
  whole record (sessions excepted), so a field only this machine has is lost for a game both
  know; `uninstall.USER_DATA` is unused; the installer deletes every top-level file not on its
  keep-list, so `library.db` must join it before an installed copy uses the database.

## Phase 62 notes (Inter one step heavier; the rail's cut-off "g"; Storage opening on its drive)

Reported from use: "the font ain't really doing it for me ... it looks too thin", and the
end of the "g" in the rail's "Play something" was missing. Two fonts the user supplied were
tried first, and neither went in:

- **Ubuntu-Title** (2005, Canonical / Andrew Fitzsimon, LGPL; one weight) was put in and
  rendered across every page, and was rejected by the user on sight -- with reason: it is
  the old Ubuntu *logo* face. 24 of its 26 capitals are drawn as lowercase, so every name
  read "the witcher 3"; its comma is drawn under the letter before it and the following
  space vanishes ("off, the" -> "of,fthe"); "&", "%", "~", "·", dashes, arrows and Romanian
  letters are not in it at all (Windows filled them from Tahoma). Read off the file, not
  assumed: its name table, `QRawFont.supportsCharacter` per character, the glyph runs of
  a laid-out line. It was taken out again; the file stays in the scratch folder only.
- **San Francisco** (SF UI Display Bold, which the user had installed in Windows) was **not**
  built in: the licence in its own name table allows it "solely for purposes of design and
  development of applications for the Apple Watch", to registered Apple developers. This
  launcher is a Windows program, the thesis, and an installer. Said plainly to the user,
  with the alternative below; the font was only drawn beside Inter for him to compare.

**What went in, approved from an in-memory preview ("yes put it in")**: Inter, one step
heavier, with its Display cut for titles -- the nearest free match for SF UI Display.
- `BODY_WEIGHT` 500 (new; the `QWidget` rule in `ui_theme`), `HEADING_WEIGHT` 600 (was
  500), `LABEL_WEIGHT` 700 (was 600), `TILE_NAME_WEIGHT` "DemiBold" (was "Medium").
  **Painted text that names no weight inherits the window's**: `QFont(family)` leaves the
  weight unresolved (mask 0x20000, family only) and `QPainter.setFont` resolves it against
  the widget's font, which the stylesheet makes Medium -- measured. The three places that
  asked for the normal weight by name now ask for `BODY_WEIGHT`: the Continue card's
  `_font` default, the tile's line under the name, the segmented Playing/Finished/Dropped.
- `FONT_DISPLAY_FAMILIES` starts with "Inter Display". Every use of the display family is
  at `HEADING_WEIGHT`, so only its SemiBold is shipped. Two files added to
  `presentation/fonts`, byte for byte from the same Inter-4.1.zip as Phase 54
  (sha256 `9883fdd4...`): `Inter-Bold.ttf` (`28831609...`) and `InterDisplay-SemiBold.ttf`
  (`0310d7a3...`); Inter's OFL, already there, covers both. Every weight used draws a real
  face -- none is faked by Qt.
- **The cut-off "g"**: measured, the button was 124 px wide and needed 134 -- the rail's 232
  px holds its foot only just (the mockup's own render wraps the words). The rail is now
  `max(RAIL_WIDTH, its layout's minimum width)`, re-measured in `apply_scale`; with the
  heavier words it is 244 at 100% and 303 at the user's 125% (232 and 290 by the design),
  "Play something" 136 and 167 wide, whole. Older checks that took "232" as the rail's
  width now take its width.
- **Storage opened scrolled past its drive's name** (seen at the user's 125% in a 1280 x 820
  render; his maximised 2560-wide window was fine): the list was 141 px, less than the
  drive's card top (133) and a row (53). Three fixes in `ui_storage`: `select_first`
  chooses the first game **with Qt's auto-scroll off for that one call** and goes to the
  top -- Qt's `currentChanged` on a list not yet on screen sets
  `shouldScrollToCurrentOnShow` and scrolls to the row as the page appears, after any scroll
  made here (traced: inside `stack.setCurrentIndex`); `set_storage` always ends with
  `select_first`, because every visit rebuilds the list, and a list that still had the
  focus got a row made current by Qt as it refilled and kept its old scroll; and **the map
  gives way to the list** (`_fit_map`, on resize, after `set_storage` and `apply_metrics`):
  the list keeps its first drive's card top and `STORAGE_LIST_MIN_ROWS` (2) rows, the map
  takes up to its full height of the rest, and below `STORAGE_TREEMAP_MIN_HEIGHT` (120) it
  steps aside. It depends only on what the two have together, so running it again changes
  nothing. At 125% the window will not go below 784 px, so in practice the map shrinks.
- **`test_sandbox` leaves the interface sizes out** (`NEVER_COPIED` gains `ui_scale` and
  `tv_scale`): the user set 125%, and every suite measures the design at 100% -- as with the
  window's place, a suite that wants another size asks for it.
- `tests/phase62_tests.py`, 27 checks: the weights and faces (real Medium, SemiBold, Bold,
  Inter Display SemiBold), the two files by hash, the live window's text and title, the
  rail's foot whole (and widening for longer words, and back), Storage at 125% in 1280 x 820
  (top, card and two rows in view, the map shrunk), in a window the user's size after being
  scrolled away (top, map full), on a page held too short (the map steps aside, the list
  still whole, the map back with the height), TV still without the map, data unchanged.
  Proven both ways: 27/27; with `presentation/` as at `before-phase-62` (stashed and put
  back, identical by hash), 20 failures -- the button 124 against 134, the list scrolled to
  46 -- and 7 passes for what was already so.
- **Older checks updated to the new values, none loosened**: suite 54 (the display face is
  Inter Display; Medium, SemiBold and Bold are real faces; the weights 500/600/700 and
  DemiBold; every stylesheet asks for 600, and 500 only in the window's rule and the
  marks; a game's title Inter Display SemiBold), 55 (tile names DemiBold), 60 (the rail is
  232 or what its rows need; the pages 32 px in from its real width), and 31: the game
  page's marks left its "bold when on" list -- a lit mark has kept its weight since Phase
  57, and at the new weights the hypothetical bold no longer fit by one pixel -- and gained
  the check that matters for them, that each holds its words at its own weight (as the
  chips left that list in Phase 55).
- **The full run was 1212 of 1228**, before those updates: the 11 old-value checks above;
  3 pad-driven menu checks in suites 27 and 52 (passed alone, 44/44 and 17/17); and suite
  28's two foreground checks, with Firefox in front -- failing the same way with
  `presentation/` as at `before-phase-62`. After the updates every changed suite passed
  alone (31 42/42, 54 21/21, 55 37/37, 60 46/46). Every safety net clean.
- **The backslash trap a seventh time**: a `\n` in a scratch script through a bash heredoc
  broke the suite-54 edit before anything was written; done with the Edit tool instead.

## Phase 61 notes (the old playtime totals, repaired)

The decision Phase 53 left open. Asked in plain words ("what do you mean how to repair the
playtime - ive got no ide"), shown the report's numbers and two choices, the user chose
"lets correct them". **The rule: wherever a game's stored total is below the sum of its
sessions, it becomes that sum; nothing is ever lowered, nothing else is touched.**

- **Why that rule**: each session's length was always measured from its start, so the session
  list is the record that was right all along; the total had lost ~16% to the drift. Raising
  only, never lowering, means a game whose total holds time from before session history
  (14 August) or a few seconds the minute-rounding drops keeps it.
- **Done with the launcher closed** (checked: no python process), because the running app
  holds the file in memory and its next write would put the old totals back.
- **Done through the app's own code**: `backups.snapshot("before-playtime-repair")` first
  (`data/backups/2026-10-08_21-49-27`, checked to hold the exact file before anything was
  written -- Settings restores it), then `catalog_io.Overrides` and its own atomic writer.
  Before writing, the script proved that writer reproduces the file byte for byte (it does:
  `_atomic_write` adds the final line break the first check forgot, which is why that
  check first said no and nothing was written); after, it read the file back and compared
  every field of all 65 records: 26 totals raised, nothing else different. `git diff`: 26
  lines. The script is a one-off and stayed in the scratch folder; the rule is above.
- **The result** (`tests/playtime_report.py`): 75h 40m stored against 88h 24m of sessions
  before; 88h 29m after, every game at 100% of its sessions or, for the few that were
  already above (minute rounding; time before 14 August), left as it was. Largest: Spider-Man 2
  16h 29m -> 18h 37m, STALKER 2 12h 25m -> 14h 49m, Silent Hill Townfall 10h 35m -> 12h 38m.
  Time played before 14 August, when no session was kept, cannot be recovered; three games
  have any (Spider-Man 2, PRAGMATA, LEGO Batman).
- **Taking the snapshot ran the backup rotation, and 8 old snapshot folders it removes were
  left behind empty**: `shutil.rmtree` emptied each and then got "Access is denied" removing
  the folder -- *not* the shell, as first written here: the folders carry Windows' ReadOnly
  mark, and the launcher's own rotation failed the same way at every start (found and fixed
  after Phase 69; see its notes). All 8 were outside the rotation's keep set,
  so the launcher would have removed them at its next start anyway; an empty one is refused
  by restore ("contains none of the files"), and the next start -- which snapshots, since the
  file changed -- prunes them.
- **Undo**: Settings -> restore `2026-10-08_21-49-27` while it is still among the last five,
  or `before-phase-61` in git for good.

## Phase 60 notes (the side rail, the design's `#1b`)

Approved as "yes - the sidebar is definetly something that i want" -- the first of the two
optional screens. Spotlight for TV (`#1c`) was not asked for and is not built.

- **At the desk the rail takes the place of the top bar and the chips** (`ui_rail.py`, new):
  232 px, the surface at 60% at its top fading to nothing, a hairline right edge; the brand;
  Library, Stats and Storage (36 high, the current one accent 900 with accent-200 words and
  a 2 px accent mark); the five filters with their counts; "Found in" -- where the games
  came from, with theirs, most first, the scanner's folders called "Folders"; and at its
  foot Play something, rescan and settings. Every number is the mockup's, in `ui_rules`
  under "Phase 60".
- **A choice, in Settings** ("Side rail" under Look and feel, on by default):
  `library_layout` in config.json, `rail` or `top`, saved with the other settings. A config
  without the key -- the user's, on the day -- gets the rail. **TV mode always keeps the
  top bar**: the design pairs the rail with the desk, and every pad path was built around
  the bar; `MainWindow._apply_layout` decides, on start, after Settings and on every TV
  switch.
- **The rail owns no state.** The chips stay the one place the filter is kept, remembered
  and read; in the rail layout they are hidden, the rail mirrors them, and a filter picked
  there checks the chip -- so everything that reads the filter is unchanged. Its buttons emit
  the top bar's signals; the rescan button's on/off follows the real one through an event
  filter. Nothing in the rail takes the keyboard focus, so a click leaves the arrows on the
  grid. **A filter picked on Stats or Storage goes to the library** (filtering a page you
  are not looking at would do nothing visible).
- **The library's own header**: its name 26 px, what it holds ("N games · K stores and
  folders"), and the search box -- the same widget, moved out of the top bar and given back
  by `TopBar.restore_search` -- 280 x 34. "ALL GAMES" over the grid, with Demos & tools,
  Hidden and the sort (now quiet words, `SortBox[variant="plain"]`) on its line.
- **Jump back in** (`ui_jump.py`, new) replaces the Continue card beside the rail: the
  three games played last by the card's own rule (`ui_continue.eligible`, split out of
  `pick`), 178 high, 14 apart, the first 1.35 times as wide and edged in accent 600, a round
  outlined Play that becomes Stop while its game runs. A click elsewhere on a card opens
  the page, a right click its menu. **It speaks the card's protocol** (present, collapsed,
  fold, `focus_button`, `focus_step`, `activate_focused`, `view`, ...), so the library page
  holds whichever of the two the layout uses as `card` and its pad and folding code did
  not change: up from the top row to the first card's Play, left/right between cards, A
  plays, X the menu, down back to the tile. **One stop per card**: the card's Details
  button has no counterpart here -- the page opens from the grid, or a click.
- **Stats and Storage carry their name** (26 px) beside the rail, start 24 px down and
  32 in, and their column is placed in the design's frame less the rail
  (`PageColumn.set_rail`). The game's own page has no rail, as it had no top bar.
- **Six icons more**, from the Phosphor CSS like the rest (squares-four, chart-bar,
  hard-drives, play-circle, check-circle, x-circle); Windows' fonts lend stand-ins.
- **Not built, on purpose**: the mockup's grid/list switch (there is no list view to switch
  to) and its "Review them" prompt -- both would be new behaviour, not appearance.
- **Every suite before this one runs in the top layout**: `test_sandbox.start` sets
  `library_layout` to `top` before a suite's own changes, so they test what they were
  written for; suite 60 asks for the rail. Suite 26 builds its own sandbox from the real
  config and so runs with the rail, and passes.
- `tests/phase60_tests.py`, 46 checks on the live window: the rail's measures and colours,
  the header, Jump back in's games, sizes and pad path, the card's click, the places, a
  filter from Stats, search, rescan, TV, the Settings switch, the default. Proven both ways:
  46/46; with `presentation/` as at `before-phase-60` (stashed and put back, identical),
  7 failures and 1 pass (the real files untouched), stopping at "there is a rail" -- it says
  the rest were not reached rather than counting them as failures (its first version did).
- **Suite 35 asked for the old set of Settings' answers** and now asks for it with
  `library_layout`, the rail's switch among the switches, and its value as opened ("top").
- **The full run was 1197 of 1201**: that check in suite 35 (78/78 once updated, alone),
  and suite 28's three foreground checks -- the Apollo console still in front in its
  "Select" mode, failing the same way with `presentation/` as at `before-phase-60`. Suites
  23, 24, 35, 58 and 60 were run again after the last edit (two long lines in Stats and
  Storage split): all green. Every safety net clean.

## Phase 59 notes (the Nocturne restyle, step 6 of 6: Phosphor icons)

Approved as "yep - lets do it", and the download separately, with the files, source and
sizes named first. **The six steps of the restyle are done**; Spotlight for TV (`#1c`) and
the side rail (`#1b`) are optional and wait for an explicit go.

- **The files**: `@phosphor-icons/web` 2.1.2 (MIT) from cdn.jsdelivr.net, into an empty
  scratch folder: `Phosphor.ttf` (488,636 bytes), `Phosphor-Fill.ttf` (449,252), both
  `style.css` lists and the `LICENSE` -- each checked against the size and sha256 the CDN
  publishes. Only the two fonts and the licence (`Phosphor-LICENSE.txt`) went into
  `presentation/fonts`; `bundled_families()` registers every `.ttf` there, so they load
  with Inter and register as "Phosphor" and "Phosphor-Fill".
- **Every code point read from the package's own CSS, never guessed** (the CLAUDE.md rule
  about formats): a script pulled `content: "\eXXX"` for each `.ph.ph-<name>` and
  `.ph-fill.ph-<name>`. `ui_icons.PHOSPHOR` holds, per icon, its style, Phosphor's own
  name and that code point, so anyone can check one against the list. The design's names:
  magnifying-glass, gear-six, arrows-clockwise, shuffle, caret-left/right, arrow-left,
  folder-open, dots-three, floppy-disk, clock, calendar-blank, hard-drive, the filled
  play, stop and star, game-controller -- **filled for the top bar's brand, outlined
  (`"controller"`, new) on the controller pill and the library figure**, as the mockup
  draws them -- clock-counter-clockwise for "all time", and a **broom on Storage's reclaim
  strip** (`"broom"`, new), the design's. A contact sheet of all 26 was rendered and looked
  at before use.
- **Windows' icon fonts stay behind it** (`ICON_FONT_FAMILIES` = Phosphor, Segoe Fluent,
  MDL2; `ICON_FILL_FAMILY`): `ui_icons.SEGOE` keeps the old code points, now written as
  numbers rather than invisible characters, and `glyph_for(name)` picks the family and the
  character. The two names Windows has no glyph for borrow one (the controller; the clock
  with its arrow for the broom). Proven in a second process with only Inter's files.
- "Next game" sat tight against its arrow: right to left, the space has to follow the
  words ("Next game "), not lead them.
- `tests/phase59_tests.py`, 19 checks: the three files byte for byte the published ones
  (the licence by its text: **git hands a text file back with Windows line endings** --
  stashing and popping it for the proof did exactly that, and the file was copied back
  from the download), both families, every code point present in its font and inking,
  each the design's glyph in the design's style, the filled set for the solid ones, the
  fallback, and the icons on the live window. Proven both ways: 19/19; with `presentation/`
  as at `before-phase-59` and the three new files set aside, 17 failures (the two that pass
  hold for both sets: a filled star, the real files untouched). Two checks passed on the
  old code at first because the table they looped over was empty there; they now require
  it. Older checks updated: suite 31 (the icon font is Phosphor; "draws something" counts
  every pixel a glyph touches -- Phosphor's three dots are 16 solid pixels at 32 px, 48
  touched, where a missing glyph touches none) and 54 (the two icon families are bundled
  beside Inter's).
- **The installed program would still have neither Inter nor Phosphor**:
  `packaging/app.spec` does not bundle `presentation/fonts` -- one line, outside
  `presentation/`, on the user's go (ARHITECTURA §12, item 18). It would fall back to
  Segoe and Windows' icons, which is what the fallback is for.
- **The full run was 1152 of 1155**: suite 28's three foreground checks again, the Apollo
  console still in front in its "Select" mode, failing the same way with `presentation/` as
  at `before-phase-59`. Every safety net clean.

## Phase 58 notes (the Nocturne restyle, step 5 of 6: Stats, Storage, the menus, buttons and Settings)

Approved as "lets go. once again it looks great". Every number read from the mockup's
`#1e` and `#1f` and the token sheet's `.card`, `.btn`, `.seg` and `.tag`; the design keeps
both pages' layout, so ours stays where the design has nothing (Storage's summary line,
sort box, map of tiles and footnote; Stats' "Where they came from").

- **One column for both pages** (`ui_pageshell.PageColumn`, replacing `centred`): 64 px in,
  18 px under the top bar, at most 1022 wide (the design's 1150 less its 64 either side),
  and every pixel a window has beyond the design's 1280 shared equally between the sides --
  so at 1280 it is exactly where the design puts it (the old centring put it 69 px in), and
  a maximised window or the TV is not lopsided. The 1 / 100 / 1 stretches had the Phase 57
  flaw. `STATS_CONTENT_MAX_WIDTH`/`STORAGE_CONTENT_MAX_WIDTH` are the 1022.
- **Stats**: the four figures 14 apart, 18 x 20 inside, the value 32 px 0.02 em tighter on a
  1.1 line (its gaps measured from the line, not the label's taller box), the caption
  12.5 px in neutral 400. The chart: bars 12 apart, the tallest 120 of 170 px, each from
  the accent at its top to accent 700 at its foot with only its top corners round, **every
  bar's value written 8 px over it** (only the peak's was), the months 11 px under a 1 px
  hairline 8 px below the bars. An unrecorded month is a 6 px stub in the hairline colour
  (no more full-height slabs -- ARHITECTURA §12, item 19, closed); a recorded quiet month a
  3 px stub in accent 700, so the two still differ (Phase 23). The span ("Nov 2025 to Oct
  2026") sits on the title's line where the design has its meta; the sentence about the
  dimmed months moved into the caveat card with the design's two-swatch legend. The two
  lists side by side and equal, 14 apart; **Most played shows each game's cover, 18 x 27
  with 3 px corners** -- the rank numbers and Phase 35's share bars are gone, as in the
  design. A tally knows a game only by name and time, so the page finds its view by those
  (the window hands the page `covers` and `views`). The caveats are escaped rich text on
  the design's 1.6 line. Card titles are 15 px everywhere now (`DETAIL_CARD_TITLE_PX`), and
  `Card` takes (sides, top, bottom) padding for the chart's 20 / 16.
- **Storage**: **each drive is a card**, painted by the list's delegate a slice per item
  (`_card_rect` finds the card's first and last item through the view), so one list still
  holds both shapes and the pad still walks only the games (Phase 24). Inside: the drive
  18 px Medium with its capacity on the same baseline; the capacity bar 14 px, 7 px
  corners, three parts 2 px apart (games accent 600 -> accent, everything else neutral 700,
  free neutral 900); a legend of 9 px swatches. Rows 38 high, 5 apart, 22 in from the card's
  sides, the text colour at 3% as glass, the bar from the row's left edge the accent at 16%
  (accent 400 at 22% past the staleness threshold, which also carries the design's outlined
  tag, "not played in 6 months"), then last played (110 px, neutral 400) and the size
  (90 px) -- the columns swapped to the design's order. The pad's ring stays inside the row:
  a ring drawn into the 5 px gap would be painted over by the next item. The reclaim strip
  is the design's -- 14 px corners, accent 900 edged in 800, a 22 px icon in accent 300, a
  14 px line in accent 100 over a 12.5 px one in 300 -- with the words split to match ("4
  games not played in over 6 months take 212 GB" / the names); with nothing to reclaim it
  is the plain card saying why. **Not built**: the design's "Review them" button (it would
  need an action that does not exist) and its sort as a segmented Size / Last played / Name
  (ours sorts two other ways, page-wide; the pill stays). The map of tiles keeps its
  per-game colours; it is not in the design.
- **Menus, tooltips, the message card**: the surface with a hairline edge; a menu's chosen
  entry accent 900 with accent-100 words, not a flood of the accent; combo lists the same.
- **Buttons with no look of their own** (dialogs, Settings, questions) are the design's
  quiet one: an outline in the divider, transparent, the text colour at 7% / 14% under the
  mouse / pressed, 6 x 10 inside, Medium in a dialog; **a dialog's default button is the
  outlined accent one** -- OK in Settings, Cancel in the uninstall question. A question's
  focused button is edged in the accent (it had no visible focus at all before). The
  scrollbars' white became the text colour (the Phase 54 sweep had missed them).
- **Settings**: its groups 8 px corners; **one `FocusRing` over the dialog** rings buttons,
  size boxes and switches 2 px outside, TV mode's thicker (`focus_ring_width`), clipped to
  the scroll area. `FocusRing` takes a `scale` for a dialog, `refresh()` and `detach()`
  (called from `done`). A switch is ringed only once a keyboard or pad move is marked, as
  before -- but the dialog gives its first switch the focus while opening, before that mark,
  so **the first version never ringed it** (suite 35 caught it): the switch now tells the
  ring when it repaints (`FocusRing.follow`). `ToggleSwitch` paints no ring of its own now.
- `tests/phase58_tests.py`, 51 checks on the live window, proven both ways: 51/51; with
  `presentation/` as at `before-phase-58` (stashed and put back, identical by hash), 45
  failures and 1 pass (the real files untouched). **Two checks first passed on the old code
  for the wrong reason** and were tightened: the hairline under the chart sat where the
  old chart's full-height wash was (now: 1 px of it, the card either side), and the message
  card's edge tolerance admitted the old divider. Older checks updated to the new values:
  suite 23 (a bar's pixel is one on the accent -> accent-700 run), 35 (covers in place of
  share bars, the storage ring inside the card's padding, the switch's ring outside it),
  54 (the quiet-month stub is accent 700 now), 57 (Stats' titles 15 px, its share-bar
  height gone).
- **The full run was 1133 of 1136**: suite 28's three foreground checks, with the Apollo
  (Sunshine) console still in front in its "Select" mode, as in Phase 57 -- and failing the
  same way with `presentation/` as at `before-phase-58`. Every safety net clean (0 upward
  imports, scanner 0 differences, the original folder untouched).

## Phase 57 notes (the Nocturne restyle, step 4 of 6: a game's own page)

Approved as "lets go - looks great". Rendered with Silent Hill 2, the mockup's own game,
beside the mockup's `#1d` cut from a headless Edge render; every number below was then
measured on the live window by `tests/phase57_tests.py`.

- **The art**: the design's 430 px plus the 5 px on to the first card, one box of 435
  (`DETAIL_HERO_HEIGHT`) -- its foot has faded to nothing by then. **On a taller window it
  keeps the design's share of the height** (`DETAIL_HERO_FRACTION` 0.54, the 430 of the
  mockup's 800 px frame), whichever is more: a fixed 435 was a thin strip on a maximised
  window and on the TV (30% of a 1440 screen, against 60% before this step). At 1280x820 that
  is 443, so the page sits 8 px lower than the mockup. Fades from 35% down; the overall shade
  is gone (`DETAIL_HERO_SHADE_ALPHA` removed); the side scrim is the ground 90% -> 25% at
  half -> none; framed a quarter of the way down (`DETAIL_HERO_ANCHOR`; `covers.banner`
  gained the `anchor_y` that `image` got in Phase 56).
- **Geometry**: cover 170, gap 30, title 46 px; the Play row's foot 4 px above the cover's
  (`DETAIL_INFO_FOOT`); the first card 30 px under the cover (`DETAIL_HERO_BOTTOM`, now the
  banner's foot, so the body has no top margin). The design's line-height 1 on the title is
  matched by measuring how far the label's box overhangs its letters (`_space_info`).
- **The cover's shadow is the design's large one**: a 1 px edge in neutral 500 *outside* it
  (`COLOR_COVER_EDGE`; the white inner edge is gone) and a 40 px soft shadow dropped 16.
  Its widget has room left and above; on the right only the 30 px gap and at the foot only
  the 30 px to the card -- **the first render put the title 70 px from the cover** because
  the shadow's room added to the gap. The flying cover (Phase 34) lands with the same edge
  and drop (`fly(..., drop)`).
- **Found against the design, older than this phase: the cards sat 12 px right of the
  cover** at 1280. The body row's stretches were 1 / 100 / 1, and a box layout hands
  stretch-weighted space to every item, so each side got a hundredth of the window. They
  are 0 / 1 / 0 now: the cards take all the width up to their cap, the sides share the rest.
- **The Play row**: Play 170x48, 16 px, over the ground at 55% (`COLOR_ON_ART_FAINT`, also
  the pills'); round buttons 44, transparent with a divider edge, icons 17 (19 for "..."),
  the starred one a filled accent-300 star with no coloured edge; 10 apart, 18 before the
  switch. **The marks are one segmented control**: a divider round it and between the
  choices (`SegmentLine`), 40 high, 13 px at the normal weight, each as wide as its words
  -- `_even_segments` is gone -- the chosen one the accent's words, ringed inside in the
  accent, never filled; the two ends follow the switch's corners.
- **The pills**: 30 high, 12.5 px (a `pt` size: px cannot be fractional), 8 apart, icons
  all neutral 400, words neutral 200, and only "Saves copied ..." in accent 200 -- a `tone`
  property, so the words change colour, not the icon. One space before the words: Qt leaves
  4 px after an icon.
- **The floating buttons**: 36 high, 18 down and 24 in, radius 8 (no longer pills), Medium
  14 px, over the ground at 65%, Previous 8 px before Next.
- **The pad's ring is drawn outside every button on the page** (`ui_cards.FocusRing`): one
  widget laid over the page, moved to whichever ringed button has the focus, following it
  through every move of the button or anything it sits in (a scroll, a card appearing),
  clipped to the scroll area, TV mode's width from the window (`detail.focus_ring_width`).
  The stylesheet `:focus` borders are gone, except on the marks, which the design rings
  inside. **First render: no ring at all** -- it mapped the button through itself, which Qt
  allows only for a parent; it goes through the page now.
- **Cards at the design's size, on the game page only** (`GAME_CARD_*`, a `Card(padding=,
  title_gap=)`): 18 x 20 inside, 18 apart, 15 px titles, 13.5 px words. Stats' cards share
  `Card` and the `#CardTitle` rule, so the page's rules are scoped to `QWidget#DetailPage`
  and Stats keeps 19 px titles until its step; its share bars got their own
  `STATS_SHARE_BAR_HEIGHT` (10) when the sessions' went to 8.
- **Line height needs rich text.** A QLabel ignores a stylesheet's `line-height` (the old
  `#Description` rule never did anything). About and the update snippets are set as escaped
  rich text with the design's 1.6 as a pixel line height (`ui_detail.spaced`), so nothing
  in them is ever read as markup. **The note stays plain text** -- phase 27 holds that it is
  never markup -- so it keeps its font's own spacing; it is usually one line. Its mark is
  2 px of accent 700, its words 12 px in (`setIndent(0)`: with a border, Qt indents a
  label's words by half an "x").
- **Sessions**: 32 px rows, the day 86 px and the length 62 px (wider if the words need
  it), 14 apart, 12.5 px, the day neutral 400 and the length neutral 200, an 8 px bar on a
  track the room's width (`COLOR_SESSION_TRACK`), never under 3% of it. **Days are written
  as the design writes them** -- Today, Yesterday, "Mon 5 Oct", "5 Oct 2025" for another
  year (`ui_detail.session_day`); the time of day is no longer shown, so two sessions on one
  day read alike. Formatted in presentation; `shared/humanize` is untouched.
- **Not taken from the mockup, deliberately**: the genre tags under About (not approved,
  Phase 12); "41 h 12 m" spacing in times (that is `humanize`, outside presentation).
- `tests/phase57_tests.py`, 59 checks, proven both ways: 59/59; with `presentation/` as at
  `before-phase-57` (stashed and put back, identical by hash), 50 failures. Suite 33's
  "Play row level with the cover" and "the three marks one width" now ask the design's
  values (4 px above; as wide as their words, lighting one changes no width); suite 56's
  "the pad still rings it" looks at the ring's pixels instead of a stylesheet string.
- **Suite 54 asked two old values**, and now asks the new ones: the title's tightening for a
  48 px title (-1.20 px; the design's 46 px carries -1.15, computed from `DETAIL_TITLE_PX`),
  and 500 as the only weight -- the marks are at the normal weight, which is lighter, so the
  check still says "nothing heavier" and names the one stylesheet allowed it.
- **The full run was 1082 of 1085**: suite 28's three foreground checks failed, and failed
  the same way alone and with `presentation/` put back as it was at `before-phase-57` (stashed,
  identical by hash after). The window in front was the console of Apollo (Sunshine, the
  streaming host), in QuickEdit "Select" mode; the test's stand-in game could not take the
  screen from it. Nothing in this phase touches focus (ARHITECTURA §12, 13).

## Phase 56 notes (the Nocturne restyle, step 3 of 6: the Continue playing card)

Approved as "lets go to the next step" (the user was away from home, so step 2 had not
been seen live yet -- worth asking after both together).

- **The card, from the mockup's markup**: 250 high (280), 8 px under the top bar
  (`LIBRARY_TOP_GAP`, 4 before), corners 14, **no shadow** -- a 1 px hairline just outside
  its edge, the design's `--shadow-sm` -- so `CONTINUE_SHADOW` and its alpha are gone and the
  card reserves only the 18 px gap above the chips. The scrim is the ground, 70% of it by
  42% of the way across, gone by 85%. The art is cropped 30% of the way down
  (`CONTINUE_ART_ANCHOR`; `ui_covers._crop_to_fill`/`image` gained an `anchor_y`, 0.5 for
  everything else).
- **The words stand on its foot** (the design's flex column, justify-end): stacked upwards
  from the buttons -- 12 px plus the 6 px gap above them -- each centred in a line box of its
  size times the design's line height (`TEXT_LINE_HEIGHT` 1.55; the title's 1.1), 6 px
  apart: the note 13 px italic in neutral 400 (`COLOR_TEXT_QUIET`, the mockup's, not the
  brief's muted), the line under the title 14 px, the title 40 px Medium -0.02 em, the
  eyebrow 10 px spaced 0.18 em at the normal weight. **The brief said 12 px for the eyebrow;
  the mockup's `.card-kicker` is 10 px, and its render measures 10** (7 px capitals, 124 px
  wide -- 10 px Inter is 126, 12 px is 149). Never wider than the design's 620 px less padding.
- **No green anywhere.** `COLOR_PLAY*` are gone. Play is outlined in the accent, words and
  icon in it, over the ground at 60% (`COLOR_ON_ART_PRIMARY`) so it reads on any art;
  Details is the quiet button over the ground at 50%, its info icon gone as in the mockup;
  both 42 high, 15 px, radius 8, **as wide as their words** (24 / 20 px either side) and
  re-measured whenever their style changes, since the stylesheet arrives after the card.
  Hover and pressed are the button states *over* that ground: `ui_theme.layered` composites
  two stylesheet colours into one rgba, which a stylesheet cannot stack. **Stop** is Play in
  red; "red fill only on hover" could not be literal -- an icon does not change colour on
  hover, and a red stop glyph vanishes on a red fill -- so it takes its red at 22% (35%
  pressed), the accent's 12/22 family. The game page shares `HeroPlay`/`HeroStop`, so its
  Play is outlined now too (its size and shape are step 4's), its icon in the accent, and the
  "Saves copied" pill, which borrowed the green, is accent 200 -- step 4's colour for it.
- **The design's focus ring is drawn outside the button**: 2 px of the accent, 2 px out
  (`FOCUS_RING_GAP`), TV mode's width from the tiles' (`ContinueCard.ring_width`) -- painted
  by the card, which owns the room around its buttons and repaints on their focus events; a
  stylesheet can only thicken a button's own edge. The game page's Play row and its
  "Played before?" buttons keep their stylesheet ring until step 4: the `:focus` rule moved
  into `ui_detail`, scoped to `[variant="large"]` and `QFrame#Card QPushButton#HeroGhost`,
  so the card's buttons are not ringed twice. `ui_continue.stylesheet` lost its ring
  argument.
- `tests/phase56_tests.py`, 32 checks, proven both ways: 32/32; with the seven files as at
  `before-phase-56`, 23 failures. **A check that read its own measure from the code passed
  on the old code**: the ring's distance came from `FOCUS_RING_GAP`, which the old code
  lacks, so it probed the old button's own (inside) border -- found by probing the pixels
  either side, and the check now uses the design's numbers (a 2 px ring 2 px out: its middle
  3 px from the edge). Suite 32 updated: the card's height has no shadow room, and its TV
  ring is `card.ring_width()`, no longer a stylesheet string.
- **The restore tag was set late again**, on the Phase 55 commit -- the code before this
  phase, the data unchanged -- so it restores the same thing.
- **The full run was 1020 of 1026**: suite 28's six foreground checks failed while the
  Claude desktop app held the foreground (read off the window in front: `Chrome_WidgetWin_1`,
  "Claude" -- the user following from another device), and passed 19/19 alone. Nothing in
  this phase touches focus; it is suite 28 needing the machine to itself (ARHITECTURA §12, 13).

## Phase 55 notes (the Nocturne restyle, step 2 of 6: the library)

Approved as "yes lets continue looks great so far!". Every number read from the mockup's
markup (`#1a`, and `.btn-*` in the token sheet), not estimated from a picture.

- **The top bar** (`ui_topbar.py`, rewritten with the same names): 28 px from the window's
  sides, 22 between groups, the brand glyph 24 px with 8 more after it, the tabs 15 px and 24
  apart, **running the bar's full height so the 2 px underline sits at its foot**. The search
  box is a 320 x 36 rectangle (radius 8, not a pill) on the surface at 70%, its placeholder
  muted through the palette, and "Ctrl F" written faintly (neutral 600, `COLOR_TEXT_FAINT`
  -- the mockup's value; the brief said "disabled") in a mouse-transparent label at its right
  end, which gives way to the clear button once there is text (`setTextMargins` keeps typed
  words clear of it). Three 36 px squares, 6 apart, quiet: transparent with the divider edge,
  the text colour at 7% under the mouse and 14% pressed.
- **Button states** are four constants used from here on: `COLOR_PRIMARY_HOVER/PRESSED`
  (the accent at 12% / 22%) and `COLOR_SECONDARY_HOVER/PRESSED` (the text at 7% / 14%).
- **Chips are outlines**: 30 high, 13 px in, 12.5 px words in soft text, the chosen one an
  accent outline with accent-200 words **and no change of weight** -- so they no longer
  reserve room for bold, and phase 31's bold-room checks now cover the tabs alone (the chips
  must fit their words in their own fonts). The number is 11.5 px and muted, which a button
  cannot paint, so `ui_library.Chip` draws the box through `QStylePainter` with the text
  emptied and paints the two parts itself; `text()` is still "Word   12" for everything that
  parses it. `COLOR_CHIP_ON`/`_ON_TEXT` are gone (the game page's lit segments borrowed the
  latter: they say `COLOR_BACKGROUND`, the same value, until step 4). "Demos & tools" and
  "Hidden" are neutral-400 outlines. The sort is `ui_library.SortBox`: Qt's arrow hidden
  (`[caret="painted"]` in the stylesheet, so Storage's and Settings' boxes keep theirs) and
  the design's thin caret painted as two strokes.
- **Fractional pixel sizes** (12.5, 11.5, 9.5): Qt takes a pixel size only whole, a point
  size as any number, and Windows' logical DPI is 96 at every scale -- `ui_theme.px_to_pt`.
- **The grid's gaps are inside the cells now** (`GRID_SPACING = 0`): 14 px above the cover
  (room for the lift, and the design's 14 px under the chips), 9 either side (covers 18
  apart), 8 under the words (with the next row's 14, the design's 22). `tile_padding` is
  still the room above -- suites 32 and 34 measure from it -- and `tile_padding_x` the side.
  A click in the gap between two covers now lands on the nearer tile (it used to fall in a
  6 px strip belonging to none); suite 32's see-through check samples a point "on no cover".
- **One left edge**: the grid's first cover starts `metrics.grid_inset` (9) into the list,
  so the page's margins are 28 less that, and the chips, the count line and the card
  (`ContinueCard.card_rect`) come that much in. Card, chips and covers all start 28 px in,
  under the brand, in the window and in TV mode alike -- measured.
- **Tiles are flat** as the design draws them: no sheen, a 1 px hairline (`COLOR_BORDER`)
  **outside** the cover, and only a lifted tile casts a shadow. **The mouse lights a tile the
  same way the pad does**: a 2 px accent ring outside the edge and the 24 px glow at 45%
  (`TILE_GLOW_PX`, `TILE_GLOW_ALPHA` 115), all drawn into the gaps -- the whole viewport
  repaints every tick, so nothing is left behind. Names 13 px Medium, the line under them
  11.5 px muted, each in a box 1.55 times its size as the design's text sits. A hidden game
  is veiled in the ground, not black. `TILE_FOCUS_COLOR` is the accent: the mockup's ring
  and the brief's "the colour is the accent" -- the table's accent 200 was a different
  screen's (Spotlight's strip) -- and since it is every control's ring, the switches, the
  storage rows and the buttons ring in the accent too. **The lift is 4 px, not 6**: the
  design's 14 px over the top row could not hold a 6 px rise, the growth and the ring.
- **The marks** are the design's pixels over its 137 px cover, as fractions of the cover's
  width so they scale with ours (176) and TV: the star accent 300, half its 24 px disc,
  the disc the ground at 75%; the NEW tag 9.5 px SemiBold letters 0.08 em apart, 2 x 7 px
  of padding, 4 px corners, accent 800 with accent 100 words and a 1 px accent-600 edge.
- **The backdrop** keeps its mechanism with the design's numbers: the art at 35%, its colour
  at 70% (`BACKDROP_SATURATION`, done on the few dozen pixels of the tiny image), gone into
  the ground by 62% of the way down; the vignette is the ground, not black. Stats and
  Storage keep this glow, so it is quieter there too -- suite 35's see-through check now
  samples between the top two figure cards, since the design's glow has faded fully by the
  lower ones, and picks the library's brightest glow so a dark cover cannot fool it.
- **Not taken from the mockup, on purpose**: its covers are about 137 px (8 across at 1280);
  ours stay 176 -- the brief keeps today's layout for `#1a` and names no cover size. One
  constant (`COVER_WIDTH`) if the user wants the denser wall.
- `tests/phase55_tests.py`, 37 checks on the live window, proven both ways: 37/37; with the
  seven files as they were at `before-phase-55`, 29 failures (the 8 that pass describe
  what was already so: the underline, the glow). Older checks updated to the new values:
  suite 31 (chips' room, the tabs' bold room), 32 (the name lines' sizes, the gap point),
  35 (rings in the focus colour, the see-through sample point), 54 (the focus colour), and
  33: between the game page's card columns the design's glow is plain ground, so no window
  pixel there can tell see-through from opaque -- **the page itself is asked**: drawn alone
  onto a transparent picture (`render` with DrawChildren, as the page transitions do), the
  gap must stay empty. Proven able to fail: alpha 0 as it is, 255 with an opaque background
  forced onto the page.
- **The restore tag was set late**: `before-phase-55` went on after the work had begun --
  on the Phase 54 commit, which is exactly the code before this phase (the data had not
  changed), so it restores the same thing it would have.

## Phase 54 notes (the Nocturne restyle, step 1 of 6: tokens and type)

Asked for as a design handoff (`docs/design/nocturne-handoff/` in the project root,
untracked: `Launcher Mockups.dc.html` with six screens, the token sheet in `_ds/`, a README
holding the brief). **Appearance only, `presentation/` only, one gated phase per step**:
2 Library, 3 the Continue card, 4 the game page, 5 Stats/Storage/toast/Settings/menus,
6 Phosphor icons; 7 (Spotlight for TV) and 8 (the side rail) only on an explicit go.

- **The token table is in `ui_rules.py`**, existing names changed in place: ground
  `#161826`, surface `#232532` (cards are solid now -- `COLOR_CARD` is the surface,
  `COLOR_CARD_BORDER` the hairline `#3f424d`), raised `#292b31`, text `#e9e9ed` / soft
  `#cfd3e5` / muted `#9397ab`, disabled `#595d6c`, accent `#9184d9` / hover `#b5abfc`, and
  the accent steps actually used so far (`COLOR_ACCENT_100/200/300/700/800`). Scrims are the
  ground. Every translucent white (`rgba(255, 255, 255, a)`) became the text colour at the
  same alpha, the four glass borders one `COLOR_DIVIDER` (text at 16%, stylesheet only), and
  the near-black glass (`COLOR_NAV`, `COLOR_HINT_BAR`) the ground at the same alpha -- each
  later step sets its exact alpha. Status marks share one hue (playing 400, finished 300,
  dropped muted): the glyph carries the meaning. The star is accent 300 on a ground disc,
  the NEW pill accent 800 with accent 100 text, the focus ring accent 200 (was white; the
  accent itself since Phase 55).
  Session and Most-played bars run accent 700 -> accent (`COLOR_SESSION_BAR_START`, new).
- **Radii**: tile 12 -> 8, Continue card 20 -> 14, the page's cover 16 -> 14, cards 18 -> 8,
  storage rows 10 -> 8.
- **Inter, downloaded with the user's go** (Inter-4.1.zip, 33.7 MB, the official release on
  github.com/rsms/inter; sha256 `9883fdd4...`), kept in the scratch folder; only five static
  TTFs and the licence are in the project. **SemiBold is the fifth, beyond the four first
  named**: the mockup sets exactly two labels at 600 -- the NEW badge and the pad buttons'
  letters -- and without the file Qt would fake the weight. `ui_icons.bundled_families()`
  registers every `.ttf` under `paths.resource_dir()/presentation/fonts` before the first
  family is chosen (it runs inside `_first_installed`); a missing folder is logged and the
  Segoe families behind "Inter" take over. Verified: the window's font resolves to Inter
  and the game page's title to "Inter Medium", a real face, not a synthesised one.
- **Weights**: `HEADING_WEIGHT = 500` replaces every stylesheet's `font-weight: 600` (14 in
  seven files; each built stylesheet checked to contain 500 and nothing else),
  `TILE_NAME_WEIGHT` is Medium, `reserve_bold_width` measures with the heading weight, and
  the painted titles, the placeholder cover's name and Storage's bold rows use it too.
  `LABEL_WEIGHT = 600` for the NEW badge and the pad letters. The Continue eyebrow is 500
  for now; the mockup has it at 400 with the rest of step 3.
- **Tracking**: `TITLE_TRACKING` (-0.02 em from 40 px, -0.025 em from 46 px) through
  `ui_theme.tracking`, on the Continue title (painted, `setLetterSpacing`) and the game
  page's title -- **Qt 6.11's stylesheets do accept `letter-spacing`**, probed: a 48 px
  line 530 px wide became 502 with -1.2 px, the same as setting it on the label's font.
- **Rendering the mockup**: the browser pane can only show a local file as an unstyled
  snapshot (support.js and the token sheet do not load). Headless Edge does it:
  `msedge --headless=new --window-size=1340,5600 --virtual-time-budget=10000 --screenshot=...`
  on the file URL, then the six 1280x800 cards cut out of the page picture (they start at
  x 22, y 211 / 1080 / 1949 / 2818 / 3687 / 4556). The `#1a` anchors are ignored headless.
  Before/after renders of the app come from a temporary `git worktree` of
  `before-phase-54`, with `test_sandbox.REAL` pointed at the real data folder (an old
  checkout has none of its own; it is git-ignored) -- read only, through the sandbox copy.
- **Left for later steps, on purpose**: the green Play (`COLOR_PLAY*`, steps 3-4), the
  light-filled chosen chip (`COLOR_CHIP_ON`, step 2), the literal blacks and whites drawn in
  code (tile edge and sheen, hero shading -- each with its screen). **One thing looks worse
  until step 5**: unrecorded months on the Stats chart take the hairline colour the table
  gives them, which the design means for a 6 px stub, so for now they are full-height grey
  slabs twice as loud as before.
- **Tests.** Three older checks asserted old values and now assert the new ones, as strictly:
  suite 31 measures bold room at `HEADING_WEIGHT` (it measured SemiBold, so "Finished" and
  "Dropped" read as one pixel short), suite 32 looks for the focus colour where it looked
  for white, suite 35 wants the row glass in the text colour where it wanted red 255.
  `tests/phase54_tests.py`, 20 checks: all 30 constants of the table, the marks, the radii,
  no pure white or black among the constants, the five files and the OFL, real Medium and
  SemiBold faces, the Segoe fallback in a second process with the folder missing, 500 in
  all seven stylesheets, the tracking (and that Qt draws it narrower), Inter in the live
  window. Proven both ways: 20/20; with the 14 files put back as they were at
  `before-phase-54` and the fonts moved aside, 19 failures. Windows also lists the static
  files under legacy names ("Inter Medium", "Inter SemiBold"); they are faces of the one
  family, as the weight checks show.
- **The installed program would not have Inter**: `packaging/app.spec` does not bundle
  `presentation/fonts`, and packaging is outside this change set -- one line there, on the
  user's go (ARHITECTURA §12, item 18). From source, as the user runs it, it is there.

## Phase 53 notes (a game's total and its sessions agree)

Reported from use: a game's total playtime read 15-20% under the sum of its sessions; the
suspected cause was the 3-second tick in `ui_window.py` adding truncated whole seconds.
**Confirmed before anything changed**, with one correction of place: the window's timer and
the adding are in `ui_window.py` (`_poll_playtime`: `_unbanked += tick.seconds`;
`_bank_playtime`: `total = stored + seconds`), but the truncation was one call down, in
`launch.PlaytimeTracker.poll`: `seconds = int(now - last_tick); last_tick = now`.

- **Why it was as much as a sixth.** The window's `QTimer` is Qt's CoarseTimer: measured
  over 30 ticks it fired every 2.993-3.012 s, and 13 of the 30 came a hair under 3 s, which
  `int()` counts as **2** -- nearly a whole second dropped. 90.02 s played, 77 s counted,
  14.5% lost. This copy's own `launcher.log` shows the same on real sessions: Slow Roads
  937 s measured, 789 s banked (15.8%); The Witcher 3 356/298 (16.3%); CULTIC 149/126
  (15.4%). The session's own length was always `int(now - started)`, measured from its
  start, so it was right -- which is why the two disagreed.
- **The fix, in `ui_window.py` as asked, and kept small**: each tick sets
  `_unbanked[key] = tick.total_seconds - _banked[key]` -- the session's length measured
  from its start, less what is already in the total -- and `_bank_playtime` adds that and
  records it in `_banked` (cleared when the session ends). So after every write the total is
  *the total at the session's start + the elapsed time*, rounded once, and the error is
  under a second however long the session or irregular the ticks. **Added, not set**: a
  literal `total = start total + elapsed` would write over time something else adds while
  the game runs -- carrying over an earlier install (Phase 36) -- and the test proves it
  survives. The logic was deliberately not moved out of `ui_window.py` (ARHITECTURA §12,
  item 6, stays open).
- **`launch.py`, three lines of code**: the session clock is `time.monotonic()` (was
  `perf_counter`; on this Python both are QueryPerformanceCounter at 100 ns, read here as
  the same value), and `last_tick` moves on by the whole seconds counted rather than to
  now, so `Tick.seconds` -- which nothing sums any more -- carries its fraction too.
- **`tests/phase53_tests.py`, 19 checks, on a fake clock** (`time` swapped in `launch` and
  `ui_window` only): one-hour sessions through the real tracker, window and banking --
  every 3.4 s; a hair either side of 3 s like the real timer; irregular 2.9-4.7 s with a
  500 s carry-over mid-session; two sessions in a row. Total and session agree within 1 s
  at every once-a-minute write and at the end. Proven both ways: 19/19 with the fix; with
  the two files put back as they were at `before-phase-53`, 10 failures -- 3604 s played,
  3180 counted. A write waits for the first poll after 60 s, so 3.4 s polls write 58
  times an hour, not 60; the first version of the check said 59.
- **`tests/playtime_report.py` is a dry run** on the real `overrides.json` (or any copy
  given to it): stored total, sum of sessions, difference, ratio, and a note where
  something other than the drift explains part of it. It reads the file once in binary and
  compares its fingerprint after. On the day: 75 h 38 m stored against 88 h 24 m of
  sessions (85.6%); the 23 games with no other explanation, 84.7%.
- **The full run was 933 of 935, not ALL GREEN**, and that is recorded as such: one pad-menu
  or focus-ring check in suite 35 and one in 49 failed while the user had Firefox in front.
  Re-run alone, 35 passed 78/78; 49 kept failing one or two of its menu checks, a different
  one each time -- **and failed the same way with the two files put back as they were at
  `before-phase-53`**, so it is the machine, not this change (ARHITECTURA §12, item 13).

**Limits that remain** (also in ARHITECTURA §12):
- **The totals stored before this phase were still ~16% low.** Nothing was repaired here:
  the rule was the user's, chosen from the report. **Repaired in Phase 61** (each total
  raised to its sessions, never lowered).
- **The sum of sessions is not exact either**: a session is kept in whole minutes, rounded
  down, and one under `SESSION_MIN_MINUTES` is not kept, so it reads up to a minute low per
  session -- two short sessions of chained.together show 135%.
- **Time before 14 August 2026 (Phase 20) has no sessions**, so a game played before then
  has total that no session accounts for; the report notes games first seen before that day.
- Unchanged and still true: a crash loses at most one write interval (60 s) of a live
  session; nothing is timed for a game started with administrator rights, a URI game, or
  after the launcher is closed (Phase 16).

## Phase 52 notes (the pad works Settings, not only menus)

Reported from use right after Phase 49: the menu on a game's page worked with the pad, but
once Start had opened Settings the pad did nothing -- locked out, as before.

- **The cause was the gate, the half Phase 49 checked only with a menu up.** `ControllerHub`
  reads the pad only while `window_is_active()` says yes (Phase 7), and the window passed
  `self.isActiveWindow`. A menu is a popup: the main window stays active under it. Settings,
  a confirmation box, the screenshot viewer are windows of their own, and Windows makes each
  the active window while it is open -- so the gate said no, `_reset_held` ran on every poll,
  and no press ever reached `_drive_dialog`, which already knew what to do. A probe read it
  directly: menu open -> active window MainWindow, gate True; Settings open -> active window
  SettingsDialog, gate False.
- **The fix**: the gate is `MainWindow._launcher_in_front`, which is
  `QApplication.activeWindow() is not None` -- "is one of this application's windows the
  active one". With a game (or anything else) in front no window of this process is active,
  so the Phase 7 defence is whole; the suite proves that half with a real second process
  that takes the foreground.
- **Why Phase 49's suite missed it**: it emitted on `pads.action`, which is *after* the gate.
  `tests/phase52_tests.py` holds buttons on a simulated pad (`get_button`/`get_axis`, the
  shape SDL hands the hub), stubs only `pygame.event.get`, and lets the hub's real 16 ms
  poll find them -- gate, button edges, queued signal and all. Settings (Start, d-pad down
  moves, B closes), a `QMessageBox` (B answers Cancel), the game menu (X, down, B), and
  another program in front (gate False, A never heard). Proven both ways: 17/17 with the
  fix; with `self.isActiveWindow` put back temporarily, 7 failures -- Settings opens and is
  then dead, the menu still works: the user's report exactly.
- **Test harness trap**: a dialog runs its own event loop *inside* whatever opened it, so
  a test that pauses with a nested `QEventLoop` of its own is stuck behind the dialog. The
  first version hung (and a timeout killed it with nothing printed). The suite is now a
  chain of timed steps, each scheduling the next *before* it runs; the chain's end -- or a
  watchdog -- closes whatever is still open and reports it, because quitting the outer loop
  waits for the inner one, and a watchdog that stands down once the steps are "done" is no
  watchdog at all (that was the second hang).
- `docs/ARHITECTURA.md` also gained the Phase 51 paragraph it was missing, and section 13
  no longer says this folder is "only the copy".

## Phase 50 notes (the pad's real buttons in the TV hint bar)

Asked for from use: the bar's text chips ("A / ✕", "LB·RB / L1·R1", "View / Create")
broke the experience; it should show actual buttons. Asked whether pictures had to be
downloaded: no -- they are painted.

- **`presentation/ui_buttons.py` draws each button** with QPainter, in fractions of its
  height, like `BatteryGlyph`: dark round face buttons carrying Xbox's coloured A B X Y or
  PlayStation's coloured ✕ ○ □ △, a pair of bumpers (LB RB / L1 R1), the two middle
  buttons (View's two windows and Menu's three lines on a round button; Create's three
  rays and Options' three lines on DualSense's upright pill), and a d-pad with arrowheads
  in the arms that are meant. Painted rather than downloaded: sharp at 225% on the 4K TV,
  no new network source, no image licences, colours in `ui_rules` (`COLOR_PAD_*`, each its
  own string so phase 35's QColor check reads them; `PAD_GLYPH_HEIGHT_FRACTION`).
- **Only the family of the pad in use.** The pad plugged in here turned out to be an
  **8BitDo Ultimate 2C** (Xbox layout), besides the DualSense. `controller.family_of` reads
  the pad's name -- `rules.CONTROLLER_PLAYSTATION_WORDS`, never "wireless controller",
  which is in the 8BitDo's name -- and anything not PlayStation is drawn as Xbox. The hub
  emits `familyChanged` when the pad in use changes family (hotplug or picking up the other
  pad); the window hands it to `HintBar.set_family`. No pad: Xbox. A Nintendo-layout pad
  would be drawn as Xbox though its A/B are printed swapped -- neither pad here is one.
- **The bar's data is unchanged**: `ui_tv.A = ("A", "✕")` etc., `HINT_SETS`, `HINTS` and
  `labels` mean what they meant, so phases 22, 23 and 35 needed nothing; `ui_tv.GLYPHS`
  maps each name pair to the button drawn. Each hint is now one `HintItem` (button + words)
  so the gap inside a hint is smaller than between hints.
- **The blanket `QWidget { background }` boxed every hint** in the first render (the Phase
  32 trap): `QWidget#HintItem, QWidget#PadButton` are transparent in `ui_tv.stylesheet`.
  The suite's check for it first passed with the rule *removed* (the box is #0f1116 on a
  #0a0b10 bar, 17 apart, under a tolerance of 18); measured, tightened to 6, and proven
  both ways.
- `tests/phase50_tests.py`, 29 checks: names to families, the hub's signal, all nine
  buttons ink pixels in their colours in both families, the window follows a pad swap, no
  text chip and no box left, one bar height per TV size and every set under 1920px at
  every size (widest 1248). ALL GREEN, 900 (871 + 29).

## Phase 49 notes (the pad keeps working in a menu it opened)

Reported from use: in TV mode, on a game's page, X opened the menu and then the pad did
nothing at all; mouse and keyboard still worked.

- **The cause was the delivery, not the routing.** `ControllerHub` polls on a 16 ms QTimer
  and emits each press; `pads.action` was connected *directly* to `_on_pad_action`, so X's
  `menu.exec()` -- and Start's `SettingsDialog.exec()` -- ran inside the timer's own
  callback, and **Qt on Windows does not fire a timer again while its callback is still
  running**. Measured: opened from inside a 16 ms timer, the timer ticked once (the press
  itself) in the 1.5 s the menu was open; opened from outside it, 94 times. The gate
  (`isActiveWindow`) was checked first and is fine -- still True with the menu up.
  **But only with a menu up**: Settings is a window of its own and took the gate away --
  the second half of this bug, reported after this phase and fixed in Phase 52.
- **Not caused by the restructure**: the same probe on `before-phase-38`, in a temporary
  worktree, behaves identically, so the user's daily launcher has it too (it is read-only
  here; not touched).
- **The fix is one line**: `self.pads.action.connect(self._on_pad_action,
  Qt.ConnectionType.QueuedConnection)`. The poll returns at once, keeps polling while the
  menu or dialog is open, and each press arrives through the event queue -- inside the
  menu's loop -- where Phase 27's routing (`_drive_popup`, `_drive_dialog`) already knew
  what to do with it.
- **Why 850 green checks missed it**: every suite pressed buttons by calling
  `_on_pad_action` from outside the timer. `tests/phase49_tests.py` presses them the way
  the hub does -- `window.pads.action.emit(...)` from inside a timer at the hub's interval --
  and works a menu (game page and grid, TV and window) and Settings with nothing else.
  *That emits after the gate, so it said Settings worked while a real pad was still locked
  out of it -- Phase 52's suite presses through the hub's own poll instead.*
  Proven both ways: 20/20 with the fix; with it temporarily undone, 16 failures, every
  scenario "poll ticks: 1". The first version of that suite *hung* without the fix (nothing
  could close the menu), so it has a watchdog that fires inside the stuck loop and closes it.
- **Any future pad-driven test should press through `pads.action` from a timer**, not call
  `_on_pad_action` directly -- the shortcut skips the very path this bug lived on. Better
  still, since Phase 52: hold buttons on a simulated pad and let the hub's poll find them,
  so the gate is on the path too.
- `run_all` now finds every `phase*_tests.py` itself (it had a fixed 22-37 range).
- Suite 22 counts 47 with the DualSense plugged in, 46 without: 871 = 850 + 20 + that one.

## Phase 48 notes (step 10: the user's data in `data/`)

- **Run from source, `paths.data_dir()` is `<project>\data`** (`rules.DATA_DIRNAME`); frozen,
  it is still the exe's folder, so an installed copy and its installer/uninstaller are
  unchanged. `paths` now imports `rules` (same layer). Every data path in the app already
  went through `data_dir()` -- config, overrides, catalog, cache, backups, save_backups, the
  log, imported art -- so `paths.py` was the only app file whose logic changed.
- **The trap was shown first, read only**: with the new `data_dir()` and the data still in
  the root, `check_paths` failed "the data folder holds the real overrides.json" naming the
  empty `data\` -- the launcher would have opened as on a first run.
- **The move**, with nothing running: `git mv` for the two tracked files (history follows),
  a same-drive rename for `catalog.json`, the two logs, `cache/` (721 files), `backups/`
  (26) and `save_backups/` (22). Counted and sized before and after: identical. The
  existing `.gitignore` patterns have no leading slash, so they match inside `data/` too.
- **The tests follow the data, not the project**: `REAL` in suites 22-26 and in
  `test_sandbox` is now `<project>\data` (`test_sandbox.PROJECT` keeps the project for
  `sys.path`); `REAL_SHOTS` and suite 36's save copies look in `data\`; `sources` skips
  `data/`. `check_paths` asserts `test_sandbox.REAL == paths.data_dir()`, which is what
  keeps the literal "data" in the tests honest.
- **The real launcher was opened on the real data** twice: built unshown (33 games, 27 on
  the grid; 65 of 65 records; 48 h 8 min, equal to the file; 13 of 13 chosen covers on
  disk; no snapshot written), and started normally for ~30 s -- it logged to
  `data\launcher.log`, scanned 33 games with 0 network requests, closed with exit code 0,
  and nothing appeared in the root. (`taskkill` needs the child's pid: the venv's
  `python.exe` is a launcher that starts the real interpreter as a second process.)
- **Never `git checkout` or `reset --hard` an older tag in this folder now**: every commit
  before Phase 48 tracks `config.json` and `overrides.json` in the root, so going back puts
  old copies there and the old code reads them. Look at old code with `git worktree add`.

## Phase 47 notes (restructure step 9 of 9: closing)

- **`tests/check_layers.py` is permanent and in `run_all`**: every import of the app, inside
  functions too, mapped to its layer (entry > presentation > adapters > logic > providers >
  web > data_access > shared); any import up the order fails. 0 today. Run from a temporary
  `git worktree` of `fb95978` (before 8b), it finds exactly the three upward imports -- it
  can fail when it should.
- **The installer was rebuilt from the restructured code and actually run.** `build.py`:
  31 s, a 137 MB app, a 66 MB installer, **without** `hook-humanize.py` and without
  `hookspath` (both removed: the collision they called off cannot happen to
  `shared.humanize`). Every app module the installed program needs is in `PYZ-00.toc`, 80 of
  them -- only `scanner` is absent, correctly; `warn-app.txt` names none of ours.
- **The installer test (scratch `installer_test.py`, 16/16) runs everything in a fake
  profile.** `USERPROFILE`, `APPDATA` and `LOCALAPPDATA` point into a temporary folder,
  because the install folder, the Desktop and the Start Menu are all found through them --
  and because **`uninstall.remove_shortcuts` deletes every shortcut declaring the app id,
  which the user's real daily shortcuts do**. Run without the fake profile, the uninstaller
  would delete them. The real four are hashed before and after, and the HKCU Add/Remove
  entry was checked absent first (the test's own is created and then removed by the
  uninstaller). The installed copy was given a quiet config.json (no network, no pad, no
  watch) before its first start; it logged "installed copy" with no traceback and found 31
  games -- Xbox is off by default in a fresh install.
- **Two runs of `run_all`**: the first, while documents were being edited, had suite 27 (5:
  the pad-driven menu and the tile photographs) and 34 (1: a frame at 32.5 ms against 20)
  red; both passed alone (44/44, 58/58). The second, on a quiet machine: ALL GREEN, 850/850.
  Nothing in the app changed this phase. Suites 27, 28 and 34 all need the machine to
  themselves; that is on the later list.
- **Decision 2 done**: `build/`, `dist/` and three `__pycache__` folders (342 MB) to the
  Recycle Bin through `SHFileOperationW` with `FOF_ALLOWUNDO | FOF_WANTNUKEWARNING`; the bin
  grew by exactly 5 items and 342 MB. Only three existed because this shell sets
  `PYTHONDONTWRITEBYTECODE=1`; they came with the copy. Root: 28 entries.
- `docs/ARHITECTURA.md` section 4 was regenerated from the code (imports grouped by layer),
  CLAUDE.md's file layout is grouped by layer, and section 13 is the final click-through list
  (Slow Roads is the plain game: a folder game with nothing chosen for it).
- The backslash trap a sixth time (`C:\Users` in a Python string through a heredoc); it
  failed to parse and changed nothing. Text with backslashes goes through the Edit tool.

## Phase 46 notes (restructure step 8 of 9: the two boundary fixes)

Code moved between modules, not files moved -- so, unlike steps 1-7, `check_move_diff`
lists non-import lines, and each sub-step names the files it was allowed to touch.

- **8a: `config.json` has an owner.** `CONFIG_PATH`, `load_config` and `save_config` moved
  from `logic/discovery.py` into `data_access/config_io.py`, cut and pasted by a script that
  asserted the 49 lines arrived byte for byte; three imports only they used left discovery
  with them. Callers changed `discovery.X` to `config_io.X`: `ui_window` (9), `transfer`
  (1, inside a function), `scanner` (`--write-config`), suites 25-27 and `check_paths`.
  `discovery` is now imported only where a scan runs (`scan_worker`, `scanner`), and it
  binds no data path at import any more.
- **The sandbox guard follows the data, not a module list**: it now refuses after
  `data_access.catalog_io` or `data_access.config_io` -- the two modules that bind real
  file paths when imported -- and no longer names `discovery`. Proven the third time the
  same way: `check_paths` with the new module listed failed against the old guard
  ("STARTED"), then passed 17 of 17.
- `scanner.py` still reads config.json with its own function (slightly different defaults);
  folding it into `config_io.load_config` would change behaviour, so it stays on the later
  list.
- **8b: logic no longer reads the appearance file.** `SOURCE_LABELS`, `STATS_CHART_MONTHS`,
  `STATS_TOP_GAMES` and `SCREENSHOT_MIN_BYTES` moved, with their comments, from
  `presentation/ui_rules.py` to the end of `shared/rules.py` under "What the logic reports,
  not how it looks". Values proven identical by loading `ui_rules.py` as it was at
  `before-phase-46` from git and comparing; none is left in `ui_rules`, so there is one
  source. Readers say `rules.X` now: `stats`, `gamedetails` (its import inside a function
  is gone), `screenshot_worker`, `ui_continue` (which gained `from shared import rules`) and
  suite 23 -- which uses `STATS_CHART_MONTHS` six times, not the five counted, so the
  script stopped at that file before writing it; finished with the right count.
- **Result: no module imports from a layer above its own.** Checked package by package --
  nothing in logic, adapters, data_access, providers, web or shared imports
  `presentation`, and so on down. The only link between the three gateway layers is the
  Steam provider using `web.steam_web` during a scan, which the diagram shows.
- The backslash trap a fifth time, in a scratch script edited through a bash heredoc; it
  failed to parse before touching anything, and was fixed with the Edit tool.
- **Suite 34 failed 2 checks in 8b's full run and passed 58 of 58 alone**: section 1 samples
  a page partway through sliding in and caught it still at 0. That minute the browser was
  rendering the Mermaid diagram -- don't do other heavy work while `run_all` runs. 8a's
  full run was clean.

## Phase 45 notes (restructure step 7 of 9: `shared/`, and `paths.py`)

- **`shared/` holds what every layer uses**: `models`, `rules`, `paths`, `naming`, `walk`,
  `humanize`, `registry`. None of the seven names exists in the venv or the standard
  library -- checked before the move, so a stale bare `import rules` can only fail, never
  quietly load something else.
- **135 import lines in 69 files**, and one line that is not an import:
  `paths._SOURCE_DIR` is now `Path(__file__).resolve().parents[1]`. `check_move_diff` was
  run with `--allow shared/paths.py` and reports that line and nothing else.
- **The trap was shown before it was closed**, read only, with the launcher never started:
  moved but unfixed, `paths.program_dir()` and `data_dir()` both answered `...\shared`,
  where there is no overrides.json -- the launcher would have opened as on a first run, no
  playtime, no art, and written a fresh library into `shared\`. `check_paths` failed 8
  checks, each naming that folder, including the shortcut targets
  (`shared\launcher.py`, `shared\.venv\...`) that `taskbar` derives from `paths`. Fixed, it
  passes 17 of 17 and reads the real 65 records.
- **One `paths` module, one name**: the sandbox now patches `shared.paths`, the same module
  object every data module imports -- the live import check finds no file loaded twice, and
  `check_paths` finds exactly one `paths.py` in `sys.modules`.
- `packaging/hooks/hook-humanize.py` existed because a top-level module named `humanize`
  collided with the PyPI package's PyInstaller hook. The module is `shared.humanize` now,
  so the hook should be dead; it stays until the step-9 rebuild proves that. (It did, and the
  hook was removed in Phase 47.)
- **The root has 31 entries**, the figure planned in Phase 38: `launcher.py`, `scanner.py`,
  ten folders, the project files, the user's data and the tools.

## Phase 44 notes (restructure step 6 of 9: `logic/`)

- **The 15 modules with the launcher's rules and no Qt are in `logic/`**: discovery, launch,
  sessions, stats, storage, saves, save_backup, removal, lineage, pick, transfer,
  gamedetails, focus, taskbar, uninstall. None derived a path from its own location;
  `taskbar` and `uninstall` take theirs from `paths`, which has not moved yet.
- **73 import lines in 33 files, and one inside a string**: the `-c` helper suite 28 starts
  in a separate process now says `from logic import focus`.
- **The import net had a hole, and the live half found it.** Six lines had the form
  `import stats as stats_module` (ui_window, ui_stats, ui_storage, suite 36), which the
  rewrite did not know -- Phase 38's survey of `as` imports covered only the `ui_` modules.
  The static half passed them, because it only checked names it recognised as the
  project's, and once `stats` left the root, `stats` was not a project name any more; it
  was taken for a library. The live half failed: those lines run on import. **A stale name
  inside a function would have slipped through both.** `check_imports` now also requires
  every name that is not the project's to exist outside it (standard library or the venv;
  built-in and frozen modules report no file and count as outside). Run on the tree before
  the fix it reported exactly the six lines and nothing else -- so steps 1-5 left none.
- **The four planned quiet fixes**: the sandbox's guard says `logic.discovery` (proven the
  same way as step 5 -- `check_paths` failed against the stale guard with "STARTED", then
  passed 17/17); suite 25 reads `removal.__file__` instead of opening `"removal.py"` from
  the working folder; `app.spec`'s hidden import is `logic.uninstall`; suite 37's
  "shortcuts are made from wherever the project is" compares `taskbar.SCRIPT_PATH` and
  `PYTHONW_PATH` with the project folder found from the test's own place, instead of with
  the folder taskbar.py sits in, which stood in for the project only while they were the
  same folder.

## Phase 43 notes (restructure step 5 of 9: `data_access/`)

- **`data_access/` holds the code that reads and writes the launcher's own files**:
  `catalog_io` (catalog.json, the `Overrides` store, and -- still -- the `GameView` merge) and
  `backups` (snapshots, rotation, restore, atomic writes). Both find their files through
  `paths.data_dir()`, never their own location. config.json still belongs to
  `discovery.py` until step 8 moves it here.
- **18 import lines in 16 files**, plus the usage example in `test_sandbox`'s docstring.
- **The sandbox's guard names modules as text, and a move silently disarms it.**
  `test_sandbox.start` refuses to run once a data module is loaded -- loaded first, it has
  bound the real file paths, and a test would write the user's real overrides.json. The
  guard looked for `"catalog_io"` in `sys.modules`; after the move that key never appears,
  so it would never fire. This was proven, not argued: `check_paths` was given the new name
  first and run against the stale guard, and failed ("STARTED" after
  `data_access.catalog_io` was imported); with the guard updated it passes 17 of 17. Step 6
  does the same for `discovery`.
- The boundary is not complete yet -- section 10 of `docs/ARHITECTURA.md` lists what still
  touches the three files from outside (`transfer`, `storage`, `lineage`, `ui_window`,
  `scanner`, `discovery`'s config functions).

## Phase 42 notes (restructure step 4 of 9: `adapters/`)

- **`adapters/` holds the six modules that use Qt but draw nothing**: the three QThread
  workers (`scan_worker`, `save_worker`, `screenshot_worker`), `folder_watch`, `controller`
  (SDL through pygame, turned into named actions) and `icons` (an exe's shell icon, turned
  into a usable pixmap). Each turns something outside the window's event loop into signals
  or pictures -- the Adapter pattern, which is why the folder has that name.
- **21 import lines in 15 files and nothing else**; none inside a function. Nothing derived
  a path from these files' own location, and the two comments that say "see controller.py"
  and "see folder_watch.py" still name the right files.
- The presentation is the only layer that uses them (`ui_window`, `ui_detail`,
  `ui_removal`); they in turn use logic (`discovery`, `saves`, `save_backup`) and the web
  clients. `screenshot_worker` is the third of the three upward imports to `ui_rules`.
- **Suite 28 failed 2 checks in the full run and passed 19 of 19 alone**, on the same code:
  its fake game did not get the screen ("took the screen False") while Firefox, Chrome and
  Word were open, so the launcher had nothing to come back in front of -- the Phase 35
  observation exactly. `run_all` runs it in the middle of a five-minute sequence; a window
  the user clicks during that minute is enough.

## Phase 41 notes (restructure step 3 of 9: `presentation/`)

- **All 28 `ui_*` modules are in `presentation/`**, names unchanged: `import ui_rules`
  became `from presentation import ui_rules`, `from ui_window import X` became
  `from presentation.ui_window import X`. Every later line that says `ui_rules.X` is
  untouched. Absolute imports, never `from . import`: one spelling per module.
- **154 import lines in 42 files**: 152 the import net sees (4 inside functions) and 2 it
  cannot -- the `import ui_window` inside the child scripts suites 34 and 35 write to disk
  and run at 225%, which only those suites' own section 9 exercises.
- **The three upward imports are now visible in the folder names**: `stats.py`,
  `gamedetails.py` and `screenshot_worker.py` say `from presentation import ui_rules`.
  Step 8 removes them.
- **Phase 32's "the shelves are gone" was the quiet trap of this step**: it asked
  `find_spec("ui_shelf")`, which after this move answers None whatever exists, because no
  `ui_` module is importable from the root any more. It now looks for a `ui_shelf.py` file
  anywhere in the project.
- Logger names follow the modules: `launcher.log` now says `presentation.ui_window`.
  Nothing filters on a logger name.

## Phase 40 notes (restructure step 2 of 9: `web/` apart from `providers/`)

- **`providers/` now holds only discovery**: the five launcher sources, the folder scanner,
  `detect`, `steam_art` (Steam's *local* art cache), and the two modules only discovery uses,
  `provider.py` (the contract) and `peinfo.py` (PE version resources), which left the root.
- **`web/` holds the four modules that talk to the internet**, and nothing outside it does:
  checked by searching for every network library after the move -- `providers/epic.py`
  imports `urllib.parse` only to encode a launch URI.
- **12 import lines in 10 files changed and nothing else** (`check_move_diff before-phase-40`:
  0 other lines). Three were inside functions (`screenshot_worker` twice, `ui_settings`);
  the import net reads those. `providers/steam.py`'s one line became two, because
  `steam_art` stayed and `steam_web` left.
- **`packaging/app.spec` collects `web` as well as `providers`**; the installer is not rebuilt
  until step 9.
- The scanner net is the one that matters here: the Steam provider asks `web.steam_web` for
  app types and art during a scan, and discovery asks `web.steam_search` for appids. All 33
  games came back with the same art paths, appids and types.
- Import lines were replaced where they stood, not re-sorted, so `from web import ...` can sit
  among the root modules' imports; reordering would be a cosmetic change in a move commit.

## Phase 39 notes (restructure step 1 of 9: the tests and the nets, nothing of the app)

Approved as "go with step 1, and yes to all four recommendations". **The four decisions**,
recorded in `docs/ARHITECTURA.md` section 11: (1) the user's data moves into one `data/`
folder, as its own step after step 9; (2) `build/`, `dist/` and `__pycache__/` go to the
Recycle Bin at the very end, after the installer rebuild; (3) the committee sees an export
made at presentation time, this repository keeps tracking config/overrides and keeps the
"Play data" habit (A or B, and whether CLAUDE.md goes in, still to choose then); (4) both
boundary fixes, config_io and the four ui_rules values, in step 8.

- **Every suite, the sandbox and the runner moved to `tests/` with `git mv`; only their
  paths changed** -- each `Path(__file__).resolve().parent` meant "the project folder" and is
  now `.parents[1]`. The child scripts of suites 34 and 35 put `tests/` on their path too,
  because they import `test_sandbox`. `run_sandboxed.py` finds a suite beside itself.
- **The two checks that listed one folder now read the whole project** (`tests/sources.py`)
  and print how much they read: suite 35 reads 104 files and finds 51 `QColor(ui_rules.X)`
  in 14 files, the same 51 in the same 14 as before the move (when it read the root's 81);
  suite 37 reads 104, the old 81 + 2 among them.
- **Suites 33-36 print how much of the real cache they copied** (40 screenshots; suite 36
  also 15 save-copy folders), so a wrong path that copied nothing would show instead of
  letting the screenshot checks pass on empty pages.
- **The nets are in `tests/` and `tests/run_all.py` runs everything** -- suites one at a time,
  then imports, paths, scanner and the original folder. `check_paths` proves the sandbox
  guards the folder holding launcher.py and the real overrides.json, catches a change planted
  in a stand-in copy, patches the one `paths` module the data modules use, and refuses to start
  after a data module was imported first. Its `DATA_MODULES` names, and the guard in
  `test_sandbox.start`, must change in the steps that move catalog_io (5) and discovery (6):
  a guard that checks a name nobody imports any more never fires.
- **`check_move_diff.py <restore point>`** is the "logic did not change" proof for every later
  step: it fails on any changed line in the app that is not an import, unless the step's
  plan lists that file with `--allow`.
- `tests/baseline/` (git-ignored) holds the scanner's saved run, carried over unchanged from
  step 0 -- comparing against it now shows discovery is untouched since before the
  restructure -- and the original folder's fingerprint, taken fresh at the start of each run.

## Phase 38 notes (the thesis copy, and the plan to restructure it)

**This folder, `C:\Users\andre\Licenta`, began as a copy made for the user's bachelor thesis,
and since 2026-10-06 it is also his daily launcher** (his decision, Phase 51). The old folder,
`C:\Users\andre\Game Launcher`, is the launcher as it was before the thesis work. Everything
above was written for the old one; four things differ here:

- **The four shortcuts (Desktop and Start Menu, normal and TV) point at this folder**, rebuilt
  with `launcher.py --make-shortcuts` from here, which is now the right way to rebuild them.
  Before switching, the old folder's changes since the copy (four records: two covers, two
  status marks, one NEW flag; four settings) were brought over through `data_access`, and the
  two new covers copied into `data\cache\sgdb_art\`; playtime and sessions were already
  identical. Going back is the user's to do, by running the old folder's own
  `launcher.py --make-shortcuts` himself (never from here: it would write the old folder's
  `__pycache__`). The copy's earlier hand-made `Game Launcher (Licenta).lnk` pair is gone (to
  the Recycle Bin): with the real shortcuts pointing here they only duplicated them.
- **The old folder is read-only** -- for the app, for tests and for Claude. It is the backup of
  the launcher before the thesis work. This copy's overrides.json still holds 34 cover/banner
  paths into the old folder's cache, read from there because they exist; the same 34 files are
  in this copy's `data\cache\`, so the Phase 37 relocation takes over if the old folder goes.
- **Git: branch `licenta` only, never push unless asked.** History and `origin` are shared with
  the original; `master` stays where it was copied (`4dab512`), tag `licenta-baseline` stays put.
- **config.json and overrides.json are no longer tracked (since Phase 69, the user's yes);
  history is not rewritten.** The repository shown to the committee is meant to be an export
  (`docs/ARHITECTURA.md`, decision 3; BAZA_DE_DATE §17). Their old versions stay in the history.

Step 0, done:

- **The baseline was red before anything was touched, for two reasons outside the code, and the
  tests were fixed in their own commit (`30fe735`).** Phase 32: the real config remembers the
  window maximized, the sandbox copied that, and a maximized window ignores the test's resize --
  `test_sandbox` now drops `window_geometry` (`NEVER_COPIED`), as phase 26 always did. Phase 37:
  the copy's art points into the original folder, so rewriting only this folder's name tested
  nothing; the folder is now also read off the chosen pictures. 850 of 850 afterwards.
- **The restructure plan is `docs/ARHITECTURA.md`**, in Romanian (the thesis language): the
  layers, a module map, two walks through the code, the target tree (103 root entries to 31),
  every quiet breakage found by search, nine steps, the data boundary for a later database phase,
  and four decisions that are the user's. Keep it updated at every step.
- **The safety nets lived outside the project until step 1** brought them into `tests/`: a static
  and a live import check (430 import lines, 19 inside functions; 75 modules load, none under two
  names), the scanner's output on the real library compared field by field (33 games), and a
  file-by-file fingerprint of the original folder before and after every test run.
- **The layer split was checked against the real import graph**, not reasoned about: zero
  unassigned modules, exactly three upward imports (stats, gamedetails, screenshot_worker ->
  ui_rules), one cycle (ui_window -> ui_actions -> ui_earlier -> ui_window, broken by a lazy
  import).

## Phase 37 notes (renaming the project folder)

Asked as "can we safely rename the folder of the project to Game Launcher?". Everything that
depended on the folder's name was found first, read only:

- **What would have broken, and how each is handled:**
  - **Chosen covers and banners** (34 in overrides.json) are stored with full paths into
    `cache\`. `catalog_io.relocated` looks for a path that is gone again under the current
    data folder, from the last component that is one of `rules.OWN_DATA_FOLDERS` (cache,
    backups, save_backups), spelled as the folder is; anything else -- art picked from
    Downloads -- is never redirected. `relocate_artwork` rewrites overrides.json once as the
    window opens (and after a restore), so an export, which bundles only art it can find,
    sees the right paths; `GameView` relocates on read too, but only after `isfile` fails,
    since cover_source runs on every tile paint. The catalog's own art paths are relocated
    once in `load_catalog`, and the next scan rewrites them.
  - **The four shortcuts** hold absolute paths: `launcher.py --make-shortcuts` from the new
    folder. `taskbar` derives every path from its own location, so it needs no change.
  - **A taskbar pin** ("Game Launcher", pointing at the old pythonw.exe) cannot be repaired
    from here: unpin it, start the launcher, pin it again.
  - **Five test files (22-26) and `packaging/build.py`** named the folder; they use
    `Path(__file__)` now, and the commands in this file are relative to the project folder.
- **Already fine, and checked rather than assumed**: Steam's cache (`steam_web.json`, 79 old
  paths) repairs itself -- `_ensure_artwork` looks in the current cache folder when a stored
  path is missing, with no network; config.json names no project path; nothing in the
  registry, the Run key or the Startup folder points at it. **The venv moves**: a copy of
  its `python.exe` and `pyvenv.cfg` in another folder took that folder as `sys.prefix` and
  imported a module from its `Lib\site-packages`; no `.pth` names the old folder
  (pywin32's are relative). Only the console-script exes in `Scripts` (pip.exe,
  pyinstaller.exe, the pyside6 tools) carry the old path -- use `python -m pip`.
- **Claude Code's per-project memory folder was empty**, so nothing to carry; earlier
  conversations stay listed under the old folder name.
- **Windows will not rename a folder a program is working in** -- the launcher and the
  Claude Code session both have to be closed first.
- **Two older tests fixed on the way, neither about the launcher**: phase 36's Witcher
  sections assumed the carry-over had not happened yet, and the user had done it on the
  real machine three days later -- nine failures; they now check the result when it has
  (the no-assumed-state rule). Phase 34 looked once, 30 ms after a move, for a glide in
  progress, and missed it twice on a busy machine; it now watches for half the glide.
- **Phase 22 has 46 checks with no pad plugged in, 47 with one** -- the real pad's reading
  is only checked when there is a pad. Not a failure.

## Phase 36 notes (a new version of a game you had)

Reported from use: The Witcher 3 was reinstalled from a newer build and the launcher showed
it as a new game -- none of the 5 hours, and the copies of its saves made before the
uninstall could not be restored to it. Two causes, both read off the real data first:
the identity key is the install folder, and the new build landed in a new one; and the old
install was GOG's, named "The Witcher 3: Wild Hunt - Game of the Year Edition", while the
new one is a folder game called "The Witcher 3" -- and Phase 30's "copies from an earlier
install" matched names letter for letter. **The saves themselves were never lost**: they
live in Documents, outside the game folder, and the new build reads them as it is.

- **It asks; it never joins two games on its own.** A wrong match would mix two games'
  histories, and a question is one click. The game's page shows a "Played before?" card
  (first, edged in the accent colour) while an earlier install looks like it: which game,
  what it holds, "Carry it over" / "Not the same game". The ... menu has "Same game as an
  earlier install..." -- every earlier install, the likely ones first -- which is the pad's
  way in, and the way to join two the question did not recognise.
- **An earlier install** (`lineage.earlier_installs`) is a record whose game is not
  installed, has not been carried already, and holds something the user did (time,
  sessions, star, mark, note, art, save folders, or copies of saves). Its name comes from
  `known_as` (written by `catalog_io.merge` for every game since this phase, only when it
  changes), else from the copies of its saves, else from its folder.
- **Which ones look like this game** (`lineage.why_same`): `naming.same_title` -- edition
  phrases dropped, a leading "The" dropped, dotted initials joined ("S.T.A.L.K.E.R." is one
  word), then one name must start with all of the other's words, at least two of them; a
  number or roman numeral straight after is a sequel ("Far Cry 3"); spacing and punctuation
  never matter -- or the two share a save folder. **The first version also accepted names
  91% alike, and took "Silent Hill 2" for "Silent Hill f"**; letters that are merely alike
  never count now. A test holds thirteen pairs from this library and its near-misses.
- **Carrying over** (`lineage.carry_over`) moves the history onto the new key: time added,
  sessions merged by start time, the latest "last played", a star kept, name/cover/banner/
  appid/arguments/tool mark/status taken only where the new game has none, two notes both
  kept, save folders joined (one inside the old game folder follows the game, as Phase 30's
  restore does). Nothing about the old *folder* comes across -- a picked exe, the hidden
  flag. The new record gets `earlier_keys`; the old keeps only `first_seen`, `known_as`,
  `carried_to`, `carried_at`, so it is never offered again and Stats never counts it
  twice -- Stats counts installed games only, so the old time was invisible until carried.
  `ui_earlier.carry_flow` takes a `backups.snapshot` first: that is the undo.
- **The restore list** (`save_backup.choices`) now offers an earlier install's copies by
  key (`earlier_keys`) or by `same_title`, never a still-installed game's, and names the
  game each earlier copy was made for. The "Saves copied" pill counts them too.
- **Never a save folder** (`saves.could_be_save_folder`, `rules.SAVES_NEVER_PARTS/WORDS`):
  a crash reporter's queue -- The Witcher 3's REDEngine\ReportQueue held a copy of an
  autosave and was recorded as its saves, and restoring that copy would have queued a stale
  crash report to send -- and telemetry: Firefox's `saved-telemetry-pings` was taken for
  Slow Roads' saves on timing alone. Applied to the walk, to folders recorded before (the
  worker drops them, and the window drops them at startup), to every new copy, and to
  restoring an old copy, which leaves such a folder out. Mozilla joined `SAVES_WALK_SKIP`.
- **On the real library** two more games ask, both correctly: SnowRunner and The Blood of
  Dawnwalker each have an earlier build. The four STALKER 2 installs are all uninstalled,
  so nothing asks for them until one is reinstalled; the menu can join any of them by hand.
- **Found in passing, not fixed here**: play time loses the fraction of a second at every
  3-second poll (`launch.PlaytimeTracker.poll` resets `last_tick` to now after truncating),
  so every timed game reads ~15-20% under its own session list. Raised as its own task.
  **Fixed in Phase 53** (see its notes); the totals stored before it are still low.
- **The backslash trap a fourth time**: a `\n` inside an f-string, patched through a bash
  heredoc, became a real line break. The Edit tool, always, for text with backslashes.

## Phase 35 notes (the redesign, step 5 of 5: Stats, Storage, Settings, and TV mode)

Approved as "loooks great - lets continue". **The last step of the five; the overhaul is
complete.** Anything further is a new request.

- **Stats and Storage keep the library's glow.** `_sync_backdrop` and `_backdrop_follows`
  treat LIBRARY, STATS and STORAGE as one place, so crossing the tabs never changes the
  colour of the room; a game's page still glows in its own. The pages are see-through the
  Phase 32 way: `#Clear` holders, `#StatsScroll`/`#StatsViewport`, and every plain label on
  `#StatsPage`/`#StoragePage` transparent in `ui_backdrop.stylesheet`. Phase 32's and 33's
  "Stats sits on the plain colour" checks were rewritten to assert the glow, since that
  changed on purpose.
- **Stats is cards** (`ui_cards.Card`, the game page's): the four figures are glass
  `StatCard`s with an accent icon (clock, calendar, history, brand) over a display-font
  number; the chart, Most played, Where they came from and the caveats are titled cards.
  Most played gained a `ShareBar` per game -- the session bars' gradient, as a share of
  the most played. The old `chart_label`/`played_label`/... names now point at the cards'
  titles, so the older suites needed no change.
- **Storage**: the drive letter in the display font, the capacity bar and every game's bar
  in the accent-to-violet gradient (stale games keep their colour), game rows as rounded
  glass, the treemap's tiles rounded with gaps, the sort box the library's pill, and **the
  pad's row ringed in white** like the tiles, at TV's ring width.
- **QColor cannot read a stylesheet's `rgba(...)`.** `COLOR_STORAGE_ROW` was first written
  as `rgba(255, 255, 255, 10)`; QColor made it invalid, and invalid paints *black* -- every
  row's empty end rendered as a black slab. It is `#12ffffff` now (#AARRGGBB), and a test
  reads every `QColor(ui_rules.X)` in the source and asserts QColor can parse it. The
  `rgba(...)` constants remain right for stylesheets, which is all they are used in.
- **Storage opened with nothing ringed** -- older than this phase, found by rendering. Giving
  the list the focus makes Qt mark its first selectable row *current without selecting
  it*, and `ensure_focus` then saw a current row and skipped `select_first`. It now picks
  first, focuses second, and selects whatever is current.
- **Settings is rebuilt as sections of rows** (Look and feel, Controller and TV, Finding
  games, Saves, Artwork and the internet, Your library data): a title and a quieter line
  on the left, the control on the right, clicking the words flips the switch. Tick-boxes
  became `ui_cards.ToggleSwitch`, which *is* a QCheckBox, so `isChecked`/`setChecked`/
  `values()` are unchanged and the window needed nothing; `setChecked` snaps, a click
  slides (`SWITCH_MS`), and Reduce animations makes it jump. The sections scroll; the
  dialog is never taller than `SETTINGS_SCREEN_FRACTION` of the screen, its `sizeHint`
  swaps the scroll area's small hint for the body's full height, and whatever the pad
  lands on is scrolled into view (`_follow_focus`, disconnected in `done`).
- **A stylesheet stops rounding a box whose radius is more than half its height.** The
  size drop-downs rendered as plain rectangles until they were given the chip's height --
  the same reason Storage's sort box has a fixed one.
- **The ring only when the keyboard or pad moved there**: `ToggleSwitch` checks the window's
  `WA_KeyboardFocusChange`, as Qt's own buttons do, because a dialog hands its first
  control the focus on opening and a ring nobody asked for reads as a selection. **Windows
  activating a dialog clears that flag**, after `showEvent` -- traced event by event -- so
  in TV mode the dialog puts it back on `ActivationChange` (deferred one tick), and the
  couch sees the first switch ringed. `changeEvent` uses `getattr` because
  `setWindowTitle` sends one before `__init__` has finished.
- **The pad works Settings** -- *once it can reach it: until Phase 52 a real pad could not.
  Start opened the dialog from inside the pad's poll timer (fixed in Phase 49), and the
  open dialog then took the pad's gate away (fixed in Phase 52); the tests below drove
  `_on_pad_action` directly, past both.* In a dialog, A on a button, switch or drop-down sends *Space*
  (Return pressed the default button, so A closed Settings instead of flipping the
  switch); left/right on a drop-down change it in place; A opens its list, and
  `_on_pad_action` now checks for a popup **before** a modal, because that list is a popup
  on top of the modal and it is the one being worked. `_drive_popup` sends to the popup's
  own focus widget -- the list inside a drop-down, not its frame.
- **The hint bar says what the buttons do where you are** (`ui_tv.HINT_SETS`): library,
  a game's page (A is Play there, not Select), Stats, Storage, a dialog, a menu.
  `MainWindow._refresh_hints` runs on every page change and on the app's `focusChanged`,
  so a dialog's opening and closing swaps the set without any dialog knowing; the right-
  click menu sets MENU around its `exec`. `ui_tv.HINTS` still holds the library's set for
  the phase 22/23 checks. Every set fits 1920 at every TV size, and the bar's height never
  changes between sets. The bar itself is glass (`COLOR_HINT_BAR`).
- **Covers are made at the screen's density.** On the 4K TV at 225% every cover was a 1x
  pixmap stretched 2.25 times -- soft. `CoverFactory.ratio` is the window's
  `devicePixelRatioF()`, followed on `showEvent` and `screenChanged`
  (`MainWindow._follow_density`, which clears the cache and repaints); `cover`, `image`
  and `banner` build at device size and tag the ratio, and the game page's finished frames
  do the same. The ratio is part of every cache key. Proven in a second process at
  `QT_SCALE_FACTOR=2.25`: a 150-wide cover is 338 real pixels.
- **A page arriving at 225% now costs ~23.5 ms a frame, up from ~17 ms** in Phase 34's
  measurement -- most likely because Stats now slides in over the glow rather than a flat
  colour. Still inside the 33 ms the Phase 34 test allows; noted so a later rise is seen.
- **Three suites failed once in the full run and passed alone**, none of them touching
  code this phase changed: phase 28's fake game could not take the screen while the user
  was working in Firefox (so its control failed too); phase 34 samples a glide 30 ms after
  a move, which a busy machine can miss; phase 33 still held the old "Stats is plain"
  wording because the edit rewriting it had been refused by a tool error. Re-run a
  failure alone before believing it -- and check an edit actually landed.

## Phase 34 notes (the redesign, step 4 of 5: motion)

Approved as "lets continue". The list is the one promised with the concept before step 1:
a cover that flies into place from its tile, tiles that fade in when the library appears,
tiles that lift smoothly, the glow fading between games (already there since Phase 32),
pages that slide between tabs, and "Reduce animations" turning all of it off.

- **Measured first, at the TV's real scale.** The TV here runs at 225% -- 3840x2160 device
  pixels, drawn in software; `QT_SCALE_FACTOR=2.25` on a 1707x960 window reproduces it on
  the desk monitor. A frame of the real library costs ~24 ms there, and the old page fade
  (a `QGraphicsOpacityEffect` on the page) ~40 ms: 25 frames a second. So **all motion is
  drawn from pictures on overlays**, never by animating real widgets:
  `ui_motion.PageTransition` slides and fades one snapshot of the arriving page over the
  backdrop (~17 ms a frame at 225%, under 1 ms at 100%), and `CoverFlight` repaints only
  the ground a cover covers (~2.5 ms). The tile wave repaints the grid only (~17 ms).
  Phase 34's last test section measures all three in a second process started at 2.25.
- **The snapshot is `render()` with DrawChildren onto a transparent pixmap**, not `grab()`,
  which paints a background under a see-through page (the Phase 32 lesson), and it is
  taken after `settle_layouts` flushes pending LayoutRequests -- a page that has just
  become current is otherwise pictured as it was last laid out.
- **The page overlay is opaque (`WA_OpaquePaintEvent`) and paints the backdrop itself**
  (`Backdrop.paint_onto`), so Qt skips both the real page and the backdrop beneath it.
  It never takes a click: the real page is already current underneath.
- **Which way a page arrives** (`MainWindow._arrival`): Library, Stats and Storage slide by
  tab order; a game's page rises; Back fades in place, so a cover flying home lands on a
  grid that is not moving; the previous and next game slide in from their side
  (`_go(index, arrive)` lets the page already showing arrive again). While a page arrives
  the glow switches at once (`set_view(animate=False)`): a crossfade under a sliding page
  costs a third of a frame again at 225%.
- **The cover flight.** A tile records where it drew its cover (`note_cover`), and only a
  tile being opened -- click, Enter, the pad's A -- leaves a launch rectangle
  (`take_launch_rect`, used once), so the Continue card, Storage and Play something open a
  page with no flight. The page's own cover is `set_in_flight` (keeps its place, draws
  nothing) before the snapshot, so the flight lands in an empty slot. **Back flies it
  home** when both ends are on screen (`cover_on_screen`, and `tile_cover_rect` from the
  same `CoverDelegate.cover_geometry` the tile paints with); the tile leaves its cover
  out (`flying_key`) until it lands. A resize or TV mode lands anything in the air at once.
- **Opening the page that is already showing now does nothing.** The second half of a
  double click re-opened it and cancelled the cover still in flight. Found by a test.
- **Tiles arrive in a wave** (`play_entrance`) on the window's first appearance and when
  the user changes what the grid holds -- a chip, a sort they pick, a switch -- and
  **never on a refresh**: playtime banking reloads the grid every minute while a game
  runs, and a rebuild restores the selection under `_restoring`, so the focused tile does
  not drop and rise again either. A remembered sort put back by `set_sort` does not play it.
- **The wave's clock starts on the first tick after it is asked for.** The window's first
  paint loads every cover from disk and took longer than the whole wave, which had
  finished before the first frame appeared. A tile not yet arrived loads its cover while
  still invisible, so the wave never stalls on a disk read.
- **Every movement a tile makes is one of three eased progress values** --
  `hover_progress`, `focus_progress`, `appear_progress` -- stepped by elapsed time, not by
  ticks, because at 225% a frame can take longer than a tick. Focus now glides
  (`FOCUS_DURATION_MS`) instead of snapping; moved while the grid is out of sight (the
  next game on its page) it simply settles.
- **A `grab()` is not an instant.** A window grab takes ~200 ms, and time-based motion keeps
  going while it paints, so a mid-wave screenshot shows later tiles further along than
  the wave was when it began. Judge motion by its state values; use renders for the look.
- **Run the suites one at a time.** Phase 23 failed four page-switching checks twice, both
  times while another test process had a window open, and passed 73 of 73 three times on
  its own. `run_sandboxed` leaves the real controller on (Phase 22 needs the real pad), so
  pad input can reach whichever test window is in front. Not caused by the motion.
- **A test window opens where the real launcher was last left** -- the sandbox copies the
  real config, `window_geometry` included -- and that can be the TV. At `QT_SCALE_FACTOR`
  2.25 on the TV's own 225% the scales multiply: one run measured at 5.06x. The TV-frame
  measurement now puts its window on the main monitor itself.

## Phase 33 notes (the redesign, step 3 of 5: a game's own page)

Approved as "let's go with step 3", against the concept render shown before step 1. Reported
in the same message: the lit "Library" tab lost the tail of its "y" -- fixed first, in its
own commit, before `before-phase-33` was tagged (see the Phase 31 notes on bold words).

- **The page is see-through, and the window glows in this game's colours behind it.**
  `MainWindow._sync_backdrop` decides the glow for whatever page is showing: the focused
  game on the library, this game on its page, plain behind Stats and Storage (since Phase
  35 they keep the library's glow). It is also
  called from `reload_views`, so a cover just picked reaches the glow.
- **The picture runs edge to edge and its foot is genuinely transparent.** Each frame is
  finished once per size (`ui_hero.Banner._pixmap_for`): shaded, darkened on the left for
  the words, then faded with `DestinationIn`. A fade to a flat colour would leave a seam
  wherever the glow is not that colour; a test reads the bottom row's alpha.
- **Everything scrolls, picture included; Back, Previous and Next float.** They are
  children of the page raised over the scroll area, pinned to the top corners, with a
  `TopFade` that comes in as the page scrolls so passing cards never fight them.
  Previous/Next are labelled pills top right; the picture's dots sit bottom right, level
  with Play -- never two sets of bare arrows (the Phase 11 rule).
- **One Play row**: the card's lit Play pill at a larger size (`[size="large"]`), round
  buttons for the star, the folder and "..." -- which is `ui_actions.build_menu`, the
  grid's right-click menu -- and Playing/Finished/Dropped as one switch. The switch's
  words are one weight lit or not, so nothing needs bold room. The page's old Change
  cover / Change banner / Hide buttons are in that menu; `MainWindow.change_art` and the
  page's `changeArtRequested`/`toggleHiddenRequested` are gone. **Uninstall stays on the
  page**, last in the Details card, still labelled with its tier (Phase 25 holds).
- **Facts, by kind** (`gamedetails.SUMMARY_FACTS` and `PATH_FACTS`): played, last played,
  size and saves copied are pills under the title (plus "Full controller support");
  paths go to a Files card in the wide column, since a path cannot wrap; the rest to
  Details. "Played" is a pill only for games timed here -- a Steam game's time is
  unknown, not zero. **`DetailPage.facts()` answers by label wherever a fact went**, and
  phase 29's test reads it now instead of two grids that no longer exist. "folders" reads
  "Found on disk", the stats page's wording.
- **Cards exist only while they have something to say** -- About, Files, Recent updates,
  Recent sessions (now bars, `ui_cards.SessionBars`), Screenshots. The note card is always
  there and asks for a note when there is none. A test checks all thirty-odd games: each
  card is shown exactly when its content exists.
- **Lined up on one edge.** The cards sit in a column capped at `DETAIL_BODY_MAX_WIDTH`
  and centred; the words over the picture start on the cards' left edge. It is the
  cover's *visible* edge that lines up, not its widget's, which carries room for the
  shadow -- the first render was 16 px off for exactly that reason -- and the Play row's
  foot lines up with the cover's.
- **Screenshots wrap** (`ui_cards.FlowLayout` in the strip): eight thumbnails in one row
  are wider than most windows, and a row that cannot wrap either clips or widens the page.
  The pills wrap the same way in a narrow window.
- **A new game's page starts at its top.** The scroll position used to carry over from
  the previous game, found in the first render, which opened the next page halfway down.
- **The pad**: up and down read down the page, the shoulders a screen at a time; X opens
  the menu under "...", where the mouse opens it; A still plays, left/right still move
  between games, B still goes back.
- **Tests need the real cache, read only.** A sandbox starts with an empty cache, so no
  Steam page had a description, screenshots or updates to show. `box.copy_cache(...)`
  copies chosen parts into the throwaway folder; the real cache is never written.
- Removed as dead: the old `#Play`, `#Stop`, `#Favorite`, status, `#Badge` and
  `#MetaLabel` styles, `Metrics.banner_height`/`detail_margin`, and twelve settings the
  old page alone used. The shared shadow helper moved to `ui_theme.soft_edge`.
- **Never name a dynamic property after a Qt one.** The page's Play was tagged
  `setProperty("size", "large")` for a `[size="large"]` style -- but every widget already
  has a `size` property (its dimensions), so the tag never stuck, the selector never
  matched, and the button quietly wore the card's smaller style. It is `variant` now, and
  a test reads the button's actual font size rather than the tag.
- **Anything measured from the stylesheet is measured after it exists.** The page is
  built before the window applies its stylesheet, so the three marks sized at build time
  came out three different widths once the real font arrived; `_even_segments` now runs
  on every `set_view` -- the same lesson as the switches' bold room, a second time.
- **The backslash trap again**, in a scratch script this time: a Windows path inside a
  Python string inside a bash heredoc. Written with the Write tool instead.

## Phase 32 notes (the redesign, step 2 of 5: the library)

Approved as "yes go with step 2", against the concept render shown before step 1. The
two shelves are gone -- `ui_shelf.py` is deleted, and no `SHELF_*` setting remains.
Recently played became the Continue playing card; Favorites had already become a chip.

- **Which game the card offers** (`ui_continue.pick`): the most recent `last_played`
  (the launcher's own or Steam's manifest) among games that are not hidden, not a demo or
  tool, and **not marked Finished or Dropped** -- "continue" a game you said you were done
  with is the wrong offer. No played game, no card. The card shows the first line of the
  game's note (Phase 27) under the title, since that is usually where you left off. It is
  off the page while searching and on any chip but All games.
- **The card's Play is the game page's Play**: `playRequested`/`stopRequested` go to the
  window's `_play_key`/`_stop_key`, and it becomes Stop while that game runs
  (`LibraryPage.is_running` is the tracker's; `refresh_running_state` updates both).
- **Art on the card is the wide art, else the cover cropped sharp.** The first render
  used `CoverFactory.banner`, whose fallback blurs and darkens a cover into a backdrop
  for the game page; under the card's own scrim that was a near-black smudge.
- **It folds with the shelves' mechanism, kept whole**: two thresholds
  (`CONTINUE_FOLD_AT`/`CONTINUE_RESTORE_AT`), `maximumHeight` driven, the finished handler
  reading current state, the scroll held still while settling. The card is anchored to
  its bottom edge, so folding slides it up and away, and it carries the gap beneath it
  itself -- the page layout has zero spacing, so nothing jumps when it finally hides.
- **The pad**: up from the top row lands on the card's Play (the crossing is detected,
  as the shelves' was); left/right move between Play and Details; A presses; X opens that
  game's menu; down returns to **the tile you came up from**. The grid's selection is
  cleared while on the card, so one ring is on screen. The buttons are `TabFocus`, so a
  mouse click never leaves a ring; their ring is the tiles' focus width, TV's included.
- **The backdrop** (`ui_backdrop.Backdrop`) is the window's central widget. It takes the
  cover the grid already made, shrinks it to 7x4 pixels and stretches it back -- a blur
  for free -- then bakes shading and a vignette into one render per game and window
  size, so a repaint is a blit. It follows the pad and keyboard at once, the mouse only
  after it rests on a tile (`BACKDROP_HOVER_SETTLE_MS`), crossfades, and is **plain on
  every page but the library**, because Stats, Storage and the game page are not built
  to sit on art yet (steps 3 and 5).
- **See-through needs explicit rules.** The blanket `QWidget { background }` paints every
  plain widget, label and frame -- the stack, the chips' holder, the count line, the
  grid. `ui_backdrop.stylesheet` makes exactly those transparent. Measured: a full grid
  repaint is ~5 ms, the whole window ~8 ms, so giving up the opaque grid cost nothing.
- **Tiles**: a cached soft shadow (stacked rounded rects, made once per size) that falls
  further as the tile lifts; a sheen; a hairline edge that brightens on hover; a white
  ring, a lift and an accent glow when focused. *(Flat since Phase 55: no sheen, the shadow
  only when lifted, the hairline and the accent ring outside the cover, hover lit like
  focus.)* The name is one line, left-aligned, with
  a quieter line under it: playtime for a game timed here, the store's name for one that
  is not ("never played" under a Steam game played for years would be a lie). The glow
  reaches past the tile's own cell, so the page repaints the whole view when the
  selection moves -- Qt alone repaints only the two cells and would leave glow behind.
- **Grabbing a see-through widget on its own shows white where it is transparent** --
  `viewport().grab()` of the grid made the names look washed out. Judge renders from the
  window's grab; the tests compare against the backdrop's own pixels.

## Phase 31 notes (the redesign, step 1 of 5: the foundation)

Asked for as "a big ui overhaul" that looks more modern with better animations. Concept
renders of five steps were approved together with "drop the shelves, start with step 1";
**each later step still waits for its own go**. The shelves are still here: they leave in
step 2 together with the Continue playing banner that replaces them, so the library is
never without a way back to recent games.

- **No new dependency for type or icons.** Windows 11 ships Segoe UI Variable and Segoe
  Fluent Icons (Segoe MDL2 Assets on older builds); `ui_icons` takes the first installed
  family from `ui_rules.FONT_*_FAMILIES`. Glyph code points were checked on a rendered
  contact sheet before use, and a test asserts every glyph actually inks pixels -- a wrong
  code point draws an empty box, not an error. Icons carry copies at 1x-3x so a scaled
  screen gets a crisp one.
- **The top bar belongs to `LibraryPage` and is shown by the window above the stack.** That
  kept every old name alive -- `filter_box` is now the search box, `stats_button` and
  `storage_button` are the Stats and Storage tabs, `rescan_button`, `surprise_button`,
  `settings_button` are the round icon buttons -- so the 22-30 suites and every pad path
  needed no change there. It hides on a game's page (the banner's Back is the way out),
  and the old header rows of Stats and Storage are hidden because the bar now says which
  page you are on. The pad's left/right still crosses Stats and Storage; the bar follows.
- **Search from anywhere.** Ctrl+F (`QKeySequence.Find`) goes to the library and focuses
  the box; typing into it while on Stats or Storage goes to the library too. The
  placeholder counts the games ("Search 21 games").
- **Chips replace the view choices**: All games, Favorites, Playing, Finished, Dropped,
  each with its count, remembered as `library_filter` in config.json (its own key only,
  per the Phase 26 rule); an unknown value falls back to All. "Demos & tools" and
  "Hidden" became toggle chips but are still checkable buttons with the old names, so
  `setChecked` works as it did for the tick-boxes.
- **A chosen chip is bold, and bold is wider.** The first render clipped the chosen chip's
  count. Each chip's minimum width is measured with a DemiBold copy of its font.
  **The same trap was left in six other places and reported from use** -- the lit
  "Library" tab lost the tail of its "y". Qt measures a button with the font it has;
  `:checked { font-weight }` only changes the font it is *painted* with. Every button
  whose words turn bold when on now goes through `ui_theme.reserve_bold_width`, called
  after the stylesheet exists (so from `refresh`, not `_build`) and whenever the words
  change, and `phase31_tests.bold_short` checks all of them at 100% and in TV mode.
- **Messages are a card, but the status bar still does the work.** About twenty call sites
  and the Phase 14 queue all post to `statusBar()`. It is now kept hidden and its
  `messageChanged` drives `Toast`: a message slides in bottom-right, an empty one or
  "Ready" sends the card away. Nothing that posts a message had to change. The card takes
  no clicks (`WA_TransparentForMouseEvents`), appears without motion under Reduce
  animations, and in TV mode sits above the button-hint bar.
- **A short message wrapped onto two lines** in the first render, because a word-wrapped
  QLabel inside a card has no width of its own to insist on. The text's minimum width is
  set to its natural width, capped at the card's room.
- **A PySide6 enum member is always truthy.** `if animation.state():` is true when the
  animation is stopped too; compare against `QAbstractAnimation.State.Stopped`.
- **Test harness trap, and the most expensive one this phase: in Qt 6, `app.quit()`
  closes every window before it stops the loop.** Tests that waited with
  `QTimer.singleShot(ms, app.quit); app.exec()` were quietly closing the window under test
  and then measuring a closed one -- six false failures here, and it is the same on the
  code before this phase, so it is the harness, not the launcher. Wait with a local
  `QEventLoop` quit by the timer instead; phase 27's section 8 was changed the same way.
  A shortcut test also needs the window really in front, which on this machine means
  `focus.bring_to_front` (Phase 28), not `activateWindow`.
- **Three older checks were about the old layout, not about behaviour, and were
  rewritten**: phase 23's header alignment now holds "when the header is shown"; phase 27
  scrolls each marked tile into view before grabbing it (the top bar and chips pushed some
  below the fold); phase 29 clears `save_dirs_checked` in its sandbox copy first, because
  the user's real launcher had already done its first saves search and the copy said so.

## Phase 30 notes (putting a copy of the saves back)

- **Everything that can destroy lives in `save_backup.restore`, in this order**, stopping at
  the first failure: every path in the zip is checked to land inside its folder (a
  climbing entry refuses the whole restore, untouched); the saves there now are copied,
  like any backup, and a failed copy changes nothing; each folder there now goes to the
  **Recycle Bin**, never deleted; the copy is unpacked with the files' own dates, because
  some games pick the newest save by date. The UI only asks, and refuses while the game
  runs -- the window holds the tracker.
- **`removal.send_to_recycle_bin(already_asked=True)`** adds `FOF_NOCONFIRMATION` alone,
  since the launcher has just asked the same question. The uninstall path's flags are
  unchanged -- a test asserts both values off a captured `SHFileOperation` call.
- **Copies from an earlier install are offered**, marked as such: same game name, different
  key. A new repack version lands in a new versioned folder, and without this the copy made
  when the old one was uninstalled could never come back. **A save folder that lived inside
  the old game folder follows the game** into the new one (`save_backup.targets`), or
  restoring CULTIC would recreate the old, deleted folder.
- Reached from the right-click menu, "Restore saves...", so it works from the pad too.
  `_drive_dialog` now sends up/down as arrow keys when a list has the focus -- before, they
  were Tab and jumped straight past the list. The settings restore dialog gains it too.
- The confirmation follows the uninstall rule: Cancel is default, escape and focus.
- Tests redirect the Recycle Bin into a folder of their own; the real shell call is only
  ever inspected, never made.

## Phase 29 notes (saves: where each game keeps them, and copies of them)

- **Read off the disk before a line was written.** The ~90 recorded sessions were matched
  against the names and dates of every file in the save locations (read only, never
  contents). Unreal games save under LocalAppData as `<project>\Saved\SaveGames`, often
  under an *internal* project name ("Ride" for RV There Yet, "Ravage" for Halloween,
  "Dinner" holds LEGO Batman's config); the repacks' Steam emulators keep saves in
  Roaming (`GSE Saves\<appid>`, `Goldberg SteamEmu Saves\<appid>`) and in Public
  Documents (`Steam\RUNE\<appid>`); Cyberpunk and The Last of Us use Saved Games; and
  **CULTIC keeps its saves inside its own game folder** -- the case where Remove from disk
  would have binned them. The same match also turned up how much else is written during
  play: shader caches, browsers, the Claude app, WhatsApp, WeMod, Office.
- **So a folder must look like a save *and* be this game's.** Shape: a path component
  containing "save" but not Unreal's bare "Saved"; the `<appid>\remote` cloud layout;
  anything in Saved Games; a file ending .sav/.save or *starting* with "save". Ownership:
  inside the game's folder, carries its Steam appid, names the game -- or, failing all
  three, at least `SAVES_OWNED_MIN_WRITES` writes during its sessions making up
  `SAVES_OWNED_FRACTION` of the writes since it was first played.
- **The first version made four mistakes on the real disk, each now a test**: it took an
  emulator's *whole* folder (every game's saves) for whichever game was running -- a
  save word followed by an appid now stops at the appid, and a folder holding appid
  folders is never one game's; one stray write made Spider-Man 2 claim The Last of Us'
  folder -- a folder naming another known game is never this one's, and timing alone
  needs two writes; Stalker 2's dated backup folders read as four places -- siblings fold
  into their parent; and "contains save" took a controller-settings file -- now "starts
  with". Emulator words (goldberg, gse, rune, codex, p2p) are ignored in name matching:
  "gospodars.tales-goldberg" otherwise named the Goldberg emulator's folder.
- **About two seconds** for ~127,000 files. `SAVES_WALK_SKIP` prunes the big noise
  folders (Packages, NVIDIA, Google, ...) for speed only; the rules decide what counts.
  Known folders come from `SHGetKnownFolderPath`, never from paths under the profile.
- **When it runs**: once per game, `SAVES_STARTUP_DELAY_MS` after the window appears
  (after the startup scan, so the two walks never compete); after every session, with the
  session just ended added as a window because one under a minute is not in the history;
  never while a game started from here is running; and synchronously before any
  uninstall. The worker never writes overrides.json -- `MainWindow.record_saves` does.
  Folders found before are kept while they exist, since a quiet session must not forget
  one. Closing waits up to 30 s for a zip in progress.
- **Copies** are zips in `save_backups\<name> - <hash of key>\`, one per backup, written to
  a temporary name and renamed into place; `manifest.json` records each folder's origin
  and a fingerprint (`walk.fingerprint`) so an unchanged set is skipped; the newest
  `SAVES_BACKUP_KEEP` are kept; a folder over `SAVES_BACKUP_MAX_BYTES` is left out and
  reported. `save_backups/` is git-ignored and not part of export bundles.
- **Uninstalling copies the saves first, for every tier of an exe game, and a copy that
  fails stops the uninstall** before the question is even asked. The question says
  whether the saves were inside the folder or safely outside it.
- **Not covered, and said so**: Steam, Epic and Xbox games (never timed -- and their
  clients keep cloud saves); and a game only ever started from its own shortcut, since
  the search needs sessions to match writes against. Restoring a copy is Phase 30.
- **Process lesson**: patching code through Python strings in a bash heredoc mangled
  backslashes three times this phase (`\335` became an octal escape, a `\n` became a real
  newline mid f-string). Edit files with the Edit tool when the text has backslashes.

## Phase 28 notes (coming back to the front after a game)

- **Measured first: this machine's foreground lock never expires.**
  `SPI_GETFOREGROUNDLOCKTIMEOUT` reads 2147483647 ms, so Windows never lets a background
  program take the foreground, and Qt's `raise_()` + `activateWindow()` only ever flashed
  the taskbar. A probe window proved it: the polite request lost; attaching our input to
  the foreground window's thread for the moment of `SetForegroundWindow` won. That is
  `focus.bring_to_front`. It fakes no key press (the other common trick taps Alt).
- **When it is used**: after a game started from here closes and no other one is running.
  In TV mode, always -- on a couch a flashing taskbar is a dead end. At a desk only when
  `focus.foreground_is_empty()`: the bare desktop (`Progman`, which is `GetShellWindow()`
  and hosts `SHELLDLL_DefView` here), a taskbar (`Shell_TrayWnd`, and one
  `Shell_SecondaryTrayWnd` per extra screen -- this machine has two), or nothing. A window
  the user moved to while the game ran is never taken from them. Everything else still
  gets the polite request. A minimised window is restored into its mode first.
- **Never attach to a thread that is not answering.** The test found a deadlock: a helper
  attached to a window whose owner was blocked waiting for that helper, and both stopped.
  `focus._responsive` sends `WM_NULL` with `SendMessageTimeout` (250 ms) before attaching;
  `IsHungAppWindow` alone only notices after five seconds of silence.
- **Testing focus has two traps, both hit.** Moving focus from inside the launcher's own
  process leaves Windows treating the launcher as entitled to the foreground, and the
  control then "passed" for the old way too -- the test's own moves now come from a
  separate process. And that process must not be waited on with the GUI thread blocked,
  or it is the deadlock above. Windows also refuses to hand the foreground to the desktop
  on request, so the desktop and taskbar classification is checked against their real
  handles instead of a staged foreground.
- **Proven end to end**: a real process started through `ui_actions.play` (the job object
  and all), taking the screen, focus moved elsewhere by another process, the game quitting
  -- with only the polite request the launcher stays behind (the control), with
  `bring_to_front` it comes back.
- **Not covered, and said so**: Steam, Epic and Xbox games. They run under their own
  client, the launcher never learns when they end, and so nothing brings it back after
  them. A pad button to summon the launcher would, but Steam claims the PS button when it
  is running; not built, not approved.

## Phase 27 notes (where you are with a game, a note -- and menus the pad can work)

- **Status and note live in overrides** (`rules.STATUS_KEY`, `rules.NOTES_KEY`), kept like
  playtime and artwork: through an uninstall, and back if the game returns to the same
  folder. A repack reinstalled under a new versioned folder name starts fresh -- the same
  limit every override has, not a new one. `GameView.status` reads anything outside
  `rules.STATUSES` as unset; notes are capped at `NOTES_MAX_CHARS` and shown with
  `Qt.TextFormat.PlainText`, because a QLabel would otherwise render `<b>` in a note.
- **On the page, three toggles on their own row** (pressing the lit one clears it) and the
  note as a quote beneath, edited through a plain-text `QInputDialog`. Each toggle carries
  a `status` property so `ui_theme` can colour its `:checked` state -- a single
  `#Status:checked` rule could only give all three one colour.
- **On the tile, a glyph on the star's dark disc, bottom-right** -- triangle, tick, cross,
  drawn as paths rather than characters. Magnified on grid and shelf before shipping.
- **Play something**: dropped is excluded from `pick.eligible`; finished is weighted by
  `PICK_FINISHED_FACTOR` (0.5). Proven: 400 rolls, never the dropped game.
- **The pad could not work a menu at all (half fixed here, finished in Phase 49).** X opened the right-click menu, and
  every later press went to the *grid* by `sendEvent`, so the stick moved tiles behind a
  menu nothing could steer or close. `_on_pad_action` now checks
  `QApplication.activePopupWidget()` right after the modal check and sends Qt's own menu
  keys to it (`POPUP_KEYS`). This is also what makes the mark reachable from the couch:
  the page's toggles are not on any pad path, the menu's "Mark as" submenu is. The test
  walks down, opens the submenu with right, picks with A, and checks the grid never moved.
- **Found by rendering: the page's button row had been cut short since Phase 25.**
  Measured, per button, width against size hint. The column's cap scales with the
  interface, but button padding and fonts have floors, so at TV mode's 85% the row needed
  770 px of a 748 px column ("Play" became "Pla"), and a Steam game's row needs 915 px
  even at 100% against an 880 px cap -- "Uninstall through Steam..." was clipped in the
  ordinary window too. The row's own size hint is now the column's floor. Three Qt traps
  on the way, each caught by a test rather than by eye:
  - a nested layout keeps its size hint until the next pass, so `invalidate()` it before
    asking;
  - that `invalidate()` also nulls the row's geometry, and nothing lays it out again until
    a later full pass -- the row sat at 0x0 with the button at its old width -- so the
    column's layout is `invalidate()`d and `activate()`d straight after;
  - raising a maximum does not resize anything; raising the **minimum** does, at once.
  A window too narrow for the row now scrolls sideways instead of clipping labels.
- **A never-shown window renders stale layouts.** The TV render first showed the facts
  drawn over each other: `deleteLater()` needs a running event loop, and `processEvents()`
  from a script does not run deferred deletes. Render a page that matters with the window
  shown and `app.exec()` running briefly; the button checks do exactly that.
- **Tests that drive a menu must wait for it, not for a clock.** The first version pressed
  on fixed timers, passed, then missed a press on a slower run. `run_chain` runs each step
  after the last and retries a step until the menu it needs is open.
- `test_sandbox.py` and `run_sandboxed.py` exist so no test here writes real data again;
  all 388 checks across Phases 22-27 ran through them.

## Phase 26 notes (the small fixes: choices that stick, new games that stand out, a log)

Three items the user picked from a suggestions list and approved together, so built as one
phase. The rest of that list -- save protection, TV mode coming back to the front, notes
and a finished mark -- was approved afterwards and is Phases 27 onwards. **The Silent Hill
"6 seconds of play" was not a bug**: the user stopped both games himself while
benchmarking them. Do not chase it.

- **The grid's sort was never saved at all.** `sort_box` had no writer, while the Storage
  page's sort already was saved (`storage_sort`). `library_sort` now sits beside it in
  config.json. `LibraryPage.set_sort` restores it with signals blocked, so putting a choice
  back is not mistaken for making one; `sortChanged` fires only for a real change.
- **Fixed in passing: saving the storage sort could turn the normal shortcut into TV
  mode.** `set_storage_sort` called `save_config(self.config)` -- the whole in-memory dict,
  which carries `tv_mode` exactly as `set_tv_mode` left it. Start from the TV shortcut,
  change the storage sort, and `"tv_mode": true` was persisted for the plain shortcut too.
  Every UI-state write now passes only its own key. **Never save `self.config` wholesale.**
- **Window size and place** are Qt's `saveGeometry` blob, base64, in `window_geometry`. Qt's
  form rather than four numbers because it carries the maximised state, and
  `restoreGeometry` pulls a window left on a detached screen (the TV, unplugged) back onto
  an attached one -- tested at -7000,-7000. Restored before the first show so nothing
  jumps; saved only if the window was really on screen (`_shown`), so tests and aborted
  starts never overwrite it; **never TV mode's fullscreen** -- `set_tv_mode(True)` keeps
  the normal geometry aside and closing from TV mode saves that. An unchanged value is not
  rewritten, which keeps backups quiet. It describes this machine, so
  `rules.TRANSFER_LOCAL_KEYS` keeps it out of exports and imports; the sort does travel.
- **The NEW tag** is `rules.NEW_KEY` in overrides, written by `catalog_io.merge` in the same
  breath as `first_seen` -- so a game the launcher already knew (reinstalled into the same
  folder, back on a replugged drive) never comes back as new -- and **never on a first
  look at a library**, when no record had `first_seen`: tagging everything says nothing.
  It clears when the page is opened (`show_detail` -> `mark_seen`) or on a successful
  start (`ui_actions.play`, normal and elevated; a failed start leaves it). `is_new` also
  lapses after `NEW_BADGE_DAYS`, and once `last_played` -- which includes Steam's own
  manifest LastPlayed -- is later than `first_seen`. Merge deletes a lapsed flag so it does
  not linger. On the day it shipped no game carried the tag; only later arrivals do.
- **The badge** is a solid accent pill, top-left opposite the star, sized from the cover
  width with the font in *pixels* from the pill's height, so one set of fractions holds
  on the grid, the shelves (0.52) and TV. It saves and restores the painter: the tile name
  drawn next copies `painter.font()`, and a leaked bold pixel-size font would have changed
  every title. Checked by rendering at 1.0, TV 0.85 and TV 1.6, magnified on a shelf, and
  by diffing one tile with and without the tag (809 badge-coloured pixels against 0).
- **A scan names what arrived** -- "New game: X", "4 new games: A, B, C and 1 more" -- from
  the keys that had no `first_seen` before the merge; hidden games and demos/tools are not
  named. **A scan that found exactly what is showing no longer rebuilds the grid**
  (compared as JSON: a loaded entry holds lists where a fresh one holds tuples), because a
  scan the folder watch asks for can land while someone is reading a game's page.
- **`folder_watch.py`**: `QFileSystemWatcher` on each root, top level only -- a game
  writing its log inside its own folder must trigger nothing. A new folder or loose `.exe`
  is measured off the GUI thread every `WATCH_SETTLE_POLL_MS` and reported after
  `WATCH_SETTLE_CHECKS` unchanged measurements, followed up for `WATCH_FOLLOW_UP_S`
  because installers pause, and given up on after `WATCH_GIVE_UP_S`. Removals are reported
  at once; archives and other loose files are never waited on. The window runs the scan
  as `start_scan(background=True)`: silent unless the library changed, **never while a
  game started from here is running** (it waits for the game to close), and after any
  scan already under way. `_scan_thread_done` calls `wait()` first: `finished()` arrives a
  hair before `isRunning()` turns false, and the queued scan would be refused as "already
  running". Settings: "While open", `watch_folders`, on by default.
- **Measured, not assumed: the directory listing lags a file still being written.** A file
  held open with 4,000,000 bytes written read as **0 bytes** through `os.scandir`'s entry
  and 4,000,000 through `os.stat`. So `walk.fingerprint` stats every file: all of C:\games
  (19,619 files, 570 GB) takes about 1.9 s, one new game a fraction of that.
- **Known gap:** installing into a folder that already existed (made empty earlier) is not
  noticed while open -- nothing new appears at the top level. The startup scan finds it.
- **`launcher.log`** sits beside the data, rotating at 1 MB with two old copies, for GUI
  runs only: `--make-shortcuts` and `--uninstall` get none, since an uninstall must not
  hold a file open inside the folder it deletes. `install_crash_logging` routes
  `sys.excepthook` and `threading.excepthook` there. **Verified: under `app.exec()`,
  PySide6 6.11 sends a slot's exception to `sys.excepthook` and the loop keeps running;
  `processEvents()` called from Python re-raises it into the caller instead** -- a harness
  property that broke the first version of the test, not a launcher one. The SteamGridDB
  key is checked absent from every rotated file.
- **Every test in this phase ran against a copy of the data.** `phase26_tests.py` points
  `paths.data_dir` at a throwaway folder before importing any project module (the module
  level paths bind at import) and compares the three real files byte for byte at the end.
  The older suites (22-25) write real data by design; this time they were run through a
  few lines of `runpy` that patch `paths.data_dir` the same way first, and all 266 checks
  passed. Do that for future regression runs -- the user's launcher is usually open while
  tests run, and it holds its own copy of overrides.json in memory.
- **The restore point moved.** `before-phase-26` now points at "Play data before phase 26"
  (a3f35b8), one commit past the Omarchy notes; it used to point at the Phase 25 commit.

## Phase 25 notes (uninstalling, and the only code here that destroys anything)

**One tier deletes, and it is folder-scanner games only.** Everything else on this machine
belongs to somebody else, and the button says so rather than pretending. Per source, as
shipped and as verified here:

| source | tier | why |
|--------|------|-----|
| folders, uninstaller at the root | run it | the game shipped one; it knows what it installed |
| folders, no uninstaller | **Recycle Bin** | ours to remove, and recoverable |
| gog | run its uninstaller | GOG records a real `uninstallCommand` per game |
| steam | `steam://uninstall/<appid>` | Steam's own confirm flow |
| epic, ubisoft | open the client | no verified programmatic uninstall exists |
| xbox | `ms-settings:appsfeatures` | same, and this is the documented Windows page |

- **The Steam URI was verified off this machine, not from documentation.** Every installed
  Steam game's `UninstallString` in `HKLM\...\Uninstall` is literally
  `steam.exe steam://uninstall/<appid>`. That is Steam itself declaring the mechanism.
  Every other scheme used here (`com.epicgames.launcher`, `uplay`, `ms-settings`) was read
  out of HKCR before it was used; **`ms-settings` is registered by the
  `windows.immersivecontrolpanel` package**, so it is absent from a naive
  `\shell\open\command` probe and present in reality -- the first probe reported it missing
  and was wrong.
- **GOG's `uninstallCommand` exists and points at a real Inno Setup uninstaller** here, so
  GOG gets the uninstaller tier rather than the "open Galaxy" fallback. The value is read
  and the file checked before the button offers it.
- **Only the folder *root* is searched for an uninstaller**, per the brief. Three games on
  this machine keep theirs one level down (`Uninstall\unins000.exe`, `_UnInstall\...`) and
  therefore get the Recycle Bin route, which is safe for them. The Windows uninstall
  registry does know where those live, and matching by DisplayName would find them -- but
  that matching is fuzzy, and running the wrong uninstaller is not recoverable. **Left
  alone deliberately; worth raising before anyone "improves" it.**
- **Four safety rules live in `removal.py`, not in the UI**, so no future caller can skip
  them, and each has a test: the deleting tier is folder-source only; the folder must be
  *inside* a scan root; it must not *be* a scan root (a loose exe in `C:\games` produces an
  entry whose install_dir is the root, and deleting that would take everything); and a
  running game refuses, because its files are open.
- **`FOF_ALLOWUNDO` and nothing else.** No `rmtree`, no `os.remove`, `shutil` is not even
  imported. The shell's own progress dialog and its "too large for the Recycle Bin" prompt
  are wanted, so no silencing flags are set in the app; `interactive=False` exists **only**
  so tests never block on a dialog nobody is there to click. Proven by sending a fabricated
  folder to the bin and counting the bin before and after with `SHQueryRecycleBin`: 1 item
  gained, byte-for-byte the size planted.
- **Cancel is the default button, the Escape button, and the focused button.** All three,
  not one: `setDefaultButton` decides Return, `setEscapeButton` decides Escape, and the
  focus decides what a pad's A does the instant the dialog opens.
- **The button's label is the tier's own wording** on all three surfaces -- "Remove from
  disk...", "Uninstall through Steam...", "Open Windows installed apps...". A flat
  "Uninstall" on an Xbox game would be a promise the launcher cannot keep.
- **Two test traps worth remembering.** A storage row's context signal reaches the window's
  real handler, and `QMenu.exec` blocks forever with nothing to dismiss it -- disconnect
  first. And grepping `removal.py` for "rmtree" matches its own docstring, which names the
  things it promises not to do; strip comments and strings with `tokenize` first, or better,
  assert the flags the shell actually receives.
- **The test broke the data rule once and was fixed.** Section 9 starts a real process
  under a real game's key to prove a running game refuses, which banks playtime against it.
  The subject is now chosen as a folder game with *no* customisation, its record is
  deep-copied before anything runs and restored in the `finally`, and the final check
  asserts record equality rather than an unchanged mtime -- asserting the file was never
  written would be asserting the launcher failed to do its job.

## Phase 24 notes (the storage page)

**Every pad button was already taken**, so Storage got none. A select, B back, X menu,
Y play something, the shoulders page, View stats, Start settings -- that is the whole
pad. Stats and Storage are therefore two tabs of one place, left and right cross between
them, and the tabs are drawn on screen so that is visible rather than a secret. That is
also why `ui_pageshell.py` exists: both pages share the capped centre column and the
header, and the shared `centred()` replaced a copy of itself in `ui_stats`.

- **One list, two item shapes.** A drive header is an item with `NoItemFlags`, so Qt's
  arrow navigation steps straight over it and up/down walks the games alone -- wrapping,
  paging and scrolling into view for free. Two lists would have meant re-solving the
  focus-crossing problem Phase 17 solved for the shelves, for nothing.
- **Sizes come from the catalogue, free space is read live.** Walking a terabyte on every
  page open is not an option, so the page says in its footnote that sizes are as of the
  last scan. Free space is the one figure that would actually mislead someone deciding
  what to delete, so it is never cached.
- **Bars are scaled per drive, not per library.** A drive holding one 40 GB game shows it
  full width; scaling every drive against a 142 GB game on another one would make a whole
  disk look empty.
- **A drive Windows will not measure still lists its games**, says so in words, and draws
  no capacity bar -- and gets a shorter header, because reserving the bar's height left a
  conspicuous empty band under it. Found by rendering three fabricated drives.
- **The treemap shipped, and it nearly did not.** The first squarified implementation laid
  13 of 21 games out as unlabelable stripes, which looked like proof that the data was too
  skewed for a treemap. It was a bug in the algorithm, not the data: **`side` must be fixed
  for the length of a row**, and a row must be laid along the *shorter* side of what is
  left. Corrected, the same library gives 19 of 21 labelled and a worst aspect of 3.5:1.
  The lesson is the general one -- do not conclude a design fails until the implementation
  is right.
- **The map is mouse-only and hidden in TV mode.** It holds no focus and has no pad path;
  the ranked list is the required baseline and the only pad route, so on a screen driven
  from a couch the map would only be taking room from the thing that works there.
- **On this machine the reclaim strip is empty and will be for months.** The launcher has
  known these games for 0-3 days, so nothing meets `rules.RECLAIM_STALE_DAYS`. That was
  reported rather than papered over, and the empty state says what fills it. A game never
  played is aged from `first_seen`, which is the only honest clock available -- nothing
  here knows when a game was installed.
- **Every game on this machine is on C:.** The drive grouping is therefore exercised
  against fabricated drives in the tests and in the renders, and is unverified against a
  real second drive holding real games.
- A test pinned to `stack.count() == 3` broke the moment a fourth page arrived. It now
  asserts the stats page sits at the index the window routes to, which is the property
  that matters. Same lesson as the hardcoded game counts.

## Phase 23 notes (the stats page)

**The whole page was designed against one session of one minute**, because that is what
the library actually held on the day it was built -- Phase 20 had shipped hours earlier.
That is harsher than the brief's "three sessions" worst case and it is also the state
every new install starts in, so it was the case designed for first and the busy case was
checked second.

- **Two records of time that disagree, on purpose.** `playtime_seconds` goes back to the
  first use of the launcher; per-session history only exists from the day Phase 20
  shipped. So the lifetime card reads 55 min while "this week" reads 1 min, and the page
  *says so* -- `stats.recording_since` is the earliest session anywhere, and the caveat
  block names the date. Leaving that gap unexplained was the alternative and it reads as
  a fault.
- **A month nobody recorded is drawn differently from a month you were quiet in.** An
  unrecorded month gets a faint full-height wash, a recorded-but-empty month gets a
  baseline stub. Rendering them the same would state something false. Three weights were
  drawn and compared at 8x: the faintest that still reads (`COLOR_CHART_UNRECORDED`)
  won, and "no wash at all" was rejected on honesty, not on looks.
- **The peak is always labelled**, which is what makes a lone full-height bar for one
  minute honest rather than alarming.
- **`STATS_MIN_BAR_PX` exists because 2 minutes against a 40-hour peak rounds to zero
  pixels.** "I played and it vanished" is the worst answer the page could give. A test
  measures the actual painted column rather than trusting the arithmetic.
- **The caveats are generated from the library, not written as fixed text** -- "8 of your
  21 games are started through Steam, Epic or Xbox" rather than a general disclaimer. An
  absence nobody explains reads as a bug; an absence stated in numbers reads as a policy.
- **Which entries count is decided once, in `stats.gather`, and the two rules differ.**
  Time counts from *everything*, because hiding a game does not unplay it; counts and
  disk size use the visible library, so they agree with the "21 of 26 games" line under
  the grid. Most played is exe-only -- ranking Steam games that all read zero against
  timed ones would be a list of lies.
- **`deleteLater()` does not clear a layout.** The widget survives until the event loop
  next runs, so reopening the page after playing anything painted the old rows
  underneath the new ones -- visible only in a screenshot. `_clear` calls `setParent(None)`
  first. Anything else that rebuilds a layout in place needs the same.
- **`humanize.playtime(0)` is "never played"**, which is right on a tile for one game and
  wrong as the value of "Played this week". `ui_stats._span` answers "none" instead.
- **A capped, centred column, and the header inside it.** Uncapped, a 2560px window put
  a game's playtime a thousand pixels from its name. The header had to move into the same
  column too -- left-aligned against centred content it read as a different page. Both
  are wrapped by `_centred`, which weights the content 100 against the margins' 1: equal
  stretches hand it a third of the window and no more, which collapsed the content to
  654px the first time.
- **The pad's Stats button is SDL's `CONTROLLER_BUTTON_BACK`** -- View on an Xbox pad,
  Create on a DualSense, and not a "back" button on any pad made this decade. Probed on
  the real DualSense before it was used: button 4, distinct from START.
- **The eighth hint did not fit.** Eight separate chips needed 2007px at `tv_scale` 1.6,
  wider than a 1080p screen. The two shoulder hints were merged into one `LB·RB / L1·R1 —
  Page` chip, which buys back more than Stats costs; a test now asserts every scale in
  `TV_SCALE_CHOICES` fits 1920.
- Nothing is cached: `show_stats` recomputes on the way in. It is one pass over a few
  dozen records, and a cached copy would be stale the moment a session ended behind it.

## Phase 22 notes (the controller's battery)

**SDL exposes the battery on the joystick, not on the controller.** The project polls
through `pygame._sdl2.controller.Controller`, which has **no** `get_power_level` at all,
while the plain `pygame.joystick.Joystick` for the same physical device does. So
`ControllerHub` keeps `_device_index`, mapping a controller's instance id to the joystick
index it was opened from, and reads the level from there. Established by probing the real
pad before any feature code was written, exactly like every other phase.

- **This machine's DualSense reports `wired`, not a percentage**, over USB. SDL only gives
  five coarse buckets (`empty`/`low`/`medium`/`full`/`max`) and a wired pad has none of
  them. That is a real answer, not a failure, and the tests report whatever the hardware
  says rather than demanding a charge level -- a suite that insisted on one would fail on
  a plugged-in pad, which is the state this machine is usually in.
- **Three outcomes, and only one of them is a battery.** A level draws a battery; `wired`
  draws a plug; anything else draws nothing and takes up no space. Showing nothing for a
  wired pad was the other candidate and was rejected by rendering: the user's pad is wired,
  so the whole feature would have looked broken on the day it shipped.
- **A plug, not a charging bolt, and that was decided by magnifying both.** At the smallest
  TV scale the glyph box is 23x12 px; a bolt at that size is an unreadable blob, while the
  plug's two prongs and body still read. Same method as every other UI call here.
- **A plug never uses the warning colour.** Amber below `rules.POWER_WARNING_BELOW` means
  "charge this"; a cable is not a low battery, and a test asserts the warning colour is
  absent from the plug's pixels.
- **The bar must be exactly as tall with the glyph as without it**, or the hints jump the
  moment a pad is plugged in. Measured across all seven states at both ends of
  `TV_SCALE_CHOICES`: one height each time (36 px and 90 px), only the width grows.
- **Polled once a minute** (`rules.CONTROLLER_POWER_POLL_MS`), which is the opposite end of
  the scale from the 60 Hz input poll -- a battery does not move fast, and this is an extra
  SDL call. Also refreshed on a pad change, on an active-pad change, and **when TV mode is
  switched on**, since the bar becomes visible at that instant and a minute-stale reading
  would be showing at exactly the wrong moment.
- `powerChanged` only fires when the level actually changes, so a wired pad emits once at
  startup and then stays quiet.

## Phase 21 notes (stopping a running game)

`PlaytimeTracker.stop` terminates the **job**, not the process, so the whole tree goes at
once -- shim, game, children. Killing only what we started would leave the real game
running with nothing watching it, which is the same reason the job exists at all.

- **The control exists only while that game is up.** Play becomes Stop on the detail page,
  and the right-click menu offers Stop *instead of* Play for the running game and Play for
  every other. One button rather than two: a disabled Stop would take space on every page
  for the sake of the few minutes a game is running.
- **`setObjectName` alone does not restyle a live widget.** The button kept Play's green
  until `unpolish`/`polish` were called on it -- the same class of trap as
  `QMenu::item:disabled` and `#Favorite:checked`, found the same way.
- **URI and elevated launches get it by construction, not by a check.** Neither is ever in
  the tracker: a URI launch returns no handle, and an elevated one comes back from
  ShellExecute with nothing to follow. `is_running` is therefore False for both.
- **A modal dialog now takes the pad.** `_on_pad_action` checks `activeModalWidget` first
  and translates A/B/left/right into Return/Escape/Tab, or the confirmation would be
  unanswerable in TV mode while the buttons behind it kept responding.
- **Stopping does not wait for the next poll**: `_poll_playtime` is called immediately, so
  playtime is banked, the session is finalised and the button reverts within the same
  click rather than up to three seconds later.
- **Honest limitation:** a game that has hung *fullscreen* may still need an alt-tab before
  the launcher can be reached at all, because pad input is deliberately ignored unless the
  launcher is the active window (Phase 7). Stop helps once you are back in the launcher; it
  is not a rescue from a window you cannot leave.

## Phase 20 notes (session history)

A session is one exe launch, from start until the Job Object reports itself empty. Stored
per game in overrides.json as `[{"start": iso, "minutes": n}, ...]`.

- **The live session is written into the list as it runs**, on the same banking cadence as
  playtime and in the same `overrides.update` call, so a crash costs at most one interval
  of it rather than the whole evening. Nothing is written when no whole second has
  accrued -- there is nothing to record then, and the poll fires far more often than time
  passes in a test.
- **A test caught a duplication bug that would have shown up as a mess.** Entries are
  matched by start time so the live one can be rewritten in place, but they are *stored*
  with `timespec="seconds"` -- so the in-memory start, which still had microseconds, never
  matched the one read back, and every banking pass appended a new entry instead of
  updating the last. `sessions.at_second` normalises at both ends.
- **Pruned by age (`rules.SESSION_KEEP_DAYS`, 400), never by count**, so one mechanism
  serves both the short list on a game's page and a twelve-month chart later. Fifty
  sessions in one day are all kept.
- **URI games never have sessions**, because they are never timed -- the block simply does
  not exist for them, exactly like playtime.
- A session under `rules.SESSION_MIN_MINUTES` is not recorded at all: a game that failed to
  start would otherwise fill the list with one-line entries nobody wants to read.

## Phase 19 notes (recent updates)

The sixth endpoint, and **the only one on a different host**: `api.steampowered.com`
rather than `store.steampowered.com`. Everything below was established by probing the live
feed before any feature code was written.

- **`feed_type` is the discriminator.** 1, with `feedname == "steam_community_announcements"`,
  is the developer posting to their own game; anything else is syndicated press. This is
  not cosmetic filtering: Left 4 Dead 2's recent feed is 3 publisher posts and 2 magazine
  articles, LEGO Batman's is 2 and 3. Patch notes only ever live in the publisher feed, and
  a PC Gamer review is not an update. Ten are fetched so that three survive the filter.
- **`maxlength` truncates *and* strips, but only when it truncates.** A long post comes
  back cut and already clean; a post shorter than the limit comes back raw with its BBCode
  intact. So `strip_bbcode` is not belt and braces -- it is the only thing handling short
  posts.
- **The contents are BBCode, not HTML** (`[h1=x]`, `[list]`, `[*]`, `[url=...]`), handled
  exactly as Phase 10 handled HTML: break-like tags become one space, everything else is
  removed, whitespace collapses, and spaces before punctuation are dropped -- otherwise
  "English[b]*[/b], French" becomes "English * , French".
- **An unknown appid answers HTTP 403**, not a 404 and not an empty list. Treated as "no
  news" and cached as a miss.
- **A day for a hit, three for a miss.** Far shorter than the art and app-type caches,
  which describe things that never change; a game with no announcements today probably has
  none tomorrow, while a game that does post wants checking again soon.
- The block follows the same appid rule as the description, so it simply does not exist for
  the third of this library that has no appid. `NewsWorker` lives beside the screenshot
  workers and is stopped from `stop_downloads`, which `closeEvent` calls -- the documented
  rule about a QThread outliving its owner applies here too.

## Phase 18 notes (play something)

The weights, as shipped. Each one *multiplies*, so nothing is ever impossible to draw:

| rule | factor |
|------|--------|
| every eligible game starts at | 1.0 |
| played in the last 7 days | x0.5 |
| exe game with under 15 minutes on it | x2.0 |
| playtime unknown, i.e. any URI game | x1.0 (no boost, ever) |
| a favorite | x1.3 |

- **A URI game's playtime is unknown, not zero, and this is the whole reason `pick.py`
  exists as its own module.** Steam, Epic and Xbox games run under their own client, so
  this launcher never sees the time and almost all of them read 0 seconds. Treating that as
  "barely played" would boost every one of them at once. Measured over 20,000 seeded rolls
  against a library of ten URI and ten exe games all showing zero: **34% URI, 66% exe**.
  Without the exclusion it would have been an even 50/50 with the Steam library winning
  every close call, and with the boost applied to both it stays 50/50 but for the wrong
  reason -- the number to watch is that URI games stay well under half while still coming
  up regularly.
- **Never the same game twice running**, verified over 3,000 consecutive rolls on a
  three-game library: zero immediate repeats. A one-game library still answers with that
  game -- `avoid_key` is only honoured while something else remains.
- The pool is `not hidden and not is_non_game`, the same test the shelves use.
- Y/Triangle was the only unused face button. The TV hint bar advertises it, so it is
  discoverable from the couch rather than being a secret.
- Opening the page focuses **Play**, so a suggestion is one press from running.

## Phase 17 notes (favorites and the shelves)

**The full version shipped, not the approved fallback.** Multi-view focus did not fight the
synthesised-key design; it extends it. The crossing is *detected, not calculated*: send the
key to whichever view has focus, and if the selection did not move, the edge was already
there and focus belongs to the neighbour. Qt keeps doing wrapping, paging and
scroll-into-view exactly as before, and only the boundary is ours.

- `LibraryPage._focused_shelf` is the whole state: `None` means the grid. Crossing clears
  the other view's selection so exactly one focus ring is ever on screen, and the landing
  tile is chosen by nearest centre-x, so moving up feels like moving up rather than
  jumping to the start of the row.
- **`isVisible()` was the wrong question and a real bug.** It is False whenever *any*
  ancestor is hidden, so every shelf read as gone the moment the detail page was on top,
  and TV mode came back to a page that thought it had no shelves. `Shelf.shown` uses
  `isHidden()`, which is True only when the widget was hidden on purpose. Caught by a test
  that opened a game first.
- **One delegate, two hosts.** `CoverDelegate` takes a `host` providing `metrics`,
  `covers`, `focus_ring_width`, `view_for` and `hover_progress`; the page and each shelf
  are hosts. That is what keeps a shelf tile identical to a grid tile apart from scale.
- **A starred tool or hidden game never reaches a shelf**, whatever the toolbar checkboxes
  say. The star is stored on any game -- unstarring something just to hide it would be its
  own annoyance -- but `_refresh_shelves` filters hidden and non-games out first.
- **`favorite` stores True or nothing.** Unstarring removes the key rather than writing
  False, the opposite of `is_tool`, where False genuinely means "I disagree with Steam".
- **The checked state of a QPushButton is invisible under a stylesheet.** The starred and
  unstarred buttons differed only by a hollow glyph until `#Favorite:checked` was styled
  gold. Same lesson as `QMenu::item:disabled`, found the same way: by rendering it.
- **Two shelves cost real vertical space** -- about 420 px of a 980 px window, leaving
  roughly one and a half grid rows. `ui_rules.SHELF_SCALE` started at 0.62 and went to 0.52
  after looking at it.
- **They fold away as soon as the grid is scrolled** (reported from use: "they take up too
  much of the screen"), and unfold at the top. Three things had to be got right, all found
  by measuring rather than reasoning:
  - **Two thresholds, far apart** (`SHELF_COLLAPSE_AT` 140, `SHELF_RESTORE_AT` 20). Folding
    hands the shelf's height to the grid, which *shortens* the grid's scrollbar; with one
    threshold the shortened bar can drag the value back across it and the shelves flicker.
  - **`QPropertyAnimation.stop()` emits `finished()`.** The finish handler originally closed
    over the target it started with, so cancelling a fold mid-way hid the shelf immediately
    after the restore had shown it -- leaving a widget with a full maximumHeight, a full
    size hint, and a height of zero. The handler now reads current state.
  - **A relayout can reset the scroll to 0 without a `valueChanged` to react to** (a rescan
    finishing, TV mode switching). `_refresh_shelves` and `_settled` both re-read the fold
    from the scrollbar's actual value, or a shelf folded before that stays folded at the
    top with no way back.
- **A test that assumes no favorites will fail**: the user has starred games of his own.
  Derive what is already starred and add to it, exactly like the no-hardcoded-counts rule.
- **`notepad.exe` is not a deterministic launch subject on Windows 11.** It is a stub that
  hands off to the Store app, and that app stays inside the job, so killing the stub no
  longer ends the session -- which is the tracking working. `gui_launch_test` terminates
  the job instead. **That "test-only; the launcher never kills a game" was true when it was
  written and is now false in exactly one way**: Phase 21 added a Stop control, which the
  user has to press and then confirm. Nothing in the app still kills a game on its own.

## TV mode size, after the first real 4K TV (reported from use)

**"TV mode means bigger" was an assumption, and it was wrong on the only TV it ever met.**
`TV_SCALE` was a fixed 1.6. On a 4K TV set to 300% Windows scaling, Qt is handed a
1280x720 canvas *already*, so 1.6 on top of that left room for **three tiles on the entire
screen**. Windows' display scaling multiplies with ours; nothing in the app can see that
happening.

- It is now `config["tv_scale"]`, chosen in Settings from `ui_rules.TV_SCALE_CHOICES`
  (50%-160%), defaulting to `TV_SCALE_DEFAULT = 0.85` on the assumption that a TV is
  already scaling something. At 85% the same screen fits 7 across and 2 down.
- **Two test suites had the same assumption baked in** -- phase 7 asserted
  `tv_cover > normal_cover`, phase 10 asserted `tv_cap > normal_cap`. Both now assert that
  the size *follows the setting*, which is the property that actually matters and which
  the old wording quietly prevented anyone from changing.
- Only the *size* is a setting. Fullscreen, the button-hint bar and the thick focus ring
  are what TV mode is; those are unconditional.
- `notepad.exe` is a poor liveness subject on Windows 11: it is a stub that hands off to
  the Store app and exits, so a fixed "still alive after 2s" check is a coin flip. That is
  the same shim shape Phase 16 exists for. `gui_launch_test` now asserts the session ends
  exactly once rather than betting on a duration.

## Phase 16 notes (playtime that follows the whole game)

`launch.py` starts every exe **suspended**, puts it in a fresh Job Object, then resumes it.
Suspended first is the point: a shim that spawned the real game before the job existed
would escape it entirely. `win32process.CreateProcess` replaces `subprocess.Popen`, so the
CREATE_SUSPENDED route the brief preferred is what shipped; no fallback was needed.

- **Proven against a real process tree, with a control.** A batch shim that starts a
  9-second child and exits: with the job, the session lasts ~9s; with the job removed and
  only the first process watched, the identical run reports ~1s. That gap is the bug --
  The Last of Us Part I's `launcher.exe`, the Cinderia loader -- made measurable.
- **`pywintypes.error` is not an `OSError`.** The old `except OSError` around the launch
  would not have caught a single `CreateProcess` failure, which would have silently killed
  the elevation prompt for any game that needs administrator rights. Caught by name now.
- **Job flags are exactly `JOB_OBJECT_LIMIT_BREAKAWAY_OK` (0x800) and nothing else**, and a
  test asserts the whole value rather than individual bits. No kill-on-close, so closing
  the launcher can never take a running game with it -- verified live, not reasoned about.
  No silent breakaway, or children would leave unnoticed and a session would look finished
  while the game was still up.
- **Time is banked, not written per poll.** The poll runs every 3s because its other job is
  noticing a game has closed; writing `overrides.json` and repainting the grid at that rate
  for hours would be absurd. `rules.PLAYTIME_WRITE_INTERVAL_S` (60s) is therefore the most
  that can be lost, a session that ends is written immediately, and `closeEvent` banks
  whatever the live session earned. *What is banked was a sum of each poll's whole seconds
  until Phase 53, which lost ~16%; it is now the session's length measured from its start,
  less what is already banked.*
- **Still not measured, both accepted and stated:** a game started with administrator
  rights (ShellExecute returns no handle to follow), and any time after the launcher is
  closed.
- **A test destroyed real user data for the third time in this project.** Phase 15's test
  asserted `cache/imported_art` should not exist on this machine -- true when it was
  written, false the moment the user ran the import from his own try-this list. The check
  deleted 18 artwork files his overrides pointed at. Recovered by copying them back from
  `cache/sgdb_art` and `cache/steam_art`, which is where the import had copied them from,
  and verified by rendering the grid. The rule was already in this file and was still got
  wrong: **photograph the state at the start of a test and compare, never assert that
  something the user could have created is absent.**

## Phase 15 notes (carrying a library to another PC)

The counterpart of the installer, which deliberately carries nothing personal. One zip:
`manifest.json`, `config.json`, `overrides.json`, and `art/` holding **only** the images an
override points at — 11 MB for this library, against hundreds of megabytes if the whole
cache went in.

- **Every path inside the bundle is relative.** Covers and banners are rewritten to
  `art/<name>` on the way out and re-absolutised on the way in; an absolute path from
  another machine is worthless. An override pointing at a file that has since been deleted
  has the key dropped rather than a dead path exported.
- **Imported art lands in `cache/imported_art/`**, apart from the art the app downloads
  itself, so a cache clear can never delete artwork that arrived from another machine.
  Re-importing the same bundle is a no-op: identical files are recognised by content, so
  nothing is duplicated.
- **Import never deletes.** Imported records win where both machines know a game, records
  only the local machine has are untouched, and `backups.snapshot("before-import")` runs
  before anything is written.
- **Session history is the exception to "imported wins", added in Phase 20.** Every other
  field is a preference with one right answer, but `sessions` is a record of evenings that
  actually happened on each machine. `transfer` unions the two lists by start time (keeping
  the longer where both claim the same moment) and then prunes, so an import can never
  erase history played here for a game both machines know.
- **Config merges key by key, except `roots` and `exclusions`, which are unioned**
  (`rules.TRANSFER_UNION_KEYS`). Replacing the roots outright would stop the receiving
  machine finding its own games.
- **The report has to be honest about identity.** A URI-keyed entry (Steam, Epic, Xbox)
  reattaches on any machine; a folder game is keyed by its install path and only reattaches
  if the game sits at the same path, so the rest are reported as kept in reserve — the same
  mechanism that makes overrides survive an uninstall. Counts are given in those words.
- **The bundle contains the SteamGridDB key because config.json does.** The export dialog
  says so and offers a checkbox; the manifest records which way it went, and the import
  confirmation warns before overwriting a local key.
- **`ui_settings.DATA_REPLACED` is shared by restore and import.** Both replace the two
  files underneath an open settings dialog, and clicking OK afterwards would write its
  stale values straight back over them. Each flow reports its own outcome; the window only
  reloads.
- **A test-only trap worth remembering:** `discovery` (since Phase 46 `data_access.config_io`)
  binds `CONFIG_PATH` at import time,
  which is right in the real app but means a sandboxed test must reload `discovery` as well
  as `backups` and `transfer`, or config writes land in the previous sandbox's deleted
  folder. It surfaced as a logged error rather than a silent wrong answer.

## Phase 14 notes (the scan that runs on its own)

- **It is triggered from `showEvent`, once, behind `rules.STARTUP_SCAN_DELAY_MS`.** Not
  from `__init__`: a scan that begins while the window is still being built makes the
  first paint feel slow. Measured on this machine: window on screen at 1.1s, scan starts
  at 2.0s, finishes at 3.6s -- 1.6s of scanning, which is what the brief predicted.
- **The startup pass is quiet and the manual one is not.** `start_scan(quiet=True)` posts
  no "Scanning..." and connects no progress messages, because at that moment the status
  bar belongs to the removed-games notice and the controller announcement. The disabled
  Rescan button is the visible sign that something is happening. A manual scan keeps its
  running commentary -- the user asked for it and expects feedback.
- **`start_scan` returns a bool now.** It was already refusing to start a second scan; the
  return value is what lets the startup pass log that it stood down, and what the test
  asserts on. Overlap is impossible from the UI anyway, since the button is disabled.
- **The repost-once hack became a queue.** `_report_uninstalled` used to reassert itself
  when the bar fell silent, which handled exactly one collision. With a third message in
  play that was not enough, so `queue_status` now holds messages and shows each in turn as
  the bar frees up. The prune notice, the controller announcement and the scan result all
  go through it; anything the user just clicked still posts immediately, because by then
  the startup rush is over and instant feedback matters more.
  - "Ready" counts as an empty bar for queue purposes, or the first queued message would
    never appear.
  - **A test that assumes the bar is free at startup will fail on this machine**, because
    a real DualSense announces itself through the same queue. Wait for silence first --
    that the wait is necessary is the feature working.
- **The no-catalog scan in `__init__` stays.** It is the emergency path for a first-ever
  run, it is not quiet, and the running-guard stops the startup pass duplicating it.

## Phase 13 notes (backups, and the two files that cannot be regenerated)

`backups.py` owns both halves of one promise: copies aside, and writes that cannot be
interrupted. `catalog.json` and `cache/` are deliberately **not** backed up — they rebuild
themselves, and including them would turn a 5 KB snapshot into hundreds of megabytes.

- **The snapshot is the first thing `MainWindow.__init__` does**, before the config load,
  before `Overrides()`, before the merge that stamps `first_seen`, and long before a scan.
  A backup taken any later is a backup of whatever went wrong. It is in the window rather
  than in `launcher.py` so that every path which opens the app — including tests — is
  covered.
- **`snapshot()` never raises.** A launcher that will not open because a backup failed is
  a worse bug than the one being guarded against.
- **Skip when nothing changed**, compared byte for byte against the newest snapshot. The
  regression run proved why: 20-odd `MainWindow` constructions produced exactly one
  snapshot, where without the rule they would have flushed the recent tier.
- **Two tiers: last 5, plus the first snapshot of each of the last 10 days.** The daily
  tier exists because a corruption nobody notices for a week would otherwise age every
  good copy out of a five-deep rotation before it was spotted.
- **A same-second collision was a real bug, caught by a test.** The second snapshot in one
  second is named `..._04-51-42-1`, which `strptime` could not read, so it was invisible
  to the list, the rotation and restore — an orphan folder that would grow forever.
  `_parse_stamp` now retries after dropping a trailing `-N`, and sorting breaks ties on
  the folder name.
- **`config.json` was not written atomically** and now is. `catalog_io._atomic_write`
  delegates to `backups.atomic_write` so there is one implementation; the temp file must
  be in the *same directory*, since `os.replace` is only atomic within a filesystem.
- **Restore snapshots the current files first.** Restoring is itself destructive and the
  state being replaced might turn out to be the wanted one.
- **A restore closes the settings dialog with `ui_backups.RESTORE_DONE`.** The dialog is
  still holding the values it was opened with, so clicking OK afterwards would write the
  old settings straight back over the restored ones. `MainWindow.reload_after_restore`
  then rebuilds config, a fresh `Overrides`, the theme and every view — no restart needed.
  Replacing `self.overrides` wholesale is safe because every caller reaches it through
  `window.overrides`; nothing keeps its own reference.
- `humanize.moment` exists because `humanize.when` is too vague here: two snapshots twenty
  minutes apart both read "2h ago", which is useless when choosing one to restore.

## Packaging: GameLauncher-Setup.exe (after the Windows integration work)

Asked for as "some sort of installer file that i can easily backup and install on other
pc's". He chose a real installer over a portable exe, and chose it to carry **no personal
data** — safe to keep anywhere or hand to someone else.

Built with `packaging/build.py`; PyInstaller 6.22.0 is a **build-time tool only**
(`requirements-build.txt`), never a runtime dependency. 6.22.0 is the first release that
lists Python 3.14, which was checked before any of this was written.

- **A frozen app cannot use `Path(__file__).parent`, and seven places did.** `paths.py` is
  now the single owner. Run from source, everything resolves exactly where it always did —
  that was the constraint, since the user's real library lives in the project folder.
  Frozen, `__file__` points inside `_internal`, which a reinstall replaces wholesale, so
  writing `overrides.json` there would destroy playtime and artwork on every upgrade.
  Data goes beside the exe instead; `paths.resource_dir()` is separate because bundled
  read-only files land in `sys._MEIPASS`, which is *not* where the exe is.
  - The refactor broke `discovery.py` twice over: it used `HERE` again 70 lines below the
    definition that was removed. Grep for the *name*, not just the definition.
- **Three traps found only by running the built exe, not by building it:**
  1. **`win32timezone`** is imported lazily from inside pywintypes the first time a COM
     call returns a time. The build was clean; reading a shortcut then died with
     `ModuleNotFoundError`. It is in `hiddenimports` now, along with `uninstall`, which
     `launcher.py` imports inside a function.
  2. **A windowed build has nowhere to print a traceback**, so PyInstaller shows it in a
     modal dialog. For `--uninstall` launched from Add/Remove Programs that is a process
     hanging forever on a click nobody can give — it presented as a 120-second test
     timeout, not as a crash. Both `installer.py` and `uninstall.py` therefore route every
     message through one function that writes to stderr when running unattended.
  3. **A process cannot delete its own working directory.** The detached command that
     removes the install folder gets `cwd=tempfile.gettempdir()`.
- **The local `humanize.py` collides with the PyPI package of that name.** PyInstaller
  applies the contrib hook for the package and fails because it is not installed. An empty
  `packaging/hooks/hook-humanize.py` won over the bundled one and called it off. **Gone since
  Phase 47**: the module is `shared.humanize`, hooks match full module names, the collision
  no longer exists, and a build without the hook (and without `hookspath`) succeeded.
- **One folder, not one file.** A one-file build unpacks 136 MB to temp on every start,
  turning a 2-second launch into ~10. The installer is one-file because it runs once.
- **Excluding the Qt modules the app never imports** (it only uses QtCore, QtGui,
  QtWidgets) is most of the difference between ~400 MB and 136 MB.
- **The installer does not write shortcuts itself** — it runs the installed
  `GameLauncher.exe --make-shortcuts`, so there is one tested code path for that, and the
  installer needs no pywin32.
- **Tested by running the built installer, not its source**, inside a fake profile with
  `USERPROFILE`, `LOCALAPPDATA` and `APPDATA` redirected to a temp folder, so the four
  shortcuts land there instead of over the real ones. `--silent` exists for that. The one
  thing that escapes the sandbox is the HKCU uninstall key, which the test asserts on and
  then deletes.
- **Do not install it on this machine.** The user's library — playtime, the artwork for 8
  games, his SteamGridDB key — lives in the project folder, and an installed copy starts
  empty *and* repoints all four shortcuts at itself. Migrating him would mean copying
  `config.json`, `overrides.json` and `cache/` across and rewriting the absolute artwork
  paths in the overrides.

## Phase 8 notes (SteamGridDB — the key now exists and works)

- **The endpoint paths were verified with a control.** Unauthenticated, each of
  `search/autocomplete/{term}`, `grids/game/{id}` and `heroes/game/{id}` returns
  401 "Authentication Required", while a deliberately wrong path under the same base returns
  a 404 HTML page. That is what proves the paths are right without holding a key.
- **It works.** The user added a key in Phase 9's window and used it: Silent Hill 2,
  The Last of Us Part I and Star Wars Racer all carry SteamGridDB art
  (`cache/sgdb_art/<sgdb id>.jpg`). The success-path parsing is therefore no longer
  theoretical. Auto-matching from SteamGridDB during a scan is still not built and still
  needs asking first.
- **It is deliberately manual only.** SteamGridDB is consulted when the user asks for artwork,
  never during a scan.
- **An invalid key is distinguishable from a missing one** — the service answers
  "Invalid key format" versus "Authentication Required" — which is what the Test button in
  Settings reports.
- **The key never reaches the log.** `_redact` replaces it in any URL before logging, and the
  settings field masks it by default.
- `models.ArtCandidate` is the shared shape for a candidate from either source; `source`
  decides whether `ident` means a Steam appid or a SteamGridDB game id.

## Phase 7 notes (controllers and TV mode)

- **SDL is initialised with the dummy video driver** (`rules.CONTROLLER_SDL_VIDEODRIVER`).
  `pygame.event.pump()` raises "video system not initialized" without a video subsystem, and
  letting SDL initialise a real one inside a Qt process means two toolkits owning windows. The
  dummy driver gives SDL its event queue and creates nothing. Verified: polling works, no window
  appears, Qt is unaffected.
- **Input is discarded unless the launcher is in front.** SDL keeps reporting buttons while a game is
  fullscreen on top, so without the gate every in-game press also drives the launcher behind it.
  *The gate was `isActiveWindow()` until Phase 52, which was also False while the launcher's own
  Settings or a confirmation was in front; it is now "one of the launcher's windows is active".*
  Held state is cleared on the way out, so returning from a game does not fire a stale press.
- **Only the pad being touched is read.** DS4Windows can present a virtual pad beside the real
  DualSense; reading both doubles every press. The active pad is sticky — it stays active until
  a different pad actually moves.
- **Navigation synthesises Qt key presses** rather than computing rows and columns, so grid
  wrapping, page jumps and scroll-into-view behave exactly as they do for the keyboard.
- **`pygame-ce` 2.5.8 has a native `cp314` wheel**; no build toolchain is needed. Checked with
  `pip download --only-binary=:all:` before any feature code was written, as the brief required.
- **Measured, not guessed:** a DualSense at rest reads ~0.035 on the left stick, so the deadzone
  sits at 0.55.
- **Returning to the foreground after a game exits was best effort** -- it only flashed the
  taskbar button. **Superseded by Phase 28**, which measured why and fixed it (`focus.py`).
- **Escape always leaves TV mode**, so a fullscreen window with no pad attached is never a trap.
- **Only the DualSense was tested against real hardware.** The Xbox pad path is the same SDL
  mapping and the same code, but it has not been run here.

## Phase 6 notes (name → appid, for everything that is not a Steam install)

- **Always score every candidate; never take the first.** Steam's search ranks by its own
  relevance: searching "Worship" returns "No Sun To Worship" first and the exact match second.
- **The gate is 0.85 and the reason is `Eden`.** Measured on this library, every correct match
  scores 1.00, while "Eden" (an emulator) hits 0.67 against "Tiny Eden" and "Worship" hits 0.67
  against "No Sun To Worship". A wrong cover is worse than none, so the threshold sits well
  above the near-misses. Do not lower it to chase the remaining misses.
- **`type` cannot filter DLC.** Every search result comes back `type=app`, including
  "SnowRunner - The Mastodon". Only the similarity score keeps DLC and soundtracks out.
- **Steam's search is punctuation-sensitive.** "Star Wars Episode I - Racer" returns *nothing*;
  the same string without the hyphen matches exactly. One stripped retry
  (`STEAM_SEARCH_PUNCTUATION_RETRY`) recovers it.
- **"Mark as game" must store `False`, not delete the override.** Deleting it means "no
  opinion", so Steam's own `demo` label immediately wins again and the menu item appears to do
  nothing. Caught by a test, not by reading.
- **Landscape art needs a backdrop, not a flat panel.** A 460x215 header centred on an accent
  panel leaves most of a 2:3 tile empty. `_fit_on_panel` fills the tile with a softened,
  darkened copy of the same art — unless the image has an alpha channel, because blurring a
  transparent logo produces a backdrop of nothing. Aimlabs keeps the flat panel for that reason.
- **The user's picked cover is stored as a file path, not an appid.** `ui_cover_actions`
  downloads the art immediately and writes `cover`/`banner` paths into overrides, so discovery
  never has to read overrides and the separation rule holds.
- **What stayed unmatched here, correctly:** Fortnite (not sold on Steam), and DS4, Nvpi, Eden
  and Lightroom Classic (not games). Those keep generated covers and can be marked as tools.

## Phase 3 notes (Steam)

- **`StateFlags` is a bitfield.** Counter-Strike 2 reads 6 on this machine — fully installed
  *and* update required. Test `flags & STEAM_STATE_FULLY_INSTALLED`, never `== 4`.
- **The artwork cache layout is version-dependent.** This client uses
  `appcache\librarycache\<appid>\library_600x900.jpg`; older ones used flat
  `<appid>_library_600x900.jpg`. Both are searched. Critically, the flat form matches on
  `"<appid>_"` and never `"<appid>*"` — a bare prefix glob for appid 550 also matches 550140,
  550650 and 550900, which are different games. Files under
  `STEAM_ARTWORK_MIN_BYTES` are 1 KB placeholders, not art.
- **Only 2 of 7 Steam games here have local artwork.** The rest fall back to the Steam client
  icon. The real images live behind Steam's CDN; fetching them needs a network dependency the
  user has not agreed to.
- **`extra.last_played_unix`** comes from the manifest and is used by `GameView.last_played` when
  the user has not launched the game from here. Without it every Steam tile would read "never"
  for games they demonstrably play. A local launch takes precedence once it happens.
- **URI entries are never timed.** `os.startfile` on `steam://rungameid/<appid>` returns as soon
  as the shell hands off; the game is Steam's child, not ours.
- **The right-click menu drops "Choose a different exe" and "Set launch arguments" for URI
  entries** — Steam owns both, and its own game properties are where launch options belong.
- **Dedup and exclusions live in `discovery.py`, never in a provider.** Manifest providers run
  first; their library roots become folder-scanner exclusions (prefix-based, so the whole tree is
  skipped), and any folder entry still landing inside a claimed directory is dropped. Verified
  with a control: scanning `steamapps\common` without the exclusion yields 7 duplicate entries,
  with it, zero.
- **Nothing in the local manifests distinguishes a game from a tool, demo, soundtrack or server
  binary.** `3DMark Demo` and `Aimlabs` appear as games because locally they are indistinguishable
  from one. That classification only exists in Steam's `appdetails` web endpoint. Do not add the
  network call without asking.

## Phase 4 notes (GOG, Epic, Ubisoft)

- **Ubisoft finds nothing here, and that is the correct answer.** Both
  `Installs\<id>` keys exist but carry only `InstallState` — no `InstallDir` in either hive,
  `games\` is empty, there are no `Uplay Install <id>` uninstall keys, and no game directories
  on disk. The games were uninstalled; the cloud saves and cached icons that remain are what an
  uninstall leaves behind. The provider is written to the brief's format and requires both
  `InstallDir` present *and* the directory to exist, so an orphan key can never become a tile.
  **Its entry-building path has therefore never run against a real installed game** — it is
  covered by tests with injected registry values (`ubisoft.build_entry` is split out for exactly
  that reason). Treat it as unverified against reality until a Ubisoft game is installed.
- **GOG is the one manifest provider that emits `launch_kind: "exe"`.** DRM free, so there is no
  client to route through and nothing lost by not doing so. The registry gives an absolute exe
  and working directory, so none of the folder scanner's exe-guessing applies.
- **GOG records no install size**, so `walk.measure_size` walks the tree
  (`rules.MEASURE_INSTALL_SIZE`). Steam and Epic report their own and never pay for this.
- **Epic paths use forward slashes** (`"C:/Program Files/Epic Games/Fortnite"`) and
  `LaunchExecutable` is relative to `InstallLocation`. Both are normalised before use.
- **Epic's `AppCategories` is a local game/tool signal** — requiring `"games"` keeps Unreal
  Engine and similar tooling out of the grid without any web lookup. Steam has no equivalent.
- **Only Steam contributes scan exclusions.** `steamapps\common` is one well-defined tree, so
  excluding it wholesale is safe. GOG, Epic and Ubisoft install to scattered locations where a
  blanket exclusion could hide a folder the user wants scanned; per-directory dedup covers them.

## EA — investigated and deliberately not built

The brief said to skip EA rather than invent a format if no reliable one exists. It does not
exist here. **Do not add an EA provider on the strength of guessed value names.** What was
actually found on this machine, 2026-08-11:

- `HKLM\SOFTWARE\WOW6432Node\Origin Games\1028663` holds `DisplayName = "A Way Out"` and
  `Locale` — **and no path value of any kind**.
- `HKLM\SOFTWARE\WOW6432Node\EA Games\Need for Speed Most Wanted` contains that game's
  *graphics settings* (`g_FSAALevel`, `g_ShadowDetail`, …), not install data.
- The Windows uninstall registry has entries for the EA app itself and for no EA game.
- `C:\ProgramData\EA Desktop\InstallData\AWayOut\…\map.eacrc` is an undocumented binary
  (`E4X$01` magic) holding *relative* paths and checksums — a file-integrity manifest, with no
  install location in it.
- EA Desktop's real install state lives in `C:\ProgramData\EA Desktop\<hash>\IS`, which is
  encrypted and undocumented.
- No EA game directory exists on C:, D: or G:. A Way Out is not installed; the Origin key is an
  orphan, exactly like the Ubisoft ones.

The blocker is not that the data is absent — it is that **with no EA game installed, a correct
implementation and a broken one both return `[]`**, so nothing could be verified. Revisit only
when an EA game is actually installed and the real value names can be read off the machine.

## Phase 4 notes (Xbox / Game Pass)

- **`WindowsApps` is never read.** Games are enumerated from `<drive>:\XboxGames`, which is
  readable by an ordinary user, and a folder counts as a game only if
  `Content\MicrosoftGame.config` exists. `GameSave` sits beside the games and is excluded by
  that test alone. A test hooks `open`/`scandir`/`listdir` at runtime to prove no access under
  WindowsApps ever happens — grepping the source is not enough, the docstring mentions it.
- **The AUMID is assembled, not guessed**: `PackageFamilyName` from `Get-AppxPackage`, plus the
  `Id` of the first `<Executable>` in MicrosoftGame.config. Verified equal to what
  `Get-StartApps` reports. Get-StartApps name-matching is only the fallback.
- **Do not classify games by scanning Get-StartApps.** It returns 255 entries on this machine,
  of which only 68 are UWP at all, and it includes `steam://rungameid/...` shortcuts that would
  duplicate the Steam provider.
- **Launching uses `explorer.exe shell:appsFolder\<AUMID>`**, handled in `launch._launch_uri`
  by the `shell:` prefix. Verified end to end against Calculator rather than a real game.
- **Known gap:** Game Pass titles predating the XboxGames layout live only under WindowsApps and
  are not found. Listing them would mean guessing which Start entries are games.
- Off by default (`rules.XBOX_ENABLED_DEFAULT`); the user's `config.json` has it on.

## The network layer (`web/steam_web.py`)

- **Two calls, both anonymous read-only GETs.** `appdetails?filters=basic` for the app type, and
  a cover image. No account, key, or user data is involved.
- **`config.json: "allow_network"`** turns it off entirely; discovery then produces the same
  games without types or downloaded art. Verified.
- **Everything is cached** in `cache/steam_web.json` + `cache/steam_art/`. A first run costs
  ~12s (rate limiting, not bandwidth); every later scan makes zero requests and takes 0.3s.
  Negative results are cached too, on a shorter expiry, so a game that gains art later is
  picked up.
- **Do not derive artwork URLs from the `header_image` value.** Replacing its filename with
  `library_600x900.jpg` returns HTTP 404 — the store's hashed asset paths do not work that way.
  The portrait capsule comes from `rules.STEAM_CAPSULE_URL`, and `header_image` from appdetails
  is the fallback.
- **Size-check every download.** `library_600x900.jpg` exists for Battlefield 6 but is a 1.6 KB
  placeholder; the real image comes from the appdetails `header_image` instead. Anything under
  `STEAM_ARTWORK_MIN_BYTES` is rejected and the next candidate tried.
- **A dead network must never cost a game.** Tested by pointing the URLs at an unroutable host:
  all 7 Steam entries still appear, just untyped. A corrupt cache file is also survived.
- **Icons are centred on a square canvas** (`icons.IconLoader._fit`). Art arrives portrait
  (600x900), landscape (460x215) and square (exe icons); without a common canvas the tiles in a
  row start at different heights.
