from __future__ import annotations

from datetime import date
from typing import Protocol

from gastos_bot.models import ExpenseRecord


class ExpenseRepository(Protocol):
    """Interfaz abstracta para persistencia de gastos y categorías."""

    async def initialize(self) -> None: ...

    async def add_expense(self, expense: ExpenseRecord) -> None: ...

    async def delete_expense(self, expense_id: str) -> ExpenseRecord | None: ...

    async def get_last_expense(self) -> ExpenseRecord | None: ...

    async def list_expenses(self, start_date: date, end_date: date) -> list[ExpenseRecord]: ...

    async def list_categories(self) -> list[str]: ...

    async def add_category(self, name: str) -> tuple[str, bool]: ...
