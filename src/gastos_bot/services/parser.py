from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from google import genai
from google.genai import types

from gastos_bot.config import FALLBACK_CATEGORY
from gastos_bot.models import ExpenseRecord, ParsedExpense


def _build_system_prompt(categories: list[str], now: datetime) -> str:
    categories_bullet = "\n".join(f"- {cat}" for cat in categories)
    return (
        "Sos un asistente experto en extraer gastos personales desde mensajes breves en español "
        "(especialmente español rioplatense / Argentina).\n"
        f"Fecha y hora local actual: {now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%A')}).\n\n"
        "Reglas estrictas:\n"
        "1. Si el mensaje NO describe un gasto o no incluye un monto claro, devolvé es_gasto=false "
        "y una razon_rechazo amigable.\n"
        "2. Interpreta expresiones coloquiales de montos: '5 lucas' = 5000, 'media luca' = 500, "
        "'1.5k' = 1500, '2 palos' = 2000000.\n"
        "3. Moneda: usa 'ARS' por defecto. Solo usa 'USD' si el usuario menciona dólares, usd, "
        "u$s, u$d o verdes.\n"
        "4. Categoría: elegí EXACTAMENTE una de las siguientes categorías disponibles:\n"
        f"{categories_bullet}\n"
        f"Si ninguna encaja bien, usá '{FALLBACK_CATEGORY}'.\n"
        "5. Fecha: si el usuario menciona una fecha relativa ('ayer', 'anteayer', 'el lunes') "
        "o explícita, devolvela en formato YYYY-MM-DD calculada respecto a la fecha actual. "
        "Si no menciona fecha, devolvé null.\n"
        "6. Descripción: breve y capitalizada "
        "(ej. 'Supermercado', 'Alimento mascota', 'Factura luz').\n"
        "7. Medio de pago: solo completalo si el usuario lo menciona (ej. Efectivo, Débito, "
        "Crédito, Transferencia, Mercado Pago); si no, devolvé null."
    )


def normalize_category(raw_category: str, categories: list[str]) -> str:
    """Normaliza la categoría al nombre exacto configurado o usa el fallback."""
    lookup = {cat.casefold(): cat for cat in categories}
    cleaned = raw_category.strip().casefold()
    if cleaned in lookup:
        return lookup[cleaned]
    if FALLBACK_CATEGORY.casefold() in lookup:
        return lookup[FALLBACK_CATEGORY.casefold()]
    return categories[0] if categories else FALLBACK_CATEGORY


def build_expense_record(
    parsed: ParsedExpense,
    original_text: str,
    categories: list[str],
    now: datetime,
) -> ExpenseRecord:
    """Construye un ExpenseRecord validado a partir de un ParsedExpense."""
    if not parsed.es_gasto or parsed.monto is None or parsed.monto <= 0:
        raise ValueError(parsed.razon_rechazo or "El mensaje no contiene un gasto válido.")

    expense_date = now.date()
    if parsed.fecha:
        try:
            expense_date = date.fromisoformat(parsed.fecha.strip())
        except ValueError:
            expense_date = now.date()

    description = parsed.descripcion.strip() or original_text.strip()
    category = normalize_category(parsed.categoria, categories)
    payment_method = (parsed.medio_pago or "").strip()

    return ExpenseRecord(
        id=uuid4().hex[:8],
        fecha=expense_date,
        hora=now.strftime("%H:%M"),
        descripcion=description,
        categoria=category,
        monto=round(float(parsed.monto), 2),
        moneda=parsed.moneda,
        medio_pago=payment_method,
        mensaje_original=original_text.strip(),
    )


class GeminiExpenseParser:
    """Parser de gastos en lenguaje natural respaldado por Gemini Structured Outputs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._client = client if client is not None else genai.Client(api_key=api_key)

    def _parse_sync(self, text: str, categories: list[str], now: datetime) -> ParsedExpense:
        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(categories, now),
            response_mime_type="application/json",
            response_schema=ParsedExpense,
            temperature=0.1,
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=text,
            config=config,
        )

        if getattr(response, "parsed", None) is not None:
            parsed = response.parsed
            if isinstance(parsed, ParsedExpense):
                return parsed
            return ParsedExpense.model_validate(parsed)

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise RuntimeError("Gemini devolvió una respuesta vacía.")
        return ParsedExpense.model_validate_json(raw_text)

    async def parse(self, text: str, categories: list[str], now: datetime) -> ParsedExpense:
        return await asyncio.to_thread(self._parse_sync, text, categories, now)
