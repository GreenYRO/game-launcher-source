"""Every tunable that affects how the launcher *looks*.

`rules.py` holds everything about finding and launching games. This file holds everything
about appearance: sizes, colours, animation timings. The split exists because one file with
both had grown past the point where you could find anything in it; the principle is
unchanged -- no magic numbers anywhere else.

Nothing here imports Qt, so these stay plain numbers and strings. Easing curves are named
and looked up on QEasingCurve where they are used.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------
# Grid tiles
# --------------------------------------------------------------------------------------

# Steam's library capsule proportions. Covers are cropped to fill this, never letterboxed.
COVER_ASPECT_W = 2
COVER_ASPECT_H = 3

COVER_WIDTH = 176
COVER_HEIGHT = COVER_WIDTH * COVER_ASPECT_H // COVER_ASPECT_W  # 264

# Since Phase 55 a tile's cell carries every gap of the design's grid itself, and the
# list adds none: 14 px above the cover -- room for a hovered tile to grow and lift, and
# the 14 px between the chips and the first row -- 9 px either side, so covers stand
# 18 px apart, and 8 px under the words, which with the next row's 14 makes the 22 px
# between rows. What a lifted tile grows, rings and glows spills into those gaps.
TILE_PADDING = 14
TILE_PADDING_X = 9
# The name and, under it, a quieter line: playtime for a game this launcher times, the
# store for one it cannot (Phase 32). One line each, so every tile is the same height.
# The design's numbers: 7 px under the cover, 13 px Medium over 11.5 px, each on a line
# 1.55 times its size, 2 px apart.
TILE_NAME_GAP = 7
TILE_NAME_PX = 13
TILE_SUB_PX = 11.5
# The design sets body text on a line 1.55 times its size; its words sit centred in it.
TEXT_LINE_HEIGHT = 1.55
TILE_LINE_HEIGHT = TEXT_LINE_HEIGHT
TILE_NAME_HEIGHT = 55  # the gap, both lines, and the 8 px under them
TILE_CORNER_RADIUS = 8

GRID_SPACING = 0

# --------------------------------------------------------------------------------------
# Detail page
# --------------------------------------------------------------------------------------

# (Its layout moved to the Phase 33 section at the end of this file.)

# When a game has no wide banner, one is built from its cover: scaled to fill, softened by
# a downscale/upscale round trip, then darkened so text stays readable on top.
BANNER_FROM_COVER_BLUR_DIVISOR = 14  # higher = softer
BANNER_FROM_COVER_DARKEN = 0.45  # 0 = untouched, 1 = black

# --------------------------------------------------------------------------------------
# Placeholder covers, for games with no art
# --------------------------------------------------------------------------------------

# The accent is derived from the name, so the wall of art-less games is varied rather than
# uniformly grey, and a given game keeps the same colour forever.
PLACEHOLDER_HUE_SATURATION = 0.42
PLACEHOLDER_HUE_LIGHTNESS = 0.34
PLACEHOLDER_GRADIENT_DARKEN = 0.55
PLACEHOLDER_ICON_FRACTION = 0.34  # icon width as a fraction of the cover width
PLACEHOLDER_NAME_MARGIN = 14

# Cropping only suits art that is already portrait. A landscape image -- a store header, or
# worse a wide transparent logo -- loses most of itself to a 2:3 crop: Aimlabs' logo came
# out as three enormous letters. Anything at or above this width-to-height ratio is instead
# scaled to fit inside a generated accent panel, whole.
COVER_CROP_MAX_ASPECT = 0.9
COVER_FIT_MARGIN = 0.04  # inset when fitting a whole image onto the panel

# A landscape image sitting on a flat panel leaves most of the tile empty. Filling the tile
# with a softened, darkened copy of the same art reads far better. Only done for artwork
# with no transparency: a logo PNG blurred into a backdrop is mostly nothing, and those
# look better on the accent panel.
COVER_FIT_BACKDROP = True
COVER_FIT_BACKDROP_BLUR_DIVISOR = 10
COVER_FIT_BACKDROP_DARKEN = 0.42


# --------------------------------------------------------------------------------------
# Detail page content
# --------------------------------------------------------------------------------------

DESCRIPTION_FONT_PT = 11
DESCRIPTION_LINE_HEIGHT = 1.45

# --------------------------------------------------------------------------------------
# Cycling banner
# --------------------------------------------------------------------------------------

BANNER_CYCLE_DWELL_MS = 6500
BANNER_CYCLE_FADE_MS = 750
BANNER_CYCLE_EASING = "InOutQuad"

# Each extra frame is a full-size screenshot download, so the cycle is short by design.
BANNER_CYCLE_MAX_FRAMES = 5

# Dots sit inside the banner, bottom centre. Game navigation deliberately lives *outside*
# the banner as labelled buttons: two sets of arrows in one rectangle, one moving between
# images and one between games, is a guessing game.
BANNER_DOT_SIZE = 9
BANNER_DOT_SPACING = 8
BANNER_DOT_MARGIN = 16
BANNER_DOT_HIT_PADDING = 6

SCREENSHOT_MAX_PER_GAME = 8
SCREENSHOT_THUMB_HEIGHT = 92
SCREENSHOT_STRIP_SPACING = 8
SCREENSHOT_CORNER_RADIUS = 5

# --------------------------------------------------------------------------------------
# Animation. Every one of these is skipped entirely when "reduce animations" is on.
# --------------------------------------------------------------------------------------

HOVER_SCALE = 1.055
HOVER_DURATION_MS = 150
HOVER_EASING = "OutCubic"

# Pages arrive rather than appear (Phase 34): across between Library, Stats and Storage,
# from whichever side the tab is on; up a little into a game's own page; in place back
# out of one. Drawn from one snapshot of the incoming page -- see ui_motion for why.
PAGE_TRANSITION_MS = 260
PAGE_TRANSITION_EASING = "OutCubic"
PAGE_SLIDE_FRACTION = 0.04  # how far the incoming page slides, as a fraction of width
PAGE_RISE_PX = 28  # how far a game's page rises as it arrives

SCROLL_DURATION_MS = 220
SCROLL_EASING = "OutCubic"
SCROLL_WHEEL_STEP = 320  # pixels per wheel notch

# --------------------------------------------------------------------------------------
# Colours (dark theme)
# --------------------------------------------------------------------------------------

# The Nocturne palette (Phase 54, from the design handoff's token sheet): a near-neutral
# blue-grey ground, solid surfaces with a hairline edge, and one blurple accent used as
# lines and glows rather than fills. Every value is from the design's ramps -- no pure
# black or white. Muted text is 6.1:1 on the ground and 5.3:1 on a card -- less than the
# old palette's 7:1, still above the 4.5:1 that ordinary reading needs.
COLOR_BACKGROUND = "#161826"  # the ground
COLOR_SURFACE = "#232532"  # cards, inputs, menus
COLOR_SURFACE_RAISED = "#292b31"
COLOR_BORDER = "#3f424d"  # the hairline edge
COLOR_TEXT = "#e9e9ed"
COLOR_TEXT_MUTED = "#9397ab"
# Distinctly dimmer than muted text, so an unavailable menu entry reads as unavailable
# rather than merely secondary.
COLOR_DISABLED = "#595d6c"
COLOR_ACCENT = "#9184d9"
COLOR_ACCENT_HOVER = "#b5abfc"  # accent 400
# The rest of the accent's ramp, light to dark, as the design names the steps.
COLOR_ACCENT_100 = "#f5f4ff"
COLOR_ACCENT_200 = "#e7e5fe"
COLOR_ACCENT_300 = "#d2cefd"  # light marks on dark: the star, a finished game
COLOR_ACCENT_600 = "#796cbf"
COLOR_ACCENT_700 = "#5d5294"
COLOR_ACCENT_800 = "#423a6a"
COLOR_ACCENT_900 = "#2b2741"  # a tinted fill: the reclaim strip, a chosen menu entry (Phase 58)
# A line between things on glass: the text colour at 16%. Stylesheets only -- QColor
# cannot read rgba(...) (Phase 35).
COLOR_DIVIDER = "rgba(233, 233, 237, 41)"
# Glass for the controls that sit on whatever is behind them: pills, the game page's
# switch. (Since Phase 55 the chips are outlines only: see CHIP_* below.)
COLOR_CHIP = "rgba(233, 233, 237, 16)"
COLOR_CHIP_BORDER = COLOR_DIVIDER
COLOR_CHIP_HOVER = "rgba(233, 233, 237, 30)"
# Button states, everywhere (Phase 55). An outlined accent button lights with the accent
# at 12% under the mouse and 22% pressed; a quiet one with the text colour at 7% and 14%.
COLOR_PRIMARY_HOVER = "rgba(145, 132, 217, 31)"
COLOR_PRIMARY_PRESSED = "rgba(145, 132, 217, 56)"
COLOR_SECONDARY_HOVER = "rgba(233, 233, 237, 18)"
COLOR_SECONDARY_PRESSED = "rgba(233, 233, 237, 36)"
COLOR_TEXT_QUIET = "#b2b6ca"  # neutral 400: between soft and muted, the two switches' words
COLOR_TEXT_FAINT = "#75798c"  # neutral 600: a shortcut's hint, quieter than muted text
COLOR_TEXT_BRIGHT = "#e4e7f5"  # neutral 200: the game page's pills and note (Phase 57)
# A quiet accent button -- "Edit note...", "Read more" -- lights with the accent at 10%.
COLOR_TEXT_BUTTON_HOVER = "rgba(145, 132, 217, 26)"

# --------------------------------------------------------------------------------------
# Interface scale
# --------------------------------------------------------------------------------------

UI_SCALE_DEFAULT = 1.0
UI_SCALE_CHOICES = (1.0, 1.25, 1.5)
REDUCE_ANIMATIONS_DEFAULT = False

# --------------------------------------------------------------------------------------
# Focus ring and TV mode
# --------------------------------------------------------------------------------------

# The focused tile has to be obvious from across a room, so it gets a thick accent border
# and grows slightly -- position alone is not enough at that distance.
FOCUS_RING_WIDTH = 2
FOCUS_RING_GAP = 2  # where a ring is drawn outside a control (Phase 56), this far out
FOCUS_SCALE = 1.05
TV_FOCUS_RING_WIDTH = 5

TV_MODE_DEFAULT = False

# TV mode's own size, independent of the desktop "Interface size" -- a couch is further
# away than a desk. It is a multiplier, and **Windows' own display scaling multiplies on
# top of it**, which is what made the original fixed 1.6 unusable: on a 4K TV set to 300%,
# Windows already hands the app a 1280x720 canvas, and 1.6 on top of that left room for
# three tiles on the whole screen. Hence a setting rather than a constant, and a default
# that assumes the TV is already doing some scaling of its own.
TV_SCALE_DEFAULT = 0.85
TV_SCALE_CHOICES = (0.5, 0.6, 0.7, 0.85, 1.0, 1.25, 1.6)
TV_HINT_BAR_HEIGHT = 56
TV_HINT_FONT_PT = 11

BASE_FONT_PT = 10
TITLE_FONT_PT = 26
META_FONT_PT = 10

# --------------------------------------------------------------------------------------
# Marks on a tile: favorite, new, and where you are with it
# --------------------------------------------------------------------------------------

# (The two shelves that used to sit above the grid were removed in Phase 32. Recently
# played became the Continue playing card; Favorites became a chip.)

# The star drawn on a favorite tile, as a fraction of the cover width so it scales with
# everything else. Drawn top-right, over the art, with a dark disc behind it because a
# bare star vanishes against pale cover art. The fractions are the design's pixels over
# its 137 px cover (Phase 55): a 24 px disc 7 px in, the ground at 75%, a 12 px star.
FAVORITE_BADGE_FRACTION = 0.175
FAVORITE_BADGE_MARGIN_FRACTION = 0.051
FAVORITE_STAR_FRACTION = 0.25  # the star's outer radius, of the disc
FAVORITE_BADGE_COLOR = COLOR_ACCENT_300
FAVORITE_BADGE_BACKDROP = COLOR_BACKGROUND
FAVORITE_BADGE_BACKDROP_ALPHA = 191

# The tag on a game the launcher has only just found. Top-left, opposite the star, and
# sized from the cover width like the star, so it scales with the grid and TV mode alike. A solid pill rather than the star's dark disc: this one exists to catch the
# eye, and its text stays readable on any art because the pill itself is opaque.
# Its sizes are the design's over its 137 px cover too: 9.5 px letters spaced 0.08 em,
# 2 by 7 px of padding, a 4 px radius and a 1 px edge in the accent's 600 step.
NEW_BADGE_TEXT = "NEW"
NEW_BADGE_MARGIN_FRACTION = FAVORITE_BADGE_MARGIN_FRACTION
NEW_BADGE_FONT_FRACTION = 0.069  # of the cover width
NEW_BADGE_PAD_V_FRACTION = 0.0146
NEW_BADGE_PAD_H_FRACTION = 0.051
NEW_BADGE_RADIUS_FRACTION = 0.029
NEW_BADGE_TRACKING = 0.08  # em
NEW_BADGE_COLOR = COLOR_ACCENT_800
NEW_BADGE_TEXT_COLOR = COLOR_ACCENT_100
NEW_BADGE_EDGE = COLOR_ACCENT_600

# Where the user says they are with a game (Phase 27). Keyed by the values in
# rules.STATUSES; a test checks the two agree. On the tile it is a glyph on a dark disc in
# the bottom-right corner -- the star's disc, so it reads on any art -- drawn as a path
# rather than a font character, because a character renders differently in every font.
STATUS_LABELS = {"playing": "Playing", "finished": "Finished", "dropped": "Dropped"}
# One hue for all three since Phase 54: the glyph (triangle, tick, cross) carries the meaning.
STATUS_COLORS = {
    "playing": COLOR_ACCENT_HOVER,
    "finished": COLOR_ACCENT_300,
    "dropped": COLOR_TEXT_MUTED,
}
STATUS_BADGE_FRACTION = FAVORITE_BADGE_FRACTION
STATUS_BADGE_MARGIN_FRACTION = FAVORITE_BADGE_MARGIN_FRACTION
STATUS_GLYPH_STROKE_FRACTION = 0.13  # of the disc, for the tick and the cross

# The Continue playing card gets out of the way once you start scrolling the grid, and
# comes back when you return to the top -- the mechanism the shelves had, kept. Two
# thresholds rather than one, and a wide gap between them, because folding the card makes
# the grid taller, which shortens its scrollbar: a single threshold would let the
# shortened scrollbar bounce the value back across it and the card would flicker.
# Fold late, restore early, and nothing oscillates.
CONTINUE_FOLD_AT = 140
CONTINUE_RESTORE_AT = 20
CONTINUE_FOLD_MS = 220
CONTINUE_FOLD_EASING = "OutCubic"

# The "Recent updates" block. Titles are a touch larger than the body so each post is
# scannable from a distance; the snippet stays at the description's size.
NEWS_TITLE_FONT_PT = 12
NEWS_ITEM_SPACING = 12

# How many past sessions the game page draws as bars. Short on purpose: it answers "when
# did I last play this, and for how long", not "show me everything".
SESSIONS_SHOWN = 6

# Two columns, wider on the left. First drawn for the old game page's facts row; the stats
# page lays its own two columns out with the same three numbers.
DETAIL_COLUMN_GAP = 28
DETAIL_FACTS_WEIGHT = 3
DETAIL_SESSIONS_WEIGHT = 2

# Stop, which replaces Play while that game is running. Red because it ends something:
# the one control in the app whose effect cannot be undone.
COLOR_STOP = "#b4453f"

# The controller battery in the TV hint bar. Sized from the hint bar's own height so it
# never drives the layout: the bar is exactly as tall with the glyph as without it.
BATTERY_HEIGHT_FRACTION = 0.34
BATTERY_ASPECT = 1.9  # width as a multiple of height
BATTERY_CAP_FRACTION = 0.12  # the nub on the positive end
BATTERY_BORDER = 2
BATTERY_PADDING = 2
BATTERY_STEPS = 4

# Amber rather than red: a low pad is worth noticing, not alarming about.
COLOR_WARNING = "#e0a33e"

# The controller's buttons in the TV hint bar (Phase 50), drawn rather than written. A
# button is this share of the bar's height, so the bar is the same height whatever it shows.
PAD_GLYPH_HEIGHT_FRACTION = 0.62
# A button's body: dark, with a hairline edge, like the buttons on the pads themselves.
COLOR_PAD_BODY = "#262b35"
COLOR_PAD_EDGE = "#525b6d"
COLOR_PAD_MARK = "#eef1f6"  # marks with no colour of their own: bumpers, menu, the d-pad
COLOR_PAD_DIM = "#4a5263"  # the d-pad's arms that are not meant
# Xbox's letters and PlayStation's shapes in their own colours, a little lifted so they
# read on the dark bar.
COLOR_PAD_A = "#5cc15a"
COLOR_PAD_B = "#ec5a50"
COLOR_PAD_X = "#4f9ef0"
COLOR_PAD_Y = "#f4c542"
COLOR_PAD_CROSS = "#82b6f2"
COLOR_PAD_CIRCLE = "#f2706c"
COLOR_PAD_SQUARE = "#e891d2"
COLOR_PAD_TRIANGLE = "#43d1b0"

# --------------------------------------------------------------------------------------
# The stats and storage pages -- the design's #1e and #1f since Phase 58
# --------------------------------------------------------------------------------------

# Both pages are one column: 64 px in from the window's side, 18 px under the top bar, and
# never wider than the design's 1150 less its 64 either side. At the 1280 px the design
# was drawn at it sits where the design puts it; every pixel a window grows beyond that is
# shared equally between the two sides, so a maximised window or the TV is not lopsided.
PAGE_COLUMN_SIDE = 64
PAGE_COLUMN_TOP = 18
PAGE_COLUMN_FRAME = 1280
STATS_CONTENT_MAX_WIDTH = 1022
STORAGE_CONTENT_MAX_WIDTH = 1022
STATS_PAGE_MARGIN = 26  # the room under the last card
STATS_SECTION_SPACING = 22  # between the figures, the chart and the lists

# The four figures along the top: 14 apart, 18 x 20 inside, an 18 px icon in the accent,
# the value 32 px Medium, 0.02 em tighter, on a 1.1 line and 4 px further down, the caption
# 12.5 px in neutral 400.
STATS_CARD_SPACING = 14
STATS_CARD_PADDING_X = 20
STATS_CARD_PADDING_Y = 18
STATS_CARD_MIN_WIDTH = 150
STATS_ICON_PX = 18
STATS_VALUE_PX = 32
STATS_VALUE_TRACKING = -0.02  # em
STATS_VALUE_LINE = 1.1
STATS_ICON_GAP = 10  # the card's 6 and the value's own 4
STATS_CAPTION_GAP = 6
STATS_CAPTION_PX = 12.5
COLOR_STATS_CAPTION = COLOR_TEXT_QUIET

# The chart's card: 20 px above, 24 either side, 16 below, 14 between its title and the bars.
STATS_CHART_PADDING_X = 24
STATS_CHART_PADDING_TOP = 20
STATS_CHART_PADDING_BOTTOM = 16
STATS_CHART_TITLE_GAP = 14
# Twelve bars 12 px apart in 170 px, the tallest 120 of it, each with its value 8 px above
# it (11 px, neutral 400); the months 11 px in neutral 500, 8 px under a 1 px hairline that
# sits 8 px under the bars. A bar runs from the accent at its top to accent 700 at its foot.
STATS_CHART_HEIGHT = 170
STATS_BAR_MAX = 120
STATS_BAR_GAP = 12
STATS_BAR_RADIUS = 3  # its top corners
STATS_VALUE_ABOVE = 8
STATS_AXIS_PX = 11
STATS_AXIS_GAP = 8  # bars to hairline, and hairline to the months
# A month nobody recorded is a 6 px stub in the hairline colour -- "Not recorded yet". A
# month that was recorded and quiet keeps a thinner stub in the accent's dark step: it was
# recorded, and nothing was played. "Nothing was played" and "nothing was being recorded"
# are different facts (Phase 23).
STATS_UNRECORDED_PX = 6
STATS_EMPTY_BAR_PX = 3
# The shortest a real bar may be drawn. One minute against a peak of forty hours rounds to
# nothing otherwise, and "you played, and it vanished" is the wrong answer.
STATS_MIN_BAR_PX = 4
COLOR_CHART_BAR = COLOR_ACCENT
COLOR_CHART_BAR_FOOT = COLOR_ACCENT_700
COLOR_CHART_BASELINE = COLOR_ACCENT_700
COLOR_CHART_UNRECORDED = COLOR_BORDER
COLOR_CHART_AXIS = COLOR_BORDER
COLOR_CHART_VALUE = COLOR_TEXT_QUIET
COLOR_CHART_MONTH = COLOR_TEXT_MUTED

# The lists: two cards side by side, 14 apart, 18 x 22 inside, their title 10 px over the
# first row; rows 30 high and 4 apart, 13 px, a game's cover 18 x 27 with 3 px corners and
# 12 px before its name, its time in neutral 300.
STATS_COLUMN_GAP = 14
STATS_LIST_PADDING_X = 22
STATS_LIST_PADDING_Y = 18
STATS_LIST_TITLE_GAP = 10
STATS_LIST_ROW_PX = 30
STATS_LIST_ROW_GAP = 4
STATS_LIST_TEXT_PX = 13
STATS_LIST_GAP = 12
STATS_THUMB_WIDTH = 18
STATS_THUMB_HEIGHT = 27
STATS_THUMB_RADIUS = 3
# What these numbers cannot see: 13 px on a 1.6 line in neutral 300, and the chart's two
# colours named under it -- 10 px swatches, 2 px corners, 12 px words in neutral 400.
STATS_CAVEAT_GAP = 8
STATS_CAVEAT_PX = 13
STATS_CAVEAT_LINE = 1.6
STATS_SWATCH_PX = 10
STATS_SWATCH_RADIUS = 2
STATS_SWATCH_GAP = 6
STATS_LEGEND_PX = 12
STATS_LEGEND_GAP = 16  # between the two
STATS_LEGEND_TOP = 6

# How far one flick of the stick scrolls a page that has no items to step between. The
# stats page is the only one: there is nothing on it to select, so up and down scroll.
PAD_SCROLL_STEPS = 3

# --------------------------------------------------------------------------------------
# Tabs shared by the Stats and Storage pages
# --------------------------------------------------------------------------------------

TAB_FONT_PT = 13
TAB_GROUP_GAP = 16

# --------------------------------------------------------------------------------------
# The storage page
# --------------------------------------------------------------------------------------

STORAGE_SECTION_SPACING = 18  # between the strip, the map and each drive's card

# The reclaim strip: 14 px corners, accent 900 with an accent-800 edge, 14 x 18 inside, its
# icon 22 px in accent 300, 16 px before the words: a 14 px Medium line in accent 100 over a
# 12.5 px one in accent 300. With nothing to reclaim it is a plain card saying why.
STORAGE_RECLAIM_RADIUS = 14
STORAGE_RECLAIM_PADDING_X = 18
STORAGE_RECLAIM_PADDING_Y = 14
STORAGE_RECLAIM_GAP = 16
STORAGE_RECLAIM_ICON_PX = 22
STORAGE_RECLAIM_TITLE_PX = 14
STORAGE_RECLAIM_LINE_PX = 12.5
COLOR_RECLAIM = COLOR_ACCENT_900
COLOR_RECLAIM_EDGE = COLOR_ACCENT_800
COLOR_RECLAIM_ICON = COLOR_ACCENT_300
COLOR_RECLAIM_TITLE = COLOR_ACCENT_100
COLOR_RECLAIM_LINE = COLOR_ACCENT_300

# Each drive is a card (18 x 22 inside, 10 between its parts): the drive 18 px Medium, its
# capacity 12.5 px in neutral 400 beside it; the capacity bar 14 px, 7 px corners, its three
# parts 2 px apart -- the games accent 600 to the accent, everything else neutral 700, free
# space neutral 900 -- and a legend of 9 px swatches, 12 px words, 18 apart; the games 8 px
# further down. Painted by the list's delegate, a slice per item, so one list still holds
# both shapes and the pad still walks only the games (Phase 24).
STORAGE_CARD_PADDING_X = 22
STORAGE_CARD_PADDING_Y = 18
STORAGE_CARD_GAP = 10
STORAGE_ROWS_TOP = 8
STORAGE_DRIVE_PX = 18
STORAGE_CAPACITY_PX = 12.5
STORAGE_CAPACITY_GAP = 12  # between the drive and its capacity
STORAGE_CAPACITY_BAR_HEIGHT = 14
STORAGE_BAR_RADIUS = 7
STORAGE_SEGMENT_GAP = 2
STORAGE_LEGEND_PX = 12
STORAGE_SWATCH_PX = 9
STORAGE_SWATCH_RADIUS = 2
STORAGE_SWATCH_GAP = 6
STORAGE_LEGEND_GAP = 18
COLOR_STORAGE_GAMES = COLOR_ACCENT
COLOR_STORAGE_GAMES_START = COLOR_ACCENT_600
COLOR_STORAGE_OTHER = COLOR_DISABLED
COLOR_STORAGE_FREE = COLOR_SURFACE_RAISED

# A game's row: 38 high, 5 apart, 8 px corners, the text colour at 3% as its glass, 14 px in;
# a bar from its left edge as long as the game is big against the drive's biggest -- the
# accent at 16%, or accent 400 at 22% for a game past the staleness threshold, which also
# carries an outlined tag; its name 13 px, then last played (110 px, 12.5 px, neutral 400)
# and the size (90 px, 13 px). QColor reads #AARRGGBB, never a stylesheet's rgba(...).
STORAGE_ROW_HEIGHT = 38
STORAGE_ROW_GAP = 5
STORAGE_ROW_RADIUS = 8
STORAGE_ROW_PADDING = 14
STORAGE_BAR_MIN_PX = 3  # a 40 MB game beside a 142 GB one must still be visible
STORAGE_AGE_COLUMN = 110
STORAGE_SIZE_COLUMN = 90
STORAGE_NAME_PX = 13
STORAGE_AGE_PX = 12.5
COLOR_STORAGE_ROW = "#08e9e9ed"
COLOR_STORAGE_BAR = "#299184d9"
COLOR_STORAGE_STALE_BAR = "#38b5abfc"
COLOR_STORAGE_AGE = COLOR_TEXT_QUIET
STORAGE_TAG_PX = 10
STORAGE_TAG_PADDING_X = 7
STORAGE_TAG_PADDING_Y = 1
STORAGE_TAG_RADIUS = 6
STORAGE_TAG_GAP = 10  # after the name
COLOR_STORAGE_TAG = COLOR_ACCENT

# The treemap: the library as rectangles, area proportional to size. Mouse only -- it has
# no pad path and is hidden in TV mode, where the ranked list is the whole page. Not in the
# design; kept as it was.
STORAGE_TREEMAP_HEIGHT = 250
# The map gives up height before the list does (Phase 62): the list always shows its first
# drive's card top and this many rows under it; the map shrinks to leave that room, and
# below this height it steps aside. At 125% in a 1280 x 820 window the map's full height
# left the list 141 px -- less than the card top and one row -- so the page opened
# scrolled past the drive's name.
STORAGE_LIST_MIN_ROWS = 2
STORAGE_TREEMAP_MIN_HEIGHT = 120
STORAGE_TREEMAP_FONT_PT = 9
STORAGE_TREEMAP_HOVER_LIGHTEN = 135  # QColor.lighter percentage
# Narrower than this and a name cannot be shown at all, so the rectangle is left plain and
# answers through its tooltip. Measured against the real library: at 1100px wide, 19 of 21
# games clear it.
STORAGE_TREEMAP_MIN_LABEL_PX = 46

# --------------------------------------------------------------------------------------
# Phase 31: type, icons, the top bar, chips and pop-up messages
# --------------------------------------------------------------------------------------

# Inter since Phase 54, shipped with the program (presentation/fonts, OFL) and registered
# before the first stylesheet is built; Windows 11's own typefaces stay behind it, and
# Windows 10's behind those. The first one present wins. Titles are in Inter Display
# since Phase 62 -- Inter's cut for large text, drawn tighter, and the nearest free match
# for San Francisco's Display, which the user asked for and whose licence rules it out.
FONT_BODY_FAMILIES = ("Inter", "Segoe UI Variable Text", "Segoe UI")
FONT_DISPLAY_FAMILIES = ("Inter Display", "Inter", "Segoe UI Variable Display", "Segoe UI Semibold",
                         "Segoe UI")
FONTS_FOLDER = ("presentation", "fonts")  # under paths.resource_dir(); every .ttf in it is loaded
# One step heavier than the design since Phase 62 ("it looks too thin"): ordinary text
# Medium, titles and headings SemiBold, and the two small labels that were heavier still
# -- the NEW badge and the letters on the pad's buttons -- Bold. Each is a real face in
# presentation/fonts (Inter Display only at SemiBold, the one weight titles use).
BODY_WEIGHT = 500
HEADING_WEIGHT = 600
LABEL_WEIGHT = 700
# Big titles are set a little tighter: (from this many pixels, letter spacing in em).
TITLE_TRACKING = ((46, -0.025), (40, -0.02))
# Phosphor since Phase 59 (the design's icons, MIT), shipped in presentation/fonts: its
# regular set first, its filled one for the solid glyphs; Windows' own behind them, for a
# copy without the files.
ICON_FONT_FAMILIES = ("Phosphor", "Segoe Fluent Icons", "Segoe MDL2 Assets")
ICON_FILL_FAMILY = "Phosphor-Fill"

# Buttons and inputs: rounder than before, which does most of the "modern" on its own.
CONTROL_RADIUS = 8

# The bar across the top of Library, Stats and Storage -- the design's numbers since
# Phase 55: 28 px from the window's sides, 22 between its groups, the tabs 15 px and 24
# apart with a 2 px underline at the bar's foot, the brand glyph 24 px with 8 more after it.
TOPBAR_HEIGHT = 64
TOPBAR_SIDE_MARGIN = 28
TOPBAR_GAP = 22
TOPBAR_BRAND_PX = 24
TOPBAR_BRAND_GAP = 8
TOPBAR_TAB_PX = 15
TOPBAR_TAB_GAP = 24
TOPBAR_UNDERLINE = 2
# The search box: a rounded rectangle now, not a pill, on the surface at 70%, with the
# shortcut written faintly at its right end.
SEARCH_WIDTH = 320
SEARCH_HEIGHT = 36
SEARCH_PX = 13
SEARCH_ICON_PX = 15
SEARCH_PADDING = 12
SEARCH_HINT = "Ctrl F"
SEARCH_HINT_PX = 11
COLOR_SEARCH = "rgba(35, 37, 50, 179)"
# Three square buttons, quiet until the mouse is on them.
ICON_BUTTON_SIZE = 36
ICON_BUTTON_GAP = 6
TOPBAR_GLYPH_PX = 17
ICON_GLYPH_PX = 16

# The filter chips under it: outlines, the chosen one in the accent (Phase 55).
CHIP_HEIGHT = 30
CHIP_PX = 12.5
CHIP_COUNT_PX = 11.5
CHIP_SIDE_PADDING = 13
CHIP_COUNT_GAP = 8  # between a chip's word and its number
CHIP_GAP = 8
SORT_LABEL_GAP = 14  # before "Sort by"
SORT_CARET_PX = 12

# Messages float as a card over the bottom-right corner instead of sitting in a bar that
# said "Ready" forever. They slide up a little as they appear.
TOAST_MAX_WIDTH = 560
TOAST_MARGIN = 24
TOAST_RADIUS = 14
TOAST_SHOW_MS = 180
TOAST_SLIDE_PX = 14
TOAST_FONT_PT = 10

# --------------------------------------------------------------------------------------
# Phase 32: the library -- Continue playing, a backdrop from the art, new tiles
# --------------------------------------------------------------------------------------

# The card at the top of the library: the game you were last playing, its wide art, and
# Play one press away. Games marked Finished or Dropped are passed over -- "continue" a
# game you have said you are done with would be the wrong suggestion.
# The design's card since Phase 56 (#1a, read from its markup): 250 high, 34 px in from top
# and bottom and 36 from the sides, edged with the 1 px hairline rather than a shadow. Its
# words stand on its foot, stacked upwards from the buttons 6 px apart -- the eyebrow 10 px
# (the brief said 12; the mockup's .card-kicker is 10, and its render measures 10) spaced
# 0.18 em, the title 40 px on a 1.1 line, the line under it 14 px, the note 13 px italic --
# never wider than 620 px less the padding, with 12 px more above the buttons.
CONTINUE_HEIGHT = 250
CONTINUE_RADIUS = 14
CONTINUE_PADDING_X = 36
CONTINUE_PADDING_Y = 34
CONTINUE_GAP = 18  # between the card and the chips (the design's 18 since Phase 55)
LIBRARY_TOP_GAP = 8  # under the top bar, above the card (the design's 8 since Phase 56; 4 before)
CONTINUE_SKIP_STATUSES = ("finished", "dropped")
# Text sizes in pixels at scale 1, because the card paints its own text.
CONTINUE_EYEBROW_PX = 10
CONTINUE_EYEBROW_TRACKING = 0.18  # em
CONTINUE_TITLE_PX = 40
CONTINUE_TITLE_LINE = 1.1
CONTINUE_META_PX = 14
CONTINUE_NOTE_PX = 13
CONTINUE_TEXT_MAX = 548
CONTINUE_LINE_GAP = 6  # between the lines of words
CONTINUE_BUTTONS_ABOVE = 12  # more, between the words and the buttons
# The buttons size to their words: 42 high, 15 px, 24 px either side of Play's, 20 of
# Details', 10 apart, Play's icon 15 px.
CONTINUE_BUTTON_HEIGHT = 42
CONTINUE_BUTTON_PX = 15
CONTINUE_PLAY_PADDING = 24
CONTINUE_DETAILS_PADDING = 20
CONTINUE_BUTTON_GAP = 10
# The scrim that keeps the words readable over any art: the ground on the left, where the
# text is, 70% of it by 42% of the way across, and gone by 85%, where the art is.
CONTINUE_SCRIM = ((0.0, 255), (0.42, 179), (0.85, 0))
CONTINUE_ART_ANCHOR = 0.3  # the art is cropped about 30% of the way down, as the design's is
# The focus ring the game page's buttons still draw as their border (until step 4); the
# card draws the design's ring outside its buttons instead: FOCUS_RING_WIDTH, FOCUS_RING_GAP out.
CONTINUE_FOCUS_RING = 3
COLOR_SCRIM = COLOR_BACKGROUND  # scrims are the ground, so art blends into the page
COLOR_TEXT_SOFT = "#cfd3e5"  # between text and muted: the line under a big title
# Since Phase 56 there is no green: Play is outlined in the accent, words and icon in the
# accent, over the ground at 60% so it reads on any art; Details the quiet button over the
# ground at 50%; Stop as Play in red. Under the mouse they take the button states above.
COLOR_ON_ART_PRIMARY = "rgba(22, 24, 38, 153)"
COLOR_ON_ART_SECONDARY = "rgba(22, 24, 38, 128)"
COLOR_STOP_TINT = "rgba(180, 69, 63, 56)"  # Stop under the mouse: its red at 22%
COLOR_STOP_TINT_PRESSED = "rgba(180, 69, 63, 89)"  # and pressed, at 35%
COLOR_GHOST = "rgba(233, 233, 237, 30)"
COLOR_GHOST_BORDER = COLOR_DIVIDER
COLOR_GHOST_HOVER = "rgba(233, 233, 237, 50)"

# The backdrop behind the library: the art of whichever game you are on, shrunk to a few
# pixels and smoothed back up -- a blur for free -- then shaded so text stays readable.
# It follows the pad and the keyboard straight away, and the mouse once it has rested on
# a tile, so sweeping across the grid does not strobe the whole window.
BACKDROP_TINY = ((28, 16), (7, 4))  # two downscale steps; the last is what gets stretched
# The design's numbers since Phase 55: the art at 35%, its colour at 70%, fading into the
# ground by 62% of the way down.
BACKDROP_STRENGTH = 0.35  # opacity of the art under the shading
BACKDROP_SATURATION = 0.7
BACKDROP_SHADE = ((0.0, 0), (0.62, 255), (1.0, 255))  # top to bottom, alpha of the ground
BACKDROP_VIGNETTE_ALPHA = 150
BACKDROP_FADE_MS = 450
BACKDROP_FADE_EASING = "InOutQuad"
BACKDROP_HOVER_SETTLE_MS = 260

# The tiles, flat since Phase 55 as the design draws them: the cover and a 1 px hairline
# outside it. The one under the mouse or the pad lifts, grows, takes a 2 px accent ring
# outside its edge and a 24 px accent glow at 45% -- and only a lifted tile casts a shadow,
# which is what makes it read as lifted. (A sheen across the top went with the glass.)
TILE_SHADOW_SPREAD = 12
TILE_SHADOW_ALPHA = 90
TILE_SHADOW_DY = 8
TILE_LIFT = 4  # how far a hovered or focused tile rises at scale 1 (6 until Phase 55: with the
# design's 14 px over the top row, a rise of 6 pushed the ring off the top of the grid)
TILE_BORDER_ALPHA = 28  # the hairline drawn in white elsewhere: the card's, the page cover's
TILE_FOCUS_COLOR = COLOR_ACCENT  # the design's ring (accent 200 in Phase 54, white before)
TILE_HIDDEN_ALPHA = 140  # the ground laid over a hidden game's cover
TILE_GLOW_ALPHA = 115
TILE_GLOW_PX = 24
TILE_NAME_WEIGHT = "DemiBold"  # Qt's name for SemiBold; a heading, as of Phase 62
TILE_SUB_GAP = 2  # between the name and the line under it

# --------------------------------------------------------------------------------------
# Phase 33: the game page -- art edge to edge, the facts as pills, cards below
# --------------------------------------------------------------------------------------

# The art across the top runs the full width and fades into the backdrop, so the page
# reads as one surface rather than a picture in a frame. Since Phase 57 the design's: its
# 430 px of art and the 5 px on to the first card, one box, since the art's foot has faded
# to nothing by then -- and on a taller window the same share of it as in the design's
# 800 px frame, so a maximised window or the TV does not get a thin strip. Or whatever the
# cover and the words beside it need, whichever is most.
DETAIL_HERO_HEIGHT = 435
DETAIL_HERO_FRACTION = 0.54
DETAIL_HERO_FADE_FROM = 0.35  # how far down the art starts fading out
DETAIL_HERO_SIDE_SCRIM = ((0.0, 230), (0.5, 64), (1.0, 0))  # the ground, 90% -> 25% -> none
DETAIL_HERO_ANCHOR = 0.25  # the art is cropped a quarter of the way down, as the design frames it
DETAIL_HERO_BOTTOM = 30  # from the cover's foot to the first card
DETAIL_HERO_CACHE = 12  # finished frames kept; each is a full-width picture

# Everything in the page's own column -- the words over the art and every card -- lines up
# on one left edge, and never spreads wider than this on a big screen.
DETAIL_PAGE_MARGIN = 48
DETAIL_BODY_MAX_WIDTH = 1400

DETAIL_COVER_WIDTH = 170  # its height follows from the 2:3 cover shape
DETAIL_COVER_RADIUS = 14
# The design's large shadow: a 1 px edge in neutral 500 and a 40 px blur dropped 16 px.
DETAIL_COVER_SHADOW = 40
DETAIL_COVER_SHADOW_DROP = 16
DETAIL_COVER_SHADOW_ALPHA = 110  # stacked rings, not a blur: by eye against the mockup
COLOR_COVER_EDGE = COLOR_TEXT_MUTED
DETAIL_COVER_GAP = 30  # between the cover and the words beside it

DETAIL_TITLE_PX = 46
DETAIL_ROW_GAP = 14  # between the title, the pills and the Play row
DETAIL_ACTIONS_TOP = 4  # and a little more above the Play row
DETAIL_INFO_FOOT = 4  # the Play row's foot stands this far above the cover's

# The facts under the title, each a small pill with its own icon, on the ground at 55%.
DETAIL_PILL_HEIGHT = 30
DETAIL_PILL_PX = 12.5
DETAIL_PILL_ICON_PX = 14
DETAIL_PILL_GAP = 8
DETAIL_PILL_SIDE_PADDING = 12
COLOR_ON_ART_FAINT = "rgba(22, 24, 38, 140)"  # the ground at 55%: the pills and the page's Play
COLOR_PILL_ICON = COLOR_TEXT_QUIET
COLOR_PILL_TEXT = COLOR_TEXT_BRIGHT
COLOR_PILL_SAVED = COLOR_ACCENT_200  # "Saves copied ...": the one pill in the accent

# The Play row: the card's outlined Play at a larger size, round buttons, and the three
# marks as one segmented switch -- the chosen one in the accent, ringed inside.
DETAIL_ACTION_HEIGHT = 48
DETAIL_PLAY_WIDTH = 170
DETAIL_PLAY_PX = 16
DETAIL_ROUND_BUTTON = 44
DETAIL_ROUND_ICON_PX = 17
DETAIL_MORE_ICON_PX = 19
DETAIL_ACTION_GAP = 10
DETAIL_SWITCH_GAP = 18  # the row's gap and 8 more, before the switch
DETAIL_SEGMENT_HEIGHT = 40
# Under the switch, since when its mark stands (Phase 103): in the room between the Play row and the first card.
DETAIL_SINCE_PX = 12
DETAIL_SINCE_GAP = 5
DETAIL_SEGMENT_PX = 13
DETAIL_SEGMENT_SIDE_PADDING = 12

# Back, Previous game and Next game float over the top corners and stay there while the
# page scrolls, so leaving never means scrolling back up first.
DETAIL_NAV_HEIGHT = 36
DETAIL_NAV_TOP = 18
DETAIL_NAV_SIDE = 24
DETAIL_NAV_GAP = 8  # between Previous and Next
DETAIL_NAV_PX = 14
DETAIL_NAV_ICON_PX = 14
DETAIL_BACK_ICON_PX = 15
DETAIL_NAV_SIDE_PADDING = 10
DETAIL_TOP_FADE = 110  # how deep the dark fade under them reaches once scrolled
DETAIL_TOP_FADE_ALPHA = 215
COLOR_NAV = "rgba(22, 24, 38, 166)"  # the ground at 65%
COLOR_NAV_BORDER = COLOR_DIVIDER

# The game page's cards, as the design has them (Phase 57). Stats and Settings still use
# the DETAIL_CARD_* values below until their own step of the restyle.
GAME_CARD_PADDING_X = 20
GAME_CARD_PADDING_Y = 18
GAME_CARD_GAP = 18
GAME_CARD_TITLE_PX = 15
GAME_CARD_TITLE_GAP = 8  # between a card's title and what is in it
GAME_CARD_TEXT_PX = 13.5
GAME_CARD_TEXT_LINE = 1.6  # About and the updates; a note keeps its font's own spacing
COLOR_GAME_CARD_TEXT = COLOR_TEXT_SOFT
GAME_TEXT_BUTTON_PX = 12.5  # "Edit note...", "Read more"
GAME_WEEK_PX = 12  # "... this week", on the sessions card's title line
# The note: neutral 200, with a 2 px mark in the accent's dark step on its left.
COLOR_NOTE = COLOR_TEXT_BRIGHT
COLOR_NOTE_MARK = COLOR_ACCENT_700
NOTE_MARK = 2
NOTE_INDENT = 12

# The cards under the art.
DETAIL_CARD_RADIUS = 8
DETAIL_CARD_PADDING = 24
DETAIL_CARD_GAP = 20
DETAIL_CARD_TITLE_PX = 15  # every card's title, the design's (Phase 58; 19 before)
DETAIL_LEFT_WEIGHT = 3  # note, about, files, updates
DETAIL_RIGHT_WEIGHT = 2  # sessions and details
DETAIL_FACT_LABEL_WIDTH = 110
DETAIL_FACT_GAP = 14  # between a fact's label and its value
DETAIL_FACT_ROW_GAP = 8
DETAIL_CARD_TITLE_GAP = 14  # between a card's title and what is in it
DETAIL_CARD_BODY_GAP = 10
# Solid since Phase 54, with a hairline edge -- no longer translucent white glass.
COLOR_CARD = COLOR_SURFACE
COLOR_CARD_BORDER = COLOR_BORDER
COLOR_PILL = "rgba(233, 233, 237, 20)"
COLOR_PILL_BORDER = COLOR_DIVIDER

# Recent sessions as bars: one row each, the longest filling the room. Since Phase 57 the
# design's: 32 px rows, a day (86 px) and a length (62 px) either side of an 8 px bar on a
# track, each column wider if its words need it.
SESSION_ROW_HEIGHT = 32
SESSION_BAR_HEIGHT = 8
SESSION_TEXT_PX = 12.5
SESSION_COLUMN_GAP = 14
SESSION_DAY_WIDTH = 86
SESSION_LENGTH_WIDTH = 62
SESSIONS_TOP = 4  # the rows start this much further under the card's title
SESSION_MIN_BAR_PX = 4  # a two-minute session beside a three-hour one must still show
SESSION_MIN_BAR_FRACTION = 0.03  # and never under 3% of the room, as the design draws it
SESSION_BAR_ROOM = 160  # the room a bar asks for; it takes whatever the card has
SESSION_BAR_MIN_ROOM = 40
COLOR_SESSION_DAY = COLOR_TEXT_QUIET
COLOR_SESSION_LENGTH = COLOR_TEXT_BRIGHT
COLOR_SESSION_TRACK = COLOR_SURFACE_RAISED
# Bars run from the accent's dark step to the accent itself (Phase 54; violet before).
COLOR_SESSION_BAR_START = COLOR_ACCENT_700
COLOR_SESSION_BAR_END = COLOR_ACCENT

# How far one press of up or down on the pad scrolls the page.
DETAIL_PAD_SCROLL = 160

# --------------------------------------------------------------------------------------
# Phase 34: motion -- a cover that flies, tiles that arrive, focus that glides
# --------------------------------------------------------------------------------------

# Opening a game from its tile: the cover lifts off the grid and settles into its place on
# the game's page, and flies back into its tile on the way out when that tile is in view.
COVER_FLIGHT_MS = 420
COVER_FLIGHT_EASING = "InOutCubic"

# The tiles arrive in a quick wave when the library first appears, and again when a chip,
# the sort or a switch changes what is in the grid -- never on a background refresh, which
# happens every minute while a game runs and would make the wall shimmer for nothing.
TILE_ENTRANCE_MS = 240
TILE_ENTRANCE_STAGGER_MS = 18  # between one tile starting and the next
TILE_ENTRANCE_STAGGERED = 20  # tiles past this many start together: they are off screen
TILE_ENTRANCE_RISE = 12  # pixels a tile rises as it fades in
TILE_ENTRANCE_EASING = "OutCubic"

# The tile the pad or the keyboard is on grows, lifts, rings and glows over this long,
# instead of snapping, and the one it left settles back the same way.
FOCUS_DURATION_MS = 140
FOCUS_EASING = "OutCubic"

# --------------------------------------------------------------------------------------
# Phase 35: Stats, Storage and Settings in the new style, and a pass over TV mode
# --------------------------------------------------------------------------------------

# Stats and Storage sit on the library's glow, their blocks in cards.
STORAGE_TREEMAP_RADIUS = 8
STORAGE_TREEMAP_TILE_GAP = 4
# Phase 58: menus, tooltips and the message card on the surface with a hairline edge; a
# chosen menu entry accent 900 with accent-100 words, not a flood of the accent. A button
# with no look of its own is the design's quiet one, 6 x 10 inside.
COLOR_MENU = COLOR_SURFACE
COLOR_MENU_EDGE = COLOR_BORDER
COLOR_MENU_SELECTED = COLOR_ACCENT_900
COLOR_MENU_SELECTED_TEXT = COLOR_ACCENT_100
COLOR_TOAST = COLOR_SURFACE
COLOR_TOAST_EDGE = COLOR_BORDER
BUTTON_PADDING_X = 10
BUTTON_PADDING_Y = 6
# Settings: a page of sections, each row a title, a quieter line under it, and a switch.
SETTINGS_WIDTH = 640
SETTINGS_TITLE_PX = 26
SETTINGS_SECTION_PX = 15
SETTINGS_ROW_PX = 14
SETTINGS_HINT_PX = 12
SETTINGS_SCREEN_FRACTION = 0.86  # never taller than this share of the screen; it scrolls
# Steam accounts (Phase 75): whose time counts, a segmented switch of three per account, the
# game page's switch at the dialog's size. Not decided is where every account starts.
STEAM_ACCOUNT_MARKS = ((True, "Mine"), (False, "Not mine"), (None, "Not decided"))
SETTINGS_SEGMENT_HEIGHT = 32
# Game folders (Phase 77): the list in the first-run question and in Settings, a few rows tall.
FOLDER_LIST_ROWS = 3
FOLDER_LIST_ROW_PX = 30
FIRST_RUN_WIDTH = 620
TRAY_OFFER_WIDTH = 560  # the one question (Phase 99), a little narrower: three short paragraphs
# What's new (Phase 106): a version's notes, scrolled in a box this tall.
WHATS_NEW_WIDTH = 640
WHATS_NEW_TEXT_HEIGHT = 380
WHATS_NEW_PADDING = 12
# Fill missing covers (Phase 105): the games listed by name, a few rows tall and scrolled past that.
FILL_COVERS_WIDTH = 580
FILL_COVERS_LIST_ROWS = 8
FIRST_RUN_TEXT_PX = 14
# The anonymous export's dialog (Phase 80): what is in the file, read before saving it.
ANALYSIS_WIDTH = 660
ANALYSIS_TEXT_PX = 14
ANALYSIS_HEADING_PX = 15
# The library with nothing in it says why (Phase 77): a title, a line, a button, centred.
EMPTY_TITLE_PX = 22
EMPTY_TEXT_PX = 14
EMPTY_TEXT_WIDTH = 520
SWITCH_WIDTH = 44
SWITCH_HEIGHT = 24
SWITCH_KNOB_MARGIN = 3
SWITCH_MS = 120
COLOR_SWITCH_OFF = COLOR_BORDER
# The TV hint bar: glass over the glow rather than a solid strip.
COLOR_HINT_BAR = "rgba(22, 24, 38, 190)"

# --------------------------------------------------------------------------------------
# Phase 60: the side rail -- the design's #1b, at the desk
# --------------------------------------------------------------------------------------

# The library's tabs, its filters and where its games were found, in a column on the left,
# with three of the games played last as wide cards above the grid. At the desk only, and
# a choice in Settings; TV mode keeps the top bar, as the design pairs its rail with the
# desk. config.json's "library_layout".
LAYOUT_RAIL, LAYOUT_TOP = "rail", "top"
LIBRARY_LAYOUT_DEFAULT = LAYOUT_RAIL

# The rail: 232 px, 22 / 14 / 16 inside, the surface at 60% at its top fading to nothing,
# its right edge a line of the text at 7%.
RAIL_WIDTH = 232
RAIL_PADDING_TOP = 22
RAIL_PADDING_X = 14
RAIL_PADDING_BOTTOM = 16
COLOR_RAIL_TOP = "#992b2741"  # #AARRGGBB: painted, so QColor's form; the accent's 900 at 60% since Phase 99
COLOR_RAIL_EDGE = "#12e9e9ed"
RAIL_ITEM_PADDING = 10  # every row's words start this far in
RAIL_ICON_GAP = 11  # between a row's icon and its words
# The brand: the filled controller 22 px in the accent, 10 px before "Game Launcher" (15 px
# Medium); 22 px under it.
RAIL_BRAND_PX = 22
RAIL_BRAND_GAP = 10
RAIL_BRAND_TEXT_PX = 15
RAIL_BRAND_BELOW = 22
# Library, Stats, Storage: 36 high, 2 apart, 8 px corners, 13.5 px words in neutral 300,
# 17 px icons; the current one accent 900 with accent-200 words and a 2 px accent mark.
RAIL_NAV_HEIGHT = 36
RAIL_NAV_GAP = 2
RAIL_NAV_PX = 13.5
RAIL_NAV_ICON_PX = 17
RAIL_MARK = 2
COLOR_RAIL_CHOSEN = COLOR_ACCENT_900
COLOR_RAIL_CHOSEN_TEXT = COLOR_ACCENT_200
COLOR_RAIL_ITEM = COLOR_TEXT_SOFT
COLOR_RAIL_HOVER = "#12e9e9ed"  # the text at 7%, as every quiet control's hover
# A line between the groups (18 px above and below, 4 in, fading in over 48 px at each
# end) and each group's label: 10.5 px capitals 0.12 em apart in neutral 500, 8 px above.
RAIL_DIVIDER_MARGIN = 18
RAIL_DIVIDER_SIDE = 4
RAIL_DIVIDER_FADE = 48
COLOR_RAIL_DIVIDER = "#29e9e9ed"  # the divider, in QColor's form
RAIL_LABEL_PX = 10.5
RAIL_LABEL_TRACKING = 0.12
RAIL_LABEL_BELOW = 8
COLOR_RAIL_LABEL = COLOR_TEXT_MUTED
# The five filters: 32 high, 1 apart, 13 px, 15 px icons, the count 11.5 px in neutral 500
# at the right; the chosen one the text colour over the text at 6%.
RAIL_FILTER_HEIGHT = 32
RAIL_FILTER_GAP = 1
RAIL_FILTER_PX = 13
RAIL_FILTER_ICON_PX = 15
RAIL_COUNT_PX = 11.5
COLOR_RAIL_FILTER_CHOSEN = "#0fe9e9ed"
# Found in: 30 high, a 6 px dot in neutral 600 before each store, its count at the right.
RAIL_SOURCE_HEIGHT = 30
RAIL_SOURCE_DOT = 6
COLOR_RAIL_DOT = COLOR_TEXT_FAINT
# At its foot: "Play something" as a quiet accent button (12.5 px, a 15 px shuffle, 6 x 8
# inside), and the rescan and settings buttons, 32 px squares with 16 px icons in neutral 400.
RAIL_FOOT_SIDE = 4
RAIL_FOOT_GAP = 4
RAIL_PLAY_PX = 12.5
RAIL_PLAY_ICON_PX = 15
RAIL_BUTTON = 32
RAIL_BUTTON_ICON_PX = 16
COLOR_RAIL_BUTTON_ICON = COLOR_TEXT_QUIET

# Beside the rail, every page starts 24 px down and 32 px in. The library's header: its name
# 26 px Medium 0.02 em tighter, what it holds 13 px in neutral 500, 16 px apart; the search
# 280 x 34. Stats and Storage carry their name the same way.
RAIL_PAGE_TOP = 24
RAIL_PAGE_SIDE = 32
RAIL_PAGE_GAP = 22  # between the header, Jump back in and All games
PAGE_TITLE_PX = 26
PAGE_TITLE_TRACKING = -0.02  # em
PAGE_META_PX = 13
PAGE_HEADER_GAP = 16
RAIL_SEARCH_WIDTH = 280
RAIL_SEARCH_HEIGHT = 34
# "JUMP BACK IN", "ALL GAMES": the rail's labels, 10 px over the cards and 12 over the grid.
SECTION_LABEL_PX = RAIL_LABEL_PX
SECTION_LABEL_TRACKING = RAIL_LABEL_TRACKING
JUMP_LABEL_BELOW = 10
GRID_LABEL_BELOW = 12
# "Sort by Name": quiet words rather than a pill, 12 px, the choice in the text colour.
SORT_PLAIN_PX = 12

# Jump back in: the three games played last that are not finished or dropped -- the Continue
# card's rule -- as cards 178 px high, 14 apart, the first wider (1.35 : 1 : 1) and edged in
# accent 600, the others with the hairline; 14 px corners; the art under the ground at 92%
# from the foot to 8% up, gone by 70%; 16 px in and 14 up, the name 16 px Medium over a
# 12 px line in neutral 300, and a round Play 34 px, outlined in the accent on the ground
# at 60%, its icon 13 px.
JUMP_COUNT = 3
JUMP_HEIGHT = 178
JUMP_GAP = 14
JUMP_WEIGHTS = (135, 100, 100)
JUMP_RADIUS = 14
JUMP_SCRIM = ((0.0, 235), (0.08, 235), (0.70, 0))  # from the foot up
COLOR_JUMP_FIRST_EDGE = COLOR_ACCENT_600
JUMP_PADDING_X = 16
JUMP_PADDING_BOTTOM = 14
JUMP_NAME_PX = 16
JUMP_META_PX = 12
JUMP_TEXT_GAP = 10  # between the words and Play
JUMP_PLAY = 34
JUMP_PLAY_ICON_PX = 13
COLOR_JUMP_META = COLOR_TEXT_SOFT
# The rail names the scanner's folders as the design does; every other store keeps the name
# rules.SOURCE_LABELS gives it ("Found on disk" would read oddly under "Found in").
RAIL_SOURCE_LABELS = {"folders": "Folders"}

# --------------------------------------------------------------------------------------
# Phase 84: the Reports page -- the reports as the Stats page's cards
# --------------------------------------------------------------------------------------

REPORTS_CONTENT_MAX_WIDTH = STATS_CONTENT_MAX_WIDTH  # one column, as Stats and Storage
REPORT_CARD_PADDING = (STATS_LIST_PADDING_X, STATS_LIST_PADDING_Y)
REPORT_CARD_TITLE_GAP = 6
REPORT_QUESTION_PX = 13          # the question, under the card's title, quiet
REPORT_SENTENCE_PX = 15          # the answer: the card's own words
REPORT_PART_PX = 11              # a part's heading, small capitals
REPORT_PART_TRACKING = 0.08      # em
REPORT_TABLE_PX = 12.5           # a part's table
REPORT_NOTE_PX = 13              # a part's line of words
REPORT_CAVEAT_PX = 12.5          # what it cannot see, and the idea: the quiet style
REPORT_PART_GAP = 14             # between the parts of one card
REPORT_BAR_ROW_HEIGHT = 26       # a ShareBars row (the session bars' are 32)
REPORT_BAR_LABEL_MAX = 240       # a bar's words are cut beyond this, the full words in its tooltip
REPORT_TABLE_CELL_PAD_X = 10     # between a table's columns
REPORT_TABLE_CELL_PAD_Y = 3
REPORT_TABLE_ROWS = 20           # a table's rows on the page; the CSV and the Markdown have them all
REPORT_LORENZ_WIDTH = 300        # the concentration card's Lorenz curve, painted like the month chart
REPORT_LORENZ_HEIGHT = 190
REPORT_LORENZ_LINE = 2.0
COLOR_REPORT_LORENZ = COLOR_ACCENT
COLOR_REPORT_LORENZ_FILL = "#2e9184d9"    # the accent at 18%: the area between curve and diagonal
COLOR_REPORT_DIAGONAL = "#59cfd3e5"       # soft text at 35%: equality, the diagonal
COLOR_REPORT_AXIS_TEXT = COLOR_TEXT_MUTED
COLOR_REPORT_TABLE_HEAD = COLOR_TEXT_MUTED
COLOR_REPORT_TABLE_TEXT = COLOR_TEXT_SOFT

# -- Phase 87: the Wishlist page -- Storage's rows, one wished game each, under two chips --------------
WISHLIST_CONTENT_MAX_WIDTH = STATS_CONTENT_MAX_WIDTH  # one column, as Stats, Storage and Reports
WISHLIST_ROW_HEIGHT = 92
WISHLIST_ROW_GAP = 8
WISHLIST_ROW_RADIUS = STORAGE_ROW_RADIUS
WISHLIST_ROW_PADDING = 12
WISHLIST_ART_HEIGHT = 68  # the portrait cover at 2:3, as on the grid
WISHLIST_ART_RADIUS = 4
WISHLIST_ART_GAP = 16  # between the cover and the words
WISHLIST_NAME_PX = 15
WISHLIST_LINE_PX = 12.5
WISHLIST_PRICE_PX = 16
WISHLIST_PRICE_COLUMN = 250  # the right-hand words: today's price, the one before, the series
WISHLIST_LINE_GAP = 3
WISHLIST_TAG_PX = 10  # "Lowest seen" and the discount, small, as Storage's tag
WISHLIST_TAG_PADDING_X = 7
WISHLIST_TAG_PADDING_Y = 1
WISHLIST_TAG_RADIUS = 6
WISHLIST_TAG_GAP = 10
WISHLIST_GROUP_HEIGHT = 40  # "No longer on your list", folded
WISHLIST_GROUP_PX = 13
WISHLIST_CHIPS_GAP = 8
COLOR_WISHLIST_ROW = COLOR_STORAGE_ROW
COLOR_WISHLIST_ART = COLOR_SURFACE_RAISED  # a cover not fetched yet
COLOR_WISHLIST_FIT = COLOR_TEXT_QUIET
ALERT_DIALOG_WIDTH = 440  # Alert me under... (Phase 101)

# How was it? (Phase 102): the rating card, bottom-right where the toast floats, but taking clicks.
RATE_CARD_PADDING = (18, 14)  # left/right, top/bottom
RATE_CARD_GAP = 8  # between the question and the stars
RATE_STAR_PX = 26  # a star's glyph
RATE_STAR_BOX = 34  # the room a star takes, its click target
RATE_STAR_GAP = 4
RATE_SKIP_GAP = 14  # before Skip
RATE_TITLE_PX = 14
RATE_SKIP_PX = 13
RATE_THANKS_MS = 1300  # "Thanks" stays this long, then the card goes
RATE_FADE_MS = 160
RATE_SESSION_STAR_PX = 12  # a session's stars on a game's page, Recent sessions
RATE_SESSION_STAR_GAP = 2
RATE_SESSION_STARS_GAP = 12  # between a session's length and its stars
COLOR_WISHLIST_META = COLOR_TEXT_MUTED
COLOR_WISHLIST_WAS = COLOR_TEXT_FAINT  # the price before the discount, struck through
COLOR_WISHLIST_DISCOUNT = NEW_BADGE_COLOR  # filled, the NEW tag's accent 800 with accent 100 words
COLOR_WISHLIST_DISCOUNT_TEXT = NEW_BADGE_TEXT_COLOR
COLOR_WISHLIST_LOWEST = COLOR_ACCENT  # outlined, as Storage's tag
COLOR_WISHLIST_GROUP = COLOR_TEXT_QUIET
# Phase 89: a wished game's prices as a small line, left of the price column, from three prices on
WISHLIST_SPARK_WIDTH = 72
WISHLIST_SPARK_HEIGHT = 24
WISHLIST_SPARK_GAP = 14  # between the line and the price column; the words stop this far before it
WISHLIST_SPARK_PEN = 1.5
WISHLIST_SPARK_DOT = 2.5  # the radius of today's price, the line's right end
COLOR_WISHLIST_SPARK = COLOR_ACCENT

# The tray icon's menu (Phase 92): the games played last, each one click from Play.
RECENT_TRAY_GAMES = 5
TRAY_BALLOON_MS = 8000  # how long the first-hide balloon asks Windows to show itself

# -- The recap card (Phase 96): one image, the same pixels on every screen --------------------------
# A 4:5 portrait that phones and chat apps show whole, in logical pixels at device pixel ratio 1: the
# card is painted straight onto an image this size with pixel-sized fonts, so the TV at 225% and a
# desk at 100% make the same file. Every size below is in the card's own pixels, never scaled.
RECAP_IMAGE_WIDTH = 1080
RECAP_IMAGE_HEIGHT = 1350
RECAP_DPI = 96  # the image's own dots per inch, and what its fonts are measured on
RECAP_MARGIN = 72
RECAP_BRAND_PX = 28
RECAP_BRAND_ICON_PX = 34
RECAP_TITLE_PX = 24  # "Month in review", top right
RECAP_PERIOD_PX = 30
RECAP_PERIOD_TRACKING = 3.0
RECAP_PERIOD_TOP = 70  # below the brand's line
RECAP_HERO_TOP = 108
RECAP_HEADLINE_PX = 200  # the hours, in the display face
RECAP_UNIT_PX = 64
RECAP_COUNT_PX = 34
RECAP_COUNT_RAISE = 100  # the two count lines start this far above the headline's baseline
RECAP_COMPARISON_PX = 30
RECAP_SECTION_PX = 22
RECAP_SECTION_TRACKING = 2.5
RECAP_SECTION_GAP = 44  # from a section's label to what it heads
RECAP_COVER_GAP = 72  # between the covers' columns; three fill the card's width
RECAP_COVER_ASPECT = 4 / 3  # height over width: a 2:3 cover cropped from its foot, where titles are not
RECAP_COVER_ANCHOR = 0.0  # crop from the bottom only: a cover's title sits at its top
RECAP_COVER_RADIUS = 14
RECAP_BADGE_PX = 48  # the rank on a cover, at its bottom left
RECAP_BADGE_FILL = "#e6161826"  # the ground at 90%
RECAP_NAME_PX = 24
RECAP_TIME_PX = 24
RECAP_BAR_HEIGHT = 8
RECAP_SINGLE_COVER = (340, 510)  # one game: its cover, larger, with its lines beside it
RECAP_SINGLE_NAME_PX = 44
RECAP_SINGLE_LINE_PX = 30
RECAP_FACT_HEIGHT = 104
RECAP_FACT_GAP = 16
RECAP_FACT_RADIUS = 18
RECAP_FACT_ICON_PX = 34
RECAP_FACT_LABEL_PX = 18
RECAP_FACT_LABEL_TRACKING = 1.5
RECAP_FACT_VALUE_PX = 28
RECAP_FACT_DETAIL_PX = 21
RECAP_FACT_ICONS = {"longest": "clock", "when": "history", "new": "star", "money": "wishlist"}
RECAP_EMPTY_TITLE_PX = 64
RECAP_EMPTY_LINE_PX = 30
RECAP_FOOTER_PX = 21
RECAP_GLOW_HEIGHT = 760  # the first game's art, blurred into the top of the card
RECAP_GLOW_OPACITY = 0.55
RECAP_GLOW_SAMPLE = (18, 22)  # blurred by scaling down to this and back up
RECAP_GLOW_TOP_ALPHA = 120  # the ground over the art at the very top; opaque by the glow's foot
# The dialog's preview: the card scaled to this height at 100%, or this share of the screen on the TV.
RECAP_PREVIEW_HEIGHT = 560
RECAP_PREVIEW_TV_SHARE = 0.62
# Painting one card, covers read from disk included: measured 37-39 ms for September 2026 (three covers,
# three facts) on this PC, 6 ms for an empty month. The bound is four times the busiest measure.
RECAP_RENDER_MAX_MS = 150
RECAP_DIALOG_MARGIN = 20
# The painter's spacings, in the card's pixels.
RECAP_TEXT_SLACK = 4  # a line's box past its words, so nothing at its right edge is clipped
RECAP_BRAND_DROP = 2
RECAP_BRAND_GAP = 12
RECAP_TITLE_DROP = 6
RECAP_HEADLINE_KERN = 6  # the big number set back by its own side bearing, to the margin's line
RECAP_UNIT_GAP = 8
RECAP_COUNT_GAP = 48
RECAP_COUNT_LINE_GAP = 6
RECAP_HERO_FOOT = 12
RECAP_COMPARISON_RAISE = 44  # the counts move up a line when the comparison joins them
RECAP_FOOTER_CLEARANCE = 24  # the least room between the content and the footer's hairline
RECAP_SECTION_TOP = 8
RECAP_BADGE_INSET = 14
RECAP_BADGE_TEXT_DROP = 8
RECAP_BADGE_TEXT_PX = 26
RECAP_BADGE_TEXT_WEIGHT = 700
RECAP_NAME_TOP = 16
RECAP_NAME_GAP = 2
RECAP_TIME_GAP = 12
RECAP_PLACEHOLDER_NAME_PX = 28
RECAP_PLACEHOLDER_INSET = 16
RECAP_SINGLE_GAP = 48
RECAP_SINGLE_TOP = 8
RECAP_SINGLE_NAME_GAP = 10
RECAP_SINGLE_SUB_PX = 28
RECAP_SINGLE_FIRST_GAP = 30
RECAP_SINGLE_LINE_GAP = 10
RECAP_FACTS_TOP = 28
RECAP_FACT_INSET = 22
RECAP_FACT_TEXT_X = 74
RECAP_FACT_TEXT_END = 18
RECAP_FACT_LABEL_TOP = 16
RECAP_FACT_VALUE_TOP = 37
RECAP_FACT_DETAIL_TOP = 71
RECAP_EMPTY_TOP = 40
RECAP_EMPTY_GAP = 24
RECAP_EMPTY_LINE_GAP = 10
RECAP_FOOTER_LINE_GAP = 2
RECAP_FOOTER_DROP = 10
RECAP_FOOTER_RULE_GAP = 22
RECAP_RULE_PX = 1.5
# The year's card: five covers in the row of three's width, then the twelve months as Stats draws them.
RECAP_YEAR_COVER_GAP = 24
RECAP_YEAR_NAME_PX = 20
RECAP_MONTH_BAR_WIDTH = 46
RECAP_MONTH_PLOT = 96  # the tallest month's bar
RECAP_MONTH_STUB = 4  # a month not recorded, or recorded and quiet: a stub, never nothing
RECAP_MONTH_LABEL_PX = 18
RECAP_MONTH_LABEL_GAP = 8
RECAP_MONTH_CAPTION_GAP = 12
RECAP_SQUEEZE_FLOOR = 0.7  # covers give way to the words, but never below this share of their height
RECAP_NAME_ROOM = 0.45  # a name shortened to less than this share of its card reads as nothing
RECAP_DIALOG_SPACING = 14

# -- For you (Phase 98): a place of its own, under Library -----------------------------------------
FORYOU_CONTENT_MAX_WIDTH = STATS_CONTENT_MAX_WIDTH  # one column, as Stats, Reports and the Wishlist
FORYOU_SUBTITLE_PX = 14
FORYOU_SECTION_PX = 11  # "WAITING FOR YOU", "ALSO WAITING", "TONIGHT"
FORYOU_SECTION_TRACKING = 1.8
FORYOU_SECTION_GAP = 16  # between the page's parts
FORYOU_PICK_COVER = (120, 174)  # a waiting game shown large: its cover
FORYOU_PICK_PADDING = 14
FORYOU_PICK_GAP = 20  # between the three
FORYOU_PICK_NAME_PX = 17
FORYOU_PICK_LIKE_PX = 14
FORYOU_PICK_TEXT_PX = 13
FORYOU_ROW_COVER = (24, 32)  # the rest of the ranking: a line each
FORYOU_ROW_HEIGHT = 44
FORYOU_ROW_NAME_PX = 14
FORYOU_ROW_TEXT_PX = 13
FORYOU_ROW_REASON_AT = 0.36  # the reason starts this far across the row; the time played at the right
FORYOU_TONIGHT_COVER = (42, 56)
FORYOU_TONIGHT_HEIGHT = 78
FORYOU_ROUND_PX = 34  # a game's round Play button
FORYOU_LEFT_PER_LINE = 2  # Left behind's cards side by side (Phase 103): each carries three answers
FORYOU_LEFT_COVER = (42, 56)
FORYOU_NOTE_PX = 12  # the quieter lines: what the score means, the cold start, who was left out
FORYOU_RADIUS = 14
FORYOU_THUMB_RADIUS = 8

# --------------------------------------------------------------------------------------
# The accent (Phase 99): a colour of your own
# --------------------------------------------------------------------------------------

# Five families, Violet first -- today's, the token sheet's (Phase 54) -- each nine steps from palest to darkest,
# 500 the accent itself and 400 its hover. Built as the sheet built Violet: in OKLCH, every step at Violet's own
# lightness (so every documented ratio survives), a hue of its own, the chroma as near Violet's as a screen can
# show it. Every pair the interface draws text or a mark with passes WCAG AA on the dark surfaces (step 0's
# table; a test computes it). The Nocturne base stays the only base: the scrims over art assume a dark ground.
ACCENTS = {
    "Violet": {100: "#f5f4ff", 200: "#e7e5fe", 300: "#d2cefd", 400: "#b5abfc", 500: "#9184d9", 600: "#796cbf",
               700: "#5d5294", 800: "#423a6a", 900: "#2b2741"},
    "Teal": {100: "#ecf9f8", 200: "#d2efed", 300: "#a7e1de", 400: "#58cdc9", 500: "#06a8a4", 600: "#048c89",
             700: "#036c69", 800: "#034d4b", 900: "#0a3231"},
    "Amber": {100: "#fcf4eb", 200: "#f6e5d1", 300: "#efcea7", 400: "#e4ab62", 500: "#c0852f", 600: "#a66c07",
              700: "#805202", 800: "#5c3a04", 900: "#39270f"},
    "Rose": {100: "#fef2f4", 200: "#fce0e4", 300: "#f8c5cd", 400: "#f19baa", 500: "#cd7385", 600: "#b35b6d",
             700: "#8a4453", 800: "#63303b", 900: "#3e2227"},
    "Slate": {100: "#f3f6fa", 200: "#e2e9f2", 300: "#c9d6e6", 400: "#a3b9d6", 500: "#7d94b2", 600: "#667c99",
              700: "#4d5f76", 800: "#364354", 900: "#252c35"},
}
ACCENT_DEFAULT = "Violet"
ACCENT_KEY = "accent"  # config.json, by its own key
# Every colour above that is a step of the accent, by name: what a switch sets (ui_theme.use_accent). The
# per-game colour (ui_theme.accent_for) and the glow from a game's art are the game's, never the theme's.
ACCENT_STEPS = {
    "COLOR_ACCENT": 500, "COLOR_ACCENT_HOVER": 400, "COLOR_ACCENT_100": 100, "COLOR_ACCENT_200": 200,
    "COLOR_ACCENT_300": 300, "COLOR_ACCENT_600": 600, "COLOR_ACCENT_700": 700, "COLOR_ACCENT_800": 800,
    "COLOR_ACCENT_900": 900, "FAVORITE_BADGE_COLOR": 300, "NEW_BADGE_COLOR": 800, "NEW_BADGE_TEXT_COLOR": 100,
    "NEW_BADGE_EDGE": 600, "COLOR_CHART_BAR": 500, "COLOR_CHART_BAR_FOOT": 700, "COLOR_CHART_BASELINE": 700,
    "COLOR_RECLAIM": 900, "COLOR_RECLAIM_EDGE": 800, "COLOR_RECLAIM_ICON": 300, "COLOR_RECLAIM_TITLE": 100,
    "COLOR_RECLAIM_LINE": 300, "COLOR_STORAGE_GAMES": 500, "COLOR_STORAGE_GAMES_START": 600,
    "COLOR_STORAGE_TAG": 500, "TILE_FOCUS_COLOR": 500, "COLOR_PILL_SAVED": 200, "COLOR_NOTE_MARK": 700,
    "COLOR_SESSION_BAR_START": 700, "COLOR_SESSION_BAR_END": 500, "COLOR_MENU_SELECTED": 900,
    "COLOR_MENU_SELECTED_TEXT": 100, "COLOR_RAIL_CHOSEN": 900, "COLOR_RAIL_CHOSEN_TEXT": 200,
    "COLOR_JUMP_FIRST_EDGE": 600, "COLOR_REPORT_LORENZ": 500, "COLOR_WISHLIST_DISCOUNT": 800,
    "COLOR_WISHLIST_DISCOUNT_TEXT": 100, "COLOR_WISHLIST_LOWEST": 500, "COLOR_WISHLIST_SPARK": 500,
    # Phase 99, so a choice shows: the small uppercase labels, a chosen chip's fill.
    "COLOR_SECTION_LABEL": 500, "COLOR_CHIP_CHOSEN": 900,
}
# And the steps written in another form: (step, "rgba" for a stylesheet or "argb" for QColor, alpha 0-255).
ACCENT_FORMS = {
    "COLOR_PRIMARY_HOVER": (500, "rgba", 31), "COLOR_PRIMARY_PRESSED": (500, "rgba", 56),
    "COLOR_TEXT_BUTTON_HOVER": (500, "rgba", 26), "COLOR_STORAGE_BAR": (500, "argb", 0x29),
    "COLOR_STORAGE_STALE_BAR": (400, "argb", 0x38), "COLOR_REPORT_LORENZ_FILL": (500, "argb", 0x2E),
    # Phase 99: the rail's ground carries the accent's darkest step, and a scroll bar under the mouse its own.
    "COLOR_RAIL_TOP": (900, "argb", 0x99), "COLOR_SCROLL_HOVER": (500, "rgba", 150),
}
ACCENT_STATUS = {"playing": 400, "finished": 300}  # STATUS_COLORS' two in the accent; "dropped" stays muted
# The new names at Violet, as the table above makes them (a test holds every one to it).
COLOR_SECTION_LABEL = COLOR_ACCENT  # JUMP BACK IN, ALL GAMES, the rail's SHOW and FOUND IN, For you's
COLOR_CHIP_CHOSEN = COLOR_ACCENT_900  # a chosen chip or switch above the grid, filled as the rail's place
COLOR_SCROLL_HOVER = "rgba(145, 132, 217, 150)"
COLOR_SCROLL_HANDLE = "rgba(233, 233, 237, 40)"  # at rest: neutral, out of the way

# Settings' row of swatches: a round colour each, the chosen one ringed inside its own button, its name under.
ACCENT_SWATCH_PX = 24  # the colour's diameter
ACCENT_SWATCH_WIDTH = 56  # each swatch's button: the colour, the ring and the name
ACCENT_SWATCH_HEIGHT = 54
ACCENT_SWATCH_RING = 2  # the chosen one's ring
ACCENT_SWATCH_RING_GAP = 3  # between the colour and its ring
ACCENT_SWATCH_NAME_PX = 11

# A pill's edge (Phase 99, reported from use: "jacked" lines). At 1 px and 16% the straight sides fell on one
# row of pixels and looked sharp while the round ends spread over two half-lit ones and looked broken; a little
# wider with the interface's size and a little stronger, it reads as one even line all round.
PILL_EDGE_WIDTH = 1.0  # times the interface scale, never under 1 px
COLOR_PILL_EDGE = "rgba(233, 233, 237, 56)"  # the text at 22%: the chips, the switches, the sort, the facts

# Starting... (Phase 99): the splash over the window, its picture made once (ui_splash)
LAUNCH_SPLASH_COVER = (180, 260)
LAUNCH_SPLASH_MARGIN = 120  # from the window's left edge to the cover
LAUNCH_SPLASH_BOTTOM = 130  # from the cover's foot to the window's
LAUNCH_SPLASH_TEXT_GAP = 36  # between the cover and the words
LAUNCH_SPLASH_EYEBROW_PX = 13
LAUNCH_SPLASH_EYEBROW_TRACKING = 1.8
LAUNCH_SPLASH_TITLE_PX = 52
LAUNCH_SPLASH_LINE_PX = 15
LAUNCH_SPLASH_HINT_PX = 13
LAUNCH_SPLASH_HINT_BOTTOM = 54
LAUNCH_SPLASH_DOT_PX = 4.5  # the three dots' radius
LAUNCH_SPLASH_DOT_GAP = 18
LAUNCH_SPLASH_DOTS_BELOW = 22  # between the name's last line and the dots
LAUNCH_SPLASH_DOT_MS = 420  # one dot lit after another
LAUNCH_SPLASH_FADE_MS = 160
LAUNCH_SPLASH_SCRIM = ((0.0, 90), (0.45, 150), (1.0, 245))  # the ground over the art, top to foot
STARTING_TEXT = "Starting\u2026"  # Play while a game starts: on the tile, the page, the cards and the tray

# The genre pill (Phase 99): beside the sort pill; remembered by its own key
LIBRARY_GENRE_KEY = "library_genre"
GENRE_ALL = "All genres"
GENRE_NONE = "No genre known"  # the games with no Steam record, or no genre in it: never hidden by a filter
