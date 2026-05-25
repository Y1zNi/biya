"""打包 exe 设备 MAC 白名单与开发者 key.txt 绕过."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

ALLOWED_MACS: frozenset[str] = frozenset({
  '62:74:b1:17:93:44',
  '70:ae:d5:53:7f:e0',
  'fc:b2:14:40:ea:1a',
})

DEV_KEY_FILENAME = 'key.txt'
DEV_KEY_VALUE = 'meyou'

_MAC_HEX_RE = re.compile(r'^[0-9a-f]{12}$')


def is_frozen() -> bool:
  return getattr(sys, 'frozen', False)


def get_exe_dir() -> Path:
  return Path(sys.executable).resolve().parent


def normalize_mac(text: str) -> str:
  raw = (text or '').strip().lower()
  if not raw:
    return ''
  compact = re.sub(r'[^0-9a-f]', '', raw)
  if not _MAC_HEX_RE.fullmatch(compact):
    return ''
  return ':'.join(compact[i:i + 2] for i in range(0, 12, 2))


def has_dev_key(exe_dir: Path | None = None) -> bool:
  base = exe_dir if exe_dir is not None else get_exe_dir()
  key_path = base / DEV_KEY_FILENAME
  if not key_path.is_file():
    return False
  try:
    content = key_path.read_text(encoding='utf-8').strip()
  except OSError:
    return False
  return content == DEV_KEY_VALUE


def _mac_from_uuid_node() -> str:
  node = uuid.getnode()
  if not node or (node >> 40) & 1:
    return ''
  return normalize_mac(f'{node:012x}')


def _macs_from_getmac() -> set[str]:
  creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
  try:
    completed = subprocess.run(
      ['getmac', '/fo', 'csv', '/nh'],
      capture_output=True,
      text=True,
      encoding='utf-8',
      errors='ignore',
      creationflags=creationflags,
      timeout=5,
      check=False,
    )
  except (OSError, subprocess.SubprocessError):
    return set()

  if completed.returncode != 0:
    return set()

  macs: set[str] = set()
  for line in (completed.stdout or '').splitlines():
    first_field = line.split(',', 1)[0].strip().strip('"')
    normalized = normalize_mac(first_field)
    if normalized:
      macs.add(normalized)
  return macs


def collect_local_macs() -> set[str]:
  macs = _macs_from_getmac()
  if macs:
    return macs
  fallback = _mac_from_uuid_node()
  return {fallback} if fallback else set()


def is_device_allowed() -> bool:
  if not is_frozen():
    return True
  if has_dev_key():
    return True
  local_macs = collect_local_macs()
  return bool(local_macs & ALLOWED_MACS)


def ensure_device_allowed() -> None:
  if not is_device_allowed():
    os._exit(0)
