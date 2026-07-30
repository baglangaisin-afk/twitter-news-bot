"""
main.py — точка входа: Telegram-бот, слушает /news, кнопку и "собрать новости".
"""
import os
import logging
import asyncio
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from modules.pipeline import run_pipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# В .env можно указать несколько id через запятую — например, себе и жене
ALLOWED_USER_IDS = {
    int(x.strip())
    for x in os.environ["TELEGRAM_ALLOWED_USER_ID"].split(",")
    if x.strip()
}

BUTTON_TEXT = "📰 Собрать новости"
KEYBOARD = ReplyKeyboardMarkup([[BUTTON_TEXT]], resize_keyboard=True)

# защита от повторного запуска, пока предыдущий прогон ещё выполняется
_is_running = False


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает кнопку запуска."""
    if update.effective_user.id not in ALLOWED_USER_IDS:
        return
    await update.message.reply_text(
        "Привет! Нажми кнопку ниже или отправь /news, чтобы собрать свежие новости.",
        reply_markup=KEYBOARD,
    )


async def _handle_news_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _is_running

    if update.effective_user.id not in ALLOWED_USER_IDS:
        logger.warning(f"Отклонён запрос от постороннего user_id={update.effective_user.id}")
        return  # молча игнорируем посторонних

    if _is_running:
        await update.message.reply_text("⏳ Сбор уже выполняется, подожди завершения.")
        return

    await update.message.reply_text("🔄 Начинаю сбор...", reply_markup=KEYBOARD)

    async def _task():
        global _is_running
        _is_running = True
        try:
            count = await run_pipeline(context.bot)
            await update.message.reply_text(f"✅ Готово, отправлено {count} постов")
        except Exception as e:
            logger.error(f"Ошибка в пайплайне: {e}")
            await update.message.reply_text(f"❌ Ошибка во время сбора: {e}")
        finally:
            _is_running = False

    asyncio.create_task(_task())


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("news", _handle_news_request))
    app.add_handler(
        MessageHandler(filters.Regex("(?i)собрать новости"), _handle_news_request)
    )

    logger.info(f"Бот запущен, доступ разрешён для {len(ALLOWED_USER_IDS)} пользователей")
    app.run_polling()


if __name__ == "__main__":
    main()
