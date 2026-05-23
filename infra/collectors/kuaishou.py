"""快手作品链接采集：PC 站走 DOM/GraphQL；H5 分享页（chenzhongtech）走 INIT_STATE."""

from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import APIRequestContext, BrowserContext, Page

from infra.collect.runtime_config import get_batch_page_timeout_ms
from core.models import CollectResultItem, CollectRowStatus
from infra.collectors.douyin_parsers import number_format
from infra.collectors.kuaishou_parsers import api_client
from infra.collectors.kuaishou_parsers import h5_author
from infra.collectors.kuaishou_parsers import h5_state
from infra.collectors.kuaishou_parsers import ids as kuaishou_ids
from infra.collectors.kuaishou_parsers import page as kuaishou_page
from infra.collectors.kuaishou_parsers import profile_state
from infra.collectors.kuaishou_parsers import render_data
from infra.collectors.kuaishou_parsers import time_util as kuaishou_time
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

H5_DOM_METRIC_SELECTORS = {
  'likes': '.right-action-bar .icon.like + .text, .right-action-bar .block .icon.like ~ .text',
}

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
  if '/fw/photo/' in url_lower or '/photo/' in url_lower:
    return '图片'
  return '视频'


def is_plausible_author(name: str) -> bool:
  text = (name or '').strip()
  if not text or text == '-':
    return False
  if text in INVALID_AUTHOR_NAMES:
    return False
  if text.isdigit():
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


def metrics_from_photo_json(photo: dict) -> dict[str, str]:
  stats = render_data.get_statistics_from_photo(photo)
  metrics: dict[str, str] = {}

  metrics['views'] = number_format.format_metric(
    number_format.pick_stat_value(
      stats,
      'viewCount',
      'view_count',
      'realPlayCount',
      'real_play_count',
      'playCount',
      'play_count',
    ),
  )
  metrics['likes'] = number_format.format_metric(
    number_format.pick_stat_value(
      stats,
      'realLikeCount',
      'real_like_count',
      'likeCount',
      'like_count',
    ),
  )
  comment_raw = number_format.pick_stat_value(
    stats,
    'commentCount',
    'comment_count',
  )
  if comment_raw is None:
    comment_raw = h5_state.photo_comment_count(photo)
  metrics['comments'] = number_format.format_metric(comment_raw)
  return metrics


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
    text = number_format.format_metric(value)
    if text not in ('',):
      formatted[key] = text
  return formatted


async def read_metrics_from_page_json(
  page: Page,
  photo_id: Optional[str],
) -> dict[str, str]:
  """PC 页内嵌 JSON 中的精确 playCount / likeCount."""
  photo = await render_data.find_photo_detail_in_page(page, photo_id)
  if not photo:
    return {}
  return metrics_from_photo_json(photo)


def _assign_photo_ids(
  item: CollectResultItem,
  photo: Optional[dict],
  *,
  target_photo_id: str,
  author: Optional[dict] = None,
  page_url: str = '',
) -> None:
  if not photo:
    # 暂时不采集作品 id（后续可能恢复）
    # item.note_id = target_photo_id or '-'
    item.author_id = kuaishou_ids.author_uid_from_page_url(page_url) or '-'
    # 暂时不采集快手号（后续可能恢复）
    # item.author_sec_uid = '-'
    return

  author_obj = author if author is not None else render_data.get_author_from_photo(photo)
  # 暂时不采集作品 id（后续可能恢复）
  # note_id = kuaishou_ids.photo_note_id(photo, target_photo_id)
  # item.note_id = note_id or target_photo_id or '-'

  author_uid = kuaishou_ids.photo_author_uid(photo, author_obj)
  if not author_uid:
    author_uid = kuaishou_ids.author_uid_from_page_url(page_url)
  if not author_uid:
    cdn_url = kuaishou_ids.cdn_url_from_photo(photo, author_obj)
    author_uid = kuaishou_ids.extract_uid_from_cdn_url(cdn_url)
  item.author_id = author_uid or '-'

  # 暂时不采集快手号（后续可能恢复）
  # kwai_id = kuaishou_ids.photo_kwai_id(photo, author_obj)
  # item.author_sec_uid = kwai_id or '-'


async def _fill_kwai_id_from_profile(
  request: APIRequestContext,
  item: CollectResultItem,
  photo: Optional[dict],
  referer: str,
  *,
  author: Optional[dict] = None,
  eid_hint: str = '',
) -> None:
  # 暂时不采集快手号（后续可能恢复）
  # needs_kwai = item.author_sec_uid in ('-', '')
  needs_uid = item.author_id in ('-', '')
  if not needs_uid:
    return

  author_obj = author
  if photo and author_obj is None:
    author_obj = render_data.get_author_from_photo(photo)

  eid = str(eid_hint or '').strip()
  if not eid and photo:
    eid = kuaishou_ids.photo_author_eid(photo, author_obj)
  if not eid:
    eid = kuaishou_ids.author_eid_from_page_url(referer)
  if not eid:
    return

  _kwai_id, profile_uid = await profile_state.fetch_profile_ids(request, eid, referer)
  # if needs_kwai and kwai_id not in ('-', ''):
  #   item.author_sec_uid = kwai_id
  if needs_uid and profile_uid not in ('-', ''):
    item.author_id = profile_uid


async def _fill_author_id_from_video_detail(
  request: APIRequestContext,
  item: CollectResultItem,
  target_photo_id: str,
  referer: str,
) -> None:
  """作者 uid 仍缺失时，仅调用 visionVideoDetail 补全（不影响评论等既有接口）."""
  if item.author_id not in ('-', ''):
    return

  uid, eid = await api_client.fetch_video_author_hints(
    request,
    target_photo_id,
    referer,
  )
  if uid:
    item.author_id = uid
    return

  if eid:
    await _fill_kwai_id_from_profile(
      request,
      item,
      None,
      referer,
      eid_hint=eid,
    )


async def _fill_h5_author_id_gaps(
  page: Page,
  item: CollectResultItem,
  photo: Optional[dict],
  *,
  target_photo_id: str,
  final_url: str,
) -> None:
  """H5 专用：常规 photo/URL/CDN/profile 仍无 uid 时的补全."""
  if item.author_id not in ('-', ''):
    return

  live_url = final_url
  try:
    live_url = str(await page.evaluate('() => location.href') or final_url).strip()
  except Exception:
    pass

  for url in (live_url, final_url):
    uid = kuaishou_ids.author_uid_from_page_url(url)
    if uid:
      item.author_id = uid
      return
    eid = kuaishou_ids.author_eid_from_page_url(url)
    if eid and item.author_id in ('-', ''):
      await _fill_kwai_id_from_profile(
        page.context.request,
        item,
        photo,
        url,
        eid_hint=eid,
      )
      if item.author_id not in ('-', ''):
        return

  state = await h5_state.read_init_state(page)
  state_hints = h5_author.collect_author_hints_from_state(state, target_photo_id)
  dom_hints = await kuaishou_page.read_h5_author_hints(page)

  merged = {'uid': '', 'eid': '', 'headurl': ''}
  for hints in (state_hints, dom_hints):
    for key in ('uid', 'eid', 'headurl'):
      if merged[key]:
        continue
      value = str(hints.get(key) or '').strip()
      if value:
        merged[key] = value

  if photo and not merged['uid']:
    author_obj = render_data.get_author_from_photo(photo)
    merged['uid'] = kuaishou_ids.photo_author_uid(photo, author_obj)
    if not merged['eid']:
      merged['eid'] = kuaishou_ids.photo_author_eid(photo, author_obj)
    if not merged['headurl']:
      merged['headurl'] = kuaishou_ids.cdn_url_from_photo(photo, author_obj)

  if not merged['uid'] and merged['headurl']:
    merged['uid'] = kuaishou_ids.extract_uid_from_cdn_url(merged['headurl'])
  if merged['uid']:
    item.author_id = merged['uid']
    return

  eid = merged['eid'] or ''
  if not eid and photo:
    eid = kuaishou_ids.photo_author_eid(photo, render_data.get_author_from_photo(photo))
  for url in (live_url, final_url):
    if not eid:
      eid = kuaishou_ids.author_eid_from_page_url(url)
  if eid:
    await _fill_kwai_id_from_profile(
      page.context.request,
      item,
      photo,
      live_url or final_url,
      eid_hint=eid,
    )
    if item.author_id not in ('-', ''):
      return

  try:
    html = await page.content()
  except Exception:
    html = ''
  html_hints = h5_author.collect_author_hints_from_html(html, target_photo_id)
  if html_hints.get('uid'):
    item.author_id = html_hints['uid']
    return
  if html_hints.get('eid') and item.author_id in ('-', ''):
    await _fill_kwai_id_from_profile(
      page.context.request,
      item,
      photo,
      live_url or final_url,
      eid_hint=html_hints['eid'],
    )

  await _fill_author_id_from_video_detail(
    page.context.request,
    item,
    target_photo_id,
    live_url or final_url,
  )


def merge_metrics(dom_metrics: dict[str, str], json_metrics: dict[str, str]) -> dict[str, str]:
  merged = dict(dom_metrics)
  for key in ('views', 'likes'):
    json_value = json_metrics.get(key)
    if json_value and json_value not in ('-', ''):
      merged[key] = json_value
    elif not merged.get(key):
      merged[key] = '0'
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
        formatted = number_format.format_metric(text)
        if formatted not in ('',):
          result[key] = formatted
    except Exception:
      continue
  return result


async def wait_for_web_detail_surface(page: Page) -> None:
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


async def wait_for_h5_detail_surface(page: Page) -> None:
  selectors = (
    '.photo-page',
    '.work-info',
    '.g-common-bar__inner__name',
    '.right-action-bar',
    '#app',
  )
  for selector in selectors:
    try:
      await page.wait_for_selector(selector, timeout=8000)
      return
    except Exception:
      continue
  await asyncio.sleep(2)


async def _resolve_web_photo_id_after_navigation(
  page: Page,
  *,
  link: str,
  final_url: str,
  preset_id: Optional[str],
) -> str:
  page_photo_id = await kuaishou_page.extract_photo_id_from_page(page)
  resolved = (
    page_photo_id
    or kuaishou_url.extract_photo_id(final_url)
    or preset_id
    or kuaishou_url.extract_photo_id(link)
  )
  if resolved:
    return resolved

  if kuaishou_url.is_share_short_url(link):
    redirected = await kuaishou_url.resolve_short_url(link)
    return kuaishou_url.extract_photo_id(redirected) or ''

  return ''


async def _resolve_h5_photo_id_after_navigation(
  page: Page,
  *,
  link: str,
  final_url: str,
  preset_id: Optional[str],
) -> str:
  page_photo_id = await kuaishou_page.extract_h5_photo_id_from_page(page)
  resolved = (
    page_photo_id
    or kuaishou_url.extract_photo_id(final_url)
    or preset_id
    or kuaishou_url.extract_photo_id(link)
  )
  if resolved:
    return resolved

  if kuaishou_url.is_share_short_url(link):
    redirected = await kuaishou_url.resolve_short_url(link)
    return kuaishou_url.extract_photo_id(redirected) or ''

  state = await h5_state.read_init_state(page)
  photo = h5_state.find_photo_in_state(state, None)
  if photo:
    return h5_state.share_info_photo_id(photo) or render_data.get_photo_id_from_detail(photo)

  return ''


async def _goto_collect_page(page: Page, link: str) -> None:
  collect_url = kuaishou_url.resolve_collect_entry_url(link)
  timeout = get_batch_page_timeout_ms()
  await page.goto(collect_url, wait_until='domcontentloaded', timeout=timeout)


async def _try_h5_photo_api_fallback(
  page: Page,
  target_photo_id: Optional[str],
) -> Optional[dict]:
  """页面已打开后，主动触发 recommend/photos 并解析（INIT_STATE 缺失时）."""
  timeout = get_batch_page_timeout_ms()
  photo_id = str(target_photo_id or '').strip()
  if not photo_id:
    return None

  try:
    async with page.expect_response(
      lambda response: (
        h5_state.is_h5_photo_api_url(response.url) and response.status == 200
      ),
      timeout=min(timeout, 20000),
    ) as response_info:
      await page.evaluate(
        """async (photoId) => {
          const body = {
            photoId,
            sharePage: 'ATLAS_PICTURE_SHARE_PAGE',
          };
          await fetch('/rest/wd/ugH5App/recommend/photos?caver=2', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify(body),
            credentials: 'include',
          });
        }""",
        photo_id,
      )
    response = await response_info.value
    return await h5_state.parse_h5_photo_api_response(response, target_photo_id)
  except Exception:
    return None


async def _collect_h5_on_page(
  page: Page,
  item: CollectResultItem,
  *,
  link: str,
  final_url: str,
  preset_photo_id: Optional[str],
) -> CollectResultItem:
  await wait_for_h5_detail_surface(page)
  await kuaishou_page.dismiss_overlays(page)
  await asyncio.sleep(1)

  target_photo_id = await _resolve_h5_photo_id_after_navigation(
    page,
    link=link,
    final_url=final_url,
    preset_id=preset_photo_id,
  )
  if not target_photo_id:
    item.error_msg = '无法解析快手 H5 作品 ID'
    return item

  if not kuaishou_page.is_kuaishou_page_url(final_url):
    item.error_msg = '链接未跳转到快手页面'
    return item

  photo = await h5_state.find_photo_on_h5_page(page, target_photo_id)
  if not photo:
    photo = await _try_h5_photo_api_fallback(page, target_photo_id)

  author_name = ''
  publish_time = '-'
  metrics: dict[str, str] = {}

  if photo:
    author_name = h5_state.photo_author_name(photo)
    if is_plausible_author(author_name):
      item.author_name = author_name
    publish_time = kuaishou_time.format_publish_time(photo.get('timestamp'))
    metrics = metrics_from_photo_json(photo)
    _assign_photo_ids(
      item,
      photo,
      target_photo_id=target_photo_id,
      page_url=final_url,
    )
    await _fill_kwai_id_from_profile(
      page.context.request,
      item,
      photo,
      final_url,
    )
    await _fill_h5_author_id_gaps(
      page,
      item,
      photo,
      target_photo_id=target_photo_id,
      final_url=final_url,
    )
  else:
    item.error_msg = '未能从 H5 页面读取作品数据（INIT_STATE）'
    _assign_photo_ids(item, None, target_photo_id=target_photo_id, page_url=final_url)
    await _fill_h5_author_id_gaps(
      page,
      item,
      None,
      target_photo_id=target_photo_id,
      final_url=final_url,
    )

  if not is_plausible_author(item.author_name):
    dom_author = await kuaishou_page.read_h5_dom_author(page)
    if is_plausible_author(dom_author):
      item.author_name = dom_author
    else:
      item.author_name = '-'

  if publish_time in ('-', ''):
    item.publish_time = '-'
  else:
    item.publish_time = publish_time

  dom_metrics = _format_metric_map(await kuaishou_page.read_dom_metrics(page))
  for key, selector in H5_DOM_METRIC_SELECTORS.items():
    if dom_metrics.get(key):
      continue
    try:
      loc = page.locator(selector).first
      if await loc.is_visible(timeout=1500):
        text = (await loc.inner_text()).strip()
        formatted = number_format.format_metric(text)
        if formatted not in ('',):
          dom_metrics[key] = formatted
    except Exception:
      continue

  merged = merge_metrics(dom_metrics, metrics)
  item.views = merged.get('views') or metrics.get('views') or '0'
  item.likes = merged.get('likes') or metrics.get('likes') or '0'

  if metrics.get('comments'):
    item.comments = metrics['comments']
  else:
    comment_count = await api_client.fetch_comment_count(
      page.context.request,
      target_photo_id,
      final_url,
    )
    item.comments = number_format.format_metric(comment_count)

  if photo:
    item.media_type = h5_state.map_h5_media_type(photo, final_url)
  else:
    item.media_type = map_photo_type(final_url)

  item = finalize_item(item)

  if item.status == CollectRowStatus.FAILED and await kuaishou_page.is_login_modal_visible(page):
    item.status = CollectRowStatus.LOGIN_EXPIRED
    item.error_msg = '登录已过期，请重新登录账号'

  return item


async def _collect_web_on_page(
  page: Page,
  item: CollectResultItem,
  *,
  link: str,
  final_url: str,
  preset_photo_id: Optional[str],
) -> CollectResultItem:
  await wait_for_web_detail_surface(page)
  await kuaishou_page.dismiss_overlays(page)
  await asyncio.sleep(1)

  target_photo_id = await _resolve_web_photo_id_after_navigation(
    page,
    link=link,
    final_url=final_url,
    preset_id=preset_photo_id,
  )
  if not target_photo_id:
    item.error_msg = '无法解析快手作品 ID（短链跳转后仍未获取到作品 ID）'
    return item

  if not kuaishou_page.is_kuaishou_page_url(final_url):
    item.error_msg = '链接未跳转到快手页面'
    return item

  if not await kuaishou_page.has_login_cookies(page):
    if await kuaishou_page.is_login_modal_visible(page):
      item.status = CollectRowStatus.LOGIN_EXPIRED
      item.error_msg = '登录已过期，请重新登录账号'
      return item

  datasets = await render_data.parse_all_page_data(page)
  photo_bundle, author_bundle = render_data.find_vision_detail_bundle(
    datasets,
    target_photo_id,
  )
  photo_for_ids = photo_bundle or await render_data.find_photo_detail_in_page(
    page,
    target_photo_id,
  )
  if photo_for_ids and not author_bundle:
    author_bundle = render_data.get_author_from_photo(photo_for_ids)

  author_name, dom_photo_time = await asyncio.gather(
    read_author_from_page_json(page, target_photo_id),
    kuaishou_page.read_dom_photo_time(page),
  )
  if not author_name and author_bundle:
    author_name = str(
      author_bundle.get('name')
      or author_bundle.get('userName')
      or author_bundle.get('user_name')
      or author_bundle.get('nickname')
      or '',
    ).strip()
  if not author_name:
    author_name = await read_dom_author(page)
  item.author_name = author_name if author_name else '-'

  apollo_time = ''
  if photo_for_ids:
    apollo_time = kuaishou_time.format_publish_time(photo_for_ids.get('timestamp'))
  if apollo_time not in ('-', ''):
    item.publish_time = apollo_time
  else:
    item.publish_time = dom_photo_time if dom_photo_time not in ('-', '') else '-'

  _assign_photo_ids(
    item,
    photo_for_ids,
    target_photo_id=target_photo_id,
    author=author_bundle,
    page_url=final_url,
  )
  await _fill_kwai_id_from_profile(
    page.context.request,
    item,
    photo_for_ids,
    final_url,
    author=author_bundle,
  )
  await _fill_author_id_from_video_detail(
    page.context.request,
    item,
    target_photo_id,
    final_url,
  )

  dom_metrics = await read_dom_metrics(page)
  json_metrics = metrics_from_photo_json(photo_for_ids) if photo_for_ids else {}
  if not json_metrics:
    json_metrics = await read_metrics_from_page_json(page, target_photo_id)
  metrics = merge_metrics(dom_metrics, json_metrics)
  item.views = metrics.get('views') or '0'
  item.likes = metrics.get('likes') or '0'

  comment_count = await api_client.fetch_comment_count(
    page.context.request,
    target_photo_id,
    final_url,
  )
  item.comments = number_format.format_metric(comment_count)

  item.media_type = map_photo_type(final_url)
  item = finalize_item(item)

  if item.status == CollectRowStatus.FAILED and await kuaishou_page.is_login_modal_visible(page):
    item.status = CollectRowStatus.LOGIN_EXPIRED
    item.error_msg = '登录已过期，请重新登录账号'

  return item


async def collect_one_on_page(
  page: Page,
  link: str,
) -> CollectResultItem:
  platform = detect_platform(link)
  preset_photo_id = kuaishou_url.extract_photo_id(link)
  is_short_link = kuaishou_url.is_share_short_url(link)
  use_h5_entry = kuaishou_url.should_use_h5_collect(link)

  item = CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    favorites='-',
    shares='-',
    status=CollectRowStatus.FAILED,
  )

  if not preset_photo_id and not is_short_link and not use_h5_entry:
    item.error_msg = '无法解析快手作品 ID'
    return item

  try:
    await _goto_collect_page(page, link)
    final_url = page.url
    item.link = final_url

    if kuaishou_url.should_use_h5_collect(link, final_url):
      return await _collect_h5_on_page(
        page,
        item,
        link=link,
        final_url=final_url,
        preset_photo_id=preset_photo_id,
      )

    return await _collect_web_on_page(
      page,
      item,
      link=link,
      final_url=final_url,
      preset_photo_id=preset_photo_id,
    )
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
