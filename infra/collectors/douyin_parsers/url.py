"""抖音链接解析与规范化."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

_AWEME_PATH_PATTERNS = (
  re.compile(r'/video/(\d+)', re.I),
  re.compile(r'/note/(\d+)', re.I),
  re.compile(r'/gallery/(\d+)', re.I),
)

_QUERY_ID_KEYS = ('modal_id', 'aweme_id', 'awemeid', 'item_id', 'group_id')


def extract_aweme_id(url: str) -> Optional[str]:
  """从抖音链接中提取作品 aweme_id（含 jingxuan?modal_id=）."""
  text = (url or '').strip()
  if not text:
    return None

  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  parsed = urlparse(text)
  query = parse_qs(parsed.query)
  for key in _QUERY_ID_KEYS:
    values = query.get(key) or query.get(key.lower())
    if values and str(values[0]).strip().isdigit():
      return str(values[0]).strip()

  path = parsed.path or ''
  for pattern in _AWEME_PATH_PATTERNS:
    match = pattern.search(path)
    if match:
      return match.group(1)

  return None


def normalize_collect_url(url: str) -> str:
  """将精选弹层等链接规范为作品详情页，便于稳定解析 RENDER_DATA."""
  text = (url or '').strip()
  if not text:
    return text

  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  aweme_id = extract_aweme_id(text)
  if not aweme_id:
    return text

  lower = text.lower()
  if '/jingxuan' in lower or 'modal_id=' in lower:
    return f'https://www.douyin.com/video/{aweme_id}'

  return text
