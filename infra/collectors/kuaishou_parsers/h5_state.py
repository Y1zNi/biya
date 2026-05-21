"""快手 H5 分享页（chenzhongtech）INIT_STATE 与推荐接口数据解析."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from playwright.async_api import Page, Response

from infra.collectors.douyin_parsers import number_format
from infra.collectors.kuaishou_parsers import render_data

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


def find_photo_in_state(
  state: Any,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  if state is None:
    return None
  candidates = render_data.collect_photo_details(state)
  if not candidates:
    return None

  target_id = str(target_photo_id or '').strip()
  if target_id:
    matched = [item for item in candidates if photo_matches_target_h5(item, target_id)]
    if matched:
      matched.sort(
        key=lambda item: (
          0 if render_data.statistics_has_values(render_data.get_statistics_from_photo(item)) else 1,
          -len(render_data.get_photo_id_from_detail(item)),
        ),
      )
      return matched[0]
    return None

  return render_data.pick_best_photo(candidates, None)


async def find_photo_on_h5_page(
  page: Page,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  state = await read_init_state(page)
  photo = find_photo_in_state(state, target_photo_id)
  if photo:
    return photo
  return None


def is_h5_photo_api_url(url: str) -> bool:
  lower = (url or '').lower()
  return any(marker in lower for marker in _H5_PHOTO_API_MARKERS)


async def parse_h5_photo_api_response(response: Response) -> Optional[Dict[str, Any]]:
  try:
    if response.status != 200 or not is_h5_photo_api_url(response.url):
      return None
    payload = await response.json()
  except Exception:
    return None
  return render_data.extract_photo_from_api_payload(payload)


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
