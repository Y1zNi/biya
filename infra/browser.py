"""Playwright 浏览器上下文（采集用）."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from playwright.async_api import Browser, BrowserContext

from config import COLLECT_HEADLESS, COLLECT_PAGE_TIMEOUT
from infra.database import Account


async def get_or_create_collect_context(
  playwright,
  platform_id: str,
  account: Account,
  cache: Dict[str, Tuple[Browser, BrowserContext]],
  navigation_timeout_ms: Optional[int] = None,
) -> BrowserContext:
  if platform_id in cache:
    return cache[platform_id][1]

  state_path = Path(account.state_file_path)
  browser = await playwright.chromium.launch(
    headless=COLLECT_HEADLESS,
    args=['--disable-blink-features=AutomationControlled'],
  )
  if platform_id == 'weibo':
    viewport = {'width': 390, 'height': 844}
    user_agent = (
      'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
      'AppleWebKit/605.1.15 (KHTML, like Gecko) '
      'Version/16.0 Mobile/15E148 Safari/604.1'
    )
  else:
    viewport = {'width': 1280, 'height': 900}
    user_agent = (
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36'
    )

  context = await browser.new_context(
    storage_state=str(state_path),
    viewport=viewport,
    locale='zh-CN',
    user_agent=user_agent,
  )
  timeout_ms = navigation_timeout_ms if navigation_timeout_ms is not None else COLLECT_PAGE_TIMEOUT
  context.set_default_navigation_timeout(timeout_ms)
  cache[platform_id] = (browser, context)
  return context
