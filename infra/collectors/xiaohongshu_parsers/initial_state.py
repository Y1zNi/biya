"""解析 window.__INITIAL_STATE__（登录昵称等）."""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def parse_initial_state_script(raw: str) -> Optional[dict]:
  if not raw:
    return None
  match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*</script>', raw, re.S)
  if not match:
    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+)', raw, re.S)
  if not match:
    return None
  try:
    state_text = match.group(1).replace(':undefined', ':null')
    return json.loads(state_text)
  except json.JSONDecodeError:
    return None


def get_user_page_data(data: object) -> Optional[dict]:
  if not isinstance(data, dict):
    return None
  user_block = data.get('user')
  if not isinstance(user_block, dict):
    return None
  user_page = user_block.get('userPageData') or user_block.get('user_page_data')
  if isinstance(user_page, dict):
    return user_page
  return None


def find_user_page_data(obj: object) -> Optional[dict]:
  if isinstance(obj, dict):
    if 'basicInfo' in obj or 'basic_info' in obj:
      return obj
    if isinstance(obj.get('userPageData'), dict):
      return obj['userPageData']
    for value in obj.values():
      found = find_user_page_data(value)
      if found:
        return found
  elif isinstance(obj, list):
    for item in obj[:20]:
      found = find_user_page_data(item)
      if found:
        return found
  return None


def nickname_from_user_page(user_page: Optional[dict]) -> str:
  if not user_page:
    return ''
  basic = user_page.get('basicInfo') or user_page.get('basic_info') or {}
  if not isinstance(basic, dict):
    return ''
  for key in ('nickname', 'nickName', 'name', 'userName'):
    value = str(basic.get(key, '')).strip()
    if value:
      return value
  return ''
