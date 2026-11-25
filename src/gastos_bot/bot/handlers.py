from __future__ import annotations

import calendar
import html
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from gastos_bot.models import Currency, ExpenseRecord, ExpenseSummary
from gastos_bot.services.parser import GeminiExpenseParser, build_expense_record
from gastos_bot.services.repository import ExpenseRepository
from gastos_bot.services.sheets import build_summary

logger = logging.getLogger(__name__)

UNDO_PREFIX = "undo:"


def format_amount(amount: float, currency: Currency) -> str:
    """Formatea montos en estilo legible (ej. $5.000,00 ARS o US$12,00)."""
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if currency == "USD":
        return f"US${formatted}"
    return f"${formatted} ARS"


def format_expense_card(expense: ExpenseRecord, header: str = "✅ Gasto registrado") -> str:
    lines = [
        f"<b>{html.escape(header)}</b>",
        f"• <b>Descripción:</b> {html.escape(expense.descripcion)}",
        f"• <b>Categoría:</b> {html.escape(expense.categoria)}",
        f"• <b>Monto:</b> {html.escape(format_amount(expense.monto, expense.moneda))}",
        f"• <b>Fecha:</b> {expense.fecha.strftime('%d/%m/%Y')} {html.escape(expense.hora)}",
    ]
    if expense.medio_pago:
        lines.append(f"• <b>Medio de pago:</b> {html.escape(expense.medio_pago)}")
    lines.append(f"• <b>ID:</b> <code>{html.escape(expense.id)}</code>")
    return "\n".join(lines)


def format_summary_message(title: str, summary: ExpenseSummary) -> str:
    if summary.total_count == 0:
        return f"<b>{html.escape(title)}</b>\n\nNo hay gastos registrados en este período."

    lines = [f"<b>{html.escape(title)}</b> ({summary.total_count} gastos)\n"]
    for currency, breakdown in summary.by_currency.items():
        lines.append(
            f"<b>Total {currency}:</b> {html.escape(format_amount(breakdown.total, currency))} "
            f"({breakdown.count})"
        )
        for category, cat_total in breakdown.by_category.items():
            pct = (cat_total / breakdown.total * 100) if breakdown.total > 0 else 0.0
            lines.append(
                f"  • {html.escape(category)}: "
                f"{html.escape(format_amount(cat_total, currency))} ({pct:.1f}%)"
            )
        lines.append("")

    return "\n".join(lines).strip()


def _parse_year_month(arg: str, today: date) -> tuple[date, date, str]:
    if not arg:
        year, month = today.year, today.month
    else:
        parts = arg.strip().split("-")
        if len(parts) != 2:
            raise ValueError("Usá el formato YYYY-MM (por ejemplo: /mes 2026-10).")
        year, month = int(parts[0]), int(parts[1])
        if not (1 <= month <= 12):
            raise ValueError("El mes debe estar entre 01 y 12.")

    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day), f"{year}-{month:02d}"


class BotHandlers:
    """Agrupa los handlers del bot con inyección de dependencias."""

    def __init__(
        self,
        allowed_user_id: int,
        tz: ZoneInfo,
        parser: GeminiExpenseParser,
        repository: ExpenseRepository,
    ) -> None:
        self._allowed_user_id = allowed_user_id
        self._tz = tz
        self._parser = parser
        self._repository = repository

    def _is_authorized(self, update: Update) -> bool:
        user = update.effective_user
        if user is None or user.id != self._allowed_user_id:
            logger.warning(
                "Acceso bloqueado para user_id=%s",
                user.id if user else "desconocido",
            )
            return False
        return True

    def _now(self) -> datetime:
        return datetime.now(self._tz)

    async def start_or_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_authorized(update) or update.message is None:
            return

        text = (
            "<b>Bot de Gastos Personales</b>\n\n"
            "Enviame un mensaje en lenguaje natural para registrar un gasto. Ejemplos:\n"
            "• <code>supermercado 5000 pesos</code>\n"
            "• <code>verduleria 8500 con debito</code>\n"
            "• <code>ayer carniceria 15 lucas</code>\n"
            "• <code>netflix 12 usd</code>\n\n"
            "<b>Comandos disponibles:</b>\n"
            "• /hoy — Resumen de gastos de hoy\n"
            "• /mes o /resumen — Resumen del mes (opcional: <code>/mes 2026-10</code>)\n"
            "• /ultimo — Ver el último gasto registrado\n"
            "• /deshacer — Eliminar el último gasto registrado\n"
            "• /categorias — Ver categorías activas\n"
            "• /agregar_categoria &lt;nombre&gt; — Sumar una categoría nueva\n"
            "• /ayuda — Mostrar esta ayuda"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def list_categories(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_authorized(update) or update.message is None:
            return

        categories = await self._repository.list_categories()
        bullets = "\n".join(f"• {html.escape(cat)}" for cat in categories)
        text = (
            f"<b>Categorías activas ({len(categories)}):</b>\n"
            f"{bullets}\n\n"
            "Podés sumar una nueva con <code>/agregar_categoria Nombre</code>."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def add_category(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_authorized(update) or update.message is None:
            return

        raw_name = " ".join(context.args).strip() if context.args else ""
        if not raw_name:
            await update.message.reply_text(
                "Indicá el nombre de la categoría. Ejemplo:\n"
                "<code>/agregar_categoria Farmacia</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        try:
            canonical, created = await self._repository.add_category(raw_name)
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {html.escape(str(exc))}", parse_mode=ParseMode.HTML)
            return

        if created:
            await update.message.reply_text(
                f"✅ Categoría <b>{html.escape(canonical)}</b> agregada a Google Sheets.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(
                f"ℹ️ La categoría <b>{html.escape(canonical)}</b> ya existe.",
                parse_mode=ParseMode.HTML,
            )

    async def today_summary(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_authorized(update) or update.message is None:
            return

        today = self._now().date()
        expenses = await self._repository.list_expenses(today, today)
        summary = build_summary(expenses)
        title = f"Resumen de hoy ({today.strftime('%d/%m/%Y')})"
        await update.message.reply_text(
            format_summary_message(title, summary),
            parse_mode=ParseMode.HTML,
        )

    async def month_summary(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_authorized(update) or update.message is None:
            return

        arg = context.args[0] if context.args else ""
        try:
            start_date, end_date, label = _parse_year_month(arg, self._now().date())
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {html.escape(str(exc))}", parse_mode=ParseMode.HTML)
            return

        expenses = await self._repository.list_expenses(start_date, end_date)
        summary = build_summary(expenses)
        await update.message.reply_text(
            format_summary_message(f"Resumen mensual ({label})", summary),
            parse_mode=ParseMode.HTML,
        )

    async def last_expense(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_authorized(update) or update.message is None:
            return

        last = await self._repository.get_last_expense()
        if last is None:
            await update.message.reply_text("Todavía no hay gastos registrados.")
            return

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🗑️ Deshacer", callback_data=f"{UNDO_PREFIX}{last.id}")]]
        )
        await update.message.reply_text(
            format_expense_card(last, header="🧾 Último gasto registrado"),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    async def undo_last(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_authorized(update) or update.message is None:
            return

        last = await self._repository.get_last_expense()
        if last is None:
            await update.message.reply_text("No hay ningún gasto para deshacer.")
            return

        deleted = await self._repository.delete_expense(last.id)
        if deleted is None:
            await update.message.reply_text("No se pudo eliminar el último gasto.")
            return

        await update.message.reply_text(
            format_expense_card(deleted, header="🗑️ Gasto eliminado"),
            parse_mode=ParseMode.HTML,
        )

    async def handle_expense_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_authorized(update) or update.message is None or not update.message.text:
            return

        if update.effective_chat is not None:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action=ChatAction.TYPING,
            )

        text = update.message.text.strip()
        now = self._now()

        try:
            categories = await self._repository.list_categories()
            parsed = await self._parser.parse(text=text, categories=categories, now=now)
        except Exception:
            logger.exception("Error al parsear mensaje con Gemini")
            await update.message.reply_text(
                "❌ Hubo un error al interpretar el mensaje. Intentá nuevamente en unos segundos."
            )
            return

        if not parsed.es_gasto or parsed.monto is None or parsed.monto <= 0:
            reason = parsed.razon_rechazo or (
                "No pude detectar un gasto con monto. Probá algo como 'supermercado 5000'."
            )
            await update.message.reply_text(f"🤔 {html.escape(reason)}", parse_mode=ParseMode.HTML)
            return

        record = build_expense_record(
            parsed=parsed,
            original_text=text,
            categories=categories,
            now=now,
        )

        try:
            await self._repository.add_expense(record)
        except Exception:
            logger.exception("Error al guardar gasto en Google Sheets")
            await update.message.reply_text(
                "❌ Interpreté el gasto pero falló el guardado en Google Sheets. "
                "Revisá los logs y la conexión."
            )
            return

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🗑️ Deshacer", callback_data=f"{UNDO_PREFIX}{record.id}")]]
        )
        await update.message.reply_text(
            format_expense_card(record),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    async def handle_undo_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None:
            return

        if not self._is_authorized(update):
            await query.answer("No autorizado.", show_alert=True)
            return

        await query.answer()
        data = query.data or ""
        expense_id = data.removeprefix(UNDO_PREFIX)

        deleted = await self._repository.delete_expense(expense_id)
        if deleted is None:
            await query.edit_message_text("ℹ️ Ese gasto ya había sido eliminado.")
            return

        await query.edit_message_text(
            format_expense_card(deleted, header="🗑️ Gasto anulado"),
            parse_mode=ParseMode.HTML,
        )

    def register(self, app: Application) -> None:
        app.add_handler(CommandHandler(["start", "ayuda", "help"], self.start_or_help))
        app.add_handler(CommandHandler("categorias", self.list_categories))
        app.add_handler(CommandHandler("agregar_categoria", self.add_category))
        app.add_handler(CommandHandler("hoy", self.today_summary))
        app.add_handler(CommandHandler(["mes", "resumen"], self.month_summary))
        app.add_handler(CommandHandler("ultimo", self.last_expense))
        app.add_handler(CommandHandler("deshacer", self.undo_last))
        app.add_handler(
            CallbackQueryHandler(self.handle_undo_callback, pattern=rf"^{UNDO_PREFIX}[a-f0-9]+$")
        )
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_expense_message)
        )
