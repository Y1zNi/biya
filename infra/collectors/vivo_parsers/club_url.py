"""vivo club 老站帖子 URL 解析."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

CLUB_THREAD_PATH_RE = re.compile(
  r'/threadDetail/(?P<tid>\d+)',
  re.I,
)
CLUB_HOST_MARKERS = ('club.vivo.com.cn',)

CLUB_THREAD_BASE = 'https://club.vivo.com.cn/threadDetail/'


@dataclass(frozen=True)
class ClubThreadUrlInfo:
  tid: str
  raw_url: str

  @property
  def is_thread(self) -> bool:
    return bool(self.tid)

  def build_canonical_url(self) -> str:
    if not self.tid:
      return self.raw_url
    return f'{CLUB_THREAD_BASE}{self.tid}'


def parse_club_thread_url(url: str) -> ClubThreadUrlInfo:
  text = (url or '').strip()
  if not text:
    return ClubThreadUrlInfo(tid='', raw_url=text)

  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  parsed = urlparse(text)
  host = (parsed.netloc or '').lower()
  if not any(marker in host for marker in CLUB_HOST_MARKERS):
    return ClubThreadUrlInfo(tid='', raw_url=text)

  match = CLUB_THREAD_PATH_RE.search(parsed.path or '')
  if not match:
    return ClubThreadUrlInfo(tid='', raw_url=text)

  tid = match.group('tid').strip()
  return ClubThreadUrlInfo(tid=tid, raw_url=text)
