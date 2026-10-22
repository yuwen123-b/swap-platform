# -*- coding: utf-8 -*-
"""db.pool.get_pool 的 SSL 传参断言：本地不真连云库，只验证参数组装正确。"""
import pymysql
import pytest

from app.db import pool
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _fresh_pool_cache():
    """get_pool 带 lru_cache：每例先清缓存，避免上一例的实例串台。"""
    pool.get_pool.cache_clear()
    yield
    pool.get_pool.cache_clear()


def _capture_pooled_db(monkeypatch, captured):
    def fake_pooled_db(**kwargs):
        captured.update(kwargs)

        class _FakePool:
            def connection(self):
                raise RuntimeError("不应真正建立连接")

        return _FakePool()

    monkeypatch.setattr(pool, "PooledDB", fake_pooled_db)


def test_ssl_disabled_keeps_legacy_behavior(monkeypatch):
    """DB_SSL=false（本地默认）：不传 ssl 参数，行为与改造前完全一致。"""
    monkeypatch.setattr(pool.settings, "db_ssl", False)
    captured = {}
    _capture_pooled_db(monkeypatch, captured)
    pool.get_pool()
    assert "ssl" not in captured
    assert captured["host"] == pool.settings.db_host
    assert captured["cursorclass"] is pymysql.cursors.DictCursor


def test_ssl_enabled_without_ca_uses_encryption_only(monkeypatch):
    """DB_SSL=true 且无 CA：仅加密（等效 ssl_mode=REQUIRED），不校验证书。"""
    monkeypatch.setattr(pool.settings, "db_ssl", True)
    monkeypatch.setattr(pool.settings, "db_ssl_ca", "")
    captured = {}
    _capture_pooled_db(monkeypatch, captured)
    pool.get_pool()
    assert captured["ssl"] == {"check_hostname": False}


def test_ssl_enabled_with_ca_verifies_identity(monkeypatch):
    """DB_SSL=true + CA 路径：加密 + 服务端身份校验（Aiven 推荐级别）。"""
    monkeypatch.setattr(pool.settings, "db_ssl", True)
    monkeypatch.setattr(pool.settings, "db_ssl_ca", "certs/ca.pem")
    captured = {}
    _capture_pooled_db(monkeypatch, captured)
    pool.get_pool()
    assert captured["ssl"] == {"ca": "certs/ca.pem", "check_hostname": True}


def test_ssl_enabled_reads_env(monkeypatch, tmp_path):
    """端到端：环境变量 DB_SSL=true 能被 Settings 解析并传导到连接参数。"""
    monkeypatch.setenv("DB_SSL", "true")
    monkeypatch.setenv("DB_SSL_CA", "")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.db_ssl is True
        monkeypatch.setattr(pool, "settings", s)
        captured = {}
        _capture_pooled_db(monkeypatch, captured)
        pool.get_pool()
        assert captured["ssl"] == {"check_hostname": False}
    finally:
        get_settings.cache_clear()
