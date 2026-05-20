"""微博个人主页（登录取昵称）."""

from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page

WEIBO_HOME_URL = 'https://m.weibo.cn'
PROFILE_NICKNAME_SELECTOR = '.profile-header .prf-detail h3 span.m-text-cut'


async def read_uid_from_page(page: Page) -> str:
  try:
    uid = await page.evaluate(
      """() => {
        if (window.config && window.config.uid) {
          return String(window.config.uid);
        }
        return '';
      }""",
    )
    return str(uid or '').strip()
  except Exception:
    return ''


def parse_nickname_from_html(html: str) -> str:
  match = re.search(
    r'class="prf-detail"[^>]*>.*?<span class="m-text-cut">\s*([^<]+?)\s*</span>',
    html or '',
    re.I | re.S,
  )
  if match:
    return match.group(1).strip()

  title_match = re.search(r'<title>\s*(.+?)的微博\s*</title>', html or '', re.I)
  if title_match:
    return title_match.group(1).strip()
  return ''


async def fetch_weibo_nickname(page: Page) -> str:
  await page.goto(WEIBO_HOME_URL, wait_until='domcontentloaded', timeout=60000)
  await asyncio.sleep(2)

  uid = await read_uid_from_page(page)
  if uid:
    await page.goto(
      f'{WEIBO_HOME_URL}/profile/{uid}',
      wait_until='domcontentloaded',
      timeout=60000,
    )
  else:
    try:
      await page.locator('.lite-iconf-profile').first.click(timeout=8000)
    except Exception:
      pass
    await page.wait_for_load_state('domcontentloaded')

  try:
    await page.wait_for_selector('.profile-header .prf-detail', timeout=15000)
  except Exception:
    pass

  await asyncio.sleep(1)

  try:
    nickname = await page.locator(PROFILE_NICKNAME_SELECTOR).first.inner_text(timeout=5000)
    nickname = (nickname or '').strip()
    if nickname:
      return nickname[:64]
  except Exception:
    pass

  html = await page.content()
  return parse_nickname_from_html(html)[:64]
