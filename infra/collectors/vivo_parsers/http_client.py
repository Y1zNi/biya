"""vivo 社区帖子页 HTTP 请求（Cookie 可选，未登录也可请求）."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import httpx

from infra.collectors.vivo_parsers.url import ThreadUrlInfo, VIVO_THREAD_BASE

VIVO_BBS_ORIGIN = 'https://bbs.vivo.com.cn'
DEFAULT_USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
)

VIVO_LOGIN_COOKIE_NAMES = frozenset({
  'vvc_token',
  'vvc_account',
  'token',
  'bbs_token',
  'BBSSESSION',
  'sessionid',
  'vivo_account_cookie_iqoo_authtoken',
  'vivo_account_cookie_iqoo_vivotoken',
  'vivo_account_cookie_iqoo_openid',
})


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
    'Accept': (
      'text/html,application/xhtml+xml,application/xml;q=0.9,'
      'image/avif,image/webp,image/apng,*/*;q=0.8'
    ),
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Pragma': 'no-cache',
    'Referer': referer,
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': DEFAULT_USER_AGENT,
    'Cookie': cookie_str,
  }


def is_logged_in(cookies: List[Dict[str, Any]]) -> bool:
  for cookie in cookies:
    domain = str(cookie.get('domain', ''))
    if 'vivo.com.cn' not in domain:
      continue
    name = str(cookie.get('name', ''))
    value = str(cookie.get('value', '')).strip()
    if not value or len(value) < 4:
      continue
    if name in VIVO_LOGIN_COOKIE_NAMES:
      return True
    lowered = name.lower()
    if any(key in lowered for key in ('token', 'session', 'sess', 'auth', 'vvc', 'bbs')):
      return True
  return False


def _looks_like_login_page(html: str, final_url: str) -> bool:
  text = (html or '').lower()
  url = (final_url or '').lower()
  if 'passport.vivo.com.cn' in url:
    return True
  if '__nuxt' not in text and 'threaddata' not in text.replace(' ', ''):
    if 'login' in url or '请登录' in html or '立即登录' in html:
      return True
  return False


async def fetch_thread_html(
  cookies: List[Dict[str, Any]],
  info: ThreadUrlInfo,
  *,
  timeout: float = 30.0,
) -> Tuple[Optional[str], Optional[str], str]:
  if not info.is_thread:
    return None, '非帖子详情链接', ''

  url = info.build_canonical_url()
  referer = f'{VIVO_BBS_ORIGIN}/newbbs/'
  cookie_str = cookies_to_header(cookies)
  headers = build_headers(cookie_str, referer)

  try:
    async with httpx.AsyncClient(
      timeout=timeout,
      follow_redirects=True,
    ) as client:
      response = await client.get(url, headers=headers)
      html = response.text
      final_url = str(response.url)
  except Exception as exc:
    return None, str(exc), ''

  if response.status_code >= 400:
    return None, f'HTTP {response.status_code}', final_url

  if _looks_like_login_page(html, final_url):
    return None, '页面需要登录或无法获取帖子数据', final_url

  if '__NUXT__' not in html:
    return None, '页面未包含帖子数据（__NUXT__）', final_url

  return html, None, final_url
