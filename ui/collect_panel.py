"""数据采集面板."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional, Set

import customtkinter as ctk

from config import EXPORT_DIR, PLATFORMS
from core.export_schema import normalize_platform_id
from core.models import CollectResultItem, CollectSummary, ExcelSheetData
from core.platforms import can_collect, get_platform_name, list_collectable_platform_ids
from infra.database import ACCOUNT_STATUS_EXPIRED, Account, Database
from infra.excel import (
  auto_detect_link_column,
  export_all_platform_results,
  export_platform_results,
  extract_links_from_column,
  read_excel_sheet,
)
from infra.platform_detect import detect_platform
from services.collect import CollectService
from shared.async_runner import run_coro_in_thread
from ui.widgets import LAYOUT_DEBOUNCE_MS, CollectResultGrid
from ui.theme import (
  BTN_HEIGHT,
  COLOR_ACCENT,
  COLOR_ACCENT_HOVER,
  COLOR_ACCENT_TEXT,
  COLOR_BORDER,
  COLOR_BORDER_LIGHT,
  COLOR_ERROR,
  COLOR_PANEL,
  COLOR_SELECTED,
  COLOR_SUCCESS,
  COLOR_SUCCESS_HOVER,
  COLOR_SURFACE,
  COLOR_TABLE_SELECT,
  COLOR_TEXT,
  COLOR_TEXT_DIM,
  FONT_SIZE_BODY,
  RADIUS_BTN,
  TAB_BAR_HEIGHT,
  TAB_SEGMENT_RADIUS,
  font_body,
  font_caption,
  font_section,
  get_font,
)

def _platform_can_collect(platform_id: str) -> bool:
  return can_collect(platform_id)


def _collect_tab_platform_ids() -> List[str]:
  return list_collectable_platform_ids()


def _tab_label(platform_id: str) -> str:
  return get_platform_name(platform_id)


class CollectPanel(ctk.CTkFrame):
  """数据采集主面板."""

  def __init__(
    self,
    master: ctk.CTk,
    db: Database,
    on_status: Callable[[str], None],
  ) -> None:
    super().__init__(master, fg_color='transparent')
    self.db = db
    self.on_status = on_status

    self.collect_service = CollectService(db)
    self.excel_path: Optional[str] = None
    self.sheet_headers: List[str] = []
    self.sheet_rows: List[list] = []
    self.results_by_platform: Dict[str, List[CollectResultItem]] = {}
    self.result_grids: Dict[str, CollectResultGrid] = {}
    self._platform_panels: Dict[str, ctk.CTkFrame] = {}
    self._tab_platform_ids: List[str] = []
    self._tab_labels: List[str] = []
    self._tab_buttons: Dict[str, ctk.CTkButton] = {}
    self._active_platform_tab: str = ''
    self._panel_layout_after_id: Optional[str] = None
    self.is_collecting = False

    self.platform_combos: Dict[str, ctk.CTkComboBox] = {}
    self.platform_account_maps: Dict[str, Dict[str, Account]] = {}

    self._build_ui()
    self.after(0, self.refresh_accounts)

  def _build_result_tabs(self) -> None:
    if hasattr(self, 'result_content'):
      for child in self.result_content.winfo_children():
        child.destroy()
    self.result_grids.clear()
    self._platform_panels.clear()
    self.results_by_platform.clear()
    self._tab_platform_ids = _collect_tab_platform_ids()
    self._tab_labels = [_tab_label(platform_id) for platform_id in self._tab_platform_ids]

    for platform_id in self._tab_platform_ids:
      panel = ctk.CTkFrame(self.result_content, fg_color='transparent')
      panel.grid(row=0, column=0, sticky='nsew')
      panel.grid_rowconfigure(0, weight=1)
      panel.grid_columnconfigure(0, weight=1)
      grid = CollectResultGrid(panel, platform_id)
      grid.grid(row=0, column=0, sticky='nsew')
      self._platform_panels[platform_id] = panel
      self.result_grids[platform_id] = grid
      self.results_by_platform[platform_id] = []

    if self._tab_platform_ids:
      self._show_platform_tab(self._tab_platform_ids[0])

  def _on_panel_destroy(self, event=None) -> None:
    if event is not None and event.widget is not self:
      return
    if self._panel_layout_after_id is not None:
      try:
        self.after_cancel(self._panel_layout_after_id)
      except Exception:
        pass
      self._panel_layout_after_id = None

  def _on_result_toplevel_configure(self, event) -> None:
    try:
      if str(event.widget) != str(self.winfo_toplevel()):
        return
    except Exception:
      return
    self._schedule_active_grid_layout()

  def _schedule_active_grid_layout(self) -> None:
    if self._panel_layout_after_id is not None:
      try:
        self.after_cancel(self._panel_layout_after_id)
      except Exception:
        pass

    def _run() -> None:
      self._panel_layout_after_id = None
      platform_id = self._get_current_tab_platform_id()
      grid = self.result_grids.get(platform_id)
      if grid is not None:
        grid.refresh_layout()

    try:
      self._panel_layout_after_id = self.after(LAYOUT_DEBOUNCE_MS, _run)
    except Exception:
      self._panel_layout_after_id = None

  def _show_platform_tab(self, platform_id: str) -> None:
    for pid, panel in self._platform_panels.items():
      if pid == platform_id:
        panel.grid()
        self.result_grids[pid].refresh_layout()
      else:
        panel.grid_remove()

  def _clear_all_results(self) -> None:
    for platform_id in self._tab_platform_ids:
      self.results_by_platform[platform_id] = []
      if platform_id in self.result_grids:
        self.result_grids[platform_id].clear()

  def _all_results(self) -> List[CollectResultItem]:
    items: List[CollectResultItem] = []
    for platform_id in self._tab_platform_ids:
      items.extend(self.results_by_platform.get(platform_id, []))
    return items

  def _has_any_results(self) -> bool:
    return any(self.results_by_platform.get(pid) for pid in self._tab_platform_ids)

  def _resolve_platform_id(self, item: CollectResultItem) -> str:
    if item.platform_id:
      return normalize_platform_id(item.platform_id)
    detected = detect_platform(item.link)
    return normalize_platform_id(detected.platform_id)

  def _get_current_tab_platform_id(self) -> str:
    if self._active_platform_tab:
      return self._active_platform_tab
    return self._tab_platform_ids[0] if self._tab_platform_ids else ''

  def _set_active_tab_button(self, platform_id: str) -> None:
    self._active_platform_tab = platform_id
    for pid, button in self._tab_buttons.items():
      if pid == platform_id:
        button.configure(
          fg_color=COLOR_ACCENT,
          hover_color=COLOR_ACCENT_HOVER,
          text_color=COLOR_ACCENT_TEXT,
          border_width=0,
        )
      else:
        button.configure(
          fg_color=COLOR_SURFACE,
          hover_color=COLOR_SELECTED,
          text_color=COLOR_TEXT,
          border_width=1,
          border_color=COLOR_BORDER_LIGHT,
        )

  def _on_platform_tab_clicked(self, platform_id: str) -> None:
    if platform_id == self._active_platform_tab:
      return
    self._set_active_tab_button(platform_id)
    self._show_platform_tab(platform_id)

  def _set_export_buttons_state(self, enabled: bool) -> None:
    state = 'normal' if enabled else 'disabled'
    self.export_current_btn.configure(state=state)
    self.export_all_btn.configure(state=state)

  def _build_ui(self) -> None:
    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(3, weight=1)

    config_card = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=8)
    config_card.grid(row=0, column=0, sticky='ew', pady=(0, 8))

    row1 = ctk.CTkFrame(config_card, fg_color='transparent')
    row1.pack(fill='x', padx=12, pady=(12, 6))

    ctk.CTkLabel(
      row1,
      text='Excel 文件',
      width=64,
      anchor='w',
      font=font_caption(weight='bold'),
      text_color=COLOR_TEXT,
    ).pack(side='left', padx=(0, 8))

    ctk.CTkButton(
      row1,
      text='选择 Excel',
      width=118,
      height=BTN_HEIGHT,
      corner_radius=RADIUS_BTN,
      fg_color=COLOR_SURFACE,
      hover_color=COLOR_TABLE_SELECT,
      border_color=COLOR_ACCENT,
      border_width=1,
      text_color=COLOR_ACCENT,
      font=font_body(weight='bold'),
      command=self._on_pick_excel,
    ).pack(side='left')

    file_box = ctk.CTkFrame(
      row1,
      fg_color=COLOR_SURFACE,
      border_color=COLOR_BORDER_LIGHT,
      border_width=1,
      corner_radius=RADIUS_BTN,
      height=BTN_HEIGHT,
    )
    file_box.pack(side='left', fill='x', expand=True, padx=(10, 12))
    file_box.pack_propagate(False)

    self.excel_label = ctk.CTkLabel(
      file_box,
      text='未选择文件，请点击「选择 Excel」',
      anchor='w',
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
    )
    self.excel_label.pack(fill='both', expand=True, padx=10)

    export_box = ctk.CTkFrame(row1, fg_color='transparent')
    export_box.pack(side='right')

    self.export_current_btn = ctk.CTkButton(
      export_box,
      text='导出当前平台',
      width=108,
      height=BTN_HEIGHT,
      corner_radius=RADIUS_BTN,
      fg_color=COLOR_SUCCESS,
      hover_color=COLOR_SUCCESS_HOVER,
      text_color=COLOR_ACCENT_TEXT,
      state='disabled',
      command=self._on_export_current,
    )
    self.export_current_btn.pack(side='left', padx=(0, 6))

    self.export_all_btn = ctk.CTkButton(
      export_box,
      text='导出全部',
      width=88,
      height=BTN_HEIGHT,
      corner_radius=RADIUS_BTN,
      fg_color=COLOR_ACCENT,
      hover_color=COLOR_ACCENT_HOVER,
      text_color=COLOR_ACCENT_TEXT,
      state='disabled',
      command=self._on_export_all,
    )
    self.export_all_btn.pack(side='left')

    row2 = ctk.CTkFrame(config_card, fg_color='transparent')
    row2.pack(fill='x', padx=12, pady=(0, 12))

    ctk.CTkLabel(row2, text='链接列', width=50, anchor='w').pack(side='left')
    self.column_combo = ctk.CTkComboBox(
      row2,
      width=220,
      values=[],
      state='readonly',
    )
    self.column_combo.pack(side='left', padx=(0, 16))

    self.start_btn = ctk.CTkButton(
      row2,
      text='开始采集',
      width=100,
      fg_color=COLOR_ACCENT,
      hover_color=COLOR_ACCENT_HOVER,
      text_color=COLOR_ACCENT_TEXT,
      command=self._on_start_collect,
    )
    self.start_btn.pack(side='left', padx=4)

    self.stop_btn = ctk.CTkButton(
      row2,
      text='停止',
      width=80,
      fg_color=COLOR_ERROR,
      hover_color=COLOR_ERROR,
      text_color=COLOR_ACCENT_TEXT,
      state='disabled',
      command=self._on_stop_collect,
    )
    self.stop_btn.pack(side='left', padx=4)

    account_card = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=8)
    account_card.grid(row=1, column=0, sticky='ew', pady=(0, 8))

    ctk.CTkLabel(
      account_card,
      text='各平台执行账号（混链时按平台自动选用）',
      font=font_caption(weight='bold'),
      text_color=COLOR_TEXT,
      anchor='w',
    ).pack(fill='x', padx=12, pady=(8, 4))

    self.account_map_frame = ctk.CTkFrame(account_card, fg_color='transparent')
    self.account_map_frame.pack(fill='x', padx=12, pady=(0, 8))
    self.account_map_frame.grid_columnconfigure(0, weight=1)
    self.account_map_frame.grid_columnconfigure(1, weight=1)

    progress_card = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=8)
    progress_card.grid(row=2, column=0, sticky='ew', pady=(0, 8))

    inner = ctk.CTkFrame(progress_card, fg_color='transparent')
    inner.pack(fill='x', padx=12, pady=8)

    self.progress_label = ctk.CTkLabel(
      inner, text='等待开始采集', anchor='w', text_color=COLOR_TEXT_DIM,
    )
    self.progress_label.pack(fill='x')

    self.progress_bar = ctk.CTkProgressBar(inner, height=12)
    self.progress_bar.pack(fill='x', pady=(8, 0))
    self.progress_bar.set(0)

    table_card = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=8)
    table_card.grid(row=3, column=0, sticky='nsew')
    table_card.grid_rowconfigure(1, weight=1)
    table_card.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
      table_card,
      text='采集结果',
      font=font_body(weight='bold'),
      text_color=COLOR_TEXT,
      anchor='w',
    ).grid(row=0, column=0, sticky='ew', padx=12, pady=(10, 4))

    table_inner = ctk.CTkFrame(table_card, fg_color='transparent')
    table_inner.grid(row=1, column=0, sticky='nsew', padx=8, pady=(0, 8))
    table_inner.grid_rowconfigure(1, weight=1)
    table_inner.grid_columnconfigure(0, weight=1)

    tab_bar_wrap = ctk.CTkFrame(
      table_inner,
      fg_color=COLOR_SURFACE,
      corner_radius=TAB_SEGMENT_RADIUS,
      border_width=1,
      border_color=COLOR_BORDER_LIGHT,
    )
    tab_bar_wrap.grid(row=0, column=0, sticky='ew', pady=(0, 8))
    tab_bar_wrap.grid_columnconfigure(0, weight=1)

    self._tab_platform_ids = _collect_tab_platform_ids()
    self._tab_labels = [_tab_label(platform_id) for platform_id in self._tab_platform_ids]
    self._tab_buttons.clear()

    tab_bar_inner = ctk.CTkFrame(tab_bar_wrap, fg_color=COLOR_PANEL, corner_radius=6)
    tab_bar_inner.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
    for col_index in range(len(self._tab_platform_ids)):
      tab_bar_inner.grid_columnconfigure(col_index, weight=1)

    tab_font = font_body(weight='bold')
    for col_index, platform_id in enumerate(self._tab_platform_ids):
      button = ctk.CTkButton(
        tab_bar_inner,
        text=self._tab_labels[col_index],
        height=TAB_BAR_HEIGHT - 8,
        corner_radius=6,
        fg_color=COLOR_SURFACE,
        hover_color=COLOR_SELECTED,
        text_color=COLOR_TEXT,
        border_width=1,
        border_color=COLOR_BORDER_LIGHT,
        font=tab_font,
        command=lambda pid=platform_id: self._on_platform_tab_clicked(pid),
      )
      button.grid(row=0, column=col_index, sticky='ew', padx=2)
      self._tab_buttons[platform_id] = button

    if self._tab_platform_ids:
      self._set_active_tab_button(self._tab_platform_ids[0])

    self.result_content = ctk.CTkFrame(table_inner, fg_color='transparent')
    self.result_content.grid(row=1, column=0, sticky='nsew')
    self.result_content.grid_rowconfigure(0, weight=1)
    self.result_content.grid_columnconfigure(0, weight=1)
    self._build_result_tabs()
    toplevel = self.winfo_toplevel()
    toplevel.bind('<Configure>', self._on_result_toplevel_configure, add='+')
    self.bind('<Destroy>', self._on_panel_destroy, add='+')

  def refresh_accounts(self) -> None:
    grouped = self.db.get_collectable_accounts_grouped()

    for widget in self.account_map_frame.winfo_children():
      widget.destroy()
    self.platform_combos.clear()
    self.platform_account_maps.clear()

    for index, platform in enumerate(PLATFORMS):
      grid_row = index // 2
      grid_col = index % 2
      cell = ctk.CTkFrame(self.account_map_frame, fg_color='transparent', height=32)
      cell.grid(row=grid_row, column=grid_col, sticky='ew', padx=(0, 8), pady=2)
      cell.grid_propagate(False)
      cell.grid_columnconfigure(1, weight=1)

      ctk.CTkLabel(
        cell,
        text=platform['name'],
        width=56,
        anchor='w',
        font=font_caption(),
        text_color=COLOR_TEXT,
      ).grid(row=0, column=0, sticky='w', padx=(0, 6))

      if not platform['enabled']:
        ctk.CTkLabel(
          cell, text='开发中', anchor='w', font=get_font(11), text_color=COLOR_TEXT_DIM,
        ).grid(row=0, column=1, sticky='w')
        continue

      if not _platform_can_collect(platform['id']):
        ctk.CTkLabel(
          cell, text='暂不支持', anchor='w', font=get_font(11), text_color=COLOR_TEXT_DIM,
        ).grid(row=0, column=1, sticky='w')
        continue

      accounts = grouped.get(platform['id'], [])
      label_map: Dict[str, Account] = {}
      labels: List[str] = []
      for account in accounts:
        label = f'{account.name} (ID:{account.id})'
        labels.append(label)
        label_map[label] = account

      combo = ctk.CTkComboBox(cell, width=160, values=[], state='readonly')
      combo.grid(row=0, column=1, sticky='ew')

      hint_text = f'{len(labels)} 个' if labels else '无账号'
      ctk.CTkLabel(
        cell,
        text=hint_text,
        width=36,
        anchor='e',
        font=get_font(11),
        text_color=COLOR_TEXT_DIM,
      ).grid(row=0, column=2, sticky='e', padx=(4, 0))

      if labels:
        combo.configure(values=labels)
        combo.set(labels[0])
      else:
        combo.configure(values=['暂无账号'])
        combo.set('暂无账号')
        combo.configure(state='disabled')

      self.platform_combos[platform['id']] = combo
      self.platform_account_maps[platform['id']] = label_map

  def _get_account_by_platform(self) -> Dict[str, Account]:
    result: Dict[str, Account] = {}
    for platform_id, combo in self.platform_combos.items():
      label = combo.get()
      account = self.platform_account_maps.get(platform_id, {}).get(label)
      if account is not None:
        result[platform_id] = account
    return result

  def _get_required_collect_platforms(self, links: List[str]) -> Set[str]:
    required: Set[str] = set()
    for link in links:
      detected = detect_platform(link)
      if detected.can_collect:
        required.add(detected.platform_id)
    return required

  def _validate_before_collect(self, links: List[str]) -> Optional[str]:
    required = self._get_required_collect_platforms(links)
    if not required:
      return None

    account_map = self._get_account_by_platform()
    missing: List[str] = []
    for platform_id in sorted(required):
      if platform_id not in account_map:
        missing.append(get_platform_name(platform_id))

    if not missing:
      return None

    names = '、'.join(missing)
    return (
      f'Excel 中包含以下平台的可采集链接，但未配置执行账号：{names}\n'
      f'请在「各平台执行账号」区域选择账号，或到账号管理添加并登录。'
    )

  def _on_pick_excel(self) -> None:
    path = filedialog.askopenfilename(
      title='选择 Excel 文件',
      filetypes=[('Excel 文件', '*.xlsx'), ('所有文件', '*.*')],
    )
    if not path:
      return

    try:
      sheet_data = read_excel_sheet(path)
    except Exception as exc:
      messagebox.showerror('错误', f'读取 Excel 失败：{exc}')
      return

    self.excel_path = path
    self.sheet_headers = sheet_data.headers
    self.sheet_rows = sheet_data.rows
    self.excel_label.configure(text=Path(path).name, text_color=COLOR_TEXT)

    if not self.sheet_headers:
      messagebox.showwarning('提示', 'Excel 表头为空')
      return

    header_labels = [
      f'{index + 1}. {header or f"列{index + 1}"}'
      for index, header in enumerate(self.sheet_headers)
    ]
    self.column_combo.configure(values=header_labels)
    default_index = auto_detect_link_column(self.sheet_headers)
    if default_index < 0:
      default_index = 0
    self.column_combo.set(header_labels[default_index])

  def _get_selected_column_index(self) -> int:
    selected = self.column_combo.get()
    if not selected:
      return -1
    try:
      return int(selected.split('.', 1)[0]) - 1
    except ValueError:
      return -1

  def _on_start_collect(self) -> None:
    if self.is_collecting:
      return

    if not self.excel_path:
      messagebox.showwarning('提示', '请先选择 Excel 文件')
      return

    column_index = self._get_selected_column_index()
    if column_index < 0:
      messagebox.showwarning('提示', '请选择链接列')
      return

    sheet_data = ExcelSheetData(headers=self.sheet_headers, rows=self.sheet_rows)
    links = extract_links_from_column(sheet_data, column_index)
    if not links:
      messagebox.showwarning('提示', '链接列中没有有效链接')
      return

    validation_error = self._validate_before_collect(links)
    if validation_error:
      messagebox.showwarning('无法开始采集', validation_error)
      return

    account_by_platform = self._get_account_by_platform()
    if not account_by_platform and self._get_required_collect_platforms(links):
      messagebox.showwarning('提示', '请为需要采集的平台选择执行账号')
      return

    self._clear_all_results()

    self.is_collecting = True
    self.start_btn.configure(state='disabled')
    self.stop_btn.configure(state='normal')
    self._set_export_buttons_state(False)
    self.progress_bar.set(0)
    self.on_status(f'开始采集，共 {len(links)} 条链接')

    service = self.collect_service

    def on_progress(progress) -> None:
      self.after(0, lambda: self._update_progress(progress))

    def on_row(item: CollectResultItem) -> None:
      self.after(0, lambda: self._append_result_row(item))

    def on_complete(summary: CollectSummary) -> None:
      self.after(0, lambda: self._on_collect_finished(summary))

    def on_error(exc: Exception) -> None:
      self.after(0, lambda: self._on_collect_error(exc))

    run_coro_in_thread(
      service.run_batch(
        links,
        account_by_platform,
        self.excel_path or '',
        on_progress=on_progress,
        on_row=on_row,
      ),
      on_complete,
      on_error,
    )

  def _on_stop_collect(self) -> None:
    self.collect_service.cancel()
    self.on_status('正在停止采集...')

  def _update_progress(self, progress) -> None:
    total = max(progress.total, 1)
    self.progress_bar.set(progress.current / total)
    self.progress_label.configure(text=progress.message)

  def _append_result_row(self, item: CollectResultItem) -> None:
    platform_id = self._resolve_platform_id(item)
    if platform_id not in self.results_by_platform:
      return
    if not item.platform_id:
      item.platform_id = platform_id

    rows = self.results_by_platform[platform_id]
    rows.append(item)
    grid = self.result_grids.get(platform_id)
    if grid is not None:
      grid.add_row(item, len(rows))

  def _on_collect_finished(self, summary: CollectSummary) -> None:
    self.is_collecting = False
    self.start_btn.configure(state='normal')
    self.stop_btn.configure(state='disabled')
    if self._has_any_results():
      self._set_export_buttons_state(True)

    if summary.expired_account_ids:
      for account_id in summary.expired_account_ids:
        self.db.update_account(account_id, status=ACCOUNT_STATUS_EXPIRED)
      self.refresh_accounts()
      messagebox.showwarning('登录过期', '部分账号登录已过期，请到账号管理重新登录')

    msg = (
      f'采集结束：成功 {summary.success_count}，失败 {summary.failed_count}，'
      f'不支持 {summary.unsupported_count}'
    )
    if summary.cancelled:
      msg += '（已停止）'
    self.progress_label.configure(text=msg)
    self.on_status(msg)

  def _on_collect_error(self, exc: Exception) -> None:
    self.is_collecting = False
    self.start_btn.configure(state='normal')
    self.stop_btn.configure(state='disabled')
    messagebox.showerror('采集失败', str(exc))
    self.on_status(f'采集失败：{exc}')

  def _on_export_current(self) -> None:
    platform_id = self._get_current_tab_platform_id()
    items = self.results_by_platform.get(platform_id, [])
    if not items:
      messagebox.showwarning('提示', f'当前「{_tab_label(platform_id)}」Tab 没有可导出的数据')
      return

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    default_name = f'采集结果_{_tab_label(platform_id)}_{timestamp}.xlsx'
    save_path = filedialog.asksaveasfilename(
      title=f'导出{_tab_label(platform_id)}采集结果',
      initialdir=str(EXPORT_DIR),
      initialfile=default_name,
      defaultextension='.xlsx',
      filetypes=[('Excel 文件', '*.xlsx')],
    )
    if not save_path:
      return

    try:
      path = export_platform_results(items, platform_id, save_path)
      messagebox.showinfo('导出成功', f'已保存到：\n{path}')
      self.on_status(f'已导出{_tab_label(platform_id)}：{path.name}')
    except Exception as exc:
      messagebox.showerror('导出失败', str(exc))

  def _on_export_all(self) -> None:
    if not self._has_any_results():
      messagebox.showwarning('提示', '没有可导出的数据')
      return

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    default_name = f'采集结果_全部_{timestamp}.xlsx'
    save_path = filedialog.asksaveasfilename(
      title='导出全部平台采集结果',
      initialdir=str(EXPORT_DIR),
      initialfile=default_name,
      defaultextension='.xlsx',
      filetypes=[('Excel 文件', '*.xlsx')],
    )
    if not save_path:
      return

    try:
      path = export_all_platform_results(self.results_by_platform, save_path)
      messagebox.showinfo('导出成功', f'已保存到：\n{path}\n（各平台独立 Sheet）')
      self.on_status(f'已导出全部平台：{path.name}')
    except Exception as exc:
      messagebox.showerror('导出失败', str(exc))
