"""主窗口."""

from __future__ import annotations

from tkinter import messagebox
from typing import Dict, List, Optional

import customtkinter as ctk

from config import PLATFORMS, WINDOW_SIZE, WINDOW_TITLE, ensure_dirs
from infra.database import Database
from ui.account_panel import AccountShell
from ui.collect_panel import CollectPanel
from ui.layout import add_horizontal_divider, add_vertical_divider
from ui.theme import (
  COLOR_BG,
  COLOR_SELECTED,
  COLOR_SELECTED_TEXT,
  COLOR_TEXT,
  COLOR_TEXT_DIM,
  SIDEBAR_MENU_SLOT_COUNT,
  SPACE_MD,
  font_caption,
  get_font,
)

MENU_ITEMS = [
  {
    'id': 'collect',
    'label': '数据采集',
    'enabled': True,
  },
  {
    'id': 'account',
    'label': '账号管理',
    'enabled': True,
  },
  {
    'id': 'settings',
    'label': '系统设置',
    'enabled': False,
  },
]


class MainApp(ctk.CTk):
  """主窗口."""

  def __init__(self) -> None:
    super().__init__()
    ensure_dirs()
    self.db = Database()

    self.current_menu = 'account'

    self.title(WINDOW_TITLE)
    self.geometry(WINDOW_SIZE)
    self.minsize(1000, 600)
    self.configure(fg_color=COLOR_BG)

    ctk.set_appearance_mode('light')
    ctk.set_default_color_theme('blue')

    self._build_layout()
    self._show_account_panel()

  def _build_layout(self) -> None:
    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(0, weight=1)

    body = ctk.CTkFrame(self, fg_color=COLOR_BG)
    body.grid(row=0, column=0, sticky='nsew')
    body.grid_columnconfigure(2, weight=1)
    body.grid_rowconfigure(0, weight=1)
    body.grid_columnconfigure(1, minsize=1)

    sidebar = ctk.CTkFrame(body, fg_color=COLOR_BG, width=180, corner_radius=0)
    sidebar.grid(row=0, column=0, sticky='ns')
    sidebar.grid_propagate(False)
    sidebar.grid_columnconfigure(0, weight=1)
    for row_index in range(SIDEBAR_MENU_SLOT_COUNT):
      sidebar.grid_rowconfigure(row_index, weight=1, uniform='sidebar_menu')

    self.menu_buttons: Dict[str, ctk.CTkButton] = {}
    for slot_index, item in enumerate(MENU_ITEMS):
      if slot_index >= SIDEBAR_MENU_SLOT_COUNT:
        break
      menu_item = ctk.CTkFrame(sidebar, fg_color='transparent')
      menu_item.grid(
        row=slot_index,
        column=0,
        sticky='nsew',
        padx=SPACE_MD,
        pady=2,
      )
      menu_item.grid_rowconfigure(0, weight=1)
      menu_item.grid_columnconfigure(0, weight=1)

      btn = ctk.CTkButton(
        menu_item,
        text=item['label'],
        anchor='center',
        font=get_font(14),
        fg_color=COLOR_BG,
        hover_color=COLOR_SELECTED if item['enabled'] else COLOR_BG,
        text_color=COLOR_TEXT_DIM if not item['enabled'] else COLOR_TEXT,
        border_width=0,
        corner_radius=6,
        state='normal' if item['enabled'] else 'disabled',
        command=lambda mid=item['id'], en=item['enabled']: self._on_menu_click(mid, en),
      )
      btn.grid(row=0, column=0, sticky='nsew')
      self.menu_buttons[item['id']] = btn

    add_vertical_divider(body, column=1, rowspan=1)

    self.content = ctk.CTkFrame(body, fg_color=COLOR_BG, corner_radius=0)
    self.content.grid(row=0, column=2, sticky='nsew', padx=(SPACE_MD, SPACE_MD), pady=SPACE_MD)
    self.content.grid_columnconfigure(0, weight=1)
    self.content.grid_rowconfigure(0, weight=1)

    self.main_panel = ctk.CTkFrame(self.content, fg_color='transparent')
    self.main_panel.grid(row=0, column=0, sticky='nsew')

    self.placeholder = ctk.CTkLabel(
      self.main_panel,
      text='',
      font=get_font(15),
      text_color=COLOR_TEXT_DIM,
    )

    self.account_shell: Optional[AccountShell] = None
    self.collect_panel: Optional[CollectPanel] = None

    self.grid_rowconfigure(1, minsize=1)
    add_horizontal_divider(self, row=1, pady=0)

    status_bar = ctk.CTkFrame(self, fg_color=COLOR_BG, corner_radius=0, height=36)
    status_bar.grid(row=2, column=0, sticky='ew')
    status_bar.grid_propagate(False)

    self.status_text = ctk.StringVar(value='')
    ctk.CTkLabel(
      status_bar,
      textvariable=self.status_text,
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
      anchor='w',
    ).pack(side='left', padx=16, pady=8)

    self.progress_text = ctk.StringVar(value='就绪')
    ctk.CTkLabel(
      status_bar,
      textvariable=self.progress_text,
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
      anchor='e',
    ).pack(side='right', padx=16, pady=8)

    self._right_status_msg = '就绪'
    self._right_progress_part = ''

  def _refresh_right_bar(self) -> None:
    if self._right_status_msg == '就绪' and not self._right_progress_part:
      self.progress_text.set('就绪')
      return
    if self._right_progress_part:
      if self._right_status_msg and self._right_status_msg != '就绪':
        self.progress_text.set(f'{self._right_status_msg} · {self._right_progress_part}')
      else:
        self.progress_text.set(self._right_progress_part)
      return
    self.progress_text.set(self._right_status_msg or '就绪')

  def set_progress_display(self, text: str) -> None:
    self._right_progress_part = text
    self._refresh_right_bar()

  def clear_progress_display(self) -> None:
    self._right_status_msg = '就绪'
    self._right_progress_part = ''
    self._refresh_right_bar()

  def _format_accounts_status(self) -> str:
    counts = self.db.count_active_accounts_by_platform()
    parts: List[str] = []
    total = 0
    for platform in PLATFORMS:
      if not platform['enabled']:
        continue
      count = counts.get(platform['id'], 0)
      total += count
      parts.append(f"{platform['name']} {count}")
    if not parts:
      return '已登录：0'
    return f"已登录：{' · '.join(parts)} · 共 {total}"

  def _update_status_bar(self, msg: str) -> None:
    self.status_text.set(self._format_accounts_status())
    self._right_status_msg = msg
    self._refresh_right_bar()

  def _on_menu_click(self, menu_id: str, enabled: bool) -> None:
    if not enabled:
      messagebox.showinfo('提示', '该功能开发中，敬请期待！')
      return
    if menu_id == 'account':
      self._show_account_panel()
    elif menu_id == 'collect':
      self._show_collect_panel()

  def _hide_all_main_panels(self) -> None:
    """隐藏主内容区面板，不销毁，便于切换菜单后保留采集结果."""
    self.placeholder.pack_forget()
    if self.account_shell is not None:
      self.account_shell.grid_remove()
    if self.collect_panel is not None:
      self.collect_panel.grid_remove()

  def _highlight_menu(self, menu_id: str) -> None:
    for mid, btn in self.menu_buttons.items():
      if mid == menu_id:
        btn.configure(fg_color=COLOR_SELECTED, text_color=COLOR_SELECTED_TEXT)
      else:
        btn.configure(fg_color=COLOR_BG, text_color=COLOR_TEXT_DIM)

  def _show_account_panel(self) -> None:
    self.current_menu = 'account'
    self._hide_all_main_panels()

    if self.account_shell is None:
      self.account_shell = AccountShell(
        self.main_panel,
        self.db,
        on_status=self._update_status_bar,
      )
    else:
      self.account_shell.refresh_on_show()

    self.account_shell.grid(row=0, column=0, sticky='nsew')
    self.main_panel.grid_rowconfigure(0, weight=1)
    self.main_panel.grid_columnconfigure(0, weight=1)
    self._highlight_menu('account')
    self.clear_progress_display()
    self._update_status_bar('就绪')

  def _show_collect_panel(self) -> None:
    self.current_menu = 'collect'
    self._hide_all_main_panels()

    if self.collect_panel is None:
      self.collect_panel = CollectPanel(
        self.main_panel,
        self.db,
        on_status=self._update_status_bar,
        on_progress_display=self.set_progress_display,
      )

    self.collect_panel.grid(row=0, column=0, sticky='nsew')
    self.main_panel.grid_rowconfigure(0, weight=1)
    self.main_panel.grid_columnconfigure(0, weight=1)
    self._highlight_menu('collect')
    self._update_status_bar('就绪')
    self.collect_panel.restore_progress_display()


def run_app() -> None:
  app = MainApp()
  app.mainloop()
