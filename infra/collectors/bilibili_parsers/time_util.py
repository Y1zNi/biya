"""B 站时间格式转换."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

CHINA_TZ = timezone(timedelta(hours=8))


def format_publish_time(raw: Any) -> str:
  if raw is None:
    return '-'
  if isinstance(raw, (int, float)):
    try:
      ts = int(raw)
      if ts <= 0:
        return '-'
      return datetime.fromtimestamp(ts, tz=CHINA_TZ).strftime('%Y-%m-%d %H:%M')
    except (OSError, OverflowError, ValueError):
      return '-'
  text = str(raw).strip()
  return text if text else '-'
