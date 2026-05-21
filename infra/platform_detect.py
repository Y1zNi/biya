"""根据 URL 识别发帖平台."""

from __future__ import annotations

import re
from typing import Tuple

from core.models import PlatformDetectResult
from core.platforms import can_collect

PLATFORM_RULES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
  ('douyin', '抖音', ('douyin.com', 'iesdouyin.com', 'v.douyin.com')),
  ('kuaishou', '快手', ('kuaishou.com', 'chenzhongtech.com')),
  ('xiaohongshu', '小红书', ('xiaohongshu.com', 'xhslink.com')),
  ('bilibili', 'B站', ('bilibili.com', 'b23.tv')),
  ('weibo', '微博', ('weibo.com', 'weibo.cn')),
  ('vivo', 'vivo社区', ('bbs.vivo.com.cn', 'club.vivo.com.cn')),
  ('channels', '微信视频号', ('channels.weixin.qq.com',)),
)


def detect_platform(url: str) -> PlatformDetectResult:
  text = (url or '').strip().lower()
  if not text:
    return PlatformDetectResult('unknown', '未知', False)

  if not text.startswith(('http://', 'https://')):
    text = f'https://{text}'

  if 'weixin.qq.com' in text and '/sph/' in text:
    return PlatformDetectResult('channels', '微信视频号', can_collect('channels'))

  for platform_id, platform_name, hosts in PLATFORM_RULES:
    for host in hosts:
      if host in text:
        return PlatformDetectResult(platform_id, platform_name, can_collect(platform_id))

  return PlatformDetectResult('unknown', '未知', False)


def is_douyin_url(url: str) -> bool:
  return detect_platform(url).platform_id == 'douyin'


def looks_like_collect_link(text: str) -> bool:
  """单元格是否像可采集链接（用于排除表头行）."""
  from infra.link_extract import extract_collect_links_from_cell

  value = (text or '').strip()
  if not value:
    return False
  if extract_collect_links_from_cell(value):
    return True
  lower = value.lower()
  if lower.startswith(('http://', 'https://')):
    return True
  return detect_platform(value).platform_id != 'unknown'


def guess_link_column_index(headers: list[str]) -> int:
  patterns = re.compile(r'链接|link|url|地址|视频|作品', re.I)
  for index, header in enumerate(headers):
    name = str(header or '').strip()
    if patterns.search(name):
      return index
  return -1
