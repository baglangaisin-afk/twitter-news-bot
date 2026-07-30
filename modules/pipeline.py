"""
pipeline.py — оркестрация всего процесса сбора и обработки твитов.

Аккаунты обходятся группами: собрали группу — отсортировали по лайкам — сразу отправили,
и только потом взялись за следующую. Так первые посты уходят через пару минут,
а не после обхода всего списка.
"""
import os
import json
import logging
import asyncio
from datetime import datetime, timezone

from telegram import Bot

from modules.scraper import get_recent_tweets
from modules.ranker import rank_candidates
from modules.media_filter import has_valid_media
from modules.dedup import is_already_sent, mark_as_sent
from modules.ai_rewrite import rewrite_tweet
from modules.telegram_sender import send_post

logger = logging.getLogger(__name__)

ACCOUNTS_PATH = "config/accounts.json"


def _load_accounts() -> list[str]:
    with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def _process_tweet(bot: Bot, chat_id: str, tweet: dict, delay: float) -> bool:
    """
    Прогоняет один твит через фильтры и отправляет.
    Возвращает True, если пост ушёл в канал.
    """
    tweet_id = tweet["tweet_id"]

    if not has_valid_media(tweet):
        logger.info(f"Tweet {tweet_id}: пропуск — нет валидного медиа")
        return False

    if await asyncio.to_thread(is_already_sent, tweet_id):
        logger.info(f"Tweet {tweet_id}: пропуск — уже отправлялся")
        return False

    await asyncio.sleep(delay)

    rewritten = await asyncio.to_thread(rewrite_tweet, tweet["text"])
    if rewritten is None:
        logger.info(f"Tweet {tweet_id}: пропуск — SKIP или ошибка AI")
        return False

    success = await send_post(
        bot=bot,
        chat_id=chat_id,
        caption=rewritten,
        media_url=tweet["media_urls"][0],
        media_type=tweet["media_type"],
        source_url=tweet["url"],
    )

    if not success:
        logger.error(f"Tweet {tweet_id}: отправка не удалась")
        return False

    sent_at = datetime.now(timezone.utc).isoformat()
    await asyncio.to_thread(mark_as_sent, tweet_id, tweet["account"], sent_at)
    logger.info(f"Tweet {tweet_id}: отправлен успешно")
    return True


async def run_pipeline(bot: Bot) -> int:
    """
    Запускает полный цикл сбора/обработки/отправки.
    Возвращает количество успешно отправленных постов.
    """
    accounts = _load_accounts()
    tweets_per_account = int(os.environ.get("TWEETS_PER_ACCOUNT", 10))
    min_likes = int(os.environ.get("MIN_LIKES", 5000))
    max_age_hours = float(os.environ.get("MAX_AGE_HOURS", 48))
    max_posts = int(os.environ.get("MAX_POSTS_PER_RUN", 30))
    batch_size = int(os.environ.get("ACCOUNTS_PER_BATCH", 10))
    delay = float(os.environ.get("REQUEST_DELAY_SECONDS", 5))
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    sent_count = 0

    for start in range(0, len(accounts), batch_size):
        if sent_count >= max_posts:
            logger.info(f"Pipeline: достигнут потолок {max_posts} постов за прогон")
            break

        batch = accounts[start : start + batch_size]
        batch_no = start // batch_size + 1
        logger.info(f"Pipeline: группа {batch_no} — аккаунты {', '.join(batch)}")

        # 1. Сбор твитов по аккаунтам группы
        batch_tweets: list[dict] = []
        for handle in batch:
            batch_tweets.extend(await get_recent_tweets(handle, tweets_per_account))
            await asyncio.sleep(delay)

        # 2. Отбор внутри группы: от популярных к менее популярным
        candidates = rank_candidates(batch_tweets, min_likes, max_age_hours)
        logger.info(
            f"Pipeline: группа {batch_no} — собрано {len(batch_tweets)} твитов, "
            f"кандидатов {len(candidates)}"
        )

        # 3. Отправка сразу, не дожидаясь остальных групп
        for tweet in candidates:
            if sent_count >= max_posts:
                break
            try:
                if await _process_tweet(bot, chat_id, tweet, delay):
                    sent_count += 1
            except Exception as e:
                logger.error(
                    f"Pipeline: ошибка при обработке твита {tweet.get('tweet_id')} — {e}"
                )
                continue

    logger.info(f"Pipeline: завершено, отправлено {sent_count} постов")
    return sent_count
