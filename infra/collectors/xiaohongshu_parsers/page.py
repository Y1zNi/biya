"""小红书页面交互与登录态检测."""

from __future__ import annotations

import asyncio

from playwright.async_api import Page

XHS_LOGIN_MODAL_SELECTORS = [
  '.login-container',
  '[class*="login-container"]',
  '[class*="login-modal"]',
]

XHS_LOGIN_BUTTON_SELECTORS = [
  '#app button:has-text("登录")',
  'header button:has-text("登录")',
  'text=登录',
]


async def dismiss_overlays(page: Page) -> None:
  try:
    await page.keyboard.press('Escape')
    await asyncio.sleep(0.15)
  except Exception:
    pass

  for text in ('我知道了', '知道了', '以后再说', '暂不', '跳过', '关闭'):
    try:
      btn = page.locator(f'text={text}').first
      if await btn.is_visible(timeout=400):
        await btn.click()
        await asyncio.sleep(0.35)
    except Exception:
      continue


async def is_login_required(page: Page) -> bool:
  for sel in XHS_LOGIN_MODAL_SELECTORS + XHS_LOGIN_BUTTON_SELECTORS:
    try:
      if await page.locator(sel).first.is_visible(timeout=500):
        return True
    except Exception:
      continue
  try:
    content = await page.content()
    if '请通过验证' in content or '扫码登录' in content:
      return True
  except Exception:
    pass
  return False


async def wait_for_note_surface(page: Page) -> None:
  selectors = (
    '[class*="note"]',
    '[class*="interaction"]',
    '[class*="like"]',
    'video',
  )
  for sel in selectors:
    try:
      await page.wait_for_selector(sel, timeout=8000)
      return
    except Exception:
      continue
  await asyncio.sleep(1.5)


async def resolve_note_url(page: Page, link: str) -> str:
  text = (link or '').strip()
  if 'xhslink.com' not in text and 'xhslink' not in text:
    return text
  try:
    await page.goto(text, wait_until='domcontentloaded', timeout=60000)
    await asyncio.sleep(1)
    return page.url
  except Exception:
    return text
