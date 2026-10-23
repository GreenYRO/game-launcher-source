"""The recap card (Phase 96): a month, or a year, in review, painted as one image to pass on, and its dialog.

**The same pixels on every screen.** The card is painted straight onto an image of
RECAP_IMAGE_WIDTH x RECAP_IMAGE_HEIGHT at device pixel ratio 1, with every font sized in pixels and
every cover made at the card's own size -- no widget tree to lay out, no stylesheet, nothing that
reads the screen. So a window on the TV at 225% and one at the desk at 100% make identical files
(a test renders it in a second process under QT_SCALE_FACTOR=2.25 and compares). The dialog only
shows that image, scaled to fit, and copies or saves the image itself.

What it draws is logic/recap.py's Recap: only the lines that have something to say -- a month with
one session has its one cover and no facts about sessions; a month with none says so -- and never a
path, an account or anything else a friend should not see when the image is passed on.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from data_access import catalog_io
from logic import recap as recap_module
from logic import saves
from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_theme
from presentation.ui_covers import CoverFactory, is_image
from shared import paths
from shared import rules
from shared import version
from web import steam_web

log = logging.getLogger(__name__)

W, H, M = ui_rules.RECAP_IMAGE_WIDTH, ui_rules.RECAP_IMAGE_HEIGHT, ui_rules.RECAP_MARGIN


# -- covers --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Stand:
    """What the cover factory needs of a game the grid no longer shows (uninstalled since)."""

    key: str
    display_name: str
    cover_source: str
    icon_path: str = ""


class Art:
    """Each game's cover at the card's own size: a factory of its own, at ratio 1, never the screen's."""

    def __init__(self, icons, views_by_key: dict, cache_dir: str | None = None) -> None:
        self.factory = CoverFactory(icons)  # ratio 1.0: the card's pixels, whatever the screen
        self.views = views_by_key
        self.cache_dir = str(cache_dir or paths.cache_dir())

    def source(self, game) -> str:
        """The image a game's tile shows; for one no longer installed, the cover it was given, else
        Steam's cover from the cache. "" when there is none: the card draws its own panel."""
        view = self.views.get(game.identity_key)
        if view is not None:
            return view.cover_source if is_image(view.cover_source) else ""
        chosen = game.cover_path or ""
        if chosen and not os.path.isfile(chosen):
            chosen = catalog_io.relocated(chosen)  # the project folder may have moved (Phase 37)
        if chosen and os.path.isfile(chosen):
            return chosen
        return steam_web.capsule_path(self.cache_dir, game.steam_appid) if game.steam_appid else ""

    def cover(self, game, width: int, height: int) -> QPixmap | None:
        path = self.source(game)
        if not path:
            return None
        image = QImage(path)
        if image.isNull():
            return None
        if image.height() >= image.width():
            return self.factory.image(path, width, height, ui_rules.RECAP_COVER_ANCHOR)
        # Landscape art cropped to a portrait loses most of itself: shown whole on its own backdrop,
        # as the tiles do (with_name off -- the card writes the name, in its own pixels).
        view = self.views.get(game.identity_key) or _Stand(game.identity_key, game.name, path)
        return self.factory.cover(view, width, height, with_name=False)


# -- painting ------------------------------------------------------------------------------------


_DPM = round(ui_rules.RECAP_DPI / 0.0254)  # dots per metre: the card's own, never the screen's
_device: QImage | None = None


def _metrics(font: QFont) -> QFontMetrics:
    """A font measured on the card's kind of image, not on the screen: at 225% the screen's metrics
    measure the same pixel size differently, and the TV's card came out different (found by the test)."""
    global _device
    if _device is None:
        _device = QImage(1, 1, QImage.Format.Format_RGB32)
        _device.setDotsPerMeterX(_DPM)
        _device.setDotsPerMeterY(_DPM)
    return QFontMetrics(font, _device)


def _font(px: float, weight: int = ui_rules.BODY_WEIGHT, display: bool = False, tracking: float = 0.0) -> QFont:
    font = QFont(ui_icons.display_family() if display else ui_icons.body_family())
    font.setPixelSize(round(px))  # pixels, never points: points would read the screen's dpi
    # No hinting: hinted outlines are fitted to the device's pixel grid, which is the screen's.
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setWeight(QFont.Weight(weight))
    if tracking:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking)
    return font


class _Canvas:
    """A painter on the card's image, and the few ways the card writes and fills."""

    def __init__(self) -> None:
        self.image = QImage(W, H, QImage.Format.Format_RGB32)
        self.image.setDevicePixelRatio(1.0)
        self.image.setDotsPerMeterX(_DPM)  # a new QImage takes the screen's dpi; the card has its own
        self.image.setDotsPerMeterY(_DPM)
        self.image.fill(QColor(ui_rules.COLOR_BACKGROUND))
        self.p = QPainter(self.image)
        for hint in (QPainter.RenderHint.Antialiasing, QPainter.RenderHint.TextAntialiasing,
                     QPainter.RenderHint.SmoothPixmapTransform):
            self.p.setRenderHint(hint, True)
        self.drawn: list[str] = []  # every string put on the card, for the no-personal-data check

    def text(self, x, y, words, font, color, width=None, align=Qt.AlignmentFlag.AlignLeft) -> int:
        """Words with their top at y, cut with an ellipsis at width. Returns the line's height."""
        metrics = _metrics(font)
        if width:
            words = metrics.elidedText(words, Qt.TextElideMode.ElideRight, int(width))
        self.drawn.append(words)
        self.p.setFont(font)
        self.p.setPen(QColor(color))
        span = width or metrics.horizontalAdvance(words) + ui_rules.RECAP_TEXT_SLACK
        self.p.drawText(QRectF(x, y, span, metrics.height()), align | Qt.AlignmentFlag.AlignTop, words)
        return metrics.height()

    def glyph(self, name, x, y, px, color) -> None:
        family, character = ui_icons.glyph_for(name)
        if not family:
            return
        font = QFont(family)
        font.setPixelSize(px)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        self.p.setFont(font)
        self.p.setPen(QColor(color))
        self.p.drawText(QRectF(x, y, px, px), Qt.AlignmentFlag.AlignCenter, character)

    def rounded(self, rect, radius, fill, edge=None) -> None:
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        self.p.fillPath(path, QColor(fill))
        if edge:
            self.p.setPen(QPen(QColor(edge), ui_rules.RECAP_RULE_PX))
            self.p.drawPath(path)

    def picture(self, pixmap, rect, radius) -> None:
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        self.p.save()
        self.p.setClipPath(clip)
        self.p.drawPixmap(rect.toRect(), pixmap)
        self.p.restore()

    def done(self) -> QImage:
        self.p.end()
        return self.image


def _balanced(words: str, font: QFont, width: float) -> list[str]:
    """One line if it fits; else two, split at the space that makes the longer line shortest -- so
    "Marvel's Spider-Man 2" reads "Marvel's / Spider-Man 2", never "Marvel's Spider-Man / 2"."""
    metrics = _metrics(font)
    # With a line's slack to spare: a name that only just fits by its advance is cut by the ellipsis,
    # which measures the glyphs' own edges (Marvel's Spider-Man 2, once hinting was off).
    if metrics.horizontalAdvance(words) <= width - ui_rules.RECAP_TEXT_SLACK or " " not in words:
        return [words]
    parts = words.split(" ")
    splits = [(" ".join(parts[:i]), " ".join(parts[i:])) for i in range(1, len(parts))]
    return list(min(splits, key=lambda ab: max(metrics.horizontalAdvance(ab[0]), metrics.horizontalAdvance(ab[1]))))


def _placeholder(c: _Canvas, name: str, rect: QRectF, px: int = ui_rules.RECAP_PLACEHOLDER_NAME_PX) -> None:
    """A game with no art: its accent wash, as its tile has, and its name in the card's own pixels."""
    accent = ui_theme.accent_for(name)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0.0, accent)
    gradient.setColorAt(1.0, ui_theme.darken(accent, ui_rules.PLACEHOLDER_GRADIENT_DARKEN))
    path = QPainterPath()
    path.addRoundedRect(rect, ui_rules.RECAP_COVER_RADIUS, ui_rules.RECAP_COVER_RADIUS)
    c.p.fillPath(path, gradient)
    font = _font(px, ui_rules.HEADING_WEIGHT)
    lines = _balanced(name, font, rect.width() - 2 * ui_rules.RECAP_PLACEHOLDER_INSET)
    line = _metrics(font).height()
    top = rect.y() + (rect.height() - line * len(lines)) / 2
    for row, part in enumerate(lines):
        c.text(rect.x() + ui_rules.RECAP_PLACEHOLDER_INSET, top + row * line, part, font, ui_rules.COLOR_TEXT, width=rect.width() - 2 * ui_rules.RECAP_PLACEHOLDER_INSET,
               align=Qt.AlignmentFlag.AlignHCenter)


def _glow(c: _Canvas, path: str) -> None:
    """The first game's art blurred and darkened into the top of the card: the window's own backdrop."""
    image = QImage(path) if path else QImage()
    if image.isNull():
        return
    small = image.scaled(*ui_rules.RECAP_GLOW_SAMPLE, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    big = small.scaled(W, ui_rules.RECAP_GLOW_HEIGHT, Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    c.p.save()
    c.p.setOpacity(ui_rules.RECAP_GLOW_OPACITY)
    c.p.drawImage(0, 0, big)
    c.p.restore()
    ground = QColor(ui_rules.COLOR_BACKGROUND)
    fade = QLinearGradient(0, 0, 0, ui_rules.RECAP_GLOW_HEIGHT)
    top = QColor(ground)
    top.setAlpha(ui_rules.RECAP_GLOW_TOP_ALPHA)
    fade.setColorAt(0.0, top)
    fade.setColorAt(1.0, ground)
    c.p.fillRect(QRectF(0, 0, W, ui_rules.RECAP_GLOW_HEIGHT), fade)


def _header(c: _Canvas, recap) -> None:
    c.glyph("brand", M, M + ui_rules.RECAP_BRAND_DROP, ui_rules.RECAP_BRAND_ICON_PX, ui_rules.COLOR_ACCENT_HOVER)
    c.text(M + ui_rules.RECAP_BRAND_ICON_PX + ui_rules.RECAP_BRAND_GAP, M + ui_rules.RECAP_BRAND_DROP, version.APP_NAME,
           _font(ui_rules.RECAP_BRAND_PX, ui_rules.HEADING_WEIGHT), ui_rules.COLOR_TEXT)
    font = _font(ui_rules.RECAP_TITLE_PX)
    width = _metrics(font).horizontalAdvance(recap.title) + ui_rules.RECAP_TEXT_SLACK
    c.text(W - M - width, M + ui_rules.RECAP_TITLE_DROP, recap.title, font, ui_rules.COLOR_TEXT_MUTED)
    c.text(M, M + ui_rules.RECAP_PERIOD_TOP, recap.period.label.upper(),
           _font(ui_rules.RECAP_PERIOD_PX, ui_rules.HEADING_WEIGHT, tracking=ui_rules.RECAP_PERIOD_TRACKING),
           ui_rules.COLOR_ACCENT_HOVER)


def _hero(c: _Canvas, recap) -> float:
    """The hours, large, with the counts beside them -- and the comparison, a third line, so a month that has
    one is no taller than one that has not. Returns the bottom."""
    y = M + ui_rules.RECAP_HERO_TOP
    big = _font(ui_rules.RECAP_HEADLINE_PX, ui_rules.HEADING_WEIGHT, display=True)
    metrics = _metrics(big)
    baseline = y + metrics.ascent()
    c.p.setFont(big)
    c.p.setPen(QColor(ui_rules.COLOR_TEXT))
    c.p.drawText(QPointF(M - ui_rules.RECAP_HEADLINE_KERN, baseline), recap.headline)
    c.drawn.append(recap.headline)
    x = M - ui_rules.RECAP_HEADLINE_KERN + metrics.horizontalAdvance(recap.headline) + ui_rules.RECAP_UNIT_GAP
    unit = _font(ui_rules.RECAP_UNIT_PX, ui_rules.HEADING_WEIGHT, display=True)
    c.p.setFont(unit)
    c.p.setPen(QColor(ui_rules.COLOR_TEXT_MUTED))
    c.p.drawText(QPointF(x, baseline), recap.unit)
    c.drawn.append(recap.unit)
    x += _metrics(unit).horizontalAdvance(recap.unit) + ui_rules.RECAP_COUNT_GAP
    lines = [(words, _font(ui_rules.RECAP_COUNT_PX), colour)
             for words, colour in zip(recap.counts, (ui_rules.COLOR_TEXT, ui_rules.COLOR_TEXT_MUTED))]
    if recap.comparison:
        lines.append((recap.comparison[:1].upper() + recap.comparison[1:], _font(ui_rules.RECAP_COMPARISON_PX),
                      ui_rules.COLOR_TEXT_QUIET))
    line_y = baseline - ui_rules.RECAP_COUNT_RAISE - (ui_rules.RECAP_COMPARISON_RAISE if recap.comparison else 0)
    for words, font, colour in lines:
        line_y += c.text(x, line_y, words, font, colour, width=W - M - x) + ui_rules.RECAP_COUNT_LINE_GAP
    return baseline + ui_rules.RECAP_HERO_FOOT


def _section(c: _Canvas, y: float, label: str) -> float:
    c.text(M, y, label.upper(), _font(ui_rules.RECAP_SECTION_PX, ui_rules.HEADING_WEIGHT,
                                      tracking=ui_rules.RECAP_SECTION_TRACKING), ui_rules.COLOR_TEXT_MUTED)
    return y + ui_rules.RECAP_SECTION_GAP


def _columns(c: _Canvas, art: Art, y: float, games, year: bool = False, squeeze: float = 0) -> float:
    """A month's three columns, or a year's five: the cover, its rank, the name, the time, a bar against
    the first."""
    slots = rules.RECAP_YEAR_TOP_GAMES if year else rules.RECAP_TOP_GAMES
    gap = ui_rules.RECAP_YEAR_COVER_GAP if year else ui_rules.RECAP_COVER_GAP
    width = (W - 2 * M - gap * (slots - 1)) / slots
    nominal = width * ui_rules.RECAP_COVER_ASPECT
    height = round(max(nominal * ui_rules.RECAP_SQUEEZE_FLOOR, nominal - squeeze))
    name_px = ui_rules.RECAP_YEAR_NAME_PX if year else ui_rules.RECAP_NAME_PX
    name_font = _font(name_px, ui_rules.HEADING_WEIGHT)
    time_font = _font(ui_rules.RECAP_YEAR_NAME_PX if year else ui_rules.RECAP_TIME_PX)
    line = _metrics(name_font).height()
    bottom = y
    for rank, game in enumerate(games, start=1):
        x = M + (rank - 1) * (width + gap)
        rect = QRectF(x, y, width, height)
        pixmap = art.cover(game, round(width), height)
        if pixmap is None or pixmap.isNull():
            _placeholder(c, game.name, rect, ui_rules.RECAP_YEAR_NAME_PX if year else ui_rules.RECAP_PLACEHOLDER_NAME_PX)
        else:
            c.picture(pixmap, rect, ui_rules.RECAP_COVER_RADIUS)
        size = ui_rules.RECAP_BADGE_PX
        inset = ui_rules.RECAP_BADGE_INSET
        badge = QRectF(x + inset, y + height - size - inset, size, size)
        c.rounded(badge, size / 2, ui_rules.RECAP_BADGE_FILL)
        c.text(badge.x(), badge.y() + ui_rules.RECAP_BADGE_TEXT_DROP, str(rank),
               _font(ui_rules.RECAP_BADGE_TEXT_PX, ui_rules.RECAP_BADGE_TEXT_WEIGHT), ui_rules.COLOR_TEXT, width=size,
               align=Qt.AlignmentFlag.AlignHCenter)
        top = y + height + ui_rules.RECAP_NAME_TOP
        for row, part in enumerate(_balanced(game.name, name_font, width)):
            c.text(x, top + row * line, part, name_font, ui_rules.COLOR_TEXT, width=width)
        top += line * 2 + ui_rules.RECAP_NAME_GAP  # two lines kept for every name, so the bars line up
        top += c.text(x, top, game.time, time_font, ui_rules.COLOR_TEXT_MUTED, width=width) + ui_rules.RECAP_TIME_GAP
        bar = ui_rules.RECAP_BAR_HEIGHT
        c.rounded(QRectF(x, top, width, bar), bar / 2, ui_rules.COLOR_SURFACE)
        c.rounded(QRectF(x, top, max(bar, width * game.share), bar), bar / 2, ui_rules.COLOR_ACCENT)
        bottom = max(bottom, top + bar)
    return bottom


def _single(c: _Canvas, art: Art, y: float, recap, squeeze: float = 0) -> float:
    """One game: its cover larger, its name and what is known of its sessions beside it."""
    game = recap.top[0]
    width, nominal = ui_rules.RECAP_SINGLE_COVER
    height = round(max(nominal * ui_rules.RECAP_SQUEEZE_FLOOR, nominal - squeeze))
    rect = QRectF(M, y, width, height)
    pixmap = art.cover(game, width, height)
    if pixmap is None or pixmap.isNull():
        _placeholder(c, game.name, rect)
    else:
        c.picture(pixmap, rect, ui_rules.RECAP_COVER_RADIUS)
    x = M + width + ui_rules.RECAP_SINGLE_GAP
    span = W - M - x
    top = y + ui_rules.RECAP_SINGLE_TOP
    name_font = _font(ui_rules.RECAP_SINGLE_NAME_PX, ui_rules.HEADING_WEIGHT, display=True)
    for part in _balanced(game.name, name_font, span):
        top += c.text(x, top, part, name_font, ui_rules.COLOR_TEXT, width=span)
    top += ui_rules.RECAP_SINGLE_NAME_GAP
    for index, words in enumerate(recap.single):
        colour = ui_rules.COLOR_TEXT_MUTED if index == 0 else ui_rules.COLOR_TEXT_QUIET
        size = ui_rules.RECAP_SINGLE_LINE_PX if index == 0 else ui_rules.RECAP_SINGLE_SUB_PX
        top += c.text(x, top, words, _font(size), colour, width=span) + (
            ui_rules.RECAP_SINGLE_FIRST_GAP if index == 0 else ui_rules.RECAP_SINGLE_LINE_GAP)
    return y + height


def _facts(c: _Canvas, y: float, facts, columns: int = 2) -> float:
    """Small cards in rows of `columns`: an icon, a label, a value, a quieter line. An odd last one of two
    columns spans the row; a year's single row shares the width between its facts."""
    gap, height = ui_rules.RECAP_FACT_GAP, ui_rules.RECAP_FACT_HEIGHT
    half = (W - 2 * M - gap * (columns - 1)) / columns
    for index, fact in enumerate(facts):
        x = M + (index % columns) * (half + gap)
        top = y + (index // columns) * (height + gap)
        width = W - 2 * M if columns == 2 and index == len(facts) - 1 and index % 2 == 0 else half
        c.rounded(QRectF(x, top, width, height), ui_rules.RECAP_FACT_RADIUS, ui_rules.COLOR_SURFACE,
                  ui_rules.COLOR_BORDER)
        c.glyph(ui_rules.RECAP_FACT_ICONS.get(fact.kind, "info"), x + ui_rules.RECAP_FACT_INSET, top + ui_rules.RECAP_FACT_INSET, ui_rules.RECAP_FACT_ICON_PX,
                ui_rules.COLOR_ACCENT_HOVER)
        words = width - ui_rules.RECAP_FACT_TEXT_X - ui_rules.RECAP_FACT_TEXT_END
        c.text(x + ui_rules.RECAP_FACT_TEXT_X, top + ui_rules.RECAP_FACT_LABEL_TOP, fact.label.upper(), _font(ui_rules.RECAP_FACT_LABEL_PX, ui_rules.HEADING_WEIGHT,
                                                           tracking=ui_rules.RECAP_FACT_LABEL_TRACKING),
               ui_rules.COLOR_TEXT_MUTED, width=words)
        c.text(x + ui_rules.RECAP_FACT_TEXT_X, top + ui_rules.RECAP_FACT_VALUE_TOP, fact.value, _font(ui_rules.RECAP_FACT_VALUE_PX, ui_rules.HEADING_WEIGHT),
               ui_rules.COLOR_TEXT, width=words)
        detail = fact.detail
        font = _font(ui_rules.RECAP_FACT_DETAIL_PX)
        if fact.names:
            # As many of the names as fit, then how many more -- never a list cut off mid-name.
            metrics = _metrics(font)
            for room in range(rules.RECAP_NEW_GAMES, 0, -1):
                detail = recap_module.listing(fact.names, room)
                if metrics.horizontalAdvance(detail) <= words:
                    break
            else:
                # Even one name is too long: it is shortened, and how many more stays whole -- unless that
                # leaves the name too little room to read, when the name alone is shortened instead.
                rest = detail[len(fact.names[0]):]
                room = words - metrics.horizontalAdvance(rest)
                if room < words * ui_rules.RECAP_NAME_ROOM:
                    rest, room = "", words
                detail = metrics.elidedText(fact.names[0], Qt.TextElideMode.ElideRight, int(room)) + rest
        elif fact.short and _metrics(font).horizontalAdvance(detail) > words:
            detail = fact.short
        if detail:
            c.text(x + ui_rules.RECAP_FACT_TEXT_X, top + ui_rules.RECAP_FACT_DETAIL_TOP, detail, font, ui_rules.COLOR_TEXT_QUIET, width=words)
    rows = (len(facts) + columns - 1) // columns
    return y + rows * height + max(0, rows - 1) * gap


def _empty(c: _Canvas, y: float, recap) -> None:
    """A month with no sessions: a card that says so, not a row of zeros."""
    title, *lines = recap.empty_lines
    top = y + ui_rules.RECAP_EMPTY_TOP
    top += c.text(M, top, title, _font(ui_rules.RECAP_EMPTY_TITLE_PX, ui_rules.HEADING_WEIGHT, display=True),
                  ui_rules.COLOR_TEXT, width=W - 2 * M) + ui_rules.RECAP_EMPTY_GAP
    for words in lines:
        top += c.text(M, top, words, _font(ui_rules.RECAP_EMPTY_LINE_PX), ui_rules.COLOR_TEXT_MUTED,
                      width=W - 2 * M) + ui_rules.RECAP_EMPTY_LINE_GAP


def _months(c: _Canvas, y: float, recap) -> float:
    """A year's twelve months as bars, as Stats' chart draws them -- a month not recorded faintly -- the
    busiest named under them. Returns the bottom."""
    y = _section(c, y, "Month by month")
    tallest = max((b.minutes for b in recap.months), default=0) or 1
    column = (W - 2 * M) / len(recap.months)
    bar_w, plot = ui_rules.RECAP_MONTH_BAR_WIDTH, ui_rules.RECAP_MONTH_PLOT
    foot = y + plot
    label_font = _font(ui_rules.RECAP_MONTH_LABEL_PX)
    for index, bar in enumerate(recap.months):
        x = M + index * column + (column - bar_w) / 2
        if not bar.recorded:
            colour, height = ui_rules.COLOR_CHART_UNRECORDED, ui_rules.RECAP_MONTH_STUB
        elif bar.minutes:
            colour = ui_rules.COLOR_CHART_BAR
            height = max(ui_rules.RECAP_MONTH_STUB, plot * bar.minutes / tallest)  # a real minute never vanishes
        else:
            colour, height = ui_rules.COLOR_SURFACE, ui_rules.RECAP_MONTH_STUB
        c.rounded(QRectF(x, foot - height, bar_w, height), ui_rules.STATS_BAR_RADIUS, colour)
        c.text(M + index * column, foot + ui_rules.RECAP_MONTH_LABEL_GAP, bar.label, label_font,
               ui_rules.COLOR_CHART_MONTH, width=column, align=Qt.AlignmentFlag.AlignHCenter)
    bottom = foot + ui_rules.RECAP_MONTH_LABEL_GAP + _metrics(label_font).height()
    if recap.busiest:
        bottom += ui_rules.RECAP_MONTH_CAPTION_GAP
        bottom += c.text(M, bottom, recap.busiest, _font(ui_rules.RECAP_FACT_DETAIL_PX), ui_rules.COLOR_TEXT_QUIET,
                         width=W - 2 * M)
    return bottom


def _footer(c: _Canvas, lines) -> float:
    """The footer's lines from the card's foot up, a hairline above them. Returns the hairline's top."""
    font = _font(ui_rules.RECAP_FOOTER_PX)
    line = _metrics(font).height() + ui_rules.RECAP_FOOTER_LINE_GAP
    y = H - M + ui_rules.RECAP_FOOTER_DROP - len(lines) * line
    rule = y - ui_rules.RECAP_FOOTER_RULE_GAP
    c.p.fillRect(QRectF(M, rule, W - 2 * M, ui_rules.RECAP_RULE_PX), QColor(ui_rules.COLOR_BORDER))
    for words in lines:
        y += c.text(M, y, words, font, ui_rules.COLOR_TEXT_FAINT, width=W - 2 * M) + ui_rules.RECAP_FOOTER_LINE_GAP
    return rule


class Painted(NamedTuple):
    image: QImage
    drawn: list  # every string drawn, for the no-personal-data check
    bottom: float  # where the content ends ...
    footer_top: float  # ... and where the footer's hairline is: the first must stay above the second


def paint(recap, art: Art) -> Painted:
    """The card, every string drawn on it, and where its content and its footer meet.

    A card whose content would reach its footer -- a month with every fact, a footer of three lines -- is
    painted again with its covers that much shorter: the covers give way, never the words."""
    first = _paint(recap, art)
    over = first.bottom - (first.footer_top - ui_rules.RECAP_FOOTER_CLEARANCE)
    return _paint(recap, art, squeeze=over) if over > 0 else first


def _paint(recap, art: Art, squeeze: float = 0) -> Painted:
    c = _Canvas()
    if recap.top:
        _glow(c, art.source(recap.top[0]))
    _header(c, recap)
    bottom = M + ui_rules.RECAP_HERO_TOP
    if recap.empty:
        _empty(c, bottom, recap)
    else:
        year = recap.period.is_year
        y = _hero(c, recap)
        if len(recap.top) == 1:
            y = _single(c, art, _section(c, y + ui_rules.RECAP_SECTION_TOP, "Played"), recap, squeeze)
        else:
            y = _columns(c, art, _section(c, y + ui_rules.RECAP_SECTION_TOP, "Most played"), recap.top, year,
                         squeeze)
        if recap.months:
            y = _months(c, y + ui_rules.RECAP_FACTS_TOP, recap)
        if recap.facts:
            y = _facts(c, y + ui_rules.RECAP_FACTS_TOP, recap.facts,
                       columns=max(1, len(recap.facts)) if year else 2)
        bottom = y
    footer_top = _footer(c, recap.footer) if recap.footer else H - M
    return Painted(c.done(), c.drawn, bottom, footer_top)


def render(recap, art: Art) -> QImage:
    began = time.perf_counter()
    image = paint(recap, art).image
    log.info("recap: %s painted in %.0f ms", recap.period.label, (time.perf_counter() - began) * 1000)
    return image


# -- the dialog ----------------------------------------------------------------------------------


class RecapDialog(QDialog):
    """The card previewed, a period to choose, and Copy image / Save image... / Close.

    The pad works it as every dialog (the window's _drive_dialog): up and down move between the rows,
    left and right move the chosen period along the chooser, A presses, B closes.
    """

    def __init__(self, source, art: Art, parent=None, now=None, fit_height: int | None = None,
                 scale: float = 1.0) -> None:
        super().__init__(parent)
        self.setObjectName("RecapDialog")
        self.setWindowTitle("Share as image")
        self.source, self.art, self.now = source, art, now
        self.recap = None
        self.image = QImage()
        self.saved_to = ""
        height = fit_height or round(ui_rules.RECAP_PREVIEW_HEIGHT * scale)
        self.preview_size = (round(height * W / H), height)

        layout = QVBoxLayout(self)
        margin = round(ui_rules.RECAP_DIALOG_MARGIN * scale)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(round(ui_rules.RECAP_DIALOG_SPACING * scale))
        chooser = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.periods = []
        for index, (words, period) in enumerate(recap_module.choices(now)):
            button = QPushButton(words)
            button.setObjectName("Chip")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # one stop, moved along by the arrows
            self.group.addButton(button, index)
            chooser.addWidget(button)
            self.periods.append(period)
        chooser.addStretch(1)
        layout.addLayout(chooser)

        self.preview = QLabel()
        self.preview.setObjectName("RecapPreview")
        self.preview.setFixedSize(*self.preview_size)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)

        self.status = QLabel("The image holds no folder paths, account names or e-mail addresses.")
        self.status.setObjectName("Meta")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy image")
        self.save_button = QPushButton("Save image...")
        self.close_button = QPushButton("Close")
        self.copy_button.clicked.connect(self.copy)
        self.save_button.clicked.connect(self.save)
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.save_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.group.idToggled.connect(lambda index, on: on and self.show_period(index))
        self.group.button(0).setChecked(True)
        self.group.button(0).setFocus(Qt.FocusReason.OtherFocusReason)

    @property
    def period(self):
        return self.periods[max(0, self.group.checkedId())]

    def show_period(self, index: int) -> None:
        self.recap = recap_module.build(self.source, self.periods[index], self.now)
        self.image = render(self.recap, self.art)
        ratio = self.devicePixelRatioF() or 1.0
        width, height = self.preview_size
        shown = QPixmap.fromImage(self.image).scaled(round(width * ratio), round(height * ratio),
                                                     Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation)
        shown.setDevicePixelRatio(ratio)
        self.preview.setPixmap(shown)

    def copy(self) -> None:
        """The image itself, at its full size, onto the clipboard -- a chat app pastes it whole."""
        QGuiApplication.clipboard().setImage(self.image)
        self.status.setText(f"Copied {self.period.label}'s card. Paste it into a chat or a post.")
        log.info("recap: %s copied to the clipboard", self.period.label)

    def default_path(self) -> str:
        folder = saves.known_folder(rules.RECAP_SAVE_FOLDER) or os.path.expanduser("~")
        return os.path.join(folder, self.period.file_name)

    def save(self) -> None:
        """One PNG, where the user chooses; nothing else is written."""
        path, _ = QFileDialog.getSaveFileName(self, "Save image", self.default_path(), "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if self.image.save(path, "PNG"):
            self.saved_to = path
            self.status.setText(f"Saved: {path}")
            log.info("recap: %s saved as a PNG", self.period.label)
        else:
            self.status.setText("The image could not be saved there. Try another folder.")
            log.warning("recap: could not save %s", path)
