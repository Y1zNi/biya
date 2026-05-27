"""小红书笔记链接解析单元测试."""

from infra.collectors.xiaohongshu_parsers.url import (
  extract_note_id_from_url,
  parse_note_url,
)

WECHAT_SHARE_URL = (
  'https://www.xiaohongshu.com/explore?app_platform=ios&app_version=9.28.1'
  '&share_from_user_hidden=true&xsec_source=app_share&type=video'
  '&xsec_token=CBcdl_dAEHg3wIcrdhF6togvuE5D8qrRdaFFui6_kVL3A%3D'
  '&author_share=1&xhsshare=WeixinSession'
  '&target_note_id=69f8c16d000000001a03628c'
  '&note_flow_source=wechat'
)

NOTE_ID = '69f8c16d000000001a03628c'
PATH_NOTE_ID = 'aaaaaaaaaaaaaaaaaaaaaaaa'


def test_wechat_share_url_parses_target_note_id():
  assert extract_note_id_from_url(WECHAT_SHARE_URL) == NOTE_ID
  info = parse_note_url(WECHAT_SHARE_URL)
  assert info.note_id == NOTE_ID
  assert info.xsec_token.startswith('CBcdl_dAEHg3wIcrdhF6togvuE5D8qrRdaFFui6_kVL3A')
  assert info.xsec_source == 'app_share'


def test_standard_explore_path_url():
  url = (
    f'https://www.xiaohongshu.com/explore/{NOTE_ID}'
    f'?xsec_token=tok123&xsec_source=pc_user'
  )
  assert extract_note_id_from_url(url) == NOTE_ID
  info = parse_note_url(url)
  assert info.note_id == NOTE_ID
  assert info.xsec_token == 'tok123'
  assert info.xsec_source == 'pc_user'


def test_path_id_takes_priority_over_target_note_id_query():
  url = (
    f'https://www.xiaohongshu.com/explore/{PATH_NOTE_ID}'
    f'?target_note_id={NOTE_ID}&xsec_token=tok'
  )
  assert extract_note_id_from_url(url) == PATH_NOTE_ID


def test_invalid_target_note_id_query_returns_empty():
  url = (
    'https://www.xiaohongshu.com/explore?'
    'target_note_id=not-hex&xsec_token=tok'
  )
  assert extract_note_id_from_url(url) == ''
