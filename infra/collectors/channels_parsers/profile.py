"""微信视频号助手（登录取昵称）."""

from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page

CHANNELS_LOGIN_URL = 'https://channels.weixin.qq.com/login.html'
CHANNELS_PLATFORM_HOME = 'https://channels.weixin.qq.com/platform/post/list'

NICKNAME_SELECTORS = [
  '[class*="account-name"]',
  '[class*="nick-name"]',
  '[class*="nickname"]',
  '[class*="finder-info"] [class*="name"]',
  '.finder-info-name',
  '.name-text',
  'header [class*="name"]',
]


def _clean_nickname(text: str) -> str:
  if not text:
    return ''
  text = re.sub(r'\s+', ' ', text.strip())
  skip_words = frozenset({
    '登录', '注册', '视频号助手', '微信', '意见反馈', '关于腾讯',
  })
  if not text or text in skip_words or len(text) > 64:
    return ''
  return text


async def fetch_channels_nickname(page: Page) -> str:
  url = (page.url or '').lower()
  if 'login' in url:
    try:
      await page.goto(
        CHANNELS_PLATFORM_HOME,
        wait_until='domcontentloaded',
        timeout=60000,
      )
      await asyncio.sleep(2)
    except Exception:
      pass

  for sel in NICKNAME_SELECTORS:
    try:
      loc = page.locator(sel).first
      if await loc.is_visible(timeout=1500):
        nickname = _clean_nickname(await loc.inner_text())
        if nickname:
          return nickname
    except Exception:
      continue

  try:
    title = await page.title()
    match = re.search(r'^(.+?)\s*[-|]', title or '')
    if match:
      nickname = _clean_nickname(match.group(1))
      if nickname:
        return nickname
  except Exception:
    pass

  return ''
