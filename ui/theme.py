"""界面主题色与设计令牌（Cursor 浅色风格）."""

from __future__ import annotations

# -------- 基础色 --------
COLOR_BG = '#ffffff'
COLOR_PANEL = '#f3f3f3'
COLOR_SURFACE = '#ffffff'
COLOR_BORDER = '#e5e5e5'
COLOR_BORDER_LIGHT = '#d4d4d4'
COLOR_TEXT = '#1e1e1e'
COLOR_TEXT_DIM = '#6e6e6e'
COLOR_DISABLED = '#b0b0b0'
COLOR_SELECTED = '#e8e8e8'
COLOR_SELECTED_TEXT = '#1e1e1e'
COLOR_ACCENT = '#0066ff'
COLOR_ACCENT_HOVER = '#0052cc'
COLOR_ACCENT_TEXT = '#ffffff'
COLOR_SUCCESS = '#1a7f37'
COLOR_SUCCESS_HOVER = '#2da44e'
COLOR_SUCCESS_BG = '#dafbe1'
COLOR_WARN = '#9a6700'
COLOR_WARN_BG = '#fff8c5'
COLOR_ERROR = '#cf222e'
COLOR_ERROR_HOVER = '#a40e26'
COLOR_ERROR_BG = '#ffebe9'
COLOR_NEUTRAL_BG = '#f6f8fa'

# -------- 表格 --------
COLOR_TABLE_HEADER = '#f6f8fa'
COLOR_TABLE_ROW_ALT = '#fafbfc'
COLOR_TABLE_BORDER = '#d8dee4'
COLOR_TABLE_SELECT = '#ddf4ff'

# -------- 间距 / 圆角 --------
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
RADIUS_CARD = 10
RADIUS_BTN = 8
BTN_HEIGHT = 34
ROW_HEIGHT = 36
TABLE_HEADER_HEIGHT = 36
TABLE_ROW_HEIGHT = 44
TABLE_ROW_RADIUS = 4
TAB_BAR_HEIGHT = 40
TAB_SEGMENT_RADIUS = 8
# 侧栏菜单槽位数（当前 3 项各占 1/9 高度，预留后续扩展至 9 项）
SIDEBAR_MENU_SLOT_COUNT = 9

# -------- 字号（通过 get_font 构造，避免 import 时无 root）--------
FONT_FAMILY = 'Microsoft YaHei UI'
FONT_SIZE_TITLE = 20
FONT_SIZE_SECTION = 14
FONT_SIZE_BODY = 13
FONT_SIZE_CAPTION = 12

_FONT_CACHE: dict[tuple, object] = {}


def get_font(size: int, *, weight: str = 'normal') -> object:
  """返回带统一字体族的 CTkFont（懒加载缓存）."""
  import customtkinter as ctk

  key = (FONT_FAMILY, size, weight)
  cached = _FONT_CACHE.get(key)
  if cached is not None:
    return cached
  font = ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
  _FONT_CACHE[key] = font
  return font


def font_title() -> object:
  return get_font(FONT_SIZE_TITLE, weight='bold')


def font_section() -> object:
  return get_font(FONT_SIZE_SECTION, weight='bold')


def font_body(*, weight: str = 'normal') -> object:
  return get_font(FONT_SIZE_BODY, weight=weight)


def font_caption(*, weight: str = 'normal') -> object:
  return get_font(FONT_SIZE_CAPTION, weight=weight)
