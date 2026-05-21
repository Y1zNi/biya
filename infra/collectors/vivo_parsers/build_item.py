"""threadData → CollectResultItem."""

from __future__ import annotations

from typing import Any, Dict

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.douyin_parsers import number_format
from infra.collectors.vivo_parsers.time_util import format_publish_time
from infra.collectors.vivo_parsers.url import ThreadUrlInfo

MEDIA_TYPE_VIDEO = '视频'
MEDIA_TYPE_IMAGE = '图文'


def _pick_author(thread_data: Dict[str, Any]) -> Dict[str, Any]:
  author = thread_data.get('author')
  return author if isinstance(author, dict) else {}


def _pick_share(thread_data: Dict[str, Any]) -> Dict[str, Any]:
  share = thread_data.get('shareDto')
  return share if isinstance(share, dict) else {}


def _resolve_media_type(thread_data: Dict[str, Any]) -> str:
  if thread_data.get('containsVideo') is True:
    return MEDIA_TYPE_VIDEO
  video_dtos = thread_data.get('videoDtos')
  if isinstance(video_dtos, list) and video_dtos:
    return MEDIA_TYPE_VIDEO
  images = thread_data.get('images')
  if isinstance(images, list) and images:
    return MEDIA_TYPE_IMAGE
  return '-'


def _resolve_link(thread_data: Dict[str, Any], info: ThreadUrlInfo, fallback: str) -> str:
  share = _pick_share(thread_data)
  share_url = str(share.get('shareUrl') or '').strip()
  if share_url:
    return share_url.rstrip('?')
  if info.is_thread:
    return info.build_canonical_url()
  return fallback


def build_item_from_thread(
  link: str,
  platform_name: str,
  thread_data: Dict[str, Any],
  info: ThreadUrlInfo,
) -> CollectResultItem:
  author = _pick_author(thread_data)
  tid = str(thread_data.get('tid') or info.tid or '').strip()
  author_name = str(author.get('bbsName') or '').strip() or '-'

  return CollectResultItem(
    link=_resolve_link(thread_data, info, link),
    platform_id='vivo',
    platform_name=platform_name,
    author_name=author_name,
    note_id=tid or '-',
    author_id=str(author.get('openId') or author.get('uid') or '').strip() or '-',
    publish_time=format_publish_time(thread_data.get('publish')),
    views=number_format.format_metric(thread_data.get('views')),
    likes=number_format.format_metric(thread_data.get('likes')),
    favorites=number_format.format_metric(thread_data.get('favorites')),
    comments=number_format.format_metric(thread_data.get('comments')),
    shares='-',
    media_type=_resolve_media_type(thread_data),
    status=CollectRowStatus.FAILED,
  )


def has_meaningful_metrics(item: CollectResultItem) -> bool:
  fields = (
    item.views,
    item.likes,
    item.favorites,
    item.comments,
    item.publish_time,
    item.media_type,
  )
  return any(value not in ('-', '', '0') for value in fields)


def is_plausible_author(name: str) -> bool:
  text = (name or '').strip()
  if not text or text == '-':
    return False
  skip = frozenset({'登录', '注册', '立即登录', '个人中心'})
  return text not in skip and len(text) >= 2


def is_collect_success(item: CollectResultItem) -> bool:
  return has_meaningful_metrics(item) or is_plausible_author(item.author_name)


def _resolve_club_media_type(data: Dict[str, Any]) -> str:
  if data.get('hasVideo') is True:
    return MEDIA_TYPE_VIDEO
  if data.get('hasImage') is True:
    return MEDIA_TYPE_IMAGE
  return '-'


def build_item_from_club(
  canonical_url: str,
  platform_name: str,
  data: Dict[str, Any],
  tid: str,
) -> CollectResultItem:
  user = data.get('user')
  user = user if isinstance(user, dict) else {}
  author_name = str(user.get('nickname') or '').strip() or '-'
  note_id = str(data.get('id') or tid or '').strip()
  publish_raw = data.get('postedAt') or data.get('createdAt')

  return CollectResultItem(
    link=canonical_url,
    platform_id='vivo',
    platform_name=platform_name,
    author_name=author_name,
    note_id=note_id or '-',
    author_id=str(user.get('code') or user.get('username') or '').strip() or '-',
    publish_time=format_publish_time(publish_raw),
    views=number_format.format_metric(data.get('viewCount')),
    likes=number_format.format_metric(data.get('likeCount')),
    favorites=number_format.format_metric(data.get('favoriteCount')),
    comments=number_format.format_metric(data.get('postCount')),
    shares=number_format.format_metric(data.get('shareCount')),
    media_type=_resolve_club_media_type(data),
    status=CollectRowStatus.FAILED,
  )


def finalize_item(item: CollectResultItem) -> CollectResultItem:
  if is_collect_success(item):
    item.status = CollectRowStatus.SUCCESS
    item.error_msg = ''
  elif not item.error_msg:
    item.error_msg = '未能获取帖子互动数据'
  return item
