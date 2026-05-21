"""mblog → CollectResultItem."""

from __future__ import annotations

import re
from typing import Any, Dict

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.douyin_parsers import number_format
from infra.collectors.weibo_parsers.time_util import format_publish_time
from infra.collectors.weibo_parsers.url import NoteUrlInfo


def _pick_user(mblog: Dict[str, Any]) -> Dict[str, Any]:
  user = mblog.get('user')
  return user if isinstance(user, dict) else {}


def build_item_from_mblog(
  link: str,
  platform_name: str,
  mblog: Dict[str, Any],
  info: NoteUrlInfo,
) -> CollectResultItem:
  user = _pick_user(mblog)
  note_id = str(mblog.get('id') or info.note_id or '').strip()
  author_name = str(user.get('screen_name') or user.get('name') or '').strip() or '-'
  publish_time = format_publish_time(mblog.get('created_at'))

  return CollectResultItem(
    link=f'https://m.weibo.cn/detail/{note_id}' if note_id else link,
    platform_id='weibo',
    platform_name=platform_name,
    author_name=author_name,
    publish_time=publish_time,
    views='-',
    likes=number_format.format_metric(mblog.get('attitudes_count')),
    favorites='-',
    comments=number_format.format_metric(mblog.get('comments_count')),
    shares=number_format.format_metric(mblog.get('reposts_count')),
    media_type='-',
    status=CollectRowStatus.FAILED,
  )


def is_plausible_author(name: str) -> bool:
  text = (name or '').strip()
  if not text or text == '-':
    return False
  skip = frozenset({'登录', '注册', '微博', '首页', '关注', '热门'})
  return text not in skip and len(text) >= 2


def has_meaningful_metrics(item: CollectResultItem) -> bool:
  fields = (item.likes, item.comments, item.shares, item.publish_time, item.media_type)
  return any(value not in ('-', '', '0') for value in fields)


def is_collect_success(item: CollectResultItem) -> bool:
  return has_meaningful_metrics(item) or is_plausible_author(item.author_name)


def finalize_item(item: CollectResultItem) -> CollectResultItem:
  item.views = '-'
  item.favorites = '-'
  if is_collect_success(item):
    item.status = CollectRowStatus.SUCCESS
    item.error_msg = ''
  elif not item.error_msg:
    item.error_msg = '未能获取微博互动数据（点赞、评论、转发等均为空）'
  return item


def parse_nickname_from_title(html: str) -> str:
  match = re.search(r'<title>\s*(.+?)的微博\s*</title>', html or '', re.I)
  if match:
    return match.group(1).strip()
  return ''
