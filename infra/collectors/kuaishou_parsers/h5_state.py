"""快手 H5 分享页（chenzhongtech）INIT_STATE 与推荐接口数据解析."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from playwright.async_api import Page, Response

from infra.collectors.douyin_parsers import number_format
from infra.collectors.kuaishou_parsers import ids as kuaishou_ids
from infra.collectors.kuaishou_parsers import render_data
from infra.collectors.kuaishou_parsers import time_util as kuaishou_time

_H5_PHOTO_API_MARKERS = ('/ugH5App/recommend/photos', '/recommend/photos')
_SHARE_INFO_PHOTO_RE = re.compile(r'(?:^|[?&])photoId=([^&]+)', re.I)


async def read_init_state(page: Page) -> Optional[Dict[str, Any]]:
  try:
    state = await page.evaluate('() => window.INIT_STATE || null')
    return state if isinstance(state, dict) else None
  except Exception:
    return None


def share_info_photo_id(photo: Dict[str, Any]) -> str:
  share_info = str(photo.get('share_info') or '').strip()
  if not share_info:
    return ''
  match = _SHARE_INFO_PHOTO_RE.search(share_info)
  return match.group(1).strip() if match else ''


def photo_matches_target_h5(photo: Dict[str, Any], target_photo_id: Optional[str]) -> bool:
  target_id = str(target_photo_id or '').strip()
  if not target_id:
    return True
  if render_data.get_photo_id_from_detail(photo) == target_id:
    return True
  if share_info_photo_id(photo) == target_id:
    return True
  return False


def _is_work_block(node: Any) -> bool:
  return isinstance(node, dict) and isinstance(node.get('photo'), dict)


def _collect_work_blocks(state: Any) -> List[Dict[str, Any]]:
  blocks: List[Dict[str, Any]] = []

  def walk(obj: Any) -> None:
    if isinstance(obj, dict):
      if _is_work_block(obj):
        blocks.append(obj)
      for value in obj.values():
        walk(value)
    elif isinstance(obj, list):
      for item in obj:
        walk(item)

  walk(state)
  return blocks


def _profile_from_work_block(block: Dict[str, Any]) -> Dict[str, Any]:
  user_profile = block.get('userProfile')
  if not isinstance(user_profile, dict):
    return {}
  profile = user_profile.get('profile')
  if isinstance(profile, dict):
    return profile
  return user_profile


def _work_block_sort_key(block: Dict[str, Any]) -> tuple:
  photo = block.get('photo') or {}
  stats = render_data.get_statistics_from_photo(photo)
  return (
    0 if render_data.statistics_has_values(stats) else 1,
    -len(render_data.get_photo_id_from_detail(photo)),
  )


def find_work_block_in_state(
  state: Any,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  if state is None:
    return None

  blocks = _collect_work_blocks(state)
  if not blocks:
    return None

  target_id = str(target_photo_id or '').strip()
  if target_id:
    matched = [
      block for block in blocks
      if photo_matches_target_h5(block['photo'], target_id)
    ]
    if not matched:
      return None
    matched.sort(key=_work_block_sort_key)
    return matched[0]

  blocks.sort(key=_work_block_sort_key)
  return blocks[0]


def find_photo_in_state(
  state: Any,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  block = find_work_block_in_state(state, target_photo_id)
  if block:
    photo = block.get('photo')
    return photo if isinstance(photo, dict) else None
  return None


def _format_metric_value(raw: Any) -> str:
  formatted = number_format.format_metric(raw)
  return formatted if formatted not in ('',) else '0'


def build_collect_fields_from_work_block(
  block: Dict[str, Any],
  page_url: str = '',
) -> Dict[str, str]:
  photo = block.get('photo') or {}
  counts = block.get('counts') if isinstance(block.get('counts'), dict) else {}
  profile = _profile_from_work_block(block)

  author_name = str(
    photo.get('userName')
    or photo.get('user_name')
    or profile.get('user_name')
    or profile.get('userName')
    or profile.get('name')
    or '',
  ).strip()

  publish_time = kuaishou_time.format_publish_time(photo.get('timestamp'))
  if publish_time in ('-', ''):
    publish_time = '0'

  favorites_raw = number_format.pick_stat_value(
    counts,
    'collectionCount',
    'collection_count',
  )
  if favorites_raw is None:
    favorites_raw = number_format.pick_stat_value(
      photo,
      'collectCount',
      'collect_count',
    )
  if favorites_raw is None:
    favorites_raw = 0

  shares_raw = number_format.pick_stat_value(
    photo,
    'forwardCount',
    'forward_count',
    'shareCount',
    'share_count',
  )
  if shares_raw is None:
    shares_raw = 0

  kwai_id = kuaishou_ids.photo_kwai_id(photo, profile)
  author_uid = kuaishou_ids.photo_author_uid(photo, profile)
  if not author_uid:
    user_id = photo.get('userId') or photo.get('user_id')
    if user_id is not None and str(user_id).strip():
      author_uid = str(user_id).strip()

  kwai_display = kwai_id or author_uid or '0'

  stats = render_data.get_statistics_from_photo(photo)
  metric_source = stats if stats else photo

  return {
    'author_name': author_name,
    'publish_time': publish_time,
    'views': _format_metric_value(
      number_format.pick_stat_value(
        metric_source,
        'viewCount',
        'view_count',
        'realPlayCount',
        'playCount',
      ),
    ),
    'likes': _format_metric_value(
      number_format.pick_stat_value(
        metric_source,
        'realLikeCount',
        'likeCount',
        'like_count',
      ),
    ),
    'comments': _format_metric_value(
      number_format.pick_stat_value(
        metric_source,
        'commentCount',
        'comment_count',
      ),
    ),
    'shares': _format_metric_value(shares_raw),
    'favorites': _format_metric_value(favorites_raw),
    'media_type': map_h5_media_type(photo, page_url),
    'author_sec_uid': kwai_display,
    'author_id': author_uid or '0',
  }


async def find_work_block_on_h5_page(
  page: Page,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  state = await read_init_state(page)
  return find_work_block_in_state(state, target_photo_id)


async def find_photo_on_h5_page(
  page: Page,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  block = await find_work_block_on_h5_page(page, target_photo_id)
  if not block:
    return None
  photo = block.get('photo')
  return photo if isinstance(photo, dict) else None


def is_h5_photo_api_url(url: str) -> bool:
  lower = (url or '').lower()
  return any(marker in lower for marker in _H5_PHOTO_API_MARKERS)


def _iter_api_feed_lists(payload: Any) -> List[List[Dict[str, Any]]]:
  feeds_lists: List[List[Dict[str, Any]]] = []
  if not isinstance(payload, dict):
    return feeds_lists

  for key in ('feeds', 'feedList', 'photoList', 'photos', 'items', 'list'):
    items = payload.get(key)
    if isinstance(items, list) and items:
      dict_items = [item for item in items if isinstance(item, dict)]
      if dict_items:
        feeds_lists.append(dict_items)

  data = payload.get('data')
  if isinstance(data, dict):
    for value in data.values():
      if isinstance(value, dict):
        for key in ('feeds', 'feedList', 'photoList', 'photos', 'items', 'list'):
          items = value.get(key)
          if isinstance(items, list) and items:
            dict_items = [item for item in items if isinstance(item, dict)]
            if dict_items:
              feeds_lists.append(dict_items)
  return feeds_lists


def find_photo_in_api_payload(
  payload: Any,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  target_id = str(target_photo_id or '').strip()
  if not target_id:
    return render_data.extract_photo_from_api_payload(payload)

  candidates: List[Dict[str, Any]] = []
  for feeds in _iter_api_feed_lists(payload):
    matched = [item for item in feeds if photo_matches_target_h5(item, target_id)]
    candidates.extend(matched)

  if candidates:
    candidates.sort(
      key=lambda item: (
        0 if render_data.statistics_has_values(render_data.get_statistics_from_photo(item)) else 1,
        -len(render_data.get_photo_id_from_detail(item)),
      ),
    )
    return candidates[0]

  found = render_data.find_photo_detail(payload, target_id)
  if found and photo_matches_target_h5(found, target_id):
    return found
  return None


async def parse_h5_photo_api_response(
  response: Response,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  try:
    if response.status != 200 or not is_h5_photo_api_url(response.url):
      return None
    payload = await response.json()
  except Exception:
    return None
  return find_photo_in_api_payload(payload, target_photo_id)


def photo_author_name(photo: Dict[str, Any]) -> str:
  author = render_data.get_author_from_photo(photo)
  name = str(
    author.get('userName')
    or author.get('user_name')
    or author.get('name')
    or author.get('nickname')
    or photo.get('userName')
    or photo.get('user_name')
    or '',
  ).strip()
  return name


def photo_comment_count(photo: Dict[str, Any]) -> Any:
  stats = render_data.get_statistics_from_photo(photo)
  source = stats if stats else photo
  return number_format.pick_stat_value(
    source,
    'commentCount',
    'comment_count',
  )


def map_h5_media_type(photo: Dict[str, Any], page_url: str) -> str:
  photo_type = str(photo.get('photoType') or '').upper()
  if photo.get('singlePicture') or 'ATLAS' in photo_type or 'PICTURE' in photo_type:
    return '图片'
  if photo.get('type') == 1 and not photo.get('mainMvUrls'):
    return '图片'

  url_lower = (page_url or '').lower()
  if '/fw/photo/' in url_lower:
    return '图片'
  if '/short-video/' in url_lower or '/video/' in url_lower:
    return '视频'
  return '视频'
