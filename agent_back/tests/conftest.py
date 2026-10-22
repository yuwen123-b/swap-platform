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


def stub_image_signer(monkeypatch):
    """把图片签名换成可读的桩 `/sign?<相对路径>`。

    「DB 只存相对路径 + 读取时现场签名」上线后，所有读取端返回的封面都是
    现场签名的 URL（带随时间变化的 exp/sig）。单测里用桩代替真实 HMAC：
    断言保持可读、不随密钥与时钟漂移，同时仍能校验「旧签名被剥掉、
    前缀被归一成相对路径」这一关键行为。
    """
    from app.services import image_utils

    monkeypatch.setattr(
        image_utils,
        "to_signed_url",
        lambda v: f"/sign?{image_utils.normalize_image_ref(v)}",
    )
