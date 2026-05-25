"""各平台采集结果列定义（UI 表格与 Excel 导出）."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from core.models import CollectResultItem

TableColumn = Tuple[str, int, str]

# 链接, 发帖平台, 平台昵称, 浏览量, 点赞, 收藏, 评论, 转发, 类型, 状态
BASE_EXPORT_HEADERS: List[str] = [
  '链接',
  '发帖平台',
  '平台昵称',
  '浏览量',
  '点赞',
  '收藏',
  '评论',
  '转发',
  '类型',
  '状态',
]

BASE_TABLE_COLUMNS: List[TableColumn] = [
  ('链接', 220, 'w'),
  ('发帖平台', 56, 'center'),
  ('平台昵称', 110, 'w'),
  ('浏览量', 72, 'center'),
  ('点赞', 72, 'center'),
  ('收藏', 72, 'center'),
  ('评论', 72, 'center'),
  ('转发', 72, 'center'),
  ('类型', 48, 'center'),
  ('状态', 96, 'w'),
]

XHS_EXTRA_HEADERS: List[str] = ['小红书id', '作者id', '小红书号', '发布日期']
XHS_EXTRA_TABLE_COLUMNS: List[TableColumn] = [
  ('小红书id', 128, 'w'),
  ('作者id', 128, 'w'),
  ('小红书号', 128, 'w'),
  ('发布日期', 140, 'center'),
]

WEIBO_EXTRA_HEADERS: List[str] = ['发布日期']
WEIBO_EXTRA_TABLE_COLUMNS: List[TableColumn] = [
  ('发布日期', 140, 'center'),
]

WEIBO_PLATFORM_EXTRA_HEADERS: List[str] = ['微博id', '作者id', '发布日期']
WEIBO_PLATFORM_EXTRA_TABLE_COLUMNS: List[TableColumn] = [
  ('微博id', 128, 'w'),
  ('作者id', 128, 'w'),
  ('发布日期', 140, 'center'),
]

DOUYIN_EXTRA_HEADERS: List[str] = ['作品id', '作者id', '作者sec_uid', '抖音号', '发布日期']
DOUYIN_EXTRA_TABLE_COLUMNS: List[TableColumn] = [
  ('作品id', 128, 'w'),
  ('作者id', 128, 'w'),
  ('作者sec_uid', 160, 'w'),
  ('抖音号', 128, 'w'),
  ('发布日期', 140, 'center'),
]

KUAISHOU_EXTRA_HEADERS: List[str] = [
  '快手号',
  '发布日期',
]
KUAISHOU_EXTRA_TABLE_COLUMNS: List[TableColumn] = [
  ('快手号', 128, 'w'),
  ('发布日期', 140, 'center'),
]

BILI_EXTRA_HEADERS: List[str] = ['作者id', '发布日期', '投币']
BILI_EXTRA_TABLE_COLUMNS: List[TableColumn] = [
  ('作者id', 128, 'w'),
  ('发布日期', 140, 'center'),
  ('投币', 72, 'center'),
]

VIVO_EXTRA_HEADERS: List[str] = ['作者id', '发布日期']
VIVO_EXTRA_TABLE_COLUMNS: List[TableColumn] = [
  ('作者id', 128, 'w'),
  ('发布日期', 140, 'center'),
]

PLATFORM_EXPORT_HEADERS: dict[str, List[str]] = {
  'douyin': [
    '链接',
    '发帖平台',
    '平台昵称',
    *DOUYIN_EXTRA_HEADERS,
    '浏览量',
    '点赞',
    '收藏',
    '评论',
    '转发',
    '类型',
    '状态',
  ],
  'kuaishou': [
    '链接',
    '发帖平台',
    '平台昵称',
    *KUAISHOU_EXTRA_HEADERS,
    '浏览量',
    '点赞',
    '收藏',
    '评论',
    '转发',
    '类型',
    '状态',
  ],
  'xiaohongshu': [
    '链接',
    '发帖平台',
    '平台昵称',
    *XHS_EXTRA_HEADERS,
    '浏览量',
    '点赞',
    '收藏',
    '评论',
    '转发',
    '类型',
    '状态',
  ],
  'weibo': [
    '链接',
    '发帖平台',
    '平台昵称',
    *WEIBO_PLATFORM_EXTRA_HEADERS,
    '浏览量',
    '点赞',
    '收藏',
    '评论',
    '转发',
    '类型',
    '状态',
  ],
  'bilibili': [
    '链接',
    '发帖平台',
    '平台昵称',
    *BILI_EXTRA_HEADERS,
    '浏览量',
    '点赞',
    '收藏',
    '评论',
    '转发',
    '类型',
    '状态',
  ],
  'vivo': [
    '链接',
    '发帖平台',
    '平台昵称',
    *VIVO_EXTRA_HEADERS,
    '浏览量',
    '点赞',
    '收藏',
    '评论',
    '转发',
    '类型',
    '状态',
  ],
  'channels': [
    '链接',
    '发帖平台',
    '平台昵称',
    *WEIBO_EXTRA_HEADERS,
    '浏览量',
    '点赞',
    '收藏',
    '评论',
    '转发',
    '类型',
    '状态',
  ],
  'unknown': BASE_EXPORT_HEADERS,
}

PLATFORM_TABLE_COLUMNS: dict[str, List[TableColumn]] = {
  'douyin': [
    BASE_TABLE_COLUMNS[0],
    BASE_TABLE_COLUMNS[1],
    BASE_TABLE_COLUMNS[2],
    *DOUYIN_EXTRA_TABLE_COLUMNS,
    *BASE_TABLE_COLUMNS[3:],
  ],
  'kuaishou': [
    BASE_TABLE_COLUMNS[0],
    BASE_TABLE_COLUMNS[1],
    BASE_TABLE_COLUMNS[2],
    *KUAISHOU_EXTRA_TABLE_COLUMNS,
    *BASE_TABLE_COLUMNS[3:],
  ],
  'xiaohongshu': [
    BASE_TABLE_COLUMNS[0],
    BASE_TABLE_COLUMNS[1],
    BASE_TABLE_COLUMNS[2],
    *XHS_EXTRA_TABLE_COLUMNS,
    *BASE_TABLE_COLUMNS[3:],
  ],
  'weibo': [
    BASE_TABLE_COLUMNS[0],
    BASE_TABLE_COLUMNS[1],
    BASE_TABLE_COLUMNS[2],
    *WEIBO_PLATFORM_EXTRA_TABLE_COLUMNS,
    *BASE_TABLE_COLUMNS[3:],
  ],
  'bilibili': [
    BASE_TABLE_COLUMNS[0],
    BASE_TABLE_COLUMNS[1],
    BASE_TABLE_COLUMNS[2],
    *BILI_EXTRA_TABLE_COLUMNS,
    *BASE_TABLE_COLUMNS[3:],
  ],
  'vivo': [
    BASE_TABLE_COLUMNS[0],
    BASE_TABLE_COLUMNS[1],
    BASE_TABLE_COLUMNS[2],
    *VIVO_EXTRA_TABLE_COLUMNS,
    *BASE_TABLE_COLUMNS[3:],
  ],
  'channels': [
    BASE_TABLE_COLUMNS[0],
    BASE_TABLE_COLUMNS[1],
    BASE_TABLE_COLUMNS[2],
    *WEIBO_EXTRA_TABLE_COLUMNS,
    *BASE_TABLE_COLUMNS[3:],
  ],
  'unknown': BASE_TABLE_COLUMNS,
}

PLATFORM_SHEET_NAMES: dict[str, str] = {
  'douyin': '抖音',
  'kuaishou': '快手',
  'xiaohongshu': '小红书',
  'weibo': '微博',
  'bilibili': 'B站',
  'vivo': 'vivo社区',
  'channels': '微信视频号',
}


def normalize_platform_id(platform_id: str) -> str:
  pid = (platform_id or '').strip()
  if pid in PLATFORM_EXPORT_HEADERS:
    return pid
  return 'unknown'


def get_export_headers(platform_id: str) -> List[str]:
  return list(PLATFORM_EXPORT_HEADERS.get(normalize_platform_id(platform_id), BASE_EXPORT_HEADERS))


def get_table_columns(platform_id: str) -> List[TableColumn]:
  return list(PLATFORM_TABLE_COLUMNS.get(normalize_platform_id(platform_id), BASE_TABLE_COLUMNS))


def get_sheet_name(platform_id: str) -> str:
  return PLATFORM_SHEET_NAMES.get(normalize_platform_id(platform_id), '未知')


def _base_cells(item: CollectResultItem) -> List[str]:
  return [
    item.link,
    item.platform_name,
    item.author_name,
    item.views,
    item.likes,
    item.favorites,
    item.comments,
    item.shares,
    item.media_type,
    item.status_label,
  ]


def item_to_export_cells(item: CollectResultItem, platform_id: str) -> List[str]:
  pid = normalize_platform_id(platform_id or item.platform_id)
  if pid == 'xiaohongshu':
    return [
      item.link,
      item.platform_name,
      item.author_name,
      item.note_id,
      item.author_id,
      item.author_sec_uid,
      item.publish_time,
      item.views,
      item.likes,
      item.favorites,
      item.comments,
      item.shares,
      item.media_type,
      item.status_label,
    ]
  if pid == 'douyin':
    return [
      item.link,
      item.platform_name,
      item.author_name,
      item.note_id,
      item.author_id,
      item.author_sec_uid,
      item.douyin_id,
      item.publish_time,
      item.views,
      item.likes,
      item.favorites,
      item.comments,
      item.shares,
      item.media_type,
      item.status_label,
    ]
  if pid == 'weibo':
    return [
      item.link,
      item.platform_name,
      item.author_name,
      item.note_id,
      item.author_id,
      item.publish_time,
      item.views,
      item.likes,
      item.favorites,
      item.comments,
      item.shares,
      item.media_type,
      item.status_label,
    ]
  if pid == 'kuaishou':
    return [
      item.link,
      item.platform_name,
      item.author_name,
      item.author_sec_uid,
      item.publish_time,
      item.views,
      item.likes,
      item.favorites,
      item.comments,
      item.shares,
      item.media_type,
      item.status_label,
    ]
  if pid == 'channels':
    return [
      item.link,
      item.platform_name,
      item.author_name,
      item.publish_time,
      item.views,
      item.likes,
      item.favorites,
      item.comments,
      item.shares,
      item.media_type,
      item.status_label,
    ]
  if pid == 'bilibili':
    return [
      item.link,
      item.platform_name,
      item.author_name,
      item.author_id,
      item.publish_time,
      item.coins,
      item.views,
      item.likes,
      item.favorites,
      item.comments,
      item.shares,
      item.media_type,
      item.status_label,
    ]
  if pid == 'vivo':
    return [
      item.link,
      item.platform_name,
      item.author_name,
      item.author_id,
      item.publish_time,
      item.views,
      item.likes,
      item.favorites,
      item.comments,
      item.shares,
      item.media_type,
      item.status_label,
    ]
  return _base_cells(item)


def metric_column_indices(platform_id: str) -> Sequence[int]:
  """互动数字段列索引（用于「-」灰色显示）."""
  headers = get_export_headers(platform_id)
  metric_names = frozenset({'浏览量', '点赞', '收藏', '评论', '转发', '投币'})
  return [index for index, name in enumerate(headers) if name in metric_names]
