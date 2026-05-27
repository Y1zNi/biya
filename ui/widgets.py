"""轻量 UI 辅助（保持 CustomTkinter 统一风格）."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import customtkinter as ctk

from core.export_schema import TableColumn, get_table_columns, item_to_export_cells, metric_column_indices
from core.models import CollectResultItem
from ui.theme import (
  BTN_HEIGHT,
  COLOR_ACCENT,
  COLOR_ACCENT_HOVER,
  COLOR_ACCENT_TEXT,
  COLOR_BORDER,
  COLOR_BORDER_LIGHT,
  COLOR_BG,
  COLOR_ERROR,
  COLOR_ERROR_HOVER,
  COLOR_PANEL,
  COLOR_TABLE_HEADER,
  COLOR_SUCCESS,
  COLOR_SURFACE,
  COLOR_TEXT,
  COLOR_TEXT_DIM,
  RADIUS_BTN,
  font_body,
  font_caption,
  font_section,
  get_font,
  TABLE_HEADER_HEIGHT,
  TABLE_ROW_HEIGHT,
  TABLE_ROW_RADIUS,
)

LINK_ELLIPSIS_THRESHOLD = 40
LAYOUT_DEBOUNCE_MS = 80
HEADER_LABEL_PAD_X = 6
METRIC_COLUMN_MIN = 48
TEXT_COLUMN_MIN = 56
LINK_COLUMN_MIN = 72
STATUS_COLUMN_MIN = 72
ID_COLUMN_MIN = 64

_HEADER_FONT = None
_BODY_FONT = None


def _header_font() -> ctk.CTkFont:
  global _HEADER_FONT
  if _HEADER_FONT is None:
    _HEADER_FONT = font_body(weight='bold')
  return _HEADER_FONT


def _body_font() -> ctk.CTkFont:
  global _BODY_FONT
  if _BODY_FONT is None:
    _BODY_FONT = font_body()
  return _BODY_FONT


def _table_total_width(columns: List[TableColumn]) -> int:
  return sum(width for _, width, _ in columns)


def _label_anchor(anchor: str) -> str:
  return 'center' if anchor == 'center' else 'w'


def _column_min_width(title: str, anchor: str) -> int:
  if title == '链接':
    return LINK_COLUMN_MIN
  if title == '状态':
    return STATUS_COLUMN_MIN
  if title in ('小红书id', '作者id', '小红书号'):
    return ID_COLUMN_MIN
  if title in ('平台昵称', '发布日期'):
    return TEXT_COLUMN_MIN
  if anchor == 'center':
    return METRIC_COLUMN_MIN
  return TEXT_COLUMN_MIN


def scale_columns_to_viewport(columns: List[TableColumn], viewport_w: int) -> List[TableColumn]:
  """按当前视口等比分配列宽，使各列宽度之和等于 viewport_w."""
  if viewport_w <= 1 or not columns:
    return list(columns)

  base_total = _table_total_width(columns)
  if base_total <= 0:
    return list(columns)

  mins = [_column_min_width(title, anchor) for title, _, anchor in columns]
  widths = [
    max(int(col_w * viewport_w / base_total), min_w)
    for (_, col_w, _), min_w in zip(columns, mins)
  ]

  total = sum(widths)
  while total > viewport_w:
    reducible = [
      (index, widths[index] - mins[index])
      for index in range(len(widths))
      if widths[index] > mins[index]
    ]
    if not reducible:
      break
    pick = max(reducible, key=lambda item: item[1])[0]
    widths[pick] -= 1
    total -= 1

  index = 0
  while total < viewport_w:
    widths[index % len(widths)] += 1
    total += 1
    index += 1

  return [(columns[i][0], widths[i], columns[i][2]) for i in range(len(columns))]


def _columns_signature(columns: List[TableColumn]) -> Tuple[Tuple[str, int, str], ...]:
  return tuple((title, width, anchor) for title, width, anchor in columns)


class CollectResultGrid(ctk.CTkFrame):
  """采集结果表：与账号管理表一致的表头 + CTkScrollableFrame + 卡片行."""

  def __init__(self, master, platform_id: str, *, empty_text: str = '') -> None:
    super().__init__(master, fg_color='transparent')
    self.platform_id = platform_id
    self._base_columns = get_table_columns(platform_id)
    self._effective_columns: List[TableColumn] = list(self._base_columns)
    self.table_total_width = _table_total_width(self._base_columns)
    self._layout_cache: Optional[Tuple[int, Tuple[Tuple[str, int, str], ...]]] = None
    self._layout_after_id: Optional[str] = None
    self.metric_indices = frozenset(metric_column_indices(platform_id))
    self.status_col_index = len(self._base_columns) - 1
    self._empty_text = empty_text or (
      '该平台采集结果将显示在这里\n选择 Excel（A 列放链接）后点击「开始采集」'
    )
    self._tooltip: Optional[ctk.CTkToplevel] = None
    self._row_records: List[Tuple[CollectResultItem, int]] = []
    self._footer_text: Optional[str] = None
    self._is_empty = True

    self.grid_rowconfigure(0, weight=1)
    self.grid_columnconfigure(0, weight=1)

    self.body_wrap = ctk.CTkFrame(self, fg_color='transparent', corner_radius=0)
    self.body_wrap.pack(fill='both', expand=True)

    self.header = ctk.CTkFrame(
      self.body_wrap,
      fg_color=COLOR_TABLE_HEADER,
      corner_radius=0,
      height=TABLE_HEADER_HEIGHT,
    )
    self.header.pack(fill='x', pady=(0, 0))
    self.header.pack_propagate(False)

    self.table_scroll = ctk.CTkScrollableFrame(
      self.body_wrap,
      fg_color=COLOR_BG,
      corner_radius=0,
    )
    self.table_scroll.pack(fill='both', expand=True)

    self.empty_label = ctk.CTkLabel(
      self.table_scroll,
      text=self._empty_text,
      font=font_section(),
      text_color=COLOR_TEXT_DIM,
      justify='center',
    )
    self.empty_label.pack(pady=60)

    self.bind('<Configure>', self._on_viewport_configure)
    self.body_wrap.bind('<Configure>', self._on_viewport_configure)
    self.bind('<Map>', self._on_viewport_configure)
    self.bind('<Destroy>', self._on_destroy, add='+')

    self.after_idle(self.refresh_layout)

  def _is_alive(self) -> bool:
    try:
      return bool(self.winfo_exists())
    except Exception:
      return False

  def _cleanup_layout_timer(self) -> None:
    if self._layout_after_id is None:
      return
    try:
      self.after_cancel(self._layout_after_id)
    except Exception:
      pass
    self._layout_after_id = None

  def _on_destroy(self, event=None) -> None:
    if event is not None and event.widget is not self:
      return
    self._cleanup_layout_timer()

  def destroy(self) -> None:
    self._cleanup_layout_timer()
    super().destroy()

  def refresh_layout(self) -> None:
    """在 Tab 显示或窗口尺寸变化后重新计算列宽."""
    self._schedule_layout()

  def _schedule_layout(self) -> None:
    if not self._is_alive():
      return
    self._cleanup_layout_timer()
    try:
      self._layout_after_id = self.after(LAYOUT_DEBOUNCE_MS, self._run_scheduled_layout)
    except Exception:
      self._layout_after_id = None

  def _run_scheduled_layout(self) -> None:
    self._layout_after_id = None
    if not self._is_alive():
      return
    self._apply_layout()

  def _viewport_width(self) -> int:
    width = self.header.winfo_width()
    if width <= 1:
      width = self.body_wrap.winfo_width()
    if width <= 1:
      width = self.winfo_width()
    if width <= 1:
      return 0
    pad_total = HEADER_LABEL_PAD_X * 2 * len(self._base_columns)
    return max(width - pad_total, 1)

  def _apply_layout(self) -> None:
    if not self._is_alive():
      return
    viewport_w = self._viewport_width()
    if viewport_w <= 1:
      return

    new_columns = scale_columns_to_viewport(self._base_columns, viewport_w)
    cache_key = (viewport_w, _columns_signature(new_columns))
    if cache_key == self._layout_cache:
      return

    self._layout_cache = cache_key
    self._effective_columns = new_columns
    self._rebuild_header()
    self._rebuild_data_rows()

  def _on_viewport_configure(self, _event=None) -> None:
    if not self._is_alive():
      return
    self._schedule_layout()

  def _clear_header_labels(self) -> None:
    for widget in self.header.winfo_children():
      widget.destroy()

  def _rebuild_header(self) -> None:
    self._clear_header_labels()
    for title, col_width, _anchor in self._effective_columns:
      ctk.CTkLabel(
        self.header,
        text=title,
        width=col_width,
        anchor='w',
        font=_header_font(),
        text_color=COLOR_TEXT_DIM,
      ).pack(side='left', padx=HEADER_LABEL_PAD_X, pady=6)

  def _clear_table_scroll(self) -> None:
    for widget in self.table_scroll.winfo_children():
      widget.destroy()

  def _rebuild_data_rows(self) -> None:
    self._clear_table_scroll()
    if not self._row_records:
      self._show_empty_state()
      self._update_footer()
      return

    self._is_empty = False
    for item, row_index in self._row_records:
      self._append_row_widget(item, row_index)
    self._update_footer()

  def _show_empty_state(self) -> None:
    self._is_empty = True
    self.empty_label = ctk.CTkLabel(
      self.table_scroll,
      text=self._empty_text,
      font=font_section(),
      text_color=COLOR_TEXT_DIM,
      justify='center',
    )
    self.empty_label.pack(pady=60)

  def _update_footer(self) -> None:
    pass

  def set_footer_text(self, text: str) -> None:
    pass

  def clear(self) -> None:
    self._row_records.clear()
    self._footer_text = None
    self._clear_table_scroll()
    self._is_empty = True
    self._show_empty_state()
    self._update_footer()

  def load_page(self, items: List[CollectResultItem], *, global_offset: int = 0) -> None:
    """加载当前页数据（先清空再渲染，最多一页行数）."""
    self._row_records.clear()
    self._clear_table_scroll()
    if not items:
      self._is_empty = True
      self._show_empty_state()
      return

    self._is_empty = False
    for index, item in enumerate(items):
      row_index = global_offset + index + 1
      self._row_records.append((item, row_index))
      self._append_row_widget(item, row_index)

  def add_row(self, item: CollectResultItem, row_index: int) -> None:
    if self._is_empty:
      self._clear_table_scroll()
      self._is_empty = False

    self._row_records.append((item, row_index))
    self._append_row_widget(item, row_index)
    self._update_footer()

  def _append_row_widget(self, item: CollectResultItem, row_index: int) -> None:
    values = item_to_export_cells(item, self.platform_id)
    status_text = str(values[self.status_col_index])

    row = ctk.CTkFrame(
      self.table_scroll,
      fg_color=COLOR_SURFACE,
      corner_radius=TABLE_ROW_RADIUS,
      height=TABLE_ROW_HEIGHT,
    )
    row.pack(fill='x', pady=2, padx=4)
    row.pack_propagate(False)

    full_link = ''
    for col_index, ((_, col_width, anchor), value) in enumerate(zip(self._effective_columns, values)):
      raw = str(value)
      display = self._format_cell(col_index, raw)
      text_color = self._status_color(status_text, col_index, display)
      if col_index == 0:
        full_link = raw

      label = ctk.CTkLabel(
        row,
        text=display,
        width=col_width,
        anchor=_label_anchor(anchor),
        font=_body_font(),
        text_color=text_color,
      )
      label.pack(side='left', padx=4)

      if col_index == 0 and len(full_link) > LINK_ELLIPSIS_THRESHOLD:
        self._bind_link_tooltip(label, full_link)

  def _format_cell(self, col_index: int, text: str) -> str:
    if col_index != 0:
      return text
    if len(text) <= LINK_ELLIPSIS_THRESHOLD:
      return text
    return f'{text[:24]}...{text[-12:]}'

  def _status_color(self, status_text: str, col_index: int, display: str) -> str:
    if col_index == self.status_col_index:
      if status_text.startswith('成功'):
        return COLOR_SUCCESS
      if '过期' in status_text or status_text.startswith('失败'):
        return COLOR_ERROR
      if status_text.startswith('暂不支持'):
        return COLOR_TEXT_DIM
    if col_index in self.metric_indices and display == '-':
      return COLOR_TEXT_DIM
    return COLOR_TEXT

  def _bind_link_tooltip(self, widget: ctk.CTkLabel, full_text: str) -> None:
    def hide(_event=None) -> None:
      if self._tooltip is not None:
        try:
          self._tooltip.destroy()
        except Exception:
          pass
        self._tooltip = None

    def show(_event=None) -> None:
      hide()
      tip = ctk.CTkToplevel(self)
      tip.wm_overrideredirect(True)
      tip.attributes('-topmost', True)
      tip.configure(fg_color=COLOR_TEXT)
      tip.geometry(f'+{widget.winfo_rootx()}+{widget.winfo_rooty() + 28}')
      ctk.CTkLabel(
        tip,
        text=full_text,
        font=get_font(11),
        text_color=COLOR_SURFACE,
        wraplength=480,
        justify='left',
      ).pack(padx=10, pady=8)
      self._tooltip = tip
      tip.bind('<Leave>', hide)
      widget.bind('<Leave>', hide, add='+')

    widget.bind('<Enter>', show)


class ResultPagerBar(ctk.CTkFrame):
  """采集结果表分页条."""

  def __init__(
    self,
    master,
    *,
    on_first: Callable[[], None],
    on_prev: Callable[[], None],
    on_next: Callable[[], None],
    on_last: Callable[[], None],
    on_jump: Callable[[], None],
  ) -> None:
    super().__init__(master, fg_color='transparent')

    for label, cmd, width in (
      ('首页', on_first, 44),
      ('上一页', on_prev, 52),
      ('下一页', on_next, 52),
      ('末页', on_last, 44),
    ):
      ctk.CTkButton(
        self,
        text=label,
        width=width,
        height=28,
        corner_radius=RADIUS_BTN,
        fg_color=COLOR_BORDER,
        hover_color=COLOR_BORDER_LIGHT,
        text_color=COLOR_TEXT,
        font=font_caption(),
        command=cmd,
      ).pack(side='left', padx=(0, 4))

    ctk.CTkLabel(self, text='第', font=font_caption(), text_color=COLOR_TEXT_DIM).pack(
      side='left', padx=(8, 2),
    )
    self.page_entry = ctk.CTkEntry(self, width=48, height=28, font=font_caption())
    self.page_entry.pack(side='left')
    self.page_suffix_label = ctk.CTkLabel(
      self,
      text='/ 1 页',
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
    )
    self.page_suffix_label.pack(side='left', padx=(4, 4))

    ctk.CTkButton(
      self,
      text='跳转',
      width=44,
      height=28,
      corner_radius=RADIUS_BTN,
      fg_color=COLOR_BORDER,
      hover_color=COLOR_BORDER_LIGHT,
      text_color=COLOR_TEXT,
      font=font_caption(),
      command=on_jump,
    ).pack(side='left', padx=(0, 8))

    self.summary_label = ctk.CTkLabel(
      self,
      text='共 0 条',
      font=font_caption(),
      text_color=COLOR_TEXT_DIM,
    )
    self.summary_label.pack(side='right', padx=8)

  def update_display(self, total: int, page: int, total_pages: int) -> None:
    total_pages = max(1, total_pages)
    self.summary_label.configure(text=f'共 {total} 条 · 第 {page} / {total_pages} 页')
    self.page_suffix_label.configure(text=f'/ {total_pages} 页')

  def set_page_entry(self, page: int) -> None:
    self.page_entry.delete(0, 'end')
    self.page_entry.insert(0, str(max(1, page)))

  def get_page_entry_value(self) -> int:
    try:
      return max(1, int(self.page_entry.get().strip()))
    except ValueError:
      return 1


def PrimaryButton(master, text: str, command: Optional[Callable] = None, width: int = 110, **kwargs) -> ctk.CTkButton:
  return ctk.CTkButton(
    master,
    text=text,
    width=width,
    height=BTN_HEIGHT,
    corner_radius=RADIUS_BTN,
    fg_color=COLOR_ACCENT,
    hover_color=COLOR_ACCENT_HOVER,
    text_color=COLOR_ACCENT_TEXT,
    command=command,
    **kwargs,
  )


def SecondaryButton(master, text: str, command: Optional[Callable] = None, width: int = 110, **kwargs) -> ctk.CTkButton:
  return ctk.CTkButton(
    master,
    text=text,
    width=width,
    height=BTN_HEIGHT,
    corner_radius=RADIUS_BTN,
    fg_color=COLOR_BORDER,
    hover_color=COLOR_BORDER_LIGHT,
    text_color=COLOR_TEXT,
    command=command,
    **kwargs,
  )


def DangerButton(master, text: str, command: Optional[Callable] = None, width: int = 90, **kwargs) -> ctk.CTkButton:
  return ctk.CTkButton(
    master,
    text=text,
    width=width,
    height=BTN_HEIGHT,
    corner_radius=RADIUS_BTN,
    fg_color=COLOR_ERROR,
    hover_color=COLOR_ERROR_HOVER,
    text_color=COLOR_ACCENT_TEXT,
    command=command,
    **kwargs,
  )
