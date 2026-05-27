"""数据采集批处理服务（L2 业务层）."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from playwright.async_api import Browser, BrowserContext, async_playwright

from core.export_schema import normalize_platform_id
from core.models import (
  CollectParams,
  CollectProgress,
  CollectResultItem,
  CollectRowStatus,
  CollectSummary,
)
from core.result_store import item_to_json
from core.platforms import can_collect, requires_collect_account
from infra.browser import (
  get_or_create_anonymous_collect_context,
  get_or_create_collect_context,
)
from infra.collect.runtime_config import (
  reset_batch_page_timeout_ms,
  set_batch_page_timeout_ms,
)
from infra.collectors.registry import get_collector
from infra.database import Account, Database
from infra.link_extract import normalize_collect_link
from infra.platform_detect import detect_platform

OnProgress = Callable[[CollectProgress], None]
OnRow = Callable[[CollectResultItem], None]
OnTaskStarted = Callable[[int], None]


def build_unsupported_item(link: str) -> CollectResultItem:
  platform = detect_platform(link)
  return CollectResultItem(
    link=link,
    platform_id=platform.platform_id,
    platform_name=platform.platform_name,
    author_name='-',
    views='-',
    likes='-',
    favorites='-',
    comments='-',
    shares='-',
    media_type='-',
    status=CollectRowStatus.UNSUPPORTED,
    error_msg='该平台暂不支持采集',
  )


def build_no_account_item(link: str, platform_name: str, platform_id: str = '') -> CollectResultItem:
  return CollectResultItem(
    link=link,
    platform_id=platform_id,
    platform_name=platform_name,
    author_name='-',
    views='-',
    likes='-',
    favorites='-',
    comments='-',
    shares='-',
    media_type='-',
    status=CollectRowStatus.FAILED,
    error_msg='该平台暂无可用账号，请到账号管理添加并登录',
  )


def _should_retry_item(item: CollectResultItem) -> bool:
  return item.status == CollectRowStatus.FAILED


async def _sleep_random_interval(params: CollectParams) -> None:
  low = min(params.min_delay_sec, params.max_delay_sec)
  high = max(params.min_delay_sec, params.max_delay_sec)
  if high <= 0:
    return
  await asyncio.sleep(random.uniform(low, high))


class CollectService:
  """串行批处理采集."""

  def __init__(self, db: Database) -> None:
    self.db = db
    self._cancelled = False

  def cancel(self) -> None:
    self._cancelled = True

  def reset_cancel(self) -> None:
    self._cancelled = False

  async def run_batch(
    self,
    links: List[str],
    account_by_platform: Dict[str, Account],
    source_file: str,
    params: CollectParams,
    *,
    on_progress: Optional[OnProgress] = None,
    on_row: Optional[OnRow] = None,
    on_task_started: Optional[OnTaskStarted] = None,
  ) -> CollectSummary:
    self.reset_cancel()

    normalized_links: List[str] = []
    for raw_link in links:
      link = normalize_collect_link(raw_link)
      if link:
        normalized_links.append(link)
    links = normalized_links

    summary = CollectSummary(total=len(links))

    for account in account_by_platform.values():
      state_path = Path(account.state_file_path)
      if not state_path.is_file():
        raise FileNotFoundError(f'账号 {account.name} 登录状态文件不存在: {state_path}')

    task_platform = 'mixed'
    task_account_id = 0
    if account_by_platform:
      task_account_id = next(iter(account_by_platform.values())).id
      if len(account_by_platform) == 1:
        only = next(iter(account_by_platform.values()))
        task_platform = only.platform
        task_account_id = only.id

    task_id = self.db.create_collect_task(
      platform=task_platform,
      account_id=task_account_id,
      source_file=source_file,
      total=len(links),
    )
    summary.task_id = task_id
    if on_task_started is not None:
      on_task_started(task_id)

    context_cache: Dict[str, Tuple[Browser, BrowserContext]] = {}
    set_batch_page_timeout_ms(params.page_timeout_ms)

    async with async_playwright() as playwright:
      try:
        for index, link in enumerate(links):
          if self._cancelled:
            summary.cancelled = True
            break

          self._emit_progress(index + 1, len(links), link, on_progress)
          platform = detect_platform(link)

          if not platform.can_collect or not can_collect(platform.platform_id):
            item = build_unsupported_item(link)
            summary.unsupported_count += 1
            self._emit_row(task_id, item, on_row)
            await _sleep_random_interval(params)
            continue

          account = account_by_platform.get(platform.platform_id)
          if account is None and requires_collect_account(platform.platform_id):
            item = build_no_account_item(link, platform.platform_name, platform.platform_id)
            summary.failed_count += 1
            self._emit_row(task_id, item, on_row)
            await _sleep_random_interval(params)
            continue

          collect_fn = get_collector(platform.platform_id)
          if collect_fn is None:
            item = CollectResultItem(
              link=link,
              platform_id=platform.platform_id,
              platform_name=platform.platform_name,
              author_name='-',
              views='-',
              likes='-',
              favorites='-',
              comments='-',
              shares='-',
              media_type='-',
              status=CollectRowStatus.FAILED,
              error_msg='该平台采集器尚未实现',
            )
            summary.failed_count += 1
            self._emit_row(task_id, item, on_row)
            await _sleep_random_interval(params)
            continue

          if account is not None:
            context = await get_or_create_collect_context(
              playwright,
              platform.platform_id,
              account,
              context_cache,
              navigation_timeout_ms=params.page_timeout_ms,
            )
          else:
            context = await get_or_create_anonymous_collect_context(
              playwright,
              platform.platform_id,
              context_cache,
              navigation_timeout_ms=params.page_timeout_ms,
            )

          item = await self._collect_with_retry(
            link=link,
            platform_id=platform.platform_id,
            context=context,
            collect_fn=collect_fn,
            params=params,
          )

          if item.status == CollectRowStatus.SUCCESS:
            summary.success_count += 1
          elif item.status == CollectRowStatus.LOGIN_EXPIRED:
            summary.login_expired = True
            summary.failed_count += 1
            if account.id not in summary.expired_account_ids:
              summary.expired_account_ids.append(account.id)
            self._emit_row(task_id, item, on_row)
            break
          elif item.status == CollectRowStatus.FAILED:
            summary.failed_count += 1
          else:
            summary.unsupported_count += 1

          self._emit_row(task_id, item, on_row)
          await _sleep_random_interval(params)
      finally:
        from infra.collectors.douyin import close_all_session_pages

        await close_all_session_pages()
        for browser, context in context_cache.values():
          await context.close()
          await browser.close()
        reset_batch_page_timeout_ms()

    task_status = 'cancelled' if summary.cancelled else 'completed'
    if summary.login_expired:
      task_status = 'login_expired'
    self.db.finish_collect_task(
      task_id,
      success_count=summary.success_count,
      status=task_status,
    )

    primary_account = next(iter(account_by_platform.values()), None)
    self.db.add_operation_log(
      'collect',
      'success' if summary.success_count > 0 else 'failed',
      (
        f'采集完成：成功 {summary.success_count}，失败 {summary.failed_count}，'
        f'不支持 {summary.unsupported_count}'
      ),
      account_id=primary_account.id if primary_account else None,
      platform=primary_account.platform if primary_account else None,
    )

    return summary

  async def _collect_with_retry(
    self,
    *,
    link: str,
    platform_id: str,
    context: BrowserContext,
    collect_fn,
    params: CollectParams,
  ) -> CollectResultItem:
    max_attempts = 1 + max(0, params.retry_count)
    item: CollectResultItem = CollectResultItem(link=link, status=CollectRowStatus.FAILED)

    for attempt in range(max_attempts):
      if self._cancelled:
        break
      item = await self._collect_once(
        link=link,
        platform_id=platform_id,
        context=context,
        collect_fn=collect_fn,
      )
      if not _should_retry_item(item) or attempt >= max_attempts - 1:
        break
      await _sleep_random_interval(params)

    return item

  async def _collect_once(
    self,
    *,
    link: str,
    platform_id: str,
    context: BrowserContext,
    collect_fn,
  ) -> CollectResultItem:
    if platform_id == 'douyin':
      from infra.collectors.douyin import collect_one as douyin_collect_one

      return await douyin_collect_one(context, link)

    page = await context.new_page()
    try:
      return await collect_fn(page, link)
    finally:
      await page.close()

  def _emit_progress(
    self,
    current: int,
    total: int,
    link: str,
    on_progress: Optional[OnProgress],
  ) -> None:
    if on_progress is None:
      return
    short_link = link if len(link) <= 60 else link[:57] + '...'
    on_progress(CollectProgress(
      current=current,
      total=total,
      current_link=short_link,
      message=f'正在采集 {current}/{total}：{short_link}',
    ))

  def _emit_row(
    self,
    task_id: int,
    item: CollectResultItem,
    on_row: Optional[OnRow],
  ) -> None:
    platform_id = normalize_platform_id(
      item.platform_id or detect_platform(item.link).platform_id,
    )
    if not item.platform_id:
      item.platform_id = platform_id
    self.db.add_collect_result(
      task_id=task_id,
      link=item.link,
      platform_name=item.platform_name,
      author_name=item.author_name,
      note_id=item.note_id,
      author_id=item.author_id,
      author_sec_uid=item.author_sec_uid,
      douyin_id=item.douyin_id,
      publish_time=item.publish_time,
      views=item.views,
      likes=item.likes,
      favorites=item.favorites,
      comments=item.comments,
      shares=item.shares,
      media_type=item.media_type,
      status=item.status.value,
      error_msg=item.error_msg,
      platform_id=platform_id,
      payload_json=item_to_json(item),
    )
    if on_row is not None:
      on_row(item)
