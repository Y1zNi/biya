"""PyInstaller 运行时：将 Playwright 浏览器目录指向打包资源."""

import os
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
  candidates = []
  meipass = getattr(sys, '_MEIPASS', None)
  if meipass:
    candidates.append(Path(meipass) / 'ms-playwright')
  candidates.append(Path(sys.executable).resolve().parent / 'ms-playwright')
  for browsers_path in candidates:
    if browsers_path.is_dir():
      os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(browsers_path)
      break
