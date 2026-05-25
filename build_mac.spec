# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller macOS .app bundle build spec."""

import os
from pathlib import Path

EXE_NAME = os.environ.get('PYINSTALLER_EXE_NAME', 'SocialMediaTool')

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
project_root = Path(SPECPATH)
bundle_browsers = project_root / '_bundle' / 'ms-playwright'

hiddenimports = [
  'sqlite3',
  'asyncio',
  'tkinter',
  'tkinter.filedialog',
  'tkinter.messagebox',
  'PIL._tkinter_finder',
]
datas = []
binaries = []

if bundle_browsers.is_dir():
  datas.append((str(bundle_browsers), 'ms-playwright'))
else:
  raise SystemExit(
    f'Missing browser bundle: {bundle_browsers}\n'
    'Run python build_mac.py first (downloads and stages Chromium).'
  )

douyin_sign_libs = project_root / 'infra' / 'collectors' / 'douyin_parsers' / 'libs'
if not (douyin_sign_libs / 'douyin.js').is_file():
  raise SystemExit(f'Missing douyin sign scripts: {douyin_sign_libs}')
datas.append((str(douyin_sign_libs), 'douyin_sign/libs'))

bundle_node_bin = project_root / '_bundle' / 'node' / 'node'
if bundle_node_bin.is_file():
  datas.append((str(bundle_node_bin), 'node'))
else:
  raise SystemExit(
    f'Missing embedded Node: {bundle_node_bin}\n'
    'Run python build_mac.py first (downloads and stages node).'
  )

for pkg in ('customtkinter', 'playwright', 'openpyxl', 'PIL'):
  pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
  datas += pkg_datas
  binaries += pkg_binaries
  hiddenimports += pkg_hidden

hiddenimports += collect_submodules('infra.collectors')
hiddenimports += collect_submodules('infra.collectors.douyin_parsers')
hiddenimports += collect_submodules('infra.collectors.kuaishou_parsers')
hiddenimports = list(dict.fromkeys(hiddenimports))

excludes = [
  'matplotlib',
  'PyQt6',
  'PySide6',
  'scipy',
  'pandas',
  'numpy',
  'sqlalchemy',
  'psycopg2',
  'IPython',
  'notebook',
  'pytest',
  'tkinter.test',
]

a = Analysis(
  [str(project_root / 'main.py')],
  pathex=[str(project_root)],
  binaries=binaries,
  datas=datas,
  hiddenimports=hiddenimports,
  hookspath=[],
  hooksconfig={},
  runtime_hooks=[str(project_root / 'hooks' / 'runtime_playwright.py')],
  excludes=excludes,
  win_no_prefer_redirects=False,
  win_private_assemblies=False,
  cipher=block_cipher,
  noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
  pyz,
  a.scripts,
  [],
  exclude_binaries=True,
  name=EXE_NAME,
  debug=False,
  bootloader_ignore_signals=False,
  strip=False,
  upx=False,
  console=False,
  disable_windowed_traceback=False,
  argv_emulation=False,
  target_arch=None,
  codesign_identity=None,
  entitlements_file=None,
)

coll = COLLECT(
  exe,
  a.binaries,
  a.zipfiles,
  a.datas,
  strip=False,
  upx=False,
  upx_exclude=[],
  name=EXE_NAME,
)

app = BUNDLE(
  coll,
  name=f'{EXE_NAME}.app',
  icon=None,
  bundle_identifier='com.socialmedia.collector',
)
