"""
dedup.py — дедупликация отправленных твитов через Google Sheets.
Лист: столбец A = tweet_id, B = account, C = sent_at.
"""
import os
import logging
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

_worksheet = None
_sent_ids_cache: set[str] | None = None


def _get_worksheet():
    global _worksheet
    if _worksheet is not None:
        return _worksheet

    creds_path = os.environ["GOOGLE_SHEETS_CREDENTIALS_PATH"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(sheet_id)
    _worksheet = sheet.sheet1
    return _worksheet


def _load_sent_ids() -> set[str]:
    global _sent_ids_cache
    if _sent_ids_cache is not None:
        return _sent_ids_cache

    try:
        ws = _get_worksheet()
        col_a = ws.col_values(1)  # включая возможный заголовок
        _sent_ids_cache = set(col_a)
    except Exception as e:
        logger.error(f"Dedup: не удалось загрузить список отправленных id — {e}")
        _sent_ids_cache = set()

    return _sent_ids_cache


def is_already_sent(tweet_id: str) -> bool:
    """True, если tweet_id уже есть в таблице."""
    return str(tweet_id) in _load_sent_ids()


def mark_as_sent(tweet_id: str, account: str, sent_at: str) -> None:
    """Дописывает новую строку в таблицу и обновляет локальный кэш."""
    try:
        ws = _get_worksheet()
        ws.append_row([str(tweet_id), account, sent_at])
        if _sent_ids_cache is not None:
            _sent_ids_cache.add(str(tweet_id))
        logger.info(f"Dedup: tweet_id={tweet_id} записан в таблицу")
    except Exception as e:
        logger.error(f"Dedup: не удалось записать tweet_id={tweet_id} — {e}")
