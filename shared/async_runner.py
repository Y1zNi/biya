"""在后台线程运行 asyncio 协程."""

from __future__ import annotations

import asyncio
import threading
from typing import Awaitable, Callable, TypeVar

T = TypeVar('T')


def run_coro_in_thread(
  coro: Awaitable[T],
  on_complete: Callable[[T], None],
  on_error: Callable[[Exception], None],
) -> None:
  def _target() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      result = loop.run_until_complete(coro)
      on_complete(result)
    except Exception as exc:
      on_error(exc)
    finally:
      loop.close()

  thread = threading.Thread(target=_target, daemon=True)
  thread.start()
