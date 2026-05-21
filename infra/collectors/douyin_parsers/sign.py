"""抖音 a_bogus 签名（子进程调用自带 node.exe + douyin.js，不依赖 PyExecJS）."""

from __future__ import annotations

import asyncio
import json
import random
import subprocess
import sys
from typing import Literal

from playwright.async_api import Page

from infra.collectors.douyin_parsers.node_runtime import (
  get_sign_cli_path,
  get_sign_libs_dir,
  resolve_node_executable,
)

SignKind = Literal['detail', 'reply']


def get_web_id() -> str:
  """生成随机 webid（与 MediaCrawler 一致）."""

  def e(t):
    if t is not None:
      return str(t ^ (int(16 * random.random()) >> (t // 4)))
    return ''.join(
      [str(int(1e7)), '-', str(int(1e3)), '-', str(int(4e3)), '-', str(int(8e3)), '-', str(int(1e11))],
    )

  web_id = ''.join(e(int(x)) if x in '018' else x for x in e(None))
  return web_id.replace('-', '')[:19]


def _resolve_sign_kind(uri: str) -> SignKind:
  return 'reply' if '/reply' in uri else 'detail'


def _subprocess_no_window_kwargs() -> dict:
  """Windows 下隐藏 node 子进程控制台，避免打包 exe 采集时闪黑窗."""
  if sys.platform != 'win32':
    return {}
  flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
  return {'creationflags': flags}


def run_douyin_sign(
  kind: SignKind,
  query_string: str,
  user_agent: str,
  *,
  timeout_sec: float = 15,
) -> str:
  node_exe = resolve_node_executable()
  sign_cli = get_sign_cli_path()
  if not sign_cli.is_file():
    raise FileNotFoundError(f'签名脚本不存在: {sign_cli}')

  payload = json.dumps(
    {'kind': kind, 'query': query_string, 'ua': user_agent},
    ensure_ascii=False,
  )
  proc = subprocess.run(
    [str(node_exe), str(sign_cli)],
    input=payload,
    capture_output=True,
    text=True,
    encoding='utf-8',
    timeout=timeout_sec,
    cwd=str(get_sign_libs_dir()),
    check=False,
    **_subprocess_no_window_kwargs(),
  )
  if proc.returncode != 0:
    err = (proc.stderr or proc.stdout or 'douyin sign failed').strip()
    raise RuntimeError(err[:200])
  result = (proc.stdout or '').strip()
  if not result:
    raise RuntimeError('douyin sign returned empty')
  return result


async def get_a_bogus(
  uri: str,
  query_string: str,
  post_data: dict,
  user_agent: str,
  page: Page | None = None,
) -> str:
  """获取 a_bogus 参数（通过自带 Node 执行 sign_cli.js）."""
  del page, post_data
  kind = _resolve_sign_kind(uri)
  return await asyncio.to_thread(
    run_douyin_sign,
    kind,
    query_string,
    user_agent,
  )
