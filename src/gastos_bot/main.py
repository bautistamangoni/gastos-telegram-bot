from __future__ import annotations

import logging

from telegram.ext import Application, ApplicationBuilder

from gastos_bot.bot.handlers import BotHandlers
from gastos_bot.config import Settings
from gastos_bot.services.parser import GeminiExpenseParser
from gastos_bot.services.sheets import GoogleSheetsRepository

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings()

    logger.info("Conectando con Google Sheets (sheet_id=%s)...", settings.google_sheet_id)
    repository = GoogleSheetsRepository.from_credentials(
        credentials_path=settings.google_credentials_path,
        sheet_id=settings.google_sheet_id,
        expenses_worksheet_name=settings.expenses_worksheet_name,
        categories_worksheet_name=settings.categories_worksheet_name,
    )

    parser = GeminiExpenseParser(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    handlers = BotHandlers(
        allowed_user_id=settings.allowed_user_id,
        tz=settings.tz,
        parser=parser,
        repository=repository,
    )

    async def post_init(app: Application) -> None:
        await repository.initialize()
        logger.info("Pestañas de Google Sheets inicializadas correctamente.")

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    handlers.register(app)

    logger.info("Bot iniciado en modo polling (whitelist user_id=%s).", settings.allowed_user_id)
    app.run_polling()


if __name__ == "__main__":
    main()
