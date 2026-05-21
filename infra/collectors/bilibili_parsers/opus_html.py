"""B 站图文（opus）页 HTML：拉取并解析 window.__INITIAL_STATE__."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from infra.collectors.bilibili_parsers.api_client import (
  build_headers,
  cookies_to_header,
)

INITIAL_STATE_MARKER = 'window.__INITIAL_STATE__'
OPUS_PAGE_HOST = 'https://www.bilibili.com'

HTML_ACCEPT = (
  'text/html,application/xhtml+xml,application/xml;q=0.9,'
  'image/avif,image/webp,image/apng,*/*;q=0.8'
)


def _extract_json_object(raw: str, start_index: int) -> Optional[str]:
  depth = 0
  in_string = False
  escape = False
  for index in range(start_index, len(raw)):
    char = raw[index]
    if in_string:
      if escape:
        escape = False
      elif char == '\\':
        escape = True
      elif char == '"':
        in_string = False
      continue
    if char == '"':
      in_string = True
      continue
    if char == '{':
      depth += 1
    elif char == '}':
      depth -= 1
      if depth == 0:
        return raw[start_index:index + 1]
  return None


def parse_initial_state(html: str) -> Optional[Dict[str, Any]]:
  if not html:
    return None
  match = re.search(
    rf'{re.escape(INITIAL_STATE_MARKER)}\s*=\s*(\{{)',
    html,
  )
  if not match:
    return None
  start = match.start(1)
  json_text = _extract_json_object(html, start)
  if not json_text:
    return None
  try:
    state = json.loads(json_text.replace(':undefined', ':null'))
  except json.JSONDecodeError:
    return None
  return state if isinstance(state, dict) else None


def _module_dict(entry: Dict[str, Any], key: str) -> Dict[str, Any]:
  block = entry.get(key)
  return block if isinstance(block, dict) else {}


def extract_modules(
  state: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
  detail = state.get('detail')
  if not isinstance(detail, dict):
    return {}, {}

  modules = detail.get('modules')
  if not isinstance(modules, list):
    return {}, {}

  author: Dict[str, Any] = {}
  stat: Dict[str, Any] = {}
  for entry in modules:
    if not isinstance(entry, dict):
      continue
    module_type = str(entry.get('module_type') or '')
    if module_type == 'MODULE_TYPE_AUTHOR' or 'module_author' in entry:
      author = _module_dict(entry, 'module_author') or author
    if module_type == 'MODULE_TYPE_STAT' or 'module_stat' in entry:
      stat = _module_dict(entry, 'module_stat') or stat
  return author, stat


def get_opus_id_from_state(state: Dict[str, Any], fallback: str = '') -> str:
  detail = state.get('detail')
  if isinstance(detail, dict):
    id_str = str(detail.get('id_str') or '').strip()
    if id_str:
      return id_str
  state_id = str(state.get('id') or '').strip()
  if state_id:
    return state_id
  return (fallback or '').strip()


async def fetch_opus_state(
  cookies: List[Dict[str, Any]],
  opus_id: str,
  *,
  timeout: float = 30.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
  oid = (opus_id or '').strip()
  if not oid:
    return None, '无法解析图文 ID'

  page_url = f'{OPUS_PAGE_HOST}/opus/{oid}'
  cookie_str = cookies_to_header(cookies)
  headers = build_headers(cookie_str, page_url)
  headers['Accept'] = HTML_ACCEPT
  headers['Cache-Control'] = 'no-cache'
  headers['Pragma'] = 'no-cache'

  try:
    async with httpx.AsyncClient(
      follow_redirects=True,
      timeout=timeout,
    ) as client:
      response = await client.get(page_url, headers=headers)
  except Exception as exc:
    return None, str(exc)

  if response.status_code != 200:
    return None, f'HTTP {response.status_code}'

  html = response.text or ''
  state = parse_initial_state(html)
  if not state:
    return None, '页面未包含图文数据（__INITIAL_STATE__）'

  _, stat = extract_modules(state)
  if not stat:
    return None, '未能获取图文互动数据'

  return state, None
