"""微博链接解析."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

NOTE_ID_PATTERNS = (
  re.compile(r'm\.weibo\.cn/detail/(\d+)', re.I),
  re.compile(r'm\.weibo\.cn/status/([A-Za-z0-9]+)', re.I),
  re.compile(r'weibo\.com/\d+/(\d{10,})', re.I),
  re.compile(r'weibo\.com/\d+/([A-Za-z][A-Za-z0-9]*)', re.I),
  re.compile(r'weibo\.cn/\d+/(\d{10,})', re.I),
  re.compile(r'weibo\.cn/\d+/([A-Za-z][A-Za-z0-9]*)', re.I),
  re.compile(r'/status/(\d+)', re.I),
  re.compile(r'/status/([A-Za-z][A-Za-z0-9]*)', re.I),
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
    else:
      segment_match = re.search(r'^/\d+/([^/?#]+)$', path)
      if segment_match:
        segment = segment_match.group(1).strip()
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', segment):
          note_id = segment

  detail_url = _build_detail_url(note_id, text)
  return NoteUrlInfo(note_id=note_id, detail_url=detail_url)


def _build_detail_url(note_id: str, original: str) -> str:
  """数字 ID 走 detail；新版字母 slug 走 status（与 PC 链跳转一致）."""
  if not note_id:
    return original
  if note_id.isdigit():
    return f'https://m.weibo.cn/detail/{note_id}'
  return f'https://m.weibo.cn/status/{note_id}'
