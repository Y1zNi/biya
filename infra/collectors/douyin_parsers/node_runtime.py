"""抖音签名用 Node 运行时路径解析（开发 / PyInstaller 打包）."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parents[2]
_LIBS_DIR = _MODULE_DIR / 'libs'
_SIGN_CLI = _LIBS_DIR / 'sign_cli.js'


def is_frozen() -> bool:
  return getattr(sys, 'frozen', False)


def get_meipass() -> Path | None:
  meipass = getattr(sys, '_MEIPASS', None)
  return Path(meipass) if meipass else None


def get_sign_libs_dir() -> Path:
  if is_frozen():
    meipass = get_meipass()
    if meipass:
      bundled = meipass / 'douyin_sign' / 'libs'
      if bundled.is_dir():
        return bundled
  return _LIBS_DIR


def get_sign_cli_path() -> Path:
  return get_sign_libs_dir() / 'sign_cli.js'


def _node_binary_name() -> str:
  return 'node.exe' if sys.platform == 'win32' else 'node'


def _bundled_node_path(base: Path) -> Path:
  return base / 'node' / _node_binary_name()


def resolve_node_executable() -> Path:
  node_name = _node_binary_name()
  if is_frozen():
    meipass = get_meipass()
    if meipass:
      bundled = _bundled_node_path(meipass)
      if bundled.is_file():
        return bundled

  bundled_dev = _PROJECT_ROOT / '_bundle' / 'node' / node_name
  if bundled_dev.is_file():
    return bundled_dev

  which = shutil.which('node')
  if which:
    return Path(which)

  build_hint = 'python build.py' if sys.platform == 'win32' else 'python build_mac.py'
  raise FileNotFoundError(
    f'未找到 Node 运行时。请先执行 {build_hint} 打包 Node，'
    '或在开发机安装 Node.js 并加入 PATH。',
  )
