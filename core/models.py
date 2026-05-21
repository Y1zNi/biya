"""数据采集相关类型定义."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CollectRowStatus(str, Enum):
  SUCCESS = 'success'
  UNSUPPORTED = 'unsupported'
  FAILED = 'failed'
  LOGIN_EXPIRED = 'login_expired'


COLLECT_ROW_STATUS_LABELS = {
  CollectRowStatus.SUCCESS: '成功',
  CollectRowStatus.UNSUPPORTED: '暂不支持',
  CollectRowStatus.FAILED: '失败',
  CollectRowStatus.LOGIN_EXPIRED: '登录已过期',
}

@dataclass
class CollectResultItem:
  link: str
  platform_id: str = ''
  platform_name: str = ''
  author_name: str = ''
  note_id: str = '-'
  author_id: str = '-'
  publish_time: str = '-'
  views: str = '-'
  likes: str = '-'
  favorites: str = '-'
  comments: str = '-'
  shares: str = '-'
  coins: str = '-'
  media_type: str = '-'
  status: CollectRowStatus = CollectRowStatus.FAILED
  error_msg: str = ''

  @property
  def status_label(self) -> str:
    label = COLLECT_ROW_STATUS_LABELS.get(self.status, self.status.value)
    if self.error_msg and self.status != CollectRowStatus.SUCCESS:
      return f'{label}: {self.error_msg}'
    return label

  def to_export_row(self, platform_id: str = '') -> list:
    from core.export_schema import item_to_export_cells

    pid = platform_id or self.platform_id or 'unknown'
    return item_to_export_cells(self, pid)


@dataclass
class CollectProgress:
  current: int = 0
  total: int = 0
  current_link: str = ''
  message: str = ''


@dataclass
class CollectParams:
  min_delay_sec: float = 2.0
  max_delay_sec: float = 2.0
  retry_count: int = 1
  page_timeout_sec: int = 60
  start_row: int = 1
  end_row: int = 0

  @property
  def page_timeout_ms(self) -> int:
    return max(1, self.page_timeout_sec) * 1000

  @classmethod
  def defaults(cls) -> 'CollectParams':
    from config import (
      COLLECT_DEFAULT_END_ROW,
      COLLECT_DEFAULT_MAX_DELAY_SEC,
      COLLECT_DEFAULT_MIN_DELAY_SEC,
      COLLECT_DEFAULT_PAGE_TIMEOUT_SEC,
      COLLECT_DEFAULT_RETRY_COUNT,
      COLLECT_DEFAULT_START_ROW,
    )

    return cls(
      min_delay_sec=COLLECT_DEFAULT_MIN_DELAY_SEC,
      max_delay_sec=COLLECT_DEFAULT_MAX_DELAY_SEC,
      retry_count=COLLECT_DEFAULT_RETRY_COUNT,
      page_timeout_sec=COLLECT_DEFAULT_PAGE_TIMEOUT_SEC,
      start_row=COLLECT_DEFAULT_START_ROW,
      end_row=COLLECT_DEFAULT_END_ROW,
    )


@dataclass
class CollectSummary:
  total: int = 0
  success_count: int = 0
  failed_count: int = 0
  unsupported_count: int = 0
  login_expired: bool = False
  cancelled: bool = False
  task_id: Optional[int] = None
  expired_account_ids: list[int] = field(default_factory=list)


@dataclass
class PlatformDetectResult:
  platform_id: str
  platform_name: str
  can_collect: bool


@dataclass
class ExcelSheetData:
  headers: list[str] = field(default_factory=list)
  rows: list[list] = field(default_factory=list)
