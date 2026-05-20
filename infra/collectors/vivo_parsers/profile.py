"""vivo 社区登录后昵称读取."""

from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page

VIVO_BBS_HOME_URL = 'https://bbs.vivo.com.cn/newbbs/'

VIVO_NICKNAME_SELECTORS = [
  '.login-container .login-main-left span.name.ellipsis',
  '.login-main-left span.name',
  'span.name.ellipsis',
]


def parse_nickname_from_nuxt_html(html: str) -> str:
  match = re.search(
    r'"user"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"',
    html or '',
    re.I | re.S,
  )
  if match:
    return match.group(1).strip()
  return ''


async def fetch_vivo_nickname(page: Page) -> str:
  try:
    if 'bbs.vivo.com.cn' not in (page.url or ''):
      await page.goto(VIVO_BBS_HOME_URL, wait_until='domcontentloaded', timeout=60000)
      await asyncio.sleep(2)
  except Exception:
    pass

  for sel in VIVO_NICKNAME_SELECTORS:
    try:
      loc = page.locator(sel).first
      if await loc.is_visible(timeout=5000):
        text = (await loc.inner_text()).strip()
        if text and text not in ('登录', '注册', '立即登录'):
          return text[:64]
    except Exception:
      continue

  try:
    nickname = await page.evaluate(
      """() => {
        const state = window.__NUXT__ && window.__NUXT__.state;
        const user = state && state.user && state.user.user;
        if (user && user.name) {
          return String(user.name).trim();
        }
        return '';
      }""",
    )
    nickname = str(nickname or '').strip()
    if nickname:
      return nickname[:64]
  except Exception:
    pass

  try:
    html = await page.content()
    nickname = parse_nickname_from_nuxt_html(html)
    if nickname:
      return nickname[:64]
  except Exception:
    pass

  return ''
