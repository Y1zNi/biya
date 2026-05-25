"""微博类型推断（无网络）."""

from infra.collectors.weibo_parsers import page as weibo_page

SAMPLE_IMAGE_TAB_HTML = """
<header class="weibo-top"><h3><span>娱乐蜀黍</span></h3></header>
<span class="time">5-17 11:43</span>
<div class="lite-page-tab">
  <i>转发<em></em></i><i>16</i>
  <i>评论<em></em></i><i>156</i>
  <i>赞<em></em></i><i>1757</i>
</div>
<div class="weibo-media-wraps"><img src="//wx1.sinaimg.cn/a.jpg"></div>
<div class="video-player" style="display: none"></div>
<video class="vjs-tech"></video>
"""

MBLOG_IMAGE = {
  'text': 'vivo X300',
  'pic_ids': ['a', 'b', 'c', 'd'],
  'comments_count': 54,
}

MBLOG_VIDEO = {
  'text': 'demo',
  'page_info': {'type': 'video', 'media_info': {}},
}

MBLOG_RETWEET = {
  'text': '转发',
  'retweeted_status': {'id': '1', 'text': 'origin'},
}

MBLOG_TEXT_ONLY = {
  'text': '只有文字',
}


def test_html_image_with_hidden_video_player_is_graphic():
  assert weibo_page.infer_media_type_from_html(SAMPLE_IMAGE_TAB_HTML) == '图文'


def test_mblog_pic_ids_is_graphic():
  assert weibo_page.infer_media_type_from_mblog(MBLOG_IMAGE) == '图文'


def test_mblog_prefers_graphic_over_hidden_html_video():
  assert weibo_page.infer_media_type(MBLOG_IMAGE, SAMPLE_IMAGE_TAB_HTML) == '图文'


def test_mblog_video():
  assert weibo_page.infer_media_type_from_mblog(MBLOG_VIDEO) == '视频'


def test_mblog_retweet():
  assert weibo_page.infer_media_type_from_mblog(MBLOG_RETWEET) == '转发'


def test_mblog_text_only():
  assert weibo_page.infer_media_type_from_mblog(MBLOG_TEXT_ONLY) == '纯文字'
