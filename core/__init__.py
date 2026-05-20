"""领域层：模型与平台规则."""

from core.export_schema import get_export_headers
from core.models import (
  CollectProgress,
  CollectResultItem,
  CollectRowStatus,
  CollectSummary,
  ExcelSheetData,
  PlatformDetectResult,
)
from core.platforms import can_collect, get_platform_name, list_collectable_platform_ids

__all__ = [
  'get_export_headers',
  'CollectProgress',
  'CollectResultItem',
  'CollectRowStatus',
  'CollectSummary',
  'ExcelSheetData',
  'PlatformDetectResult',
  'can_collect',
  'get_platform_name',
  'list_collectable_platform_ids',
]
