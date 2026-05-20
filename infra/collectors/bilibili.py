"""B 站视频链接采集：Web API 优先（/x/web-interface/view/detail）."""

from __future__ import annotations

from typing import Any, Dict, List

from playwright.async_api import Page

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.bilibili_parsers import api_client
from infra.collectors.bilibili_parsers import build_item
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
  if info.is_opus:
    item.status = CollectRowStatus.UNSUPPORTED
    item.error_msg = '暂不支持 opus/动态链接，请使用 /video/BV… 视频链接'
    return item

  if not info.is_video:
    item.error_msg = '无法解析 B 站视频 ID（需要 /video/BV… 或 /video/av…）'
    return item

  cookies: List[Dict[str, Any]] = await page.context.cookies()
  if not await api_client.is_logged_in(cookies):
    item.error_msg = '登录已过期，请重新登录 B 站账号'
    item.status = CollectRowStatus.LOGIN_EXPIRED
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
