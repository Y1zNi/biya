"""B 站 Web API（Cookie 鉴权，视频详情无需 WBI 签名）."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import httpx

from infra.collectors.bilibili_parsers.url import VideoUrlInfo

BILI_API_HOST = 'https://api.bilibili.com'
VIDEO_DETAIL_URI = '/x/web-interface/view/detail'
NAV_URI = '/x/web-interface/nav'

DEFAULT_USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

LOGIN_EXPIRED_CODES = frozenset({-101, -111, -400})


def cookies_to_header(cookies: List[Dict[str, Any]]) -> str:
  parts: list[str] = []
  for cookie in cookies:
    name = cookie.get('name', '')
    value = cookie.get('value', '')
    if name:
      parts.append(f'{name}={value}')
  return '; '.join(parts)


def build_headers(cookie_str: str, referer: str) -> Dict[str, str]:
  return {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Origin': 'https://www.bilibili.com',
    'Referer': referer,
    'User-Agent': DEFAULT_USER_AGENT,
    'Cookie': cookie_str,
  }


def _parse_api_body(body: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str], bool]:
  if not isinstance(body, dict):
    return None, '接口返回格式异常', False

  code = body.get('code', 0)
  if code == 0:
    data = body.get('data')
    return data if isinstance(data, dict) else {}, None, False

  message = str(body.get('message') or body.get('msg') or '请求失败')
  login_expired = code in LOGIN_EXPIRED_CODES or '登录' in message
  return None, message, login_expired


async def fetch_nav(
  cookies: List[Dict[str, Any]],
  *,
  timeout: float = 20.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], bool]:
  cookie_str = cookies_to_header(cookies)
  headers = build_headers(cookie_str, 'https://www.bilibili.com/')

  try:
    async with httpx.AsyncClient(timeout=timeout) as client:
      response = await client.get(f'{BILI_API_HOST}{NAV_URI}', headers=headers)
      if response.status_code != 200:
        return None, f'HTTP {response.status_code}', False
      body = response.json()
  except Exception as exc:
    return None, str(exc), False

  return _parse_api_body(body)


async def is_logged_in(cookies: List[Dict[str, Any]]) -> bool:
  data, _, _ = await fetch_nav(cookies)
  if not data:
    return False
  if data.get('isLogin') is True:
    return True
  return bool(str(data.get('uname') or '').strip())


async def fetch_video_detail(
  cookies: List[Dict[str, Any]],
  info: VideoUrlInfo,
  *,
  timeout: float = 30.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], bool]:
  if not info.is_video:
    return None, '非视频链接', False

  params: Dict[str, str] = {}
  referer = info.build_canonical_url() or 'https://www.bilibili.com/'
  if info.bvid:
    params['bvid'] = info.bvid
  elif info.aid:
    params['aid'] = info.aid
  else:
    return None, '无法解析视频 ID', False

  cookie_str = cookies_to_header(cookies)
  headers = build_headers(cookie_str, referer)

  try:
    async with httpx.AsyncClient(timeout=timeout) as client:
      response = await client.get(
        f'{BILI_API_HOST}{VIDEO_DETAIL_URI}',
        params=params,
        headers=headers,
      )
      if response.status_code != 200:
        return None, f'HTTP {response.status_code}', False
      body = response.json()
  except Exception as exc:
    return None, str(exc), False

  data, message, login_expired = _parse_api_body(body)
  if data is None:
    return None, message, login_expired

  view = data.get('View')
  if isinstance(view, dict) and view:
    return data, None, False

  return None, message or '未获取到视频详情', login_expired
