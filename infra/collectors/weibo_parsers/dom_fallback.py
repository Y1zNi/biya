"""Lite 详情页 DOM 兜底解析."""

from __future__ import annotations

import re
from datetime import datetime

from core.models import CollectResultItem
from infra.collectors.douyin_parsers import number_format


def _extract_text(pattern: str, html: str, group: int = 1) -> str:
  match = re.search(pattern, html, re.I | re.S)
  if not match:
    return ''
  return (match.group(group) or '').strip()


def _normalize_relative_time(text: str) -> str:
  raw = (text or '').strip()
  if not raw:
    return '-'

  if re.match(r'\d{4}-\d{2}-\d{2}', raw):
    return raw

  now = datetime.now()
  year = now.year

  month_day = re.match(r'(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})', raw)
  if month_day:
    month, day, hour, minute = month_day.groups()
    return f'{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}'

  if raw.startswith('昨天'):
    time_match = re.search(r'(\d{1,2}):(\d{2})', raw)
    if time_match:
      hour, minute = time_match.groups()
      day = now.day - 1
      month = now.month
      if day < 1:
        month -= 1
        day = 28
      return f'{year}-{month:02d}-{day:02d} {int(hour):02d}:{minute}'
    return raw

  hour_ago = re.match(r'(\d+)\s*小时前', raw)
  if hour_ago:
    return raw

  return raw


def _parse_tab_metrics(html: str) -> tuple[str, str, str]:
  """正文页 .lite-page-tab：转发 / 评论 / 赞."""
  metrics: list[str] = []
  for label in ('转发', '评论', '赞'):
    match = re.search(
      rf'{label}<em[^>]*></em></i>\s*<i[^>]*>\s*([^<]+?)\s*</i>',
      html,
      re.I,
    )
    if not match:
      match = re.search(
        rf'>{label}</i>\s*<i[^>]*>\s*([^<]+?)\s*</i>',
        html,
        re.I,
      )
    if match:
      metrics.append(number_format.format_count(match.group(1)))
    else:
      metrics.append('-')

  if len(metrics) == 3 and any(value != '-' for value in metrics):
    return metrics[0], metrics[1], metrics[2]
  return '-', '-', '-'


def _parse_footer_metrics(html: str) -> tuple[str, str, str]:
  """时间线卡片 footer：转发 / 评论 / 赞."""
  footer = _extract_text(
    r'<footer class="f-footer-ctrl">(.*?)</footer>',
    html,
    1,
  )
  if not footer:
    return '-', '-', '-'

  values: list[str] = []
  for h4 in re.findall(r'<h4[^>]*>\s*([^<]+?)\s*</h4>', footer, re.I):
    text = h4.strip()
    if text in ('转发', '评论', '赞'):
      values.append('-')
    else:
      values.append(number_format.format_count(text))

  while len(values) < 3:
    values.append('-')
  return values[0], values[1], values[2]


def fill_from_dom(html: str, item: CollectResultItem) -> CollectResultItem:
  author = _extract_text(
    r'class="weibo-top[^"]*"[^>]*>.*?<h3[^>]*>.*?<span[^>]*>([^<]+)</span>',
    html,
    1,
  )
  if author:
    item.author_name = author

  time_text = _extract_text(r'<span class="time">\s*([^<]+?)\s*</span>', html, 1)
  if time_text:
    item.publish_time = _normalize_relative_time(time_text)

  shares, comments, likes = _parse_tab_metrics(html)
  if shares == '-' and comments == '-' and likes == '-':
    shares, comments, likes = _parse_footer_metrics(html)

  if shares != '-':
    item.shares = shares
  if comments != '-':
    item.comments = comments
  if likes != '-':
    item.likes = likes

  author_id = _extract_text(r'/profile/(\d+)', html, 1)
  if author_id:
    item.author_id = author_id

  item.views = '-'
  item.favorites = '-'
  return item
