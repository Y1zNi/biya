#!/usr/bin/env python3
"""Build a macOS .app bundle with embedded Playwright Chromium (Apple Silicon)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import APP_NAME, PLATFORMS

BUNDLE_DIR = ROOT / '_bundle' / 'ms-playwright'
NODE_DIR = ROOT / '_bundle' / 'node'
NODE_BIN = NODE_DIR / 'node'
NODE_VERSION = '18.20.8'
NODE_TAR = f'node-v{NODE_VERSION}-darwin-arm64.tar.gz'
NODE_DOWNLOAD_URL = f'https://nodejs.org/dist/v{NODE_VERSION}/{NODE_TAR}'
APP_DIR = ROOT / 'dist' / f'{APP_NAME}.app'
RELEASE_DIR = ROOT / 'release'
RELEASE_ZIP = RELEASE_DIR / f'{APP_NAME}-mac-arm64.zip'
VENV_DIR = ROOT / '.venv'
VENV_PYTHON = VENV_DIR / 'bin' / 'python'


def ensure_build_venv() -> None:
  """Homebrew Python (PEP 668) 不允许全局 pip，构建依赖装进 .venv。"""
  if Path(sys.executable).resolve() == VENV_PYTHON.resolve():
    return
  if not VENV_PYTHON.is_file():
    print(f'=== Creating build venv: {VENV_DIR} ===')
    run([sys.executable, '-m', 'venv', str(VENV_DIR)])
  os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


def run(cmd: list[str], **kwargs) -> None:
  print('>', ' '.join(cmd))
  subprocess.run(cmd, check=True, **kwargs)


def get_ms_playwright_dir() -> Path:
  env_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
  if env_path:
    path = Path(env_path)
    if path.is_dir():
      return path

  home = Path.home()
  for candidate in (
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
  run([sys.executable, '-m', 'playwright', 'install', '--with-deps', 'chromium'])


def stage_playwright_browsers() -> None:
  src = get_ms_playwright_dir()
  if BUNDLE_DIR.exists():
    shutil.rmtree(BUNDLE_DIR)
  print(f'Staging embedded browsers: {src} -> {BUNDLE_DIR}')
  shutil.copytree(src, BUNDLE_DIR)


def stage_node_runtime() -> None:
  if NODE_BIN.is_file():
    print(f'Embedded Node already staged: {NODE_BIN}')
    return

  import urllib.request

  NODE_DIR.mkdir(parents=True, exist_ok=True)
  tar_path = NODE_DIR / NODE_TAR
  print(f'Downloading Node {NODE_VERSION}: {NODE_DOWNLOAD_URL}')
  urllib.request.urlretrieve(NODE_DOWNLOAD_URL, tar_path)
  try:
    with tarfile.open(tar_path, 'r:gz') as tf:
      node_member = f'node-v{NODE_VERSION}-darwin-arm64/bin/node'
      extracted = tf.extractfile(node_member)
      if extracted is None:
        raise FileNotFoundError(f'Missing {node_member} in {NODE_TAR}')
      with open(NODE_BIN, 'wb') as dst:
        shutil.copyfileobj(extracted, dst)
    NODE_BIN.chmod(0o755)
  finally:
    tar_path.unlink(missing_ok=True)

  if not NODE_BIN.is_file():
    raise FileNotFoundError(f'Failed to stage node at {NODE_BIN}')
  print(f'Staged embedded Node: {NODE_BIN}')


def build_app() -> None:
  if APP_DIR.exists():
    shutil.rmtree(APP_DIR)
  env = os.environ.copy()
  env['PYINSTALLER_EXE_NAME'] = APP_NAME
  run(
    [
      sys.executable,
      '-m',
      'PyInstaller',
      str(ROOT / 'build_mac.spec'),
      '--noconfirm',
      '--clean',
    ],
    env=env,
  )
  if not APP_DIR.is_dir():
    raise FileNotFoundError(f'App bundle not found: {APP_DIR}')


def embed_playwright_into_app() -> None:
  """Chromium.app 不能经 PyInstaller COLLECT（会触发 codesign 失败），打包后手动复制。"""
  target = APP_DIR / 'Contents' / 'MacOS' / 'ms-playwright'
  if target.exists():
    shutil.rmtree(target)
  print(f'Embedding browsers into app: {BUNDLE_DIR} -> {target}')
  shutil.copytree(BUNDLE_DIR, target)


def maybe_codesign() -> None:
  if os.environ.get('CODESIGN_APP') != '1':
    return
  print('=== Ad-hoc codesign ===')
  run(['codesign', '--force', '--deep', '--sign', '-', str(APP_DIR)])


def get_enabled_platform_names() -> str:
  names = [p['name'] for p in PLATFORMS if p.get('enabled')]
  return '、'.join(names) if names else '见软件内说明'


def write_readme() -> Path:
  readme = RELEASE_DIR / 'README-mac.txt'
  platform_line = get_enabled_platform_names()
  readme.write_text(
    '\n'.join(
      [
        'Social Media Collector (macOS Apple Silicon)',
        '',
        f'1. Unzip and open {APP_NAME}.app (Python not required).',
        '2. First launch unpacks embedded Chromium and Node; wait 10-20 seconds.',
        '3. If macOS blocks the app: right-click the app -> Open, or run:',
        f'   xattr -cr {APP_NAME}.app',
        '4. No need to install Python, Node.js, or Playwright separately.',
        f'5. Accounts and exports: ~/Library/Application Support/{APP_NAME}',
        f'6. Supported platforms: {platform_line}.',
        '',
      ]
    ),
    encoding='utf-8',
  )
  return readme


def clean_release_dir() -> None:
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
  if RELEASE_ZIP.exists():
    RELEASE_ZIP.unlink()
  print(f'Creating zip: {RELEASE_ZIP}')
  readme = write_readme()
  with zipfile.ZipFile(RELEASE_ZIP, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for file_path in APP_DIR.rglob('*'):
      if file_path.is_file():
        arcname = file_path.relative_to(APP_DIR.parent)
        zf.write(file_path, arcname.as_posix())
    zf.write(readme, readme.name)
  return RELEASE_ZIP


def format_size(num_bytes: int) -> str:
  mb = num_bytes / (1024 * 1024)
  return f'{mb:.1f} MB'


def main() -> None:
  if sys.platform != 'darwin':
    raise SystemExit('build_mac.py must run on macOS (Apple Silicon recommended).')

  ensure_build_venv()
  os.chdir(ROOT)
  print('=== Installing dependencies ===')
  ensure_dependencies()
  print('=== Staging Chromium ===')
  stage_playwright_browsers()
  print('=== Staging Node (Douyin sign) ===')
  stage_node_runtime()
  print('=== Building .app bundle (large, please wait) ===')
  build_app()
  embed_playwright_into_app()
  maybe_codesign()
  zip_path = create_zip()
  app_size = sum(f.stat().st_size for f in APP_DIR.rglob('*') if f.is_file())
  print('')
  print('Build complete.')
  print(f'App: {APP_DIR} ({format_size(app_size)})')
  print(f'Zip: {zip_path} ({format_size(zip_path.stat().st_size)})')


if __name__ == '__main__':
  main()
