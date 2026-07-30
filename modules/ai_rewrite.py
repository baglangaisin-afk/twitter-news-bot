"""
ai_rewrite.py — перевод + рерайт твита в вирусный пост через Groq API.
"""
import os
import re
import logging
from groq import Groq

# t.co-ссылки ведут на сам твит и в готовом посте только мешают
TCO_LINK_RE = re.compile(r"https?://t\.co/\S+")

logger = logging.getLogger(__name__)

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — главный редактор популярного поп-культурного Telegram-канала.

Канал пишет про:
— звёзд кино и сериалов, музыкантов, иконы моды, селебрити;
— мировых спортивных звёзд первой величины;
— масштабные события индустрии: премьеры, «Оскар», «Грэмми», Met Gala, крупные фестивали и показы;
— скандалы, слухи, интриги и громкие разборки вокруг знаменитостей.

Задача: перевести твит из X на русский язык и сделать из него короткий, увлекательный и вирусный пост (не более 800 символов).

Ответь одним словом SKIP, если верно хотя бы одно:
— твит про политику, тюрьму или убийство;
— твит не подходит каналу по теме: местные происшествия, бизнес и финансы, техника, погода, реклама, спортивная статистика без звёзд, малоизвестные персоны.

Имена людей и названия передавай кириллицей (Zendaya → Зендая, Met Gala → Мет Гала).

В ответе выдавай только готовый текст поста — без пояснений, заголовков и кавычек."""

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def rewrite_tweet(text: str) -> str | None:
    """
    Возвращает переписанный текст на русском, либо None если модель ответила SKIP
    или произошла ошибка (пайплайн должен пропустить твит).
    """
    clean_text = TCO_LINK_RE.sub("", text).replace("\n", " ").replace("\r", " ").strip()
    if not clean_text:
        return None

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": clean_text},
            ],
            max_tokens=1000,
        )
        result = response.choices[0].message.content.strip()

        if result.upper() == "SKIP":
            logger.info("AI rewrite: твит помечен как SKIP")
            return None

        return result

    except Exception as e:
        logger.error(f"AI rewrite: ошибка Groq API — {e}")
        return None
