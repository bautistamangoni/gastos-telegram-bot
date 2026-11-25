from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CATEGORIES: tuple[str, ...] = (
    "Supermercado",
    "Mascota",
    "Tarjeta",
    "Alquiler",
    "Seguro Auto",
    "Internet + telefono",
    "Gas",
    "Luz",
    "Expensas",
    "Verduleria",
    "Otros Gastos",
    "Carniceria + Polleria",
)

FALLBACK_CATEGORY = "Otros Gastos"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., min_length=1)
    allowed_user_id: int = Field(..., gt=0)
    gemini_api_key: str = Field(..., min_length=1)
    gemini_model: str = "gemini-2.5-flash"
    google_sheet_id: str = Field(..., min_length=1)
    google_credentials_path: Path = Path("credentials.json")
    timezone: str = "America/Argentina/Buenos_Aires"
    expenses_worksheet_name: str = "Gastos"
    categories_worksheet_name: str = "Categorias"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
