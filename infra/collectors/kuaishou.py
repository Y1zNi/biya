"""快手作品链接采集：评论走 commentListQuery，播放/点赞走 DOM."""

from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import BrowserContext, Page

from infra.collect.runtime_config import get_batch_page_timeout_ms
from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.douyin_parsers import number_format
from infra.collectors.kuaishou_parsers import api_client
from infra.collectors.kuaishou_parsers import page as kuaishou_page
from infra.collectors.kuaishou_parsers import render_data
from infra.collectors.kuaishou_parsers import url as kuaishou_url
from infra.platform_detect import detect_platform

DOM_METRIC_SELECTORS = {
  'views': '.play-count, [class*="play-count"]',
  'likes': '.like-item .item-count',
}

DOM_AUTHOR_SELECTORS = [
  '.profile-user-name-title',
  'a.profile-user-name .profile-user-name-title',
  '.profile-user .profile-user-name-title',
]

INVALID_AUTHOR_NAMES = frozenset({
  '登录',
  '首页',
  '推荐',
  '关注',
  '发现',
  '搜索',
  '消息',
  '直播',
  '精选',
  '同城',
})


def map_photo_type(page_url: str) -> str:
  url_lower = (page_url or '').lower()
  if '/short-video/' in url_lower or '/video/' in url_lower:
    return '视频'
  if '/photo/' in url_lower:
    return '图片'
  return '视频'


def is_plausible_author(name: str) -> bool:
  text = (name or '').strip()
  if not text or text == '-':
    return False
  if text in INVALID_AUTHOR_NAMES:
    return False
  return len(text) >= 2


def has_meaningful_metrics(item: CollectResultItem) -> bool:
  fields = (item.views, item.likes, item.comments, item.media_type)
  return any(value not in ('-', '', '0') for value in fields)


def is_collect_success(item: CollectResultItem) -> bool:
  return has_meaningful_metrics(item) or is_plausible_author(item.author_name)


def finalize_item(item: CollectResultItem) -> CollectResultItem:
  if is_collect_success(item):
    item.status = CollectRowStatus.SUCCESS
    item.error_msg = ''
  elif not item.error_msg:
    item.error_msg = '未能获取作品互动数据（作者、点赞、评论等均为空）'
  return item


async def read_author_from_page_json(
  page: Page,
  photo_id: Optional[str],
) -> str:
  photo = await render_data.find_photo_detail_in_page(page, photo_id)
  if not photo:
    return ''

  author = render_data.get_author_from_photo(photo)
  name = str(
    author.get('name')
    or author.get('userName')
    or author.get('user_name')
    or author.get('nickname')
    or '',
  ).strip()
  return name if is_plausible_author(name) else ''


async def read_dom_author(page: Page) -> str:
  for selector in DOM_AUTHOR_SELECTORS:
    try:
      loc = page.locator(selector).first
      if await loc.is_visible(timeout=2500):
        text = (await loc.inner_text()).strip()
        if is_plausible_author(text):
          return text
    except Exception:
      continue
  return ''


def _format_metric_map(raw: dict[str, str]) -> dict[str, str]:
  formatted: dict[str, str] = {}
  for key, value in raw.items():
    text = number_format.format_count(value)
    if text not in ('-', ''):
      formatted[key] = text
  return formatted


async def read_metrics_from_page_json(
  page: Page,
  photo_id: Optional[str],
) -> dict[str, str]:
  """页面内嵌 JSON 中的精确 playCount / likeCount（DOM 为 2.3万 时的补充）."""
  photo = await render_data.find_photo_detail_in_page(page, photo_id)
  if not photo:
    return {}

  stats = render_data.get_statistics_from_photo(photo)
  metrics: dict[str, str] = {}

  views = number_format.format_count(
    stats.get('viewCount', stats.get('view_count', stats.get('realPlayCount', stats.get('real_play_count')))),
  )
  if views in ('-', ''):
    views = number_format.format_count(
      stats.get('playCount', stats.get('play_count')),
    )
  if views not in ('-', ''):
    metrics['views'] = views

  likes = number_format.format_count(
    stats.get('realLikeCount', stats.get('real_like_count')),
  )
  if likes in ('-', ''):
    likes = number_format.format_count(
      stats.get('likeCount', stats.get('like_count')),
    )
  if likes not in ('-', ''):
    metrics['likes'] = likes

  return metrics


def merge_metrics(dom_metrics: dict[str, str], json_metrics: dict[str, str]) -> dict[str, str]:
  """页面 JSON 的 playCount/likeCount 为精确整数，优先于 DOM 的 2.3万 缩写."""
  merged = dict(dom_metrics)
  for key in ('views', 'likes'):
    json_value = json_metrics.get(key)
    if json_value and json_value not in ('-', ''):
      merged[key] = json_value
    elif not merged.get(key):
      merged[key] = '-'
  return merged


async def read_dom_metrics(page: Page) -> dict[str, str]:
  result = _format_metric_map(await kuaishou_page.read_dom_metrics(page))
  for key, selector in DOM_METRIC_SELECTORS.items():
    if result.get(key):
      continue
    try:
      loc = page.locator(selector).first
      if await loc.is_visible(timeout=1500):
        text = (await loc.inner_text()).strip()
        formatted = number_format.format_count(text)
        if formatted not in ('-', ''):
          result[key] = formatted
    except Exception:
      continue
  return result


async def wait_for_detail_surface(page: Page) -> None:
  selectors = (
    '.short-video-detail',
    '.profile-user-name-title',
    '.photo-time',
    'video.player-video',
    'video',
    '.like-item .item-count',
  )
  for selector in selectors:
    try:
      await page.wait_for_selector(selector, timeout=8000)
      return
    except Exception:
      continue
  await asyncio.sleep(2)


async def collect_one_on_page(
  page: Page,
  link: str,
) -> CollectResultItem:
  platform = detect_platform(link)
  target_photo_id = kuaishou_url.extract_photo_id(link)
  collect_url = kuaishou_url.normalize_collect_url(link)

  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    favorites='-',
    shares='-',
    status=CollectRowStatus.FAILED,
  )

  if not target_photo_id:
    item.error_msg = '无法解析快手作品 ID'
    return item

  try:
    await page.goto(
      collect_url,
      wait_until='domcontentloaded',
      timeout=get_batch_page_timeout_ms(),
    )
    await wait_for_detail_surface(page)
    await kuaishou_page.dismiss_overlays(page)
    await asyncio.sleep(1)

    final_url = page.url
    item.link = final_url

    page_photo_id = await kuaishou_page.extract_photo_id_from_page(page)
    resolved_photo_id = (
      page_photo_id
      or kuaishou_url.extract_photo_id(final_url)
      or target_photo_id
    )
    if resolved_photo_id:
      target_photo_id = resolved_photo_id

    if not kuaishou_page.is_kuaishou_page_url(final_url):
      item.error_msg = '链接未跳转到快手页面'
      return item

    if not await kuaishou_page.has_login_cookies(page):
      if await kuaishou_page.is_login_modal_visible(page):
        item.status = CollectRowStatus.LOGIN_EXPIRED
        item.error_msg = '登录已过期，请重新登录账号'
        return item

    author_name, dom_photo_time = await asyncio.gather(
      read_author_from_page_json(page, target_photo_id),
      kuaishou_page.read_dom_photo_time(page),
    )
    if not author_name:
      author_name = await read_dom_author(page)
    item.author_name = author_name if author_name else '-'
    item.publish_time = dom_photo_time if dom_photo_time not in ('-', '') else '-'

    dom_metrics = await read_dom_metrics(page)
    json_metrics = await read_metrics_from_page_json(page, target_photo_id)
    metrics = merge_metrics(dom_metrics, json_metrics)
    item.views = metrics.get('views') or '-'
    item.likes = metrics.get('likes') or '-'

    comment_count = await api_client.fetch_comment_count(
      page.context.request,
      target_photo_id,
      final_url,
    )
    item.comments = number_format.format_count(comment_count)

    item.media_type = map_photo_type(final_url)
    item = finalize_item(item)

    if item.status == CollectRowStatus.FAILED and await kuaishou_page.is_login_modal_visible(page):
      item.status = CollectRowStatus.LOGIN_EXPIRED
      item.error_msg = '登录已过期，请重新登录账号'

    return item
  except Exception as exc:
    item.status = CollectRowStatus.FAILED
    item.error_msg = str(exc)[:120]
    return item


async def collect_one(
  context: BrowserContext,
  link: str,
) -> CollectResultItem:
  page = await context.new_page()
  try:
    return await collect_one_on_page(page, link)
  finally:
    await page.close()
