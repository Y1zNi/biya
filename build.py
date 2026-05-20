#!/usr/bin/env python3
"""Build a single Windows exe with embedded Playwright Chromium."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import APP_NAME, PLATFORMS

BUNDLE_DIR = ROOT / '_bundle' / 'ms-playwright'
NODE_DIR = ROOT / '_bundle' / 'node'
NODE_EXE = NODE_DIR / 'node.exe'
NODE_VERSION = '18.20.8'
NODE_WIN_ZIP = f'node-v{NODE_VERSION}-win-x64.zip'
NODE_DOWNLOAD_URL = f'https://nodejs.org/dist/v{NODE_VERSION}/{NODE_WIN_ZIP}'
EXE_FILE = ROOT / 'dist' / f'{APP_NAME}.exe'
RELEASE_DIR = ROOT / 'release'


def run(cmd: list[str], **kwargs) -> None:
  print('>', ' '.join(cmd))
  subprocess.run(cmd, check=True, **kwargs)


def get_ms_playwright_dir() -> Path:
  env_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
  if env_path:
    path = Path(env_path)
    if path.is_dir():
      return path

  local_app_data = os.environ.get('LOCALAPPDATA')
  if local_app_data:
    path = Path(local_app_data) / 'ms-playwright'
    if path.is_dir():
      return path

  home = Path.home()
  for candidate in (
    home / 'AppData' / 'Local' / 'ms-playwright',
    home / 'Library' / 'Caches' / 'ms-playwright',
    home / '.cache' / 'ms-playwright',
  ):
    if candidate.is_dir():
      return candidate

  raise FileNotFoundError(
    'Playwright browsers not found. Run: python -m playwright install chromium'
  )


def ensure_dependencies() -> None:
  run([sys.executable, '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')])
  run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
  run([sys.executable, '-m', 'playwright', 'install', 'chromium'])


def stage_playwright_browsers() -> None:
  src = get_ms_playwright_dir()
  if BUNDLE_DIR.exists():
    shutil.rmtree(BUNDLE_DIR)
  print(f'Staging embedded browsers: {src} -> {BUNDLE_DIR}')
  shutil.copytree(src, BUNDLE_DIR)


def stage_node_runtime() -> None:
  if NODE_EXE.is_file():
    print(f'Embedded Node already staged: {NODE_EXE}')
    return

  import urllib.request

  NODE_DIR.mkdir(parents=True, exist_ok=True)
  zip_path = NODE_DIR / NODE_WIN_ZIP
  print(f'Downloading Node {NODE_VERSION}: {NODE_DOWNLOAD_URL}')
  urllib.request.urlretrieve(NODE_DOWNLOAD_URL, zip_path)
  try:
    with zipfile.ZipFile(zip_path, 'r') as zf:
      node_member = f'node-v{NODE_VERSION}-win-x64/node.exe'
      with zf.open(node_member) as src, open(NODE_EXE, 'wb') as dst:
        shutil.copyfileobj(src, dst)
  finally:
    zip_path.unlink(missing_ok=True)

  if not NODE_EXE.is_file():
    raise FileNotFoundError(f'Failed to stage node.exe at {NODE_EXE}')
  print(f'Staged embedded Node: {NODE_EXE}')


def build_exe() -> None:
  if EXE_FILE.exists():
    EXE_FILE.unlink()
  env = os.environ.copy()
  env['PYINSTALLER_EXE_NAME'] = APP_NAME
  run(
    [
      sys.executable,
      '-m',
      'PyInstaller',
      str(ROOT / 'build.spec'),
      '--noconfirm',
      '--clean',
    ],
    env=env,
  )
  if not EXE_FILE.exists():
    raise FileNotFoundError(f'Exe not found: {EXE_FILE}')


def get_enabled_platform_names() -> str:
  names = [p['name'] for p in PLATFORMS if p.get('enabled')]
  return '、'.join(names) if names else '见软件内说明'


def write_readme() -> Path:
  readme = RELEASE_DIR / 'README.txt'
  platform_line = get_enabled_platform_names()
  readme.write_text(
    '\n'.join(
      [
        'Social Media Collector',
        '',
        f'1. Run {APP_NAME}.exe directly (Python not required).',
        '2. First launch unpacks embedded Chromium and Node; wait 10-20 seconds.',
        '3. No need to install Python, Node.js, or Playwright separately.',
        '4. If antivirus blocks the app, add it to the allow list.',
        '5. Accounts and exports: %APPDATA%\\SocialMediaTool',
        f'6. Supported platforms: {platform_line}.',
        '',
      ]
    ),
    encoding='utf-8',
  )
  return readme


def clean_release_dir() -> None:
  """移除 release 内过期的 zip/说明，避免与本次打包产物混在一起."""
  if not RELEASE_DIR.is_dir():
    return
  for path in RELEASE_DIR.iterdir():
    if path.name == '.gitkeep':
      continue
    if path.is_file():
      path.unlink()
    elif path.is_dir():
      shutil.rmtree(path)


def create_zip() -> Path:
  RELEASE_DIR.mkdir(parents=True, exist_ok=True)
  clean_release_dir()
  zip_path = RELEASE_DIR / f'{APP_NAME}.zip'
  if zip_path.exists():
    zip_path.unlink()
  print(f'Creating zip: {zip_path}')
  with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    zf.write(EXE_FILE, EXE_FILE.name)
    readme = write_readme()
    zf.write(readme, readme.name)
  return zip_path


def format_size(num_bytes: int) -> str:
  mb = num_bytes / (1024 * 1024)
  return f'{mb:.1f} MB'


def main() -> None:
  os.chdir(ROOT)
  print('=== Installing dependencies ===')
  ensure_dependencies()
  print('=== Staging Chromium ===')
  stage_playwright_browsers()
  print('=== Staging Node (Douyin sign) ===')
  stage_node_runtime()
  print('=== Building single-file exe (large, please wait) ===')
  build_exe()
  zip_path = create_zip()
  exe_size = EXE_FILE.stat().st_size
  print('')
  print('Build complete.')
  print(f'Exe: {EXE_FILE} ({format_size(exe_size)})')
  print(f'Zip: {zip_path} ({format_size(zip_path.stat().st_size)})')


if __name__ == '__main__':
  main()
