"""笔记 dict → CollectResultItem."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.douyin_parsers import number_format
from infra.collectors.xiaohongshu_parsers.url import NoteUrlInfo, build_explore_url


def _pick_dict(obj: Any, *keys: str) -> Dict[str, Any]:
  if not isinstance(obj, dict):
    return {}
  for key in keys:
    value = obj.get(key)
    if isinstance(value, dict):
      return value
  return {}


def _pick_str(obj: Dict[str, Any], *keys: str) -> str:
  for key in keys:
    value = obj.get(key)
    if value is not None and str(value).strip() not in ('', 'None'):
      return str(value).strip()
  return ''


def format_publish_time(raw: Any) -> str:
  if raw is None or raw == '':
    return '-'
  try:
    ts = int(raw)
  except (TypeError, ValueError):
    return '-'
  if ts > 1_000_000_000_000:
    ts = ts // 1000
  try:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
  except (OSError, OverflowError, ValueError):
    return '-'


def map_media_type(note_type: str) -> str:
  text = (note_type or '').strip().lower()
  if text == 'video':
    return '视频'
  if text in ('normal', 'image', 'multi'):
    return '图文'
  return '图文' if text else '-'


def build_item_from_note(
  link: str,
  platform_name: str,
  note: Dict[str, Any],
  info: NoteUrlInfo,
) -> CollectResultItem:
  user = note.get('user') or note.get('User') or {}
  if not isinstance(user, dict):
    user = {}
  interact = note.get('interact_info') or note.get('interactInfo') or {}
  if not isinstance(interact, dict):
    interact = {}

  note_id = _pick_str(note, 'note_id', 'noteId') or info.note_id or '-'
  author_id = _pick_str(user, 'user_id', 'userId') or '-'
  author_name = _pick_str(user, 'nickname', 'nickName', 'name') or '-'
  publish_time = format_publish_time(note.get('time') or note.get('last_update_time'))

  views_raw = (
    interact.get('view_count')
    or interact.get('viewCount')
    or interact.get('read_count')
    or interact.get('readCount')
  )
  views = number_format.format_count(views_raw) if views_raw is not None else '-'

  likes = number_format.format_count(
    interact.get('liked_count') or interact.get('likedCount'),
  )
  favorites = number_format.format_count(
    interact.get('collected_count') or interact.get('collectedCount'),
  )
  comments = number_format.format_count(
    interact.get('comment_count') or interact.get('commentCount'),
  )
  shares = number_format.format_count(
    interact.get('share_count') or interact.get('shareCount'),
  )

  final_link = link.strip() or build_explore_url(info)

  return CollectResultItem(
    link=final_link,
    platform_id='xiaohongshu',
    platform_name=platform_name,
    author_name=author_name,
    note_id=note_id,
    author_id=author_id,
    publish_time=publish_time,
    views=views,
    likes=likes,
    favorites=favorites,
    comments=comments,
    shares=shares,
    media_type=map_media_type(_pick_str(note, 'type')),
    status=CollectRowStatus.FAILED,
  )


def is_plausible_author(name: str) -> bool:
  text = (name or '').strip()
  if not text or text == '-':
    return False
  skip = frozenset({'登录', '注册', '小红书', '我', '发现', '发布'})
  return text not in skip and len(text) >= 2


def has_meaningful_metrics(item: CollectResultItem) -> bool:
  fields = (item.views, item.likes, item.comments, item.favorites, item.shares)
  return any(value not in ('-', '', '0') for value in fields)


def is_collect_success(item: CollectResultItem) -> bool:
  if item.note_id and item.note_id != '-':
    if is_plausible_author(item.author_name) or has_meaningful_metrics(item):
      return True
  return has_meaningful_metrics(item) or is_plausible_author(item.author_name)


def finalize_item(item: CollectResultItem) -> CollectResultItem:
  if is_collect_success(item):
    item.status = CollectRowStatus.SUCCESS
    item.error_msg = ''
  elif not item.error_msg:
    item.error_msg = '未能获取作品数据（请确认链接含 xsec_token 且账号已登录）'
  return item
