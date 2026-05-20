"""抖音页面通用操作."""

from __future__ import annotations

import asyncio
from typing import FrozenSet

from playwright.async_api import Page

from infra.collectors.douyin_parsers.time_util import format_dom_publish_time

LOGIN_COOKIE_NAMES: FrozenSet[str] = frozenset({'sessionid', 'sessionid_ss'})

LOGIN_MODAL_SELECTORS = [
  '[class*="login-panel"]',
  '[class*="login-modal"]',
  '[class*="passport-login"]',
  '[class*="passport"]',
  'motion.div[class*="login"]',
  'motion.div[class*="Login"]',
  'div[class*="login"]',
]


async def dismiss_overlays(page: Page) -> None:
  """关闭登录框、保存个人信息等可能遮挡内容的弹层."""
  try:
    await page.keyboard.press('Escape')
    await asyncio.sleep(0.15)
  except Exception:
    pass

  dismiss_texts = ('我知道了', '知道了', '以后再说', '暂不', '跳过', '关闭')
  for text in dismiss_texts:
    try:
      btn = page.locator(f'text={text}').first
      if await btn.is_visible(timeout=250):
        await btn.click()
        await asyncio.sleep(0.15)
        break
    except Exception:
      continue


async def read_dom_publish_time(page: Page) -> str:
  """读取作品页展示的发布时间（兜底）."""
  try:
    raw = await page.evaluate(
      """() => {
        const el = document.querySelector('.video-create-time .time')
          || document.querySelector('.video-create-time span.time');
        return el && el.textContent ? el.textContent.trim() : '';
      }"""
    )
    return format_dom_publish_time(str(raw) if raw else '')
  except Exception:
    return '-'


async def read_dom_metrics(page: Page) -> dict[str, str]:
  """一次读取互动数据 DOM，无需等待视频加载完成."""
  try:
    raw = await page.evaluate(
      """() => {
        const pick = (sel) => {
          const el = document.querySelector(sel);
          return el && el.textContent ? el.textContent.trim() : '';
        };
        return {
          likes: pick('[data-e2e="digg-count"]'),
          comments: pick('[data-e2e="comment-count"]'),
          favorites: pick('[data-e2e="collect-count"]'),
          shares: pick('[data-e2e="share-count"]'),
        };
      }"""
    )
    return raw if isinstance(raw, dict) else {}
  except Exception:
    return {}


async def has_login_cookies(page: Page) -> bool:
  try:
    cookies = await page.context.cookies()
  except Exception:
    return False
  for cookie in cookies:
    name = cookie.get('name', '')
    if name in LOGIN_COOKIE_NAMES and str(cookie.get('value', '')).strip():
      return True
  return False


async def is_login_modal_visible(page: Page) -> bool:
  for sel in LOGIN_MODAL_SELECTORS:
    try:
      if await page.locator(sel).first.is_visible(timeout=300):
        return True
    except Exception:
      continue
  return False


def is_douyin_page_url(url: str) -> bool:
  lower = (url or '').lower()
  return 'douyin.com' in lower or 'iesdouyin.com' in lower
