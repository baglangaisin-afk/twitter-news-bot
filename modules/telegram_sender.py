"""
telegram_sender.py — отправка готового поста (медиа + подпись) в Telegram.
"""
import html
import logging
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # ограничение Telegram на подпись к медиа
LINK_LABEL = "🔗 Смотреть в X"


def build_caption(text: str, source_url: str | None) -> str:
    """
    Собирает подпись: текст поста + ссылка на исходный твит.
    Текст режем по лимиту Telegram с запасом под ссылку, теги в счёт длины не идут.
    """
    if not source_url:
        return html.escape(text[:CAPTION_LIMIT])

    reserve = len(LINK_LABEL) + 2  # две переносимые строки перед ссылкой
    body = text[: CAPTION_LIMIT - reserve]
    link = f'<a href="{html.escape(source_url, quote=True)}">{LINK_LABEL}</a>'
    return f"{html.escape(body)}\n\n{link}"


async def send_post(
    bot: Bot,
    chat_id: str,
    caption: str,
    media_url: str,
    media_type: str,
    source_url: str | None = None,
) -> bool:
    """
    Отправляет пост в chat_id. Возвращает True/False (успех), не бросает исключение наружу —
    ошибка одного поста не должна прерывать остальной пайплайн.
    """
    try:
        full_caption = build_caption(caption, source_url)

        if media_type == "photo":
            await bot.send_photo(
                chat_id=chat_id,
                photo=media_url,
                caption=full_caption,
                parse_mode=ParseMode.HTML,
            )
        elif media_type == "video":
            await bot.send_video(
                chat_id=chat_id,
                video=media_url,
                caption=full_caption,
                parse_mode=ParseMode.HTML,
            )
        else:
            logger.error(f"Telegram sender: неизвестный media_type={media_type}")
            return False

        return True

    except TelegramError as e:
        logger.error(f"Telegram sender: ошибка отправки — {e}")
        return False
    except Exception as e:
        logger.error(f"Telegram sender: неожиданная ошибка — {e}")
        return False
