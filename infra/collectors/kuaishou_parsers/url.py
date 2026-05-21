"""快手链接解析与规范化."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx

SHORT_LINK_HOST_MARKERS = ('v.kuaishou.com',)

# 站外 H5 分享 SSR 域（非 www.kuaishou.com PC 站）
H5_SHARE_HOST_MARKERS = ('chenzhongtech.com',)

PC_WEB_HOST_MARKERS = ('www.kuaishou.com', 'kuaishou.com')

DEFAULT_USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

_PHOTO_PATH_PATTERNS = (
  re.compile(r'/short-video/([^/?#]+)', re.I),
  re.compile(r'/fw/photo/([^/?#]+)', re.I),
  re.compile(r'/photo/([^/?#]+)', re.I),
  re.compile(r'/f/([^/?#]+)', re.I),
)

_QUERY_ID_KEYS = ('photoId', 'photo_id', 'shareObjectId', 'shareObjectid')


def ensure_https(url: str) -> str:
  text = (url or '').strip()
  if not text:
    return text
  if not text.startswith(('http://', 'https://')):
    return f'https://{text}'
  return text


def is_h5_share_url(url: str) -> bool:
  """是否为站外 H5 分享页（如 v.m.chenzhongtech.com/fw/photo/...）."""
  parsed = urlparse(ensure_https(url))
  host = (parsed.netloc or '').lower()
  path = (parsed.path or '').lower()
  if any(marker in host for marker in H5_SHARE_HOST_MARKERS):
    return True
  return '/fw/photo/' in path


def is_pc_web_url(url: str) -> bool:
  """是否为快手 PC 站作品页（www.kuaishou.com/short-video/...）."""
  if is_h5_share_url(url):
    return False
  parsed = urlparse(ensure_https(url))
  host = (parsed.netloc or '').lower()
  path = (parsed.path or '').lower()
  return 'www.kuaishou.com' in host and '/short-video/' in path


def should_use_h5_collect(link: str, final_url: str = '') -> bool:
  """根据原始链接或跳转后的地址判断是否走 H5 分享采集."""
  if is_h5_share_url(link):
    return True
  if final_url and is_h5_share_url(final_url):
    return True
  return False


def is_share_short_url(url: str) -> bool:
  """是否为 v.kuaishou.com 等分享短链（路径段不是 photoId）."""
  parsed = urlparse(ensure_https(url))
  host = (parsed.netloc or '').lower()
  return any(marker in host for marker in SHORT_LINK_HOST_MARKERS)


async def resolve_short_url(url: str, *, timeout: float = 15.0) -> str:
  """跟随短链重定向，返回最终 URL（失败返回空串）."""
  target = ensure_https(url)
  if not target:
    return ''
  try:
    async with httpx.AsyncClient(
      follow_redirects=True,
      timeout=timeout,
    ) as client:
      response = await client.get(
        target,
        headers={
          'User-Agent': DEFAULT_USER_AGENT,
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
      )
      return str(response.url)
  except Exception:
    return ''


def extract_photo_id(url: str) -> Optional[str]:
  """从快手作品链接中提取 photoId."""
  text = ensure_https(url)
  if not text:
    return None

  parsed = urlparse(text)
  query = parse_qs(parsed.query)
  for key in _QUERY_ID_KEYS:
    values = query.get(key) or query.get(key.lower())
    if values and str(values[0]).strip():
      return str(values[0]).strip()

  path = parsed.path or ''
  for pattern in _PHOTO_PATH_PATTERNS:
    match = pattern.search(path)
    if match:
      photo_id = match.group(1).strip()
      if photo_id:
        return photo_id

  return None


def normalize_collect_url(url: str) -> str:
  """将作品链接规范为 PC 短剧详情页（H5 分享链不转换）."""
  text = ensure_https(url)
  if not text:
    return text

  if is_h5_share_url(text) or is_share_short_url(text):
    return text

  photo_id = extract_photo_id(text)
  if not photo_id:
    return text

  lower = text.lower()
  if '/short-video/' not in lower and photo_id:
    return f'https://www.kuaishou.com/short-video/{photo_id}'

  return text


def resolve_collect_entry_url(link: str) -> str:
  """采集入口 URL：短链/H5 保持原址，其余尽量规范为 PC 详情页."""
  text = ensure_https(link)
  if not text:
    return text
  if is_share_short_url(text) or is_h5_share_url(text):
    return text
  return normalize_collect_url(text)
