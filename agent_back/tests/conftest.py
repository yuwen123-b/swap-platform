"""pytest 公共工具：假数据库连接（不连真实 MySQL）。

各 service 通过 `from app.db.pool import connection` 获取连接，
测试中用 monkeypatch 把对应模块的 connection 替换为 make_connection(cursor)。
"""
import sys
from contextlib import contextmanager
from pathlib import Path

# 保证能 import app.*（agent_back 目录加入 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeCursor:
    """按预设结果队列返回的假游标：fetchone 依次弹出 rows。"""

    def __init__(self, rows=None, rowcount: int = 1, lastrowid: int = 1):
        self._rows = list(rows or [])
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.executed: list = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows = list(self._rows)
        self._rows.clear()
        return rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def make_connection(cursor: FakeCursor):
    """生成与 pool.connection 签名一致的上下文管理器工厂。"""

    @contextmanager
    def _conn():
        yield FakeConn(cursor)

    return _conn
