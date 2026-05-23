"""快手页面通用操作."""

from __future__ import annotations

import asyncio
from typing import FrozenSet

from playwright.async_api import Page

from infra.collectors.kuaishou_parsers import h5_author
from infra.collectors.kuaishou_parsers import ids as kuaishou_ids
from infra.collectors.kuaishou_parsers.time_util import format_dom_photo_time

LOGIN_COOKIE_NAMES: FrozenSet[str] = frozenset({
  'kuaishou.server.web_st',
  'passToken',
  'userId',
  'kwssectoken',
  'did',
})

LOGIN_MODAL_SELECTORS = [
  '.login-modal-v2',
  '[class*="login-modal"]',
  '[class*="passport-login"]',
  '[class*="login-panel"]',
]


async def dismiss_overlays(page: Page) -> None:
  for _ in range(3):
    try:
      await page.keyboard.press('Escape')
      await asyncio.sleep(0.35)
    except Exception:
      break

  dismiss_texts = ('我知道了', '知道了', '以后再说', '暂不', '跳过', '关闭')
  for text in dismiss_texts:
    try:
      btn = page.locator(f'text={text}').first
      if await btn.is_visible(timeout=400):
        await btn.click()
        await asyncio.sleep(0.4)
    except Exception:
      continue


async def has_login_cookies_from_context(context) -> bool:
  try:
    cookies = await context.cookies()
  except Exception:
    return False
  for cookie in cookies:
    name = cookie.get('name', '')
    if name in LOGIN_COOKIE_NAMES and str(cookie.get('value', '')).strip():
      return True
  return False


async def has_login_cookies(page: Page) -> bool:
  return await has_login_cookies_from_context(page.context)


async def is_login_modal_visible(page: Page) -> bool:
  for sel in LOGIN_MODAL_SELECTORS:
    try:
      if await page.locator(sel).first.is_visible(timeout=300):
        return True
    except Exception:
      continue
  return False


def is_kuaishou_page_url(url: str) -> bool:
  lower = (url or '').lower()
  return 'kuaishou.com' in lower or 'gifshow.com' in lower or 'chenzhongtech.com' in lower


async def extract_photo_id_from_page(page: Page) -> str:
  """从当前详情页 URL 或 video 的 clientCacheKey 解析作品 ID."""
  try:
    photo_id = await page.evaluate(
      """() => {
        const pathMatch = location.pathname.match(/\\/short-video\\/([^/?#]+)/i);
        if (pathMatch && pathMatch[1]) return pathMatch[1];

        const video = document.querySelector('video.player-video, video[src*="clientCacheKey"]');
        const src = video && (video.currentSrc || video.src || '');
        if (!src) return '';

        const keyMatch = src.match(/clientCacheKey=([^&._]+)/i);
        if (keyMatch && keyMatch[1]) return keyMatch[1];

        const idMatch = src.match(/\\/([3][a-z0-9]{10,})_/i);
        return idMatch && idMatch[1] ? idMatch[1] : '';
      }"""
    )
    return str(photo_id or '').strip()
  except Exception:
    return ''


async def read_dom_photo_time(page: Page) -> str:
  """读取作品页作者旁的发布时间（.photo-time）."""
  try:
    raw = await page.evaluate(
      """() => {
        const el = document.querySelector('.photo-time')
          || document.querySelector('span.photo-time');
        return el && el.textContent ? el.textContent.trim() : '';
      }"""
    )
    return format_dom_photo_time(str(raw) if raw else '')
  except Exception:
    return '-'


async def extract_h5_photo_id_from_page(page: Page) -> str:
  """H5 分享页：/fw/photo/{id} 或封面图 clientCacheKey."""
  try:
    photo_id = await page.evaluate(
      """() => {
        const fwMatch = location.pathname.match(/\\/fw\\/photo\\/([^/?#]+)/i);
        if (fwMatch && fwMatch[1]) return fwMatch[1];

        const img = document.querySelector('img.image[src*="clientCacheKey"], img[src*="clientCacheKey"]');
        const src = img && (img.src || '');
        if (!src) return '';

        const keyMatch = src.match(/clientCacheKey=([^&._]+)/i);
        return keyMatch && keyMatch[1] ? keyMatch[1] : '';
      }"""
    )
    return str(photo_id or '').strip()
  except Exception:
    return ''


H5_DOM_AUTHOR_SELECTORS = (
  '.g-common-bar__inner__name',
  '.work-info .author .txt',
)


async def read_h5_dom_author(page: Page) -> str:
  for selector in H5_DOM_AUTHOR_SELECTORS:
    try:
      loc = page.locator(selector).first
      if await loc.is_visible(timeout=2000):
        text = (await loc.inner_text()).strip()
        if text.startswith('@'):
          text = text[1:].strip()
        if text:
          return text
    except Exception:
      continue
  return ''


async def read_h5_author_hints(page: Page) -> dict[str, str]:
  """从 H5 页面 URL、作者区链接与 INIT_STATE 提取 uid / eid / 头像."""
  try:
    raw = await page.evaluate(
      """() => {
        const result = { uid: '', eid: '', headurl: '' };
        const pickQuery = (search) => {
          if (!search) return;
          const params = new URLSearchParams(search.startsWith('?') ? search : `?${search}`);
          const fid = params.get('fid') || '';
          if (/^\\d+$/.test(fid) && !result.uid) result.uid = fid;
          for (const key of ['efid', 'userEid', 'eid']) {
            const value = params.get(key) || '';
            if (value && !/^\\d+$/.test(value) && !result.eid) {
              result.eid = value;
              break;
            }
          }
          const userId = params.get('userId') || '';
          if (/^\\d+$/.test(userId) && !result.uid) result.uid = userId;
          else if (userId && !/^\\d+$/.test(userId) && !result.eid) result.eid = userId;
        };
        pickQuery(location.search || '');

        const selectors = [
          'a[href*="fid="]',
          'a[href*="efid="]',
          'a[href*="userEid="]',
          'a[href*="/profile/"]',
          '.g-common-bar a[href]',
          '.work-info a[href]',
        ];
        for (const sel of selectors) {
          document.querySelectorAll(sel).forEach((node) => {
            const href = node.href || node.getAttribute('href') || '';
            if (!href) return;
            try {
              const url = new URL(href, location.href);
              pickQuery(url.search || '');
              const profileMatch = url.pathname.match(/\\/profile\\/([^/?#]+)/i);
              if (profileMatch && profileMatch[1]) {
                const token = profileMatch[1];
                if (/^\\d{8,}$/.test(token) && !result.uid) result.uid = token;
                else if (token && !/^\\d+$/.test(token) && !result.eid) result.eid = token;
              }
            } catch (e) {}
          });
        }

        const head = document.querySelector(
          '.g-common-bar img, .work-info img, img[class*="avatar"], img[class*="head"]',
        );
        if (head && (head.src || head.getAttribute('src'))) {
          result.headurl = head.src || head.getAttribute('src') || '';
        }
        return result;
      }"""
    )
    if isinstance(raw, dict):
      hints = {
        'uid': str(raw.get('uid') or '').strip(),
        'eid': str(raw.get('eid') or '').strip(),
        'headurl': str(raw.get('headurl') or '').strip(),
      }
      for url in (page.url,):
        url_hints = h5_author.parse_author_hints_from_href(url)
        for key in ('uid', 'eid', 'headurl'):
          if hints.get(key):
            continue
          value = str(url_hints.get(key) or '').strip()
          if value:
            hints[key] = value
      if not hints['uid'] and hints['headurl']:
        hints['uid'] = kuaishou_ids.extract_uid_from_cdn_url(hints['headurl'])
      return hints
  except Exception:
    pass
  return {'uid': '', 'eid': '', 'headurl': ''}


async def read_dom_metrics(page: Page) -> dict[str, str]:
  """从作品页 DOM 读取播放量、点赞数（页面展示文案，含 2.3万 等形式）."""
  try:
    raw = await page.evaluate(
      """() => {
        const result = {};
        const pick = (node) => (node && node.textContent ? node.textContent.trim() : '');

        const likeEl = document.querySelector('.like-item .item-count');
        if (likeEl) result.likes = pick(likeEl);

        const viewSelectors = [
          '.play-count',
          '.video-info-detail .view',
          '[class*="play-count"]',
          '[class*="playCount"]',
          '.photo-info .view',
          '.profile-video-info .count',
          '.video-info .count',
          '.short-video-info .count',
          '[class*="video-info"] [class*="count"]',
        ];
        for (const sel of viewSelectors) {
          const el = document.querySelector(sel);
          if (el && pick(el)) {
            result.views = pick(el);
            break;
          }
        }

        if (!result.views) {
          document.querySelectorAll('.interactive-item, [class*="interactive-item"]').forEach((item) => {
            const cls = (item.className || '').toString().toLowerCase();
            const countText = pick(item.querySelector('.item-count'));
            if (!countText) return;
            if (cls.includes('play') && !result.views) result.views = countText;
            if (cls.includes('like') && !result.likes) result.likes = countText;
          });
        }

        if (!result.views) {
          const bodyText = document.body ? document.body.innerText : '';
          const m = bodyText.match(/([\\d.]+)\\s*万\\s*次播放/);
          if (m) result.views = m[0].replace(/次播放/g, '').trim();
        }

        return result;
      }"""
    )
    return raw if isinstance(raw, dict) else {}
  except Exception:
    return {}
