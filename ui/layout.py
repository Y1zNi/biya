"""全局布局分隔线（横线 / 竖线）."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ui.theme import COLOR_DIVIDER, DIVIDER_SIZE, SPACE_SM


def _normalize_pady(pady: int | tuple[int, int]) -> tuple[int, int]:
  if isinstance(pady, tuple):
    return pady
  return pady, pady


def add_horizontal_divider(
  parent: ctk.CTkFrame,
  *,
  row: int | None = None,
  pady: int | tuple[int, int] = SPACE_SM,
) -> tk.Frame:
  """横线：使用 tk.Frame 保证 1px 可见（CTk 小高度 Frame 常被缩放为 0）."""
  top_pad, bottom_pad = _normalize_pady(pady)
  line = tk.Frame(
    parent,
    height=DIVIDER_SIZE,
    bg=COLOR_DIVIDER,
    bd=0,
    highlightthickness=0,
  )
  if row is not None:
    parent.grid_rowconfigure(row, minsize=DIVIDER_SIZE + top_pad + bottom_pad)
    line.grid(row=row, column=0, sticky='ew', pady=(top_pad, bottom_pad))
  else:
    line.pack(fill='x', pady=(top_pad, bottom_pad))
  return line


def add_vertical_divider(
  parent: ctk.CTkFrame,
  *,
  column: int | None = None,
  rowspan: int = 1,
  padx: int | tuple[int, int] = 0,
) -> tk.Frame:
  """竖线：使用 tk.Frame 保证 1px 可见."""
  if isinstance(padx, tuple):
    left_pad, right_pad = padx
  else:
    left_pad, right_pad = padx, padx

  line = tk.Frame(
    parent,
    width=DIVIDER_SIZE,
    bg=COLOR_DIVIDER,
    bd=0,
    highlightthickness=0,
  )
  if column is not None:
    parent.grid_columnconfigure(column, minsize=DIVIDER_SIZE + left_pad + right_pad)
    line.grid(
      row=0,
      column=column,
      rowspan=rowspan,
      sticky='ns',
      padx=(left_pad, right_pad),
    )
  else:
    line.pack(side='left', fill='y', padx=(left_pad, right_pad))
  return line
