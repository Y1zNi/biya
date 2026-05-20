"""vivo 社区帖子采集：HTTP 拉取 SSR + 解析 __NUXT__."""

from __future__ import annotations

from typing import Any, Dict, List

from playwright.async_api import Page

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.vivo_parsers import build_item, http_client, nuxt
from infra.collectors.vivo_parsers.url import parse_thread_url
from infra.platform_detect import detect_platform


async def collect_one_on_page(page: Page, link: str) -> CollectResultItem:
  platform = detect_platform(link)
  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    status=CollectRowStatus.FAILED,
  )

  info = parse_thread_url(link)
  if not info.is_thread:
    item.status = CollectRowStatus.UNSUPPORTED
    item.error_msg = '仅支持 vivo 社区帖子链接（/newbbs/thread/数字）'
    return item

  cookies: List[Dict[str, Any]] = await page.context.cookies()
  if not http_client.is_logged_in(cookies):
    item.error_msg = '登录已过期，请重新登录 vivo 社区账号'
    item.status = CollectRowStatus.LOGIN_EXPIRED
    return item

  canonical = info.build_canonical_url()
  thread_data = None

  html, err_msg, login_expired, _final_url = await http_client.fetch_thread_html(
    cookies,
    info,
  )
  if login_expired:
    item.error_msg = '登录已过期，请重新登录 vivo 社区账号'
    item.status = CollectRowStatus.LOGIN_EXPIRED
    return item

  if html:
    thread_data = await nuxt.extract_thread_data_from_html(page, html)

  if not thread_data:
    try:
      await page.goto(canonical, wait_until='domcontentloaded', timeout=60000)
      thread_data = await nuxt.extract_thread_data_from_page(page)
    except Exception as exc:
      if not err_msg:
        err_msg = str(exc)

  if not thread_data:
    item.error_msg = err_msg or '未能解析帖子数据（__NUXT__）'
    return item

  built = build_item.build_item_from_thread(
    canonical,
    platform.platform_name,
    thread_data,
    info,
  )
  return build_item.finalize_item(built)
