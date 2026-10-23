"""The stats page: four figures, a year of months, two lists, and what none of it can see.

Everything here is drawn from `stats.gather`. The chart is painted with QPainter rather
than pulled in from a plotting library -- twelve bars and a row of labels do not justify a
dependency, and the project has none it did not need.

**Designed for a nearly empty library first.** On the day this shipped the whole history
was one session of one minute, which is the state every new install starts in and the state
this page has to look deliberate in. Three things follow from that:

  * A month that was never recorded is drawn differently from a month that was quiet. The
    first is "we were not looking", the second is "you did not play", and a page that
    renders them identically is telling the user something false.
  * Every bar carries its value (the peak alone did until Phase 58, when the design wrote
    one over each), so a lone full-height bar reads as "one minute, which is the most in
    any month" rather than as a suspiciously full column.
  * A real but tiny bar never rounds away to nothing. One minute against a forty-hour peak
    is still drawn, because "I played and it vanished" is the worst possible answer.
"""

from __future__ import annotations

import html
import logging

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from shared import humanize
from logic import stats as stats_module
from presentation import ui_icons
from presentation import ui_pageshell
from presentation import ui_rules
from presentation import ui_theme
from presentation.ui_cards import Card

log = logging.getLogger(__name__)


def _span(seconds: int) -> str:
    """A duration as something a person reads.

    Not `humanize.playtime` directly: that answers "never played", which is right on a
    tile for one game and wrong as the value of "Played this week" -- a quiet week is not
    a game you have never played.
    """
    return humanize.playtime(seconds) if seconds > 0 else "none"


def _hours(minutes: int) -> str:
    """Minutes as something a person reads. Shared by the cards and the chart's peak."""
    return _span(minutes * 60)


class MonthChart(QWidget):
    """Twelve columns of minutes played, painted by hand -- the design's (Phase 58).

    A bar runs from the accent at its top to accent 700 at its foot, with its value written
    over it; a month nobody recorded is a short stub in the hairline colour; a month that
    was recorded and quiet, a thinner one in the accent's dark step. The months sit under a
    hairline.
    """

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.metrics = metrics
        self.months: list = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._resize()

    def set_months(self, months: list) -> None:
        self.months = list(months)
        self.setToolTip(self._tooltip())
        self.update()

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        self._resize()
        self.update()

    def peak_label(self) -> str:
        """The text drawn above the tallest bar, or "" when there is no bar."""
        peak = max((m.minutes for m in self.months), default=0)
        return _hours(peak) if peak else ""

    def _tooltip(self) -> str:
        return "\n".join(
            f"{m.label} {m.year}: "
            + ("not recorded" if not m.recorded else _hours(m.minutes) if m.minutes else "nothing")
            for m in self.months
        )

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(max(6.0, ui_theme.px_to_pt(ui_rules.STATS_AXIS_PX * self.metrics.scale)))
        return font

    def _label_height(self) -> int:
        return QFontMetrics(self._font()).height()

    def _plot_height(self) -> int:
        return max(60, round(ui_rules.STATS_CHART_HEIGHT * self.metrics.scale))

    def _s(self, value: float) -> int:
        return max(1, round(value * self.metrics.scale))

    def _resize(self) -> None:
        gap = self._s(ui_rules.STATS_AXIS_GAP)
        self.setFixedHeight(self._plot_height() + gap + 1 + gap + self._label_height())

    def column_box(self, index: int) -> QRectF:
        """Where month `index` stands: its column, the bars' full height."""
        count = max(1, len(self.months))
        gap = self._s(ui_rules.STATS_BAR_GAP)
        column = (self.width() - gap * (count - 1)) / count
        return QRectF(index * (column + gap), 0, column, self._plot_height())

    def paintEvent(self, event) -> None:
        if not self.months:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(self._font())

        radius = self._s(ui_rules.STATS_BAR_RADIUS)
        plot = self._plot_height()
        tallest = min(plot, self._s(ui_rules.STATS_BAR_MAX))
        min_px = self._s(ui_rules.STATS_MIN_BAR_PX)
        label_h = self._label_height()
        above = self._s(ui_rules.STATS_VALUE_ABOVE)
        peak = max((m.minutes for m in self.months), default=0)

        for index, month in enumerate(self.months):
            box = self.column_box(index)
            if not month.recorded:
                height, fill, rounded = self._s(ui_rules.STATS_UNRECORDED_PX), QColor(ui_rules.COLOR_CHART_UNRECORDED), True
            elif month.minutes > 0 and peak > 0:
                height = max(min_px, round(tallest * month.minutes / peak))
                fill = QLinearGradient(0, plot - height, 0, plot)
                fill.setColorAt(0.0, QColor(ui_rules.COLOR_CHART_BAR))
                fill.setColorAt(1.0, QColor(ui_rules.COLOR_CHART_BAR_FOOT))
                rounded = True
            else:
                height, fill, rounded = self._s(ui_rules.STATS_EMPTY_BAR_PX), QColor(ui_rules.COLOR_CHART_BASELINE), False
            bar = QRectF(box.left(), plot - height, box.width(), height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            if rounded:
                # Only the top corners are round: the bar stands on the hairline.
                painter.save()
                painter.setClipRect(bar)
                painter.drawRoundedRect(bar.adjusted(0, 0, 0, radius), radius, radius)
                painter.restore()
            else:
                painter.drawRect(bar)
            if month.recorded and month.minutes > 0:
                painter.setPen(QColor(ui_rules.COLOR_CHART_VALUE))
                painter.drawText(
                    QRectF(box.left() - box.width() / 2, plot - height - above - label_h,
                           box.width() * 2, label_h),
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
                    _hours(month.minutes),
                )

        gap = self._s(ui_rules.STATS_AXIS_GAP)
        painter.fillRect(QRectF(0, plot + gap, self.width(), 1), QColor(ui_rules.COLOR_CHART_AXIS))
        top = plot + gap + 1 + gap
        painter.setPen(QColor(ui_rules.COLOR_CHART_MONTH))
        for index, month in enumerate(self.months):
            box = self.column_box(index)
            painter.drawText(
                QRectF(box.left(), top, box.width(), label_h),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                month.label,
            )
        painter.end()


class StatCard(QFrame):
    """One big number with a caption under it, and a small icon over it (Phase 35).

    The design's since Phase 58: 18 x 20 inside, the icon 10 px over a 32 px value on a 1.1
    line, the caption 6 px under it. A label's box is its font's whole height, a little
    more than the design's line, so the gaps are measured from the line, not the box.
    """

    def __init__(self, label: str, metrics, glyph: str = "", parent=None) -> None:
        super().__init__(parent)
        self.metrics = metrics
        self.glyph = glyph
        self.setObjectName("StatCard")
        self.icon = QLabel()
        self.icon.setObjectName("StatIcon")
        self.value_label = QLabel("-")
        self.value_label.setObjectName("StatValue")
        self.caption = QLabel(label)
        self.caption.setObjectName("StatCaption")
        self.caption.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.addWidget(self.icon)
        self._above_value = QSpacerItem(0, 0)
        layout.addSpacerItem(self._above_value)
        layout.addWidget(self.value_label)
        self._under_value = QSpacerItem(0, 0)
        layout.addSpacerItem(self._under_value)
        layout.addWidget(self.caption)
        self.apply_metrics(metrics)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        s = metrics.scale
        side = max(8, round(ui_rules.STATS_CARD_PADDING_X * s))
        ends = max(8, round(ui_rules.STATS_CARD_PADDING_Y * s))
        self.layout().setContentsMargins(side, ends, side, ends)
        # The value's font, as the stylesheet sets it, measured here rather than off the
        # label: the label gets its font only once the window's stylesheet exists.
        size = max(16, round(ui_rules.STATS_VALUE_PX * s))
        font = QFont(ui_icons.display_family())
        font.setPixelSize(size)
        font.setWeight(QFont.Weight(ui_rules.HEADING_WEIGHT))
        box = QFontMetrics(font).height()
        overhang = max(0, round((box - size * ui_rules.STATS_VALUE_LINE) / 2))
        self._above_value.changeSize(0, max(0, round(ui_rules.STATS_ICON_GAP * s) - overhang))
        self._under_value.changeSize(0, max(0, round(ui_rules.STATS_CAPTION_GAP * s) - overhang))
        self.layout().invalidate()
        self.setMinimumWidth(max(90, round(ui_rules.STATS_CARD_MIN_WIDTH * s)))
        px = max(10, round(ui_rules.STATS_ICON_PX * s))
        if self.glyph:
            self.icon.setPixmap(ui_icons.glyph_pixmap(self.glyph, ui_rules.COLOR_ACCENT, px,
                                                      self.devicePixelRatioF() or 1.0))
        self.icon.setVisible(bool(self.glyph))


class Swatch(QWidget):
    """A small square of one of the chart's colours, for the legend under the caveats."""

    def __init__(self, colour: str, parent=None) -> None:
        super().__init__(parent)
        self.colour = colour
        self.apply_scale(1.0)

    def apply_scale(self, scale: float) -> None:
        size = max(6, round(ui_rules.STATS_SWATCH_PX * scale))
        self.radius = max(1, round(ui_rules.STATS_SWATCH_RADIUS * scale))
        self.setFixedSize(size, size)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colour))
        painter.drawRoundedRect(QRectF(self.rect()), self.radius, self.radius)


def rounded(pixmap: QPixmap, width: int, height: int, radius: float, ratio: float) -> QPixmap:
    """A cover cut to a small card with round corners, at the screen's density."""
    result = QPixmap(max(1, round(width * ratio)), max(1, round(height * ratio)))
    result.setDevicePixelRatio(ratio)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(path)
    if pixmap is not None and not pixmap.isNull():
        painter.drawPixmap(QRectF(0, 0, width, height), pixmap, QRectF(pixmap.rect()))
    else:
        painter.fillRect(QRectF(0, 0, width, height), QColor(ui_rules.COLOR_SURFACE_RAISED))
    painter.end()
    return result


class StatsPage(QWidget):
    """The page itself. B or Escape leaves, exactly like the detail page."""

    backRequested = Signal()
    tabSelected = Signal(str)
    shareRequested = Signal()  # the Recap card's button, or A on the pad (Phase 96)

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatsPage")
        self.metrics = metrics
        self.stats: stats_module.Stats | None = None
        # Set by the window, for the most-played games' covers (Phase 58). Without them a
        # row shows a plain small card where its cover would be.
        self.covers = None
        self.views: list = []
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build()

    # -- construction -----------------------------------------------------------------------

    def _build(self) -> None:
        # The header sits in the same capped column as the content. Left-aligned against a
        # centred body, it read as belonging to a different page.
        self.header_row = ui_pageshell.PageHeader(ui_pageshell.TAB_STATS, self)
        self.header_row.backRequested.connect(self.backRequested)
        self.header_row.tabSelected.connect(self.tabSelected)
        self.back_button = self.header_row.back_button

        # The recap (Phase 96): this month so far in one line -- the same card the dialog draws -- and
        # the way to it. At the top, as the design's page leads with what is newest.
        list_padding = (ui_rules.STATS_LIST_PADDING_X, ui_rules.STATS_LIST_PADDING_Y)
        self.recap_card = Card("Recap", padding=list_padding, title_gap=ui_rules.STATS_LIST_TITLE_GAP)
        self.recap_line = QLabel()
        self.recap_line.setObjectName("StatName")
        self.recap_line.setWordWrap(True)
        self.share_button = QPushButton("Share as image...")
        self.share_button.setObjectName("RecapShare")
        self.share_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.share_button.clicked.connect(self.shareRequested)
        recap_row = QHBoxLayout()
        recap_row.setContentsMargins(0, 0, 0, 0)
        recap_row.addWidget(self.recap_line, 1)
        recap_row.addWidget(self.share_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.recap_card.body.addLayout(recap_row)

        self.cards = {
            "week": StatCard("Played this week", self.metrics, "clock"),
            "month": StatCard("Played this month", self.metrics, "calendar"),
            "lifetime": StatCard("Timed here, all time", self.metrics, "history"),
            "library": StatCard("Games in your library", self.metrics, "controller"),
        }
        self.card_row = QHBoxLayout()
        for card in self.cards.values():
            self.card_row.addWidget(card, 1)

        # Each block is one of the game page's cards (Phase 35), so the three pages that
        # show information about games read as one design. The paddings are the design's.
        self.chart_card = Card(
            "The last 12 months",
            padding=(ui_rules.STATS_CHART_PADDING_X, ui_rules.STATS_CHART_PADDING_TOP,
                     ui_rules.STATS_CHART_PADDING_BOTTOM),
            title_gap=ui_rules.STATS_CHART_TITLE_GAP)
        self.chart_label = self.chart_card.title
        # Which twelve months, on the title's line where the design has its meta.
        self.chart_span = QLabel()
        self.chart_span.setObjectName("ChartSpan")
        self.chart_card.add_to_header(self.chart_span)
        self.chart = MonthChart(self.metrics, self)
        self.chart_card.body.addWidget(self.chart)

        self.played_card = Card("Most played", padding=list_padding,
                                title_gap=ui_rules.STATS_LIST_TITLE_GAP)
        self.played_label = self.played_card.title
        self.played_grid = QGridLayout()
        self.played_grid.setColumnStretch(1, 1)
        self.played_empty = QLabel()
        self.played_empty.setObjectName("Meta")
        self.played_empty.setWordWrap(True)
        self.played_card.body.addLayout(self.played_grid)
        self.played_card.body.addWidget(self.played_empty)
        self.played_card.body.addStretch(1)

        self.library_card = Card("Where they came from", padding=list_padding,
                                 title_gap=ui_rules.STATS_LIST_TITLE_GAP)
        self.library_label = self.library_card.title
        self.library_grid = QGridLayout()
        # A short label and a one-digit count, so the empty third column takes the slack.
        # Stretching the count to the column's right edge instead strands it half a screen
        # from the thing it counts.
        self.library_grid.setColumnStretch(2, 1)
        self.library_total = QLabel()
        self.library_total.setObjectName("Meta")
        self.library_card.body.addLayout(self.library_grid)
        self.library_card.body.addWidget(self.library_total)
        self.library_card.body.addStretch(1)

        # Side by side and equal, as the design has its two lists.
        columns = QHBoxLayout()
        self._columns = columns
        columns.addWidget(self.played_card, 1)
        columns.addWidget(self.library_card, 1)

        self.caveat_card = Card("What these numbers cannot see", padding=list_padding,
                                title_gap=ui_rules.STATS_CAVEAT_GAP)
        self.caveat_label = self.caveat_card.title
        self.caveats = QLabel()
        self.caveats.setObjectName("Caveats")
        self.caveats.setWordWrap(True)
        self.caveats.setTextFormat(Qt.TextFormat.RichText)
        self.caveat_card.body.addWidget(self.caveats)
        # What the chart's two colours mean, which the design writes here rather than under
        # the chart: the sentence about the dimmed months, and a legend of the two.
        self.chart_caption = QLabel()
        self.chart_caption.setObjectName("Caveats")
        self.chart_caption.setWordWrap(True)
        self.chart_caption.setTextFormat(Qt.TextFormat.RichText)
        self.caveat_card.body.addWidget(self.chart_caption)
        self.legend = QHBoxLayout()
        self.legend.setContentsMargins(0, 0, 0, 0)
        self.swatches = []
        for colour, words in ((ui_rules.COLOR_CHART_BAR, "Recorded"),
                              (ui_rules.COLOR_CHART_UNRECORDED, "Not recorded yet")):
            swatch = Swatch(colour)
            label = QLabel(words)
            label.setObjectName("Legend")
            item = QHBoxLayout()
            item.setContentsMargins(0, 0, 0, 0)
            item.addWidget(swatch)
            item.addWidget(label)
            self.legend.addLayout(item)
            self.swatches.append((item, swatch))
        self.legend.addStretch(1)
        self.caveat_card.body.addLayout(self.legend)

        body = QWidget()
        body.setObjectName("Clear")
        self.body_layout = QVBoxLayout(body)
        # Beside the side rail (Phase 60) the page carries its own name, as the library does.
        self.page_title = QLabel("Stats")
        self.page_title.setObjectName("PageTitle")
        self.page_title.setVisible(False)
        self.body_layout.addWidget(self.page_title)
        self.rail = False
        self.body_layout.addWidget(self.recap_card)
        self.body_layout.addLayout(self.card_row)
        self.body_layout.addWidget(self.chart_card)
        self.body_layout.addLayout(columns)
        self.body_layout.addWidget(self.caveat_card)
        self.body_layout.addStretch(1)

        # One column, placed as the design places it: see ui_pageshell.PageColumn.
        self.content = body
        self.column = ui_pageshell.PageColumn(body, ui_rules.STATS_CONTENT_MAX_WIDTH)
        self.header_column = ui_pageshell.PageColumn(self.header_row, ui_rules.STATS_CONTENT_MAX_WIDTH)

        # See-through, so the library's glow carries on behind the page (Phase 35).
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("StatsScroll")
        self.scroll.viewport().setObjectName("StatsViewport")
        self.scroll.setWidget(self.column)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header_column)
        layout.addWidget(self.scroll, 1)
        self.apply_metrics(self.metrics)

    # -- filling it in ----------------------------------------------------------------------

    def set_stats(self, value: stats_module.Stats) -> None:
        self.stats = value
        self.cards["week"].set_value(_hours(value.minutes_this_week))
        self.cards["month"].set_value(_hours(value.minutes_this_month))
        self.cards["lifetime"].set_value(_span(value.lifetime_seconds))
        self.cards["library"].set_value(str(value.total_games))

        self.chart.set_months(value.months)
        self.chart_span.setText(self._chart_span(value))
        self.chart_caption.setText(self._spaced([self._chart_caption(value)]))
        self.chart_caption.setVisible(bool(self._chart_caption(value)))

        self._fill_played(value)
        self._fill_sources(value)
        self.caveats.setText(self._spaced(stats_module.caveats(value)))

    def set_recap(self, line: str) -> None:
        """The Recap card's line: logic/recap.py's summary of this month's card."""
        self.recap_line.setText(line)

    def _spaced(self, lines: list[str]) -> str:
        """Plain sentences as rich text on the design's 1.6 line, escaped, one per paragraph.

        A QLabel ignores a stylesheet's line-height; only rich text carries one (Phase 57).
        """
        line = ui_rules.STATS_CAVEAT_PX * ui_rules.STATS_CAVEAT_LINE * self.metrics.scale
        return "".join(f'<div style="line-height: {line:.1f}px">{html.escape(text)}</div>'
                       for text in lines if text)

    @staticmethod
    def _chart_span(value: stats_module.Stats) -> str:
        if not value.months:
            return ""
        first, last = value.months[0], value.months[-1]
        return f"{first.label} {first.year} to {last.label} {last.year}"

    @staticmethod
    def _chart_caption(value: stats_module.Stats) -> str:
        if not value.months:
            return ""
        if value.recording_since is None:
            return "Nothing has been recorded yet."
        greyed = sum(1 for m in value.months if not m.recorded)
        if greyed:
            return (
                f"The {greyed} greyed months are before this launcher began keeping "
                "session history, not months you did not play."
            )
        return ""

    def _clear(self, grid: QGridLayout) -> None:
        """Empty a grid, and have it *look* empty before this function returns.

        `deleteLater` alone does not: the widget survives until the event loop next runs,
        so the old rows carry on painting underneath the new ones. Reopening the page after
        playing anything showed both sets of names on top of each other. `setParent(None)`
        takes them off the screen now; deleteLater still frees them.
        """
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _row(
        self, grid: QGridLayout, row: int, cells: list[tuple[str, str]], align_last=True
    ) -> None:
        for column, (text, name) in enumerate(cells):
            label = QLabel(text)
            label.setObjectName(name)
            if align_last and column == len(cells) - 1:
                label.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            grid.addWidget(label, row, column)

    def _thumb(self, entry) -> QLabel:
        """The game's cover, 18 x 27 with round corners, as the design lists them (Phase 58).

        The tally knows a game by its name and time only, so the view is found by those --
        two installs of one title share a cover anyway.
        """
        s = self.metrics.scale
        width = max(8, round(ui_rules.STATS_THUMB_WIDTH * s))
        height = max(12, round(ui_rules.STATS_THUMB_HEIGHT * s))
        same_name = [v for v in self.views if v.display_name == entry.label]
        view = next((v for v in same_name if v.playtime_seconds == entry.value), None) or (
            same_name[0] if same_name else None)
        art = None
        if self.covers is not None and view is not None:
            art = self.covers.cover(view, width, height, with_name=False)
        ratio = self.devicePixelRatioF() or 1.0
        thumb = QLabel()
        thumb.setObjectName("Thumb")
        thumb.setFixedSize(width, height)
        thumb.setPixmap(rounded(art, width, height, ui_rules.STATS_THUMB_RADIUS * s, ratio))
        return thumb

    def _fill_played(self, value: stats_module.Stats) -> None:
        self._clear(self.played_grid)
        row_h = max(16, round(ui_rules.STATS_LIST_ROW_PX * self.metrics.scale))
        for index, entry in enumerate(value.top_games):
            # The cover, the name and the time -- the design's row, with neither the rank
            # number nor the bar this list carried before (Phase 35).
            self.played_grid.addWidget(self._thumb(entry), index, 0)
            name = QLabel(entry.label)
            name.setObjectName("StatName")
            name.setFixedHeight(row_h)
            self.played_grid.addWidget(name, index, 1)
            time = QLabel(humanize.playtime(entry.value))
            time.setObjectName("StatTime")
            time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.played_grid.addWidget(time, index, 2)
        # The empty state is the normal state on a new install, so it is a sentence rather
        # than a blank space where a list ought to be.
        self.played_empty.setText(
            ""
            if value.top_games
            else "Nothing has been timed yet. Start a game from here and it appears in this list."
        )
        self.played_empty.setVisible(not value.top_games)

    def _fill_sources(self, value: stats_module.Stats) -> None:
        self._clear(self.library_grid)
        row_h = max(16, round(ui_rules.STATS_LIST_ROW_PX * self.metrics.scale))
        for index, entry in enumerate(value.sources):
            self._row(
                self.library_grid,
                index,
                [(entry.label, "StatName"), (str(entry.value), "StatTime")],
                align_last=False,
            )
            for column in (0, 1):
                self.library_grid.itemAtPosition(index, column).widget().setFixedHeight(row_h)
        self.library_total.setText(
            f"{humanize.size(value.total_bytes)} on disk"
            if value.total_bytes
            else "No install sizes recorded"
        )

    # -- chrome -----------------------------------------------------------------------------

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        s = metrics.scale
        top = ui_rules.RAIL_PAGE_TOP if getattr(self, "rail", False) else ui_rules.PAGE_COLUMN_TOP
        self.layout().setContentsMargins(0, max(6, round(top * s)), 0, 0)
        self.layout().setSpacing(0)
        self.body_layout.setContentsMargins(0, 0, 0, max(10, round(ui_rules.STATS_PAGE_MARGIN * s)))
        self.body_layout.setSpacing(max(10, round(ui_rules.STATS_SECTION_SPACING * s)))
        self.card_row.setSpacing(max(6, round(ui_rules.STATS_CARD_SPACING * s)))
        gap = max(6, round(ui_rules.STATS_LIST_GAP * s))
        for grid in (self.played_grid, self.library_grid):
            grid.setHorizontalSpacing(gap)
            grid.setVerticalSpacing(max(2, round(ui_rules.STATS_LIST_ROW_GAP * s)))
        cap = round(ui_rules.STATS_CONTENT_MAX_WIDTH * s)
        self.content.setMaximumWidth(cap)
        self.header_row.setMaximumWidth(cap)
        for column in (self.column, self.header_column):
            column.set_scale(s)
        for card in self.cards.values():
            card.apply_metrics(metrics)
        for card in (self.recap_card, self.chart_card, self.played_card, self.library_card, self.caveat_card):
            card.apply_scale(s)
        self._columns.setSpacing(max(6, round(ui_rules.STATS_COLUMN_GAP * s)))
        self.legend.setSpacing(max(6, round(ui_rules.STATS_LEGEND_GAP * s)))
        for item, swatch in self.swatches:
            item.setSpacing(max(3, round(ui_rules.STATS_SWATCH_GAP * s)))
            swatch.apply_scale(s)
        self.legend.setContentsMargins(0, max(2, round(ui_rules.STATS_LEGEND_TOP * s)), 0, 0)
        self.chart.apply_metrics(metrics)
        if self.stats is not None:
            self.set_stats(self.stats)

    def set_rail(self, rail: bool) -> None:
        """Beside the side rail or under the top bar (Phase 60): the column's place, the top."""
        self.rail = rail
        self.page_title.setVisible(rail)
        for column in (self.column, self.header_column):
            column.set_rail(rail)
        self.apply_metrics(self.metrics)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.backRequested.emit()
            return
        super().keyPressEvent(event)


def stylesheet(scale: float) -> str:
    """Appended to the app stylesheet; only affects this page."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    pt = lambda px: f"{ui_theme.px_to_pt(px * scale):.2f}pt"  # noqa: E731 -- fractional px
    radius = max(6, round(ui_rules.DETAIL_CARD_RADIUS * scale))
    display = ui_icons.display_family()
    return f"""
    QFrame#StatCard {{
        background: {ui_rules.COLOR_CARD};
        border: 1px solid {ui_rules.COLOR_CARD_BORDER};
        border-radius: {radius}px;
    }}
    /* The blanket QWidget rule gives every label the page background, which is invisible
       on the page and a dark bar once a label sits on a lighter card. Same class of trap
       as QMenu::item:disabled: the blanket rule wins unless something says otherwise. */
    QFrame#StatCard QLabel {{ background: transparent; border: none; }}
    QLabel#StatValue {{
        font-family: "{display}";
        font-size: {s(ui_rules.STATS_VALUE_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        letter-spacing: {ui_rules.STATS_VALUE_TRACKING * ui_rules.STATS_VALUE_PX * scale:.2f}px;
        color: {ui_rules.COLOR_TEXT};
    }}
    QLabel#StatCaption {{
        font-size: {pt(ui_rules.STATS_CAPTION_PX)};
        color: {ui_rules.COLOR_STATS_CAPTION};
    }}
    QLabel#StatName {{ font-size: {s(ui_rules.STATS_LIST_TEXT_PX)}px; color: {ui_rules.COLOR_TEXT}; }}
    QLabel#StatTime {{ font-size: {s(ui_rules.STATS_LIST_TEXT_PX)}px; color: {ui_rules.COLOR_TEXT_SOFT}; }}
    QLabel#ChartSpan {{ font-size: {s(ui_rules.GAME_WEEK_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#Caveats {{ font-size: {s(ui_rules.STATS_CAVEAT_PX)}px; color: {ui_rules.COLOR_TEXT_SOFT}; }}
    QLabel#Legend {{ font-size: {s(ui_rules.STATS_LEGEND_PX)}px; color: {ui_rules.COLOR_TEXT_QUIET}; }}
    QLabel#Thumb {{ background: transparent; }}
    """
