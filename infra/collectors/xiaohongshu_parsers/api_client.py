"""小红书笔记详情 API（feed）."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from infra.collectors.xiaohongshu_parsers.playwright_sign import sign_with_xhshow
from infra.collectors.xiaohongshu_parsers.url import NoteUrlInfo, build_explore_url

XHS_API_HOST = 'https://edith.xiaohongshu.com'
FEED_URI = '/api/sns/web/v1/feed'

DEFAULT_USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
)


def cookies_to_header(cookies: List[Dict[str, Any]]) -> str:
  parts: list[str] = []
  for cookie in cookies:
    name = cookie.get('name', '')
    value = cookie.get('value', '')
    if name:
      parts.append(f'{name}={value}')
  return '; '.join(parts)


def build_base_headers(cookie_str: str, referer: str) -> Dict[str, str]:
  return {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Content-Type': 'application/json;charset=UTF-8',
    'Origin': 'https://www.xiaohongshu.com',
    'Referer': referer,
    'User-Agent': DEFAULT_USER_AGENT,
    'Cookie': cookie_str,
  }


async def fetch_note_by_id(
  cookies: List[Dict[str, Any]],
  info: NoteUrlInfo,
  *,
  timeout: float = 30.0,
) -> Optional[Dict]:
  if not info.note_id:
    return None

  xsec_source = info.xsec_source or 'pc_search'
  payload = {
    'source_note_id': info.note_id,
    'image_formats': ['jpg', 'webp', 'avif'],
    'extra': {'need_body_topic': 1},
    'xsec_source': xsec_source,
    'xsec_token': info.xsec_token,
  }

  cookie_str = cookies_to_header(cookies)
  referer = build_explore_url(info)
  signs = sign_with_xhshow(FEED_URI, payload, cookie_str, method='POST')
  headers = build_base_headers(cookie_str, referer)
  headers.update({
    'X-S': signs['x-s'],
    'X-T': signs['x-t'],
    'x-S-Common': signs['x-s-common'],
    'X-B3-Traceid': signs['x-b3-traceid'],
  })

  json_str = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
  try:
    async with httpx.AsyncClient(timeout=timeout) as client:
      response = await client.post(
        f'{XHS_API_HOST}{FEED_URI}',
        content=json_str,
        headers=headers,
      )
      if response.status_code != 200:
        return None
      body = response.json()
  except Exception:
    return None

  if not isinstance(body, dict) or not body.get('success'):
    return None

  data = body.get('data') or body
  items = data.get('items') if isinstance(data, dict) else None
  if not items:
    return None

  first = items[0] if isinstance(items, list) else None
  if not isinstance(first, dict):
    return None

  note_card = first.get('note_card') or first.get('noteCard')
  if isinstance(note_card, dict) and note_card:
    return note_card
  return None
