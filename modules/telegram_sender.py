"""
telegram_sender.py — отправка готового поста (медиа + подпись) в Telegram.

Медиа скачиваем сами и отправляем файлом, а не ссылкой: по URL Telegram тянет
не больше 20 МБ и на превышении молча теряет пост, при загрузке файлом лимит 50 МБ.
"""
import html
import logging
from io import BytesIO

import httpx
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # ограничение Telegram на подпись к медиа
LINK_LABEL = "🔗 Смотреть в X"

# Лимиты Bot API на загрузку файлом
PHOTO_LIMIT = 10 * 1024 * 1024
VIDEO_LIMIT = 50 * 1024 * 1024

DOWNLOAD_TIMEOUT = 180


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


async def _download(url: str, limit: int) -> bytes | None:
    """Скачивает медиа. None, если не влезло в лимит или запрос не удался."""
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram sender: не удалось скачать медиа — {e}")
        return None

    data = response.content
    if len(data) > limit:
        logger.error(
            f"Telegram sender: медиа {len(data) / 1048576:.1f} МБ превышает лимит "
            f"{limit / 1048576:.0f} МБ, пост пропущен — {url}"
        )
        return None

    return data


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
            data = await _download(media_url, PHOTO_LIMIT)
            if data is None:
                return False
            await bot.send_photo(
                chat_id=chat_id,
                photo=BytesIO(data),
                caption=full_caption,
                parse_mode=ParseMode.HTML,
            )
        elif media_type == "video":
            data = await _download(media_url, VIDEO_LIMIT)
            if data is None:
                return False
            await bot.send_video(
                chat_id=chat_id,
                video=BytesIO(data),
                caption=full_caption,
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
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
