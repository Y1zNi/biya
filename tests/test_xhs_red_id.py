"""小红书号解析单元测试."""

from infra.collectors.xiaohongshu_parsers import initial_state as xhs_initial_state
from infra.collectors.xiaohongshu_parsers.url import (
  build_profile_url,
  parse_profile_href,
  profile_url_from_note_page_html,
)


def test_parse_profile_href_with_token():
  href = (
    '/user/profile/5684ecb3aed758404ddd38ff'
    '?xsec_token=ABLRk7q1w9myV8i22_PfKDNxlac5I4QwonESPPtsaKTsI=&xsec_source=pc_note'
  )
  info = parse_profile_href(href)
  assert info is not None
  assert info.user_id == '5684ecb3aed758404ddd38ff'
  assert info.xsec_token.startswith('ABLRk7q1')
  assert info.xsec_source == 'pc_note'


def test_build_profile_url_fallback_order():
  url = build_profile_url('5684ecb3aed758404ddd38ff')
  assert url == 'https://www.xiaohongshu.com/user/profile/5684ecb3aed758404ddd38ff'
  url2 = build_profile_url(
    '5684ecb3aed758404ddd38ff',
    xsec_token='tok',
    xsec_source='app_share',
  )
  assert 'xsec_token=tok' in url2
  assert 'xsec_source=app_share' in url2


def test_profile_from_note_container_html():
  html = '''
  <div id="noteContainer">
    <a href="/user/profile/5684ecb3aed758404ddd38ff?xsec_token=DOM_TOKEN&xsec_source=pc_note">主页</a>
  </div>
  <a href="/user/profile/aaaaaaaaaaaaaaaaaaaaaaaa?xsec_token=OTHER">other</a>
  '''
  info = profile_url_from_note_page_html(html, '5684ecb3aed758404ddd38ff')
  assert info is not None
  assert info.xsec_token == 'DOM_TOKEN'


def test_red_id_from_user_page():
  user_page = {
    'basicInfo': {
      'nickname': '测试',
      'redId': '123456789',
    },
  }
  assert xhs_initial_state.red_id_from_user_page(user_page) == '123456789'


if __name__ == '__main__':
  test_parse_profile_href_with_token()
  test_build_profile_url_fallback_order()
  test_profile_from_note_container_html()
  test_red_id_from_user_page()
  print('ok')
