#!/usr/bin/env python3
"""Social Media Collector - 入口."""

import multiprocessing

from config import ensure_dirs
from shared.device_guard import ensure_device_allowed
from ui.main_window import run_app

if __name__ == '__main__':
  multiprocessing.freeze_support()
  ensure_device_allowed()
  ensure_dirs()
  run_app()
