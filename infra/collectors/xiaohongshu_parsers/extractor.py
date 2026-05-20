"""从页面 HTML 解析小红书笔记详情."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def _get_note_from_state(state: Dict[str, Any], note_id: str) -> Optional[Dict]:
  note_block = state.get('note') or state.get('Note') or {}
  detail_map = (
    note_block.get('note_detail_map')
    or note_block.get('noteDetailMap')
    or {}
  )
  entry = detail_map.get(note_id) or {}
  if isinstance(entry, dict):
    note = entry.get('note') or entry.get('Note')
    if isinstance(note, dict):
      return note
  return None


def extract_note_detail_from_html(note_id: str, html: str) -> Optional[Dict]:
  if not html or 'noteDetailMap' not in html and 'note_detail_map' not in html:
    return None

  matches = re.findall(r'window\.__INITIAL_STATE__=({.*})</script>', html, re.S)
  if not matches:
    return None

  state_text = matches[0].replace('undefined', '""')
  if state_text == '{}':
    return None

  try:
    state = json.loads(state_text)
  except json.JSONDecodeError:
    return None

  return _get_note_from_state(state, note_id)
