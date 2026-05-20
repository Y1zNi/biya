"""微博链接解析."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

NOTE_ID_PATTERNS = (
  re.compile(r'm\.weibo\.cn/detail/(\d+)', re.I),
  re.compile(r'weibo\.com/\d+/(\d+)', re.I),
  re.compile(r'weibo\.cn/\d+/(\d+)', re.I),
  re.compile(r'/status/(\d+)', re.I),
)


@dataclass
class NoteUrlInfo:
  note_id: str
  detail_url: str


def parse_note_url(link: str) -> NoteUrlInfo:
  text = (link or '').strip()
  note_id = ''
  for pattern in NOTE_ID_PATTERNS:
    match = pattern.search(text)
    if match:
      note_id = match.group(1)
      break

  if not note_id:
    path = urlparse(text).path or ''
    match = re.search(r'/(\d{10,})$', path)
    if match:
      note_id = match.group(1)

  detail_url = f'https://m.weibo.cn/detail/{note_id}' if note_id else text
  return NoteUrlInfo(note_id=note_id, detail_url=detail_url)
