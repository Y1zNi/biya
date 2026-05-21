"""微信视频号 feed 详情 → CollectResultItem."""

from __future__ import annotations

from typing import Any, Dict

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.bilibili_parsers.time_util import format_publish_time
from infra.collectors.channels_parsers.url import ChannelsUrlInfo, build_canonical_link
from infra.collectors.douyin_parsers import number_format

MEDIA_TYPE_VIDEO = '视频'
MEDIA_TYPE_IMAGE = '图片'

INVALID_AUTHOR_NAMES = frozenset({
  '登录',
  '注册',
  '视频号助手',
  '微信',
})


def _pick_author(data: Dict[str, Any]) -> Dict[str, Any]:
  author = data.get('authorInfo')
  return author if isinstance(author, dict) else {}


def _pick_feed(data: Dict[str, Any]) -> Dict[str, Any]:
  feed = data.get('feedInfo')
  return feed if isinstance(feed, dict) else {}


def _format_metric(raw: Any) -> str:
  if isinstance(raw, (int, float)):
    return number_format.format_metric(raw)
  text = str(raw).strip() if raw is not None else ''
  if not text:
    return number_format.format_metric(None)
  if text.isdigit():
    return number_format.format_metric(int(text))
  return text


def is_plausible_author(name: str) -> bool:
  text = (name or '').strip()
  if not text or text == '-':
    return False
  if text in INVALID_AUTHOR_NAMES:
    return False
  return len(text) >= 2


def has_meaningful_metrics(item: CollectResultItem) -> bool:
  fields = (
    item.likes,
    item.favorites,
    item.comments,
    item.shares,
    item.publish_time,
    item.media_type,
  )
  return any(value not in ('-', '', '0') for value in fields)


def is_collect_success(item: CollectResultItem) -> bool:
  return has_meaningful_metrics(item) or is_plausible_author(item.author_name)


def infer_media_type(feed: Dict[str, Any]) -> str:
  pic_info = feed.get('picInfo')
  if isinstance(pic_info, list) and len(pic_info) > 0:
    return MEDIA_TYPE_IMAGE
  return MEDIA_TYPE_VIDEO


def build_item_from_feed(
  link: str,
  platform_name: str,
  data: Dict[str, Any],
  info: ChannelsUrlInfo,
) -> CollectResultItem:
  author = _pick_author(data)
  feed = _pick_feed(data)

  canonical = info.canonical_link or build_canonical_link(info.short_uri) or link

  return CollectResultItem(
    link=canonical,
    platform_id='channels',
    platform_name=platform_name,
    author_name=str(author.get('nickname') or '').strip() or '-',
    publish_time=format_publish_time(feed.get('createtime')),
    views='-',
    likes=_format_metric(feed.get('likeCountFmt')),
    favorites=_format_metric(feed.get('favCountFmt')),
    comments=_format_metric(feed.get('commentCountFmt')),
    shares=_format_metric(feed.get('forwardCountFmt')),
    media_type=infer_media_type(feed),
    status=CollectRowStatus.FAILED,
  )


def finalize_item(item: CollectResultItem) -> CollectResultItem:
  if is_collect_success(item):
    item.status = CollectRowStatus.SUCCESS
    item.error_msg = ''
  elif not item.error_msg:
    item.error_msg = '未能获取视频号互动数据'
  return item
