"""B 站链接采集：视频 Web API，图文 opus 页 HTML."""

from __future__ import annotations

from typing import Any, Dict, List

from playwright.async_api import Page

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.bilibili_parsers import api_client
from infra.collectors.bilibili_parsers import build_item
from infra.collectors.bilibili_parsers import opus_html
from infra.collectors.bilibili_parsers import page as bili_page
from infra.collectors.bilibili_parsers.url import parse_video_url
from infra.platform_detect import detect_platform


async def collect_one_on_page(page: Page, link: str) -> CollectResultItem:
  platform = detect_platform(link)
  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    status=CollectRowStatus.FAILED,
  )

  resolved_link = await bili_page.resolve_video_url(page, link)
  info = parse_video_url(resolved_link)

  cookies: List[Dict[str, Any]] = await page.context.cookies()
  if not await api_client.is_logged_in(cookies):
    item.error_msg = '登录已过期，请重新登录 B 站账号'
    item.status = CollectRowStatus.LOGIN_EXPIRED
    return item

  if info.is_opus:
    state, err_msg = await opus_html.fetch_opus_state(cookies, info.opus_id)
    if not state:
      item.error_msg = err_msg or '未能获取图文详情'
      return item
    author, stat = opus_html.extract_modules(state)
    built = build_item.build_item_from_opus(
      resolved_link or link,
      platform.platform_name,
      state,
      info,
      author=author,
      stat=stat,
    )
    if resolved_link and resolved_link != link:
      built.link = info.build_canonical_opus_url() or resolved_link
    return build_item.finalize_item(built)

  if not info.is_video:
    item.error_msg = '无法解析 B 站链接（需要 /video/BV…、/video/av… 或 /opus/…）'
    return item

  detail, err_msg, login_expired = await api_client.fetch_video_detail(cookies, info)
  if login_expired:
    item.error_msg = '登录已过期，请重新登录 B 站账号'
    item.status = CollectRowStatus.LOGIN_EXPIRED
    return item

  if not detail:
    item.error_msg = err_msg or '未能获取视频详情'
    return item

  built = build_item.build_item_from_detail(
    resolved_link or link,
    platform.platform_name,
    detail,
    info,
  )
  if resolved_link and resolved_link != link:
    built.link = resolved_link
  return build_item.finalize_item(built)
