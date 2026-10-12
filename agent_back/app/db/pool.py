from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from dbutils.pooled_db import PooledDB
import pymysql
from app.core.config import settings


SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

@lru_cache
def get_pool() -> PooledDB:
    return PooledDB(
        creator=pymysql,
        maxconnections=settings.db_pool_max_connections,
        mincached=settings.db_pool_min_cached,
        maxcached=settings.db_pool_max_cached,
        blocking=True,
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset=settings.db_charset,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=settings.db_connect_timeout,
    )


@contextmanager
def connection():
    conn = get_pool().connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_schema() -> None:
    with connection() as conn:
        with conn.cursor() as cursor:
            for sql_file in sorted(SQL_DIR.glob("*.sql")):
                cursor.execute(sql_file.read_text(encoding="utf-8"))


def ensure_item_contact_column() -> None:
    """幂等迁移：item 表缺 contact 列时补齐（用户上传物品的联系方式）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'item' AND COLUMN_NAME = 'contact'"
            )
            if cursor.fetchone()["c"] == 0:
                cursor.execute(
                    "ALTER TABLE item ADD COLUMN contact VARCHAR(100) NULL COMMENT '联系方式'"
                )


def _ensure_column(cursor, table: str, column: str, ddl: str) -> None:
    """幂等加列：information_schema 判断列是否存在，不存在才执行 ddl。"""
    cursor.execute(
        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column),
    )
    if cursor.fetchone()["c"] == 0:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def ensure_accessibility_columns() -> None:
    """幂等迁移：无障碍/国际化/360° 所需的表结构变更。

    - user：mobility_level、accessibility_mode、preferred_lang
    - item：panorama_views、panorama_status
    - volunteer_task：志愿者代取任务表
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            _ensure_column(cursor, "user", "mobility_level",
                           "mobility_level VARCHAR(20) NOT NULL DEFAULT 'free' COMMENT '行动能力：free/limited/assisted'")
            _ensure_column(cursor, "user", "accessibility_mode",
                           "accessibility_mode VARCHAR(30) NOT NULL DEFAULT 'normal' COMMENT '无障碍模式：normal/visually_impaired/mobility_impaired'")
            _ensure_column(cursor, "user", "preferred_lang",
                           "preferred_lang VARCHAR(10) NOT NULL DEFAULT 'zh_CN' COMMENT '界面语言：zh_CN/en_US'")
            _ensure_column(cursor, "user", "elderly_mode",
                           "elderly_mode TINYINT NOT NULL DEFAULT 0 COMMENT '助老模式开关：0关 1开'")
            _ensure_column(cursor, "user", "high_contrast",
                           "high_contrast TINYINT NOT NULL DEFAULT 0 COMMENT '高对比度开关：0关 1开'")
            _ensure_column(cursor, "item", "panorama_views",
                           "panorama_views TEXT NULL COMMENT '360° 四视角图路径（JSON）'")
            _ensure_column(cursor, "item", "panorama_status",
                           "panorama_status VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT 'none/generating/ready/failed'")
            _ensure_column(cursor, "item", "panorama_generated_at",
                           "panorama_generated_at DATETIME NULL COMMENT '360° 生成完成时间'")
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS `volunteer_task` (
                       `id` BIGINT NOT NULL AUTO_INCREMENT,
                       `exchange_id` VARCHAR(64) NOT NULL COMMENT '关联的交换单号',
                       `requester_id` BIGINT NOT NULL COMMENT '委托人用户ID',
                       `volunteer_id` BIGINT NULL COMMENT '接单志愿者用户ID',
                       `item_id` BIGINT NULL COMMENT '代取物品ID',
                       `handover_method` VARCHAR(30) NOT NULL DEFAULT 'volunteer_pickup' COMMENT '交接方式',
                       `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/accepted/done/cancelled',
                       `note` VARCHAR(255) NULL COMMENT '备注',
                       `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                       `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                       PRIMARY KEY (`id`),
                       KEY `idx_requester` (`requester_id`),
                       KEY `idx_volunteer` (`volunteer_id`),
                       KEY `idx_status` (`status`)
                   ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
            )
