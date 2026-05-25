"""拉取作者主页并解析小红书号（red_id）."""

from __future__ import annotations

from typing import List, Optional

from playwright.async_api import Page

from infra.collectors.xiaohongshu_parsers import initial_state as xhs_initial_state
from infra.collectors.xiaohongshu_parsers.api_client import DEFAULT_USER_AGENT, cookies_to_header
from infra.collectors.xiaohongshu_parsers.url import (
  NoteUrlInfo,
  ProfileUrlInfo,
  build_profile_url,
  parse_profile_href,
  profile_url_from_note_page_html,
)

_PROFILE_LINK_SELECTORS = (
  '#noteContainer a[href*="/user/profile/"]',
  'a[href*="/user/profile/"]',
)


def _is_valid_author_id(author_id: str) -> bool:
  text = (author_id or '').strip()
  return bool(text) and text != '-' and len(text) == 24


def _profile_attempt_urls(
  user_id: str,
  note_info: NoteUrlInfo,
  *,
  page_profile: Optional[ProfileUrlInfo] = None,
  html_profile: Optional[ProfileUrlInfo] = None,
) -> List[str]:
  seen: set[str] = set()
  urls: List[str] = []

  def add(url: str) -> None:
    text = (url or '').strip()
    if not text or text in seen:
      return
    seen.add(text)
    urls.append(text)

  for profile in (page_profile, html_profile):
    if not profile or profile.user_id.lower() != user_id.lower():
      continue
    if profile.xsec_token:
      add(build_profile_url(
        user_id,
        xsec_token=profile.xsec_token,
        xsec_source=profile.xsec_source,
      ))

  if note_info.xsec_token:
    add(build_profile_url(
      user_id,
      xsec_token=note_info.xsec_token,
      xsec_source=note_info.xsec_source or 'pc_note',
    ))

  add(build_profile_url(user_id))
  return urls


async def _extract_profile_from_page(page: Page, user_id: str) -> Optional[ProfileUrlInfo]:
  for sel in _PROFILE_LINK_SELECTORS:
    try:
      loc = page.locator(sel).first
      href = await loc.get_attribute('href', timeout=2000)
      if not href:
        continue
      profile = parse_profile_href(href)
      if profile and profile.user_id.lower() == user_id.lower():
        return profile
    except Exception:
      continue
  return None


async def fetch_author_red_id(
  page: Page,
  note_info: NoteUrlInfo,
  author_id: str,
  *,
  note_page_html: Optional[str] = None,
) -> str:
  if not _is_valid_author_id(author_id):
    return ''

  html_profile = profile_url_from_note_page_html(note_page_html or '', author_id)
  page_profile: Optional[ProfileUrlInfo] = None
  if note_page_html is not None:
    page_profile = await _extract_profile_from_page(page, author_id)

  urls = _profile_attempt_urls(
    author_id,
    note_info,
    page_profile=page_profile,
    html_profile=html_profile,
  )
  if not urls:
    return ''

  cookies = await page.context.cookies()
  cookie_str = cookies_to_header(cookies)
  referer = page.url or ''

  for profile_url in urls:
    red_id = await _fetch_red_id_from_profile_url(
      page,
      profile_url,
      cookie_str=cookie_str,
      referer=referer,
    )
    if red_id:
      return red_id
  return ''


async def _fetch_red_id_from_profile_url(
  page: Page,
  profile_url: str,
  *,
  cookie_str: str,
  referer: str,
) -> str:
  headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'User-Agent': DEFAULT_USER_AGENT,
    'Cookie': cookie_str,
  }
  if referer:
    headers['Referer'] = referer
  try:
    response = await page.context.request.get(
      profile_url,
      headers=headers,
      timeout=30000,
    )
    if response.status != 200:
      return ''
    html = await response.text()
  except Exception:
    return ''
  return xhs_initial_state.red_id_from_initial_state_html(html)
