from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from gastos_bot.bot.handlers import BotHandlers, format_amount
from gastos_bot.config import DEFAULT_CATEGORIES
from gastos_bot.models import ExpenseRecord, ParsedExpense

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
ALLOWED_ID = 999888


class _InMemoryRepo:
    def __init__(self) -> None:
        self.expenses: list[ExpenseRecord] = []
        self.categories: list[str] = list(DEFAULT_CATEGORIES)

    async def initialize(self) -> None:
        return None

    async def add_expense(self, expense: ExpenseRecord) -> None:
        self.expenses.append(expense)

    async def delete_expense(self, expense_id: str) -> ExpenseRecord | None:
        for idx, item in enumerate(self.expenses):
            if item.id == expense_id:
                return self.expenses.pop(idx)
        return None

    async def get_last_expense(self) -> ExpenseRecord | None:
        return self.expenses[-1] if self.expenses else None

    async def list_expenses(self, start_date: date, end_date: date) -> list[ExpenseRecord]:
        return [e for e in self.expenses if start_date <= e.fecha <= end_date]

    async def list_categories(self) -> list[str]:
        return list(self.categories)

    async def add_category(self, name: str) -> tuple[str, bool]:
        cleaned = " ".join(name.strip().split())
        for existing in self.categories:
            if existing.casefold() == cleaned.casefold():
                return existing, False
        self.categories.append(cleaned)
        return cleaned, True


class _FakeParser:
    def __init__(self, parsed: ParsedExpense) -> None:
        self._parsed = parsed

    async def parse(self, text: str, categories: list[str], now: datetime) -> ParsedExpense:
        return self._parsed


def _make_update(user_id: int, text: str = "") -> SimpleNamespace:
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
        message=message,
        callback_query=None,
    )


def _make_context(args: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        args=args or [],
        bot=SimpleNamespace(send_chat_action=AsyncMock()),
    )


async def test_whitelist_blocks_unauthorized_user():
    repo = _InMemoryRepo()
    parser = _FakeParser(ParsedExpense(es_gasto=True, monto=5000, categoria="Supermercado"))
    handlers = BotHandlers(ALLOWED_ID, TZ, parser, repo)  # type: ignore[arg-type]

    update = _make_update(user_id=111111, text="supermercado 5000")
    await handlers.handle_expense_message(update, _make_context())

    assert repo.expenses == []
    update.message.reply_text.assert_not_called()


async def test_handle_expense_and_undo_callback():
    repo = _InMemoryRepo()
    parser = _FakeParser(
        ParsedExpense(
            es_gasto=True,
            monto=5000.0,
            moneda="ARS",
            categoria="Supermercado",
            descripcion="Supermercado",
        )
    )
    handlers = BotHandlers(ALLOWED_ID, TZ, parser, repo)  # type: ignore[arg-type]

    update = _make_update(user_id=ALLOWED_ID, text="supermercado 5000 pesos")
    await handlers.handle_expense_message(update, _make_context())

    assert len(repo.expenses) == 1
    saved = repo.expenses[0]
    assert saved.categoria == "Supermercado"
    assert saved.monto == 5000.0
    update.message.reply_text.assert_awaited_once()
    reply_text = update.message.reply_text.call_args.args[0]
    assert "Gasto registrado" in reply_text
    assert "$5.000,00 ARS" in reply_text

    # Simula click en botón inline Deshacer
    query = SimpleNamespace(
        data=f"undo:{saved.id}",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    cb_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=ALLOWED_ID),
        callback_query=query,
    )
    await handlers.handle_undo_callback(cb_update, _make_context())

    assert repo.expenses == []
    query.edit_message_text.assert_awaited_once()
    assert "Gasto anulado" in query.edit_message_text.call_args.args[0]


async def test_add_category_command():
    repo = _InMemoryRepo()
    parser = _FakeParser(ParsedExpense(es_gasto=False))
    handlers = BotHandlers(ALLOWED_ID, TZ, parser, repo)  # type: ignore[arg-type]

    update = _make_update(user_id=ALLOWED_ID)
    await handlers.add_category(update, _make_context(args=["Farmacia", "y", "Salud"]))

    assert "Farmacia y Salud" in repo.categories
    assert "agregada" in update.message.reply_text.call_args.args[0]


async def test_month_summary_formats_currencies():
    repo = _InMemoryRepo()
    today = datetime.now(TZ).date()
    repo.expenses.append(
        ExpenseRecord(
            id="abc12345",
            fecha=today,
            hora="12:00",
            descripcion="Carne",
            categoria="Carniceria + Polleria",
            monto=18000.0,
            moneda="ARS",
        )
    )
    parser = _FakeParser(ParsedExpense(es_gasto=False))
    handlers = BotHandlers(ALLOWED_ID, TZ, parser, repo)  # type: ignore[arg-type]

    update = _make_update(user_id=ALLOWED_ID)
    await handlers.month_summary(update, _make_context())

    reply = update.message.reply_text.call_args.args[0]
    assert "Carniceria + Polleria" in reply
    assert format_amount(18000.0, "ARS") in reply
