"""SQLite 数据库访问层."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, Iterable, Iterator, List, Optional, Tuple

from config import DB_FILE, PLATFORMS, ensure_dirs

ACCOUNT_STATUS_ACTIVE = 'active'
ACCOUNT_STATUS_EXPIRED = 'expired'
ACCOUNT_STATUS_INACTIVE = 'inactive'

OP_ADD = 'add'
OP_DELETE = 'delete'
OP_RELOGIN = 'relogin'
OP_COLLECT = 'collect'

OP_STATUS_SUCCESS = 'success'
OP_STATUS_FAILED = 'failed'


@dataclass
class Account:
  id: int
  platform: str
  name: str
  status: str
  state_file_path: str
  created_at: datetime
  updated_at: datetime


@dataclass
class OperationLog:
  id: int
  operation_type: str
  account_id: Optional[int]
  platform: Optional[str]
  status: str
  message: str
  created_at: datetime


@dataclass
class CollectTask:
  id: int
  platform: str
  account_id: int
  source_file: str
  total: int
  success_count: int
  status: str
  created_at: datetime


def _parse_datetime(value: str) -> datetime:
  return datetime.fromisoformat(value)


class Database:
  """数据库管理."""

  def __init__(self, db_path: Path = DB_FILE) -> None:
    ensure_dirs()
    self.db_path = db_path
    self._init_tables()

  @contextmanager
  def _connect(self) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    try:
      yield conn
      conn.commit()
    except Exception:
      conn.rollback()
      raise
    finally:
      conn.close()

  def _init_tables(self) -> None:
    with self._connect() as conn:
      conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          platform TEXT NOT NULL,
          name TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          state_file_path TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(platform, name)
        );
        CREATE INDEX IF NOT EXISTS idx_accounts_platform ON accounts(platform);

        CREATE TABLE IF NOT EXISTS operation_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          operation_type TEXT NOT NULL,
          account_id INTEGER,
          platform TEXT,
          status TEXT NOT NULL,
          message TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at
          ON operation_logs(created_at DESC);

        CREATE TABLE IF NOT EXISTS collect_tasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          platform TEXT NOT NULL,
          account_id INTEGER NOT NULL,
          source_file TEXT NOT NULL DEFAULT '',
          total INTEGER NOT NULL DEFAULT 0,
          success_count INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'running',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_collect_tasks_created_at
          ON collect_tasks(created_at DESC);

        CREATE TABLE IF NOT EXISTS collect_results (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id INTEGER NOT NULL,
          link TEXT NOT NULL,
          platform_name TEXT NOT NULL DEFAULT '',
          author_name TEXT NOT NULL DEFAULT '',
          note_id TEXT NOT NULL DEFAULT '-',
          author_id TEXT NOT NULL DEFAULT '-',
          author_sec_uid TEXT NOT NULL DEFAULT '-',
          douyin_id TEXT NOT NULL DEFAULT '-',
          publish_time TEXT NOT NULL DEFAULT '-',
          views TEXT NOT NULL DEFAULT '-',
          likes TEXT NOT NULL DEFAULT '-',
          favorites TEXT NOT NULL DEFAULT '-',
          comments TEXT NOT NULL DEFAULT '-',
          shares TEXT NOT NULL DEFAULT '-',
          media_type TEXT NOT NULL DEFAULT '-',
          status TEXT NOT NULL DEFAULT '',
          error_msg TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_collect_results_task_id
          ON collect_results(task_id);
        """
      )
      self._migrate_collect_results(conn)

  def _migrate_collect_results(self, conn: sqlite3.Connection) -> None:
    columns = (
      ('note_id', "TEXT NOT NULL DEFAULT '-'"),
      ('author_id', "TEXT NOT NULL DEFAULT '-'"),
      ('author_sec_uid', "TEXT NOT NULL DEFAULT '-'"),
      ('douyin_id', "TEXT NOT NULL DEFAULT '-'"),
      ('publish_time', "TEXT NOT NULL DEFAULT '-'"),
      ('platform_id', "TEXT NOT NULL DEFAULT ''"),
      ('payload_json', "TEXT NOT NULL DEFAULT ''"),
    )
    for name, definition in columns:
      try:
        conn.execute(f'ALTER TABLE collect_results ADD COLUMN {name} {definition}')
      except sqlite3.OperationalError:
        pass
    try:
      conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_collect_results_task_platform '
        'ON collect_results(task_id, platform_id)'
      )
    except sqlite3.OperationalError:
      pass

  def create_account(
    self,
    platform: str,
    name: str,
    state_file_path: str = '',
    status: str = ACCOUNT_STATUS_ACTIVE,
  ) -> int:
    now = datetime.now().isoformat()
    with self._connect() as conn:
      cursor = conn.execute(
        """
        INSERT INTO accounts (platform, name, status, state_file_path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (platform, name, status, state_file_path, now, now),
      )
      return int(cursor.lastrowid)

  def update_account(
    self,
    account_id: int,
    *,
    state_file_path: Optional[str] = None,
    status: Optional[str] = None,
    name: Optional[str] = None,
  ) -> None:
    account = self.get_account_by_id(account_id)
    if account is None:
      return
    now = datetime.now().isoformat()
    new_path = state_file_path if state_file_path is not None else account.state_file_path
    new_status = status if status is not None else account.status
    new_name = name if name is not None else account.name
    with self._connect() as conn:
      conn.execute(
        """
        UPDATE accounts
        SET state_file_path = ?, status = ?, name = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_path, new_status, new_name, now, account_id),
      )

  def get_account_by_id(self, account_id: int) -> Optional[Account]:
    with self._connect() as conn:
      row = conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
    return self._row_to_account(row) if row else None

  def get_accounts_paginated(
    self,
    platform: str,
    page: int = 1,
    page_size: int = 20,
  ) -> Tuple[List[Account], int]:
    page = max(1, page)
    offset = (page - 1) * page_size
    with self._connect() as conn:
      total = conn.execute(
        'SELECT COUNT(*) FROM accounts WHERE platform = ?',
        (platform,),
      ).fetchone()[0]
      rows = conn.execute(
        """
        SELECT * FROM accounts WHERE platform = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (platform, page_size, offset),
      ).fetchall()
    return [self._row_to_account(r) for r in rows], int(total)

  def count_active_accounts(self, platform: Optional[str] = None) -> int:
    with self._connect() as conn:
      if platform:
        row = conn.execute(
          "SELECT COUNT(*) FROM accounts WHERE platform = ? AND status = ?",
          (platform, ACCOUNT_STATUS_ACTIVE),
        ).fetchone()
      else:
        row = conn.execute(
          "SELECT COUNT(*) FROM accounts WHERE status = ?",
          (ACCOUNT_STATUS_ACTIVE,),
        ).fetchone()
    return int(row[0])

  def count_active_accounts_by_platform(self) -> Dict[str, int]:
    """各平台已登录（active）账号数量."""
    result: Dict[str, int] = {}
    for platform in PLATFORMS:
      result[platform['id']] = self.count_active_accounts(platform['id'])
    return result

  def delete_account(self, account_id: int) -> bool:
    with self._connect() as conn:
      cursor = conn.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
      return cursor.rowcount > 0

  def name_exists(self, platform: str, name: str, exclude_id: Optional[int] = None) -> bool:
    with self._connect() as conn:
      if exclude_id is not None:
        row = conn.execute(
          'SELECT 1 FROM accounts WHERE platform = ? AND name = ? AND id != ?',
          (platform, name, exclude_id),
        ).fetchone()
      else:
        row = conn.execute(
          'SELECT 1 FROM accounts WHERE platform = ? AND name = ?',
          (platform, name),
        ).fetchone()
    return row is not None

  def add_operation_log(
    self,
    operation_type: str,
    status: str,
    message: str,
    account_id: Optional[int] = None,
    platform: Optional[str] = None,
  ) -> int:
    now = datetime.now().isoformat()
    with self._connect() as conn:
      cursor = conn.execute(
        """
        INSERT INTO operation_logs
          (operation_type, account_id, platform, status, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (operation_type, account_id, platform, status, message, now),
      )
      return int(cursor.lastrowid)

  def get_collectable_accounts(self, platform: str) -> List[Account]:
    """获取可用于采集的 active 账号（state 文件存在）."""
    with self._connect() as conn:
      rows = conn.execute(
        """
        SELECT * FROM accounts
        WHERE platform = ? AND status = ?
        ORDER BY id DESC
        """,
        (platform, ACCOUNT_STATUS_ACTIVE),
      ).fetchall()
    accounts = [self._row_to_account(row) for row in rows]
    result: List[Account] = []
    for account in accounts:
      if account.state_file_path and Path(account.state_file_path).is_file():
        result.append(account)
    return result

  def get_collectable_accounts_grouped(self) -> Dict[str, List[Account]]:
    """返回各平台可采集账号列表."""
    grouped: Dict[str, List[Account]] = {}
    for platform in PLATFORMS:
      grouped[platform['id']] = self.get_collectable_accounts(platform['id'])
    return grouped

  def get_latest_collectable_account(self, platform: str) -> Optional[Account]:
    """取该平台最新可采集账号（id 最大且 state 文件存在）."""
    accounts = self.get_collectable_accounts(platform)
    return accounts[0] if accounts else None

  def get_latest_collectable_account_map(
    self,
    platform_ids: Iterable[str],
  ) -> Dict[str, Account]:
    """为各平台解析最新可采集账号."""
    result: Dict[str, Account] = {}
    for platform_id in platform_ids:
      account = self.get_latest_collectable_account(platform_id)
      if account is not None:
        result[platform_id] = account
    return result

  def create_collect_task(
    self,
    platform: str,
    account_id: int,
    source_file: str,
    total: int,
  ) -> int:
    now = datetime.now().isoformat()
    with self._connect() as conn:
      cursor = conn.execute(
        """
        INSERT INTO collect_tasks
          (platform, account_id, source_file, total, success_count, status, created_at)
        VALUES (?, ?, ?, ?, 0, 'running', ?)
        """,
        (platform, account_id, source_file, total, now),
      )
      return int(cursor.lastrowid)

  def finish_collect_task(
    self,
    task_id: int,
    *,
    success_count: int,
    status: str,
  ) -> None:
    with self._connect() as conn:
      conn.execute(
        """
        UPDATE collect_tasks
        SET success_count = ?, status = ?
        WHERE id = ?
        """,
        (success_count, status, task_id),
      )

  def add_collect_result(
    self,
    *,
    task_id: int,
    link: str,
    platform_name: str,
    author_name: str,
    note_id: str = '-',
    author_id: str = '-',
    author_sec_uid: str = '-',
    douyin_id: str = '-',
    publish_time: str = '-',
    views: str,
    likes: str,
    favorites: str,
    comments: str,
    shares: str,
    media_type: str,
    status: str,
    error_msg: str = '',
    platform_id: str = '',
    payload_json: str = '',
  ) -> int:
    now = datetime.now().isoformat()
    with self._connect() as conn:
      cursor = conn.execute(
        """
        INSERT INTO collect_results (
          task_id, link, platform_name, author_name,
          note_id, author_id, author_sec_uid, douyin_id, publish_time,
          views, likes, favorites, comments, shares, media_type,
          status, error_msg, created_at, platform_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          task_id, link, platform_name, author_name,
          note_id, author_id, author_sec_uid, douyin_id, publish_time,
          views, likes, favorites, comments, shares, media_type,
          status, error_msg, now, platform_id, payload_json,
        ),
      )
      return int(cursor.lastrowid)

  def get_latest_task(self) -> Optional[CollectTask]:
    with self._connect() as conn:
      row = conn.execute(
        'SELECT * FROM collect_tasks ORDER BY id DESC LIMIT 1',
      ).fetchone()
    return self._row_to_collect_task(row) if row else None

  def count_results_with_payload(self, task_id: int) -> int:
    with self._connect() as conn:
      row = conn.execute(
        """
        SELECT COUNT(*) FROM collect_results
        WHERE task_id = ? AND payload_json IS NOT NULL AND TRIM(payload_json) != ''
        """,
        (task_id,),
      ).fetchone()
    return int(row[0]) if row else 0

  def count_results_by_platform(self, task_id: int) -> Dict[str, int]:
    with self._connect() as conn:
      rows = conn.execute(
        """
        SELECT platform_id, COUNT(*) AS cnt FROM collect_results
        WHERE task_id = ?
          AND payload_json IS NOT NULL AND TRIM(payload_json) != ''
        GROUP BY platform_id
        """,
        (task_id,),
      ).fetchall()
    result: Dict[str, int] = {}
    for row in rows:
      pid = (row['platform_id'] or '').strip() or 'unknown'
      result[pid] = int(row['cnt'])
    return result

  def count_exportable_results(self, task_id: int, platform_id: Optional[str] = None) -> int:
    with self._connect() as conn:
      if platform_id:
        row = conn.execute(
          """
          SELECT COUNT(*) FROM collect_results
          WHERE task_id = ? AND platform_id = ?
            AND payload_json IS NOT NULL AND TRIM(payload_json) != ''
          """,
          (task_id, platform_id),
        ).fetchone()
      else:
        row = conn.execute(
          """
          SELECT COUNT(*) FROM collect_results
          WHERE task_id = ?
            AND payload_json IS NOT NULL AND TRIM(payload_json) != ''
          """,
          (task_id,),
        ).fetchone()
    return int(row[0]) if row else 0

  def iter_collect_results(
    self,
    task_id: int,
    platform_id: Optional[str] = None,
    batch_size: int = 500,
  ) -> Iterator[sqlite3.Row]:
    """按 id 升序分批读取可导出的结果行（含 payload_json）."""
    last_id = 0
    while True:
      with self._connect() as conn:
        if platform_id:
          rows = conn.execute(
            """
            SELECT * FROM collect_results
            WHERE task_id = ? AND platform_id = ? AND id > ?
              AND payload_json IS NOT NULL AND TRIM(payload_json) != ''
            ORDER BY id ASC
            LIMIT ?
            """,
            (task_id, platform_id, last_id, batch_size),
          ).fetchall()
        else:
          rows = conn.execute(
            """
            SELECT * FROM collect_results
            WHERE task_id = ? AND id > ?
              AND payload_json IS NOT NULL AND TRIM(payload_json) != ''
            ORDER BY id ASC
            LIMIT ?
            """,
            (task_id, last_id, batch_size),
          ).fetchall()
      if not rows:
        break
      for row in rows:
        last_id = int(row['id'])
        yield row

  def get_recent_logs(self, limit: int = 50, platform: Optional[str] = None) -> List[OperationLog]:
    with self._connect() as conn:
      if platform:
        rows = conn.execute(
          """
          SELECT * FROM operation_logs
          WHERE platform = ?
          ORDER BY created_at DESC
          LIMIT ?
          """,
          (platform, limit),
        ).fetchall()
      else:
        rows = conn.execute(
          """
          SELECT * FROM operation_logs
          ORDER BY created_at DESC
          LIMIT ?
          """,
          (limit,),
        ).fetchall()
    return [self._row_to_log(row) for row in rows]

  @staticmethod
  def _row_to_account(row: sqlite3.Row) -> Account:
    return Account(
      id=row['id'],
      platform=row['platform'],
      name=row['name'],
      status=row['status'],
      state_file_path=row['state_file_path'],
      created_at=_parse_datetime(row['created_at']),
      updated_at=_parse_datetime(row['updated_at']),
    )

  @staticmethod
  def _row_to_collect_task(row: sqlite3.Row) -> CollectTask:
    return CollectTask(
      id=row['id'],
      platform=row['platform'],
      account_id=row['account_id'],
      source_file=row['source_file'],
      total=row['total'],
      success_count=row['success_count'],
      status=row['status'],
      created_at=_parse_datetime(row['created_at']),
    )

  @staticmethod
  def _row_to_log(row: sqlite3.Row) -> OperationLog:
    return OperationLog(
      id=row['id'],
      operation_type=row['operation_type'],
      account_id=row['account_id'],
      platform=row['platform'],
      status=row['status'],
      message=row['message'],
      created_at=_parse_datetime(row['created_at']),
    )
