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
