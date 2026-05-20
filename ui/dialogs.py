"""登录与操作日志弹窗."""

from __future__ import annotations

import io
import shutil
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from config import (
  APP_DATA_DIR,
  ensure_dirs,
  format_account_display_id,
  get_platform_name,
  get_state_file_path,
)
from infra.database import (
  ACCOUNT_STATUS_ACTIVE,
  OP_ADD,
  OP_RELOGIN,
  OP_STATUS_FAILED,
  OP_STATUS_SUCCESS,
  Account,
  Database,
  OperationLog,
)
from services.login import LoginHandler, LoginResult, run_login_in_thread
from ui.theme import (
  COLOR_ACCENT_TEXT,
  COLOR_BORDER,
  COLOR_BORDER_LIGHT,
  COLOR_DISABLED,
  COLOR_ERROR,
  COLOR_PANEL,
  COLOR_SUCCESS,
  COLOR_SUCCESS_HOVER,
  COLOR_SURFACE,
  COLOR_TEXT,
  COLOR_TEXT_DIM,
  COLOR_WARN,
  font_body,
  font_caption,
  font_section,
  get_font,
)

OP_TYPE_LABELS = {
  'add': '添加账号',
  'delete': '删除账号',
  'relogin': '重新登录',
  'collect': '数据采集',
}

LOG_STATUS_LABELS = {
  'success': '成功',
  'failed': '失败',
}


class LoginDialog(ctk.CTkToplevel):
  """添加账号 / 重新登录弹窗."""

  def __init__(
    self,
    master: ctk.CTk,
    platform_id: str,
    db: Database,
    mode: str = 'add',
    account: Optional[Account] = None,
    on_success: Optional[Callable[[], None]] = None,
  ) -> None:
    super().__init__(master)
    self.master_app = master
    self.platform_id = platform_id
    self.db = db
    self.mode = mode
    self.account = account
    self.on_success_cb = on_success
    self.login_handler: Optional[LoginHandler] = None
    self.login_success = False
    self.qr_pending_confirm = False
    self.temp_state_path: Optional[Path] = None
    self._qr_image_ref: Optional[ImageTk.PhotoImage] = None

    title = '重新登录' if mode == 'relogin' else '添加新账号'
    self.title(title)
    self.geometry('440x640')
    self.minsize(440, 640)
    self.resizable(False, False)
    self.transient(master)
    self.grab_set()
    self.configure(fg_color=COLOR_PANEL)

    self._build_ui()
    self.protocol('WM_DELETE_WINDOW', self._on_cancel)
    self.after(300, self._start_login)

  def _build_ui(self) -> None:
    bottom_bar = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=0)
    bottom_bar.pack(side='bottom', fill='x')

    self.status_label = ctk.CTkLabel(
      bottom_bar,
      text='状态：等待扫码...',
      font=font_body(),
      text_color=COLOR_TEXT_DIM,
    )
    self.status_label.pack(fill='x', padx=20, pady=(12, 6))

    btn_frame = ctk.CTkFrame(bottom_bar, fg_color='transparent')
    btn_frame.pack(fill='x', padx=20, pady=(0, 16))

    self.cancel_btn = ctk.CTkButton(
      btn_frame,
      text='取消',
      width=120,
      height=40,
      font=font_section(),
      fg_color=COLOR_BORDER,
      hover_color=COLOR_BORDER_LIGHT,
      text_color=COLOR_TEXT,
      command=self._on_cancel,
    )
    self.cancel_btn.pack(side='left')

    self.confirm_btn = ctk.CTkButton(
      btn_frame,
      text='保存账号',
      width=140,
      height=40,
      font=font_section(),
      fg_color=COLOR_SUCCESS,
      hover_color=COLOR_SUCCESS_HOVER,
      text_color=COLOR_ACCENT_TEXT,
      state='disabled',
      command=self._on_confirm,
    )
    self.confirm_btn.pack(side='right')

    content = ctk.CTkFrame(self, fg_color='transparent')
    content.pack(side='top', fill='both', expand=True)

    ctk.CTkLabel(
      content,
      text='重新登录' if self.mode == 'relogin' else '添加新账号',
      font=get_font(18, weight='bold'),
      text_color=COLOR_TEXT,
    ).pack(padx=20, pady=(14, 4))

    platform_name = get_platform_name(self.platform_id)
    ctk.CTkLabel(
      content,
      text=f'当前平台：{platform_name}',
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
    ).pack(padx=20, pady=(0, 8))

    form = ctk.CTkFrame(content, fg_color='transparent')
    form.pack(fill='x', padx=20, pady=4)

    ctk.CTkLabel(
      form, text='账号名称：', anchor='w', text_color=COLOR_TEXT_DIM,
    ).grid(row=0, column=0, sticky='w', pady=4)
    default_name = self.account.name if self.account else ''
    self.name_var = ctk.StringVar(value=default_name)
    name_state = 'disabled' if self.mode == 'relogin' else 'normal'
    self.name_entry = ctk.CTkEntry(form, textvariable=self.name_var, width=260, state=name_state)
    self.name_entry.grid(row=0, column=1, sticky='ew', pady=4)

    ctk.CTkLabel(
      form, text='登录昵称：', anchor='w', text_color=COLOR_TEXT_DIM,
    ).grid(row=1, column=0, sticky='w', pady=4)
    self.nickname_var = ctk.StringVar(value='扫码成功后自动显示')
    self.nickname_label = ctk.CTkLabel(
      form,
      textvariable=self.nickname_var,
      anchor='w',
      width=260,
      text_color=COLOR_TEXT_DIM,
      font=font_body(),
    )
    self.nickname_label.grid(row=1, column=1, sticky='w', pady=4)
    form.grid_columnconfigure(1, weight=1)

    self.qr_frame = ctk.CTkFrame(
      content, fg_color=COLOR_SURFACE, corner_radius=8,
      border_width=1, border_color=COLOR_BORDER, height=300,
    )
    self.qr_frame.pack(fill='x', padx=20, pady=10)
    self.qr_frame.pack_propagate(False)

    self.qr_label = ctk.CTkLabel(
      self.qr_frame,
      text='正在加载二维码...',
      width=260,
      height=260,
      font=font_body(),
      text_color=COLOR_TEXT_DIM,
    )
    self.qr_label.pack(pady=(12, 4))

    self.qr_hint_label = ctk.CTkLabel(
      self.qr_frame,
      text=f'请使用{platform_name} APP 扫描二维码',
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
    )
    self.qr_hint_label.pack(pady=(0, 10))

  def _set_status(self, text: str) -> None:
    def _apply() -> None:
      self.status_label.configure(text=f'状态：{text}')
      if '请在手机上确认' in text or (
        '扫码成功' in text and '确认' in text
      ):
        self._show_qr_pending_confirm()

    self.after(0, _apply)

  def _show_qr_pending_confirm(self) -> None:
    self.qr_pending_confirm = True
    self._qr_image_ref = None
    self.qr_label.configure(
      image='',
      text='扫码成功\n\n请在手机上确认登录',
      font=get_font(16, weight='bold'),
      text_color=COLOR_SUCCESS,
    )
    self.qr_hint_label.configure(
      text='确认后稍候，将自动完成登录',
      text_color=COLOR_TEXT_DIM,
    )

  def _update_qr_image(self, image_bytes: bytes) -> None:
    def _apply() -> None:
      if self.qr_pending_confirm:
        return
      try:
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        img = img.resize((260, 260), Image.Resampling.LANCZOS)
        self._qr_image_ref = ImageTk.PhotoImage(img)
        self.qr_label.configure(
          image=self._qr_image_ref,
          text='',
          font=font_body(),
          text_color=COLOR_TEXT_DIM,
        )
      except Exception:
        pass

    self.after(0, _apply)

  def _start_login(self) -> None:
    ensure_dirs()
    temp_dir = APP_DATA_DIR / 'temp'
    temp_dir.mkdir(parents=True, exist_ok=True)
    self.temp_state_path = temp_dir / f'login_{self.platform_id}_{id(self)}.json'

    self.login_handler = LoginHandler(self.platform_id)

    def on_qr(data: bytes) -> None:
      self._update_qr_image(data)

    def on_status(msg: str) -> None:
      self._set_status(msg)

    async def _coro() -> LoginResult:
      assert self.login_handler and self.temp_state_path
      return await self.login_handler.run_login(
        self.temp_state_path,
        on_qr_image=on_qr,
        on_status=on_status,
      )

    def on_complete(result: LoginResult) -> None:
      self.after(0, lambda: self._on_login_complete(result))

    def on_error(exc: Exception) -> None:
      self.after(0, lambda: self._on_login_error(exc))

    run_login_in_thread(_coro(), on_complete, on_error)

  def _on_login_complete(self, result: LoginResult) -> None:
    if result.success:
      self.login_success = True
      nickname = (result.nickname or '').strip()

      if nickname:
        self.nickname_var.set(nickname)
        self.nickname_label.configure(text_color=COLOR_SUCCESS)
        if self.mode == 'add':
          self.name_var.set(nickname)
      else:
        self.nickname_var.set('未获取到昵称，请手动填写账号名称')
        self.nickname_label.configure(text_color=COLOR_WARN)

      self.qr_frame.pack_forget()
      self._set_status('登录成功，请点击「保存账号」')
      self.confirm_btn.configure(state='normal')
      self.update_idletasks()
      self.lift()
      self.focus_force()
    else:
      self._set_status(result.message)
      messagebox.showwarning('登录失败', result.message, parent=self)

  def _on_login_error(self, exc: Exception) -> None:
    self._set_status(f'错误: {exc}')
    messagebox.showerror('错误', str(exc), parent=self)

  def _on_confirm(self) -> None:
    if not self.login_success or not self.temp_state_path:
      messagebox.showwarning('提示', '请先完成扫码登录', parent=self)
      return

    if self.mode == 'add':
      name = self.name_var.get().strip()
      if not name:
        messagebox.showwarning('提示', '请输入账号名称（可使用登录昵称）', parent=self)
        self.name_entry.configure(state='normal')
        self.name_entry.focus()
        return
      if self.db.name_exists(self.platform_id, name):
        messagebox.showwarning('提示', f'账号名称「{name}」已存在', parent=self)
        return
      try:
        account_id = self.db.create_account(self.platform_id, name)
        final_path = get_state_file_path(self.platform_id, account_id)
        shutil.move(str(self.temp_state_path), str(final_path))
        self.db.update_account(
          account_id,
          state_file_path=str(final_path),
          status=ACCOUNT_STATUS_ACTIVE,
        )
        msg = f'成功添加账号 {format_account_display_id(self.platform_id, account_id)}'
        self.db.add_operation_log(OP_ADD, OP_STATUS_SUCCESS, msg, account_id, self.platform_id)
      except Exception as exc:
        self.db.add_operation_log(OP_ADD, OP_STATUS_FAILED, str(exc), platform=self.platform_id)
        messagebox.showerror('失败', str(exc), parent=self)
        return
    else:
      assert self.account is not None
      final_path = Path(self.account.state_file_path)
      try:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.temp_state_path), str(final_path))
        self.db.update_account(self.account.id, status=ACCOUNT_STATUS_ACTIVE)
        msg = f'账号 {format_account_display_id(self.account.platform, self.account.id)} 重新登录成功'
        self.db.add_operation_log(
          OP_RELOGIN, OP_STATUS_SUCCESS, msg, self.account.id, self.platform_id,
        )
      except Exception as exc:
        self.db.add_operation_log(
          OP_RELOGIN, OP_STATUS_FAILED, str(exc), self.account.id, self.platform_id,
        )
        messagebox.showerror('失败', str(exc), parent=self)
        return

    if self.on_success_cb:
      self.on_success_cb()
    self.destroy()

  def _on_cancel(self) -> None:
    if self.login_handler:
      self.login_handler.cancel()
    if self.temp_state_path and self.temp_state_path.exists() and self.mode == 'add':
      self.temp_state_path.unlink(missing_ok=True)
    self.destroy()


class OperationLogsDialog(ctk.CTkToplevel):
  """操作日志查看弹窗."""

  def __init__(self, master: ctk.CTk, db: Database, platform_id: Optional[str] = None) -> None:
    super().__init__(master)
    self.db = db
    self.platform_id = platform_id

    self.title('操作日志')
    self.geometry('900x520')
    self.minsize(720, 400)
    self.transient(master)
    self.grab_set()
    self.configure(fg_color=COLOR_PANEL)

    ctk.CTkLabel(
      self,
      text='最近操作记录（最多 50 条）',
      font=get_font(16, weight='bold'),
    ).pack(anchor='w', padx=20, pady=(16, 8))

    scroll = ctk.CTkScrollableFrame(self, fg_color=COLOR_SURFACE, corner_radius=8)
    scroll.pack(fill='both', expand=True, padx=20, pady=8)

    header = ctk.CTkFrame(scroll, fg_color=COLOR_PANEL, height=32)
    header.pack(fill='x', pady=(0, 4))
    header.pack_propagate(False)
    for text, width in [
      ('时间', 150), ('操作类型', 90), ('账号ID', 80),
      ('状态', 60), ('消息', 420),
    ]:
      ctk.CTkLabel(
        header, text=text, width=width, anchor='w',
        font=font_caption(weight='bold'), text_color=COLOR_TEXT_DIM,
      ).pack(side='left', padx=6, pady=4)

    logs = db.get_recent_logs(50, platform_id)
    if not logs:
      ctk.CTkLabel(
        scroll, text='暂无操作日志', text_color=COLOR_TEXT_DIM,
      ).pack(pady=40)
    else:
      for log in logs:
        self._add_log_row(scroll, log)

    ctk.CTkButton(
      self, text='关闭', width=100, command=self.destroy,
      fg_color=COLOR_BORDER, hover_color=COLOR_DISABLED,
    ).pack(pady=16)

  def _add_log_row(self, parent: ctk.CTkScrollableFrame, log: OperationLog) -> None:
    row = ctk.CTkFrame(parent, fg_color=COLOR_PANEL, corner_radius=4, height=36)
    row.pack(fill='x', pady=2)
    row.pack_propagate(False)

    time_str = log.created_at.strftime('%Y-%m-%d %H:%M:%S')
    op_label = OP_TYPE_LABELS.get(log.operation_type, log.operation_type)
    account_str = str(log.account_id) if log.account_id is not None else '-'
    status_label = LOG_STATUS_LABELS.get(log.status, log.status)
    status_color = COLOR_SUCCESS if log.status == 'success' else COLOR_ERROR
    message = log.message if len(log.message) <= 55 else log.message[:55] + '...'

    ctk.CTkLabel(row, text=time_str, width=150, anchor='w').pack(side='left', padx=6)
    ctk.CTkLabel(row, text=op_label, width=90, anchor='w').pack(side='left', padx=4)
    ctk.CTkLabel(row, text=account_str, width=80, anchor='w').pack(side='left', padx=4)
    ctk.CTkLabel(row, text=status_label, width=60, anchor='w', text_color=status_color).pack(
      side='left', padx=4,
    )
    ctk.CTkLabel(row, text=message, width=420, anchor='w').pack(side='left', padx=4)
