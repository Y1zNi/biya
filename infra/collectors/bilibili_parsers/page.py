"""B 站页面辅助：短链跳转解析."""

from __future__ import annotations

import asyncio

import httpx
from playwright.async_api import Page

from infra.collect.runtime_config import get_batch_page_timeout_ms
from infra.collectors.bilibili_parsers.api_client import DEFAULT_USER_AGENT
from infra.collectors.bilibili_parsers.url import needs_url_resolve, parse_video_url


async def resolve_via_http(link: str, *, timeout: float = 20.0) -> str:
  text = (link or '').strip()
  if not text:
    return text
  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  headers = {'User-Agent': DEFAULT_USER_AGENT}
  try:
    async with httpx.AsyncClient(
      follow_redirects=True,
      timeout=timeout,
      headers=headers,
    ) as client:
      response = await client.get(text)
      final_url = str(response.url)
      if parse_video_url(final_url).is_video or parse_video_url(final_url).is_opus:
        return final_url
  except Exception:
    pass
  return text


async def resolve_video_url(page: Page, link: str) -> str:
  """将 b23.tv 等短链解析为最终视频/opus URL."""
  text = (link or '').strip()
  if not needs_url_resolve(text):
    return text

  resolved = await resolve_via_http(text)
  if not needs_url_resolve(resolved):
    return resolved

  try:
    await page.goto(text, wait_until='domcontentloaded', timeout=get_batch_page_timeout_ms())
    await asyncio.sleep(1.2)
    final_url = page.url or text
    if parse_video_url(final_url).is_video or parse_video_url(final_url).is_opus:
      return final_url
  except Exception:
    pass

  return resolved or text
