"""What I paid (Phase 74): a game's purchases, typed by hand -- shown, added, removed.

Reached from the "..." menu of any game (and the right-click menu, which is the same menu),
so the pad reaches it too; the window's pad routing works the dialog as it works Settings:
up and down move between its controls (or through the list), left and right change an
amount, a currency or a date in place, A presses or ticks, B closes.

Only this game's purchases are touched -- never another field of its record. A game with no
purchase is unknown, not free, and the dialog says so. Removing one asks first, with Cancel
the default, escape and focused button (the Phase 25 rule).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from PySide6.QtCore import QDate, QLocale, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QVBoxLayout)

from shared import humanize
from shared import rules

log = logging.getLogger(__name__)

# The store a game's own source suggests, so the box starts on the likely answer.
SOURCE_STORES = {"steam": "Steam", "gog": "GOG", "epic": "Epic", "xbox": "Xbox or Game Pass"}
AMOUNT_MAX = 9999.99


def describe(purchase: dict) -> str:
    """One purchase as the list shows it: "12,50 €  ·  key reseller  ·  3 May 2026  ·  note"."""
    parts = [humanize.money(purchase["paid_cents"], purchase["currency"]), purchase["store"]]
    parts.append(humanize.day(date.fromisoformat(purchase["bought_on"]), year=True)
                 if purchase.get("bought_on") else "date unknown")
    if purchase.get("note"):
        parts.append(purchase["note"])
    return "  ·  ".join(parts)


class PurchaseDialog(QDialog):
    """The purchases of one game, and a small form to add one."""

    def __init__(self, window, view) -> None:
        super().__init__(window)
        self.window_ = window
        self.view = view
        self.store_ = window.overrides
        self.changed = False
        self.setObjectName("Purchases")
        self.setWindowTitle(f"What I paid -- {view.display_name}")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        self.list = QListWidget(self)
        self.list.setObjectName("PurchaseList")
        self.empty = QLabel("Nothing recorded yet. A game with no purchase is unknown, not free.", self)
        self.empty.setWordWrap(True)
        layout.addWidget(self.list)
        layout.addWidget(self.empty)

        form_box = QGroupBox("Add a purchase", self)
        form = QFormLayout(form_box)
        self.amount = QDoubleSpinBox(form_box)
        self.amount.setLocale(QLocale(QLocale.Language.Romanian, QLocale.Country.Romania))  # "12,50"
        self.amount.setDecimals(2)
        self.amount.setRange(0.0, AMOUNT_MAX)
        self.amount.setSingleStep(1.0)
        self.currency = QComboBox(form_box)
        self.currency.addItems(rules.PURCHASE_CURRENCIES)  # EUR first, and chosen
        amount_row = QHBoxLayout()
        amount_row.addWidget(self.amount, 1)
        amount_row.addWidget(self.currency)
        form.addRow("Amount", amount_row)
        self.shop = QComboBox(form_box)
        self.shop.setEditable(True)
        self.shop.addItems(rules.PURCHASE_STORES)
        self.shop.setCurrentText(SOURCE_STORES.get(view.entry.source, rules.PURCHASE_STORES[0]))
        form.addRow("Store", self.shop)
        self.bought_on = QDateEdit(QDate.currentDate(), form_box)
        self.bought_on.setCalendarPopup(True)
        self.bought_on.setDisplayFormat("d MMM yyyy")
        self.unknown_date = QCheckBox("Date unknown", form_box)
        self.unknown_date.toggled.connect(lambda on: self.bought_on.setEnabled(not on))
        date_row = QHBoxLayout()
        date_row.addWidget(self.bought_on, 1)
        date_row.addWidget(self.unknown_date)
        form.addRow("Bought on", date_row)
        self.note = QLineEdit(form_box)
        self.note.setPlaceholderText("A bundle, a sale, a gift from... (optional)")
        form.addRow("Note", self.note)
        self.add_button = QPushButton("Add", form_box)
        self.add_button.clicked.connect(self.add)
        form.addRow("", self.add_button)
        layout.addWidget(form_box)

        buttons = QHBoxLayout()
        self.remove_button = QPushButton("Remove selected...", self)
        self.remove_button.clicked.connect(self.remove)
        self.close_button = QPushButton("Close", self)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        # No button answers Return on its own: A on a box must not close the dialog or add half
        # a purchase. Each button acts when it is pressed, by the mouse, Space or the pad's A.
        for button in (self.add_button, self.remove_button, self.close_button):
            button.setAutoDefault(False)
            button.setDefault(False)
        self.list.currentRowChanged.connect(lambda _row: self._enable())
        self.refresh()
        self.amount.setFocus()

    # -- what is there ---------------------------------------------------------------------------

    def refresh(self) -> None:
        self.rows = self.store_.purchases(self.view.key)
        self.list.clear()
        for purchase in self.rows:
            item = QListWidgetItem(describe(purchase))
            item.setData(Qt.ItemDataRole.UserRole, purchase["id"])
            self.list.addItem(item)
        self.list.setVisible(bool(self.rows))
        self.empty.setVisible(not self.rows)
        if self.rows:
            self.list.setCurrentRow(0)
        self._enable()

    def _enable(self) -> None:
        self.remove_button.setEnabled(self.list.currentItem() is not None)

    # -- changing it -----------------------------------------------------------------------------

    def add(self) -> bool:
        store_name = self.shop.currentText().strip()
        if not store_name:
            QMessageBox.information(self, "Which store?", "Say where it was bought -- or pick \"other\".")
            return False
        bought_on = None if self.unknown_date.isChecked() else self.bought_on.date().toPython().isoformat()
        new_id = self.store_.add_purchase(
            self.view.key, paid_cents=round(self.amount.value() * 100), currency=self.currency.currentText(),
            store=store_name, bought_on=bought_on, note=self.note.text().strip() or None,
            recorded_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        if new_id is None:
            QMessageBox.warning(self, "Not saved", "That purchase could not be saved. The log says why.")
            return False
        log.info("purchase %s recorded for %s", new_id, self.view.key)
        self.changed = True
        self.note.clear()
        self.refresh()
        return True

    def remove(self) -> bool:
        item = self.list.currentItem()
        if item is None:
            return False
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Remove this purchase?")
        box.setText(item.text())
        box.setInformativeText("It is taken out of what you paid for this game. Nothing else changes.")
        go = box.addButton("Remove", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        # All three, as the uninstall question has them: Return, Escape, and the pad's A the
        # moment the box opens all mean Cancel.
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        cancel.setFocus()
        box.exec()
        if box.clickedButton() is not go:
            return False
        if not self.store_.remove_purchase(item.data(Qt.ItemDataRole.UserRole)):
            QMessageBox.warning(self, "Not removed", "That purchase could not be removed. The log says why.")
            return False
        log.info("purchase removed for %s: %s", self.view.key, item.text())
        self.changed = True
        self.refresh()
        return True


def purchases_flow(window, view) -> None:
    """Open the dialog for a game; refresh the page if anything changed."""
    dialog = PurchaseDialog(window, view)
    dialog.exec()
    if dialog.changed:
        window.reload_views()
