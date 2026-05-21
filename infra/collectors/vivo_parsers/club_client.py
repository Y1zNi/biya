"""vivo club 老站：通过页面加载拦截 API 响应（复用浏览器 sign / visitor）."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from playwright.async_api import Page

CLUB_API_THREAD_PREFIX = 'https://club-api.vivo.com.cn/api/v5/threads/'


def _club_thread_page_url(tid: str) -> str:
  return f'https://club.vivo.com.cn/threadDetail/{tid}'


def _club_api_url(tid: str) -> str:
  return f'{CLUB_API_THREAD_PREFIX}{tid}'


def _pick_thread_data(body: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
  if not isinstance(body, dict):
    return None, '接口响应格式异常'
  code = body.get('Code')
  if code != 0:
    message = str(body.get('Message') or '').strip()
    return None, message or f'接口 Code={code}'
  data = body.get('Data')
  if not isinstance(data, dict):
    return None, '接口 Data 为空'
  return data, None


async def fetch_club_thread_data(page: Page, tid: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
  """打开 club 帖子页并拦截 v5/threads 接口 JSON."""
  page_url = _club_thread_page_url(tid)
  api_url = _club_api_url(tid)

  try:
    async with page.expect_response(
      lambda response: api_url in response.url and response.status == 200,
      timeout=60000,
    ) as response_info:
      await page.goto(page_url, wait_until='domcontentloaded', timeout=60000)
    response = await response_info.value
    body = await response.json()
  except Exception as exc:
    return None, str(exc)

  return _pick_thread_data(body)
