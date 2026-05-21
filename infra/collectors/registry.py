"""平台采集函数注册表."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from playwright.async_api import Page

from core.models import CollectResultItem
from infra.collectors.douyin import collect_one_on_page
from infra.collectors.kuaishou import collect_one_on_page as kuaishou_collect_one_on_page
from infra.collectors.bilibili import collect_one_on_page as bilibili_collect_one_on_page
from infra.collectors.weibo import collect_one_on_page as weibo_collect_one_on_page
from infra.collectors.vivo import collect_one_on_page as vivo_collect_one_on_page
from infra.collectors.xiaohongshu import collect_one_on_page as xiaohongshu_collect_one_on_page
from infra.collectors.channels import collect_one_on_page as channels_collect_one_on_page

CollectorFn = Callable[[Page, str], Awaitable[CollectResultItem]]

COLLECTOR_MAP: dict[str, CollectorFn] = {
  'douyin': collect_one_on_page,
  'kuaishou': kuaishou_collect_one_on_page,
  'xiaohongshu': xiaohongshu_collect_one_on_page,
  'weibo': weibo_collect_one_on_page,
  'bilibili': bilibili_collect_one_on_page,
  'vivo': vivo_collect_one_on_page,
  'channels': channels_collect_one_on_page,
}


def get_collector(platform_id: str) -> Optional[CollectorFn]:
  return COLLECTOR_MAP.get(platform_id)
