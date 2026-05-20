"""快手链接解析与规范化."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

_PHOTO_PATH_PATTERNS = (
  re.compile(r'/short-video/([^/?#]+)', re.I),
  re.compile(r'/photo/([^/?#]+)', re.I),
  re.compile(r'/f/([^/?#]+)', re.I),
)

_QUERY_ID_KEYS = ('photoId', 'photo_id', 'shareObjectId', 'shareObjectid')


def extract_photo_id(url: str) -> Optional[str]:
  """从快手作品链接中提取 photoId."""
  text = (url or '').strip()
  if not text:
    return None

  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  parsed = urlparse(text)
  query = parse_qs(parsed.query)
  for key in _QUERY_ID_KEYS:
    values = query.get(key) or query.get(key.lower())
    if values and str(values[0]).strip():
      return str(values[0]).strip()

  path = parsed.path or ''
  for pattern in _PHOTO_PATH_PATTERNS:
    match = pattern.search(path)
    if match:
      photo_id = match.group(1).strip()
      if photo_id:
        return photo_id

  return None


def normalize_collect_url(url: str) -> str:
  """将作品链接规范为 PC 短剧详情页."""
  text = (url or '').strip()
  if not text:
    return text

  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  photo_id = extract_photo_id(text)
  if not photo_id:
    return text

  lower = text.lower()
  if '/short-video/' not in lower and photo_id:
    return f'https://www.kuaishou.com/short-video/{photo_id}'

  return text
