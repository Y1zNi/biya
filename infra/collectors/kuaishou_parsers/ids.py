"""快手作品/作者标识解析（作品 id、数字 uid、eid、快手号）."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from infra.collectors.kuaishou_parsers import render_data
from infra.collectors.kuaishou_parsers.h5_state import share_info_photo_id

_CDN_UID_SLASH_RE = re.compile(r'/(\d{8,})/')
_CDN_UID_EMBED_RE = re.compile(r'_(\d{8,11})(?=\D|$)')
_B64_SEGMENT_RE = re.compile(r'^[A-Za-z0-9+/]+$')
_KS_UPIC_UID_B64_RE = re.compile(
  r'f([A-Z][A-Za-z0-9+/]{10,14})(?=X[A-Za-z0-9])',
)
_KS_UPIC_UID_B64_ALT_RE = re.compile(
  r'(?:^|_)([A-Z][A-Za-z0-9+/]{11,15})(?=_\d|_\d)',
)
_PAGE_EID_QUERY_KEYS = ('efid', 'userEid', 'user_eid', 'eid')
_PAGE_UID_QUERY_KEYS = ('fid',)
_NUMERIC_UID_KEYS = ('userId', 'user_id', 'authorId', 'author_id')
_EID_KEYS = ('userEid', 'user_eid', 'eid')
_KWAI_ID_KEYS = ('kwaiId', 'kwai_id', 'userDefineId', 'user_define_id')


def _pick_str(obj: Dict[str, Any], *keys: str) -> str:
  for key in keys:
    value = obj.get(key)
    if value is not None and str(value).strip():
      return str(value).strip()
  return ''


def is_numeric_uid(value: Any) -> bool:
  text = str(value or '').strip()
  return bool(text) and text.isdigit()


def is_plausible_author_uid(value: str) -> bool:
  text = str(value or '').strip()
  if not is_numeric_uid(text):
    return False
  if text.startswith('202'):
    return False
  return 9 <= len(text) <= 11


def _decode_b64_uid_segment(segment: str) -> str:
  text = str(segment or '').strip()
  if not text:
    return ''
  padded = text + '=' * ((4 - len(text) % 4) % 4)
  try:
    decoded = base64.b64decode(padded, validate=False).decode('utf-8')
  except (binascii.Error, UnicodeDecodeError, ValueError):
    return ''
  return decoded if is_plausible_author_uid(decoded) else ''


def _pick_best_cdn_uid(candidates: list[str]) -> str:
  if not candidates:
    return ''
  preferred = [text for text in candidates if is_plausible_author_uid(text)]
  if preferred:
    return preferred[0]
  return ''


def _cdn_filename_for_scan(url: str) -> str:
  parsed = urlparse(str(url or '').strip())
  path = parsed.path or ''
  if not path:
    return str(url or '')
  filename = path.rsplit('/', 1)[-1]
  return filename if filename else path


def extract_uid_from_cdn_url(url: str) -> str:
  if not url:
    return ''
  text = _cdn_filename_for_scan(url)
  slash_matches = _CDN_UID_SLASH_RE.findall(text)
  picked = _pick_best_cdn_uid(slash_matches)
  if picked:
    return picked
  embed_matches = _CDN_UID_EMBED_RE.findall(text)
  picked = _pick_best_cdn_uid(embed_matches)
  if picked:
    return picked

  for segment in text.split('_'):
    if 8 <= len(segment) <= 32:
      decoded = _decode_b64_uid_segment(segment)
      if decoded:
        return decoded

  for pattern in (_KS_UPIC_UID_B64_RE, _KS_UPIC_UID_B64_ALT_RE):
    for match in pattern.finditer(text):
      decoded = _decode_b64_uid_segment(match.group(1))
      if is_plausible_author_uid(decoded):
        return decoded
  return ''


def author_eid_from_page_url(url: str) -> str:
  """从作品页 URL 查询参数取作者 eid（PC 分享链 userId/efid 常为 eid 字符串）."""
  parsed = urlparse(str(url or '').strip())
  query = parse_qs(parsed.query)
  for key in _PAGE_EID_QUERY_KEYS:
    values = query.get(key) or query.get(key.lower())
    if not values:
      continue
    text = str(values[0]).strip()
    if text and not is_numeric_uid(text):
      return text
  values = query.get('userId') or query.get('userid')
  if values:
    text = str(values[0]).strip()
    if text and not is_numeric_uid(text):
      return text
  return ''


def author_uid_from_page_url(url: str) -> str:
  """H5 分享链 URL 中 fid 常为作者数字 uid."""
  parsed = urlparse(str(url or '').strip())
  query = parse_qs(parsed.query)
  for key in _PAGE_UID_QUERY_KEYS:
    values = query.get(key) or query.get(key.lower())
    if not values:
      continue
    text = str(values[0]).strip()
    if is_numeric_uid(text):
      return text
  return ''


def photo_note_id(photo: Dict[str, Any], fallback: str = '') -> str:
  note_id = render_data.get_photo_id_from_detail(photo)
  if note_id:
    return note_id
  short_id = share_info_photo_id(photo)
  if short_id:
    return short_id
  return str(fallback or '').strip()


def _author_dict(photo: Dict[str, Any]) -> Dict[str, Any]:
  author = render_data.get_author_from_photo(photo)
  if author:
    return author
  for key in _EID_KEYS:
    value = photo.get(key)
    if value is not None and str(value).strip():
      return {'id': str(value).strip()}
  return {}


def photo_author_uid(photo: Dict[str, Any], author: Optional[Dict[str, Any]] = None) -> str:
  author_obj = author if author is not None else _author_dict(photo)
  for source in (photo, author_obj):
    if not isinstance(source, dict):
      continue
    for key in _NUMERIC_UID_KEYS:
      value = source.get(key)
      if is_numeric_uid(value):
        return str(value).strip()
  return ''


def photo_author_eid(photo: Dict[str, Any], author: Optional[Dict[str, Any]] = None) -> str:
  author_obj = author if author is not None else _author_dict(photo)
  if isinstance(author_obj, dict):
    for key in ('id', 'profileId', 'profile_id', *_EID_KEYS):
      value = author_obj.get(key)
      if value is None:
        continue
      text = str(value).strip()
      if not text or is_numeric_uid(text):
        continue
      return text
  for key in _EID_KEYS:
    value = photo.get(key)
    if value is None:
      continue
    text = str(value).strip()
    if not text or is_numeric_uid(text):
      continue
    return text
  return ''


def photo_kwai_id(photo: Dict[str, Any], author: Optional[Dict[str, Any]] = None) -> str:
  author_obj = author if author is not None else _author_dict(photo)
  for source in (photo, author_obj):
    if not isinstance(source, dict):
      continue
    kwai_id = _pick_str(source, *_KWAI_ID_KEYS)
    if kwai_id and not is_numeric_uid(kwai_id):
      return kwai_id
  return ''


def cdn_url_from_photo(photo: Dict[str, Any], author: Optional[Dict[str, Any]] = None) -> str:
  author_obj = author if author is not None else _author_dict(photo)
  for source in (author_obj, photo):
    if not isinstance(source, dict):
      continue
    for key in ('headerUrl', 'header_url', 'headurl', 'headUrl', 'avatar', 'coverUrl', 'cover_url'):
      url = str(source.get(key) or '').strip()
      if url:
        return url
  return ''
