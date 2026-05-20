"""抖音 Web API 客户端（对齐 MediaCrawler detail 模式，无作品页 goto）."""

from __future__ import annotations

import copy
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from playwright.async_api import BrowserContext, Page

from infra.collectors.douyin_parsers.cookies_util import convert_browser_context_cookies
from infra.collectors.douyin_parsers.sign import get_a_bogus, get_web_id


class DataFetchError(Exception):
  """接口请求或解析失败."""


class DouyinApiClient:
  """通过 /aweme/v1/web/aweme/detail/ 拉取作品详情."""

  def __init__(
    self,
    *,
    headers: Dict[str, str],
    playwright_page: Page,
    cookie_dict: Dict[str, str],
    timeout: float = 60,
  ) -> None:
    self.timeout = timeout
    self.headers = headers
    self._host = 'https://www.douyin.com'
    self.playwright_page = playwright_page
    self.cookie_dict = cookie_dict
    self.cookie_urls = [
      'https://douyin.com',
      self._host,
      'https://creator.douyin.com',
      'https://douhot.douyin.com',
      'https://live.douyin.com',
    ]

  async def __process_req_params(
    self,
    uri: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    request_method: str = 'GET',
  ) -> None:
    if not params:
      return
    headers = headers or self.headers
    local_storage: Dict = await self.playwright_page.evaluate('() => window.localStorage')
    common_params = {
      'device_platform': 'webapp',
      'aid': '6383',
      'channel': 'channel_pc_web',
      'version_code': '190600',
      'version_name': '19.6.0',
      'update_version_code': '170400',
      'pc_client_type': '1',
      'cookie_enabled': 'true',
      'browser_language': 'zh-CN',
      'browser_platform': 'MacIntel',
      'browser_name': 'Chrome',
      'browser_version': '125.0.0.0',
      'browser_online': 'true',
      'engine_name': 'Blink',
      'os_name': 'Mac OS',
      'os_version': '10.15.7',
      'cpu_core_num': '8',
      'device_memory': '8',
      'engine_version': '109.0',
      'platform': 'PC',
      'screen_width': '2560',
      'screen_height': '1440',
      'effective_type': '4g',
      'round_trip_time': '50',
      'webid': get_web_id(),
      'msToken': local_storage.get('xmst'),
    }
    params.update(common_params)
    query_string = urllib.parse.urlencode(params)
    post_data: Dict[str, Any] = {}
    if request_method == 'POST':
      post_data = params
    if '/v1/web/general/search' not in uri:
      a_bogus = await get_a_bogus(
        uri,
        query_string,
        post_data,
        headers['User-Agent'],
        self.playwright_page,
      )
      params['a_bogus'] = a_bogus

  async def request(self, method: str, url: str, **kwargs) -> Any:
    async with httpx.AsyncClient() as client:
      response = await client.request(method, url, timeout=self.timeout, **kwargs)
    try:
      if response.text == '' or response.text == 'blocked':
        raise DataFetchError(f'account blocked: {response.text}')
      return response.json()
    except DataFetchError:
      raise
    except Exception as exc:
      raise DataFetchError(f'{exc}, {response.text}') from exc

  async def get(
    self,
    uri: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
  ) -> Any:
    await self.__process_req_params(uri, params, headers)
    headers = headers or self.headers
    return await self.request(
      method='GET',
      url=f'{self._host}{uri}',
      params=params,
      headers=headers,
    )

  async def pong(self, browser_context: BrowserContext) -> bool:
    local_storage = await self.playwright_page.evaluate('() => window.localStorage')
    if local_storage.get('HasUserLogin', '') == '1':
      return True
    _, cookie_dict = await convert_browser_context_cookies(
      browser_context,
      urls=self.cookie_urls,
    )
    return cookie_dict.get('LOGIN_STATUS') == '1'

  async def update_cookies(
    self,
    browser_context: BrowserContext,
    urls: Optional[list[str]] = None,
  ) -> None:
    cookie_str, cookie_dict = await convert_browser_context_cookies(
      browser_context,
      urls=urls or self.cookie_urls,
    )
    self.headers['Cookie'] = cookie_str
    self.cookie_dict = cookie_dict

  async def get_video_by_id(self, aweme_id: str) -> Dict[str, Any]:
    params = {'aweme_id': aweme_id}
    headers = copy.copy(self.headers)
    headers.pop('Origin', None)
    res = await self.get('/aweme/v1/web/aweme/detail/', params, headers)
    aweme = res.get('aweme_detail') or {}
    if not aweme:
      raise DataFetchError(f'empty aweme_detail for aweme_id={aweme_id}')
    return aweme

  async def resolve_short_url(self, short_url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=False) as client:
      try:
        response = await client.get(short_url, timeout=10)
        if response.status_code in (301, 302, 303, 307, 308):
          return response.headers.get('Location', '') or ''
        return ''
      except Exception:
        return ''


async def create_douyin_api_client(
  browser_context: BrowserContext,
  session_page: Page,
) -> DouyinApiClient:
  cookie_str, cookie_dict = await convert_browser_context_cookies(
    browser_context,
    urls=[
      'https://douyin.com',
      'https://www.douyin.com',
      'https://creator.douyin.com',
      'https://douhot.douyin.com',
      'https://live.douyin.com',
    ],
  )
  user_agent = await session_page.evaluate('() => navigator.userAgent')
  return DouyinApiClient(
    headers={
      'User-Agent': user_agent,
      'Cookie': cookie_str,
      'Host': 'www.douyin.com',
      'Origin': 'https://www.douyin.com/',
      'Referer': 'https://www.douyin.com/',
      'Content-Type': 'application/json;charset=UTF-8',
    },
    playwright_page=session_page,
    cookie_dict=cookie_dict,
  )
