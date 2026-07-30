"""
media_filter.py — фильтр "есть нормальное фото/видео".
"""


def has_valid_media(tweet: dict) -> bool:
    """
    True, если у твита есть media_urls, и это не HLS-поток (.m3u8),
    а полноценный файл (фото или mp4-видео).
    """
    media_urls = tweet.get("media_urls") or []
    if not media_urls:
        return False

    media_type = tweet.get("media_type")

    if media_type == "video":
        # отсекаем чистые HLS-плейлисты без реального mp4
        has_real_video = any(not url.lower().endswith(".m3u8") for url in media_urls)
        return has_real_video

    if media_type == "photo":
        return True

    return False
