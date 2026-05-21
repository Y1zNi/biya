"""应用路径与全局配置."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = 'SocialMediaTool'
APP_VERSION = '1.0.0'
WINDOW_TITLE = f'Social Media Collector v{APP_VERSION}'
WINDOW_SIZE = '1200x700'

APP_DATA_DIR = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming')) / APP_NAME
DB_FILE = APP_DATA_DIR / 'data.db'
STATES_DIR = APP_DATA_DIR / 'states'
TEMP_DIR = APP_DATA_DIR / 'temp'

LOGIN_TIMEOUT_SECONDS = 120
QR_REFRESH_INTERVAL_SECONDS = 1.5
# 登录时使用无头浏览器（后台运行，不弹窗）；若二维码加载失败可改为 False
LOGIN_HEADLESS = True
PAGE_SIZE = 20

COLLECT_REQUEST_INTERVAL = 2
COLLECT_PAGE_TIMEOUT = 60000
COLLECT_DEFAULT_MIN_DELAY_SEC = 2.0
COLLECT_DEFAULT_MAX_DELAY_SEC = 2.0
COLLECT_DEFAULT_RETRY_COUNT = 1
COLLECT_DEFAULT_PAGE_TIMEOUT_SEC = 60
COLLECT_DEFAULT_START_ROW = 1
COLLECT_DEFAULT_END_ROW = 0
COLLECT_PAGE_TIMEOUT_MIN_SEC = 10
COLLECT_PAGE_TIMEOUT_MAX_SEC = 180
# 采集使用无头模式，不弹出浏览器窗口
COLLECT_HEADLESS = True
EXPORT_DIR = APP_DATA_DIR / 'exports'

# 平台定义（enabled=False 表示开发中）
PLATFORMS = [
  {'id': 'douyin', 'name': '抖音', 'enabled': True},
  {'id': 'kuaishou', 'name': '快手', 'enabled': True},
  {'id': 'xiaohongshu', 'name': '小红书', 'enabled': True},
  {'id': 'weibo', 'name': '微博', 'enabled': True},
  {'id': 'bilibili', 'name': 'B站', 'enabled': True},
  {'id': 'vivo', 'name': 'vivo社区', 'enabled': True},
]

PLATFORM_LOGIN_URLS = {
  'douyin': 'https://www.douyin.com/',
  'kuaishou': 'https://www.kuaishou.com/new-reco',
  'xiaohongshu': 'https://www.xiaohongshu.com/',
  'weibo': 'https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog',
  'bilibili': 'https://www.bilibili.com/',
  'vivo': (
    'https://passport.vivo.com.cn/#/login?client_id=10'
    '&redirect_uri=https%3A%2F%2Fbbs.vivo.com.cn%2Fnewbbs%2F'
  ),
}


def ensure_dirs() -> None:
  APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
  STATES_DIR.mkdir(parents=True, exist_ok=True)
  TEMP_DIR.mkdir(parents=True, exist_ok=True)
  EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def get_platform_state_dir(platform: str) -> Path:
  path = STATES_DIR / platform
  path.mkdir(parents=True, exist_ok=True)
  return path


def get_state_file_path(platform: str, account_id: int) -> Path:
  return get_platform_state_dir(platform) / f'account_{account_id}.json'


def get_platform_name(platform_id: str) -> str:
  for p in PLATFORMS:
    if p['id'] == platform_id:
      return p['name']
  return platform_id


def format_account_display_id(platform: str, account_id: int) -> str:
  return f'{platform}_{account_id:03d}'
