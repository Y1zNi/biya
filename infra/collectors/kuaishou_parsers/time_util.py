"""快手发布时间（页面 DOM 原文）."""

from __future__ import annotations

from typing import Any


def format_dom_photo_time(raw: Any) -> str:
  """页面 .photo-time 文案原样保留，如 2月前、3天前."""
  text = str(raw or '').strip()
  return text if text else '-'
