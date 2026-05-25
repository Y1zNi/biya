"""微博页面检测与类型推断."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from playwright.async_api import Page

PASSPORT_HOST_MARKERS = ('passport.weibo.com', 'login.sina.com.cn')


def _mblog_has_retweet(mblog: Dict[str, Any]) -> bool:
  retweeted = mblog.get('retweeted_status')
  return isinstance(retweeted, dict) and bool(retweeted)


def _page_info_is_video(page_info: Dict[str, Any]) -> bool:
  for key in ('type', 'object_type', 'page_type'):
    value = str(page_info.get(key) or '').strip().lower()
    if value == 'video':
      return True
  return False


def _mblog_has_video(mblog: Dict[str, Any]) -> bool:
  page_info = mblog.get('page_info')
  if isinstance(page_info, dict) and _page_info_is_video(page_info):
    return True

  if mblog.get('stream'):
    return True

  mix_media = mblog.get('mix_media_info') or mblog.get('mix_media')
  if isinstance(mix_media, dict):
    items = mix_media.get('items') or mix_media.get('mix_media_items') or []
    if isinstance(items, list):
      for item in items:
        if not isinstance(item, dict):
          continue
        media_type = str(item.get('type') or item.get('media_type') or '').lower()
        if media_type == 'video':
          return True

  for key in ('url_struct', 'url_objects'):
    entries = mblog.get(key)
    if not isinstance(entries, list):
      continue
    for entry in entries:
      if not isinstance(entry, dict):
        continue
      obj = entry.get('object')
      if isinstance(obj, dict):
        obj_type = str(obj.get('object_type') or '').lower()
        if obj_type == 'video':
          return True
      entry_type = str(entry.get('object_type') or '').lower()
      if entry_type == 'video':
        return True

  return False


def _mblog_has_pics(mblog: Dict[str, Any]) -> bool:
  pic_ids = mblog.get('pic_ids')
  if isinstance(pic_ids, list) and pic_ids:
    return True

  pics = mblog.get('pics')
  if isinstance(pics, list) and pics:
    return True

  try:
    if int(mblog.get('pic_num') or 0) > 0:
      return True
  except (TypeError, ValueError):
    pass

  return bool(
    mblog.get('thumbnail_pic')
    or mblog.get('bmiddle_pic')
    or mblog.get('original_pic'),
  )


def infer_media_type_from_mblog(mblog: Optional[Dict[str, Any]]) -> str:
  """从 $render_data status(mblog) 推断类型，与微博接口字段一致."""
  if not isinstance(mblog, dict):
    return ''

  if _mblog_has_retweet(mblog):
    return '转发'
  if _mblog_has_video(mblog):
    return '视频'
  if _mblog_has_pics(mblog):
    return '图文'
  if str(mblog.get('text') or '').strip():
    return '纯文字'
  return ''


def infer_media_type_from_html(html: str) -> str:
  text = html or ''
  if re.search(r'class="weibo-rp"[^>]*>', text):
    return '转发'

  video_player_hidden = re.search(
    r'class="video-player[^"]*"[^>]*style="[^"]*display:\s*none',
    text,
    re.I,
  )
  has_visible_video = bool(
    re.search(r'class="video-player[^"]*"', text, re.I)
    and not video_player_hidden,
  )
  if has_visible_video:
    return '视频'

  if re.search(r'weibo-media-wraps|weibo-media\s', text, re.I):
    if re.search(r'<img[^>]+sinaimg\.cn', text, re.I):
      return '图文'

  if re.search(r'class="weibo-text"', text, re.I):
    return '纯文字'

  return '-'


def infer_media_type(
  mblog: Optional[Dict[str, Any]],
  html: str,
) -> str:
  """mblog 优先；无 mblog 或字段不足时回退 HTML DOM 规则."""
  from_mblog = infer_media_type_from_mblog(mblog)
  if from_mblog:
    return from_mblog
  return infer_media_type_from_html(html)


async def is_login_required(page: Page, html: str) -> bool:
  url = (page.url or '').lower()
  if any(marker in url for marker in PASSPORT_HOST_MARKERS):
    return True

  if 'showPSWLogin' in html and 'weibo-top' not in html and 'profile-header' not in html:
    return True

  if '请先登录' in html or '登录后' in html:
    return True

  return False
