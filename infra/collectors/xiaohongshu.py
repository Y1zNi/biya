"""小红书作品链接采集：API feed 优先，HTML __INITIAL_STATE__ 兜底."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

from infra.collect.runtime_config import get_batch_page_timeout_ms
from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.xiaohongshu_parsers import api_client
from infra.collectors.xiaohongshu_parsers import build_item
from infra.collectors.xiaohongshu_parsers import extractor
from infra.collectors.xiaohongshu_parsers import page as xhs_page
from infra.collectors.xiaohongshu_parsers import profile as xhs_profile
from infra.collectors.xiaohongshu_parsers.url import NoteUrlInfo, build_explore_url, parse_note_url
from infra.platform_detect import detect_platform


async def collect_one_on_page(page: Page, link: str) -> CollectResultItem:
  platform = detect_platform(link)
  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    status=CollectRowStatus.FAILED,
  )

  resolved_link = await xhs_page.resolve_note_url(page, link)
  info = parse_note_url(resolved_link or link)
  if not info.note_id:
    item.error_msg = '无法解析小红书笔记 ID'
    return item

  if not info.xsec_token:
    item.error_msg = '链接缺少 xsec_token，请使用小红书 App 分享的完整链接'
    return item

  cookies: List[Dict[str, Any]] = await page.context.cookies()
  note: Optional[Dict[str, Any]] = await api_client.fetch_note_by_id(cookies, info)
  note_page_html: Optional[str] = None

  if not note:
    explore_url = build_explore_url(info)
    try:
      await page.goto(explore_url, wait_until='domcontentloaded', timeout=get_batch_page_timeout_ms())
      await xhs_page.wait_for_note_surface(page)
      await xhs_page.dismiss_overlays(page)
      await asyncio.sleep(1)

      if await xhs_page.is_login_required(page):
        item.error_msg = '登录已过期，请重新登录小红书账号'
        item.status = CollectRowStatus.LOGIN_EXPIRED
        return item

      html = await page.content()
      note_page_html = html
      note = extractor.extract_note_detail_from_html(info.note_id, html)
      item.link = page.url or explore_url
    except Exception as exc:
      item.error_msg = f'打开笔记页失败: {exc}'
      return item

  if not note:
    item.error_msg = '未能从 API 或页面 HTML 获取笔记详情（验证码/笔记不存在/token 失效）'
    return item

  built = build_item.build_item_from_note(
    resolved_link or link,
    platform.platform_name,
    note,
    info,
  )
  if item.link and item.link != link:
    built.link = item.link

  built = build_item.finalize_item(built)
  if built.status == CollectRowStatus.SUCCESS:
    red_id = await xhs_profile.fetch_author_red_id(
      page,
      info,
      built.author_id,
      note_page_html=note_page_html,
    )
    if red_id:
      built.author_sec_uid = red_id
  return built
