"""
ranker.py — отбор кандидатов: отсев непопулярных и несвежих, сортировка по лайкам.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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


def rank_candidates(
    tweets: list[dict],
    min_likes: int = 0,
    max_age_hours: float = 0,
) -> list[dict]:
    """
    Отсеивает твиты слабее порога по лайкам и старше max_age_hours,
    возвращает остальные от самых популярных к менее популярным.
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

    return sorted(selected, key=lambda t: t.get("likes", 0), reverse=True)
