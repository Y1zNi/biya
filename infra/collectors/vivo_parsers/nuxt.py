"""从 SSR 页面 __NUXT__ 提取帖子 threadData."""

from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.async_api import Page

EXTRACT_THREAD_DATA_JS = """
() => {
  const nuxt = window.__NUXT__;
  if (!nuxt || !Array.isArray(nuxt.data) || !nuxt.data[0]) {
    return null;
  }
  const threadData = nuxt.data[0].threadData;
  if (!threadData || !threadData.tid) {
    return null;
  }
  return threadData;
}
"""


def pick_thread_data(nuxt_payload: Any) -> Optional[Dict[str, Any]]:
  if not isinstance(nuxt_payload, dict):
    return None
  data = nuxt_payload.get('data')
  if not isinstance(data, list) or not data:
    return None
  first = data[0]
  if not isinstance(first, dict):
    return None
  thread_data = first.get('threadData')
  if not isinstance(thread_data, dict):
    return None
  tid = str(thread_data.get('tid') or '').strip()
  if not tid:
    return None
  return thread_data


async def extract_thread_data_from_page(page: Page) -> Optional[Dict[str, Any]]:
  try:
    payload = await page.evaluate(EXTRACT_THREAD_DATA_JS)
    if isinstance(payload, dict):
      return payload
  except Exception:
    pass
  return None


async def extract_thread_data_from_html(page: Page, html: str) -> Optional[Dict[str, Any]]:
  if not html or '__NUXT__' not in html:
    return None
  try:
    await page.set_content(html, wait_until='domcontentloaded', timeout=30000)
  except Exception:
    return None
  return await extract_thread_data_from_page(page)
