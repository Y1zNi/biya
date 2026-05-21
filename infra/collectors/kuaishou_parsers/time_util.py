"""快手发布时间（页面 DOM 原文 / 毫秒时间戳）."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

CHINA_TZ = timezone(timedelta(hours=8))


def format_dom_photo_time(raw: Any) -> str:
  """页面 .photo-time 文案原样保留，如 2月前、3天前."""
  text = str(raw or '').strip()
  return text if text else '-'


def format_publish_time(raw: Any) -> str:
  """H5 INIT_STATE 的 timestamp（毫秒）等."""
  if raw is None:
    return '-'
  if isinstance(raw, (int, float)):
    try:
      ts = int(raw)
      if ts <= 0:
        return '-'
      if ts > 1_000_000_000_000:
        ts = ts // 1000
      return datetime.fromtimestamp(ts, tz=CHINA_TZ).strftime('%Y-%m-%d %H:%M')
    except (OSError, OverflowError, ValueError):
      return '-'
  text = str(raw).strip()
  return text if text else '-'
