from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import gspread
from gspread.exceptions import WorksheetNotFound

from gastos_bot.config import DEFAULT_CATEGORIES
from gastos_bot.models import Currency, CurrencyBreakdown, ExpenseRecord, ExpenseSummary

EXPENSES_HEADERS = [
    "id",
    "fecha",
    "hora",
    "descripcion",
    "categoria",
    "monto",
    "moneda",
    "medio_pago",
    "mensaje_original",
]

CATEGORIES_HEADERS = ["nombre"]


def expense_to_row(expense: ExpenseRecord) -> list[Any]:
    return [
        expense.id,
        expense.fecha.isoformat(),
        expense.hora,
        expense.descripcion,
        expense.categoria,
        round(expense.monto, 2),
        expense.moneda,
        expense.medio_pago,
        expense.mensaje_original,
    ]


def row_to_expense(row: list[Any]) -> ExpenseRecord | None:
    if len(row) < 6:
        return None
    padded = list(row) + [""] * max(0, len(EXPENSES_HEADERS) - len(row))
    raw_id = str(padded[0]).strip()
    raw_date = str(padded[1]).strip()
    raw_amount = str(padded[5]).strip().replace(",", ".")
    if not raw_id or not raw_date or not raw_amount:
        return None

    try:
        parsed_date = date.fromisoformat(raw_date)
        amount = float(raw_amount)
    except ValueError:
        return None

    raw_currency = str(padded[6]).strip().upper()
    currency: Currency = "USD" if raw_currency == "USD" else "ARS"

    return ExpenseRecord(
        id=raw_id,
        fecha=parsed_date,
        hora=str(padded[2]).strip(),
        descripcion=str(padded[3]).strip(),
        categoria=str(padded[4]).strip(),
        monto=amount,
        moneda=currency,
        medio_pago=str(padded[7]).strip(),
        mensaje_original=str(padded[8]).strip(),
    )


def build_summary(expenses: list[ExpenseRecord]) -> ExpenseSummary:
    """Agrupa gastos por moneda y categoría, ordenando categorías de mayor a menor."""
    totals: dict[Currency, float] = defaultdict(float)
    counts: dict[Currency, int] = defaultdict(int)
    per_category: dict[Currency, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for expense in expenses:
        totals[expense.moneda] += expense.monto
        counts[expense.moneda] += 1
        per_category[expense.moneda][expense.categoria] += expense.monto

    by_currency: dict[Currency, CurrencyBreakdown] = {}
    for currency in ("ARS", "USD"):
        if counts[currency] > 0:
            sorted_cats = dict(
                sorted(
                    ((k, round(v, 2)) for k, v in per_category[currency].items()),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )
            by_currency[currency] = CurrencyBreakdown(
                total=round(totals[currency], 2),
                count=counts[currency],
                by_category=sorted_cats,
            )

    return ExpenseSummary(total_count=len(expenses), by_currency=by_currency)


class GoogleSheetsRepository:
    """Repositorio de gastos y categorías dinámicas respaldado por Google Sheets."""

    def __init__(
        self,
        spreadsheet: Any,
        expenses_worksheet_name: str = "Gastos",
        categories_worksheet_name: str = "Categorias",
        default_categories: tuple[str, ...] = DEFAULT_CATEGORIES,
    ) -> None:
        self._spreadsheet = spreadsheet
        self._expenses_ws_name = expenses_worksheet_name
        self._categories_ws_name = categories_worksheet_name
        self._default_categories = default_categories
        self._expenses_ws: Any | None = None
        self._categories_ws: Any | None = None

    @classmethod
    def from_credentials(
        cls,
        credentials_path: Path,
        sheet_id: str,
        expenses_worksheet_name: str = "Gastos",
        categories_worksheet_name: str = "Categorias",
    ) -> GoogleSheetsRepository:
        client = gspread.service_account(filename=str(credentials_path))
        spreadsheet = client.open_by_key(sheet_id)
        return cls(
            spreadsheet=spreadsheet,
            expenses_worksheet_name=expenses_worksheet_name,
            categories_worksheet_name=categories_worksheet_name,
        )

    def _get_or_create_worksheet(self, title: str, cols: int) -> Any:
        try:
            return self._spreadsheet.worksheet(title)
        except WorksheetNotFound:
            return self._spreadsheet.add_worksheet(title=title, rows=1000, cols=cols)

    def _initialize_sync(self) -> None:
        self._expenses_ws = self._get_or_create_worksheet(
            self._expenses_ws_name, cols=len(EXPENSES_HEADERS)
        )
        expense_rows = self._expenses_ws.get_all_values()
        if not expense_rows:
            self._expenses_ws.append_row(EXPENSES_HEADERS, value_input_option="USER_ENTERED")

        self._categories_ws = self._get_or_create_worksheet(
            self._categories_ws_name, cols=len(CATEGORIES_HEADERS)
        )
        category_rows = self._categories_ws.get_all_values()
        if not category_rows:
            initial_rows = [CATEGORIES_HEADERS, *([cat] for cat in self._default_categories)]
            self._categories_ws.append_rows(initial_rows, value_input_option="USER_ENTERED")

    def _ensure_ready(self) -> tuple[Any, Any]:
        if self._expenses_ws is None or self._categories_ws is None:
            self._initialize_sync()
        return self._expenses_ws, self._categories_ws

    def _add_expense_sync(self, expense: ExpenseRecord) -> None:
        expenses_ws, _ = self._ensure_ready()
        expenses_ws.append_row(expense_to_row(expense), value_input_option="USER_ENTERED")

    def _delete_expense_sync(self, expense_id: str) -> ExpenseRecord | None:
        expenses_ws, _ = self._ensure_ready()
        rows = expenses_ws.get_all_values()
        for idx in range(len(rows) - 1, 0, -1):
            row = rows[idx]
            if row and str(row[0]).strip() == expense_id:
                record = row_to_expense(row)
                expenses_ws.delete_rows(idx + 1)
                return record
        return None

    def _get_last_expense_sync(self) -> ExpenseRecord | None:
        expenses_ws, _ = self._ensure_ready()
        rows = expenses_ws.get_all_values()
        for row in reversed(rows[1:]):
            record = row_to_expense(row)
            if record is not None:
                return record
        return None

    def _list_expenses_sync(self, start_date: date, end_date: date) -> list[ExpenseRecord]:
        expenses_ws, _ = self._ensure_ready()
        rows = expenses_ws.get_all_values()
        results: list[ExpenseRecord] = []
        for row in rows[1:]:
            record = row_to_expense(row)
            if record is not None and start_date <= record.fecha <= end_date:
                results.append(record)
        return results

    def _list_categories_sync(self) -> list[str]:
        _, categories_ws = self._ensure_ready()
        rows = categories_ws.get_all_values()
        seen: set[str] = set()
        categories: list[str] = []
        for row in rows[1:]:
            if not row:
                continue
            name = str(row[0]).strip()
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                categories.append(name)
        return categories or list(self._default_categories)

    def _add_category_sync(self, name: str) -> tuple[str, bool]:
        cleaned = " ".join(name.strip().split())
        if not cleaned:
            raise ValueError("El nombre de la categoría no puede estar vacío.")

        _, categories_ws = self._ensure_ready()
        existing = self._list_categories_sync()
        for cat in existing:
            if cat.casefold() == cleaned.casefold():
                return cat, False

        categories_ws.append_row([cleaned], value_input_option="USER_ENTERED")
        return cleaned, True

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def add_expense(self, expense: ExpenseRecord) -> None:
        await asyncio.to_thread(self._add_expense_sync, expense)

    async def delete_expense(self, expense_id: str) -> ExpenseRecord | None:
        return await asyncio.to_thread(self._delete_expense_sync, expense_id)

    async def get_last_expense(self) -> ExpenseRecord | None:
        return await asyncio.to_thread(self._get_last_expense_sync)

    async def list_expenses(self, start_date: date, end_date: date) -> list[ExpenseRecord]:
        return await asyncio.to_thread(self._list_expenses_sync, start_date, end_date)

    async def list_categories(self) -> list[str]:
        return await asyncio.to_thread(self._list_categories_sync)

    async def add_category(self, name: str) -> tuple[str, bool]:
        return await asyncio.to_thread(self._add_category_sync, name)
