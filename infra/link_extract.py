"""从分享文案、表格单元格中提取可采集链接."""

from __future__ import annotations

import re
from typing import List

from infra.platform_detect import detect_platform

_URL_PATTERN = re.compile(
  r'https?://[^\s<>"\'\u3000-\u303f\u4e00-\u9fff【】「」\[\]()（）]+',
  re.I,
)

_TRAILING_CHARS = '.,;:!?)、。，；：！？]》」'


def extract_urls_from_text(text: str) -> List[str]:
  """从文本中匹配 http(s) URL，去掉末尾粘连标点."""
  if not text:
    return []
  urls: List[str] = []
  seen: set[str] = set()
  for raw in _URL_PATTERN.findall(text):
    url = raw.rstrip(_TRAILING_CHARS)
    if not url or url in seen:
      continue
    seen.add(url)
    urls.append(url)
  return urls


def extract_collect_links_from_cell(text: str) -> List[str]:
  """从单元格/一行分享文案中提取可采集的平台链接（可多条）."""
  stripped = (text or '').strip()
  if not stripped:
    return []

  urls = extract_urls_from_text(stripped)
  result: List[str] = []
  seen: set[str] = set()
  for url in urls:
    if detect_platform(url).platform_id == 'unknown':
      continue
    if url in seen:
      continue
    seen.add(url)
    result.append(url)

  if result:
    return result

  lower = stripped.lower()
  if lower.startswith(('http://', 'https://')):
    return [stripped]

  if detect_platform(stripped).platform_id != 'unknown':
    return [stripped]

  return []


def normalize_collect_link(link: str) -> str:
  """采集前规范化：分享文案取首个可识别平台链接，否则原样."""
  extracted = extract_collect_links_from_cell(link)
  if extracted:
    return extracted[0]
  return (link or '').strip()
