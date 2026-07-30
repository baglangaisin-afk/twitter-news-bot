"""
ranker.py — отбор кандидатов: отсев непопулярных и несвежих, сортировка по разгону.

Сортируем не по сумме лайков, а по скорости их набора (лайки в час). Иначе твит
47-часовой давности с 50к лайков обгонит часовой с 8к — хотя первый уже все видели,
а второй разгоняется прямо сейчас.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Возраст моложе этого считаем за него: у свежих твитов деление на почти ноль
# давало бы бесконечную скорость и они бы всегда шли первыми
MIN_AGE_HOURS = 1.0

# Возраст для твита с неразобранной датой — чтобы он не выпал и не всплыл наверх
FALLBACK_AGE_HOURS = 24.0


def _age_hours(tweet: dict) -> float | None:
    """Возраст твита в часах. None, если дату разобрать не удалось."""
    raw = tweet.get("created_at")
    if not raw:
        return None
    try:
        created = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        logger.warning(f"Ranker: не разобрал дату {raw!r}")
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds() / 3600


def velocity(tweet: dict) -> float:
    """Скорость набора лайков — лайков в час."""
    likes = tweet.get("likes") or 0
    age = _age_hours(tweet)
    if age is None:
        age = FALLBACK_AGE_HOURS
    return likes / max(age, MIN_AGE_HOURS)


def rank_candidates(
    tweets: list[dict],
    min_likes: int = 0,
    max_age_hours: float = 0,
) -> list[dict]:
    """
    Отсеивает твиты слабее порога по лайкам и старше max_age_hours,
    возвращает остальные по убыванию скорости набора лайков.
    Жёсткого лимита по количеству нет — сколько набралось, столько и вернём.
    max_age_hours=0 отключает проверку возраста.
    Твит с неразобранной датой не отсеиваем — лучше лишний пост, чем молчание.
    """
    selected = []
    for tweet in tweets:
        if (tweet.get("likes") or 0) < min_likes:
            continue
        if max_age_hours:
            age = _age_hours(tweet)
            if age is not None and age > max_age_hours:
                continue
        selected.append(tweet)

    return sorted(selected, key=velocity, reverse=True)
