"""抖音发布时间格式转换."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

CHINA_TZ = timezone(timedelta(hours=8))


def format_publish_time(raw: Any) -> str:
  """aweme.create_time 等 Unix 时间戳 → 本地展示."""
  if raw is None or raw == '':
    return '-'
  try:
    ts = int(raw)
  except (TypeError, ValueError):
    return '-'
  if ts <= 0:
    return '-'
  if ts > 1_000_000_000_000:
    ts = ts // 1000
  try:
    return datetime.fromtimestamp(ts, tz=CHINA_TZ).strftime('%Y-%m-%d %H:%M')
  except (OSError, OverflowError, ValueError):
    return '-'


def _infer_year(month: int, day: int, now: datetime) -> int:
  year = now.year
  try:
    candidate = datetime(year, month, day)
  except ValueError:
    return year
  if candidate.date() > now.date():
    return year - 1
  return year


def format_dom_publish_time(raw: Any) -> str:
  """页面 .video-create-time 文案，如 · 3月5日."""
  text = str(raw or '').strip().lstrip('·').strip()
  if not text:
    return '-'

  if re.match(r'\d{4}-\d{2}-\d{2}', text):
    return text

  now = datetime.now(tz=CHINA_TZ)

  full = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
  if full:
    year, month, day = (int(full.group(i)) for i in range(1, 4))
    return f'{year}-{month:02d}-{day:02d} 00:00'

  month_day = re.match(r'(\d{1,2})月(\d{1,2})日', text)
  if month_day:
    month, day = int(month_day.group(1)), int(month_day.group(2))
    year = _infer_year(month, day, now)
    return f'{year}-{month:02d}-{day:02d} 00:00'

  if text.startswith('昨天'):
    target = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    time_match = re.search(r'(\d{1,2}):(\d{2})', text)
    if time_match:
      hour, minute = time_match.groups()
      return f'{target} {int(hour):02d}:{minute}'
    return f'{target} 00:00'

  if text.startswith('前天'):
    target = (now - timedelta(days=2)).strftime('%Y-%m-%d')
    return f'{target} 00:00'

  return text if text else '-'
