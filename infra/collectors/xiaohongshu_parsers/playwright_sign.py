"""小红书 API 请求签名（xhshow）."""

from __future__ import annotations

import hashlib
import json
import random
import time
from typing import Any, Dict, Optional, Union
from urllib.parse import quote


def get_trace_id() -> str:
  return ''.join(random.choice('abcdef0123456789') for _ in range(16))


def _patch_xhshow_a3_hash() -> None:
  from xhshow.core.crypto import CryptoProcessor

  original_build = CryptoProcessor.build_payload_array

  def patched_build(
    self,
    hex_parameter,
    a1_value,
    app_identifier='xhs-pc-web',
    string_param='',
    timestamp=None,
    sign_state=None,
  ):
    payload = original_build(
      self,
      hex_parameter,
      a1_value,
      app_identifier,
      string_param,
      timestamp,
      sign_state,
    )
    if '{' not in string_param:
      correct_md5_hex = hashlib.md5(string_param.encode('utf-8')).hexdigest()
      correct_md5_bytes = [int(correct_md5_hex[i:i + 2], 16) for i in range(0, 32, 2)]
      seed_byte = payload[4]
      ts_bytes = payload[8:16]
      correct_a3_hash = self._custom_hash_v2(list(ts_bytes) + correct_md5_bytes)
      for index in range(16):
        payload[128 + index] = correct_a3_hash[index] ^ seed_byte
    return payload

  CryptoProcessor.build_payload_array = patched_build


_patch_xhshow_a3_hash()


def _build_sign_string(
  uri: str,
  data: Optional[Union[Dict, str]] = None,
  method: str = 'POST',
) -> str:
  if method.upper() == 'POST':
    content = uri
    if data is not None:
      if isinstance(data, dict):
        content += json.dumps(data, separators=(',', ':'), ensure_ascii=False)
      elif isinstance(data, str):
        content += data
    return content

  if not data or (isinstance(data, dict) and len(data) == 0):
    return uri
  if isinstance(data, dict):
    params = []
    for key in data.keys():
      value = data[key]
      if isinstance(value, list):
        value_str = ','.join(str(item) for item in value)
      elif value is not None:
        value_str = str(value)
      else:
        value_str = ''
      value_str = quote(value_str, safe=',')
      params.append(f'{key}={value_str}')
    return f'{uri}?{"&".join(params)}'
  if isinstance(data, str):
    return f'{uri}?{data}'
  return uri


def sign_with_xhshow(
  uri: str,
  data: Optional[Union[Dict, str]] = None,
  cookie_str: str = '',
  method: str = 'POST',
) -> Dict[str, Any]:
  from xhshow import Xhshow

  client = Xhshow()
  if method.upper() == 'POST':
    headers = client.sign_headers_post(
      uri=uri,
      cookies=cookie_str,
      payload=data if isinstance(data, dict) else {},
    )
  else:
    content_string = _build_sign_string(uri, data, method)
    cookie_dict = client._parse_cookies(cookie_str)
    a1_value = cookie_dict.get('a1', '')
    ts = time.time()
    digest = hashlib.md5(content_string.encode('utf-8')).hexdigest()
    payload_array = client.crypto_processor.build_payload_array(
      digest, a1_value, 'xhs-pc-web', content_string, ts,
    )
    xor_result = client.crypto_processor.bit_ops.xor_transform_array(payload_array)
    config = client.config
    x3_b64 = client.crypto_processor.b64encoder.encode_x3(
      xor_result[:config.PAYLOAD_LENGTH],
    )
    sig_data = config.SIGNATURE_DATA_TEMPLATE.copy()
    sig_data['x3'] = config.X3_PREFIX + x3_b64
    x_s = config.XYS_PREFIX + client.crypto_processor.b64encoder.encode(
      json.dumps(sig_data, separators=(',', ':'), ensure_ascii=False),
    )
    headers = {
      'x-s': x_s,
      'x-s-common': client.sign_xs_common(cookie_dict),
      'x-t': str(client.get_x_t(ts)),
      'x-b3-traceid': client.get_b3_trace_id(),
    }

  return {
    'x-s': headers.get('x-s', ''),
    'x-t': headers.get('x-t', ''),
    'x-s-common': headers.get('x-s-common', ''),
    'x-b3-traceid': headers.get('x-b3-traceid', get_trace_id()),
  }
