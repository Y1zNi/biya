"""微博时间格式转换."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

CHINA_TZ = timezone(timedelta(hours=8))
RFC2822_FORMAT = '%a %b %d %H:%M:%S %z %Y'


def rfc2822_to_china_datetime(rfc2822_time: str) -> Optional[datetime]:
  text = (rfc2822_time or '').strip()
  if not text:
    return None
  try:
    dt_object = datetime.strptime(text, RFC2822_FORMAT)
    return dt_object.astimezone(CHINA_TZ)
  except ValueError:
    return None


def format_publish_time(raw: Any) -> str:
  if raw is None:
    return '-'
  if isinstance(raw, str):
    dt = rfc2822_to_china_datetime(raw)
    if dt:
      return dt.strftime('%Y-%m-%d %H:%M')
    text = raw.strip()
    return text if text else '-'
  return '-'
