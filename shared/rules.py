"""Every tunable knob in the scanner. Change values here, not in the walk logic.

Nothing in this file imports from the rest of the project, so it is safe to edit freely.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------
# Where to look
# --------------------------------------------------------------------------------------

# Where the folder scanner looks when config.json names no roots. Since Phase 77 a new install
# is asked first and writes its answer -- an empty list included -- so this serves only where
# nothing asks: scanner.py run without a config, and a config.json without a "roots" key.
# Both are this machine's, where the launcher was built.
DEFAULT_ROOTS: tuple[str, ...] = (r"C:\games", r"C:\voices38")

# The first-run question (Phase 77): a folder one level below a fixed drive's root is offered
# as a place the games might be when one of the words of its name is one of these (split on
# anything that is not a letter, any case: "Games", "PC Games", "Jocuri", "Games2").
FIRST_RUN_FOLDER_HINTS = ("games", "game", "gaming", "jocuri", "joc")
# Never offered, whatever their names say: the stores' own libraries -- their providers find
# those games, and the scan excludes them anyway -- and Windows' own folders (SYSTEM_FOLDERS,
# below). Compared in lower case. A folder holding a "steamapps" folder is a Steam library
# whatever it is called.
FIRST_RUN_STORE_FOLDERS = (
    "steamlibrary", "steam library", "steamapps", "steam", "epic games", "epicgames", "gog games",
    "gog galaxy", "gog", "xboxgames", "riot games", "ea games", "origin games", "ubisoft",
    "ubisoft game launcher", "battle.net", "rockstar games",
)
FIRST_RUN_STEAM_MARKER = "steamapps"

# Windows' own folders (Phase 82; until then only "not offered" by the first run): never a game
# folder, never chosen as one, never walked by the scan whatever its folders are, and never
# removed (removal's fifth rule). Each is its path below a drive's root, in lower case -- **by
# where it is, not by its name alone**: 13 folders called "Windows" or "ProgramData" sit inside
# the real games here (every Unreal game's Engine\Binaries\ThirdParty\Windows, Lightroom's
# Data\ProgramData), and a rule by name would have walked past what is in them.
SYSTEM_FOLDERS = (
    "windows", "windows.old", "program files", "program files (x86)", "programdata", "users",
    "documents and settings", "$recycle.bin", "system volume information", "recovery", "perflogs",
    "boot", "config.msi", "msocache", "onedrivetemp", "$windows.~ws", "$windows.~bt", "$winreagent",
    "$sysreset", "$getcurrent", "program files\\windowsapps", "program files\\modifiablewindowsapps",
)

# Hard cap on how deep inside a game folder we will look for an exe.
MAX_DEPTH = 6

# --------------------------------------------------------------------------------------
# Directories never descended into
# --------------------------------------------------------------------------------------

SKIP_DIR_NAMES: frozenset[str] = frozenset(
    name.casefold()
    for name in (
        "_CommonRedist",
        "redist",
        "redistributable",
        "redistributables",
        "DirectX",
        "vcredist",
        "DotNet",
        "__Installer",
        "_Redist",
        "DXSETUP",
        "node_modules",
        ".git",
    )
)

# Matched against the path relative to the game folder, so a nested Engine\Binaries\ThirdParty
# is caught wherever it sits.
SKIP_DIR_PATH_FRAGMENTS: tuple[str, ...] = (r"engine\binaries\thirdparty",)

# --------------------------------------------------------------------------------------
# Executables never considered as a launch target
# --------------------------------------------------------------------------------------

# Verbatim from the brief. fnmatch semantics: "unins*" is a prefix match,
# "*crashhandler*" is a contains match. All comparisons are casefolded.
BRIEF_SKIP_EXE_GLOBS: tuple[str, ...] = (
    "unins*",
    "setup*",
    "install*",
    "vcredist*",
    "dxsetup*",
    "dxwebsetup*",
    "oalinst*",
    "*crashhandler*",
    "*crashreport*",
    "unitycrashhandler*",
    "*crashreportclient*",
    "python*",
    "ffmpeg*",
    "7z*",
    "notification_helper*",
    "*config*.exe",
    "*editor*.exe",
    "*server*.exe",
    "*benchmark*.exe",
)

# Added after seeing what actually sits in C:\games and C:\voices38. Each one is a real
# file observed there that the brief's list does not catch, because the separator differs
# ("crash_reporter" vs "crashreport") or the vendor uses another word entirely.
EXTRA_SKIP_EXE_GLOBS: tuple[str, ...] = (
    "*vc_redist*",  # VC_redist.x64.exe -- the real Microsoft filename has an underscore,
    # so the brief's "vcredist*" never matches it. Only caught by the
    # _CommonRedist directory skip, which misses copies kept elsewhere
    # (BeamNG ships one in Bin64\).
    "crashpad*",  # crashpad_handler.exe -- Unity/Chromium crash reporter
    "*crash_report*",  # crash_reporter.exe -- SnowRunner
    "crashsender*",  # CrashSender.exe -- BeamNG
    "*prereqsetup*",  # UE4PrereqSetup_x64.exe
    "epicwebhelper*",  # Epic overlay helper shipped inside UE games
    "winrar*",  # bundled installer found next to an emulator build
    "*uninstall*",
)

SKIP_EXE_GLOBS: tuple[str, ...] = BRIEF_SKIP_EXE_GLOBS + EXTRA_SKIP_EXE_GLOBS

# Anything smaller than this is a stub, a shim or a helper, never a game binary.
MIN_CANDIDATE_SIZE_BYTES = 24 * 1024

# --------------------------------------------------------------------------------------
# Engine fingerprints, in priority order
# --------------------------------------------------------------------------------------

UNITY_DATA_SUFFIX = "_data"  # <stem>_Data sibling folder
UNREAL_SHIPPING_SUFFIX = "-win64-shipping.exe"
UNREAL_REQUIRED_PARENTS: tuple[str, str] = ("binaries", "win64")  # ...\Binaries\Win64\
GODOT_PACK_SUFFIX = ".pck"  # <stem>.pck sibling file

# Many packaged builds wrap the real game in one pointless subfolder (sometimes two). When a folder
# holds nothing but a single subfolder, treat that subfolder as the game's real root so the
# "sits at the top of the game folder" bonus still means something.
WRAPPER_DESCENT_MAX = 3

# A loader sitting above the game. Packaged builds routinely place a small exe at the top of the
# game folder next to a Steam-emulation layer; it prepares that layer and then starts the
# real engine binary nested below. Launching the engine binary directly makes the game boot,
# fail to reach Steam, and crash a few seconds in -- which is exactly what Cinderia did.
#
# These markers are chosen because a genuine game never ships them: steamclient64.dll and
# gameoverlayrenderer64.dll belong to the Steam client itself, and steam_settings is an
# emulator's configuration directory. steam_api64.dll is deliberately NOT here -- real games
# ship that one all the time.
PREFER_LOADER_AT_ROOT = True
LOADER_MARKER_FILES: tuple[str, ...] = (
    "steamclient64.dll",
    "steamclient.dll",
    "gameoverlayrenderer64.dll",
    "gameoverlayrenderer.dll",
)
LOADER_MARKER_DIRS: tuple[str, ...] = ("steam_settings",)

# steam_emu.ini is an emulator's own config and is never shipped by a real game. It is what
# marks The Last of Us Part I, whose working entry point is launcher.exe rather than the
# 59 MB tlou-i.exe the score would otherwise pick.
LOADER_MARKER_FILES += ("steam_emu.ini", "coldclientloader.ini")

# A loader is usually the smallest exe present, so size is the last resort. An exe named
# after the game wins first, then these conventional names.
LOADER_EXE_NAMES: frozenset[str] = frozenset({"launcher", "start", "play", "game", "run"})
LOADER_NAME_RATIO = 0.75

# Unreal ships a small bootstrapper beside the game folder that starts the real binary under
# Binaries\Win64. It is the entry point the game's own shortcut uses. Khazan's is KZ.exe,
# whose version resource names it outright even though the shipping binary is BBQ-*.
PREFER_UNREAL_BOOTSTRAPPER = True
UNREAL_BOOTSTRAP_PRODUCT_NAMES: frozenset[str] = frozenset({"bootstrappackagedgame"})

# --------------------------------------------------------------------------------------
# Fallback scoring. Only consulted when no engine fingerprint matched.
# --------------------------------------------------------------------------------------

SCORE_NAME_SIMILARITY = 100.0  # x difflib ratio of exe stem vs folder name
SCORE_DEPTH_BONUS = 30.0  # x 1/(1+depth below the game's real root)
SCORE_SIZE_MAX = 35.0  # x log-scaled file size
SCORE_SIZE_CEILING_MB = 512.0  # size at which the size bonus saturates
SCORE_PE_NAME_MATCH = 45.0  # x ratio of PE ProductName vs folder name
SCORE_PE_PRESENT = 5.0  # flat bonus for having any version resource at all

# Reading version resources is cheap but not free; stop after this many per game folder.
MAX_PE_READS_PER_GAME = 40

# Rejected candidates recorded per entry, so a mis-detected game can be retargeted.
MAX_ALTERNATIVES = 40

# --------------------------------------------------------------------------------------
# Display names
# --------------------------------------------------------------------------------------

# A PE ProductName is only trusted if it is recognisably the same title as the folder.
# Measured against real files: Khazan's exe reports "KZ" (ratio 0.08 -> rejected).
PE_NAME_ACCEPT_RATIO = 0.5

# Second guard: a run-together token like "LEGOBatmanLotDK" or "SilentHill" is an internal
# build name. If the folder name has real word breaks and says more, the folder wins.
PE_NAME_REJECT_IF_SQUASHED = True

# Stripped from PE names.
NAME_TRIM_CHARS = "\u2122\u00ae\u00a9"  # (tm) (r) (c)

# Regexes removed from a folder name before anything else, while the dots are still intact.
NAME_STRIP_PATTERNS: tuple[str, ...] = (
    r"\bv?\d+(?:\.\d+)+[a-z]?\b",  # v1.0.19, 0.6.10b, 15.3.0.11
    r"\bbuild[._ -]?\d+\b",  # Build.19656838
    r"\b(?:x64|x86|win64|win32|amd64)\b",
    r"\[[^\]]*\]",  # [MULTi12], [ENG]
    r"\((?:\d{4})\)",  # (2023)
)

# Whole words/phrases dropped after separators become spaces. Casefolded comparison.
NAME_STRIP_TOKENS: tuple[str, ...] = (
    "repack",
    "gog",
    "p2p",
    "skidrow",
    "reloaded",
    "codex",
    "plaza",
    "flt",
    "tenoke",
    "rune",
    "empress",
    "dodi",
    "fitgirl",
    "elamigos",
    "ankergames",
    "anker games",
    "early access",
    "steamrip",
    "steam rip",
    "proper",
    "cracked",
    "incl dlc",
    "multi",
)

# Characters that become spaces once version numbers have been removed.
NAME_SEPARATORS = "._-+"

# --------------------------------------------------------------------------------------
# Steam
# --------------------------------------------------------------------------------------

# Both confirmed present on a real install. HKCU is authoritative and is checked first;
# it returns a lowercase forward-slash path ("c:/program files (x86)/steam") that must be
# normalised before use.
STEAM_REGISTRY_LOCATIONS = (
    ("HKCU", r"Software\Valve\Steam", "SteamPath"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
)

# StateFlags is a bitfield, not an enum. Counter-Strike 2 sits at 6 -- fully installed AND
# update required -- so this must be tested as a bit, never compared for equality.
STEAM_STATE_FULLY_INSTALLED = 4

STEAM_SKIP_APPIDS: frozenset[str] = frozenset({"228980"})  # Steamworks Common Redistributables

# Matched casefolded against the installdir.
STEAM_SKIP_INSTALLDIRS: frozenset[str] = frozenset({"steamworks shared", "steam controller configs"})

# Matched casefolded against the app name, as a prefix, so a game whose title merely
# contains one of these words is not swept up with the runtimes.
STEAM_SKIP_NAME_PREFIXES: tuple[str, ...] = (
    "proton ",
    "proton-",
    "proton experimental",
    "steam linux runtime",
    "steamworks common redistributables",
)
STEAM_SKIP_NAMES_EXACT: frozenset[str] = frozenset({"proton"})

# Artwork basenames in order of preference. The cache layout has changed across client
# versions -- today it is librarycache\<appid>\library_600x900.jpg, older clients used a
# flat librarycache\<appid>_library_600x900.jpg -- so both shapes are searched and no
# single filename is assumed to exist.
STEAM_ARTWORK_NAMES: tuple[str, ...] = (
    "library_600x900",
    "library_capsule",
    "capsule_616x353",
    "header",
    "logo",
)
STEAM_ARTWORK_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png")

# Anything the UI will accept as a cover or banner, including a file the user picks.
ARTWORK_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# The cache is littered with 0-1 KB hash-named placeholders; anything this small is not art.
STEAM_ARTWORK_MIN_BYTES = 4096

# --------------------------------------------------------------------------------------
# Steam web lookups -- the ONLY sanctioned network use in this project
# --------------------------------------------------------------------------------------

# The user approved these two specifically: cover art for games with none cached locally,
# and the app type, which is the only way to tell a game from a demo, tool, soundtrack or
# server binary. Nothing else may reach the network without asking again.
# Both are read-only, anonymous GETs. No account, key or personal data is involved.

ALLOW_NETWORK_DEFAULT = True

# The full record, not filters=basic. Same endpoint, same caching, same rate limiting; it
# just returns everything instead of the four fields the type check needed. English is asked
# for explicitly so the description does not arrive in the store's guess at your language.
# The country likewise, since Phase 70: without it the store answers for wherever the request
# seems to come from, and two records here came back priced in Polish zloty. The storefront
# search has always asked for Romania; the store answers for it in euros (38 of the 40 priced
# records; asked again for Romania, the two in zloty came back in euros too).
STEAM_STORE_COUNTRY = "RO"
STEAM_STORE_CURRENCY = "EUR"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails?appids={appid}&l=english&cc=" + STEAM_STORE_COUNTRY

# The weekly price observation (Phase 73): the same appdetails endpoint, filtered to the
# price alone, which is the one form that takes several appids in one call -- measured on
# 11 October 2026 with 730, 550 and 1: one answer, three shapes (BAZA_DE_DATE section 8).
STEAM_PRICES_URL = ("https://store.steampowered.com/api/appdetails?appids={appids}&filters=price_overview"
                    "&l=english&cc=" + STEAM_STORE_COUNTRY)
PRICE_REFRESH_DAYS = 7  # an app is asked again once its newest observation is this old
PRICE_BATCH_SIZE = 50  # appids per request; the library has 48 apps with a record today
PRICE_REQUESTS_PER_SCAN = 8  # at most this many price requests in one scan, a second apart (2 until
                             # Phase 75: the apps of the Steam history join the weekly batch)
PRICE_HANDOFF_FILE = "price_observations.json"  # in cache/: the scan thread's prices, for the window

# Steam's own playtime (Phase 75), read from its files -- verified on this machine on 11 October
# 2026: <Steam folder>\config\loginusers.vdf (the accounts that logged in here, by SteamID64)
# and <Steam folder>\userdata\<account id>\config\localconfig.vdf, whose
# UserLocalConfigStore -> Software -> Valve -> Steam -> apps -> <appid> holds Playtime (lifetime
# minutes on that account), Playtime2wks, PlaytimeDisconnected and LastPlayed (unix seconds).
# The casing drifts between client versions -- one file here says "Apps" -- so every key is
# looked up case-insensitively. The account id is the low 32 bits of the SteamID64.
STEAM_LOGIN_USERS_FILE = ("config", "loginusers.vdf")
STEAM_USERDATA_DIRNAME = "userdata"
STEAM_LOCALCONFIG_FILE = ("config", "localconfig.vdf")
STEAM_LOCALCONFIG_APPS = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps")
STEAM_ID64_BASE = 76561197960265728  # an individual account's SteamID64 less this is its account id
STEAM_TIME_KEYS = {"minutes_total": "Playtime", "minutes_2wks": "Playtime2wks",
                   "minutes_disconnected": "PlaytimeDisconnected", "last_played": "LastPlayed"}
STEAM_TIME_HANDOFF_FILE = "steam_time.json"  # in cache/: the scan thread's reading, for the window
# The apps of the accounts marked mine that the launcher has no record of are fetched from the
# store a few a scan, the most played first, so the names that matter arrive first.
STEAM_HISTORY_RECORDS_PER_SCAN = 20

# The Steam wishlist (Phase 86): the eighth sanctioned address, the user's brief the asking.
# IWishlistService/GetWishlist on api.steampowered.com -- the news endpoint's host, another
# service -- read only, anonymous, no key, one request per account marked mine. Read on this
# machine on 15 October 2026, the four accounts: a public list answers HTTP 200
# {"response":{"items":[{"appid":296470,"priority":0,"date_added":1463944159},...]}}; the other
# three answered {"response":{}} -- and one of them, the account signed in, shows "Wishlist 6" in
# the store, so a private list answers exactly that, as an empty one would. The two cannot be told
# apart: an answer with no items is "nothing to read", and never takes an item off the list.
STEAM_WISHLIST_URL = "https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={steamid}"
WISHLIST_HANDOFF_FILE = "wishlist.json"  # in cache/: the scan thread's readings, for the window
# Once a day: each marked account's list, and the price of every game on one (the user's yes on
# 15 October -- a Steam sale lasts one to two weeks, and a weekly look can miss one). 20 hours,
# not 24, so a start a little earlier the next day still counts as the next day.
WISHLIST_READ_HOURS = 20
WISHLIST_PRICE_HOURS = 20
# The Wishlist page (Phase 87). A row opens the Steam client's store page by the protocol Steam
# registered (HKCR\steam\shell\open\command is `steam.exe -- "%1"`; checked on this machine on 15
# October: Steam's console_log took steam://store/1144200 and the client showed that game's page);
# with no client to take it, the store's web page in the browser.
STEAM_STORE_PAGE_URI = "steam://store/{appid}"
STEAM_STORE_WEB_PAGE = "https://store.steampowered.com/app/{appid}/"
WISHLIST_ART_PER_VISIT = 20  # covers fetched for a visit to the page at most, a second apart
WISHLIST_FIT_GENRES_NAMED = 2  # the fit line names the genres that add the most to it (Phase 89)
WISHLIST_SERIES_MIN = 3  # a wished game's price line is drawn once it has this many prices (Phase 89)
# Report 8, stated against revealed (Phase 89): a genre is said to be wished for more than it is
# played only when it is on this many wished games -- one game of sixteen is noise.
REPORT_STATED_MIN_GAMES = 2
# Kept in config.json, each its own key (never the whole config): the games hidden from the page
# -- a mark on this PC, never a change to the Steam list -- and the chosen chip. (Phase 87's once-a-day
# notice kept a third, "wishlist_notice"; Phase 101 retired the notice, and the key is no longer written.)
WISHLIST_HIDDEN_SETTING = "wishlist_hidden"
WISHLIST_FILTER_SETTING = "wishlist_filter"

# Price alerts on the wishlist (Phase 101): judged on the prices a scan has just landed, written to the
# price_alert log before they are shown, each (game, price, kind) once. 'lowest' needs a series of this many
# prices in the price's currency: one or two are no reference point yet, and an alert on them is noise.
ALERT_LOWEST, ALERT_TARGET = "lowest", "target"
ALERT_MIN_OBSERVATIONS = 3
ALERT_KEEP_DAYS = 30  # the Wishlist tab's Alerts list shows the alerts of this many days; the log keeps them all
ALERT_NAMED_MAX = 2  # one message names this many games, then "and N more"
# The target dialog: from a cent to 9999,99 in the game's currency, a step of 1,00 on the arrows and the pad.
ALERT_TARGET_MIN_CENTS = 1
ALERT_TARGET_MAX_CENTS = 999_999
ALERT_TARGET_STEP_CENTS = 100

# "How was it?" (Phase 102): one quiet question after a session, five stars, one tap (logic/rate.py).
RATE_MIN_MINUTES = 10  # step 0: the sessions split here -- quick starts below (10th percentile 2 min), play above
RATE_CARD_S = 20  # unanswered, the card goes by itself and nothing is written
RATE_LATE_DAYS = 14  # a session can still be rated from its game's page this long; nothing older is asked for
RATE_ASK_ONCE_PER_DAY = True  # one question a game a day, whatever it is answered
RATE_RETRY_MS = 2000  # a dialog or a menu is open: the card waits, and looks again this often
RATE_TRIES = 30  # for a minute at most; then the session waits for its page
RATE_STARS = 5
RATE_ASK_KEY = "ask_rating"  # Settings, After a game: "Ask how a session was"
RATE_ASK_DEFAULT = True

# Money (Phase 74). An amount is written as the store writes it for Romania, with its
# currency's sign after it (humanize.money); a currency not listed keeps its code.
CURRENCY_SIGNS = {"EUR": "€", "RON": "lei"}
# What the purchase dialog offers: EUR first and chosen, RON beside it; and the stores it
# suggests -- the user can type any other.
PURCHASE_CURRENCIES = ("EUR", "RON")
PURCHASE_STORES = ("Steam", "GOG", "Epic", "Xbox or Game Pass", "key reseller", "gift", "other")

# Full records are 17-29 KB each, so they live one-file-per-game rather than bloating the
# small hot cache that every scan reads. Only the game whose page you open is ever parsed.
STEAM_DETAILS_DIRNAME = "steam_details"

# Two independent signals for the same thing; a game has one, both, or neither.
STEAM_CONTROLLER_FULL_VALUE = "full"
STEAM_CATEGORY_FULL_CONTROLLER = "full controller support"

# Portrait capsule. Verified to serve real art for older titles, but it returns a ~1.6 KB
# placeholder for some newer ones, so the size check below is what actually decides.
STEAM_CAPSULE_URL = "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"

# Wide banner for the detail page, same appid-keyed family as the capsule above. Verified
# present and full-size for every appid installed on this machine.
STEAM_HERO_URL = "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_hero.jpg"

# Local banner names, in preference order. "library_hero_blur" is deliberately absent: it
# is a ~2 KB smudge the client uses as a backdrop, not artwork.
STEAM_BANNER_NAMES: tuple[str, ...] = ("library_hero", "capsule_616x353")

STEAM_USER_AGENT = "game-launcher/1.0 (local game catalogue; no data collected)"
STEAM_WEB_TIMEOUT_SECONDS = 10
STEAM_WEB_RATE_LIMIT_SECONDS = 1.0  # the store endpoint throttles aggressive callers
STEAM_WEB_MAX_REQUESTS_PER_SCAN = 60
STEAM_WEB_CACHE_DAYS = 30  # a game's type and art essentially never change
STEAM_WEB_MISS_CACHE_DAYS = 7  # shorter, so a game that gains art later is picked up

# Steam "type" values that mean an actual game. Everything else -- demo, dlc, music, video,
# tool, application, mod, series -- is real but is not something to show as a game.
STEAM_GAME_TYPES: frozenset[str] = frozenset({"game"})

# --------------------------------------------------------------------------------------
# Steam storefront search -- resolving a name to an appid, for entries that have none
# --------------------------------------------------------------------------------------

STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/?term={term}&l=english&cc=" + STEAM_STORE_COUNTRY

# Measured against this library. Every correct match scores 1.00; the dangerous near-misses
# are "Eden" against "Tiny Eden" and "Worship" against "No Sun To Worship", both 0.67. A
# wrong cover on a game is worse than no cover, so the gate sits well above those.
STEAM_SEARCH_MATCH_RATIO = 0.85

# Steam's search ranks by its own relevance, which is not ours: searching "Worship" returns
# "No Sun To Worship" first and the exact match second. Always score every candidate.
STEAM_SEARCH_MAX_CANDIDATES = 8

# Never auto-match these: a short tool name will confidently match some unrelated game.
# DS4 scores 0.29 and Nvpi returns nothing, but the rule is the safeguard, not the numbers.
STEAM_SEARCH_SKIP_DETECTIONS: frozenset[str] = frozenset({"loose_exe"})

# Steam's search is strict about punctuation: "Star Wars Episode I - Racer" returns nothing
# while the same name without the hyphen matches exactly. One retry, stripped.
STEAM_SEARCH_PUNCTUATION_RETRY = True

STEAM_SEARCH_CACHE_DAYS = 30
STEAM_SEARCH_MISS_CACHE_DAYS = 7

# Recorded in extra.appid_source when an appid came from the name search rather than from a
# launcher's own manifest. A searched appid is a good guess, not a fact, so it is never
# allowed to hide a game the user actually installed.
APPID_SOURCE_SEARCH = "storefront search"

# --------------------------------------------------------------------------------------
# GOG -- DRM free, so these launch by exe path rather than through a client
# --------------------------------------------------------------------------------------

# Confirmed present. The 64-bit location is checked too for machines with a 64-bit client.
GOG_REGISTRY_LOCATIONS = (
    ("HKLM", r"SOFTWARE\WOW6432Node\GOG.com\Games"),
    ("HKLM", r"SOFTWARE\GOG.com\Games"),
)

# --------------------------------------------------------------------------------------
# Epic
# --------------------------------------------------------------------------------------

# Relative to %ProgramData%, which is read from the environment rather than assumed as C:.
EPIC_MANIFEST_SUBPATH = ("Epic", "EpicGamesLauncher", "Data", "Manifests")
EPIC_MANIFEST_SUFFIX = ".item"
EPIC_LAUNCH_URI = "com.epicgames.launcher://apps/{namespace}%3A{item_id}%3A{app_name}?action=launch&silent=true"

# Epic manifests carry an AppCategories list. Requiring "games" keeps Unreal Engine and
# other tooling out of the grid; it is a local field, not a web lookup.
EPIC_REQUIRED_CATEGORY = "games"

# --------------------------------------------------------------------------------------
# Ubisoft Connect
# --------------------------------------------------------------------------------------

UBISOFT_REGISTRY_LOCATIONS = (
    ("HKLM", r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"),
    ("HKCU", r"Software\Ubisoft\Launcher\Installs"),
)
UBISOFT_LAUNCH_URI = "uplay://launch/{game_id}/0"

# On the machine this was built against, both Installs\<id> keys exist but carry only
# InstallState and no InstallDir, because the games were uninstalled. An entry is only
# emitted when InstallDir is present AND the directory is really there -- otherwise the
# launcher would list games that are not installed.

# --------------------------------------------------------------------------------------
# Xbox / Game Pass
# --------------------------------------------------------------------------------------

# Off by default, as the brief requires: this is the least certain source, and a wrong
# guess here puts ordinary Windows apps in a list of games.
XBOX_ENABLED_DEFAULT = False

# Modern Game Pass installs land in <drive>:\XboxGames, which -- unlike
# C:\Program Files\WindowsApps -- is readable without fighting TrustedInstaller ACLs.
# WindowsApps is never touched.
XBOX_GAMES_DIRNAME = "XboxGames"

# Presence of this file is what makes a folder a game rather than a stray directory.
# GameSave sits alongside the games and has no config, so it is excluded automatically.
XBOX_CONFIG_RELATIVE = ("Content", "MicrosoftGame.config")

# Launched through the shell's app folder, not by exe path: these are packaged apps and
# running the inner exe directly bypasses the container they expect.
XBOX_LAUNCH_TARGET = "shell:appsFolder\\{aumid}"

# Cover art shipped inside the package, largest first.
XBOX_LOGO_PREFERENCE = ("LargeLogo.png", "Logo.png", "StoreLogo.png", "SmallLogo.png")

XBOX_POWERSHELL_TIMEOUT_SECONDS = 45

# --------------------------------------------------------------------------------------
# SteamGridDB -- the only endpoint here that needs a key, and the only one that is optional
# --------------------------------------------------------------------------------------

# For games Steam's own store cannot match at all. Requires a free key from the user's own
# SteamGridDB account, stored in config.json as "steamgriddb_key". With no key configured,
# none of this runs and nothing changes.
#
# Paths verified against the live service: each returns 401 "Authentication Required"
# unauthenticated, while a deliberately wrong path returns a 404 HTML page. That is the
# control that proves these are right.
SGDB_BASE = "https://www.steamgriddb.com/api/v2"
SGDB_SEARCH_URL = SGDB_BASE + "/search/autocomplete/{term}"
SGDB_GRIDS_URL = SGDB_BASE + "/grids/game/{game_id}?dimensions=600x900&types=static"
SGDB_HEROES_URL = SGDB_BASE + "/heroes/game/{game_id}"

# Each candidate shown in the picker costs one extra request to fetch its thumbnail, so the
# list is kept short.
SGDB_PICKER_CANDIDATES = 5
# Where a key is made (Phase 79's first-run question links to it): the page SteamGridDB's own
# client library names, github.com/SteamGridDB/node-steamgriddb -- "Get your API key". Opened
# in the browser, never asked by the launcher.
SGDB_KEY_PAGE_URL = "https://www.steamgriddb.com/profile/preferences"
SGDB_CACHE_DAYS = 30

# Heroes for the banner cycle, used only for games with no Steam screenshots of their own.
# Short, because each is a full-size download, and paced because this service rate-limits
# like any other.
SGDB_HERO_CYCLE_MAX = 4
SGDB_REQUEST_GAP_SECONDS = 0.6
SGDB_NAME_CACHE_FILE = "sgdb_names.json"
SGDB_NAME_CACHE_DAYS = 30
SGDB_NAME_MISS_CACHE_DAYS = 7

# The same gate the Steam name search uses: a wrong match here would put another game's
# artwork on the banner.
SGDB_MATCH_RATIO = STEAM_SEARCH_MATCH_RATIO

# Missing covers, filled in one go (Phase 105): every request of the batch waits SGDB_REQUEST_GAP_SECONDS after
# the one before; SteamGridDB asking to slow down (HTTP 429) is waited out -- its Retry-After, or this long when
# it names none -- and asked once more. A second 429, or a Retry-After longer than the cap, stops the batch.
SGDB_BACKOFF_SECONDS = 30
SGDB_RETRY_AFTER_MAX_SECONDS = 60
SGDB_WAIT_SLICE_SECONDS = 0.1  # a wait looks this often whether Cancel was pressed
FILL_COVERS_SNAPSHOT_REASON = "before-fill-covers"  # the backup taken before the first cover is written
FILL_COVERS_REFRESH_MS = 1000  # the grid refreshed at most this often while covers land
FILL_COVERS_NAMED_MAX = 5  # the final message names this many games a kind, then "and N more"

# --------------------------------------------------------------------------------------
# Controllers
# --------------------------------------------------------------------------------------

CONTROLLER_ENABLED_DEFAULT = True

# Polled from the Qt event loop rather than a thread, so pad input and clicks arrive on the
# same timeline and nothing needs locking.
CONTROLLER_POLL_MS = 16

# A DualSense at rest reads about 0.035 on the left stick. This is far above that, so drift
# can never scroll the library on its own.
CONTROLLER_AXIS_DEADZONE = 0.55

# Held direction repeats: a pause after the first step so a single nudge moves exactly one
# tile, then a steady rate.
CONTROLLER_REPEAT_DELAY_MS = 420
CONTROLLER_REPEAT_RATE_MS = 110

# SDL will not give us an event queue without a video subsystem, and letting it initialise
# a real one inside a Qt process means two toolkits owning windows. The dummy driver gives
# SDL its queue and no window at all. Verified: pad polling works, Qt is untouched.
CONTROLLER_SDL_VIDEODRIVER = "dummy"

# --------------------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------------------

# Directory-size measurement for providers whose records carry no size (GOG, Ubisoft).
# Steam and Epic report their own, so they never pay for this walk.
MEASURE_INSTALL_SIZE = True

# --------------------------------------------------------------------------------------
# The two files that cannot be regenerated, and the snapshots that protect them
# --------------------------------------------------------------------------------------

# catalog.json rebuilds itself from disk and cache/ re-downloads, so neither is backed up.
# These two cannot be recovered from anywhere: overrides.json holds playtime, chosen
# artwork, custom names and hidden flags; config.json holds the scan roots and the
# SteamGridDB key.
PROTECTED_FILES = ("overrides.json", "config.json")

# The library database (Phase 67 on), beside them. A snapshot holds a copy of it too, made
# through SQLite's own backup rather than by copying the file of an open database
# (backups.py); the program uses it from Phase 69.
LIBRARY_DB_FILE = "library.db"
# Where the JSON files go once the migration has put the library into the database, each
# migration in a folder of its own named by its time -- moved, never deleted (Phase 69).
MIGRATED_DIRNAME = "migrated"

# Run from source, all of the above -- and the catalog, the log, cache/, backups/ and
# save_backups/ -- live in this one folder under the project (Phase 48), so the project's
# root holds the program and its data sits apart. An installed copy keeps its data beside
# its exe, as it always has.
DATA_DIRNAME = "data"

BACKUP_DIRNAME = "backups"
BACKUP_STAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

# Two tiers, on purpose. The recent tier covers "I broke something just now"; without the
# daily tier, a corruption nobody notices for a week would push every good copy out of a
# five-deep rotation before it was spotted.
BACKUP_KEEP_RECENT = 5
BACKUP_KEEP_DAILY_DAYS = 10

# --------------------------------------------------------------------------------------
# The scan that runs on its own when the launcher opens
# --------------------------------------------------------------------------------------

# On by default: a cached scan costs about 1.6 seconds and removes the need to remember to
# press Rescan after installing a game. Turned off in Settings for anyone who would rather
# the launcher touched nothing until asked.
STARTUP_SCAN_DEFAULT = True

# Long enough for the window to be on screen and for the startup messages to be posted
# before a scan begins competing for the same status bar.
STARTUP_SCAN_DELAY_MS = 1200

# --------------------------------------------------------------------------------------
# New games: the tag on the tile, and noticing one installed while the launcher is open
# --------------------------------------------------------------------------------------

# Written into a game's overrides record when a scan finds it for the first time, and
# removed the moment its page is opened or it is played. Only ever written together with
# first_seen, so a game the launcher already knew -- reinstalled into the same folder, or
# back on a drive that was unplugged -- never comes back as "new".
NEW_KEY = "new"

# The tag lets go on its own after this long, so something that is never opened -- a
# tool, a playtest nobody asked for -- does not wear it forever.
NEW_BADGE_DAYS = 14

# Watching the scan roots while the launcher is open. On by default, because the whole
# point is not having to remember Rescan; Settings turns it off.
WATCH_FOLDERS_DEFAULT = True

# Changes arrive in bursts -- a copy creates a folder and a dozen entries in one go -- so
# the top level of a root is re-read once they pause, not once per event.
WATCH_DEBOUNCE_MS = 1500

# A new folder is not scanned the moment it appears. An installer creates it first and
# then spends minutes, sometimes most of an hour, filling it; a game scanned half way
# through gets whichever exe happened to exist yet. So the folder is measured this often,
# and scanned once this many measurements in a row have found nothing written, created
# or grown -- three at 20 seconds is a full minute of silence.
WATCH_SETTLE_POLL_MS = 20_000
WATCH_SETTLE_CHECKS = 3

# Something that keeps writing for longer than this -- a game copied in and started
# straight away -- is scanned anyway rather than keeping the launcher waiting for good.
WATCH_GIVE_UP_S = 3 * 60 * 60

# Installers pause. Some spend minutes unpacking into a temporary folder elsewhere before
# writing the next file, which looks exactly like a finished install. A folder that has
# settled and been scanned is therefore still measured for this long afterwards, and
# scanned again if it changes and settles a second time.
WATCH_FOLLOW_UP_S = 15 * 60

# How deep the measurement goes. Deeper than the exe search (MAX_DEPTH), because this is
# not looking for a launch target -- it is looking for anything still being written.
WATCH_MEASURE_MAX_DEPTH = 12

# --------------------------------------------------------------------------------------
# Moving a library between machines
# --------------------------------------------------------------------------------------

# Bumped only if the bundle layout changes in a way an older build could not read. Import
# refuses a bundle from the future rather than half-understanding it.
TRANSFER_FORMAT = 1
TRANSFER_MANIFEST = "manifest.json"
# The records and the settings inside a bundle, by name. The same names the files have on
# disk today -- but a bundle's format does not change when the library moves into the
# database (Phase 69), so they are not PROTECTED_FILES, which says what is on disk.
TRANSFER_RECORDS_MEMBER = "overrides.json"
TRANSFER_CONFIG_MEMBER = "config.json"
# What the user paid (Phase 74), a file of its own in the bundle: written only when there are
# purchases, so a bundle without them is the same as before, and an older one still imports.
TRANSFER_PURCHASES_MEMBER = "purchases.json"
# A session's stars (Phase 102), the same way: written only when something is rated.
TRANSFER_RATINGS_MEMBER = "ratings.json"
TRANSFER_ART_DIR = "art"
TRANSFER_SUFFIX = ".gamelauncher.zip"

# Imported art is kept apart from the cache the app downloads for itself, so a later scan
# clearing its own cache can never delete artwork that arrived from another machine.
IMPORTED_ART_DIRNAME = "imported_art"

# Config keys that are lists of places to look. Merged as a union rather than replaced:
# the other machine's folders are worth adding, but losing this machine's would stop it
# finding its own games.
TRANSFER_UNION_KEYS = ("roots", "exclusions")

# Config keys that describe this machine rather than a preference, so they never travel:
# neither exported nor accepted on import. A window's size and position mean nothing on a
# computer with different screens.
TRANSFER_LOCAL_KEYS = ("window_geometry",)

# --------------------------------------------------------------------------------------
# Playtime
# --------------------------------------------------------------------------------------

# How often a running session's time is actually written to overrides.json. The poll loop
# runs far more often than this, because its other job is noticing that a game has closed;
# writing on every one of those would rewrite the file -- and repaint the grid -- every few
# seconds for hours. This is therefore the most that can be lost if the launcher is closed
# or crashes mid-session. A session that ends is always written immediately.
PLAYTIME_WRITE_INTERVAL_S = 60

# How often the window looks at the games it started: how much time to add, and whether each
# has ended. Moved here from ui_window in Phase 94, so the gap below is counted in one place.
PLAYTIME_POLL_MS = 3000

# The most one gap between two looks adds to a game's time: three looks' worth (Phase 94), the
# rule the process watcher uses for its own looks (Phase 93). Nothing looks while the PC sleeps
# or hibernates, and the clock the tracker reads -- time.monotonic(), QueryPerformanceCounter
# on this Windows -- is reported to keep counting through a sleep, so the first look after
# waking would add the whole night. A longer gap counts as this, and the log says so. When
# nothing sleeps every gap is one look (2.99-3.01 s, measured in Phase 53; banking never added
# more than 63 s in 982 saves from 25 September to 18 October), nothing is cut, and the total
# still agrees with the session to the second.
PLAYTIME_GAP_MAX_S = 3 * PLAYTIME_POLL_MS // 1000

# --------------------------------------------------------------------------------------
# "Play something" -- picking a game for the user
# --------------------------------------------------------------------------------------

# Every eligible game starts here and is multiplied by whichever rules below apply, so a
# game is never impossible to draw, only more or less likely.
PICK_BASE_WEIGHT = 1.0

# Recency first. Something played in the last week is the thing you are least likely to
# need suggesting, so it is halved -- discouraged, not excluded.
PICK_RECENT_DAYS = 7
PICK_RECENT_FACTOR = 0.5

# Playtime second, and only where playtime means anything. A barely-touched game is
# usually the one worth being reminded of.
PICK_BARELY_PLAYED_UNDER_S = 900  # 15 minutes
PICK_BARELY_PLAYED_FACTOR = 2.0

# **URI games have UNKNOWN playtime, not zero.** Steam, Epic and Xbox games are launched
# through their own client, and time spent there is invisible to this launcher -- most of
# them read as 0 seconds however much they have been played. Treating that as
# "barely played" would boost every one of them and Steam would win nearly every roll, so
# the boost above is only ever applied to exe games, whose playtime this launcher measures
# itself (Phase 16).
PICK_UNKNOWN_PLAYTIME_FACTOR = 1.0

# A mild nudge, deliberately smaller than the others: favorites should come up a little
# more often, not turn the roll into a favorites-only shuffle.
PICK_FAVORITE_FACTOR = 1.3

# The user's own verdicts (Phase 27). A game marked dropped is never suggested at all --
# being offered the thing you gave up on is the one suggestion that is plainly wrong. A
# finished one still comes up, half as often: replaying is real, but it is not usually
# what "play something" is asking for.
PICK_FINISHED_FACTOR = 0.5

# --------------------------------------------------------------------------------------
# Your own marks on a game: where you are with it, and a note
# --------------------------------------------------------------------------------------

# Both live in the game's overrides record, so they are kept exactly as playtime and
# artwork are: through an uninstall, and back again if the game is reinstalled into the
# same folder. Neither is ever inferred -- the launcher only records what the user said.
STATUS_KEY = "status"
STATUS_CHANGED_KEY = "status_changed_at"  # when the mark was last set or cleared (version 8, Phase 101)
NUDGED_KEY = "nudged_at"  # when Left behind's "Still playing" was last answered (version 8, written from Phase 103)
NOTES_KEY = "notes"
STATUS_PLAYING = "playing"
STATUS_FINISHED = "finished"
STATUS_DROPPED = "dropped"
STATUSES = (STATUS_PLAYING, STATUS_FINISHED, STATUS_DROPPED)

# A note is for "where I left off" and "the settings that worked", not a diary. The cap
# keeps one runaway paste from bloating overrides.json, which is rewritten on every save.
NOTES_MAX_CHARS = 4000

# --------------------------------------------------------------------------------------
# Steam news -- the sixth and only remaining endpoint
# --------------------------------------------------------------------------------------

# NOTE THE HOST. Every other Steam call in this project goes to store.steampowered.com;
# this one is api.steampowered.com, a different service. Still anonymous, still a
# read-only GET, still no account or key.
STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

# Asked for more than are shown, because the press items are filtered out afterwards and a
# game whose recent feed is mostly syndicated articles would otherwise come up empty.
STEAM_NEWS_FETCH_COUNT = 10
STEAM_NEWS_SHOW = 3

# Truncation is done by Steam, server side, from this parameter. Verified: a post longer
# than this comes back cut *and* with its markup already stripped; a shorter one comes back
# raw, which is why the BBCode stripping below still has to exist.
STEAM_NEWS_MAXLENGTH = 400
STEAM_NEWS_SNIPPET_CHARS = 220

# Only the publisher's own announcements. Verified against the live feed: those carry
# feed_type 1 and feedname "steam_community_announcements", while syndicated press
# carries feed_type 0 and the outlet's name -- Left 4 Dead 2 returns 3 publisher posts and
# 2 press articles, LEGO Batman 2 and 3. Patch notes only ever live in the publisher feed.
STEAM_NEWS_PUBLISHER_FEED_TYPE = 1
STEAM_NEWS_PUBLISHER_FEEDNAME = "steam_community_announcements"

# Much shorter than the art and app-type caches. Those describe things that essentially
# never change; news that is a month stale is simply wrong.
STEAM_NEWS_CACHE_DAYS = 1
STEAM_NEWS_MISS_CACHE_DAYS = 3
STEAM_NEWS_CACHE_FILE = "steam_news.json"

# --------------------------------------------------------------------------------------
# The anonymous export for analysis (Phase 80)
# --------------------------------------------------------------------------------------

# A participant's code in a thesis comparison: random, made at the first export and kept in
# config.json so two exports from one PC are known to be one person's -- and nothing else about
# them. Never in the diagnostics bundle (that one has paths): the two must not be joinable.
ANALYSIS_ID_SETTING = "analysis_id"
ANALYSIS_FORMAT = "game-launcher-analysis"
ANALYSIS_FORMAT_VERSION = 3  # 2 (Phase 93): how sessions were measured, launched or observed;
#                              3 (Phase 102): per game its ratings (the stars, the session's day) and the day
#                              its mark was set
ANALYSIS_FILE_PREFIX = "GameLauncher-anonymous"
# Sessions leave only as totals by month, hour and weekday -- never their times -- named so.
# (A purchase's store leaves as one of PURCHASE_STORES, else "other": the field is typed, and
# typed text is not exported.)
ANALYSIS_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# The comparison of several exports (Phase 81, compare_exports.py): where the friends' files go
# (inside the data folder, git-ignored), where the report is written, and a file no bigger than
# this is read -- a real export is about 70 KB.
COMPARISON_DIRNAME = "exports"
COMPARISON_REPORT_DIRNAME = "comparison"
COMPARISON_MAX_BYTES = 20_000_000
COMPARISON_TOP_GENRES = 6
COMPARISON_TOP_GAMES = 5
COMPARISON_COMMON_GAMES = 25
# The report's colours: the dataviz reference palette (categorical slots in their validated order,
# the blue ramp for the similarity map, chrome and ink), light and dark. A report is not the
# launcher's window, so these live here, not in ui_rules (which only presentation/ may read).
REPORT_SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
REPORT_SERIES_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767")
REPORT_RAMP = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")

# --------------------------------------------------------------------------------------
# The update check -- the seventh endpoint (Phase 79), installed copies only
# --------------------------------------------------------------------------------------

# A third host: api.github.com, GitHub's releases of a public repository that holds only the
# installers (the code's own repository is private, and a private one cannot be read without
# a password, which must never be in a file handed to anyone). Anonymous, read-only, no key.
# Verified on 11 October: a release answers 200 with tag_name, draft, prerelease,
# published_at; a repository with no release yet answers 404 {"message": "Not Found"}; 60
# questions an hour are allowed from one connection, and this asks at most once a day.
UPDATE_REPOSITORY = "GreenYRO/game-launcher-releases"
UPDATE_LATEST_URL = f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases/latest"
# What the download button opens, in the browser. Always this page: never an address taken
# from GitHub's answer.
UPDATE_PAGE_URL = f"https://github.com/{UPDATE_REPOSITORY}/releases/latest"
UPDATE_USER_AGENT = "game-launcher (update check; no data collected)"
UPDATE_ACCEPT = "application/vnd.github+json"
UPDATE_API_VERSION = "2022-11-28"
UPDATE_TIMEOUT_SECONDS = 10
# An answer is good for a day; a question nobody answered is asked again after a few hours.
UPDATE_CHECK_HOURS = 24
UPDATE_RETRY_HOURS = 6
UPDATE_CACHE_FILE = "update_check.json"
# After the window appears, behind the startup scan (STARTUP_SCAN_DELAY_MS).
UPDATE_CHECK_DELAY_MS = 6000

# --------------------------------------------------------------------------------------
# Session history
# --------------------------------------------------------------------------------------

# One session is one exe launch, from start until the job reports itself empty. Kept in
# overrides.json under this key, as a list of {"start": iso, "minutes": n}.
SESSIONS_KEY = "sessions"

# Pruned by age rather than by count, so one mechanism serves both the short "recent
# sessions" list and a twelve-month chart. A little over a year, so the chart's oldest
# month is still complete on the day it rolls over.
SESSION_KEEP_DAYS = 400

# Below this a session is noise -- a game that failed to start, or a mis-click -- and
# recording it would fill the list with entries nobody wants to read.
SESSION_MIN_MINUTES = 1

# How a session was measured (Phase 93; session.origin, version 7). 'launched': the launcher started
# the game and timed it to the second. 'observed': it saw the game in the process list, whoever
# started it -- each edge uncertain by one look. Only 'observed' is written into a record's session
# dict; a session that does not say is 'launched', the only kind there was before.
SESSION_ORIGIN_KEY = "origin"
SESSION_LAUNCHED = "launched"
SESSION_OBSERVED = "observed"

# The exit code handed to a game the user stops from the launcher. Non-zero so that
# anything inspecting it can tell a deliberate stop from a clean quit.
STOP_EXIT_CODE = 1

# Written out rather than taken from the locale, so the chart's twelve labels are always
# three characters wide and the columns line up whatever machine this runs on.
MONTH_ABBREVIATIONS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# --------------------------------------------------------------------------------------
# Controller battery
# --------------------------------------------------------------------------------------

# Read on a slow timer and never in the input path: the level changes over hours, and a
# poll that runs alongside button reads would cost something 60 times a second for nothing.
CONTROLLER_POWER_POLL_MS = 60000

# What SDL answers. "wired" and "unknown" both mean there is no battery reading to show --
# the first because it is plugged in, the second because the device will not say.
POWER_UNKNOWN = "unknown"
POWER_WIRED = "wired"
# Ordered emptiest first; the index into this list is how many bars are drawn.
POWER_STEPS = ("empty", "low", "medium", "full", "max")
# Below this many steps the glyph is drawn in the warning colour.
POWER_WARNING_BELOW = 2

# Whose buttons the pad in your hands has printed on it (Phase 50), so the TV hint bar can
# draw those. SDL maps every pad onto one Xbox-shaped layout -- the bottom face button is
# "A" whatever is printed on it -- so the family changes the pictures, never what a button
# does. Decided from the pad's name: anything not recognisably PlayStation is drawn as
# Xbox, which is also what an 8BitDo Ultimate 2C has printed on it. Never "wireless
# controller": that is in the 8BitDo's name too.
PAD_XBOX = "xbox"
PAD_PLAYSTATION = "playstation"
CONTROLLER_PLAYSTATION_WORDS = ("dualsense", "dualshock", "playstation", "sony", "ps5", "ps4", "ps3")

# --------------------------------------------------------------------------------------
# Reclaimable space
# --------------------------------------------------------------------------------------

# A game untouched this long is offered as something to reclaim. Six months, in days,
# because everything else here counts in days. It is a suggestion and nothing more: the
# storage page can delete nothing.
RECLAIM_STALE_DAYS = 183

# How the "biggest and coldest" sort trades size against staleness: a game idle this long
# counts as twice its size. Long enough that size still dominates -- freeing 200 MB is not
# the answer to "what is eating my disk", however cold that 200 MB is.
RECLAIM_WEIGHT_DAYS = 365

# --------------------------------------------------------------------------------------
# Uninstalling, tiered by who owns the install (Phase 25)
# --------------------------------------------------------------------------------------

# The only tier that deletes anything, and it exists for folder-scanner entries alone:
# nothing else on this machine is ours to remove.
TIER_DELETE = "delete"          # shell delete to the Recycle Bin
TIER_UNINSTALLER = "uninstaller"  # run a real uninstaller the game shipped
TIER_STORE = "store"            # hand it to the store's own uninstall flow
TIER_OWNER = "owner"            # open whoever owns it; we cannot do more
TIER_BLOCKED = "blocked"        # refused, with a reason

# An uninstaller sitting at the *root* of a game folder. Only the root: something found by
# searching subfolders could belong to a bundled component rather than to the game, and
# running the wrong uninstaller is not a recoverable mistake. Measured on this machine:
# one folder game ships one here, while three more keep theirs a level down and therefore
# fall through to the Recycle Bin route, which is safe for them.
UNINSTALLER_ROOT_GLOBS = ("unins*.exe", "uninstall*.exe")

# Verified against this machine's own registry, not from documentation: every installed
# Steam game's UninstallString in HKLM\...\Uninstall is literally steam.exe with this URI.
STEAM_UNINSTALL_URI = "steam://uninstall/{appid}"

# GOG records a real uninstaller command per game. Read, never constructed; the file has
# to exist before the button offers to run it.
GOG_UNINSTALL_VALUE = "uninstallCommand"

# No verified programmatic uninstall exists for these, so the button opens their owner and
# says so. All three schemes were read out of this machine's registry before being used.
EPIC_LIBRARY_URI = "com.epicgames.launcher://apps"
UBISOFT_CLIENT_URI = "uplay://"
# Registered by the windows.immersivecontrolpanel package; confirmed present with a
# URL Protocol value.
XBOX_APPS_URI = "ms-settings:appsfeatures"

# Longer than an ordinary status message: a game leaving the library is worth reading.
UNINSTALL_STATUS_MS = 12000

# --------------------------------------------------------------------------------------
# The log file
# --------------------------------------------------------------------------------------

# The launcher runs under pythonw.exe, which has no console, so before Phase 26 everything
# it logged -- a crash's traceback included -- went nowhere. It now also goes to this file
# beside the data. Rotated, keeping two old copies, so yesterday's problem is still there
# to read and the whole thing can never grow past a few megabytes.
LOG_FILENAME = "launcher.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 2
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

# --------------------------------------------------------------------------------------
# Saves: finding them by watching what a game wrote while it ran, and keeping copies
# --------------------------------------------------------------------------------------

# Where games on this machine were seen saving, read off the disk against the recorded
# play sessions before any of this was written: Unreal games under LocalAppData
# (<project>\Saved\SaveGames, often under an internal project name -- "Ride", "Ravage"),
# Unity under LocalLow, the Steam emulators in Roaming ("GSE Saves", "Goldberg
# SteamEmu Saves") and in Public Documents (Steam\RUNE), Cyberpunk in Saved Games, and
# CULTIC inside its own game folder. Resolved through SHGetKnownFolderPath, never by
# assembling a path under the user profile.
SAVES_KNOWN_FOLDERS = (
    "FOLDERID_LocalAppData",
    "FOLDERID_LocalAppDataLow",
    "FOLDERID_RoamingAppData",
    "FOLDERID_Documents",
    "FOLDERID_SavedGames",
    "FOLDERID_PublicDocuments",
)

# Skipped while walking, for speed only -- the rules below decide what counts. Every one
# of these was seen filling up with writes during play sessions here (graphics driver
# caches, browsers, store apps, Office) and none held a save. A tracked game is an exe
# game, so the Store apps' Packages folder never holds one of its saves.
SAVES_WALK_SKIP = {
    "FOLDERID_LocalAppData": (
        "Packages", "Microsoft", "Google", "Temp", "CrashDumps", "D3DSCache",
        "NVIDIA", "NVIDIA Corporation", "imput", "Wand", "Mozilla",
    ),
    # Mozilla since Phase 36: Firefox writes its profile all through a session, and its
    # "saved-telemetry-pings" folder was taken for Slow Roads' saves on timing alone.
    "FOLDERID_RoamingAppData": ("Microsoft", "NVIDIA", "Claude", "WeMod", "Mozilla"),
}
SAVES_MAX_DEPTH = 10

# Never a save folder, whatever is inside it (Phase 36). A crash reporter's queue holds a
# copy of the save that was loaded when the game fell over -- The Witcher 3's REDEngine
# ReportQueue was taken for its saves, and restoring it would have queued a stale crash
# report to send -- and telemetry is a program reporting on itself. Path components, whole
# and case-blind; the words match anywhere inside a component.
SAVES_NEVER_PARTS = (
    "reportqueue", "crashreports", "crash reports", "crashes", "crashdumps", "crashpad",
    "crashreporter", "minidumps",
)
SAVES_NEVER_WORDS = ("telemetry",)

# A game may write its save as it closes, and a session's end is only noticed on the next
# three-second poll, so a write this long after the recorded end still belongs to it.
SAVES_SESSION_SLACK_S = 180

# A save-shaped folder that matches neither the game's name nor its appid is only taken
# if at least this share of the writes made to it since the game was first played
# happened while the game was running. That is what keeps another program's saves -- a
# Minecraft world autosaving in the background -- from being mistaken for this game's.
SAVES_OWNED_FRACTION = 0.5

# Keys in a game's overrides record.
SAVE_DIRS_KEY = "save_dirs"
SAVE_DIRS_CHECKED_KEY = "save_dirs_checked"
SAVE_DIRS_IGNORED_KEY = "save_dirs_ignored"

# --------------------------------------------------------------------------------------
# A new version of a game you had (Phase 36)
# --------------------------------------------------------------------------------------

# A record is keyed by where the game was installed, so a new build in a new folder -- or
# a GOG install replaced by a folder copy -- starts with no past. These keys let its
# history follow it, when the user says it is the same game.
KNOWN_AS_KEY = "known_as"  # the name the launcher last saw it under, for once it is gone
EARLIER_KEYS_KEY = "earlier_keys"  # on the new record: the installs it carries on from
CARRIED_TO_KEY = "carried_to"  # on the old record: where its history went
CARRIED_AT_KEY = "carried_at"
NOT_SAME_KEY = "not_same_as"  # earlier installs the user said are a different game

# Moved across as they are: summed, merged or kept, field by field, in lineage.carry_over.
# Everything about the old *folder* -- a hand-picked exe, the hidden flag, when its saves
# were last looked for -- stays behind, because it described a folder that is gone.
CARRY_IF_MISSING = ("name", "cover", "banner", "appid", "args", "is_tool",
                    "status", "notes")

# How names are compared. Edition words are dropped first, so "Deluxe Edition" and
# "Complete Edition" of one game compare equal; then one name must start with all of the
# other's words. The Witcher 3 is exactly this: "The Witcher 3" against "The Witcher 3:
# Wild Hunt - Game of the Year Edition". A one-word name must match whole -- "Control"
# is not "Control Resonant" -- and a number straight after the shared words is a sequel:
# "Far Cry" is not "Far Cry 3". Spacing and punctuation never matter ("Spider-Man" is
# "Spiderman"); letters that are merely alike never count -- "Silent Hill 2" and "Silent
# Hill f" are 91% alike, and the first version of this rule took them for one game.
TITLE_EDITION_PHRASES = (
    "game of the year edition", "game of the year", "goty", "complete edition",
    "definitive edition", "ultimate edition", "deluxe edition", "enhanced edition",
    "gold edition", "standard edition", "digital deluxe edition", "special edition",
)
TITLE_MIN_PREFIX_WORDS = 2
TITLE_SEQUEL_NUMERALS = ("ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x")

# Copies of a game's saves, one zip per backup, beside the data. Kept: the newest
# SAVES_BACKUP_KEEP per game. A save folder bigger than SAVES_BACKUP_MAX_BYTES is not
# copied -- that is a cache or a world folder, not a save -- and the page says so.
SAVES_BACKUP_DEFAULT = True
SAVES_BACKUP_DIRNAME = "save_backups"
SAVES_BACKUP_KEEP = 10
SAVES_BACKUP_MAX_BYTES = 1_000_000_000
# ...and only on real evidence: a folder claimed by timing alone needs at least this many
# writes during the game's sessions. One stray write once did it with one.
SAVES_OWNED_MIN_WRITES = 2

# The first look for saves happens once per game, this long after the window appears --
# after the startup scan, so the two walks never compete for the disk.
SAVES_STARTUP_DELAY_MS = 8000

# --------------------------------------------------------------------------------------
# The project folder can move (Phase 37)
# --------------------------------------------------------------------------------------

# The folders beside the data that the launcher fills itself. A path written into
# overrides.json that leads into one of these -- a cover picked from the cache, a banner
# from imported art -- is looked for again under the current data folder when the old
# one is gone, so renaming or moving the project does not lose anyone's chosen artwork.
OWN_DATA_FOLDERS = ("cache", BACKUP_DIRNAME, SAVES_BACKUP_DIRNAME)

# The artwork fields of an overrides record: the ones that hold such paths.
ARTWORK_KEYS = ("cover", "banner")

# --------------------------------------------------------------------------------------
# What the logic reports, not how it looks (Phase 46)
# --------------------------------------------------------------------------------------

# Moved here unchanged from ui_rules.py: stats, gamedetails and the screenshot worker read
# them, and nothing below the interface may depend on the appearance file.

# "folders" is what the scanner calls itself and is meaningless to anyone else; the rest
# are shown the way their owners spell them.
SOURCE_LABELS = {
    "folders": "Found on disk",
    "steam": "Steam",
    "gog": "GOG",
    "epic": "Epic",
    "xbox": "Xbox",
    "ubisoft": "Ubisoft",
}

# A year of columns. Twelve fits comfortably at every scale and matches the pruning
# window, so the chart can never want a month that has already been dropped.
STATS_CHART_MONTHS = 12
STATS_TOP_GAMES = 5

# --------------------------------------------------------------------------------------
# For you (Phase 98): what is waiting, most like what you play; and what fits tonight
# --------------------------------------------------------------------------------------

FORYOU_GAMES = 3  # the waiting games shown large; the rest are a line each
FORYOU_MORE = 12  # the most of the rest the page lists; past that, how many more
FORYOU_TONIGHT = 3  # the games Tonight offers
# A game played in the last this many days is not offered as waiting: Jump back in and the Continue card
# already offer it (the user's yes, 18 October -- Max Payne 3, played the day before, read first).
FORYOU_RECENT_DAYS = 7
# Tonight's choices: (minutes, the chip's words, the words for "within" it). An evening is three hours.
TONIGHT_CHOICES = ((30, "30 min", "within 30 minutes"), (60, "1 h", "within an hour"),
                   (120, "2 h", "within two hours"), (180, "An evening", "within an evening"))
TONIGHT_DEFAULT = 60
FORYOU_TONIGHT_KEY = "foryou_tonight"  # config.json: the choice, in minutes, remembered
# A typical session is the median of a game's sessions, both origins, once it has this many; fewer is not judged.
SESSION_MEDIAN_MIN = 3
# Left behind (Phase 103): a game marked Playing that nothing has been heard of for this many days -- no counted
# session, no mark set, no nudge answered -- is asked about in For you, at most LEFT_BEHIND_GAMES at a time, the
# longest left first. "Still playing" leaves it alone for as many days again.
LEFT_BEHIND_DAYS = 30
LEFT_BEHIND_GAMES = 4

# --------------------------------------------------------------------------------------
# The recap (Phase 96): a month, or a year, in review -- one image to pass on
# --------------------------------------------------------------------------------------

RECAP_TOP_GAMES = 3  # covers on a month's card
RECAP_YEAR_TOP_GAMES = 5  # and on a year's
RECAP_NEW_GAMES = 3  # the games new in the period named on the card; the rest are counted
# The parts of the day a session's start falls in, by its local hour: [first, last), the card's words.
RECAP_DAY_PARTS = ((0, 6, "after midnight"), (6, 12, "in the morning"), (12, 18, "in the afternoon"),
                   (18, 24, "in the evening"))
RECAP_WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")  # SQLite's %w
# Written out, as MONTH_ABBREVIATIONS is, never taken from the locale.
RECAP_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August",
                     "September", "October", "November", "December")
# The year's card is offered from this day of December (month, day), and through January.
RECAP_YEAR_OFFER_DAY = (12, 15)
# config.json, each by its own key: the month ("2026-10") and the year ("2026") whose offer was shown.
RECAP_OFFERED_KEY = "recap_offered"
RECAP_YEAR_OFFERED_KEY = "recap_year_offered"
RECAP_OFFER_DELAY_MS = 9000  # after the window's own start-up messages
# Where Save image... opens, as Windows names the folder; the file's name.
RECAP_SAVE_FOLDER = "FOLDERID_Pictures"
RECAP_FILE_NAME = "{app} - {period}.png"

SCREENSHOT_MIN_BYTES = 3000  # anything smaller is not a real screenshot

# --------------------------------------------------------------------------------------
# Reports (Phase 83): what the library database can say, one query at a time
# --------------------------------------------------------------------------------------

# Steam apps whose hours are not one game's: set aside from every report's figures and shown
# on their own in the data-quality report -- left out at analysis, never at collection (the
# database and the friends' anonymous exports keep them as read). The comparison of the
# friends' exports sets them aside the same way. Both have no store page, so the names are
# written here.
STEAM_NOT_GAMES: dict[int, str] = {
    # Spacewar: Valve's own test app. A game that uses Steam's API without being sold on Steam
    # -- a mod, a fan port, an unofficial copy -- reports its time under this appid, so these
    # hours are some other game's, and which one cannot be told.
    480: "Spacewar",
    # Source SDK Base 2007: the engine base Source mods are started on; its hours are the mods'.
    218: "Source SDK Base 2007",
}

# Steam files these as genres; the profile report keeps them out of the genre bars. "Free To
# Play" is a business model -- the price, not the kind of game -- so it gets a line of its own
# (the share of hours on free titles, which is what the money report's cost per hour leans on).
# The others are a release state and content descriptors. Steam's own ids, read off this PC's data.
STEAM_FREE_TO_PLAY_GENRE = 37
STEAM_NOT_GENRES: dict[int, str] = {37: "Free To Play", 70: "Early Access", 72: "Nudity", 73: "Violent"}

REPORT_TOP_ROWS = 20                       # the concentration table's rows
REPORT_CONCENTRATION_TOPS = (1, 5, 10, 20)  # "the top N apps hold X% of the hours"
REPORT_CONCENTRATION_MARKS = (0.5, 0.8)    # "N apps make half (80%) of all hours"
# Abandonment buckets, in minutes of Steam time. Two hours is Steam's refund window: a game
# played for less than that, within 14 days of buying it, can be refunded.
REPORT_TEN_MINUTES = 10
REPORT_ONE_HOUR = 60
REPORT_REFUND_WINDOW_MINUTES = 120
REPORT_TEN_HOURS = 600
REPORT_HUNDRED_HOURS = 6000
# What kind of app each started game is (Phase 91): the business model confounds "dropped early" --
# a free game is tried because trying costs nothing -- so report 2 counts paid games on their own.
#   free:    Steam's is_free flag, OR the Free To Play genre (STEAM_FREE_TO_PLAY_GENRE). Both count
#            because each catches titles the other misses: on 16 October, of the games started, 65
#            carried both, 8 only the flag (games given away free -- Cry of Fear, Life is Strange
#            Episode 1) and 20 only the genre (free-to-play titles whose record lacks the flag --
#            Loadout, Robocraft).
#   unknown: no store record (steam_app.has_record = 0, or no steam_app row): nothing can be said.
#   paid:    the rest, "no longer sold" included (it was sold once).
# The query (data_access/reports.ABANDONMENT) writes these three words; here are their names.
REPORT_APP_KINDS = {"paid": "Paid", "free": "Free to play", "unknown": "No store record"}
REPORT_PROFILE_ROWS = 10                  # bars per profile (genre, publisher, developer)
REPORT_BACKLOG_UNDER_MINUTES = 120         # "installed, played under two hours in total"
REPORT_SESSION_EDGES = (15, 30, 60, 120)   # session length buckets, in minutes
REPORT_NIGHT_ENDS = 6                      # the night is 00:00-05:59 local wall time
REPORT_PROXY_MIN_MINUTES = 60              # a list price per hour only for games played an hour or more
REPORT_LIST_ROWS = 10                      # rows of a ranked list (sales, prices, value per hour)
REPORT_LOOK_BACK_MIN = 10                  # report 9: fewer evenings than this, and a hit rate says little
REPORT_COMPANY_ROLES = ("publisher", "developer")  # report 3's two lists, as steam_app_company names them
# Report 10, Said and played (Phase 102): the stars set against the hours, and against the fit.
REPORT_RATED_MIN = 2                       # a game's mean stars only from this many rated sessions
REPORT_SPEARMAN_MIN = 5                    # fewer games than this, and no correlation is worked out
REPORT_SPEARMAN_HINT = 10                  # fewer than this, and a correlation is a hint, never a finding
# A rank correlation's size in words, by |rho|: under 0.2 little or none, under 0.4 weak, ... (the usual rough
# bands; a convention, not a test).
REPORT_CORRELATION_WORDS = ((0.2, "little or no"), (0.4, "a weak"), (0.6, "a moderate"), (1.01, "a strong"))
REPORT_RATED_WELL = 4.0                    # a disagreement: rated this or better on average ...
REPORT_BARELY_PLAYED_MINUTES = 120         # ... and played under two hours in all
REPORT_RATED_LOW = 2.5                     # or rated this or lower on average ...
REPORT_PLAYED_MUCH_MINUTES = 600           # ... and played ten hours or more
# Report 11, Finishing (Phase 103): a completion rate on fewer decided games (finished or dropped) than this is
# said to be a hint, not a finding.
REPORT_DECIDED_MIN = 5

# --------------------------------------------------------------------------------------
# Running in the background (Phase 92): the tray, a hidden start, the tick, Start with Windows
# --------------------------------------------------------------------------------------

# Settings' "Keep running when the window is closed": closing hides the window into the tray and
# the launcher goes on -- timing a running game, watching the folders, taking its readings. Off by
# default, so no copy changes behaviour until someone turns it on.
KEEP_RUNNING_KEY = "keep_running"
KEEP_RUNNING_DEFAULT = False

# Written the first time a close hides the window: the tray says once where the launcher went.
TRAY_HINT_KEY = "tray_hint_shown"

# The one question (Phase 99): with the switch off, once, a second after the window first appears -- would
# they like it to stay in the tray? Never on a first run's start, never twice: the day it was asked is kept
# under its own key, whichever the answer. Settings' OK writes the switch off even when it was never
# touched, so an absent key could not tell "never chose" from "chose off": the switch being off is the gate.
TRAY_OFFER_KEY = "tray_offer_shown"
TRAY_OFFER_DELAY_MS = 1000  # after the window's first paint, not before it
TRAY_OFFER_RETRY_MS = 2000  # another dialog is up: asked again this long after
TRAY_OFFER_TRIES = 30  # and given up for this start after this many tries (a minute)

# Starting... (Phase 99): from Play until the game is up. It ends when the game takes the screen, the tracker
# sees it close at once, the watcher sees a store's game running, Escape or a click -- or after this long at
# most, a backstop: step 0 measured Play to the process handed back at 0-4.4 s, 13.1 s once (Hellraiser's first
# start, Windows checking a new program), and Steam can take 10-30 s more when it is not open yet.
LAUNCH_SPLASH_MAX_S = 30
LAUNCH_ON_A_THREAD = ("exe",)  # what starts off the GUI thread: Windows' start call is the wait; an address is quick

# The genre pill (Phase 99): Steam's genres, less the two that are content warnings rather than kinds of game
# (Nudity 72, Violent 73). Free To Play and Early Access stay: they answer "what can I play for free", "what is
# unfinished".
GENRE_FILTER_LEFT_OUT = (72, 73)

# The version that last ran (Phase 99), written at every start but a first run's. Since Phase 106 it gates What's
# new: the first start after an update finds another version here, shows the notes a moment after the window
# appears, and writes this one only once they are closed -- a start hidden in the tray writes nothing.
VERSION_SEEN_KEY = "version_seen"
WHATS_NEW_DELAY_MS = 1000  # after the window appears, as the tray offer; the offer then waits for the notes
WHATS_NEW_RETRY_MS = 2000  # the window not to be seen, or another dialog up: shown this long after
WHATS_NEW_TRIES = 30  # and left for the next shown start after this many tries (a minute)
# Each version's release notes (Phase 106): docs/release-notes/<version>.md, the Romanian under its heading and the
# English under its own -- the GitHub release's body is the file. Bundled at the same place below the program's
# resources; a build of a version without one is refused.
RELEASE_NOTES_DIR = ("docs", "release-notes")
RELEASE_NOTES_HEADINGS = ("## Română", "## English")

# One launcher at a time: a second start asks the running one to show itself, and gives up after this
# long without an answer -- the running one is wedged, and is said to be; it is never started over.
# Long enough for a launcher still building its window (a second or two) to answer.
SINGLE_INSTANCE_TIMEOUT_MS = 10000
SINGLE_INSTANCE_RETRY_MS = 200  # between tries of the channel while the running one gets ready
SINGLE_INSTANCE_PREFIX = "GameLauncher-"  # the lock's and the channel's name, then the data folder's hash

# A start with no window, the tray icon only: what Start with Windows runs.
BACKGROUND_ARGUMENT = "--background"

# At sign-in Windows starts the Run entries before the shell has its tray. A hidden start waits for
# it this often, this long; if it never comes the window is shown -- the launcher is never left
# running with no window and no icon.
TRAY_RETRY_MS = 2000
TRAY_RETRY_MAX_S = 120

# The tick: while the launcher runs -- the window shown or in the tray -- this often it asks whether a
# reading is due (prices.due, wishlist.due, Steam's playtime files written since the last scan) and,
# when one is and nothing stands in the way, runs a quiet scan that takes it. The due rules keep their
# own cadences; the tick only asks. The update check, asked with it, keeps its own once a day
# (UPDATE_CHECK_HOURS). A tick's scan is recorded as a "watch" scan (the user's choice: the database's
# reasons for a scan are fixed, and a new one would be a schema change); launcher.log says "tick".
BACKGROUND_TICK_MINUTES = 30
# Steam's playtime files are due for a tick's scan only when they were written since the last scan AND
# either a Steam game was seen being played since (Phase 93's watch) or the last scan is this old. Steam
# rewrites localconfig.vdf with no play at all: on 18 October the tick scanned every half hour for it
# (00:48, 01:18, 01:48), each time reading the same counters. Its counters only move when a game is played.
STEAM_TIME_TICK_HOURS = 12

# Start with Windows: the launcher's value in the user's Run key, and Windows' own on/off for it.
STARTUP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
STARTUP_VALUE_NAME = "Game Launcher"
# A test -- or check_installer.py, whose installed copy is another process -- names another key root
# here, and the two keys are looked for under it instead: <root>\Run and <root>\StartupApproved\Run.
# Read only when it is set; nothing sets it on anyone's PC.
STARTUP_TEST_KEY_ENV = "GAME_LAUNCHER_TEST_STARTUP_KEY"
# A test copy of the data never starts one of the user's games (Phase 103: on 21 October a suite's pad, its
# window not in front, pressed Play and started two). tests/test_sandbox.py names the copy's folder in this
# variable; there only a suite's fake game -- its folder in the temp folder -- starts, and any other start is
# refused as if made and written into the folder, so the suite says so at its end.
TEST_COPY_ENV = "GAME_LAUNCHER_TEST_COPY"
TEST_COPY_STARTS = "starts_refused.txt"

# --------------------------------------------------------------------------------------
# Games started outside the launcher (Phase 93): the process list, matched to the games here
# --------------------------------------------------------------------------------------

# Settings' "Notice games started outside the launcher" (Running in the background). On by default:
# it only reads the names and paths of the processes on this PC and keeps nothing but the sessions
# of games the launcher already knows. The first day it watched, written once by its own key, is
# what every caveat means by "since".
WATCH_GAMES_KEY = "watch_games"
WATCH_GAMES_DEFAULT = True
WATCH_SINCE_KEY = "watch_games_since"

# One look at the process list this often, on a thread of its own: 3.0 ms a look on 18 October (321
# processes, median of 20), so a look every five seconds costs well under a thousandth of the time.
WATCH_PROCESS_POLL_S = 5
# A look is expected under this; one that takes longer is said once in the log, and a test holds it.
WATCH_ENUMERATION_MAX_MS = 30
# A game is gone after this many looks in a row that see none of its processes. Measured on 18 October
# with Aimlabs started from Steam: its 7 processes left between two looks and none came back in 19, and
# none was missing at the start either -- a gap of 0 looks. One look more than that, so a starter that
# hands over to the real exe in the instant between two looks is never taken for the game ending.
WATCH_GONE_POLLS = 2
# A gap between two looks that saw the game counts at most this long (three looks' worth): a PC that
# sleeps with a game open counts seconds of it, not the night.
WATCH_GAP_MAX_S = 15
# An observed session longer than this is still recorded, and said at warning in the log.
SESSION_MAX_HOURS = 12

# The no-double-count rule: a game from one of these stores has its hours on the store's own counter
# (Steam's, read since Phase 75 and added in v_hours), so an observed session of it keeps its shape --
# when, how long -- and never adds to playtime_seconds. Every other game's observed minutes are its hours.
HOURS_KEPT_BY_STORE = frozenset({"steam"})

# Steam types a watched game may have, when the appid is certain: a demo or a mod is played like a game;
# anything else Steam calls a tool, an application, a soundtrack, is never watched.
WATCH_GAME_TYPES = frozenset({"game", "demo", "mod"})
