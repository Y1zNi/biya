"""微信视频号 finder-preview API（Cookie 可选，未登录也可请求）."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import httpx

from infra.collectors.channels_parsers.url import build_preview_referer

FEED_INFO_URL = 'https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info'
CHANNELS_ORIGIN = 'https://channels.weixin.qq.com'

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


def build_headers(cookie_str: str, short_uri: str) -> Dict[str, str]:
  referer = build_preview_referer(short_uri)
  return {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Origin': CHANNELS_ORIGIN,
    'Pragma': 'no-cache',
    'Referer': referer,
    'User-Agent': DEFAULT_USER_AGENT,
    'Cookie': cookie_str,
  }


def _parse_feed_body(body: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
  if not isinstance(body, dict):
    return None, '接口返回格式异常'

  err_code = body.get('errCode', body.get('errcode', -1))
  err_msg = str(body.get('errMsg') or body.get('errmsg') or '').strip()

  try:
    code_ok = int(err_code) == 0
  except (TypeError, ValueError):
    code_ok = False

  if not code_ok:
    return None, err_msg or f'接口错误 errCode={err_code}'

  data = body.get('data')
  if not isinstance(data, dict):
    return None, '未获取到作品数据'

  feed_info = data.get('feedInfo')
  if not isinstance(feed_info, dict):
    return None, '未获取到作品详情 feedInfo'

  return data, None


async def fetch_feed_info(
  cookies: List[Dict[str, Any]],
  short_uri: str,
  *,
  general_token: str = '',
  timeout: float = 30.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
  uri = (short_uri or '').strip()
  if not uri:
    return None, '无法解析视频号作品短码'

  cookie_str = cookies_to_header(cookies)
  headers = build_headers(cookie_str, uri)
  payload = {
    'baseReq': {'generalToken': general_token or ''},
    'shortUri': uri,
  }

  try:
    async with httpx.AsyncClient(timeout=timeout) as client:
      response = await client.post(FEED_INFO_URL, headers=headers, json=payload)
  except Exception as exc:
    return None, str(exc)

  # finder-preview 成功时常返回 201 Created，与浏览器一致按 2xx 处理
  if not (200 <= response.status_code < 300):
    return None, f'HTTP {response.status_code}'

  try:
    body = response.json()
  except Exception:
    return None, '响应不是有效 JSON'

  return _parse_feed_body(body)
