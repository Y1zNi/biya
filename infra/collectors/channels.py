"""微信视频号作品链接采集：finder-preview get_feed_info API（无需登录）."""

from __future__ import annotations

from playwright.async_api import Page

from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.channels_parsers import api_client
from infra.collectors.channels_parsers import build_item
from infra.collectors.channels_parsers.url import parse_channels_url
from infra.platform_detect import detect_platform


async def collect_one_on_page(page: Page, link: str) -> CollectResultItem:
  platform = detect_platform(link)
  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    status=CollectRowStatus.FAILED,
  )

  info = parse_channels_url(link)
  if not info.is_valid:
    item.error_msg = '无法解析视频号作品短码（需要 weixin.qq.com/sph/… 链接）'
    return item

  # 有登录态则带上 Cookie，未登录则用空 Cookie 继续请求（公开预览接口通常仍可用）
  cookies = await page.context.cookies()
  data, err_msg = await api_client.fetch_feed_info(cookies, info.short_uri)

  if not data:
    item.error_msg = err_msg or '未能获取视频号作品详情'
    return item

  built = build_item.build_item_from_feed(
    link,
    platform.platform_name,
    data,
    info,
  )
  return build_item.finalize_item(built)
