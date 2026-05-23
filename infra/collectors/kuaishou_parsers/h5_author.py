"""H5 分享页作者 uid / eid 补全（仅在常规解析失败时使用）."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from infra.collectors.kuaishou_parsers import ids as kuaishou_ids
from infra.collectors.kuaishou_parsers import render_data
from infra.collectors.kuaishou_parsers.h5_state import photo_matches_target_h5, share_info_photo_id

_AUTHOR_HINT_KEYS = frozenset({
  'author',
  'user',
  'profile',
  'userProfile',
  'userInfo',
  'user_info',
})

_HEADURL_KEYS = ('headerUrl', 'header_url', 'headurl', 'headUrl', 'avatar', 'coverUrl', 'cover_url')

_HTML_UID_RE = re.compile(
  r'"(?:userId|authorId|fid)"\s*:\s*"?(\d{8,15})"?',
  re.I,
)
_HTML_EID_RE = re.compile(
  r'"(?:efid|userEid|user_eid|eid)"\s*:\s*"([^"]{6,})"',
  re.I,
)


def _empty_hints() -> Dict[str, str]:
  return {'uid': '', 'eid': '', 'headurl': ''}


def _merge_hints(base: Dict[str, str], extra: Dict[str, str]) -> Dict[str, str]:
  merged = dict(base)
  for key in ('uid', 'eid', 'headurl'):
    if merged.get(key):
      continue
    value = str(extra.get(key) or '').strip()
    if value:
      merged[key] = value
  return merged


def _hints_from_author_dict(author: Dict[str, Any]) -> Dict[str, str]:
  if not author:
    return _empty_hints()
  uid = kuaishou_ids.photo_author_uid({}, author)
  eid = kuaishou_ids.photo_author_eid({}, author)
  headurl = ''
  for key in _HEADURL_KEYS:
    text = str(author.get(key) or '').strip()
    if text:
      headurl = text
      break
  if not uid and headurl:
    uid = kuaishou_ids.extract_uid_from_cdn_url(headurl)
  return {'uid': uid, 'eid': eid, 'headurl': headurl}


def _hints_from_photo_dict(photo: Dict[str, Any]) -> Dict[str, str]:
  author = render_data.get_author_from_photo(photo)
  hints = _hints_from_author_dict(author)
  if not hints['uid']:
    hints['uid'] = kuaishou_ids.photo_author_uid(photo, author)
  if not hints['eid']:
    hints['eid'] = kuaishou_ids.photo_author_eid(photo, author)
  if not hints['headurl']:
    hints['headurl'] = kuaishou_ids.cdn_url_from_photo(photo, author)
  if not hints['uid'] and hints['headurl']:
    hints['uid'] = kuaishou_ids.extract_uid_from_cdn_url(hints['headurl'])
  if not hints['eid']:
    hints['eid'] = kuaishou_ids.photo_author_eid(photo, author)
  return hints


def _photo_id_matches(photo: Dict[str, Any], target_photo_id: str) -> bool:
  if not target_photo_id:
    return False
  if photo_matches_target_h5(photo, target_photo_id):
    return True
  if render_data.get_photo_id_from_detail(photo) == target_photo_id:
    return True
  if share_info_photo_id(photo) == target_photo_id:
    return True
  return False


def _collect_photo_hint_candidates(
  obj: Any,
  target_photo_id: str,
  depth: int,
  bucket: List[Dict[str, str]],
) -> None:
  if depth > 14:
    return

  if isinstance(obj, dict):
    if target_photo_id and _photo_id_matches(obj, target_photo_id):
      bucket.append(_hints_from_photo_dict(obj))

    for key in _AUTHOR_HINT_KEYS:
      value = obj.get(key)
      if isinstance(value, dict):
        bucket.append(_hints_from_author_dict(value))

    for key in _HEADURL_KEYS:
      headurl = str(obj.get(key) or '').strip()
      if headurl:
        uid = kuaishou_ids.extract_uid_from_cdn_url(headurl)
        if uid:
          bucket.append({'uid': uid, 'eid': '', 'headurl': headurl})

    for value in obj.values():
      _collect_photo_hint_candidates(value, target_photo_id, depth + 1, bucket)

  elif isinstance(obj, list):
    for item in obj[:160]:
      _collect_photo_hint_candidates(item, target_photo_id, depth + 1, bucket)


def _pick_best_hint(candidates: List[Dict[str, str]]) -> Dict[str, str]:
  if not candidates:
    return _empty_hints()

  def score(item: Dict[str, str]) -> Tuple[int, int]:
    uid = item.get('uid') or ''
    plausible = 1 if kuaishou_ids.is_plausible_author_uid(uid) else 0
    return (plausible, len(uid))

  best = max(candidates, key=score)
  merged = _empty_hints()
  for item in sorted(candidates, key=score, reverse=True):
    merged = _merge_hints(merged, item)
  if not merged['uid'] and best.get('uid'):
    merged['uid'] = best['uid']
  return merged


def collect_author_hints_from_state(
  state: Any,
  target_photo_id: Optional[str] = None,
) -> Dict[str, str]:
  """在 INIT_STATE 中查找与目标作品相关的作者 uid / eid / 头像."""
  target = str(target_photo_id or '').strip()
  if state is None:
    return _empty_hints()

  candidates: List[Dict[str, str]] = []
  _collect_photo_hint_candidates(state, target, 0, candidates)

  if not target:
    for photo in render_data.collect_photo_details(state):
      candidates.append(_hints_from_photo_dict(photo))

  return _pick_best_hint(candidates)


def collect_author_hints_from_html(html: str, target_photo_id: Optional[str] = None) -> Dict[str, str]:
  """从页面 HTML 文本中兜底提取 uid / eid（靠近作品 id 的片段优先）."""
  text = str(html or '')
  if not text:
    return _empty_hints()

  target = str(target_photo_id or '').strip()
  hints = _empty_hints()

  if target and target in text:
    idx = text.find(target)
    window = text[max(0, idx - 2500): idx + 4500]
    uid_match = _HTML_UID_RE.search(window)
    if uid_match and kuaishou_ids.is_numeric_uid(uid_match.group(1)):
      hints['uid'] = uid_match.group(1).strip()
    eid_match = _HTML_EID_RE.search(window)
    if eid_match:
      eid = eid_match.group(1).strip()
      if eid and not kuaishou_ids.is_numeric_uid(eid):
        hints['eid'] = eid

  if not hints['uid']:
    for match in _HTML_UID_RE.finditer(text):
      uid = match.group(1).strip()
      if kuaishou_ids.is_plausible_author_uid(uid):
        hints['uid'] = uid
        break

  if not hints['eid']:
    for match in _HTML_EID_RE.finditer(text):
      eid = match.group(1).strip()
      if eid and not kuaishou_ids.is_numeric_uid(eid):
        hints['eid'] = eid
        break

  return hints


def parse_author_hints_from_href(href: str) -> Dict[str, str]:
  parsed = urlparse(str(href or '').strip())
  if not parsed.scheme and not parsed.netloc:
    return _empty_hints()

  query = parse_qs(parsed.query)
  hints = _empty_hints()

  for key in ('fid',):
    values = query.get(key) or query.get(key.lower())
    if values:
      text = str(values[0]).strip()
      if kuaishou_ids.is_numeric_uid(text):
        hints['uid'] = text
        break

  for key in ('efid', 'userEid', 'user_eid', 'eid'):
    values = query.get(key) or query.get(key.lower())
    if values:
      text = str(values[0]).strip()
      if text and not kuaishou_ids.is_numeric_uid(text):
        hints['eid'] = text
        break

  values = query.get('userId') or query.get('userid')
  if values:
    text = str(values[0]).strip()
    if kuaishou_ids.is_numeric_uid(text):
      hints['uid'] = hints['uid'] or text
    elif text:
      hints['eid'] = hints['eid'] or text

  path = parsed.path or ''
  profile_match = re.search(r'/profile/([^/?#]+)', path, re.I)
  if profile_match:
    token = profile_match.group(1).strip()
    if token and kuaishou_ids.is_numeric_uid(token):
      hints['uid'] = hints['uid'] or token
    elif token:
      hints['eid'] = hints['eid'] or token

  return hints
