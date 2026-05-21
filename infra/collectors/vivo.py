"""vivo 社区帖子采集：新站 bbs（__NUXT__）与 club 老站（API 拦截）."""

from __future__ import annotations

from playwright.async_api import Page

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.vivo_parsers import build_item, club_client, http_client, nuxt
from infra.collectors.vivo_parsers.club_url import parse_club_thread_url
from infra.collectors.vivo_parsers.url import parse_thread_url
from infra.platform_detect import detect_platform


async def _collect_club_on_page(
  page: Page,
  link: str,
  platform_name: str,
) -> CollectResultItem:
  club_info = parse_club_thread_url(link)
  canonical = club_info.build_canonical_url()
  item = CollectResultItem(
    link=link,
    platform_id='vivo',
    platform_name=platform_name,
    status=CollectRowStatus.FAILED,
  )

  data, err_msg = await club_client.fetch_club_thread_data(page, club_info.tid)
  if not data:
    item.error_msg = err_msg or '未能获取 club 帖子数据'
    return item

  built = build_item.build_item_from_club(
    canonical,
    platform_name,
    data,
    club_info.tid,
  )
  return build_item.finalize_item(built)


async def collect_one_on_page(page: Page, link: str) -> CollectResultItem:
  platform = detect_platform(link)
  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    status=CollectRowStatus.FAILED,
  )

  club_info = parse_club_thread_url(link)
  if club_info.is_thread:
    return await _collect_club_on_page(page, link, platform.platform_name)

  info = parse_thread_url(link)
  if not info.is_thread:
    item.status = CollectRowStatus.UNSUPPORTED
    item.error_msg = (
      '仅支持 vivo 社区帖子链接（bbs: /newbbs/thread/数字；club: /threadDetail/数字）'
    )
    return item

  cookies = await page.context.cookies()
  canonical = info.build_canonical_url()
  thread_data = None

  html, err_msg, _final_url = await http_client.fetch_thread_html(cookies, info)

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
