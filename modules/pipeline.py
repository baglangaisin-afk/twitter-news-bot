"""
pipeline.py — оркестрация всего процесса сбора и обработки твитов.

Аккаунты обходятся группами: собрали группу — отсортировали по разгону — свернули
в сюжеты — сразу отправили, и только потом взялись за следующую. Так первые посты
уходят через пару минут, а не после обхода всего списка.
"""
import os
import json
import logging
import asyncio
from datetime import datetime, timezone

from telegram import Bot

from modules.scraper import get_recent_tweets
from modules.ranker import rank_candidates
from modules.cluster import group_similar
from modules.media_filter import has_valid_media
from modules.dedup import is_already_sent, mark_as_sent
from modules.ai_rewrite import rewrite_tweet
from modules.telegram_sender import send_post

logger = logging.getLogger(__name__)

ACCOUNTS_PATH = "config/accounts.json"


def _load_accounts() -> list[str]:
    with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def _process_cluster(bot: Bot, chat_id: str, cluster: list[dict], delay: float) -> bool:
    """
    Отправляет один пост на сюжет.

    Берёт самый быстро растущий твит группы с пригодным медиа, а остальные версии
    помечает отправленными — иначе та же новость от другого издания всплывёт
    следующим прогоном.
    Возвращает True, если пост ушёл в канал.
    """
    # Если любую версию сюжета уже отправляли — новость освещена, пропускаем целиком
    for tweet in cluster:
        if await asyncio.to_thread(is_already_sent, tweet["tweet_id"]):
            logger.info(f"Сюжет: пропуск — твит {tweet['tweet_id']} уже отправлялся")
            return False

    chosen = next((t for t in cluster if has_valid_media(t)), None)
    if chosen is None:
        logger.info(f"Сюжет {cluster[0]['tweet_id']}: пропуск — ни у одной версии нет медиа")
        return False

    await asyncio.sleep(delay)

    rewritten = await asyncio.to_thread(rewrite_tweet, chosen["text"])
    if rewritten is None:
        logger.info(f"Сюжет {chosen['tweet_id']}: пропуск — SKIP или ошибка AI")
        return False

    success = await send_post(
        bot=bot,
        chat_id=chat_id,
        caption=rewritten,
        media_url=chosen["media_urls"][0],
        media_type=chosen["media_type"],
        source_url=chosen["url"],
    )

    if not success:
        logger.error(f"Сюжет {chosen['tweet_id']}: отправка не удалась")
        return False

    sent_at = datetime.now(timezone.utc).isoformat()
    for tweet in cluster:
        await asyncio.to_thread(mark_as_sent, tweet["tweet_id"], tweet["account"], sent_at)

    extra = len(cluster) - 1
    logger.info(
        f"Сюжет {chosen['tweet_id']}: отправлен успешно"
        + (f", схлопнуто версий: {extra}" if extra else "")
    )
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
    similarity = float(os.environ.get("CLUSTER_THRESHOLD", 0.45))
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

        # 2. Отбор внутри группы: по убыванию скорости набора лайков
        candidates = rank_candidates(batch_tweets, min_likes, max_age_hours)

        # 3. Свёртка версий одной новости в сюжеты
        clusters = group_similar(candidates, similarity)
        logger.info(
            f"Pipeline: группа {batch_no} — собрано {len(batch_tweets)} твитов, "
            f"кандидатов {len(candidates)}, сюжетов {len(clusters)}"
        )

        # 4. Отправка сразу, не дожидаясь остальных групп
        for cluster in clusters:
            if sent_count >= max_posts:
                break
            try:
                if await _process_cluster(bot, chat_id, cluster, delay):
                    sent_count += 1
            except Exception as e:
                logger.error(
                    f"Pipeline: ошибка при обработке сюжета {cluster[0].get('tweet_id')} — {e}"
                )
                continue

    logger.info(f"Pipeline: завершено, отправлено {sent_count} постов")
    return sent_count
