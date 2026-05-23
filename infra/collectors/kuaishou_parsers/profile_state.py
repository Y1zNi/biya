"""快手 PC 主页 SSR（INIT_STATE）解析：快手号与头像 CDN uid."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import APIRequestContext

from infra.collectors.kuaishou_parsers import api_client
from infra.collectors.kuaishou_parsers.ids import (
  extract_uid_from_cdn_url,
  is_numeric_uid,
  is_plausible_author_uid,
)

_PROFILE_URL_TEMPLATE = 'https://www.kuaishou.com/profile/{eid}'
_USER_DEFINE_ID_RE = re.compile(r'"userDefineId"\s*:\s*"([^"]+)"')
_PROFILE_HEADURL_RE = re.compile(
  r'"(?:headurl|headUrl)"\s*:\s*"(https?://[^"]+|/[^"]+)"',
  re.I,
)


def _extract_json_object_after_marker(html: str, marker: str) -> Optional[str]:
  idx = html.find(marker)
  if idx < 0:
    return None
  start = html.find('{', idx)
  if start < 0:
    return None

  depth = 0
  in_string = False
  escape = False
  for pos in range(start, len(html)):
    ch = html[pos]
    if in_string:
      if escape:
        escape = False
      elif ch == '\\':
        escape = True
      elif ch == '"':
        in_string = False
      continue
    if ch == '"':
      in_string = True
      continue
    if ch == '{':
      depth += 1
    elif ch == '}':
      depth -= 1
      if depth == 0:
        return html[start:pos + 1]
  return None


def extract_init_state_from_html(html: str) -> Optional[Dict[str, Any]]:
  if not html:
    return None
  raw = _extract_json_object_after_marker(html, 'window.INIT_STATE')
  if not raw:
    return None
  try:
    data = json.loads(raw)
    return data if isinstance(data, dict) else None
  except Exception:
    return None


def _find_user_profile(state: Any) -> Optional[Dict[str, Any]]:
  if not isinstance(state, dict):
    return None
  user_profile = state.get('userProfile')
  if isinstance(user_profile, dict):
    return user_profile

  def walk(obj: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
    if depth > 12 or not isinstance(obj, dict):
      return None
    if 'userDefineId' in obj or (
      isinstance(obj.get('profile'), dict)
      and ('headurl' in obj['profile'] or 'headUrl' in obj['profile'])
    ):
      return obj
    for value in obj.values():
      if isinstance(value, dict):
        found = walk(value, depth + 1)
        if found:
          return found
    return None

  return walk(state)


def extract_profile_ids_from_html(html: str) -> Tuple[str, str]:
  """优先从 HTML 文本提取（SSR 中 INIT_STATE 结构可能无法完整 json.loads）."""
  kwai_id = '-'
  author_uid = '-'

  match = _USER_DEFINE_ID_RE.search(html)
  if match:
    text = str(match.group(1)).strip()
    if text:
      if is_plausible_author_uid(text):
        author_uid = text
      elif not is_numeric_uid(text):
        kwai_id = text

  head_match = _PROFILE_HEADURL_RE.search(html)
  if head_match:
    uid = extract_uid_from_cdn_url(head_match.group(1))
    if uid:
      author_uid = uid

  return kwai_id, author_uid


def parse_profile_ids(state: Optional[Dict[str, Any]]) -> Tuple[str, str]:
  if not state or not isinstance(state, dict):
    return '-', '-'

  user_profile = _find_user_profile(state)
  if not user_profile:
    return '-', '-'

  user_define_id = str(user_profile.get('userDefineId') or '').strip()
  kwai_id = '-'
  author_uid = '-'
  if user_define_id:
    if is_plausible_author_uid(user_define_id):
      author_uid = user_define_id
    elif not is_numeric_uid(user_define_id):
      kwai_id = user_define_id

  profile = user_profile.get('profile')
  if isinstance(profile, dict):
    headurl = str(profile.get('headurl') or profile.get('headUrl') or '').strip()
    uid = extract_uid_from_cdn_url(headurl)
    if uid:
      author_uid = uid

  return kwai_id, author_uid


async def fetch_profile_ids(
  request: APIRequestContext,
  eid: str,
  referer: str,
) -> Tuple[str, str]:
  eid_text = str(eid or '').strip()
  if not eid_text:
    return '-', '-'

  profile_url = _PROFILE_URL_TEMPLATE.format(eid=eid_text)
  headers = api_client.build_api_headers(referer or profile_url)

  try:
    response = await request.get(profile_url, headers=headers, timeout=20000)
    if response.status != 200:
      return '-', '-'
    html = await response.text()
  except Exception:
    return '-', '-'

  state = extract_init_state_from_html(html)
  json_kwai, json_uid = parse_profile_ids(state)

  html_kwai, html_uid = extract_profile_ids_from_html(html)
  kwai_id = json_kwai if json_kwai not in ('-', '') else html_kwai
  author_uid = json_uid if json_uid not in ('-', '') else html_uid
  if kwai_id not in ('-', '') or author_uid not in ('-', ''):
    return kwai_id, author_uid

  return '-', '-'
