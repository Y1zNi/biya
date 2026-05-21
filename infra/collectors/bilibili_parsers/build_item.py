"""B 站视频详情 API → CollectResultItem."""

from __future__ import annotations

from typing import Any, Dict

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.bilibili_parsers.opus_html import get_opus_id_from_state
from infra.collectors.bilibili_parsers.time_util import format_publish_time
from infra.collectors.bilibili_parsers.url import VideoUrlInfo
from infra.collectors.douyin_parsers import number_format

MEDIA_TYPE_VIDEO = '视频'
MEDIA_TYPE_OPUS = '图文'


def _pick_view(detail: Dict[str, Any]) -> Dict[str, Any]:
  view = detail.get('View')
  return view if isinstance(view, dict) else {}


def _pick_stat(view: Dict[str, Any]) -> Dict[str, Any]:
  stat = view.get('stat')
  return stat if isinstance(stat, dict) else {}


def _pick_owner(view: Dict[str, Any]) -> Dict[str, Any]:
  owner = view.get('owner')
  return owner if isinstance(owner, dict) else {}


def build_item_from_detail(
  link: str,
  platform_name: str,
  detail: Dict[str, Any],
  info: VideoUrlInfo,
) -> CollectResultItem:
  view = _pick_view(detail)
  stat = _pick_stat(view)
  owner = _pick_owner(view)

  bvid = str(view.get('bvid') or info.bvid or '').strip()
  aid = str(view.get('aid') or info.aid or '').strip()
  note_id = bvid or (f'av{aid}' if aid else '-')
  canonical = (
    f'https://www.bilibili.com/video/{bvid}' if bvid
    else (f'https://www.bilibili.com/video/av{aid}' if aid else link)
  )

  return CollectResultItem(
    link=canonical,
    platform_id='bilibili',
    platform_name=platform_name,
    author_name=str(owner.get('name') or '').strip() or '-',
    note_id=note_id,
    author_id=str(owner.get('mid') or '').strip() or '-',
    publish_time=format_publish_time(view.get('pubdate')),
    views=number_format.format_metric(stat.get('view')),
    likes=number_format.format_metric(stat.get('like')),
    favorites=number_format.format_metric(stat.get('favorite')),
    comments=number_format.format_metric(stat.get('reply')),
    shares=number_format.format_metric(stat.get('share')),
    coins=number_format.format_metric(stat.get('coin')),
    media_type=MEDIA_TYPE_VIDEO,
    status=CollectRowStatus.FAILED,
  )


def _opus_stat_count(stat: Dict[str, Any], key: str) -> Any:
  block = stat.get(key)
  if not isinstance(block, dict):
    return None
  return block.get('count')


def build_item_from_opus(
  link: str,
  platform_name: str,
  state: Dict[str, Any],
  info: VideoUrlInfo,
  *,
  author: Dict[str, Any],
  stat: Dict[str, Any],
) -> CollectResultItem:
  opus_id = get_opus_id_from_state(state, info.opus_id)
  canonical = info.build_canonical_opus_url() or link
  if opus_id and not canonical:
    canonical = f'https://www.bilibili.com/opus/{opus_id}'

  pub_raw = author.get('pub_ts') or author.get('pub_time')

  return CollectResultItem(
    link=canonical,
    platform_id='bilibili',
    platform_name=platform_name,
    author_name=str(author.get('name') or '').strip() or '-',
    note_id=opus_id or '-',
    author_id=str(author.get('mid') or '').strip() or '-',
    publish_time=format_publish_time(pub_raw),
    views='-',
    likes=number_format.format_metric(_opus_stat_count(stat, 'like')),
    favorites=number_format.format_metric(_opus_stat_count(stat, 'favorite')),
    comments=number_format.format_metric(_opus_stat_count(stat, 'comment')),
    shares=number_format.format_metric(_opus_stat_count(stat, 'forward')),
    coins=number_format.format_metric(_opus_stat_count(stat, 'coin')),
    media_type=MEDIA_TYPE_OPUS,
    status=CollectRowStatus.FAILED,
  )


def has_meaningful_metrics(item: CollectResultItem) -> bool:
  fields = (
    item.views,
    item.likes,
    item.favorites,
    item.comments,
    item.shares,
    item.coins,
    item.publish_time,
  )
  return any(value not in ('-', '', '0') for value in fields)


def is_collect_success(item: CollectResultItem) -> bool:
  author_ok = bool((item.author_name or '').strip() not in ('', '-'))
  return has_meaningful_metrics(item) or author_ok


def finalize_item(item: CollectResultItem) -> CollectResultItem:
  if is_collect_success(item):
    item.status = CollectRowStatus.SUCCESS
    item.error_msg = ''
  elif not item.error_msg:
    if item.media_type == MEDIA_TYPE_OPUS:
      item.error_msg = '未能获取 B 站图文互动数据'
    else:
      item.error_msg = '未能获取 B 站视频互动数据'
  return item
