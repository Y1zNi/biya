"""B 站作品链接解析（仅视频）."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

BV_PATTERN = re.compile(r'/video/(BV[a-zA-Z0-9]+)', re.I)
AV_PATTERN = re.compile(r'/video/av(\d+)', re.I)
OPUS_PATTERN = re.compile(r'/opus/(\d+)', re.I)
SHORT_BV_PATTERN = re.compile(r'^(BV[a-zA-Z0-9]+)$', re.I)
SHORT_LINK_HOST_MARKERS = ('b23.tv', 'b23.tv/')


@dataclass
class VideoUrlInfo:
  bvid: str = ''
  aid: str = ''
  is_opus: bool = False
  opus_id: str = ''

  @property
  def is_video(self) -> bool:
    return bool(self.bvid or self.aid)

  def build_canonical_url(self) -> str:
    if self.bvid:
      return f'https://www.bilibili.com/video/{self.bvid}'
    if self.aid:
      return f'https://www.bilibili.com/video/av{self.aid}'
    return ''


def parse_video_url(link: str) -> VideoUrlInfo:
  text = (link or '').strip()
  if not text:
    return VideoUrlInfo()

  if SHORT_BV_PATTERN.match(text):
    return VideoUrlInfo(bvid=text)

  parsed = urlparse(text)
  path = parsed.path or text

  opus_match = OPUS_PATTERN.search(path)
  if opus_match:
    return VideoUrlInfo(is_opus=True, opus_id=opus_match.group(1))

  bv_match = BV_PATTERN.search(path) or BV_PATTERN.search(text)
  if bv_match:
    return VideoUrlInfo(bvid=bv_match.group(1))

  av_match = AV_PATTERN.search(path) or AV_PATTERN.search(text)
  if av_match:
    return VideoUrlInfo(aid=av_match.group(1))

  return VideoUrlInfo()


def needs_url_resolve(link: str) -> bool:
  text = (link or '').strip().lower()
  if not text:
    return False
  info = parse_video_url(link)
  if info.is_video or info.is_opus:
    return False
  return any(marker in text for marker in SHORT_LINK_HOST_MARKERS)


def is_supported_video_link(link: str) -> bool:
  info = parse_video_url(link)
  return info.is_video and not info.is_opus
