"""互动数字文案解析."""

from __future__ import annotations

import re
from typing import Any, Optional, Union

_EMPTY_VALUES = frozenset({'', '-', 'none', 'null', 'undefined'})


def format_count(value: Any) -> str:
  if value is None:
    return '-'
  if isinstance(value, bool):
    return str(int(value))
  if isinstance(value, (int, float)):
    if value < 0:
      return '-'
    if isinstance(value, float) and value.is_integer():
      return str(int(value))
    return str(int(value)) if float(value).is_integer() else str(value)

  text = str(value).strip()
  if not text or text.lower() in _EMPTY_VALUES:
    return '-'

  parsed = parse_count_text(text)
  if parsed is None:
    return text
  return str(parsed)


def _normalize_count_text(text: str) -> str:
  raw = (text or '').strip()
  raw = raw.replace(',', '').replace('，', '').replace('\u00a0', '').replace(' ', '')
  raw = re.sub(r'(次播放|播放量|播放|观看|次观看)$', '', raw, flags=re.I)
  return raw


def parse_count_text(text: str) -> Optional[int]:
  raw = _normalize_count_text(text)
  if not raw or raw.lower() in _EMPTY_VALUES:
    return None

  if raw.isdigit():
    return int(raw)

  match = re.search(r'([\d.]+)\s*([万亿Ww])', raw, re.I)
  if match:
    number = float(match.group(1))
    unit = match.group(2).lower()
    if unit in ('万', 'w'):
      number *= 10000
    elif unit == '亿':
      number *= 100000000
    return int(number)

  match = re.match(r'^([\d.]+)$', raw)
  if match:
    return int(float(match.group(1)))
  return None
