"""抖音作品链接采集（MediaCrawler detail API，无作品页 goto 兜底）."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from playwright.async_api import BrowserContext, Page

from config import COLLECT_PAGE_TIMEOUT, COLLECT_REQUEST_INTERVAL
from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.douyin_parsers import number_format, render_data, url as douyin_url
from infra.collectors.douyin_parsers.api_client import (
  DataFetchError,
  DouyinApiClient,
  create_douyin_api_client,
)
from infra.collectors.douyin_parsers.page import has_login_cookies
from infra.collectors.douyin_parsers.time_util import format_publish_time
from infra.platform_detect import detect_platform

DOUYIN_INDEX_URL = 'https://www.douyin.com'

NOTE_AWEME_TYPES = frozenset({68, 101, 102})
VIDEO_AWEME_TYPES = frozenset({0, 4, 61})

INVALID_AUTHOR_NAMES = frozenset({
  '我的',
  '登录',
  '首页',
  '推荐',
  '关注',
  '朋友',
  '搜索',
  '消息',
  '直播',
  '探索',
  '开拍',
  '放映厅',
})

_SESSION_PAGES: dict[int, Page] = {}
_API_CLIENTS: dict[int, DouyinApiClient] = {}


def map_aweme_type(aweme_type: Any, page_url: str) -> str:
  url_lower = (page_url or '').lower()
  if '/note/' in url_lower:
    return '图片'
  if '/video/' in url_lower:
    return '视频'

  try:
    type_value = int(aweme_type)
  except (TypeError, ValueError):
    return '-'

  if type_value in NOTE_AWEME_TYPES:
    return '图片'
  if type_value in VIDEO_AWEME_TYPES:
    return '视频'
  return '视频'


def is_plausible_author(name: str) -> bool:
  text = (name or '').strip()
  if not text or text == '-':
    return False
  if text in INVALID_AUTHOR_NAMES:
    return False
  return len(text) >= 2


def has_meaningful_metrics(item: CollectResultItem) -> bool:
  fields = (
    item.views,
    item.likes,
    item.favorites,
    item.comments,
    item.shares,
    item.media_type,
  )
  return any(value not in ('-', '', '0') for value in fields)


def is_collect_success(item: CollectResultItem) -> bool:
  return has_meaningful_metrics(item) or is_plausible_author(item.author_name)


def build_item_from_aweme(
  link: str,
  page_url: str,
  aweme: Dict[str, Any],
) -> CollectResultItem:
  platform = detect_platform(link)
  author = aweme.get('author') or {}
  statistics = render_data.get_statistics_from_aweme(aweme)

  play_count = statistics.get('play_count', statistics.get('playCount'))
  views = number_format.format_count(play_count)
  if views == '0':
    views = '-'

  author_name = str(
    author.get('nickname') or author.get('nick_name') or author.get('unique_id') or '',
  ).strip()
  if not is_plausible_author(author_name):
    author_name = '-'

  create_time = aweme.get('create_time', aweme.get('createTime'))
  publish_time = format_publish_time(create_time)

  return CollectResultItem(
    link=page_url or link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    author_name=author_name,
    publish_time=publish_time,
    views=views,
    likes=number_format.format_count(
      statistics.get('digg_count', statistics.get('diggCount')),
    ),
    favorites=number_format.format_count(
      statistics.get('collect_count', statistics.get('collectCount')),
    ),
    comments=number_format.format_count(
      statistics.get('comment_count', statistics.get('commentCount')),
    ),
    shares=number_format.format_count(
      statistics.get('share_count', statistics.get('shareCount'))
      or statistics.get('forward_count', statistics.get('forwardCount')),
    ),
    media_type=map_aweme_type(aweme.get('aweme_type', aweme.get('awemeType')), page_url),
    status=CollectRowStatus.FAILED,
  )


def is_short_douyin_url(url: str) -> bool:
  text = (url or '').strip().lower()
  if 'v.douyin.com' in text:
    return True
  return (
    text.startswith('http')
    and len(text) < 50
    and 'video' not in text
    and 'note' not in text
  )


async def resolve_aweme_id(link: str, client: DouyinApiClient) -> Optional[str]:
  text = (link or '').strip()
  if not text:
    return None
  if text.isdigit():
    return text

  aweme_id = douyin_url.extract_aweme_id(text)
  if aweme_id:
    return aweme_id

  if is_short_douyin_url(text):
    short_url = text if text.startswith(('http://', 'https://')) else f'https://{text}'
    resolved = await client.resolve_short_url(short_url)
    if resolved:
      return douyin_url.extract_aweme_id(resolved)

  return None


async def get_session_page(context: BrowserContext) -> Page:
  key = id(context)
  page = _SESSION_PAGES.get(key)
  if page and not page.is_closed():
    return page

  page = await context.new_page()
  await page.goto(
    DOUYIN_INDEX_URL,
    wait_until='domcontentloaded',
    timeout=COLLECT_PAGE_TIMEOUT,
  )
  _SESSION_PAGES[key] = page
  _API_CLIENTS.pop(key, None)
  return page


async def get_api_client(context: BrowserContext) -> DouyinApiClient:
  key = id(context)
  client = _API_CLIENTS.get(key)
  if client:
    return client

  session_page = await get_session_page(context)
  client = await create_douyin_api_client(context, session_page)
  await client.update_cookies(context)
  _API_CLIENTS[key] = client
  return client


async def close_all_session_pages() -> None:
  for key, page in list(_SESSION_PAGES.items()):
    try:
      if not page.is_closed():
        await page.close()
    except Exception:
      pass
    _SESSION_PAGES.pop(key, None)
    _API_CLIENTS.pop(key, None)


async def collect_one(
  context: BrowserContext,
  link: str,
) -> CollectResultItem:
  platform = detect_platform(link)
  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    status=CollectRowStatus.FAILED,
  )

  try:
    client = await get_api_client(context)
    session_page = await get_session_page(context)
    await client.update_cookies(context)

    if not await client.pong(context):
      if not await has_login_cookies(session_page):
        item.status = CollectRowStatus.LOGIN_EXPIRED
        item.error_msg = '登录已过期，请重新登录账号'
        return item

    aweme_id = await resolve_aweme_id(link, client)
    if not aweme_id:
      item.error_msg = '无法从链接解析作品 ID'
      return item

    aweme = await client.get_video_by_id(aweme_id)
    detail_url = douyin_url.normalize_collect_url(link) or f'https://www.douyin.com/video/{aweme_id}'
    item = build_item_from_aweme(link, detail_url, aweme)

    if is_collect_success(item):
      item.status = CollectRowStatus.SUCCESS
      item.error_msg = ''
    else:
      item.error_msg = '未能获取作品互动数据（作者、点赞、评论等均为空）'

    return item
  except DataFetchError as exc:
    item.error_msg = str(exc)[:120]
    if 'blocked' in item.error_msg.lower():
      item.status = CollectRowStatus.LOGIN_EXPIRED
      item.error_msg = '账号可能被风控，请重新登录后再试'
    return item
  except Exception as exc:
    item.error_msg = str(exc)[:120]
    return item
  finally:
    await asyncio.sleep(COLLECT_REQUEST_INTERVAL)


async def collect_one_on_page(
  page: Page,
  link: str,
) -> CollectResultItem:
  """兼容注册表签名；实际走 context + API，不打开作品页."""
  return await collect_one(page.context, link)
