"""微信视频号链接解析（weixin.qq.com/sph/ 短码）."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

WEIXIN_SPH_HOST = 'weixin.qq.com'
CHANNELS_HOST = 'channels.weixin.qq.com'
SPH_PATH_PATTERN = re.compile(r'/sph/([A-Za-z0-9_-]+)', re.I)
PREVIEW_PAGE_BASE = 'https://channels.weixin.qq.com/finder-preview/pages/sph'


@dataclass
class ChannelsUrlInfo:
  short_uri: str = ''
  canonical_link: str = ''

  @property
  def is_valid(self) -> bool:
    return bool(self.short_uri)


def extract_short_uri(link: str) -> str:
  text = (link or '').strip()
  if not text:
    return ''

  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  parsed = urlparse(text)
  path = parsed.path or ''

  match = SPH_PATH_PATTERN.search(path)
  if match:
    return match.group(1)

  if 'finder-preview' in path or 'channels.weixin.qq.com' in (parsed.netloc or '').lower():
    query = parse_qs(parsed.query)
    for key in ('id', 'shortUri', 'short_uri'):
      values = query.get(key)
      if values and str(values[0]).strip():
        return str(values[0]).strip()

  return ''


def build_canonical_link(short_uri: str) -> str:
  uri = (short_uri or '').strip()
  if not uri:
    return ''
  return f'https://{WEIXIN_SPH_HOST}/sph/{uri}'


def build_preview_referer(short_uri: str) -> str:
  uri = (short_uri or '').strip()
  if not uri:
    return f'{PREVIEW_PAGE_BASE}'
  return f'{PREVIEW_PAGE_BASE}?id={uri}'


def parse_channels_url(link: str) -> ChannelsUrlInfo:
  short_uri = extract_short_uri(link)
  canonical = build_canonical_link(short_uri) if short_uri else ''
  return ChannelsUrlInfo(short_uri=short_uri, canonical_link=canonical)
