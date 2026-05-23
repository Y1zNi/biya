"""快手评论数 GraphQL 接口."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from playwright.async_api import APIRequestContext

from infra.collectors.kuaishou_parsers import graphql_queries
from infra.collectors.kuaishou_parsers import ids as kuaishou_ids

GRAPHQL_URL = 'https://www.kuaishou.com/graphql'

DEFAULT_USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
)

_COMMENT_COUNT_KEYS = ('commentCountV2', 'commentCount', 'comment_count')


def build_api_headers(referer: str) -> Dict[str, str]:
  return {
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Cache-Control': 'no-cache',
    'Content-Type': 'application/json',
    'Origin': 'https://www.kuaishou.com',
    'Pragma': 'no-cache',
    'Referer': referer,
    'User-Agent': DEFAULT_USER_AGENT,
  }


def parse_comment_count(body: Optional[Dict[str, Any]]) -> Any:
  if not body or body.get('errors'):
    return None

  data = body.get('data')
  if not isinstance(data, dict):
    return None

  comment_list = data.get('visionCommentList')
  if not isinstance(comment_list, dict):
    return None

  for key in _COMMENT_COUNT_KEYS:
    if key in comment_list and comment_list.get(key) is not None:
      return comment_list.get(key)
  return None


def _parse_video_author_hints(body: Optional[Dict[str, Any]]) -> tuple[str, str]:
  if not body or body.get('errors'):
    return '', ''

  data = body.get('data')
  if not isinstance(data, dict):
    return '', ''

  detail = data.get('visionVideoDetail')
  if not isinstance(detail, dict):
    return '', ''

  author = detail.get('author')
  author_obj = author if isinstance(author, dict) else {}
  photo = detail.get('photo')
  photo_obj = photo if isinstance(photo, dict) else {}

  uid = kuaishou_ids.photo_author_uid(photo_obj, author_obj)
  if not uid:
    uid = kuaishou_ids.extract_uid_from_cdn_url(
      kuaishou_ids.cdn_url_from_photo(photo_obj, author_obj),
    )

  eid = kuaishou_ids.photo_author_eid(photo_obj, author_obj)
  if not eid:
    author_id = str(author_obj.get('id') or '').strip()
    if author_id and not kuaishou_ids.is_numeric_uid(author_id):
      eid = author_id

  return uid, eid


async def fetch_video_author_hints(
  request: APIRequestContext,
  photo_id: str,
  referer: str,
) -> tuple[str, str]:
  """仅在缺少作者 uid 时调用 visionVideoDetail 补全作者信息."""
  photo = str(photo_id or '').strip()
  if not photo:
    return '', ''

  payload = {
    'operationName': 'visionVideoDetail',
    'variables': {'photoId': photo, 'page': 'search'},
    'query': graphql_queries.VIDEO_DETAIL_QUERY,
  }
  try:
    response = await request.post(
      GRAPHQL_URL,
      data=json.dumps(payload, ensure_ascii=False),
      headers=build_api_headers(referer),
    )
    if response.status != 200:
      return '', ''
    body = await response.json()
    return _parse_video_author_hints(body if isinstance(body, dict) else None)
  except Exception:
    return '', ''


async def fetch_comment_count(
  request: APIRequestContext,
  photo_id: str,
  referer: str,
) -> Any:
  """调用 commentListQuery 获取作品评论总数."""
  payload = {
    'operationName': 'commentListQuery',
    'variables': {'photoId': photo_id, 'pcursor': ''},
    'query': graphql_queries.COMMENT_LIST_QUERY,
  }
  try:
    response = await request.post(
      GRAPHQL_URL,
      data=json.dumps(payload, ensure_ascii=False),
      headers=build_api_headers(referer),
    )
    if response.status != 200:
      return None
    body = await response.json()
    return parse_comment_count(body if isinstance(body, dict) else None)
  except Exception:
    return None
