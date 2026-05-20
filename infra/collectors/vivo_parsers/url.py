"""vivo 社区帖子 URL 解析."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

THREAD_PATH_RE = re.compile(
  r'/newbbs/thread/(?P<tid>\d+)',
  re.I,
)
BBS_HOST_MARKERS = ('bbs.vivo.com.cn',)

VIVO_THREAD_BASE = 'https://bbs.vivo.com.cn/newbbs/thread/'


@dataclass(frozen=True)
class ThreadUrlInfo:
  tid: str
  raw_url: str

  @property
  def is_thread(self) -> bool:
    return bool(self.tid)

  def build_canonical_url(self) -> str:
    if not self.tid:
      return self.raw_url
    return f'{VIVO_THREAD_BASE}{self.tid}'


def parse_thread_url(url: str) -> ThreadUrlInfo:
  text = (url or '').strip()
  if not text:
    return ThreadUrlInfo(tid='', raw_url=text)

  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  parsed = urlparse(text)
  host = (parsed.netloc or '').lower()
  if not any(marker in host for marker in BBS_HOST_MARKERS):
    return ThreadUrlInfo(tid='', raw_url=text)

  match = THREAD_PATH_RE.search(parsed.path or '')
  if not match:
    return ThreadUrlInfo(tid='', raw_url=text)

  tid = match.group('tid').strip()
  return ThreadUrlInfo(tid=tid, raw_url=text)
