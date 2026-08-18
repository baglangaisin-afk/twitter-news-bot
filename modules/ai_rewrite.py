"""
ai_rewrite.py — перевод + рерайт твита в вирусный пост через Groq API.
"""
import os
import re
import time
import logging
from groq import Groq

# Бесплатный тариф Groq ограничен по токенам в минуту. Пауза перед повтором
# берётся с запасом: лимит скользящий, минуты хватает на его сброс.
RATE_LIMIT_WAIT = 45

# t.co-ссылки ведут на сам твит и в готовом посте только мешают
TCO_LINK_RE = re.compile(r"https?://t\.co/\S+")

logger = logging.getLogger(__name__)

# Модель вынесена в переменную окружения: Groq выводит модели из эксплуатации
# без предупреждения, и тогда каждый вызов падает с 404, а канал молча пустеет.
# Так замена сводится к правке секрета, без выката кода.
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

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

Точность важнее яркости. Не добавляй фактов, которых нет в твите: ни оценок вроде «впервые в истории», ни подробностей, ни домыслов. Не путай, кто кому что сделал — если в твите один человек помог другому, не переписывай это как действие в свою пользу. Названия фильмов, шоу и альбомов оставляй как в оригинале, не переводи их.

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

    for attempt in (1, 2):
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
            # Лимит токенов в минуту — не повод терять сюжет: ждём и пробуем ещё раз
            if attempt == 1 and "rate_limit" in str(e).lower():
                logger.warning(f"AI rewrite: упёрлись в лимит Groq, ждём {RATE_LIMIT_WAIT}с")
                time.sleep(RATE_LIMIT_WAIT)
                continue
            logger.error(f"AI rewrite: ошибка Groq API — {e}")
            return None
