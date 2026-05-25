"""device_guard 单元测试."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.device_guard import (
  ALLOWED_MACS,
  DEV_KEY_FILENAME,
  DEV_KEY_VALUE,
  collect_local_macs,
  get_exe_dir,
  has_dev_key,
  is_device_allowed,
  normalize_mac,
)


class TestNormalizeMac(unittest.TestCase):
  def test_colon_dash_and_compact(self):
    self.assertEqual(normalize_mac('62:74:B1:17:93:44'), '62:74:b1:17:93:44')
    self.assertEqual(normalize_mac('62-74-B1-17-93-44'), '62:74:b1:17:93:44')
    self.assertEqual(normalize_mac('6274b1179344'), '62:74:b1:17:93:44')
    self.assertEqual(normalize_mac('invalid'), '')


class TestHasDevKey(unittest.TestCase):
  def test_key_txt_bypass(self):
    with tempfile.TemporaryDirectory() as tmp:
      base = Path(tmp)
      self.assertFalse(has_dev_key(base))
      (base / DEV_KEY_FILENAME).write_text('meyou\n', encoding='utf-8')
      self.assertTrue(has_dev_key(base))
      (base / DEV_KEY_FILENAME).write_text(' wrong ', encoding='utf-8')
      self.assertFalse(has_dev_key(base))


class TestIsDeviceAllowed(unittest.TestCase):
  def test_dev_key_when_frozen(self):
    with tempfile.TemporaryDirectory() as tmp:
      base = Path(tmp)
      (base / DEV_KEY_FILENAME).write_text(DEV_KEY_VALUE, encoding='utf-8')
      with patch.object(sys, 'frozen', True, create=True):
        with patch('shared.device_guard.get_exe_dir', return_value=base):
          self.assertTrue(is_device_allowed())

  def test_whitelist_hit(self):
    sample = next(iter(ALLOWED_MACS))
    with patch.object(sys, 'frozen', True, create=True):
      with patch('shared.device_guard.has_dev_key', return_value=False):
        with patch('shared.device_guard.collect_local_macs', return_value={sample}):
          self.assertTrue(is_device_allowed())

  def test_denied_when_frozen(self):
    with patch.object(sys, 'frozen', True, create=True):
      with patch('shared.device_guard.has_dev_key', return_value=False):
        with patch('shared.device_guard.collect_local_macs', return_value={'00:11:22:33:44:55'}):
          self.assertFalse(is_device_allowed())

  def test_skips_when_not_frozen(self):
    with patch.object(sys, 'frozen', False, create=True):
      with patch('shared.device_guard.has_dev_key', return_value=False):
        with patch('shared.device_guard.collect_local_macs', return_value=set()):
          self.assertTrue(is_device_allowed())


class TestCollectLocalMacs(unittest.TestCase):
  def test_returns_normalized_set(self):
    macs = collect_local_macs()
    self.assertIsInstance(macs, set)
    for mac in macs:
      self.assertEqual(normalize_mac(mac), mac)


class TestGetExeDir(unittest.TestCase):
  def test_darwin_app_bundle_parent(self):
    with tempfile.TemporaryDirectory() as tmp:
      base = Path(tmp)
      exe_path = base / 'SocialMediaTool.app' / 'Contents' / 'MacOS' / 'SocialMediaTool'
      exe_path.parent.mkdir(parents=True, exist_ok=True)
      exe_path.touch()
      with patch.object(sys, 'frozen', True, create=True):
        with patch.object(sys, 'platform', 'darwin'):
          with patch.object(sys, 'executable', str(exe_path)):
            self.assertEqual(get_exe_dir().resolve(), base.resolve())

  def test_windows_exe_parent(self):
    with tempfile.TemporaryDirectory() as tmp:
      exe_path = Path(tmp) / 'SocialMediaTool.exe'
      exe_path.touch()
      with patch.object(sys, 'frozen', True, create=True):
        with patch.object(sys, 'platform', 'win32'):
          with patch.object(sys, 'executable', str(exe_path)):
            self.assertEqual(get_exe_dir().resolve(), exe_path.parent.resolve())


if __name__ == '__main__':
  unittest.main()
