"""解析快手页面内嵌 JSON 与接口返回中的作品数据."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

_PHOTO_DETAIL_KEYS = (
  'photo',
  'photoInfo',
  'photo_info',
  'photoDetail',
  'photo_detail',
  'currentPhoto',
  'visionPhotoDetail',
  'feed',
  'item',
)

_PHOTO_ID_KEYS = ('photoId', 'photo_id', 'id', 'workId', 'work_id')
_STAT_KEYS = (
  'viewCount', 'view_count', 'playCount', 'play_count', 'realPlayCount', 'real_play_count',
  'likeCount', 'like_count', 'realLikeCount', 'real_like_count',
  'commentCount', 'comment_count',
  'collectCount', 'collect_count',
  'shareCount', 'share_count',
  'forwardCount', 'forward_count',
)


async def get_page_json_blobs(page: Page) -> List[Dict[str, str]]:
  try:
    return await page.evaluate(
      """() => {
        const blobs = [];
        document.querySelectorAll('script[type="application/json"]').forEach((el) => {
          const text = el.textContent || '';
          if (text.trim().length < 80) return;
          const id = el.id || el.getAttribute('data-id') || '';
          if (blobs.some((b) => b.text === text)) return;
          blobs.push({ id, text });
        });
        const state = window.__INITIAL_STATE__ || window.__APOLLO_STATE__;
        if (state) {
          try {
            blobs.push({ id: '__state__', text: JSON.stringify(state) });
          } catch (e) {}
        }
        return blobs;
      }"""
    )
  except Exception:
    return []


def parse_json_blob_text(raw: str) -> Optional[Dict[str, Any]]:
  if not raw:
    return None
  try:
    decoded = urllib.parse.unquote(str(raw).strip())
    data = json.loads(decoded)
    return data if isinstance(data, dict) else None
  except Exception:
    return None


async def parse_all_page_data(page: Page) -> List[Dict[str, Any]]:
  results: List[Dict[str, Any]] = []
  for blob in await get_page_json_blobs(page):
    data = parse_json_blob_text(str(blob.get('text') or ''))
    if data:
      results.append(data)
  return results


def get_photo_id_from_detail(obj: Dict[str, Any]) -> str:
  for key in _PHOTO_ID_KEYS:
    value = obj.get(key)
    if value is not None and str(value).strip():
      return str(value).strip()
  return ''


def photo_matches_target(obj: Dict[str, Any], target_photo_id: Optional[str]) -> bool:
  target_id = str(target_photo_id or '').strip()
  if not target_id:
    return True
  photo_id = get_photo_id_from_detail(obj)
  return target_id == photo_id


def get_statistics_from_photo(obj: Dict[str, Any]) -> Dict[str, Any]:
  for key in ('counts', 'statistics', 'stats', 'stat', 'photoCount', 'photo_count'):
    value = obj.get(key)
    if isinstance(value, dict):
      return value
  if any(key in obj for key in _STAT_KEYS):
    return obj
  return {}


def statistics_has_values(statistics: Dict[str, Any]) -> bool:
  for key in _STAT_KEYS:
    value = statistics.get(key)
    if value is None:
      continue
    if isinstance(value, (int, float)) and value >= 0:
      if value > 0:
        return True
    elif str(value).strip() not in ('', '-', '0'):
      return True
  return False


def get_author_from_photo(obj: Dict[str, Any]) -> Dict[str, Any]:
  for key in ('author', 'user', 'profile', 'userProfile'):
    value = obj.get(key)
    if isinstance(value, dict):
      return value
  return {}


def is_photo_detail(obj: Dict[str, Any]) -> bool:
  statistics = get_statistics_from_photo(obj)
  has_author = bool(get_author_from_photo(obj))
  has_photo_id = bool(get_photo_id_from_detail(obj))
  return statistics_has_values(statistics) and (has_author or has_photo_id)


def unwrap_photo_detail(obj: Any) -> Optional[Dict[str, Any]]:
  if not isinstance(obj, dict):
    return None

  if is_photo_detail(obj):
    return obj

  for key in _PHOTO_DETAIL_KEYS:
    inner = obj.get(key)
    if isinstance(inner, dict):
      found = unwrap_photo_detail(inner)
      if found:
        return found

  detail = obj.get('detail')
  if isinstance(detail, dict):
    found = unwrap_photo_detail(detail)
    if found:
      return found

  data = obj.get('data')
  if isinstance(data, dict):
    found = unwrap_photo_detail(data)
    if found:
      return found

  return None


def _photo_identity(obj: Dict[str, Any]) -> str:
  photo_id = get_photo_id_from_detail(obj)
  if photo_id:
    return photo_id
  author = get_author_from_photo(obj)
  nickname = str(author.get('userName') or author.get('name') or '')
  return f'unknown:{nickname}'


def collect_photo_details(
  obj: Any,
  depth: int = 0,
  bucket: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
  items = bucket if bucket is not None else []
  if depth > 14:
    return items

  if isinstance(obj, dict):
    unwrapped = unwrap_photo_detail(obj)
    if unwrapped:
      identity = _photo_identity(unwrapped)
      if not any(_photo_identity(item) == identity for item in items):
        items.append(unwrapped)

    for value in obj.values():
      collect_photo_details(value, depth + 1, items)

  elif isinstance(obj, list):
    for item in obj[:120]:
      collect_photo_details(item, depth + 1, items)

  return items


def pick_best_photo(
  candidates: List[Dict[str, Any]],
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  if not candidates:
    return None

  target_id = str(target_photo_id or '').strip()
  if target_id:
    matched = [item for item in candidates if photo_matches_target(item, target_id)]
    if matched:
      matched.sort(
        key=lambda item: (
          0 if statistics_has_values(get_statistics_from_photo(item)) else 1,
          -len(get_photo_id_from_detail(item)),
        ),
      )
      return matched[0]
    return None

  candidates.sort(
    key=lambda item: (
      0 if statistics_has_values(get_statistics_from_photo(item)) else 1,
      -len(get_photo_id_from_detail(item)),
    ),
  )
  return candidates[0]


def find_photo_detail(
  obj: Any,
  target_photo_id: Optional[str] = None,
  depth: int = 0,
) -> Optional[Dict[str, Any]]:
  if obj is None:
    return None
  candidates = collect_photo_details(obj, depth)
  return pick_best_photo(candidates, target_photo_id)


def find_photo_in_page_datasets(
  datasets: List[Dict[str, Any]],
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  candidates: List[Dict[str, Any]] = []
  for data in datasets:
    candidates.extend(collect_photo_details(data))
  return pick_best_photo(candidates, target_photo_id)


def extract_comment_count_from_payload(payload: Any) -> Any:
  if not isinstance(payload, dict):
    return None

  for key in ('commentCountV2', 'commentCount', 'comment_count'):
    if key in payload and payload.get(key) is not None:
      return payload.get(key)

  for value in payload.values():
    if isinstance(value, dict):
      found = extract_comment_count_from_payload(value)
      if found is not None:
        return found
  return None


def extract_photo_from_api_payload(payload: Any) -> Optional[Dict[str, Any]]:
  if payload is None:
    return None

  direct = unwrap_photo_detail(payload)
  if direct:
    return direct

  if isinstance(payload, dict):
    for key in ('feeds', 'feedList', 'photoList', 'photos', 'items', 'list'):
      items = payload.get(key)
      if isinstance(items, list) and items:
        found = pick_best_photo(
          [item for item in items if isinstance(item, dict)],
          None,
        )
        if found:
          return found

  return find_photo_detail(payload)


def is_photo_detail_api_url(url: str) -> bool:
  lower = (url or '').lower()
  if not any(host in lower for host in ('kuaishou.com', 'gifshow.com', 'yximgs.com')):
    return False

  keywords = (
    '/rest/wd/photo',
    '/rest/k/',
    'photo/info',
    'photo/detail',
    'short/video',
    'shortvideo',
    'vision/profile/photo',
    'feed/photo',
    'photo/comment',
    'graphql',
    'vision/video',
    'profile/photo',
  )
  if 'graphql' in lower:
    return True
  return any(key in lower for key in keywords)


async def collect_photo_from_api_responses(
  responses: List[Any],
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  candidates: List[Dict[str, Any]] = []
  target_id = str(target_photo_id or '').strip()

  for response in responses:
    try:
      url = response.url
      if not is_photo_detail_api_url(url):
        continue
      if response.status != 200:
        continue
      payload = await response.json()
    except Exception:
      continue

    found = extract_photo_from_api_payload(payload)
    if not found:
      continue

    if target_id and photo_matches_target(found, target_id):
      return found
    candidates.append(found)

  return pick_best_photo(candidates, target_photo_id)


async def find_photo_detail_in_page(
  page: Page,
  target_photo_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  datasets = await parse_all_page_data(page)
  photo = find_photo_in_page_datasets(datasets, target_photo_id)
  if photo:
    return photo

  try:
    html = await page.content()
  except Exception:
    return None

  if not html or not target_photo_id:
    return None

  target = re.escape(str(target_photo_id))
  patterns = [
    rf'"photoId"\s*:\s*"{target}"[\s\S]{{0,8000}}?"likeCount"\s*:\s*\d+',
    rf'"photo_id"\s*:\s*"{target}"[\s\S]{{0,8000}}?"like_count"\s*:\s*\d+',
    rf'"photoId"\s*:\s*"{target}"[\s\S]{{0,8000}}?"commentCount"\s*:\s*\d+',
    rf'"photoId"\s*:\s*"{target}"[\s\S]{{0,8000}}?"shareCount"\s*:\s*\d+',
    rf'"photoId"\s*:\s*"{target}"[\s\S]{{0,8000}}?"collectCount"\s*:\s*\d+',
  ]
  for pattern in patterns:
    match = re.search(pattern, html)
    if not match:
      continue
    snippet = '{' + match.group(0).lstrip('{')
    try:
      data = json.loads(snippet)
    except Exception:
      continue
    found = find_photo_detail(data, target_photo_id)
    if found:
      return found

  return None
