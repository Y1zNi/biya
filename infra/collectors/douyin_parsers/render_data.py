"""解析抖音页面内嵌 JSON 与接口返回中的作品数据."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

_SCRIPT_JSON_IDS = ('RENDER_DATA', 'SIGI_STATE', 'ROUTER_DATA')
_AWEME_DETAIL_KEYS = (
  'aweme_detail',
  'awemeDetail',
  'aweme_info',
  'awemeInfo',
  'aweme',
  'item',
  'video',
)


async def get_page_json_blobs(page: Page) -> List[Dict[str, str]]:
  try:
    return await page.evaluate(
      """() => {
        const blobs = [];
        const ids = ['RENDER_DATA', 'SIGI_STATE', 'ROUTER_DATA'];
        for (const id of ids) {
          const el = document.getElementById(id);
          if (el && el.textContent && el.textContent.trim()) {
            blobs.push({ id, text: el.textContent });
          }
        }
        document.querySelectorAll('script[type="application/json"]').forEach((el) => {
          const text = el.textContent || '';
          if (text.trim().length < 80) return;
          const id = el.id || el.getAttribute('data-id') || '';
          if (blobs.some((b) => b.text === text)) return;
          blobs.push({ id, text });
        });
        return blobs;
      }"""
    )
  except Exception:
    return []


async def get_render_data_raw(page: Page) -> str:
  blobs = await get_page_json_blobs(page)
  for blob in blobs:
    if blob.get('id') == 'RENDER_DATA':
      return str(blob.get('text') or '')
  return ''


def parse_json_blob_text(raw: str) -> Optional[Dict[str, Any]]:
  if not raw:
    return None
  try:
    decoded = urllib.parse.unquote(str(raw).strip())
    data = json.loads(decoded)
    return data if isinstance(data, dict) else None
  except Exception:
    return None


def parse_render_data_text(raw: str) -> Optional[Dict[str, Any]]:
  return parse_json_blob_text(raw)


async def parse_render_data(page: Page) -> Optional[Dict[str, Any]]:
  raw = await get_render_data_raw(page)
  return parse_render_data_text(raw)


async def parse_all_page_data(page: Page) -> List[Dict[str, Any]]:
  results: List[Dict[str, Any]] = []
  for blob in await get_page_json_blobs(page):
    data = parse_json_blob_text(str(blob.get('text') or ''))
    if data:
      results.append(data)
  return results


def get_aweme_id_from_detail(obj: Dict[str, Any]) -> str:
  for key in ('aweme_id', 'awemeId'):
    value = obj.get(key)
    if value is not None and str(value).strip():
      return str(value).strip()
  return ''


def _pick_author_from_aweme(aweme: Dict[str, Any]) -> Dict[str, Any]:
  author = aweme.get('author')
  return author if isinstance(author, dict) else {}


def _pick_author_str(author: Dict[str, Any], *keys: str) -> str:
  for key in keys:
    value = author.get(key)
    if value is not None and str(value).strip():
      return str(value).strip()
  return ''


def get_author_uid_from_aweme(aweme: Dict[str, Any]) -> str:
  return _pick_author_str(
    _pick_author_from_aweme(aweme),
    'uid',
    'uid_str',
    'user_id',
    'userId',
  )


def get_author_sec_uid_from_aweme(aweme: Dict[str, Any]) -> str:
  return _pick_author_str(
    _pick_author_from_aweme(aweme),
    'sec_uid',
    'secUid',
  )


def get_douyin_id_from_aweme(aweme: Dict[str, Any]) -> str:
  return _pick_author_str(
    _pick_author_from_aweme(aweme),
    'unique_id',
    'uniqueId',
  )


def get_group_id_from_detail(obj: Dict[str, Any]) -> str:
  for key in ('group_id', 'groupId'):
    value = obj.get(key)
    if value is not None and str(value).strip():
      return str(value).strip()
  return ''


def aweme_matches_target(obj: Dict[str, Any], target_aweme_id: Optional[str]) -> bool:
  target_id = str(target_aweme_id or '').strip()
  if not target_id:
    return True
  aweme_id = get_aweme_id_from_detail(obj)
  group_id = get_group_id_from_detail(obj)
  return target_id in {aweme_id, group_id}


def get_statistics_from_aweme(obj: Dict[str, Any]) -> Dict[str, Any]:
  for key in ('statistics', 'stats', 'stat'):
    value = obj.get(key)
    if isinstance(value, dict):
      return value
  return {}


def statistics_has_values(statistics: Dict[str, Any]) -> bool:
  keys = (
    'play_count', 'playCount',
    'digg_count', 'diggCount',
    'comment_count', 'commentCount',
    'collect_count', 'collectCount',
    'share_count', 'shareCount',
    'forward_count', 'forwardCount',
  )
  for key in keys:
    value = statistics.get(key)
    if value is None:
      continue
    if isinstance(value, (int, float)) and value >= 0:
      if value > 0:
        return True
    elif str(value).strip() not in ('', '-', '0'):
      return True
  return False


def unwrap_aweme_detail(obj: Any) -> Optional[Dict[str, Any]]:
  if not isinstance(obj, dict):
    return None

  if is_aweme_detail(obj):
    return obj

  for key in _AWEME_DETAIL_KEYS:
    inner = obj.get(key)
    if isinstance(inner, dict):
      found = unwrap_aweme_detail(inner)
      if found:
        return found

  detail = obj.get('detail')
  if isinstance(detail, dict):
    found = unwrap_aweme_detail(detail)
    if found:
      return found

  data = obj.get('data')
  if isinstance(data, dict):
    found = unwrap_aweme_detail(data)
    if found:
      return found

  return None


def is_aweme_detail(obj: Dict[str, Any]) -> bool:
  statistics = get_statistics_from_aweme(obj)
  has_author = isinstance(obj.get('author'), dict)
  has_aweme_id = bool(get_aweme_id_from_detail(obj) or get_group_id_from_detail(obj))
  return bool(statistics) and (has_author or has_aweme_id)


def _aweme_identity(obj: Dict[str, Any]) -> str:
  aweme_id = get_aweme_id_from_detail(obj)
  group_id = get_group_id_from_detail(obj)
  if aweme_id or group_id:
    return f'{aweme_id}:{group_id}'
  author = obj.get('author') or {}
  nickname = str(author.get('nickname') or '')
  return f'unknown:{nickname}'


def collect_aweme_details(obj: Any, depth: int = 0, bucket: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
  items = bucket if bucket is not None else []
  if depth > 14:
    return items

  if isinstance(obj, dict):
    unwrapped = unwrap_aweme_detail(obj)
    if unwrapped:
      identity = _aweme_identity(unwrapped)
      if not any(_aweme_identity(item) == identity for item in items):
        items.append(unwrapped)

    for value in obj.values():
      collect_aweme_details(value, depth + 1, items)

  elif isinstance(obj, list):
    for item in obj[:120]:
      collect_aweme_details(item, depth + 1, items)

  return items


def pick_best_aweme(
  candidates: List[Dict[str, Any]],
  target_aweme_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  if not candidates:
    return None

  target_id = str(target_aweme_id or '').strip()
  if target_id:
    matched = [item for item in candidates if aweme_matches_target(item, target_id)]
    if matched:
      matched.sort(
        key=lambda item: (
          0 if statistics_has_values(get_statistics_from_aweme(item)) else 1,
          -len(get_aweme_id_from_detail(item)),
        ),
      )
      return matched[0]

  candidates.sort(
    key=lambda item: (
      0 if statistics_has_values(get_statistics_from_aweme(item)) else 1,
      -len(get_aweme_id_from_detail(item)),
    ),
  )
  return candidates[0]


def find_aweme_detail(
  obj: Any,
  target_aweme_id: Optional[str] = None,
  depth: int = 0,
) -> Optional[Dict[str, Any]]:
  if obj is None:
    return None
  candidates = collect_aweme_details(obj, depth)
  return pick_best_aweme(candidates, target_aweme_id)


def find_aweme_in_page_datasets(
  datasets: List[Dict[str, Any]],
  target_aweme_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  candidates: List[Dict[str, Any]] = []
  for data in datasets:
    candidates.extend(collect_aweme_details(data))
  return pick_best_aweme(candidates, target_aweme_id)


def extract_aweme_from_api_payload(payload: Any) -> Optional[Dict[str, Any]]:
  if payload is None:
    return None

  direct = unwrap_aweme_detail(payload)
  if direct:
    return direct

  if isinstance(payload, dict):
    for key in ('aweme_list', 'awemeList', 'item_list', 'itemList'):
      items = payload.get(key)
      if isinstance(items, list) and items:
        found = pick_best_aweme(
          [item for item in items if isinstance(item, dict)],
          None,
        )
        if found:
          return found

  return find_aweme_detail(payload)


def is_aweme_detail_api_url(url: str) -> bool:
  lower = (url or '').lower()
  if 'aweme' not in lower:
    return False
  keywords = (
    'aweme/detail',
    'aweme/post',
    'aweme/v1',
    'iteminfo',
    'item_info',
    'multi/aweme',
  )
  return any(key in lower for key in keywords)


async def collect_aweme_from_api_responses(
  responses: List[Any],
  target_aweme_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  candidates: List[Dict[str, Any]] = []
  target_id = str(target_aweme_id or '').strip()

  for response in responses:
    try:
      url = response.url
      if not is_aweme_detail_api_url(url):
        continue
      if response.status != 200:
        continue
      payload = await response.json()
    except Exception:
      continue

    found = extract_aweme_from_api_payload(payload)
    if not found:
      continue

    if target_id and aweme_matches_target(found, target_id):
      return found
    candidates.append(found)

  return pick_best_aweme(candidates, target_aweme_id)


async def find_aweme_detail_in_page(
  page: Page,
  target_aweme_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
  datasets = await parse_all_page_data(page)
  aweme = find_aweme_in_page_datasets(datasets, target_aweme_id)
  if aweme:
    return aweme

  try:
    html = await page.content()
  except Exception:
    return None

  if not html or not target_aweme_id:
    return None

  target = re.escape(str(target_aweme_id))
  patterns = [
    rf'"aweme_id"\s*:\s*"{target}"[\s\S]{{0,4000}}?"statistics"\s*:\s*\{{[\s\S]{{0,1200}}?\}}',
    rf'"awemeId"\s*:\s*"{target}"[\s\S]{{0,4000}}?"statistics"\s*:\s*\{{[\s\S]{{0,1200}}?\}}',
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
    found = find_aweme_detail(data, target_aweme_id)
    if found:
      return found

  return None
