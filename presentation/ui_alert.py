"""Alert me under... (Phase 101): a wished game's target price, in the currency its price is in.

Reached from a wished game's menu on the Wishlist page (X on the pad, or a right click). One amount, prefilled
with the lowest price the series has seen (or the target already set), in the game's own currency as its row
shows it -- never converted, so a target always compares with a price in its own money. The window's pad
routing works it as it works What I paid: up and down between the amount and the buttons, left and right
change the amount, A presses, B closes. No button answers Return on its own: A on the amount must not set it
by accident. One target per game, kept in the library database (price_target); nothing in config.json.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from presentation import ui_rules
from shared import humanize
from shared import rules

TITLE = "Alert me under..."


class TargetDialog(QDialog):
    """The amount for one wished game; `cents()` after it was accepted."""

    def __init__(self, parent, name: str, currency: str, start_cents: int, today: str = "",
                 lowest: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("PriceTarget")
        self.setWindowTitle(TITLE)
        self.setMinimumWidth(ui_rules.ALERT_DIALOG_WIDTH)
        self.currency = currency
        layout = QVBoxLayout(self)
        heading = QLabel(name, self)
        heading.setObjectName("DialogTitle")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        facts = " · ".join(part for part in (f"Today {today}" if today else "", lowest) if part)
        if facts:
            line = QLabel(facts, self)
            line.setObjectName("Meta")
            line.setWordWrap(True)
            layout.addWidget(line)
        ask = QLabel("Tell me when it costs this or less:", self)
        ask.setWordWrap(True)
        layout.addWidget(ask)
        row = QHBoxLayout()
        self.amount = QDoubleSpinBox(self)
        self.amount.setLocale(QLocale(QLocale.Language.Romanian, QLocale.Country.Romania))  # "20,00", as the rows
        self.amount.setDecimals(2)
        self.amount.setRange(rules.ALERT_TARGET_MIN_CENTS / 100, rules.ALERT_TARGET_MAX_CENTS / 100)
        self.amount.setSingleStep(rules.ALERT_TARGET_STEP_CENTS / 100)
        self.amount.setValue(max(rules.ALERT_TARGET_MIN_CENTS, min(start_cents, rules.ALERT_TARGET_MAX_CENTS)) / 100)
        self.amount.setAccessibleName("Target price")
        row.addWidget(self.amount, 1)
        unit = QLabel(currency, self)
        unit.setObjectName("Meta")
        row.addWidget(unit)
        layout.addLayout(row)
        note = QLabel("A message comes once for each drop to or under it \u2014 in the window, or by the "
                      "clock when the launcher is in the tray.", self)
        note.setObjectName("Meta")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        self.set_button = QPushButton("Set alert", self)
        self.set_button.clicked.connect(self.accept)
        for button in (self.cancel_button, self.set_button):
            button.setAutoDefault(False)
            button.setDefault(False)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.amount.setFocus()

    def cents(self) -> int:
        """The amount chosen, in cents (the spin box keeps two decimals: rounding, never truncating)."""
        return int(round(self.amount.value() * 100))

    def words(self) -> str:
        return humanize.money(self.cents(), self.currency)
