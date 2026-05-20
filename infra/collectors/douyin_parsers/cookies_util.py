"""浏览器 Cookie 转换工具."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from playwright.async_api import BrowserContext


def convert_cookies(cookies: Optional[list]) -> Tuple[str, Dict[str, str]]:
  if not cookies:
    return '', {}
  cookie_str = ';'.join([f"{c.get('name')}={c.get('value')}" for c in cookies])
  cookie_dict = {c.get('name'): c.get('value') for c in cookies}
  return cookie_str, cookie_dict


async def convert_browser_context_cookies(
  browser_context: BrowserContext,
  urls: Optional[List[str]] = None,
) -> Tuple[str, Dict[str, str]]:
  cookies = (
    await browser_context.cookies(urls=urls)
    if urls
    else await browser_context.cookies()
  )
  return convert_cookies(cookies)
