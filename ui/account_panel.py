"""账号管理面板（含平台分栏）."""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox
from typing import Callable, Dict, List, Optional, Set

import customtkinter as ctk

from config import PLATFORMS, format_account_display_id
from core.platforms import get_platform_name
from infra.database import (
  ACCOUNT_STATUS_ACTIVE,
  OP_DELETE,
  OP_RELOGIN,
  OP_STATUS_SUCCESS,
  Account,
  Database,
)
from ui.layout import add_horizontal_divider
from ui.theme import (
  COLOR_ACCENT,
  COLOR_BG,
  COLOR_ACCENT_HOVER,
  COLOR_ACCENT_TEXT,
  COLOR_BORDER,
  COLOR_BORDER_LIGHT,
  COLOR_DISABLED,
  COLOR_ERROR,
  COLOR_ERROR_HOVER,
  COLOR_PANEL,
  COLOR_TABLE_HEADER,
  COLOR_SURFACE,
  COLOR_TEXT,
  COLOR_TEXT_DIM,
  COLOR_SUCCESS,
  COLOR_TABLE_SELECT,
  COLOR_WARN,
  TAB_BAR_HEIGHT,
  SPACE_SM,
  font_body,
  font_caption,
  font_section,
  get_font,
)

STATUS_LABELS = {
  'active': ('✅ 已登录', COLOR_SUCCESS),
  'expired': ('⚠️ 已过期', COLOR_WARN),
  'inactive': ('⏸ 已停用', COLOR_TEXT_DIM),
}


class AccountManagementPanel(ctk.CTkFrame):
  """单平台账号列表."""

  def __init__(
    self,
    master: ctk.CTk,
    db: Database,
    platform_id: str,
    on_status: Callable[[str], None],
  ) -> None:
    super().__init__(master, fg_color='transparent')
    self.db = db
    self.platform_id = platform_id
    self.on_status = on_status
    self.selected_ids: Set[int] = set()
    self.row_check_vars: Dict[int, ctk.BooleanVar] = {}

    self._build_ui()
    self.refresh_list()

  def _build_ui(self) -> None:
    toolbar = ctk.CTkFrame(self, fg_color='transparent')
    toolbar.pack(fill='x', pady=(0, SPACE_SM))

    ctk.CTkButton(
      toolbar,
      text='➕ 添加账号',
      width=110,
      height=34,
      fg_color=COLOR_ACCENT,
      hover_color=COLOR_ACCENT_HOVER,
      text_color=COLOR_ACCENT_TEXT,
      command=self._on_add_account,
    ).pack(side='left', padx=12, pady=9)

    ctk.CTkButton(
      toolbar,
      text='🗑️ 删除账号',
      width=110,
      height=34,
      fg_color=COLOR_ERROR,
      hover_color=COLOR_ERROR_HOVER,
      text_color=COLOR_ACCENT_TEXT,
      command=self._on_delete_accounts,
    ).pack(side='left', padx=4, pady=9)

    ctk.CTkButton(
      toolbar,
      text='🔄 刷新列表',
      width=110,
      height=34,
      fg_color=COLOR_BORDER,
      hover_color=COLOR_BORDER_LIGHT,
      text_color=COLOR_TEXT,
      command=self.refresh_list,
    ).pack(side='left', padx=4, pady=9)

    ctk.CTkButton(
      toolbar,
      text='📋 操作日志',
      width=110,
      height=34,
      fg_color=COLOR_BORDER,
      hover_color=COLOR_BORDER_LIGHT,
      text_color=COLOR_TEXT,
      command=self._on_view_logs,
    ).pack(side='left', padx=4, pady=6)

    add_horizontal_divider(self)

    table_block = ctk.CTkFrame(self, fg_color='transparent')
    table_block.pack(fill='both', expand=True)

    header = ctk.CTkFrame(table_block, fg_color=COLOR_TABLE_HEADER, height=36, corner_radius=0)
    header.pack(fill='x')
    header.pack_propagate(False)
    cols = [
      ('', 36),
      ('账号ID', 120),
      ('平台', 70),
      ('账号名称', 160),
      ('状态', 110),
      ('创建时间', 150),
      ('操作', 100),
    ]
    for text, width in cols:
      ctk.CTkLabel(
        header,
        text=text,
        width=width,
        anchor='w',
        font=font_body(weight='bold'),
        text_color=COLOR_TEXT_DIM,
      ).pack(side='left', padx=6, pady=6)

    self.table_scroll = ctk.CTkScrollableFrame(
      table_block,
      fg_color=COLOR_BG,
      corner_radius=0,
    )
    self.table_scroll.pack(fill='both', expand=True)

    self.bind('<Delete>', lambda _e: self._on_delete_accounts())

  def set_platform(self, platform_id: str) -> None:
    self.platform_id = platform_id
    self.selected_ids.clear()
    self.refresh_list()

  def refresh_list(self) -> None:
    for widget in self.table_scroll.winfo_children():
      widget.destroy()
    self.row_check_vars.clear()
    self.selected_ids.clear()

    accounts, _total = self.db.get_accounts_paginated(
      self.platform_id,
      page=1,
      page_size=10_000,
    )

    if not accounts:
      ctk.CTkLabel(
        self.table_scroll,
        text='暂无账号，点击「添加账号」开始',
        font=font_section(),
        text_color=COLOR_TEXT_DIM,
      ).pack(pady=60)
      return

    for acc in accounts:
      self._add_row(acc)

  def _add_row(self, account: Account) -> None:
    row = ctk.CTkFrame(self.table_scroll, fg_color=COLOR_SURFACE, corner_radius=4, height=44)
    row.pack(fill='x', pady=2, padx=4)
    row.pack_propagate(False)

    var = ctk.BooleanVar(value=False)

    def on_check() -> None:
      if var.get():
        self.selected_ids.add(account.id)
      else:
        self.selected_ids.discard(account.id)

    var.trace_add('write', lambda *_: on_check())
    self.row_check_vars[account.id] = var

    ctk.CTkCheckBox(
      row, text='', variable=var, width=28, checkbox_width=20, checkbox_height=20,
    ).pack(side='left', padx=8)

    display_id = format_account_display_id(account.platform, account.id)
    ctk.CTkLabel(row, text=display_id, width=120, anchor='w').pack(side='left', padx=4)
    ctk.CTkLabel(row, text=get_platform_name(account.platform), width=70, anchor='w').pack(
      side='left', padx=4,
    )
    ctk.CTkLabel(row, text=account.name, width=160, anchor='w').pack(side='left', padx=4)

    status_text, status_color = STATUS_LABELS.get(
      account.status, ('未知', COLOR_TEXT_DIM),
    )
    ctk.CTkLabel(
      row, text=status_text, width=110, anchor='w', text_color=status_color,
    ).pack(side='left', padx=4)

    time_str = account.created_at.strftime('%Y-%m-%d %H:%M')
    ctk.CTkLabel(row, text=time_str, width=150, anchor='w').pack(side='left', padx=4)

    ctk.CTkButton(
      row,
      text='重新登录',
      width=88,
      height=28,
      font=font_caption(),
      fg_color=COLOR_BORDER,
      hover_color=COLOR_BORDER_LIGHT,
      text_color=COLOR_TEXT,
      command=lambda a=account: self._on_relogin(a),
    ).pack(side='left', padx=8, pady=6)

  def _on_view_logs(self) -> None:
    from ui.dialogs import OperationLogsDialog

    OperationLogsDialog(self.winfo_toplevel(), self.db, self.platform_id)

  def _on_add_account(self) -> None:
    from ui.dialogs import LoginDialog

    LoginDialog(
      self.winfo_toplevel(),
      self.platform_id,
      self.db,
      mode='add',
      on_success=self.refresh_list,
    )

  def _on_relogin(self, account: Account) -> None:
    from ui.dialogs import LoginDialog

    LoginDialog(
      self.winfo_toplevel(),
      self.platform_id,
      self.db,
      mode='relogin',
      account=account,
      on_success=self.refresh_list,
    )

  def _on_delete_accounts(self) -> None:
    if not self.selected_ids:
      messagebox.showwarning('提示', '请先勾选要删除的账号（支持多选）')
      return

    count = len(self.selected_ids)
    if not messagebox.askyesno('确认删除', f'确定要删除选中的 {count} 个账号吗？\n此操作不可恢复。'):
      return

    deleted = 0
    for account_id in list(self.selected_ids):
      account = self.db.get_account_by_id(account_id)
      if account is None:
        continue
      state_path = Path(account.state_file_path)
      if self.db.delete_account(account_id):
        if state_path.is_file():
          state_path.unlink(missing_ok=True)
        self.db.add_operation_log(
          OP_DELETE, OP_STATUS_SUCCESS,
          f'已删除账号 {account.name}',
          account_id, account.platform,
        )
        deleted += 1

    messagebox.showinfo('完成', f'成功删除 {deleted} 个账号')
    self.refresh_list()


class AccountShell(ctk.CTkFrame):
  """账号管理外壳：平台 Tab + 账号列表."""

  def __init__(
    self,
    master: ctk.CTk,
    db: Database,
    on_status: Callable[[str], None],
  ) -> None:
    super().__init__(master, fg_color='transparent')
    self.db = db
    self.on_status = on_status
    self.current_platform_id = _default_platform_id()
    self.tab_buttons: Dict[str, ctk.CTkButton] = {}
    self.account_panel: Optional[AccountManagementPanel] = None

    self._build_ui()
    self._select_platform(self.current_platform_id)

  def _build_ui(self) -> None:
    tab_row = ctk.CTkFrame(self, fg_color='transparent')
    tab_row.pack(fill='x', pady=(0, SPACE_SM))
    for col_index in range(len(PLATFORMS)):
      tab_row.grid_columnconfigure(col_index, weight=1)

    for col_index, platform in enumerate(PLATFORMS):
      label = platform['name']
      if not platform['enabled']:
        label = f"{platform['name']}（开发中）"

      btn = ctk.CTkButton(
        tab_row,
        text=label,
        height=TAB_BAR_HEIGHT - 8,
        corner_radius=6,
        font=font_body(),
        fg_color=COLOR_BG,
        hover_color=COLOR_DISABLED if not platform['enabled'] else COLOR_TABLE_SELECT,
        text_color=COLOR_TEXT_DIM if not platform['enabled'] else COLOR_TEXT,
        border_width=0,
        state='disabled' if not platform['enabled'] else 'normal',
        command=lambda pid=platform['id'], en=platform['enabled']: self._on_tab_click(pid, en),
      )
      btn.grid(row=0, column=col_index, sticky='ew', padx=(0, 4))
      self.tab_buttons[platform['id']] = btn

    add_horizontal_divider(self)

    self.subtitle_label = ctk.CTkLabel(
      self,
      text='',
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
      anchor='w',
    )
    self.subtitle_label.pack(fill='x', pady=(0, SPACE_SM))

    self.content_frame = ctk.CTkFrame(self, fg_color='transparent')
    self.content_frame.pack(fill='both', expand=True)

  def _on_tab_click(self, platform_id: str, enabled: bool) -> None:
    if not enabled:
      messagebox.showinfo('提示', '该平台开发中，敬请期待！')
      return
    self._select_platform(platform_id)

  def refresh_on_show(self) -> None:
    """再次显示账号管理时刷新列表（例如从数据采集切回）."""
    if self.account_panel is not None:
      self.account_panel.refresh_list()

  def _select_platform(self, platform_id: str) -> None:
    self.current_platform_id = platform_id
    self._highlight_tab(platform_id)
    self.subtitle_label.configure(text=f'当前平台：{get_platform_name(platform_id)}')

    if self.account_panel:
      self.account_panel.destroy()
    self.account_panel = AccountManagementPanel(
      self.content_frame,
      self.db,
      platform_id,
      on_status=self.on_status,
    )
    self.account_panel.pack(fill='both', expand=True)

  def _highlight_tab(self, platform_id: str) -> None:
    tab_font = font_body()
    tab_font_active = font_body(weight='bold')
    for pid, btn in self.tab_buttons.items():
      platform = next((p for p in PLATFORMS if p['id'] == pid), None)
      if not platform or not platform['enabled']:
        btn.configure(
          fg_color=COLOR_BG,
          hover_color=COLOR_BG,
          text_color=COLOR_TEXT_DIM,
          border_width=0,
          font=tab_font,
        )
      elif pid == platform_id:
        btn.configure(
          fg_color=COLOR_ACCENT,
          hover_color=COLOR_ACCENT_HOVER,
          text_color=COLOR_ACCENT_TEXT,
          border_width=0,
          font=tab_font_active,
        )
      else:
        btn.configure(
          fg_color=COLOR_BG,
          hover_color=COLOR_TABLE_SELECT,
          text_color=COLOR_TEXT,
          border_width=0,
          font=tab_font,
        )


def _default_platform_id() -> str:
  for platform in PLATFORMS:
    if platform['enabled']:
      return platform['id']
  return PLATFORMS[0]['id']
