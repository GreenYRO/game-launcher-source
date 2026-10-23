"""The Reports page (Phase 84): the reports of logic/reports.py, one card each (eight since Phase 89, nine since 98,
ten since 102, eleven since 103).

A card is the Stats page's: the report's number and title, its question in the quiet colour, the
sentence that answers it in the card's own words, then its parts -- a list of shares as bars
(ui_cards.ShareBars), a small table, a line of words -- and at its foot what the numbers cannot see
and the idea behind them, quiet again. The concentration card draws its Lorenz curve, painted here
like the month chart (no new dependency). A report with nothing to say yet keeps its card and says
so in words; a library that cannot answer (no database, or one older than version 5) gets one card
saying what to do.

**Worked out on the way in, like Stats**: the window builds the reports from the database every time
the tab is shown (39 ms on the user's library). The cards themselves are rebuilt only when an answer
changed -- a Report is a frozen dataclass, so equal answers compare equal -- since building some
hundred widgets again each visit would cost more than the queries.

Worked by the pad as Stats is: up and down scroll, left and right walk the tabs, B goes back.
"""

from __future__ import annotations

import html
import logging
import re

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from presentation import ui_icons
from presentation import ui_pageshell
from presentation import ui_rules
from presentation import ui_theme
from presentation.ui_cards import Card, ShareBars
from shared import paths

log = logging.getLogger(__name__)

INTRO = ("Eleven questions the library's database answers. The hours come from two sources \u2014 the "
         "launcher's own timing and Steam's counters on the accounts marked yours (Settings, Steam accounts) "
         "\u2014 and each card says which it reads. Spacewar and Source SDK Base 2007 are left out of every figure; the seventh card "
         "shows them.")
UNAVAILABLE = ("The reports read the library database at its newest version. This copy is still on an "
               "older one: start the launcher again and it upgrades the file (a backup is taken first).")
_NUMERIC = re.compile(r"^[-+]?[\d—]")


class LorenzCurve(QWidget):
    """The share of the hours held by the least played x of the games, against the diagonal."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.points: tuple = ()
        self.scale = 1.0
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip("The Lorenz curve: the share of all hours (up) held by the least played share "
                        "of the games (across). On the diagonal every game would have the same hours.")

    def set_points(self, points) -> None:
        self.points = tuple(points)
        self.update()

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        self.setFixedSize(round(ui_rules.REPORT_LORENZ_WIDTH * scale), round(ui_rules.REPORT_LORENZ_HEIGHT * scale))
        self.update()

    def _font(self) -> QFont:
        font = QFont(ui_icons.body_family())
        font.setPointSizeF(max(6.5, ui_theme.px_to_pt(ui_rules.REPORT_PART_PX * self.scale)))
        return font

    def plot_box(self) -> QRectF:
        line = QFontMetrics(self._font()).height()
        pad = max(4.0, 6 * self.scale)
        return QRectF(pad, pad, self.width() - 2 * pad, self.height() - 2 * pad - line)

    def paintEvent(self, event) -> None:
        if len(self.points) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = self.plot_box()
        at = lambda x, y: QPointF(box.left() + x * box.width(), box.bottom() - y * box.height())  # noqa: E731
        curve = QPainterPath(at(*self.points[0]))
        for x, y in self.points[1:]:
            curve.lineTo(at(x, y))
        area = QPainterPath(curve)
        area.lineTo(at(0.0, 0.0))
        painter.fillPath(area, QColor(ui_rules.COLOR_REPORT_LORENZ_FILL))
        diagonal = QPen(QColor(ui_rules.COLOR_REPORT_DIAGONAL), max(1.0, self.scale))
        diagonal.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(diagonal)
        painter.drawLine(at(0.0, 0.0), at(1.0, 1.0))
        painter.setPen(QPen(QColor(ui_rules.COLOR_REPORT_LORENZ), ui_rules.REPORT_LORENZ_LINE * self.scale))
        painter.drawPath(curve)
        painter.setFont(self._font())
        painter.setPen(QColor(ui_rules.COLOR_REPORT_AXIS_TEXT))
        words = QRectF(box.left(), box.bottom() + 2, box.width(), self.height() - box.bottom() - 2)
        painter.drawText(words, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), "least played")
        painter.drawText(words, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop), "most played")


def more_rows(more: int) -> str:
    """What a cut-short table says under its last row. reports.py lives beside the source only: an
    installed copy (a friend's, Phase 85) has no such command to point to."""
    if paths.FROZEN:
        return f"... and {more:,} more."
    return f"... and {more:,} more: reports.py --csv has them all."


def table_html(columns, rows, limit: int) -> str:
    """A part's table as rich text -- one label, not a widget per cell. Every cell is escaped:
    names come from the store and from folders, and are never read as markup."""
    shown = list(rows)[:limit]
    right = [i > 0 and all(_NUMERIC.match(str(row[i])) or not str(row[i]) for row in shown)
             for i in range(len(columns))]
    def cell(tag, text, i, colour):
        align = "right" if right[i] else "left"
        # Room between the columns, none before the first: it starts on the card's edge.
        left = 0 if i == 0 else ui_rules.REPORT_TABLE_CELL_PAD_X
        pad = f"{ui_rules.REPORT_TABLE_CELL_PAD_Y}px 0px {ui_rules.REPORT_TABLE_CELL_PAD_Y}px {left}px"
        return (f'<{tag} align="{align}" style="padding: {pad}; color: {colour}; font-weight: '
                f'{ui_rules.BODY_WEIGHT if tag == "td" else ui_rules.HEADING_WEIGHT};">{html.escape(str(text))}</{tag}>')

    head = "".join(cell("th", c, i, ui_rules.COLOR_REPORT_TABLE_HEAD) for i, c in enumerate(columns))
    body = "".join("<tr>" + "".join(cell("td", v, i, ui_rules.COLOR_REPORT_TABLE_TEXT) for i, v in enumerate(row))
                   + "</tr>" for row in shown)
    more = len(rows) - len(shown)
    tail = (f'<p style="color: {ui_rules.COLOR_TEXT_MUTED};">{html.escape(more_rows(more))}</p>'
            if more > 0 else "")
    return f'<table cellspacing="0" cellpadding="0"><tr>{head}</tr>{body}</table>{tail}'


def _label(text: str, name: str, rich: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return label


class ReportCard(Card):
    """One report: its title, question, answer, parts, and what it cannot see."""

    def __init__(self, report, scale: float, parent=None) -> None:
        super().__init__(f"{report.number}. {report.title}", parent, padding=ui_rules.REPORT_CARD_PADDING,
                         title_gap=ui_rules.REPORT_CARD_TITLE_GAP)
        self.report = report
        self.question = _label(report.question, "ReportQuestion")
        self.sentence = _label(report.sentence, "ReportSentence")
        self.body.addWidget(self.question)
        self.body.addWidget(self.sentence)
        self.curve = None
        self.bars: list[ShareBars] = []
        self.tables: list[QLabel] = []
        if report.curve and not report.empty:
            self.curve = LorenzCurve()
            self.curve.set_points(report.curve)
            self.curve.apply_scale(scale)
            self.body.addWidget(self.curve)
        for part in () if report.empty else report.parts:
            if not (part.bars or part.rows or part.note):
                continue  # a part kept for the CSV files alone
            self.body.addSpacing(max(4, round(ui_rules.REPORT_PART_GAP * scale)))
            self.body.addWidget(_label(part.heading.upper(), "ReportPart"))
            if part.bars:
                bars = ShareBars()
                bars.set_rows((bar.label, bar.fraction, bar.value) for bar in part.bars)
                bars.apply_scale(scale)
                self.bars.append(bars)
                self.body.addWidget(bars)
            if part.rows:
                table = _label(table_html(part.columns, part.rows, ui_rules.REPORT_TABLE_ROWS), "ReportTable", rich=True)
                # A table never wraps: measured once, where a wrapped rich-text label is measured
                # again at every width the layout tries (the first visit took half a second).
                table.setWordWrap(False)
                self.tables.append(table)
                self.body.addWidget(table)
            if part.note:
                self.body.addWidget(_label(part.note, "ReportNote"))
        self.body.addSpacing(max(4, round(ui_rules.REPORT_PART_GAP * scale)))
        if not report.empty:
            self.caveat = _label(f"<b>What it cannot see.</b> {html.escape(report.caveat)}", "ReportCaveat", rich=True)
            self.body.addWidget(self.caveat)
        self.concept = _label(f"<b>The idea.</b> {html.escape(report.concept)}", "ReportCaveat", rich=True)
        self.body.addWidget(self.concept)
        self.apply_scale(scale)


class ReportsPage(QWidget):
    """The page itself. B or Escape leaves, as from Stats."""

    backRequested = Signal()
    tabSelected = Signal(str)

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ReportsPage")
        self.metrics = metrics
        self.reports = None          # what the cards show: a list of Report, or None (cannot answer)
        self.shown_for = object()    # what the cards were last built from, and at what scale
        self.cards: list[Card] = []
        self.rebuilt = 0             # how many times the cards were built (a test reads it)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build()

    def _build(self) -> None:
        self.header_row = ui_pageshell.PageHeader(ui_pageshell.TAB_REPORTS, self)
        self.header_row.backRequested.connect(self.backRequested)
        self.header_row.tabSelected.connect(self.tabSelected)
        self.back_button = self.header_row.back_button

        body = QWidget()
        body.setObjectName("Clear")
        self.body_layout = QVBoxLayout(body)
        self.page_title = QLabel("Reports")
        self.page_title.setObjectName("PageTitle")
        self.page_title.setVisible(False)
        self.body_layout.addWidget(self.page_title)
        self.rail = False
        self.intro = _label(INTRO, "ReportIntro")
        self.body_layout.addWidget(self.intro)
        self.cards_layout = QVBoxLayout()
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.addLayout(self.cards_layout)
        self.body_layout.addStretch(1)

        self.content = body
        self.column = ui_pageshell.PageColumn(body, ui_rules.REPORTS_CONTENT_MAX_WIDTH)
        self.header_column = ui_pageshell.PageColumn(self.header_row, ui_rules.REPORTS_CONTENT_MAX_WIDTH)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("ReportsScroll")
        self.scroll.viewport().setObjectName("ReportsViewport")
        self.scroll.setWidget(self.column)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header_column)
        layout.addWidget(self.scroll, 1)
        self.apply_metrics(self.metrics)

    # -- filling it in ----------------------------------------------------------------------

    def set_reports(self, reports) -> None:
        """The reports (logic.reports.build), or None when the library cannot answer.
        Equal answers at the same scale leave the cards as they are."""
        self.reports = reports
        key = (tuple(reports) if reports is not None else None, round(self.metrics.scale, 3))
        if key == self.shown_for:
            return
        self.shown_for = key
        self._clear()
        scale = self.metrics.scale
        if reports is None:
            card = Card("The reports", padding=ui_rules.REPORT_CARD_PADDING, title_gap=ui_rules.REPORT_CARD_TITLE_GAP)
            card.body.addWidget(_label(UNAVAILABLE, "ReportSentence"))
            card.apply_scale(scale)
            self.cards = [card]
        else:
            self.cards = [ReportCard(report, scale) for report in reports]
        for card in self.cards:
            self.cards_layout.addWidget(card)
        self.rebuilt += 1

    def _clear(self) -> None:
        # setParent(None) first: deleteLater alone leaves the old cards painted under the new ones
        # until the event loop runs (the Stats page's Phase 23 lesson).
        for card in self.cards:
            self.cards_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self.cards = []

    def card(self, key: str):
        return next((c for c in self.cards if getattr(c, "report", None) is not None and c.report.key == key), None)

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        s = metrics.scale
        top = ui_rules.RAIL_PAGE_TOP if getattr(self, "rail", False) else ui_rules.PAGE_COLUMN_TOP
        self.layout().setContentsMargins(0, max(6, round(top * s)), 0, 0)
        self.layout().setSpacing(0)
        self.body_layout.setContentsMargins(0, 0, 0, max(10, round(ui_rules.STATS_PAGE_MARGIN * s)))
        self.body_layout.setSpacing(max(10, round(ui_rules.STATS_SECTION_SPACING * s)))
        self.cards_layout.setSpacing(max(10, round(ui_rules.STATS_SECTION_SPACING * s)))
        cap = round(ui_rules.REPORTS_CONTENT_MAX_WIDTH * s)
        self.content.setMaximumWidth(cap)
        self.header_row.setMaximumWidth(cap)
        for column in (self.column, self.header_column):
            column.set_scale(s)
        if self.reports is not None or self.cards:
            self.set_reports(self.reports)  # a new scale builds the cards at it

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
    return f"""
    QLabel#ReportIntro {{ font-size: {s(ui_rules.REPORT_NOTE_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#ReportQuestion {{ font-size: {s(ui_rules.REPORT_QUESTION_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#ReportSentence {{ font-size: {s(ui_rules.REPORT_SENTENCE_PX)}px; color: {ui_rules.COLOR_TEXT}; }}
    QLabel#ReportPart {{
        font-size: {s(ui_rules.REPORT_PART_PX)}px;
        letter-spacing: {ui_rules.REPORT_PART_TRACKING * ui_rules.REPORT_PART_PX * scale:.2f}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        color: {ui_rules.COLOR_TEXT_QUIET};
    }}
    QLabel#ReportTable {{ font-size: {pt(ui_rules.REPORT_TABLE_PX)}; color: {ui_rules.COLOR_REPORT_TABLE_TEXT}; }}
    QLabel#ReportNote {{ font-size: {s(ui_rules.REPORT_NOTE_PX)}px; color: {ui_rules.COLOR_TEXT_SOFT}; }}
    QLabel#ReportCaveat {{ font-size: {pt(ui_rules.REPORT_CAVEAT_PX)}; color: {ui_rules.COLOR_TEXT_QUIET}; }}
    """
