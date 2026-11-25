from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from gastos_bot.config import DEFAULT_CATEGORIES
from gastos_bot.models import ParsedExpense
from gastos_bot.services.parser import (
    GeminiExpenseParser,
    build_expense_record,
    normalize_category,
)

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


class _FakeModels:
    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response
        self.last_call: dict | None = None

    def generate_content(self, **kwargs):
        self.last_call = kwargs
        return self._response


class _FakeClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self.models = _FakeModels(response)


async def test_gemini_parser_returns_parsed_expense():
    expected = ParsedExpense(
        es_gasto=True,
        monto=5000.0,
        moneda="ARS",
        categoria="Supermercado",
        descripcion="Supermercado",
        medio_pago="Débito",
        fecha=None,
    )
    fake_client = _FakeClient(SimpleNamespace(parsed=expected, text=None))
    parser = GeminiExpenseParser(api_key="test-key", client=fake_client)
    now = datetime(2026, 11, 25, 14, 30, tzinfo=TZ)

    result = await parser.parse(
        text="supermercado 5000 pesos con debito",
        categories=list(DEFAULT_CATEGORIES),
        now=now,
    )

    assert result == expected
    assert fake_client.models.last_call is not None
    assert fake_client.models.last_call["contents"] == "supermercado 5000 pesos con debito"


async def test_gemini_parser_falls_back_to_json_text():
    raw_json = (
        '{"es_gasto": true, "monto": 12.5, "moneda": "USD", '
        '"categoria": "Otros Gastos", "descripcion": "Suscripcion"}'
    )
    fake_client = _FakeClient(SimpleNamespace(parsed=None, text=raw_json))
    parser = GeminiExpenseParser(api_key="test-key", client=fake_client)
    now = datetime(2026, 11, 25, 14, 30, tzinfo=TZ)

    result = await parser.parse("suscripcion 12.5 usd", list(DEFAULT_CATEGORIES), now)

    assert result.es_gasto is True
    assert result.monto == 12.5
    assert result.moneda == "USD"


def test_normalize_category_case_insensitive_and_fallback():
    cats = list(DEFAULT_CATEGORIES)
    assert normalize_category("carniceria + polleria", cats) == "Carniceria + Polleria"
    assert normalize_category("Categoria Inexistente", cats) == "Otros Gastos"


def test_build_expense_record_handles_relative_date_and_defaults():
    now = datetime(2026, 11, 25, 18, 45, tzinfo=TZ)
    parsed = ParsedExpense(
        es_gasto=True,
        monto=8500,
        moneda="ARS",
        categoria="verduleria",
        descripcion="Verdulería",
        fecha="2026-11-24",
    )

    record = build_expense_record(
        parsed=parsed,
        original_text="ayer verduleria 8500",
        categories=list(DEFAULT_CATEGORIES),
        now=now,
    )

    assert len(record.id) == 8
    assert record.fecha == date(2026, 11, 24)
    assert record.hora == "18:45"
    assert record.categoria == "Verduleria"
    assert record.monto == 8500.0
    assert record.moneda == "ARS"


def test_build_expense_record_rejects_non_expense():
    now = datetime(2026, 11, 25, 18, 45, tzinfo=TZ)
    parsed = ParsedExpense(es_gasto=False, razon_rechazo="Es un saludo, no un gasto.")

    with pytest.raises(ValueError, match="saludo"):
        build_expense_record(parsed, "hola!", list(DEFAULT_CATEGORIES), now)
