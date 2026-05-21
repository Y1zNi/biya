"""互动数字文案解析."""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Union

_EMPTY_VALUES = frozenset({'', '-', 'none', 'null', 'undefined'})


def pick_stat_value(data: Any, *keys: str) -> Any:
  """取 statistics 等对象中第一个存在的键（0 为有效值，不用 or）."""
  if not isinstance(data, Mapping):
    return None
  for key in keys:
    if key in data:
      return data[key]
  return None


def format_metric(value: Any, *, missing: str = '0') -> str:
  """平台有该指标时：接口缺失填 missing（默认 0），有值（含 0）原样格式化."""
  if value is None:
    return missing
  formatted = format_count(value)
  if formatted == '-':
    return missing
  return formatted


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
