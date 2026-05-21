"""采集批处理运行期配置（页面超时等）."""

from __future__ import annotations

from config import COLLECT_PAGE_TIMEOUT

_batch_page_timeout_ms = COLLECT_PAGE_TIMEOUT


def set_batch_page_timeout_ms(timeout_ms: int) -> None:
  global _batch_page_timeout_ms
  _batch_page_timeout_ms = max(1000, int(timeout_ms))


def get_batch_page_timeout_ms() -> int:
  return _batch_page_timeout_ms


def reset_batch_page_timeout_ms() -> None:
  global _batch_page_timeout_ms
  _batch_page_timeout_ms = COLLECT_PAGE_TIMEOUT
