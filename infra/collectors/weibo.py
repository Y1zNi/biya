"""微博作品链接采集：$render_data/mblog 优先，Lite DOM 兜底."""

from __future__ import annotations

import asyncio

from playwright.async_api import Page

from infra.collect.runtime_config import get_batch_page_timeout_ms
from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.weibo_parsers import build_item
from infra.collectors.weibo_parsers import dom_fallback
from infra.collectors.weibo_parsers import page as weibo_page
from infra.collectors.weibo_parsers import render_data
from infra.collectors.weibo_parsers.url import parse_note_url
from infra.platform_detect import detect_platform

MOBILE_USER_AGENT = (
  'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
  'AppleWebKit/605.1.15 (KHTML, like Gecko) '
  'Version/16.0 Mobile/15E148 Safari/604.1'
)


async def _ensure_mobile_page(page: Page) -> None:
  try:
    await page.set_viewport_size({'width': 390, 'height': 844})
  except Exception:
    pass


async def collect_one_on_page(page: Page, link: str) -> CollectResultItem:
  platform = detect_platform(link)
  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    status=CollectRowStatus.FAILED,
  )

  info = parse_note_url(link)
  if not info.note_id:
    item.error_msg = '无法解析微博博文 ID'
    return item

  await _ensure_mobile_page(page)

  try:
    await page.goto(
      info.detail_url,
      wait_until='domcontentloaded',
      timeout=get_batch_page_timeout_ms(),
    )
    await asyncio.sleep(2)
  except Exception as exc:
    item.error_msg = f'打开微博详情页失败: {exc}'
    return item

  html = await page.content()

  if await weibo_page.is_login_required(page, html):
    item.error_msg = '登录已过期，请重新登录微博账号'
    item.status = CollectRowStatus.LOGIN_EXPIRED
    return item

  mblog = render_data.extract_mblog_from_html(html)
  if mblog:
    built = build_item.build_item_from_mblog(link, platform.platform_name, mblog, info)
    item = built
  else:
    item.link = info.detail_url
    dom_fallback.fill_from_dom(html, item)
    if info.note_id:
      item.note_id = info.note_id

  item.media_type = weibo_page.infer_media_type(mblog, html)
  return build_item.finalize_item(item)
