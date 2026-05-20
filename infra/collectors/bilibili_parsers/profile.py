"""登录后从 nav 接口获取 B 站昵称."""

from __future__ import annotations

from typing import Any, Dict, List

from infra.collectors.bilibili_parsers.api_client import fetch_nav


def nickname_from_nav(data: Dict[str, Any]) -> str:
  for key in ('uname', 'uname_spacesta'):
    text = str(data.get(key) or '').strip()
    if text:
      return text[:64]
  return ''


async def fetch_bilibili_nickname(cookies: List[Dict[str, Any]]) -> str:
  data, _, _ = await fetch_nav(cookies)
  if not data:
    return ''
  return nickname_from_nav(data)
