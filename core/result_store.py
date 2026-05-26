"""CollectResultItem 与 DB payload_json 序列化."""

from __future__ import annotations

import json
from typing import Any, Optional

from core.models import CollectResultItem, CollectRowStatus


def item_to_json(item: CollectResultItem) -> str:
  payload: dict[str, Any] = {
    'link': item.link,
    'platform_id': item.platform_id,
    'platform_name': item.platform_name,
    'author_name': item.author_name,
    'note_id': item.note_id,
    'author_id': item.author_id,
    'author_sec_uid': item.author_sec_uid,
    'douyin_id': item.douyin_id,
    'publish_time': item.publish_time,
    'views': item.views,
    'likes': item.likes,
    'favorites': item.favorites,
    'comments': item.comments,
    'shares': item.shares,
    'coins': item.coins,
    'media_type': item.media_type,
    'status': item.status.value if isinstance(item.status, CollectRowStatus) else str(item.status),
    'error_msg': item.error_msg,
  }
  return json.dumps(payload, ensure_ascii=False)


def item_from_json(text: str) -> CollectResultItem:
  data = json.loads(text)
  status_raw = data.get('status', CollectRowStatus.FAILED.value)
  try:
    status = CollectRowStatus(status_raw)
  except ValueError:
    status = CollectRowStatus.FAILED
  return CollectResultItem(
    link=str(data.get('link', '')),
    platform_id=str(data.get('platform_id', '')),
    platform_name=str(data.get('platform_name', '')),
    author_name=str(data.get('author_name', '')),
    note_id=str(data.get('note_id', '-')),
    author_id=str(data.get('author_id', '-')),
    author_sec_uid=str(data.get('author_sec_uid', '-')),
    douyin_id=str(data.get('douyin_id', '-')),
    publish_time=str(data.get('publish_time', '-')),
    views=str(data.get('views', '-')),
    likes=str(data.get('likes', '-')),
    favorites=str(data.get('favorites', '-')),
    comments=str(data.get('comments', '-')),
    shares=str(data.get('shares', '-')),
    coins=str(data.get('coins', '-')),
    media_type=str(data.get('media_type', '-')),
    status=status,
    error_msg=str(data.get('error_msg', '')),
  )


def item_from_db_row(row: Any) -> Optional[CollectResultItem]:
  """仅从 payload_json 解析；空或无效则返回 None."""
  raw = ''
  if hasattr(row, 'keys') and 'payload_json' in row.keys():
    raw = row['payload_json'] or ''
  elif isinstance(row, dict):
    raw = row.get('payload_json') or ''
  text = str(raw).strip()
  if not text:
    return None
  try:
    return item_from_json(text)
  except (json.JSONDecodeError, TypeError, ValueError):
    return None
