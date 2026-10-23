# Handoff: Game Launcher — the Nocturne restyle

Paste the **Prompt for Claude Code** section into Claude Code, run from the project folder (`Game Launcher`, the PySide6 launcher whose `CLAUDE.md` describes phases 0–53). Keep this whole folder next to the project (e.g. `docs/design/nocturne/`) so Claude Code can open the files it names.

## About the design files

`Launcher Mockups.dc.html` is a **design reference built in HTML**, not code to ship. It shows the intended look of six screens; the job is to recreate that look **inside the existing Qt app** — in `presentation/ui_rules.py`, the `stylesheet()` functions, and the widgets that paint themselves — using the mechanisms that already exist there. Nothing moves to QML or a web view.

Every value in the mockup is an inline `style="…"` in that file, so exact numbers can be read straight from the source. Design tokens are CSS variables defined in `_ds/nocturne-…/styles.css` (`--color-*`, `--radius-*`, `--shadow-*`); the table in the prompt resolves them to hex. The `<script>` block at the bottom of the mockup holds the sample data (the game list, pills, sessions, months, storage rows) and nothing visual.

Open the HTML in a browser to see it; use the hash links `#1a` … `#1f` to jump to a screen.

## Fidelity

**High-fidelity for appearance** — colours, type, radii, borders, button treatment, spacing. Match it closely.

**Layout:** `1a`, `1d`, `1e`, `1f` keep the layout the app has today (top bar, Continue playing card, chips, cover grid; the game page; Stats; Storage) and only restyle it. `1b` (side rail) and `1c` (Spotlight) are **new layouts** and are optional, separately gated phases at the end.

Playtimes, sizes and stats in the mockup are illustrative. The cover art is the user's own, from `data/cache/steam_art`.

---

## Prompt for Claude Code

> Read `CLAUDE.md` first and keep every rule in it: one phase at a time, show the result, stop, wait for my go. This is an **appearance-only** change set. No file outside `presentation/` changes, and nothing about finding, launching, timing or saving games changes. Verify every phase by rendering (`QWidget.grab().save(...)` at 1280×820, as `CLAUDE.md` says), set the render side by side with the matching screen in `docs/design/nocturne/Launcher Mockups.dc.html` (open it in a browser; `#1a`–`#1f`), and fix what differs before showing me. Run `.venv\Scripts\python.exe tests\run_all.py` at the end of each phase; a test that asserts an old colour or radius is updated to the new value, never deleted or loosened.
>
> **What the design is.** The launcher moves to the "Nocturne" look: a near-neutral blue-grey ground, Inter at medium weight, 8 px radii, one blurple accent used as **lines and glows, never as a fill**. Primary actions — including **Play** — are an outlined button (1 px accent border, accent text, dark glass fill over art), not the green pill. Cards are solid surfaces with a 1 px hairline edge instead of translucent white glass. Scrims and fades use the ground colour so art blends into the page. No pure black or pure white anywhere; every value comes from the ramps below.
>
> **Tokens.** Put these in `presentation/ui_rules.py` (that is the only place a colour or size may live). Where a constant already exists, change its value; where the mockup needs a new one, add it next to its neighbours with the same kind of comment the file already uses.
>
> | Role | Hex | Replaces |
> | --- | --- | --- |
> | Ground | `#161826` | `COLOR_BACKGROUND`, and `COLOR_SCRIM` (scrims now use the ground) |
> | Surface (cards, inputs, menus) | `#232532` | `COLOR_SURFACE`; also `COLOR_CARD` (cards become solid) |
> | Raised surface | `#292b31` | `COLOR_SURFACE_RAISED`; also `COLOR_STORAGE_FREE`, `COLOR_CHART_BASELINE`, the empty session-bar track |
> | Hairline edge | `#3f424d` | `COLOR_BORDER`, `COLOR_CARD_BORDER`, `COLOR_SWITCH_OFF`, `COLOR_CHART_UNRECORDED` |
> | Divider on glass | `rgba(233,233,237,41)` (= text at 16 %) | `COLOR_CHIP_BORDER`, `COLOR_PILL_BORDER`, `COLOR_GHOST_BORDER`, `COLOR_NAV_BORDER` |
> | Text | `#e9e9ed` | `COLOR_TEXT` |
> | Soft text | `#cfd3e5` | `COLOR_TEXT_SOFT` |
> | Muted text | `#9397ab` | `COLOR_TEXT_MUTED` |
> | Disabled | `#595d6c` | `COLOR_DISABLED`; also `COLOR_STORAGE_OTHER` |
> | Accent | `#9184d9` | `COLOR_ACCENT`, `COLOR_CHART_BAR`, `COLOR_STORAGE_GAMES`, `COLOR_SESSION_BAR_END` (bars now run accent-700 → accent, see below) |
> | Accent hover / pressed | `#b5abfc` | `COLOR_ACCENT_HOVER`; `STATUS_COLORS["playing"]` |
> | Accent 300 (light marks on dark) | `#d2cefd` | `FAVORITE_BADGE_COLOR` (the star), `STATUS_COLORS["finished"]`, text in the reclaim strip |
> | Accent 200 | `#e7e5fe` | `TILE_FOCUS_COLOR` (was white); text of the chosen chip |
> | Accent 100 | `#f5f4ff` | `NEW_BADGE_TEXT_COLOR`; title in the reclaim strip |
> | Accent 600 | `#796cbf` | the 1 px edge of the NEW badge |
> | Accent 700 | `#5d5294` | dark end of the session and chart gradients; the note's left mark |
> | Accent 800 | `#423a6a` | `NEW_BADGE_COLOR` (badge fill); edge of the reclaim strip |
> | Accent 900 | `#2b2741` | fill of the reclaim strip and of the chosen rail item (1b) |
> | Stop | keep `COLOR_STOP` / `COLOR_STOP_HOVER` | the one colour outside the ramps: Stop is destructive and must still read red. Draw it like Play (outlined, red border and text; red fill only on hover) |
>
> Remove the green: `COLOR_PLAY`, `COLOR_PLAY_HOVER`, `COLOR_PLAY_TOP/BOTTOM(_HOVER)` and `COLOR_PLAY_TEXT` go away, and the two Play buttons (ui_continue, ui_detail) paint the outlined style instead. `COLOR_CHIP_ON` / `COLOR_CHIP_ON_TEXT` go away too: the chosen chip is a 1 px accent outline with accent-200 text, not a light fill. `STATUS_COLORS["dropped"]` becomes muted `#9397ab` — the glyph (play / tick / cross) already carries the meaning, so the three marks share one hue.
>
> Button states, everywhere: hover = accent at 12 % over the button, pressed = 22 %; secondary (glass) buttons hover with text at 7 %. Keyboard/pad focus = a 2 px accent ring, 2 px outside the control (`FOCUS_RING_WIDTH` stays 2; the colour is the accent, not white).
>
> **Type.** Inter replaces Segoe. Add `presentation/fonts/Inter-Variable.ttf` (or the static Regular + Medium) and its OFL licence file from https://github.com/rsms/inter/releases, load it with `QFontDatabase.addApplicationFont` **before** the stylesheet is built (where `ui_icons.body_family()` / `display_family()` decide the family), and keep `("Segoe UI Variable Text", "Segoe UI")` as the fallback when the file is missing. `FONT_BODY_FAMILIES` and `FONT_DISPLAY_FAMILIES` both start with `"Inter"`. Headings and titles are **weight 500**, not 600 — change `font-weight: 600` in every stylesheet to 500, `TILE_NAME_WEIGHT` to `"Medium"`, and make `ui_theme.reserve_bold_width` measure with Medium. Big titles get negative tracking: −0.02 em at 40 px, −0.025 em at 46 px and above. Sizes at scale 1, in px, from the mockup:
>
> - Top bar: height 64, side margin 28, brand glyph 24 in the accent, tabs 15 px with a 2 px accent underline on the current one (`TOPBAR_UNDERLINE` 3 → 2); search 320×36, radius 8 (not a pill), 1 px divider border, placeholder "Search 21 games" muted, "Ctrl F" hint at the right in disabled colour; three 36 px icon buttons, radius 8, divider border.
> - Chips: height 30, pill radius, 12.5 px, divider border, muted count after the label; chosen = accent outline + accent-200 text. "Demos & tools", "Hidden", then "Sort by" (muted) and the sort as a chip with a caret.
> - Tiles: cover radius 8 (`TILE_CORNER_RADIUS` 12 → 8), 1 px hairline edge, name 13 px Medium, line under it 11.5 px muted; grid gaps 22 (rows) × 18 (columns). Focused/hovered tile: 2 px accent ring plus a 24 px accent glow at 45 % (the existing `soft_edge` mechanism and `TILE_GLOW_*`). NEW badge: 9.5 px, letter-spacing 0.08 em, padding 2×7, radius 4, accent-800 fill, accent-100 text, 1 px accent-600 edge. Favourite: 24 px disc in the ground at 75 % with a 12 px accent-300 star.
> - Continue playing card: height 250, radius 14 (`CONTINUE_RADIUS` 20 → 14), padding 34×36, scrim ground-colour from the left (100 % → 70 % at 42 % → 0 at 85 %). Eyebrow 12 px uppercase, letter-spacing 0.18 em, accent. Title 40 px/500. Meta 14 px soft text. Note 13 px italic muted. Play 42 px tall, 24 px side padding, 15 px text, outlined; Details beside it as a glass secondary button.
> - Game page (`#1d`): hero 430 px tall fading to the ground from 35 % down, left scrim 90 % → 25 % at half → 0. Floating nav buttons 36 px, glass at ground 65 %, divider border, "Library" with an arrow, "Previous game" / "Next game" with carets. Cover 170 wide, radius 14 (`DETAIL_COVER_RADIUS` 16 → 14), `--shadow-lg` (1 px `#9397ab` edge + 16/40 px ambient). Title 46 px/500. Pills: height 30, 12.5 px, ground at 55 % fill, inset 1 px divider, 14 px icon muted; "Saves copied …" in accent-200. Play 170×48, 16 px text, outlined. Round buttons 44 px (star, folder, …). Status switch = the three marks as one 40 px segmented control, divider border, the chosen one in accent text with an inset 1 px accent ring. Cards: radius 8 (`DETAIL_CARD_RADIUS` 18 → 8), padding 18×20, surface fill, `--shadow-sm` edge, title 15 px/500, body 13.5 px / 1.6 in soft text. The note has a 2 px accent-700 mark on its left. Sessions: 32 px rows, columns 86 / flexible / 62, 8 px bar on a raised-surface track, bar gradient accent-700 → accent.
> - Stats (`#1e`): content max width 1150, four figure cards (padding 18×20; 18 px accent icon; value 32 px/500 −0.02 em; label 12.5 px muted); chart card: bars in a 12-column grid 12 px apart, 170 px tall, gradient accent → accent-700 top to bottom, value above each bar 11 px muted, month labels 11 px under a 1 px hairline; unrecorded months are a 6 px hairline-coloured stub. Two list cards: "Most played" rows 30 px with an 18×27 cover thumb, radius 3; the caveat card with a two-swatch legend.
> - Storage (`#1f`): reclaim strip radius 14, accent-900 fill, inset 1 px accent-800, 22 px accent-300 icon, 14 px/500 accent-100 title, 12.5 px accent-300 line, outlined "Review them" 34 px; drive card: 18 px drive name, 12.5 px muted capacity line, sort as a small segmented control; capacity bar 14 px, radius 7, 2 px gaps, games = accent-600 → accent gradient, everything else = disabled grey, free = raised surface; game rows 38 px, radius 8 (`STORAGE_ROW_RADIUS` 10 → 8), text at 3 % as the row glass, the size bar accent at 16 % (stale rows: accent-400 at 22 %), columns flexible / 110 / 90, stale games carry an outlined accent tag "not played in 90 days".
>
> **Icons.** Phosphor replaces Segoe Fluent Icons. Add Phosphor's regular and fill `.ttf` (MIT, from the `@phosphor-icons/web` package) under `presentation/fonts/` with their licence, register them the same way as Inter, and map the glyph names `ui_icons` already uses onto Phosphor code points — **read the code points from the package's own CSS; never guess one** (that is the `CLAUDE.md` rule about formats). Glyphs used in the mockup: game-controller (fill, the brand), magnifying-glass, shuffle, arrows-clockwise, gear-six, caret-down/left/right, arrow-left, play (fill), star (fill), clock, calendar-blank, hard-drive, hard-drives, floppy-disk, folder-open, dots-three, squares-four, chart-bar, list, list-checks, timer, play-circle, check-circle, x-circle, battery-high, broom. Keep `ICON_FONT_FAMILIES` as the fallback when the files are missing.
>
> **Phases.** Propose numbering after 53; one commit and tag each; stop after each one.
>
> 1. Tokens and type: the table above into `ui_rules.py`, Inter loaded, weights to 500, radii changed. The whole app shifts palette; nothing else moves. Show me Library, a game's page, Stats, Storage rendered.
> 2. Library (`#1a`): top bar, chips, tiles, badges, focus ring and glow, the backdrop (keep its mechanism; its shading uses the ground colour).
> 3. The Continue playing card (`#1a`, top): outlined Play, glass Details, the scrim, the type sizes.
> 4. The game page (`#1d`): hero fade, nav, cover, pills, Play row, segmented status, cards, note mark, sessions.
> 5. Stats and Storage (`#1e`, `#1f`), the toast, the Settings dialog and the menus in the same palette (surface fill, hairline edge, accent 12 % hover; menu selection is an accent-900 fill with accent-100 text, not an accent flood).
> 6. Icons: Phosphor, as above. Last on purpose — everything before it works with the Windows glyphs.
> 7. *Optional, only on my go:* Spotlight (`#1c`) as the TV-mode library — one game large with its hero through a lighten blend, 54 px title, a strip of covers 104 px wide (the focused one 128 px with a 3 px accent-200 ring and glow), and the hint bar reading the pad's real buttons as it does today.
> 8. *Optional, only on my go:* the side rail (`#1b`) — a 232 px column holding the three tabs, the five filters with counts, and the stores ("Found in"), with "Jump back in" as three 178 px wide cards above the grid.
>
> **Out of scope.** The four shortcuts, the taskbar identity, `logic/`, `providers/`, `data_access/`, `web/`, `shared/`, every tunable in `rules.py`, and any behaviour. If a visual change seems to need one of those, stop and tell me instead.

---

## Files in this folder

- `Launcher Mockups.dc.html` — the six screens (`#1a` Library, `#1b` side rail, `#1c` Spotlight, `#1d` game page, `#1e` Stats, `#1f` Storage). Open in a browser.
- `support.js`, `_ds/` — what the HTML needs to render (the runtime and the Nocturne tokens: `_ds/nocturne-…/styles.css` is the token sheet).
- `art/` — the cover and hero art the mockup shows, copied from the launcher's own `data/cache/steam_art` (Steam appid-named).

## Not included

Screenshots of the six screens. Ask for them if Claude Code should have pictures as well as the HTML.
