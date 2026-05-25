"""小红书笔记链接解析."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
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


@dataclass
class ProfileUrlInfo:
  user_id: str
  xsec_token: str
  xsec_source: str


_PROFILE_PATH_RE = re.compile(
  r'/user/profile/([0-9a-f]{24})(?:\?([^"\'#\s<>]*))?',
  re.I,
)


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


def parse_profile_href(href: str) -> Optional[ProfileUrlInfo]:
  text = (href or '').strip()
  if not text:
    return None
  match = _PROFILE_PATH_RE.search(text)
  if not match:
    return None
  user_id = match.group(1)
  query = match.group(2) or ''
  params = dict(parse_qsl(query)) if query else extract_url_params(text)
  return ProfileUrlInfo(
    user_id=user_id,
    xsec_token=params.get('xsec_token', ''),
    xsec_source=params.get('xsec_source', '') or 'pc_note',
  )


def _profile_from_html_chunk(
  html: str,
  expected_user_id: str = '',
) -> Optional[ProfileUrlInfo]:
  uid = (expected_user_id or '').strip().lower()
  for match in _PROFILE_PATH_RE.finditer(html):
    user_id = match.group(1)
    if uid and user_id.lower() != uid:
      continue
    query = match.group(2) or ''
    params = dict(parse_qsl(query)) if query else {}
    return ProfileUrlInfo(
      user_id=user_id,
      xsec_token=params.get('xsec_token', ''),
      xsec_source=params.get('xsec_source', '') or 'pc_note',
    )
  first = _PROFILE_PATH_RE.search(html)
  if not first:
    return None
  return parse_profile_href(first.group(0))


def profile_url_from_note_page_html(
  html: str,
  expected_user_id: str = '',
) -> Optional[ProfileUrlInfo]:
  if not html or '/user/profile/' not in html:
    return None
  marker = 'id="noteContainer"'
  start = html.find(marker)
  if start >= 0:
    chunk = html[start:start + 80000]
    found = _profile_from_html_chunk(chunk, expected_user_id)
    if found:
      return found
  return _profile_from_html_chunk(html, expected_user_id)


def build_profile_url(
  user_id: str,
  *,
  xsec_token: str = '',
  xsec_source: str = 'pc_note',
) -> str:
  uid = (user_id or '').strip()
  if not uid:
    return ''
  base = f'{XHS_DOMAIN}/user/profile/{uid}'
  if not xsec_token:
    return base
  source = (xsec_source or '').strip() or 'pc_note'
  return f'{base}?xsec_token={xsec_token}&xsec_source={source}'
