from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Currency = Literal["ARS", "USD"]


class ParsedExpense(BaseModel):
    """Esquema estructurado que devuelve Gemini al analizar un mensaje."""

    es_gasto: bool = Field(
        description="True si el mensaje describe un gasto económico real; False en caso contrario."
    )
    monto: float | None = Field(
        default=None,
        description="Monto numérico positivo del gasto. None si es_gasto es False.",
    )
    moneda: Currency = Field(
        default="ARS",
        description="Moneda del gasto: 'ARS' por defecto o 'USD' si menciona dólares/USD.",
    )
    categoria: str = Field(
        default="Otros Gastos",
        description="Categoría exacta elegida de la lista provista.",
    )
    descripcion: str = Field(
        default="",
        description="Descripción corta y clara del gasto (ej. 'Supermercado', 'Alimento perro').",
    )
    medio_pago: str | None = Field(
        default=None,
        description=(
            "Medio de pago si el usuario lo menciona "
            "(Efectivo, Débito, Crédito, Transferencia)."
        ),
    )
    fecha: str | None = Field(
        default=None,
        description=(
            "Fecha del gasto en formato YYYY-MM-DD si el usuario indica otra fecha (ej. 'ayer')."
        ),
    )
    razon_rechazo: str | None = Field(
        default=None,
        description="Explicación breve en español si es_gasto es False.",
    )


class ExpenseRecord(BaseModel):
    """Registro persistido de un gasto."""

    id: str
    fecha: date
    hora: str
    descripcion: str
    categoria: str
    monto: float
    moneda: Currency = "ARS"
    medio_pago: str = ""
    mensaje_original: str = ""


class CurrencyBreakdown(BaseModel):
    """Totales de una moneda específica y su desglose por categoría."""

    total: float = 0.0
    count: int = 0
    by_category: dict[str, float] = Field(default_factory=dict)


class ExpenseSummary(BaseModel):
    """Resumen agregado de una lista de gastos separado por moneda."""

    total_count: int = 0
    by_currency: dict[Currency, CurrencyBreakdown] = Field(default_factory=dict)
