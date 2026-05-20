"""小红书笔记链接解析."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlparse

XHS_DOMAIN = 'https://www.xiaohongshu.com'

_NOTE_ID_PATTERNS = (
  re.compile(r'/explore/([0-9a-f]+)', re.I),
  re.compile(r'/discovery/item/([0-9a-f]+)', re.I),
  re.compile(r'/note/([0-9a-f]+)', re.I),
)


@dataclass
class NoteUrlInfo:
  note_id: str
  xsec_token: str
  xsec_source: str


def extract_url_params(url: str) -> dict[str, str]:
  if not url:
    return {}
  parsed = urlparse(url)
  return dict(parse_qsl(parsed.query))


def extract_note_id_from_url(url: str) -> str:
  text = (url or '').strip()
  for pattern in _NOTE_ID_PATTERNS:
    match = pattern.search(text)
    if match:
      return match.group(1)
  tail = text.split('/')[-1].split('?')[0].strip()
  if re.fullmatch(r'[0-9a-f]{24}', tail, re.I):
    return tail
  return ''


def parse_note_url(url: str) -> NoteUrlInfo:
  note_id = extract_note_id_from_url(url)
  params = extract_url_params(url)
  xsec_token = params.get('xsec_token', '')
  xsec_source = params.get('xsec_source', '') or 'pc_user'
  return NoteUrlInfo(
    note_id=note_id,
    xsec_token=xsec_token,
    xsec_source=xsec_source,
  )


def build_explore_url(info: NoteUrlInfo) -> str:
  query = f'xsec_token={info.xsec_token}&xsec_source={info.xsec_source}'
  return f'{XHS_DOMAIN}/explore/{info.note_id}?{query}'
