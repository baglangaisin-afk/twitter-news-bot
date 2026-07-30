"""
run_once.py — один прогон пайплайна и выход.

Точка входа для GitHub Actions: там нет смысла держать бота с кнопкой,
нужно просто собрать новости по расписанию и отправить их в канал.
Для запуска с кнопкой из Telegram используется main.py.
"""
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from telegram import Bot

from modules.pipeline import run_pipeline

load_dotenv()  # локально берём .env, в Actions переменные приходят из секретов

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> int:
    bot = Bot(os.environ["TELEGRAM_BOT_TOKEN"])
    count = await run_pipeline(bot)
    logger.info(f"Прогон завершён, отправлено постов: {count}")
    return count


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Прогон упал с ошибкой: {e}")
        sys.exit(1)
