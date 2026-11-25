from __future__ import annotations

from datetime import date

from gspread.exceptions import WorksheetNotFound

from gastos_bot.config import DEFAULT_CATEGORIES
from gastos_bot.models import ExpenseRecord
from gastos_bot.services.sheets import (
    CATEGORIES_HEADERS,
    EXPENSES_HEADERS,
    GoogleSheetsRepository,
    build_summary,
    expense_to_row,
    row_to_expense,
)


class _FakeWorksheet:
    def __init__(self, title: str, rows: list[list[str]] | None = None) -> None:
        self.title = title
        self._rows: list[list[str]] = rows or []

    def get_all_values(self) -> list[list[str]]:
        return [list(r) for r in self._rows]

    def append_row(self, row: list, value_input_option: str = "USER_ENTERED") -> None:
        self._rows.append([str(v) for v in row])

    def append_rows(self, rows: list[list], value_input_option: str = "USER_ENTERED") -> None:
        for row in rows:
            self.append_row(row, value_input_option=value_input_option)

    def delete_rows(self, start_index: int, end_index: int | None = None) -> None:
        end = end_index or start_index
        del self._rows[start_index - 1 : end]


class _FakeSpreadsheet:
    def __init__(self) -> None:
        self._sheets: dict[str, _FakeWorksheet] = {}

    def worksheet(self, title: str) -> _FakeWorksheet:
        if title not in self._sheets:
            raise WorksheetNotFound(title)
        return self._sheets[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> _FakeWorksheet:
        ws = _FakeWorksheet(title)
        self._sheets[title] = ws
        return ws


async def test_initialize_creates_worksheets_and_default_categories():
    spreadsheet = _FakeSpreadsheet()
    repo = GoogleSheetsRepository(spreadsheet=spreadsheet)

    await repo.initialize()

    gastos_ws = spreadsheet.worksheet("Gastos")
    cats_ws = spreadsheet.worksheet("Categorias")
    assert gastos_ws.get_all_values() == [EXPENSES_HEADERS]
    assert cats_ws.get_all_values()[0] == CATEGORIES_HEADERS
    categories = await repo.list_categories()
    assert categories == list(DEFAULT_CATEGORIES)


async def test_add_category_persists_and_prevents_duplicates():
    spreadsheet = _FakeSpreadsheet()
    repo = GoogleSheetsRepository(spreadsheet=spreadsheet)
    await repo.initialize()

    name, created = await repo.add_category("  Farmacia  ")
    assert (name, created) == ("Farmacia", True)

    dup_name, dup_created = await repo.add_category("farmacia")
    assert (dup_name, dup_created) == ("Farmacia", False)
    assert "Farmacia" in await repo.list_categories()


async def test_crud_expenses_and_date_filtering():
    spreadsheet = _FakeSpreadsheet()
    repo = GoogleSheetsRepository(spreadsheet=spreadsheet)
    await repo.initialize()

    e1 = ExpenseRecord(
        id="aaaa1111",
        fecha=date(2026, 11, 10),
        hora="10:00",
        descripcion="Supermercado",
        categoria="Supermercado",
        monto=5000.0,
        moneda="ARS",
        medio_pago="Débito",
        mensaje_original="supermercado 5000",
    )
    e2 = ExpenseRecord(
        id="bbbb2222",
        fecha=date(2026, 11, 25),
        hora="20:15",
        descripcion="Netflix",
        categoria="Otros Gastos",
        monto=12.0,
        moneda="USD",
        mensaje_original="netflix 12 usd",
    )

    await repo.add_expense(e1)
    await repo.add_expense(e2)

    last = await repo.get_last_expense()
    assert last is not None and last.id == "bbbb2222"

    nov_items = await repo.list_expenses(date(2026, 11, 1), date(2026, 11, 30))
    assert [e.id for e in nov_items] == ["aaaa1111", "bbbb2222"]

    only_today = await repo.list_expenses(date(2026, 11, 25), date(2026, 11, 25))
    assert [e.id for e in only_today] == ["bbbb2222"]

    deleted = await repo.delete_expense("bbbb2222")
    assert deleted is not None and deleted.id == "bbbb2222"
    assert await repo.delete_expense("bbbb2222") is None
    remaining = await repo.get_last_expense()
    assert remaining is not None and remaining.id == "aaaa1111"


def test_row_serialization_roundtrip():
    record = ExpenseRecord(
        id="1234abcd",
        fecha=date(2026, 11, 25),
        hora="09:30",
        descripcion="Alimento gato",
        categoria="Mascota",
        monto=14500.5,
        moneda="ARS",
        medio_pago="Transferencia",
        mensaje_original="alimento gato 14500.5 transferencia",
    )
    row = [str(v) for v in expense_to_row(record)]
    assert row_to_expense(row) == record


def test_build_summary_separates_currencies_and_sorts_categories():
    expenses = [
        ExpenseRecord(
            id="1",
            fecha=date(2026, 11, 20),
            hora="10:00",
            descripcion="Super",
            categoria="Supermercado",
            monto=10000.0,
            moneda="ARS",
        ),
        ExpenseRecord(
            id="2",
            fecha=date(2026, 11, 21),
            hora="11:00",
            descripcion="Luz",
            categoria="Luz",
            monto=25000.0,
            moneda="ARS",
        ),
        ExpenseRecord(
            id="3",
            fecha=date(2026, 11, 22),
            hora="12:00",
            descripcion="Hosting",
            categoria="Otros Gastos",
            monto=15.0,
            moneda="USD",
        ),
    ]

    summary = build_summary(expenses)
    assert summary.total_count == 3
    assert summary.by_currency["ARS"].total == 35000.0
    assert list(summary.by_currency["ARS"].by_category.keys()) == ["Luz", "Supermercado"]
    assert summary.by_currency["USD"].total == 15.0
