"""主窗口."""

from __future__ import annotations

from tkinter import messagebox
from typing import Dict, List, Optional

import customtkinter as ctk

from config import APP_DATA_DIR, PLATFORMS, WINDOW_SIZE, WINDOW_TITLE, ensure_dirs
from infra.database import Database
from ui.account_panel import AccountShell
from ui.collect_panel import CollectPanel
from ui.theme import (
  COLOR_BG,
  COLOR_PANEL,
  COLOR_SELECTED,
  COLOR_SELECTED_TEXT,
  COLOR_TEXT,
  COLOR_TEXT_DIM,
  SIDEBAR_MENU_SLOT_COUNT,
  font_caption,
  font_title,
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
    body = ctk.CTkFrame(self, fg_color='transparent')
    body.pack(fill='both', expand=True, padx=12, pady=12)

    sidebar = ctk.CTkFrame(body, fg_color=COLOR_PANEL, corner_radius=8, width=180)
    sidebar.pack(side='left', fill='y', padx=(0, 10))
    sidebar.pack_propagate(False)
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
        padx=8,
        pady=2,
      )
      menu_item.grid_rowconfigure(0, weight=1)
      menu_item.grid_columnconfigure(0, weight=1)

      btn = ctk.CTkButton(
        menu_item,
        text=item['label'],
        anchor='center',
        font=get_font(14),
        fg_color='transparent' if item['enabled'] else COLOR_PANEL,
        hover_color=COLOR_SELECTED if item['enabled'] else COLOR_PANEL,
        text_color=COLOR_TEXT_DIM if not item['enabled'] else COLOR_TEXT,
        state='normal' if item['enabled'] else 'disabled',
        command=lambda mid=item['id'], en=item['enabled']: self._on_menu_click(mid, en),
      )
      btn.grid(row=0, column=0, sticky='nsew')
      self.menu_buttons[item['id']] = btn

    self.content = ctk.CTkFrame(body, fg_color='transparent')
    self.content.pack(side='left', fill='both', expand=True)

    title_frame = ctk.CTkFrame(self.content, fg_color='transparent')
    title_frame.pack(fill='x', pady=(0, 8))
    self.content_title = ctk.CTkLabel(
      title_frame,
      text='账号管理',
      font=font_title(),
      text_color=COLOR_TEXT,
    )
    self.content_title.pack(side='left')

    self.main_panel = ctk.CTkFrame(self.content, fg_color='transparent')
    self.main_panel.pack(fill='both', expand=True)

    self.placeholder = ctk.CTkLabel(
      self.main_panel,
      text='',
      font=get_font(15),
      text_color=COLOR_TEXT_DIM,
    )

    self.account_shell: Optional[AccountShell] = None
    self.collect_panel: Optional[CollectPanel] = None

    status_bar = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=0, height=32)
    status_bar.pack(fill='x', side='bottom')
    status_bar.pack_propagate(False)

    self.status_text = ctk.StringVar(value='状态：就绪')
    ctk.CTkLabel(
      status_bar,
      textvariable=self.status_text,
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
      anchor='w',
    ).pack(side='left', padx=16, pady=6)

    ctk.CTkLabel(
      status_bar,
      text=f'数据目录：{APP_DATA_DIR}',
      font=get_font(11),
      text_color=COLOR_TEXT_DIM,
      anchor='e',
    ).pack(side='right', padx=16, pady=6)

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
    accounts_part = self._format_accounts_status()
    self.status_text.set(f'状态：{msg} | {accounts_part}')

  def _on_menu_click(self, menu_id: str, enabled: bool) -> None:
    if not enabled:
      messagebox.showinfo('提示', '该功能开发中，敬请期待！')
      return
    if menu_id == 'account':
      self._show_account_panel()
    elif menu_id == 'collect':
      self._show_collect_panel()

  def _clear_main_panel(self) -> None:
    self.placeholder.pack_forget()
    if self.account_shell:
      self.account_shell.destroy()
      self.account_shell = None
    if self.collect_panel:
      self.collect_panel.destroy()
      self.collect_panel = None

  def _highlight_menu(self, menu_id: str) -> None:
    for mid, btn in self.menu_buttons.items():
      if mid == menu_id:
        btn.configure(fg_color=COLOR_SELECTED, text_color=COLOR_SELECTED_TEXT)
      else:
        btn.configure(fg_color='transparent', text_color=COLOR_TEXT_DIM)

  def _show_account_panel(self) -> None:
    if self.current_menu == 'account' and self.account_shell is not None:
      self._highlight_menu('account')
      return

    self.current_menu = 'account'
    self.content_title.configure(text='账号管理')
    self._clear_main_panel()
    self.account_shell = AccountShell(
      self.main_panel,
      self.db,
      on_status=self._update_status_bar,
    )
    self.account_shell.pack(fill='both', expand=True)
    self._highlight_menu('account')
    self._update_status_bar('就绪')

  def _show_collect_panel(self) -> None:
    if self.current_menu == 'collect' and self.collect_panel is not None:
      self._highlight_menu('collect')
      return

    self.current_menu = 'collect'
    self.content_title.configure(text='数据采集')
    self._clear_main_panel()
    self.collect_panel = CollectPanel(
      self.main_panel,
      self.db,
      on_status=self._update_status_bar,
    )
    self.collect_panel.pack(fill='both', expand=True)
    self._highlight_menu('collect')
    self._update_status_bar('就绪')


def run_app() -> None:
  app = MainApp()
  app.mainloop()
