"""
scraper.py — получение твитов через twscrape (без официального API Twitter).
"""
import os
import logging
from twscrape import API, gather

logger = logging.getLogger(__name__)

ACCOUNTS_DB = "accounts.db"

_api: API | None = None


async def get_api() -> API:
    """Возвращает готовый API twscrape (логин один раз, сессия кэшируется в accounts.db)."""
    global _api
    if _api is not None:
        return _api

    api = API(ACCOUNTS_DB)
    username = os.environ["TWITTER_USERNAME"]
    cookies = os.environ.get("TWITTER_COOKIES", "").strip()

    account = await api.pool.get_account(username)

    if cookies:
        # Куки из браузера: X блокирует программный вход, поэтому сессию берём готовую.
        if account is None or not account.active:
            await api.pool.delete_accounts(username)
            await api.pool.add_account_cookies(username, cookies)
            logger.info(f"twscrape: аккаунт @{username} добавлен по кукам")
    else:
        if not os.environ.get("TWITTER_PASSWORD"):
            raise RuntimeError(
                "Нет ни TWITTER_COOKIES, ни TWITTER_PASSWORD. "
                "Обнови куки: войди в x.com в браузере, скопируй auth_token и ct0 "
                "из DevTools и положи в секрет TWITTER_COOKIES."
            )
        if account is None:
            await api.pool.add_account(
                username,
                os.environ["TWITTER_PASSWORD"],
                os.environ["TWITTER_EMAIL"],
                os.environ.get("TWITTER_EMAIL_PASSWORD", ""),
            )
            logger.info(f"twscrape: аккаунт @{username} добавлен в пул")
        await api.pool.login_all()
        logger.info("twscrape: логин выполнен, сессия сохранена в accounts.db")

    _api = api
    return _api


MAX_VIDEO_BYTES = 18 * 1024 * 1024  # Telegram принимает до 20 МБ при отправке по URL


def _pick_variant(video):
    """
    Вариант с наибольшим битрейтом, который уложится в лимит Telegram.
    Размер оцениваем как битрейт × длительность — без лишних сетевых запросов.
    """
    duration_s = (video.duration or 0) / 1000
    ranked = sorted(
        (v for v in video.variants if v.url),
        key=lambda v: v.bitrate or 0,
        reverse=True,
    )
    for v in ranked:
        if duration_s and (v.bitrate or 0) * duration_s / 8 > MAX_VIDEO_BYTES:
            continue
        return v
    return ranked[-1] if ranked else None  # всё крупное — берём самый лёгкий


def _extract_media(tweet) -> tuple[list[str], str | None]:
    """Достаёт media_urls и media_type ('photo'/'video') из объекта твита twscrape."""
    media = getattr(tweet, "media", None)
    if media is None:
        return [], None

    # Видео приоритетнее фото: у twscrape в variants уже только mp4 (с bitrate)
    videos: list[str] = []
    for video in media.videos or []:
        best = _pick_variant(video)
        if best:
            videos.append(best.url)

    for gif in media.animated or []:
        if gif.videoUrl:
            videos.append(gif.videoUrl)

    if videos:
        return videos, "video"

    photos = [p.url for p in (media.photos or []) if p.url]
    if photos:
        return photos, "photo"

    return [], None


async def get_recent_tweets(handle: str, count: int) -> list[dict]:
    """
    Возвращает список твитов аккаунта handle (без @).
    Каждый твит: tweet_id, text, likes, retweets, media_urls, media_type, created_at, url.
    При ошибке — логирует и возвращает пустой список (не прерывает пайплайн).
    """
    try:
        api = await get_api()
        user = await api.user_by_login(handle)
        if user is None:
            logger.error(f"@{handle}: аккаунт не найден")
            return []

        tweets = await gather(api.user_tweets(user.id, limit=count))

        result = []
        for tweet in tweets:
            media_urls, media_type = _extract_media(tweet)
            result.append({
                "tweet_id": str(tweet.id),
                "text": tweet.rawContent or "",
                "likes": tweet.likeCount or 0,
                "retweets": tweet.retweetCount or 0,
                "media_urls": media_urls,
                "media_type": media_type,
                "created_at": str(tweet.date),
                "url": tweet.url,
                "account": handle,
            })
        logger.info(f"@{handle}: получено {len(result)} твитов")
        return result

    except Exception as e:
        logger.error(f"@{handle}: ошибка при получении твитов — {e}")
        return []
