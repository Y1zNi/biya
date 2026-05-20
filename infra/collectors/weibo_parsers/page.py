"""微博页面检测与类型推断."""

from __future__ import annotations

import re

from playwright.async_api import Page

PASSPORT_HOST_MARKERS = ('passport.weibo.com', 'login.sina.com.cn')


def infer_media_type_from_html(html: str) -> str:
  text = html or ''
  if re.search(r'class="weibo-rp"[^>]*>', text):
    return '转发'

  video_player_match = re.search(
    r'class="video-player[^"]*"[^>]*style="[^"]*display:\s*none',
    text,
    re.I,
  )
  has_visible_video = bool(
    re.search(r'class="video-player[^"]*"', text, re.I)
    and not video_player_match,
  )
  if has_visible_video or re.search(r'<video[^>]+class="vjs-tech"', text, re.I):
    return '视频'

  if re.search(r'weibo-media-wraps|weibo-media\s', text, re.I):
    if re.search(r'<img[^>]+sinaimg\.cn', text, re.I):
      return '图文'

  if re.search(r'class="weibo-text"', text, re.I):
    return '纯文字'

  return '-'


async def is_login_required(page: Page, html: str) -> bool:
  url = (page.url or '').lower()
  if any(marker in url for marker in PASSPORT_HOST_MARKERS):
    return True

  if 'showPSWLogin' in html and 'weibo-top' not in html and 'profile-header' not in html:
    return True

  if '请先登录' in html or '登录后' in html:
    return True

  return False
