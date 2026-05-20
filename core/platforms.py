"""平台能力与元数据（领域规则）."""

from __future__ import annotations

from config import PLATFORMS, get_platform_name as config_get_platform_name

# 已实现采集器的平台
_COLLECTABLE_IDS = frozenset({
  'douyin',
  'kuaishou',
  'xiaohongshu',
  'weibo',
  'bilibili',
  'vivo',
})


def can_collect(platform_id: str) -> bool:
  """业务上是否允许采集（已启用且已实现）."""
  if platform_id not in _COLLECTABLE_IDS:
    return False
  for platform in PLATFORMS:
    if platform['id'] == platform_id:
      return bool(platform.get('enabled', False))
  return False


def get_platform_name(platform_id: str) -> str:
  return config_get_platform_name(platform_id)


def list_collectable_platform_ids() -> list[str]:
  """与 config.PLATFORMS / 账号管理 Tab 顺序一致."""
  result: list[str] = []
  for platform in PLATFORMS:
    pid = platform['id']
    if can_collect(pid):
      result.append(pid)
  return result
