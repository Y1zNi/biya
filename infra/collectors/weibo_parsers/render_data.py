"""从详情页 HTML 解析 $render_data."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

RENDER_DATA_PATTERN = re.compile(
  r'var\s+\$render_data\s*=\s*(\[.*?\])\s*\[0\]',
  re.DOTALL,
)


def extract_mblog_from_html(html: str) -> Optional[Dict[str, Any]]:
  if not html:
    return None
  match = RENDER_DATA_PATTERN.search(html)
  if not match:
    return None
  try:
    render_list = json.loads(match.group(1))
  except json.JSONDecodeError:
    return None
  if not render_list or not isinstance(render_list, list):
    return None
  first = render_list[0]
  if not isinstance(first, dict):
    return None
  status = first.get('status')
  if isinstance(status, dict):
    return status
  return None
