"""
cluster.py — группировка твитов об одном и том же событии.

Одну новость освещают сразу несколько аккаунтов: премьеру снимут и TMZ, и PageSix,
и PopCrave. Без группировки в канал уйдут три почти одинаковых поста и уйдут три
вызова Groq вместо одного.

Схожесть считаем по пересечению слов (коэффициент Жаккара) — без внешних
зависимостей и моделей: заголовки новостей об одном событии переиспользуют
имена и ключевые слова, этого достаточно.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Замерено на живых твитах: настоящие дубли об одном событии дают ~0.75,
# а шаблонные твиты разных событий («Happy Nth birthday to the talented ...») — ~0.33.
# Порог посередине: дубли ловим, однотипные, но разные новости не склеиваем.
DEFAULT_THRESHOLD = 0.45

URL_RE = re.compile(r"https?://\S+")
TOKEN_RE = re.compile(r"[a-zа-яё0-9']+", re.IGNORECASE)

# Служебные слова не несут смысла, но раздувают пересечение
STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "has", "have", "was", "were",
    "are", "his", "her", "she", "him", "they", "them", "their", "its", "but", "not",
    "you", "your", "who", "what", "when", "will", "just", "out", "all", "new", "now",
    "after", "before", "about", "into", "over", "more", "than", "been", "being",
    "says", "said", "say", "via", "amp", "how", "why", "get", "got", "one", "two",
}


def _tokens(text: str) -> set[str]:
    """Значимые слова твита: без ссылок, коротких слов и служебных."""
    clean = URL_RE.sub("", text.lower())
    return {w for w in TOKEN_RE.findall(clean) if len(w) > 2 and w not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Доля общих слов: 0 — ничего общего, 1 — наборы совпадают."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def group_similar(
    tweets: list[dict],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[list[dict]]:
    """
    Разбивает твиты на группы об одном событии.

    Порядок входного списка сохраняется, поэтому если он отсортирован по разгону,
    первым в каждой группе окажется самый быстро растущий твит — его и стоит брать
    представителем.
    """
    clusters: list[tuple[set[str], list[dict]]] = []

    for tweet in tweets:
        tokens = _tokens(tweet.get("text") or "")
        for cluster_tokens, members in clusters:
            if _jaccard(tokens, cluster_tokens) >= threshold:
                members.append(tweet)
                break
        else:
            clusters.append((tokens, [tweet]))

    groups = [members for _, members in clusters]
    merged = sum(len(g) - 1 for g in groups)
    if merged:
        logger.info(
            f"Cluster: {len(tweets)} твитов свёрнуты в {len(groups)} сюжетов "
            f"(схлопнуто дублей: {merged})"
        )
    return groups
