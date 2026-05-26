"""数据采集面板."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional, Set, Tuple

import customtkinter as ctk

from config import (
  COLLECT_PAGE_TIMEOUT_MAX_SEC,
  COLLECT_PAGE_TIMEOUT_MIN_SEC,
  EXPORT_DIR,
  EXPORT_WARN_ROW_COUNT,
  UI_RESTORE_RENDER_LIMIT,
)
from core.export_schema import normalize_platform_id
from core.result_store import item_from_db_row
from core.models import (
  CollectParams,
  CollectProgress,
  CollectResultItem,
  CollectRowStatus,
  CollectSummary,
)
from core.platforms import (
  get_platform_name,
  list_collectable_platform_ids,
  requires_collect_account,
)
from infra.database import ACCOUNT_STATUS_EXPIRED, Account, Database
from infra.excel import (
  export_all_platform_results_from_db,
  export_platform_results_from_db,
  extract_first_column_links_with_rows,
  extract_links_from_text,
  filter_links_by_row_range,
)
from infra.platform_detect import detect_platform
from ui.layout import add_horizontal_divider
from services.collect import CollectService
from shared.async_runner import run_coro_in_thread, run_in_thread
from ui.widgets import LAYOUT_DEBOUNCE_MS, CollectResultGrid
from ui.theme import (
  BTN_HEIGHT,
  COLOR_ACCENT,
  COLOR_ACCENT_HOVER,
  COLOR_ACCENT_TEXT,
  COLOR_BG,
  COLOR_BORDER,
  COLOR_BORDER_LIGHT,
  SPACE_SM,
  COLOR_ERROR,
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
  font_body,
  font_caption,
)

def _collect_tab_platform_ids() -> List[str]:
  return list_collectable_platform_ids()


def _tab_label(platform_id: str) -> str:
  return get_platform_name(platform_id)


COLLECT_MODULE_ITEMS = [
  {'id': 'single_work', 'label': '单作品采集', 'enabled': True, 'visible': True},
  {'id': 'keyword', 'label': '关键词采集', 'enabled': False, 'visible': False},
  {'id': 'homepage', 'label': '主页采集', 'enabled': False, 'visible': False},
]

MANUAL_LINK_SOURCE = 'manual://links'
LINK_TEXTBOX_WIDTH = 280
LINK_TEXTBOX_HEIGHT = 88
PLATFORM_TAB_MIN_WIDTH = 52
PLATFORM_TAB_MAX_WIDTH = 88
ACTION_ROW_PLATFORM_GAP = 12
LINK_TEXTBOX_PLACEHOLDER = (
  '每行粘贴一个链接，支持多行\n'
  '与 Excel 二选一；有内容时优先使用此处'
)


class CollectPanel(ctk.CTkFrame):
  """数据采集主面板."""

  def __init__(
    self,
    master: ctk.CTk,
    db: Database,
    on_status: Callable[[str], None],
    on_progress_display: Callable[[str], None],
  ) -> None:
    super().__init__(master, fg_color='transparent')
    self.db = db
    self.on_status = on_status
    self.on_progress_display = on_progress_display

    self.collect_service = CollectService(db)
    self.excel_path: Optional[str] = None
    self.results_by_platform: Dict[str, List[CollectResultItem]] = {}
    self.result_grids: Dict[str, CollectResultGrid] = {}
    self._platform_panels: Dict[str, ctk.CTkFrame] = {}
    self._tab_platform_ids: List[str] = []
    self._tab_labels: List[str] = []
    self._tab_buttons: Dict[str, ctk.CTkButton] = {}
    self._active_platform_tab: str = ''
    self._active_module_tab: str = ''
    self._module_tab_buttons: Dict[str, ctk.CTkButton] = {}
    self._module_panels: Dict[str, ctk.CTkFrame] = {}
    self._panel_layout_after_id: Optional[str] = None
    self.is_collecting = False
    self.is_exporting = False
    self._latest_task_id: Optional[int] = None
    self.pick_excel_btn: Optional[ctk.CTkButton] = None
    self._param_entries: List[ctk.CTkEntry] = []
    self._progress_total = 0
    self._progress_current = 0
    self._progress_success = 0
    self._progress_failed = 0
    self._progress_unsupported = 0

    self._build_ui()
    self._restore_session_from_db()

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

  def _on_action_row_configure(self, event=None) -> None:
    if event is not None and event.widget is not self._action_row:
      return
    try:
      total_w = self._action_row.winfo_width()
      if total_w <= 1 or not self._tab_buttons:
        return
      self._action_row.update_idletasks()
      left_w = self._action_buttons_frame.winfo_reqwidth()
      spare = total_w - left_w - ACTION_ROW_PLATFORM_GAP - 8
      tab_count = len(self._tab_buttons)
      per_tab = max(
        PLATFORM_TAB_MIN_WIDTH,
        min(PLATFORM_TAB_MAX_WIDTH, spare // tab_count),
      )
      for button in self._tab_buttons.values():
        button.configure(width=per_tab)
    except Exception:
      pass

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
          fg_color=COLOR_BG,
          hover_color=COLOR_SELECTED,
          text_color=COLOR_TEXT,
          border_width=0,
        )

  def _on_platform_tab_clicked(self, platform_id: str) -> None:
    if platform_id == self._active_platform_tab:
      return
    self._set_active_tab_button(platform_id)
    self._show_platform_tab(platform_id)

  def _set_export_buttons_state(self, enabled: bool) -> None:
    if self.is_collecting or self.is_exporting:
      enabled = False
    state = 'normal' if enabled else 'disabled'
    self.export_current_btn.configure(state=state)
    self.export_all_btn.configure(state=state)

  def _set_input_locked(self, locked: bool) -> None:
    """采集中/导出中锁定参数与输入；模块 Tab、平台 Tab 不锁."""
    entry_state = 'disabled' if locked else 'normal'
    for entry in self._param_entries:
      entry.configure(state=entry_state)
    if self.pick_excel_btn is not None:
      self.pick_excel_btn.configure(state=entry_state)
    if locked:
      self.link_textbox.configure(state='disabled')
    else:
      self.link_textbox.configure(state='normal')
      if self._link_textbox_placeholder_active:
        self._show_link_textbox_placeholder()

  def _refresh_workflow_buttons(self) -> None:
    busy = self.is_collecting or self.is_exporting
    if busy:
      self.start_btn.configure(state='disabled')
    else:
      self.start_btn.configure(state='normal')
    if self.is_collecting:
      self.stop_btn.configure(state='normal')
    else:
      self.stop_btn.configure(state='disabled')
    can_export = (
      not busy
      and self._latest_task_id is not None
      and self.db.count_results_with_payload(self._latest_task_id) > 0
    )
    self._set_export_buttons_state(can_export)
    self._set_input_locked(busy)

  def _get_latest_task_id(self) -> Optional[int]:
    if self._latest_task_id is not None:
      return self._latest_task_id
    task = self.db.get_latest_task()
    if task is None:
      return None
    self._latest_task_id = task.id
    return task.id

  def _restore_session_from_db(self) -> None:
    task = self.db.get_latest_task()
    if task is None:
      return
    self._latest_task_id = task.id
    total_payload = self.db.count_results_with_payload(task.id)
    if total_payload <= 0:
      return

    items_by_platform: Dict[str, List[CollectResultItem]] = {
      pid: [] for pid in self._tab_platform_ids
    }
    for db_row in self.db.iter_collect_results(task.id):
      item = item_from_db_row(db_row)
      if item is None:
        continue
      platform_id = self._resolve_platform_id(item)
      if platform_id not in items_by_platform:
        items_by_platform[platform_id] = []
      items_by_platform[platform_id].append(item)

    for platform_id in self._tab_platform_ids:
      items = items_by_platform.get(platform_id, [])
      self.results_by_platform[platform_id] = items
      grid = self.result_grids.get(platform_id)
      if grid is None:
        continue
      grid.clear()
      if not items:
        continue
      render_items = items
      if len(items) > UI_RESTORE_RENDER_LIMIT:
        render_items = items[-UI_RESTORE_RENDER_LIMIT:]
      for index, item in enumerate(render_items, start=1):
        grid.add_row(item, index)
      if len(items) > len(render_items):
        grid.set_total_display(len(items), len(render_items))

    self._progress_total = task.total
    self._progress_current = total_payload
    self._progress_success = 0
    self._progress_failed = 0
    self._progress_unsupported = 0
    for items in items_by_platform.values():
      for item in items:
        self._record_result_status(item.status)
    self._refresh_progress_display()
    self._refresh_workflow_buttons()
    self.on_status(f'已恢复上次采集 {total_payload} 条，可直接导出')

  def _add_param_field(
    self,
    parent: ctk.CTkFrame,
    label: str,
    default: str,
    width: int = 56,
  ) -> ctk.CTkEntry:
    wrap = ctk.CTkFrame(parent, fg_color='transparent')
    wrap.pack(side='left', padx=(0, 8))
    ctk.CTkLabel(
      wrap,
      text=label,
      font=font_caption(),
      text_color=COLOR_TEXT,
      anchor='w',
    ).pack(side='left', padx=(0, 4))
    entry = ctk.CTkEntry(wrap, width=width, height=BTN_HEIGHT - 4)
    entry.pack(side='left')
    entry.insert(0, default)
    self._param_entries.append(entry)
    return entry

  def _set_active_module_button(self, module_id: str) -> None:
    self._active_module_tab = module_id
    for mid, button in self._module_tab_buttons.items():
      item = next((x for x in COLLECT_MODULE_ITEMS if x['id'] == mid), None)
      is_enabled = bool(item and item.get('enabled'))
      if mid == module_id:
        button.configure(
          fg_color=COLOR_ACCENT,
          hover_color=COLOR_ACCENT_HOVER,
          text_color=COLOR_ACCENT_TEXT,
          border_width=0,
        )
      elif is_enabled:
        button.configure(
          fg_color=COLOR_BG,
          hover_color=COLOR_SELECTED,
          text_color=COLOR_TEXT,
          border_width=0,
        )
      else:
        button.configure(
          fg_color=COLOR_BG,
          hover_color=COLOR_BG,
          text_color=COLOR_TEXT_DIM,
          border_width=0,
        )

  def _show_module_panel(self, module_id: str) -> None:
    for mid, panel in self._module_panels.items():
      if mid == module_id:
        panel.grid(row=0, column=0, sticky='nsew')
      else:
        panel.grid_remove()

  def _on_module_tab_clicked(self, module_id: str, enabled: bool) -> None:
    if not enabled:
      label = next((x['label'] for x in COLLECT_MODULE_ITEMS if x['id'] == module_id), module_id)
      messagebox.showinfo('提示', f'「{label}」功能开发中，敬请期待！')
      return
    if module_id == self._active_module_tab:
      return
    self._set_active_module_button(module_id)
    self._show_module_panel(module_id)

  def _build_module_tab_bar(self, parent: ctk.CTkFrame) -> None:
    tab_bar_inner = ctk.CTkFrame(parent, fg_color='transparent')
    tab_bar_inner.grid(row=0, column=0, sticky='ew')
    for col_index in range(len(COLLECT_MODULE_ITEMS)):
      tab_bar_inner.grid_columnconfigure(col_index, weight=1)

    tab_font = font_body(weight='bold')
    tab_height = TAB_BAR_HEIGHT - 8
    for col_index, item in enumerate(COLLECT_MODULE_ITEMS):
      if not item.get('visible', True):
        spacer = ctk.CTkFrame(
          tab_bar_inner,
          fg_color=COLOR_BG,
          height=tab_height,
          corner_radius=0,
        )
        spacer.grid(row=0, column=col_index, sticky='ew', padx=(0, 4))
        spacer.grid_propagate(False)
        continue

      button = ctk.CTkButton(
        tab_bar_inner,
        text=item['label'],
        height=tab_height,
        corner_radius=6,
        fg_color=COLOR_BG,
        hover_color=COLOR_SELECTED if item['enabled'] else COLOR_BG,
        text_color=COLOR_TEXT if item['enabled'] else COLOR_TEXT_DIM,
        border_width=0,
        font=tab_font,
        command=lambda mid=item['id'], en=item['enabled']: self._on_module_tab_clicked(mid, en),
      )
      button.grid(row=0, column=col_index, sticky='ew', padx=(0, 4))
      self._module_tab_buttons[item['id']] = button

    first_enabled = next((x['id'] for x in COLLECT_MODULE_ITEMS if x['enabled']), 'single_work')
    self._set_active_module_button(first_enabled)
    add_horizontal_divider(parent, row=1)

  def _build_coming_soon_panel(self, parent: ctk.CTkFrame, title: str) -> ctk.CTkFrame:
    panel = ctk.CTkFrame(parent, fg_color='transparent')
    panel.grid_rowconfigure(0, weight=1)
    panel.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
      panel,
      text=f'{title}功能开发中，敬请期待',
      font=font_body(),
      text_color=COLOR_TEXT_DIM,
    ).grid(row=0, column=0)
    return panel

  def _build_ui(self) -> None:
    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(0, weight=1)

    shell = ctk.CTkFrame(self, fg_color='transparent')
    shell.grid(row=0, column=0, sticky='nsew')
    shell.grid_columnconfigure(0, weight=1)
    shell.grid_rowconfigure(2, weight=1)

    self._build_module_tab_bar(shell)

    self.module_content = ctk.CTkFrame(shell, fg_color='transparent')
    self.module_content.grid(row=2, column=0, sticky='nsew')
    self.module_content.grid_columnconfigure(0, weight=1)
    self.module_content.grid_rowconfigure(0, weight=1)

    self.single_work_panel = ctk.CTkFrame(self.module_content, fg_color='transparent')
    self.single_work_panel.grid_columnconfigure(0, weight=1)
    self.single_work_panel.grid_rowconfigure(6, weight=1)

    keyword_item = next(x for x in COLLECT_MODULE_ITEMS if x['id'] == 'keyword')
    homepage_item = next(x for x in COLLECT_MODULE_ITEMS if x['id'] == 'homepage')
    self.keyword_panel = self._build_coming_soon_panel(
      self.module_content, keyword_item['label'],
    )
    self.homepage_panel = self._build_coming_soon_panel(
      self.module_content, homepage_item['label'],
    )

    self._module_panels = {
      'single_work': self.single_work_panel,
      'keyword': self.keyword_panel,
      'homepage': self.homepage_panel,
    }
    self._show_module_panel('single_work')

    self._build_single_work_ui(self.single_work_panel)

    toplevel = self.winfo_toplevel()
    toplevel.bind('<Configure>', self._on_result_toplevel_configure, add='+')
    self.bind('<Destroy>', self._on_panel_destroy, add='+')

  def _build_single_work_ui(self, parent: ctk.CTkFrame) -> None:
    defaults = CollectParams.defaults()

    params_row = ctk.CTkFrame(parent, fg_color='transparent')
    params_row.grid(row=0, column=0, sticky='ew')
    self.min_delay_entry = self._add_param_field(
      params_row, '最小延迟', str(defaults.min_delay_sec), width=48,
    )
    self.max_delay_entry = self._add_param_field(
      params_row, '最大延迟', str(defaults.max_delay_sec), width=48,
    )
    self.retry_count_entry = self._add_param_field(
      params_row, '重试次数', str(defaults.retry_count), width=44,
    )
    self.page_timeout_entry = self._add_param_field(
      params_row, '页面超时(秒)', str(defaults.page_timeout_sec), width=52,
    )
    self.start_row_entry = self._add_param_field(
      params_row, '起始编号', str(defaults.start_row), width=44,
    )
    self.end_row_entry = self._add_param_field(
      params_row, '终止编号', str(defaults.end_row), width=44,
    )

    add_horizontal_divider(parent, row=1, pady=(SPACE_SM, SPACE_SM))

    excel_row = ctk.CTkFrame(parent, fg_color='transparent')
    excel_row.grid(row=2, column=0, sticky='ew')

    ctk.CTkLabel(
      excel_row,
      text='Excel 文件',
      width=64,
      anchor='w',
      font=font_caption(weight='bold'),
      text_color=COLOR_TEXT,
    ).pack(side='left', padx=(0, 8))

    self.pick_excel_btn = ctk.CTkButton(
      excel_row,
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
    )
    self.pick_excel_btn.pack(side='left', padx=(0, 12))

    self.link_textbox = ctk.CTkTextbox(
      excel_row,
      width=LINK_TEXTBOX_WIDTH,
      height=LINK_TEXTBOX_HEIGHT,
      wrap='none',
      fg_color=COLOR_SURFACE,
      border_color=COLOR_BORDER_LIGHT,
      border_width=1,
      corner_radius=RADIUS_BTN,
      font=font_caption(),
      text_color=COLOR_TEXT,
    )
    self.link_textbox.pack(side='left', fill='both', expand=True)
    self._link_textbox_placeholder_active = False
    self._bind_link_textbox_placeholder()
    self._show_link_textbox_placeholder()

    add_horizontal_divider(parent, row=3, pady=(SPACE_SM, SPACE_SM))

    self._action_row = ctk.CTkFrame(parent, fg_color='transparent')
    self._action_row.grid(row=4, column=0, sticky='ew')
    self._action_row.grid_columnconfigure(0, weight=0)
    self._action_row.grid_columnconfigure(1, weight=1)
    self._action_row.grid_columnconfigure(2, weight=0)

    self._action_buttons_frame = ctk.CTkFrame(self._action_row, fg_color='transparent')
    self._action_buttons_frame.grid(row=0, column=0, sticky='w')

    self.start_btn = ctk.CTkButton(
      self._action_buttons_frame,
      text='开始采集',
      width=100,
      height=BTN_HEIGHT,
      corner_radius=RADIUS_BTN,
      fg_color=COLOR_ACCENT,
      hover_color=COLOR_ACCENT_HOVER,
      text_color=COLOR_ACCENT_TEXT,
      command=self._on_start_collect,
    )
    self.start_btn.pack(side='left', padx=(0, 6))

    self.stop_btn = ctk.CTkButton(
      self._action_buttons_frame,
      text='停止采集',
      width=100,
      height=BTN_HEIGHT,
      corner_radius=RADIUS_BTN,
      fg_color=COLOR_ERROR,
      hover_color=COLOR_ERROR,
      text_color=COLOR_ACCENT_TEXT,
      state='disabled',
      command=self._on_stop_collect,
    )
    self.stop_btn.pack(side='left', padx=(0, 6))

    self.export_current_btn = ctk.CTkButton(
      self._action_buttons_frame,
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
      self._action_buttons_frame,
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

    self._platform_tab_bar = ctk.CTkFrame(self._action_row, fg_color='transparent')
    self._platform_tab_bar.grid(
      row=0,
      column=2,
      sticky='e',
      padx=(ACTION_ROW_PLATFORM_GAP, 0),
    )
    self._tab_platform_ids = _collect_tab_platform_ids()
    self._tab_labels = [_tab_label(platform_id) for platform_id in self._tab_platform_ids]
    self._tab_buttons.clear()

    tab_font = font_body(weight='bold')
    tab_height = TAB_BAR_HEIGHT - 8
    for col_index, platform_id in enumerate(self._tab_platform_ids):
      button = ctk.CTkButton(
        self._platform_tab_bar,
        text=self._tab_labels[col_index],
        width=PLATFORM_TAB_MIN_WIDTH,
        height=tab_height,
        corner_radius=6,
        fg_color=COLOR_BG,
        hover_color=COLOR_SELECTED,
        text_color=COLOR_TEXT,
        border_width=0,
        font=tab_font,
        command=lambda pid=platform_id: self._on_platform_tab_clicked(pid),
      )
      button.grid(row=0, column=col_index, padx=(4, 0))
      self._tab_buttons[platform_id] = button

    if self._tab_platform_ids:
      self._set_active_tab_button(self._tab_platform_ids[0])

    self._action_row.bind('<Configure>', self._on_action_row_configure, add='+')
    self.after_idle(self._on_action_row_configure)

    add_horizontal_divider(parent, row=5)

    results_section = ctk.CTkFrame(parent, fg_color='transparent')
    results_section.grid(row=6, column=0, sticky='nsew')
    results_section.grid_rowconfigure(0, weight=1)
    results_section.grid_columnconfigure(0, weight=1)

    self.result_content = ctk.CTkFrame(results_section, fg_color='transparent')
    self.result_content.grid(row=0, column=0, sticky='nsew')
    self.result_content.grid_rowconfigure(0, weight=1)
    self.result_content.grid_columnconfigure(0, weight=1)
    self._build_result_tabs()

  def _resolve_latest_accounts(self, links: List[str]) -> Dict[str, Account]:
    """按链接涉及的平台，自动选用各平台最新可采集账号."""
    required = self._get_required_collect_platforms(links)
    return self.db.get_latest_collectable_account_map(required)

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

    account_map = self.db.get_latest_collectable_account_map(required)
    missing: List[str] = []
    for platform_id in sorted(required):
      if not requires_collect_account(platform_id):
        continue
      if platform_id not in account_map:
        missing.append(get_platform_name(platform_id))

    if not missing:
      return None

    names = '、'.join(missing)
    return (
      f'Excel 中包含以下平台的可采集链接，但暂无可用账号：{names}\n'
      f'请到账号管理添加对应平台账号并完成登录。'
    )

  def _parse_collect_params(self) -> Optional[CollectParams]:
    try:
      min_delay = float(self.min_delay_entry.get().strip())
      max_delay = float(self.max_delay_entry.get().strip())
      retry_count = int(self.retry_count_entry.get().strip())
      page_timeout_sec = int(self.page_timeout_entry.get().strip())
      start_row = int(self.start_row_entry.get().strip())
      end_row = int(self.end_row_entry.get().strip())
    except ValueError:
      messagebox.showwarning('参数错误', '请填写有效的数字参数')
      return None

    if min_delay < 0 or max_delay < 0:
      messagebox.showwarning('参数错误', '延迟不能为负数')
      return None
    if min_delay > max_delay:
      messagebox.showwarning('参数错误', '最小延迟不能大于最大延迟')
      return None
    if retry_count < 0:
      messagebox.showwarning('参数错误', '重试次数不能为负数')
      return None
    if page_timeout_sec < COLLECT_PAGE_TIMEOUT_MIN_SEC or page_timeout_sec > COLLECT_PAGE_TIMEOUT_MAX_SEC:
      messagebox.showwarning(
        '参数错误',
        f'页面超时请在 {COLLECT_PAGE_TIMEOUT_MIN_SEC}～{COLLECT_PAGE_TIMEOUT_MAX_SEC} 秒之间',
      )
      return None
    if start_row < 1:
      messagebox.showwarning('参数错误', '起始编号不能小于 1')
      return None
    if end_row != 0 and end_row < start_row:
      messagebox.showwarning('参数错误', '终止编号为 0 表示到最后，否则不能小于起始编号')
      return None

    return CollectParams(
      min_delay_sec=min_delay,
      max_delay_sec=max_delay,
      retry_count=retry_count,
      page_timeout_sec=page_timeout_sec,
      start_row=start_row,
      end_row=end_row,
    )

  def _on_pick_excel(self) -> None:
    path = filedialog.askopenfilename(
      title='选择 Excel 文件',
      filetypes=[('Excel 文件', '*.xlsx'), ('所有文件', '*.*')],
    )
    if not path:
      return

    self.excel_path = path

  def _bind_link_textbox_placeholder(self) -> None:
    self.link_textbox.bind('<FocusIn>', self._on_link_textbox_focus_in)
    self.link_textbox.bind('<FocusOut>', self._on_link_textbox_focus_out)

  def _show_link_textbox_placeholder(self) -> None:
    self._link_textbox_placeholder_active = True
    self.link_textbox.delete('1.0', 'end')
    self.link_textbox.insert('1.0', LINK_TEXTBOX_PLACEHOLDER)
    self.link_textbox.configure(text_color=COLOR_TEXT_DIM)

  def _on_link_textbox_focus_in(self, _event=None) -> None:
    if not self._link_textbox_placeholder_active:
      return
    self.link_textbox.delete('1.0', 'end')
    self.link_textbox.configure(text_color=COLOR_TEXT)
    self._link_textbox_placeholder_active = False

  def _on_link_textbox_focus_out(self, _event=None) -> None:
    if self.link_textbox.get('1.0', 'end').strip():
      return
    self._show_link_textbox_placeholder()

  def _get_link_textbox_raw(self) -> str:
    if self._link_textbox_placeholder_active:
      return ''
    return self.link_textbox.get('1.0', 'end').strip()

  def _resolve_collect_links(
    self,
    params: CollectParams,
  ) -> Optional[Tuple[List[str], str]]:
    """解析采集链接：输入框优先，否则 Excel。返回 (links, source_file)."""
    raw_text = self._get_link_textbox_raw()
    if raw_text:
      row_links = extract_links_from_text(raw_text)
      links = filter_links_by_row_range(row_links, params.start_row, params.end_row)
      if not links:
        messagebox.showwarning('提示', '输入框在该行号范围内没有有效链接')
        return None
      return links, MANUAL_LINK_SOURCE

    if not self.excel_path:
      messagebox.showwarning('提示', '请选择 Excel 文件，或在右侧输入框粘贴链接')
      return None

    try:
      row_links = extract_first_column_links_with_rows(self.excel_path)
    except Exception as exc:
      messagebox.showerror('错误', f'读取 Excel 失败：{exc}')
      return None

    links = filter_links_by_row_range(row_links, params.start_row, params.end_row)
    if not links:
      messagebox.showwarning('提示', '该行号范围内 A 列没有有效链接')
      return None
    return links, self.excel_path

  def _reset_progress_counters(self, total: int) -> None:
    self._progress_total = total
    self._progress_current = 0
    self._progress_success = 0
    self._progress_failed = 0
    self._progress_unsupported = 0

  def _record_result_status(self, status: CollectRowStatus) -> None:
    if status == CollectRowStatus.SUCCESS:
      self._progress_success += 1
    elif status == CollectRowStatus.UNSUPPORTED:
      self._progress_unsupported += 1
    else:
      self._progress_failed += 1

  def _refresh_progress_display(self) -> None:
    if self._progress_total <= 0:
      return
    text = (
      f'{self._progress_current}/{self._progress_total} · '
      f'成功 {self._progress_success} · 失败 {self._progress_failed} · '
      f'不支持 {self._progress_unsupported}'
    )
    self.on_progress_display(text)

  def restore_progress_display(self) -> None:
    """切回数据采集时恢复右侧进度统计."""
    if self._progress_total > 0:
      self._refresh_progress_display()

  def _on_start_collect(self) -> None:
    if self.is_collecting:
      return

    params = self._parse_collect_params()
    if params is None:
      return

    resolved = self._resolve_collect_links(params)
    if resolved is None:
      return
    links, source_file = resolved

    validation_error = self._validate_before_collect(links)
    if validation_error:
      messagebox.showwarning('无法开始采集', validation_error)
      return

    account_by_platform = self._resolve_latest_accounts(links)

    self._clear_all_results()

    self.is_collecting = True
    self._latest_task_id = None
    self._refresh_workflow_buttons()
    self._reset_progress_counters(len(links))
    self._refresh_progress_display()
    self.on_status(f'开始采集，共 {len(links)} 条链接')

    service = self.collect_service

    def on_progress(progress: CollectProgress) -> None:
      def handle_progress() -> None:
        self._progress_current = progress.current
        self._progress_total = progress.total
        self.on_status('正在采集')
        self._refresh_progress_display()

      self.after(0, handle_progress)

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
        source_file,
        params,
        on_progress=on_progress,
        on_row=on_row,
      ),
      on_complete,
      on_error,
    )

  def _on_stop_collect(self) -> None:
    self.collect_service.cancel()
    self.on_status('正在停止采集...')

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
    self._record_result_status(item.status)
    self._refresh_progress_display()

  def _on_collect_finished(self, summary: CollectSummary) -> None:
    self.is_collecting = False
    if summary.task_id is not None:
      self._latest_task_id = summary.task_id
    self._refresh_workflow_buttons()

    if summary.expired_account_ids:
      for account_id in summary.expired_account_ids:
        self.db.update_account(account_id, status=ACCOUNT_STATUS_EXPIRED)
      messagebox.showwarning('登录过期', '部分账号登录已过期，请到账号管理重新登录')

    msg = '采集结束（已停止）' if summary.cancelled else '采集结束'
    self.on_status(msg)
    self._progress_total = summary.total
    self._progress_current = summary.total
    self._progress_success = summary.success_count
    self._progress_failed = summary.failed_count
    self._progress_unsupported = summary.unsupported_count
    self._refresh_progress_display()

  def _on_collect_error(self, exc: Exception) -> None:
    self.is_collecting = False
    self._refresh_workflow_buttons()
    messagebox.showerror('采集失败', str(exc))
    self.on_status(f'采集失败：{exc}')

  def _on_export_current(self) -> None:
    if self.is_collecting or self.is_exporting:
      return
    platform_id = self._get_current_tab_platform_id()
    task_id = self._get_latest_task_id()
    if task_id is None:
      messagebox.showwarning('提示', '没有可导出的采集批次')
      return
    row_count = self.db.count_exportable_results(task_id, platform_id)
    if row_count <= 0:
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
    self._run_export_in_background(
      lambda: export_platform_results_from_db(self.db, task_id, platform_id, save_path),
      success_title='导出成功',
      success_detail=f'已保存到：\n{save_path}',
      status_ok=f'已导出{_tab_label(platform_id)}：{Path(save_path).name}',
    )

  def _on_export_all(self) -> None:
    if self.is_collecting or self.is_exporting:
      return
    task_id = self._get_latest_task_id()
    if task_id is None:
      messagebox.showwarning('提示', '没有可导出的采集批次')
      return
    row_count = self.db.count_exportable_results(task_id)
    if row_count <= 0:
      messagebox.showwarning('提示', '没有可导出的数据')
      return
    if row_count >= EXPORT_WARN_ROW_COUNT:
      if not messagebox.askyesno(
        '数据量较大',
        f'当前共 {row_count} 条，导出可能需要一些时间。\n建议可先分平台导出。\n\n是否继续导出全部？',
      ):
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
    self._run_export_in_background(
      lambda: export_all_platform_results_from_db(self.db, task_id, save_path),
      success_title='导出成功',
      success_detail=f'已保存到：\n{save_path}\n（各平台独立 Sheet）',
      status_ok=f'已导出全部平台：{Path(save_path).name}',
    )

  def _run_export_in_background(
    self,
    export_fn: Callable[[], Path],
    *,
    success_title: str,
    success_detail: str,
    status_ok: str,
  ) -> None:
    self.is_exporting = True
    self._refresh_workflow_buttons()
    self.on_status('正在导出，请稍候...')

    def on_complete(path: Path) -> None:
      def handle_ok() -> None:
        self.is_exporting = False
        self._refresh_workflow_buttons()
        messagebox.showinfo(success_title, success_detail)
        self.on_status(status_ok)

      self.after(0, handle_ok)

    def on_error(exc: Exception) -> None:
      def handle_err() -> None:
        self.is_exporting = False
        self._refresh_workflow_buttons()
        messagebox.showerror('导出失败', str(exc))
        self.on_status(f'导出失败：{exc}')

      self.after(0, handle_err)

    run_in_thread(export_fn, on_complete, on_error)
