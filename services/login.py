"""Playwright 登录处理（抖音/快手：打开登录入口，页面截图获取二维码）."""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Tuple

from playwright.async_api import (
  Browser,
  BrowserContext,
  Frame,
  Locator,
  Page,
  Playwright,
  async_playwright,
)

from config import (
  LOGIN_HEADLESS,
  LOGIN_TIMEOUT_SECONDS,
  PLATFORM_LOGIN_URLS,
  QR_REFRESH_INTERVAL_SECONDS,
)
from infra.collectors.douyin_parsers.page import dismiss_overlays
from infra.collectors.bilibili_parsers.profile import fetch_bilibili_nickname
from infra.collectors.vivo_parsers.profile import VIVO_BBS_HOME_URL, fetch_vivo_nickname
from infra.collectors.weibo_parsers.profile import fetch_weibo_nickname
from infra.collectors.xiaohongshu_parsers import initial_state as xhs_initial_state
from shared.async_runner import run_coro_in_thread

OnQrImage = Callable[[bytes], None]
OnStatus = Callable[[str], None]

# 抖音 PC 登录后顶部头像为 live-avatar（非 user-avatar）
LOGGED_IN_SELECTORS = [
  'header [data-e2e="live-avatar"]',
  'header a[href*="/user/self"] [data-e2e="live-avatar"]',
  '#douyin-header-menuCt [data-e2e="live-avatar"]',
]

DOUYIN_HOME_URL = 'https://www.douyin.com/'
KUAISHOU_HOME_URL = 'https://www.kuaishou.com/new-reco'
XIAOHONGSHU_HOME_URL = 'https://www.xiaohongshu.com/'
WEIBO_SSO_URL = 'https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog'
WEIBO_HOME_URL = 'https://m.weibo.cn'

WEIBO_QR_IMG_SELECTORS = [
  'xpath=//img[@class="w-full h-full"]',
  'img.w-full.h-full',
]

WEIBO_LOGIN_COOKIE_NAMES = frozenset({'SSOLoginState', 'WBPSESS'})

BILIBILI_HOME_URL = 'https://www.bilibili.com/'

BILIBILI_LOGIN_BUTTON_SELECTORS = [
  'xpath=//*[@id="app"]/motion[2]/div[1]/motion[1]/motion[1]/motion[1]/div[1]/motion[1]/motion[1]/div[1]/ul[2]/li[1]',
  'xpath=//*[@id="app"]/div[2]/motion[1]/motion[1]/motion[1]/div[1]/motion[1]/div[1]/ul[2]/li[1]',
  'xpath=//*[@id="app"]/div[2]/div[1]/motion[1]/motion[1]/div[1]/ul[2]/li[1]',
  '.right-entry__outside.go-login-btn',
  '.go-login-btn',
  'text=登录',
]

BILIBILI_QR_IMG_SELECTORS = [
  'xpath=//motion[@class="login-scan-box"]//img',
  'div.login-scan-box img',
  '[class*="login-scan"] img',
  'img[src*="qrcode"]',
  'img[src^="data:image"]',
]

BILIBILI_LOGIN_MODAL_SELECTORS = [
  '.login-scan-box',
  '[class*="login-scan"]',
  '[class*="bili-login"]',
  '[class*="login-panel"]',
]

BILIBILI_LOGIN_COOKIE_NAMES = frozenset({'SESSDATA', 'DedeUserID'})

VIVO_LOGIN_URL = (
  'https://passport.vivo.com.cn/#/login?client_id=10'
  '&redirect_uri=https%3A%2F%2Fbbs.vivo.com.cn%2Fnewbbs%2F'
)

VIVO_QR_MODE_SWITCH_SELECTORS = [
  '.login-switch',
  '.login-switch img.hover',
  '.login-switch img:last-of-type',
  'xpath=//div[contains(@class,"login-switch")]//img[2]',
]

VIVO_QR_IMG_SELECTORS = [
  '.layout .inner-box img[src^="http"]',
  '.layout .inner-box img[src*="qrcode"]',
  'img[src*="qrcode"]',
  'img[src^="data:image"]',
]

VIVO_LOGIN_MODAL_SELECTORS = [
  '.login.pc-login-banner-content',
  '.layout .inner-box',
  '[class*="login-scan"]',
]

VIVO_LOGGED_IN_SELECTORS = [
  '.login-container .login-main-left span.name.ellipsis',
  '.login-container span.name.ellipsis',
  '.login-main-left span.name',
]

VIVO_LOGIN_COOKIE_NAMES = frozenset({
  'vvc_token',
  'vvc_account',
  'token',
  'bbs_token',
  'BBSSESSION',
  'sessionid',
})

# 小红书未登录时通常会自动弹出登录框；二维码在 .qrcode-img
XIAOHONGSHU_QR_IMG_SELECTORS = [
  'img.qrcode-img',
  '.qrcode-img',
  '[class*="qrcode-img"] img',
  'img[src*="qrcode"]',
  'img[src^="data:image"]',
]

XIAOHONGSHU_LOGIN_MODAL_SELECTORS = [
  '.login-container',
  '[class*="login-container"]',
  '[class*="login-modal"]',
  '[class*="passport"]',
]

XIAOHONGSHU_LOGIN_BUTTON_SELECTORS = [
  '#app button:has-text("登录")',
  'header button:has-text("登录")',
  'xpath=//*[@id="app"]//button[contains(., "登录")]',
  'xpath=//*[@id="app"]/motion/button',
  'text=登录',
]

XIAOHONGSHU_LOGGED_IN_SELECTORS = [
  'a[href*="/user/profile/"]',
  'a[href*="/user/profile/"] span:has-text("我")',
  '[class*="user-avatar"]',
  '[class*="avatar"][class*="user"]',
  'header a[href*="/user/"]',
]

XIAOHONGSHU_LOGIN_COOKIE_NAMES = frozenset({'web_session'})

# 登录后点击侧栏「我」进入个人主页（首页 __INITIAL_STATE__ 通常无 nickname）
XIAOHONGSHU_PROFILE_LINK_SELECTORS = [
  'xpath=//*[@id="global"]/motion[2]/motion[1]/ul/div[1]/li[5]/motion/a',
  'xpath=//*[@id="global"]/div[2]/div[1]/ul/div[1]/li[5]/div/a',
  'xpath=//*[@id="global"]/div[2]/motion[1]/ul/div[1]/li[5]/motion/a',
  'xpath=//a[contains(@href, "/user/profile/")]//span[text()="我"]/ancestor::a[1]',
  'xpath=//a[contains(@href, "/user/profile/")]//span[contains(text(), "我")]/ancestor::a[1]',
  'a[href*="/user/profile/"]',
]

XIAOHONGSHU_NICKNAME_SELECTORS = [
  '[class*="user-name"]',
  '[class*="nickname"]',
  '[class*="userNickname"]',
  '.user-nickname',
  'div.user-info .name',
  'h1[class*="name"]',
]

# 快手侧栏「立即登录」按钮（未登录时不会自动弹窗，需主动点击）
KUAISHOU_LOGIN_BUTTON_SELECTORS = [
  '.sidebar-login-button',
  '[class*="sidebar-login-button"]',
  'span.sidebar-login-button',
  'span:has-text("立即登录")',
  'button:has-text("登录")',
  'p:has-text("登录")',
  'text=立即登录',
  'text=登录',
]

KUAISHOU_QR_IMG_SELECTORS = [
  '.qrcode-img img',
  '[class*="qrcode-img"] img',
  '[class*="qrcode"] img',
  'img[src*="qrcode"]',
  'img[src^="data:image"]',
]

KUAISHOU_LOGIN_MODAL_SELECTORS = [
  '[class*="qrcode"]',
  '[class*="login-modal"]',
  '[class*="login-panel"]',
  '[class*="passport"]',
  'motion[class*="login"]',
]

KUAISHOU_LOGGED_IN_SELECTORS = [
  '.sidebar-login-button',
  'span:has-text("立即登录")',
  'text=登录即可享受',
]

# 登录后侧栏用户信息（勿用 feed 内 a.name，会误取当前视频作者昵称）
KUAISHOU_NICKNAME_SELECTORS = [
  '.down-box.login .user.item .text-name._qu-ellipsis',
  '.down-box.login .text-name._qu-ellipsis',
  '.down-box.login .user .text-name',
  '.wb-left .sidebar .down-box.login .text-name',
]

KUAISHOU_LOGIN_COOKIE_NAMES = frozenset({'passToken'})

# 登录弹窗内二维码候选选择器（按优先级）
QR_CANVAS_SELECTORS = [
  '[class*="login"] canvas',
  '[class*="modal"] canvas',
  '[class*="qrcode"] canvas',
  'canvas',
]

QR_IMG_SELECTORS = [
  'img[src*="qrcode"]',
  'img[src*="qr_code"]',
  'img[src^="data:image"]',
  '[class*="qrcode"] img',
  '[class*="qr"] img',
]

LOGIN_MODAL_SELECTORS = [
  '[class*="login-panel"]',
  '[class*="login-modal"]',
  '[class*="passport-login"]',
  '[class*="passport"]',
  'div[class*="login"]',
]

PASSPORT_LOGIN_URLS = (
  'https://www.douyin.com/passport/web/login/',
  'https://www.douyin.com/login',
)

MAX_QR_CANDIDATES = 12

# 登录后 hover/点击头像出现的个人面板（抖音 PC 实测类名）
USER_POPOVER_SELECTORS = [
  '[class*="userMenuPanel"]',
  '.userMenuPanelShadowAnimation',
  '[class*="userMenuPanelShadow"]',
]

USER_NAME_IN_POPOVER = [
  'a[href*="/user/self"][href*="personal_panel"]:not([href*="showTab"])',
  'a[href*="/user/self"][href*="personal_panel"]',
  'a[href*="/user/self"]',
  '[class*="user-name"]',
  '[class*="nickname"]',
]

HEADER_AVATAR_SELECTORS = [
  'header [data-e2e="live-avatar"]',
  '#douyin-header-menuCt [data-e2e="live-avatar"]',
  'header a[href*="/user/self"]',
  'a[href="//www.douyin.com/user/self"]',
]

QR_MIN_SIZE = 100
QR_MAX_SIZE = 450

# 仅这些 Cookie 表示真正登录
LOGIN_COOKIE_NAMES = frozenset({'sessionid', 'sessionid_ss'})


@dataclass
class LoginResult:
  success: bool
  message: str
  state_path: Optional[Path] = None
  nickname: str = ''


@dataclass
class LoginFlowState:
  qr_captured: bool = False
  logged_in: bool = False
  qr_pending_confirm: bool = False
  baseline_cookie_values: dict[str, str] | None = None


class LoginHandler:
  """平台扫码登录处理器."""

  def __init__(self, platform_id: str) -> None:
    self.platform_id = platform_id
    self.login_url = PLATFORM_LOGIN_URLS.get(platform_id, DOUYIN_HOME_URL)
    self._cancelled = False
    self._playwright: Optional[Playwright] = None
    self._browser: Optional[Browser] = None
    self._context: Optional[BrowserContext] = None
    self._page: Optional[Page] = None
    self._on_qr_image: Optional[OnQrImage] = None
    self._on_status: Optional[OnStatus] = None
    self._flow_state = LoginFlowState()

  def cancel(self) -> None:
    self._cancelled = True

  async def run_login(
    self,
    state_path: Path,
    on_qr_image: OnQrImage,
    on_status: OnStatus,
  ) -> LoginResult:
    self._cancelled = False
    self._on_qr_image = on_qr_image
    self._on_status = on_status
    self._flow_state = LoginFlowState()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    try:
      on_status('正在启动浏览器...')
      await self._start_browser()

      if self._page is None:
        return LoginResult(False, '浏览器启动失败')

      refresh_task = None
      if self.platform_id == 'douyin':
        on_status('正在加载抖音...')
        await self._page.goto(DOUYIN_HOME_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(2)
        await self._open_douyin_scan_login(on_status)
        refresh_task = asyncio.create_task(self._qr_refresh_loop(on_status))
      elif self.platform_id == 'kuaishou':
        on_status('正在加载快手...')
        await self._page.goto(KUAISHOU_HOME_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(2)
        await self._open_kuaishou_scan_login(on_status)
        refresh_task = asyncio.create_task(self._qr_refresh_loop(on_status))
      elif self.platform_id == 'xiaohongshu':
        on_status('正在加载小红书...')
        await self._page.goto(XIAOHONGSHU_HOME_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(2)
        await self._open_xiaohongshu_scan_login(on_status)
        refresh_task = asyncio.create_task(self._qr_refresh_loop(on_status))
      elif self.platform_id == 'weibo':
        on_status('正在打开微博登录...')
        await self._page.goto(WEIBO_SSO_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(2)
        await self._open_weibo_scan_login(on_status)
        refresh_task = asyncio.create_task(self._qr_refresh_loop(on_status))
      elif self.platform_id == 'bilibili':
        on_status('正在加载 B 站...')
        await self._page.goto(BILIBILI_HOME_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(2)
        await self._open_bilibili_scan_login(on_status)
        refresh_task = asyncio.create_task(self._qr_refresh_loop(on_status))
      elif self.platform_id == 'vivo':
        on_status('正在打开 vivo 社区登录...')
        await self._page.goto(VIVO_LOGIN_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(2)
        await self._open_vivo_scan_login(on_status)
        refresh_task = asyncio.create_task(self._qr_refresh_loop(on_status))
      else:
        await self._generic_login_flow(on_status)

      logged_in = await self._wait_for_login(self._page, LOGIN_TIMEOUT_SECONDS)

      if refresh_task:
        refresh_task.cancel()

      if self._cancelled:
        return LoginResult(False, '已取消登录')

      if not logged_in:
        return LoginResult(False, '登录超时，请重试')

      on_status('登录成功，正在获取昵称...')
      nickname = ''
      if self._page:
        if self.platform_id == 'douyin':
          nickname = await self._fetch_douyin_nickname(self._page)
        elif self.platform_id == 'kuaishou':
          nickname = await self._fetch_kuaishou_nickname(self._page)
        elif self.platform_id == 'xiaohongshu':
          nickname = await self._fetch_xiaohongshu_nickname(self._page)
        elif self.platform_id == 'weibo':
          nickname = await self._fetch_weibo_nickname(self._page)
        elif self.platform_id == 'bilibili':
          nickname = await self._fetch_bilibili_nickname(self._page)
        elif self.platform_id == 'vivo':
          nickname = await self._fetch_vivo_nickname(self._page)

      on_status('正在保存登录状态...')
      if self._context:
        await self._context.storage_state(path=str(state_path))

      msg = '登录成功'
      if nickname:
        msg = f'登录成功（{nickname}）'
      return LoginResult(True, msg, state_path, nickname=nickname)

    except Exception as exc:
      return LoginResult(False, f'登录失败: {exc}')

    finally:
      await self._cleanup()

  async def _open_douyin_scan_login(self, on_status: OnStatus) -> None:
    """打开首页 → 检测/打开登录弹窗 → 截图二维码（循环重试，避免卡死）."""
    on_status('正在准备登录...')
    await asyncio.sleep(2)

    tried_open_login = False
    tried_passport_url = False

    for i in range(35):
      if self._cancelled:
        return

      image_bytes = await self._capture_qr_from_page()
      if image_bytes:
        self._flow_state.qr_captured = True
        if self._on_qr_image:
          self._on_qr_image(image_bytes)
        on_status('请使用抖音 APP 扫描二维码')
        return

      if i < 4:
        on_status('正在检测登录窗口...')
      elif i == 4 and not tried_open_login:
        on_status('正在打开登录窗口...')
        tried_open_login = await self._click_login_button()
        await asyncio.sleep(1.2)
        await self._switch_to_scan_tab()
      elif i == 10 and not tried_passport_url:
        on_status('正在进入扫码登录页...')
        tried_passport_url = await self._goto_passport_login_page()
        await self._switch_to_scan_tab()
      else:
        on_status(f'正在获取二维码... ({i + 1}/35)')

      await asyncio.sleep(1)

    on_status('未能获取二维码，请关闭后重试')

  async def _open_kuaishou_scan_login(self, on_status: OnStatus) -> None:
    """快手 PC 站不会自动弹登录窗，需先点击侧栏「立即登录」."""
    on_status('正在准备登录...')
    await asyncio.sleep(1.5)

    on_status('正在打开登录窗口...')
    clicked = await self._click_kuaishou_login_button()
    if not clicked:
      on_status('未找到登录入口，请确认页面已加载完成')
    else:
      await asyncio.sleep(1.2)

    for i in range(40):
      if self._cancelled:
        return

      image_bytes = await self._capture_qr_from_page()
      if image_bytes:
        self._flow_state.qr_captured = True
        if self._on_qr_image:
          self._on_qr_image(image_bytes)
        on_status('请使用快手 APP 扫描二维码')
        return

      if i < 3 and not clicked:
        on_status('正在点击「立即登录」...')
        clicked = await self._click_kuaishou_login_button()
        await asyncio.sleep(1.2)
      else:
        on_status(f'正在获取二维码... ({i + 1}/40)')

      await asyncio.sleep(1)

    on_status('未能获取二维码，请关闭后重试')

  async def _open_xiaohongshu_scan_login(self, on_status: OnStatus) -> None:
    """小红书未登录时通常会自动弹出登录框，直接截取二维码."""
    on_status('正在准备登录...')
    await asyncio.sleep(2)

    tried_open_login = False

    for i in range(35):
      if self._cancelled:
        return

      image_bytes = await self._capture_qr_from_page()
      if image_bytes:
        self._flow_state.qr_captured = True
        await self._capture_baseline_login_cookies()
        if self._on_qr_image:
          self._on_qr_image(image_bytes)
        on_status('请使用小红书 APP 扫描二维码')
        return

      if i < 4:
        on_status('正在检测登录窗口...')
      elif i == 4 and not tried_open_login:
        on_status('正在打开登录窗口...')
        tried_open_login = await self._click_xiaohongshu_login_button()
        await asyncio.sleep(1.2)
      else:
        on_status(f'正在获取二维码... ({i + 1}/35)')

      await asyncio.sleep(1)

    on_status('未能获取二维码，请关闭后重试')

  async def _open_weibo_scan_login(self, on_status: OnStatus) -> None:
    """微博 SSO 页直接展示扫码二维码."""
    on_status('正在准备登录...')
    await asyncio.sleep(1)

    for i in range(35):
      if self._cancelled:
        return

      image_bytes = await self._capture_qr_from_page()
      if image_bytes:
        self._flow_state.qr_captured = True
        await self._capture_baseline_login_cookies()
        if self._on_qr_image:
          self._on_qr_image(image_bytes)
        on_status('请使用微博 App 扫码')
        return

      if i < 4:
        on_status('正在检测登录窗口...')
      else:
        on_status(f'正在获取二维码... ({i + 1}/35)')

      await asyncio.sleep(1)

    on_status('未能获取二维码，请关闭后重试')

  async def _open_bilibili_scan_login(self, on_status: OnStatus) -> None:
    """B 站 PC 站需点击右上角登录，再截取扫码框."""
    on_status('正在准备登录...')
    await asyncio.sleep(1.5)

    clicked = False
    for i in range(40):
      if self._cancelled:
        return

      image_bytes = await self._capture_qr_from_page()
      if image_bytes:
        self._flow_state.qr_captured = True
        await self._capture_baseline_login_cookies()
        if self._on_qr_image:
          self._on_qr_image(image_bytes)
        on_status('请使用哔哩哔哩 App 扫码')
        return

      if i < 5 and not clicked:
        on_status('正在打开登录窗口...')
        clicked = await self._click_bilibili_login_button()
        await asyncio.sleep(1.2)
      elif i < 8:
        on_status('正在检测登录窗口...')
      else:
        on_status(f'正在获取二维码... ({i + 1}/40)')

      await asyncio.sleep(1)

    on_status('未能获取二维码，请关闭后重试')

  async def _open_vivo_scan_login(self, on_status: OnStatus) -> None:
    """vivo 账号页默认短信登录，需切换到扫码后再截取二维码."""
    on_status('正在准备登录...')
    await asyncio.sleep(1.5)

    switched = False
    for i in range(40):
      if self._cancelled:
        return

      image_bytes = await self._capture_qr_from_page()
      if image_bytes:
        self._flow_state.qr_captured = True
        await self._capture_baseline_login_cookies()
        if self._on_qr_image:
          self._on_qr_image(image_bytes)
        on_status('请使用 vivo 账号 App 扫码')
        return

      if i < 6 and not switched:
        on_status('正在切换到扫码登录...')
        switched = await self._click_vivo_qr_switch()
        await asyncio.sleep(1.2)
      elif i < 10:
        on_status('正在检测登录窗口...')
      else:
        on_status(f'正在获取二维码... ({i + 1}/40)')

      await asyncio.sleep(1)

    on_status('未能获取二维码，请关闭后重试')

  async def _click_vivo_qr_switch(self) -> bool:
    if not self._page:
      return False
    for sel in VIVO_QR_MODE_SWITCH_SELECTORS:
      try:
        loc = self._page.locator(sel).first
        if await loc.is_visible(timeout=2000):
          await loc.click(timeout=3000, no_wait_after=True)
          return True
      except Exception:
        continue
    return False

  async def _click_bilibili_login_button(self) -> bool:
    if not self._page:
      return False
    for sel in BILIBILI_LOGIN_BUTTON_SELECTORS:
      try:
        loc = self._page.locator(sel).first
        if await loc.is_visible(timeout=2000):
          await loc.click(timeout=3000, no_wait_after=True)
          return True
      except Exception:
        continue
    return False

  async def _click_xiaohongshu_login_button(self) -> bool:
    if not self._page:
      return False
    for sel in XIAOHONGSHU_LOGIN_BUTTON_SELECTORS:
      try:
        loc = self._page.locator(sel).first
        if await loc.is_visible(timeout=2000):
          await loc.click(timeout=3000, no_wait_after=True)
          return True
      except Exception:
        continue
    return False

  async def _click_kuaishou_login_button(self) -> bool:
    if not self._page:
      return False
    for sel in KUAISHOU_LOGIN_BUTTON_SELECTORS:
      try:
        loc = self._page.locator(sel).first
        if await loc.is_visible(timeout=2000):
          await loc.click(timeout=3000, no_wait_after=True)
          return True
      except Exception:
        continue
    return False

  async def _goto_passport_login_page(self) -> bool:
    if not self._page:
      return False
    for url in PASSPORT_LOGIN_URLS:
      try:
        await self._page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)
        return True
      except Exception:
        continue
    return False

  async def _click_login_button(self) -> bool:
    if not self._page:
      return False
    for sel in [
      '#douyin-header-menuCt button:has-text("登录")',
      'header button:has-text("登录")',
      '[data-e2e="login-button"]',
      'header >> text=登录',
    ]:
      try:
        loc = self._page.locator(sel).first
        if await loc.is_visible(timeout=1500):
          await loc.click(timeout=3000, no_wait_after=True)
          return True
      except Exception:
        continue
    return False

  async def _switch_to_scan_tab(self) -> None:
    if not self._page:
      return
    scopes: List[Page | Frame] = [self._page]
    scopes.extend(
      fr for fr in self._page.frames if fr != self._page.main_frame
    )
    for scope in scopes:
      for text in ('扫码登录', '扫码'):
        try:
          tab = scope.locator(f'text={text}').first
          if await tab.is_visible(timeout=1200):
            await tab.click(timeout=3000, no_wait_after=True)
            await asyncio.sleep(0.8)
            return
        except Exception:
          continue

  async def _qr_refresh_loop(self, on_status: OnStatus) -> None:
    """定时从页面重新截图二维码（页面会自动刷新二维码）."""
    while not self._cancelled and not self._flow_state.logged_in:
      if self._flow_state.qr_captured and self._page:
        if self.platform_id == 'xiaohongshu':
          if await self._is_xiaohongshu_scan_pending_confirm():
            self._flow_state.qr_pending_confirm = True
            on_status('扫码成功，请在手机上确认登录')
            await asyncio.sleep(QR_REFRESH_INTERVAL_SECONDS)
            continue

        try:
          image_bytes = await self._capture_qr_from_page()
          if image_bytes and self._on_qr_image:
            self._on_qr_image(image_bytes)
        except Exception:
          pass
      await asyncio.sleep(QR_REFRESH_INTERVAL_SECONDS)

  async def _is_xiaohongshu_scan_pending_confirm(self) -> bool:
    """小红书扫码后需在手机端确认，此时登录框会显示「扫码成功」而非二维码."""
    if not self._page:
      return False
    try:
      modal = await self._get_login_modal_locator(self._page)
      scope = modal if modal else self._page.locator('body')
      text = await scope.inner_text()
      normalized = re.sub(r'\s+', '', text)
      if '扫码成功' in normalized and ('手机上' in normalized or '确认' in normalized):
        return True
    except Exception:
      pass
    return False

  async def _is_valid_qr_screenshot_target(self, loc: Locator) -> bool:
    if self.platform_id == 'vivo':
      try:
        in_switch = await loc.evaluate('(el) => !!el.closest(".login-switch")')
        if in_switch:
          return False
      except Exception:
        pass
    if self.platform_id != 'xiaohongshu':
      return True
    try:
      container = loc.locator(
        'xpath=ancestor::*[contains(@class,"qrcode") or contains(@class,"login-container")][1]',
      ).first
      text = await container.inner_text()
      normalized = re.sub(r'\s+', '', text)
      if '扫码成功' in normalized or '重新扫码' in normalized:
        return False
    except Exception:
      pass
    return True

  async def _capture_qr_from_page(self) -> Optional[bytes]:
    """从登录弹窗中定位二维码元素并截图."""
    if not self._page:
      return None

    if self.platform_id == 'xiaohongshu':
      if await self._is_xiaohongshu_scan_pending_confirm():
        return None

    targets: List[Tuple[Page | Frame, Locator]] = []

    # 优先在 passport / login 相关 iframe 中查找
    for frame in self._page.frames:
      if frame == self._page.main_frame:
        continue
      frame_url = (frame.url or '').lower()
      if not any(key in frame_url for key in ('passport', 'login', 'sso')):
        continue
      try:
        frame_loc = await self._find_qr_locator_in_frame(frame)
        if frame_loc:
          targets.append((frame, frame_loc))
      except Exception:
        continue

    main_loc = await self._find_qr_locator(self._page)
    if main_loc:
      targets.append((self._page, main_loc))

    for frame in self._page.frames:
      if frame == self._page.main_frame:
        continue
      if any(fr is frame for fr, _ in targets):
        continue
      try:
        frame_loc = await self._find_qr_locator_in_frame(frame)
        if frame_loc:
          targets.append((frame, frame_loc))
      except Exception:
        continue

    for _, loc in targets:
      try:
        if not await loc.is_visible(timeout=800):
          continue
        if not await self._is_valid_qr_screenshot_target(loc):
          continue
        box = await loc.bounding_box()
        if not box or box['width'] < QR_MIN_SIZE:
          continue
        return await loc.screenshot(type='png')
      except Exception:
        continue

    return None

  async def _find_qr_locator(self, page: Page) -> Optional[Locator]:
    modal = await self._get_login_modal_locator(page)
    if modal:
      loc = await self._find_qr_in_container(modal)
      if loc:
        return loc
    return await self._find_qr_in_container(page.locator('body'))

  async def _find_qr_locator_in_frame(self, frame: Frame) -> Optional[Locator]:
    try:
      body = frame.locator('body')
      return await self._find_qr_in_container(body)
    except Exception:
      return None

  def _get_login_modal_selectors(self) -> List[str]:
    if self.platform_id == 'kuaishou':
      return list(KUAISHOU_LOGIN_MODAL_SELECTORS) + list(LOGIN_MODAL_SELECTORS)
    if self.platform_id == 'xiaohongshu':
      return list(XIAOHONGSHU_LOGIN_MODAL_SELECTORS) + list(LOGIN_MODAL_SELECTORS)
    if self.platform_id == 'weibo':
      return list(LOGIN_MODAL_SELECTORS)
    if self.platform_id == 'bilibili':
      return list(BILIBILI_LOGIN_MODAL_SELECTORS) + list(LOGIN_MODAL_SELECTORS)
    if self.platform_id == 'vivo':
      return list(VIVO_LOGIN_MODAL_SELECTORS) + list(LOGIN_MODAL_SELECTORS)
    return list(LOGIN_MODAL_SELECTORS)

  def _get_qr_img_selectors(self) -> List[str]:
    if self.platform_id == 'kuaishou':
      return list(KUAISHOU_QR_IMG_SELECTORS) + list(QR_IMG_SELECTORS)
    if self.platform_id == 'xiaohongshu':
      return list(XIAOHONGSHU_QR_IMG_SELECTORS) + list(QR_IMG_SELECTORS)
    if self.platform_id == 'weibo':
      return list(WEIBO_QR_IMG_SELECTORS) + list(QR_IMG_SELECTORS)
    if self.platform_id == 'bilibili':
      return list(BILIBILI_QR_IMG_SELECTORS) + list(QR_IMG_SELECTORS)
    if self.platform_id == 'vivo':
      return list(VIVO_QR_IMG_SELECTORS) + list(QR_IMG_SELECTORS)
    return list(QR_IMG_SELECTORS)

  async def _get_login_modal_locator(self, page: Page) -> Optional[Locator]:
    for sel in self._get_login_modal_selectors():
      try:
        loc = page.locator(sel).first
        if await loc.is_visible(timeout=500):
          return loc
      except Exception:
        continue
    return None

  async def _find_qr_in_container(self, container: Locator) -> Optional[Locator]:
    for sel in self._get_qr_img_selectors():
      try:
        loc = container.locator(sel)
        count = min(await loc.count(), MAX_QR_CANDIDATES)
        for i in range(count):
          item = loc.nth(i)
          if await self._is_valid_qr_box(item):
            return item
      except Exception:
        continue

    for sel in QR_CANVAS_SELECTORS:
      try:
        loc = container.locator(sel)
        count = min(await loc.count(), MAX_QR_CANDIDATES)
        for i in range(count):
          item = loc.nth(i)
          if await self._is_valid_qr_box(item):
            return item
      except Exception:
        continue

    return None

  async def _is_valid_qr_box(self, loc: Locator) -> bool:
    try:
      if not await loc.is_visible(timeout=300):
        return False
      box = await loc.bounding_box()
      if not box:
        return False
      w, h = box['width'], box['height']
      if w < QR_MIN_SIZE or h < QR_MIN_SIZE:
        return False
      if w > QR_MAX_SIZE or h > QR_MAX_SIZE:
        return False
      ratio = w / h if h else 0
      return 0.75 <= ratio <= 1.33
    except Exception:
      return False

  async def _generic_login_flow(self, on_status: OnStatus) -> None:
    on_status('正在加载登录页面...')
    if self._page:
      await self._page.goto(self.login_url, wait_until='domcontentloaded', timeout=60000)
    on_status('请完成登录...')

  async def _start_browser(self) -> None:
    self._playwright = await async_playwright().start()
    self._browser = await self._playwright.chromium.launch(
      headless=LOGIN_HEADLESS,
      args=['--disable-blink-features=AutomationControlled'],
    )
    self._context = await self._browser.new_context(
      viewport={'width': 1280, 'height': 900},
      locale='zh-CN',
      user_agent=(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
      ),
    )
    self._page = await self._context.new_page()

  async def _cleanup(self) -> None:
    if self._context:
      await self._context.close()
      self._context = None
    if self._browser:
      await self._browser.close()
      self._browser = None
    if self._playwright:
      await self._playwright.stop()
      self._playwright = None
    self._page = None

  async def _wait_for_login(self, page: Page, timeout_seconds: int) -> bool:
    elapsed = 0.0
    poll_interval = 1.0

    while elapsed < timeout_seconds and not self._cancelled:
      if self._flow_state.logged_in:
        await self._after_login_page_ready(page)
        return True

      # 必须先拿到二维码，避免打开登录框就误判
      if not self._flow_state.qr_captured:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        continue

      if self.platform_id == 'xiaohongshu':
        if await self._is_xiaohongshu_scan_pending_confirm():
          self._flow_state.qr_pending_confirm = True

      if await self._has_real_login_cookies(page):
        self._flow_state.logged_in = True
        await self._after_login_page_ready(page)
        return True

      if self.platform_id == 'kuaishou':
        if not await self._is_kuaishou_login_prompt_visible(page):
          if await self._has_real_login_cookies(page):
            self._flow_state.logged_in = True
            await self._after_login_page_ready(page)
            return True
      elif self.platform_id == 'xiaohongshu':
        if await self._is_xiaohongshu_logged_in_ui(page):
          if await self._has_real_login_cookies(page):
            self._flow_state.logged_in = True
            await self._after_login_page_ready(page)
            return True
        if await self._is_login_modal_closed(page):
          if await self._has_real_login_cookies(page):
            self._flow_state.logged_in = True
            await self._after_login_page_ready(page)
            return True
      elif self.platform_id == 'vivo':
        if await self._is_vivo_logged_in_ui(page):
          self._flow_state.logged_in = True
          await self._after_login_page_ready(page)
          return True
        if await self._has_vivo_session_cookies(page):
          self._flow_state.logged_in = True
          await self._after_login_page_ready(page)
          return True
      elif await self._is_login_modal_closed(page):
        if await self._has_real_login_cookies(page):
          self._flow_state.logged_in = True
          await self._after_login_page_ready(page)
          return True

        for selector in LOGGED_IN_SELECTORS:
          try:
            if await page.locator(selector).first.is_visible(timeout=400):
              if await self._has_real_login_cookies(page):
                self._flow_state.logged_in = True
                await self._after_login_page_ready(page)
                return True
          except Exception:
            continue

      await asyncio.sleep(poll_interval)
      elapsed += poll_interval

    return False

  async def _is_xiaohongshu_logged_in_ui(self, page: Page) -> bool:
    for sel in XIAOHONGSHU_LOGGED_IN_SELECTORS:
      try:
        if await page.locator(sel).first.is_visible(timeout=400):
          return True
      except Exception:
        continue
    return False

  async def _is_kuaishou_login_prompt_visible(self, page: Page) -> bool:
    for sel in KUAISHOU_LOGGED_IN_SELECTORS:
      try:
        if await page.locator(sel).first.is_visible(timeout=400):
          return True
      except Exception:
        continue
    return False

  async def _is_login_modal_closed(self, page: Page) -> bool:
    """登录弹窗关闭通常表示扫码完成."""
    for sel in self._get_login_modal_selectors():
      try:
        if await page.locator(sel).first.is_visible(timeout=300):
          return False
      except Exception:
        continue
    return True

  async def _after_login_page_ready(self, page: Page) -> None:
    """登录成功后关闭弹层并刷新页面，确保页面含已登录用户信息."""
    if self.platform_id == 'weibo':
      try:
        await page.goto(WEIBO_HOME_URL, wait_until='domcontentloaded', timeout=60000)
      except Exception:
        pass
      await asyncio.sleep(2)
      return

    if self.platform_id == 'vivo':
      try:
        await page.goto(VIVO_BBS_HOME_URL, wait_until='domcontentloaded', timeout=60000)
      except Exception:
        pass
      await asyncio.sleep(2)
      return

    if self.platform_id != 'douyin':
      try:
        await page.reload(wait_until='domcontentloaded', timeout=60000)
      except Exception:
        pass
      await asyncio.sleep(2)
      return

    await dismiss_overlays(page)
    try:
      await page.reload(wait_until='domcontentloaded', timeout=60000)
    except Exception:
      pass
    await asyncio.sleep(2)
    await dismiss_overlays(page)

  async def _fetch_douyin_nickname(self, page: Page) -> str:
    """登录成功后从 RENDER_DATA / 个人面板 / 页面内嵌数据读取昵称."""
    await dismiss_overlays(page)

    # 优先：页面 RENDER_DATA（最稳定，不依赖 hover）
    nickname = await self._parse_nickname_from_render_data(page)
    if nickname:
      return nickname

    # 等待顶部头像出现（登录弹窗关闭后 DOM 会刷新）
    for avatar_sel in HEADER_AVATAR_SELECTORS:
      try:
        if await page.locator(avatar_sel).first.is_visible(timeout=8000):
          break
      except Exception:
        continue
    else:
      await asyncio.sleep(2)

    for avatar_sel in HEADER_AVATAR_SELECTORS:
      try:
        avatar = page.locator(avatar_sel).first
        if not await avatar.is_visible(timeout=3000):
          continue

        await avatar.scroll_into_view_if_needed()

        for action in ('hover', 'click'):
          try:
            if action == 'hover':
              await avatar.hover()
            else:
              await avatar.click()
            await asyncio.sleep(1.5)

            nickname = await self._read_nickname_from_popover(page)
            if nickname:
              return nickname
          except Exception:
            continue

      except Exception:
        continue

    # 页面内嵌的登录用户 JSON（不发起 HTTP 接口）
    nickname = await self._parse_nickname_from_page_embed(page)
    if nickname:
      return nickname

    # DOM 兜底：个人主页链接文字
    dom_selectors = [
      'a[href*="/user/self"][href*="personal_panel"]:not([href*="showTab"])',
      'a[href*="/user/self"][href*="personal_panel"]',
      'header a[href*="/user/self"]',
      '[class*="userMenuPanel"] a[href*="/user/self"]',
    ]
    for selector in dom_selectors:
      try:
        loc = page.locator(selector).first
        if await loc.is_visible(timeout=1500):
          text = await loc.inner_text()
          nickname = self._clean_nickname(text)
          if nickname:
            return nickname
      except Exception:
        continue

    return ''

  async def _parse_nickname_from_render_data(self, page: Page) -> str:
    """从 #RENDER_DATA 脚本解析当前登录用户昵称."""
    try:
      raw = await page.evaluate(
        """() => {
          const el = document.querySelector('#RENDER_DATA');
          return el ? el.textContent : '';
        }"""
      )
    except Exception:
      return ''

    if not raw:
      return ''

    try:
      decoded = urllib.parse.unquote(str(raw).strip())
      data = json.loads(decoded)
    except Exception:
      return ''

    user_block = self._find_logged_in_user_block(data)
    if not user_block:
      return ''

    info = user_block.get('info') or {}
    for key in ('nickname', 'realName', 'uniqueId'):
      nickname = self._clean_nickname(str(info.get(key, '')))
      if nickname:
        return nickname
    return ''

  def _find_logged_in_user_block(self, obj: object) -> Optional[dict]:
    if isinstance(obj, dict):
      if obj.get('isLogin') is True and isinstance(obj.get('info'), dict):
        return obj
      for value in obj.values():
        found = self._find_logged_in_user_block(value)
        if found:
          return found
    elif isinstance(obj, list):
      for item in obj[:30]:
        found = self._find_logged_in_user_block(item)
        if found:
          return found
    return None

  async def _parse_nickname_from_page_embed(self, page: Page) -> str:
    """从页面 HTML/脚本内嵌的 user 对象解析昵称（非 HTTP 请求）."""
    try:
      content = await page.content()
    except Exception:
      return ''

    patterns = [
      r'"isLogin":true[^}]{0,400}?"nickname":"([^"]+)"',
      r'"shortId":"\d+","realName":"([^"]+)","remarkName"[^}]*?"nickname":"([^"]+)"',
      r'\\"isLogin\\":true[^}]{0,400}?\\"nickname\\":\\"([^"\\]+)\\"',
      r'\\"realName\\":\\"([^"\\]+)\\"[^}]{0,120}?\\"nickname\\":\\"([^"\\]+)\\"',
    ]
    for pattern in patterns:
      for match in re.finditer(pattern, content):
        for group in match.groups():
          nickname = self._clean_nickname(group)
          if nickname and nickname not in ('$undefined', 'undefined'):
            return nickname
    return ''

  async def _read_nickname_from_popover(self, page: Page) -> str:
    # 优先直接读个人面板里的主页链接（含 Linnn. 这类昵称）
    direct_selectors = [
      'a[href*="/user/self"][href*="personal_panel"]:not([href*="showTab"])',
      'a[href*="/user/self"][href*="personal_panel"]',
      '[class*="userMenuPanel"] a[href*="/user/self"]',
    ]
    for sel in direct_selectors:
      try:
        loc = page.locator(sel).first
        if await loc.is_visible(timeout=2000):
          text = await loc.inner_text()
          nickname = self._clean_nickname(text)
          if nickname:
            return nickname
      except Exception:
        continue

    for pop_sel in USER_POPOVER_SELECTORS:
      try:
        popover = page.locator(pop_sel)
        count = await popover.count()
        for i in range(min(count, 5)):
          block = popover.nth(i)
          if not await block.is_visible(timeout=800):
            continue
          for name_sel in USER_NAME_IN_POPOVER:
            try:
              name_el = block.locator(name_sel).first
              if await name_el.is_visible(timeout=600):
                text = await name_el.inner_text()
                nickname = self._clean_nickname(text)
                if nickname:
                  return nickname
            except Exception:
              continue
      except Exception:
        continue
    return ''

  @staticmethod
  def _clean_nickname(text: str) -> str:
    if not text:
      return ''
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    skip_words = frozenset({
      '登录', '注册', '抖音', '退出登录', '个人主页', '创作者中心',
      '我的收藏', '观看历史', '设置', '消息', '发布',
    })
    for line in lines:
      if line in skip_words:
        continue
      if re.match(r'^[\d.]+[万wW]?$', line):
        continue
      if len(line) >= 2:
        return line
    return ''

  async def _fetch_kuaishou_nickname(self, page: Page) -> str:
    await dismiss_overlays(page)
    for sel in KUAISHOU_NICKNAME_SELECTORS:
      try:
        loc = page.locator(sel).first
        if await loc.is_visible(timeout=5000):
          text = await loc.inner_text()
          nickname = self._clean_kuaishou_nickname(text)
          if nickname:
            return nickname
      except Exception:
        continue
    return ''

  @staticmethod
  def _clean_kuaishou_nickname(text: str) -> str:
    if not text:
      return ''
    text = text.strip().lstrip('@').strip()
    skip_words = frozenset({
      '登录', '立即登录', '我的', '更多', '推荐', '发现', '关注', '直播', '赛事',
    })
    if not text or text in skip_words:
      return ''
    return text[:64]

  async def _fetch_weibo_nickname(self, page: Page) -> str:
    return await fetch_weibo_nickname(page)

  async def _fetch_bilibili_nickname(self, page: Page) -> str:
    cookies = await page.context.cookies()
    return await fetch_bilibili_nickname(cookies)

  async def _fetch_vivo_nickname(self, page: Page) -> str:
    return await fetch_vivo_nickname(page)

  async def _fetch_xiaohongshu_nickname(self, page: Page) -> str:
    await self._navigate_xiaohongshu_profile(page)

    nickname = await self._parse_xiaohongshu_nickname_from_initial_state(page)
    if nickname:
      return nickname

    nickname = await self._parse_xiaohongshu_nickname_from_title(page)
    if nickname:
      return nickname

    for sel in XIAOHONGSHU_NICKNAME_SELECTORS:
      try:
        loc = page.locator(sel).first
        if await loc.is_visible(timeout=3000):
          text = await loc.inner_text()
          nickname = self._clean_xiaohongshu_nickname(text)
          if nickname:
            return nickname
      except Exception:
        continue
    return ''

  async def _navigate_xiaohongshu_profile(self, page: Page) -> bool:
    """登录后进入个人主页，profile 页才有 user.userPageData.basicInfo."""
    try:
      if '/user/profile/' in page.url:
        return True
    except Exception:
      pass

    for sel in XIAOHONGSHU_PROFILE_LINK_SELECTORS:
      try:
        loc = page.locator(sel).first
        if not await loc.is_visible(timeout=2500):
          continue
        await loc.scroll_into_view_if_needed()
        await loc.click(timeout=5000)
        try:
          await page.wait_for_url('**/user/profile/**', timeout=15000)
        except Exception:
          await asyncio.sleep(2)
        try:
          await page.wait_for_load_state('domcontentloaded', timeout=15000)
        except Exception:
          pass
        await asyncio.sleep(0.8)
        return '/user/profile/' in page.url
      except Exception:
        continue

    try:
      href = await page.evaluate(
        """() => {
          const link = document.querySelector('a[href*="/user/profile/"]');
          return link ? link.href : '';
        }"""
      )
      if href and '/user/profile/' in str(href):
        await page.goto(str(href), wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(0.8)
        return True
    except Exception:
      pass
    return '/user/profile/' in page.url

  async def _parse_xiaohongshu_nickname_from_title(self, page: Page) -> str:
    """个人主页 title 通常为「昵称 - 小红书」."""
    try:
      title = await page.title()
    except Exception:
      return ''
    match = re.match(r'^(.+?)\s*[-–—]\s*小红书', (title or '').strip())
    if not match:
      return ''
    return self._clean_xiaohongshu_nickname(match.group(1))

  async def _parse_xiaohongshu_nickname_from_initial_state(self, page: Page) -> str:
    try:
      raw = await page.evaluate(
        """() => {
          const scripts = document.querySelectorAll('script');
          for (const el of scripts) {
            const text = el.textContent || '';
            if (text.includes('window.__INITIAL_STATE__=')) {
              return text;
            }
          }
          return '';
        }"""
      )
    except Exception:
      return ''

    data = xhs_initial_state.parse_initial_state_script(raw or '')
    if not data:
      return ''

    user_page = xhs_initial_state.get_user_page_data(data)
    if not user_page:
      user_page = xhs_initial_state.find_user_page_data(data)
    nickname = xhs_initial_state.nickname_from_user_page(user_page)
    return self._clean_xiaohongshu_nickname(nickname)

  @staticmethod
  def _clean_xiaohongshu_nickname(text: str) -> str:
    if not text:
      return ''
    text = text.strip().lstrip('@').strip()
    skip_words = frozenset({
      '登录', '注册', '小红书', '我', '发现', '发布', '通知', '消息',
    })
    if not text or text in skip_words:
      return ''
    return text[:64]

  def _login_cookie_names(self) -> frozenset[str]:
    if self.platform_id == 'kuaishou':
      return KUAISHOU_LOGIN_COOKIE_NAMES
    if self.platform_id == 'xiaohongshu':
      return XIAOHONGSHU_LOGIN_COOKIE_NAMES
    if self.platform_id == 'weibo':
      return WEIBO_LOGIN_COOKIE_NAMES
    if self.platform_id == 'bilibili':
      return BILIBILI_LOGIN_COOKIE_NAMES
    if self.platform_id == 'vivo':
      return VIVO_LOGIN_COOKIE_NAMES
    return LOGIN_COOKIE_NAMES

  async def _capture_baseline_login_cookies(self) -> None:
    if not self._page:
      return
    cookies = await self._page.context.cookies()
    names = self._login_cookie_names()
    baseline: dict[str, str] = {}
    for cookie in cookies:
      name = cookie.get('name', '')
      if name in names:
        baseline[name] = str(cookie.get('value', '')).strip()
    self._flow_state.baseline_cookie_values = baseline

  async def _has_real_login_cookies(self, page: Page) -> bool:
    if not self._flow_state.qr_captured:
      return False
    cookies = await page.context.cookies()
    names = self._login_cookie_names()
    baseline = self._flow_state.baseline_cookie_values or {}

    for cookie in cookies:
      name = cookie.get('name', '')
      if name not in names:
        continue
      value = str(cookie.get('value', '')).strip()
      if not value:
        continue
      if self.platform_id == 'xiaohongshu':
        old_value = baseline.get(name, '')
        if value != old_value:
          return True
        continue
      if self.platform_id == 'weibo':
        if name == 'SSOLoginState' and value:
          return True
        if name == 'WBPSESS':
          old_value = baseline.get('WBPSESS', '')
          if value and value != old_value:
            return True
        continue
      if self.platform_id == 'bilibili':
        if name == 'SESSDATA' and value:
          old_value = baseline.get('SESSDATA', '')
          if not old_value or value != old_value:
            return True
        continue
      if self.platform_id == 'vivo':
        old_value = baseline.get(name, '')
        if value and value != old_value:
          return True
        continue
      return True
    return False

  async def _is_vivo_logged_in_ui(self, page: Page) -> bool:
    url = (page.url or '').lower()
    if 'bbs.vivo.com.cn' not in url:
      return False
    for sel in VIVO_LOGGED_IN_SELECTORS:
      try:
        loc = page.locator(sel).first
        if await loc.is_visible(timeout=800):
          text = (await loc.inner_text()).strip()
          if text and text not in ('登录', '注册', '立即登录'):
            return True
      except Exception:
        continue
    return False

  async def _has_vivo_session_cookies(self, page: Page) -> bool:
    if not self._flow_state.qr_captured:
      return False
    cookies = await page.context.cookies()
    for cookie in cookies:
      domain = str(cookie.get('domain', ''))
      if 'vivo.com.cn' not in domain:
        continue
      name = str(cookie.get('name', '')).lower()
      value = str(cookie.get('value', '')).strip()
      if not value or len(value) < 8:
        continue
      if any(key in name for key in ('token', 'session', 'sess', 'auth', 'vvc', 'bbs')):
        return True
    return False


def run_login_in_thread(
  coro: Awaitable[LoginResult],
  on_complete: Callable[[LoginResult], None],
  on_error: Callable[[Exception], None],
) -> None:
  run_coro_in_thread(coro, on_complete, on_error)
